"""Scoring the resolver against labelled data.

Entity resolution is judged on pairs of records, not on records. Two records
that belong to the same real company form a true pair; two records the
resolver put in the same cluster form a predicted pair. Precision is the share
of predicted pairs that are true, recall is the share of true pairs that were
predicted, and every merge mistake shows up as one or the other:

  - a false merge (two companies in one cluster) creates predicted pairs that
    are not true pairs, so it lowers precision
  - a split entity (one company across two clusters) leaves true pairs
    unpredicted, so it lowers recall

The functions here are pure so that the arithmetic can be unit tested on five
records, and the same code then runs over the warehouse in the evaluate stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations


@dataclass(frozen=True)
class ResolutionMetrics:
    records: int
    true_entities: int
    predicted_clusters: int
    true_pairs: int
    predicted_pairs: int
    true_positive_pairs: int
    false_positive_pairs: int
    false_negative_pairs: int
    precision: float
    recall: float
    f1: float
    entities_split: int  # true entities spread over more than one cluster
    clusters_merging_entities: int  # clusters holding more than one true entity


@dataclass(frozen=True)
class PairError:
    left_id: str
    right_id: str
    kind: str  # missed | false_merge


def _pairs_within(groups: dict[object, list[str]]) -> int:
    return sum(len(members) * (len(members) - 1) // 2 for members in groups.values())


def _group(mapping: dict[str, object]) -> dict[object, list[str]]:
    groups: dict[object, list[str]] = {}
    for record_id, key in mapping.items():
        groups.setdefault(key, []).append(record_id)
    return groups


def pairwise_metrics(truth: dict[str, object], predicted: dict[str, str]) -> ResolutionMetrics:
    """Pairwise precision, recall and F1 of a clustering against labels.

    ``truth`` maps record id to the entity it really belongs to, ``predicted``
    maps record id to the cluster the resolver assigned. Only records present
    in both are scored, so a record the resolver dropped counts against
    nothing here; the dbt test assert_every_record_has_a_cluster is what
    catches that.
    """
    scored = {record_id: truth[record_id] for record_id in predicted if record_id in truth}
    predicted = {record_id: predicted[record_id] for record_id in scored}

    truth_groups = _group(scored)
    predicted_groups = _group(predicted)

    # A true positive pair is one that sits in the same true entity and the
    # same cluster, which is a pair inside the intersection of the two groups.
    intersections: dict[tuple[object, str], int] = {}
    for record_id, entity in scored.items():
        key = (entity, predicted[record_id])
        intersections[key] = intersections.get(key, 0) + 1
    true_positive = sum(n * (n - 1) // 2 for n in intersections.values())

    true_pairs = _pairs_within(truth_groups)
    predicted_pairs = _pairs_within(predicted_groups)
    false_positive = predicted_pairs - true_positive
    false_negative = true_pairs - true_positive

    precision = true_positive / predicted_pairs if predicted_pairs else 1.0
    recall = true_positive / true_pairs if true_pairs else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    entities_split = sum(
        1 for members in truth_groups.values() if len({predicted[m] for m in members}) > 1
    )
    clusters_merging = sum(
        1 for members in predicted_groups.values() if len({scored[m] for m in members}) > 1
    )

    return ResolutionMetrics(
        records=len(scored),
        true_entities=len(truth_groups),
        predicted_clusters=len(predicted_groups),
        true_pairs=true_pairs,
        predicted_pairs=predicted_pairs,
        true_positive_pairs=true_positive,
        false_positive_pairs=false_positive,
        false_negative_pairs=false_negative,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        entities_split=entities_split,
        clusters_merging_entities=clusters_merging,
    )


def pair_errors(truth: dict[str, object], predicted: dict[str, str]) -> list[PairError]:
    """Every wrong pair, named, so that a miss can be looked at rather than counted.

    Missed pairs are enumerated inside true entities and false merges inside
    predicted clusters, so the cost is proportional to the group sizes rather
    than to the number of records squared.
    """
    scored = {record_id: truth[record_id] for record_id in predicted if record_id in truth}
    errors: list[PairError] = []

    for members in _group(scored).values():
        for left, right in combinations(sorted(members), 2):
            if predicted[left] != predicted[right]:
                errors.append(PairError(left, right, "missed"))

    for members in _group({r: predicted[r] for r in scored}).values():
        for left, right in combinations(sorted(members), 2):
            if scored[left] != scored[right]:
                errors.append(PairError(left, right, "false_merge"))

    return errors
