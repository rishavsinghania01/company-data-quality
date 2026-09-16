from cdq.evaluate import pair_errors, pairwise_metrics

# Five records, three real companies: A has three records, B has two, C has one.
TRUTH = {"a1": "A", "a2": "A", "a3": "A", "b1": "B", "b2": "B", "c1": "C"}


def test_perfect_clustering_scores_one_on_everything():
    predicted = {"a1": "x", "a2": "x", "a3": "x", "b1": "y", "b2": "y", "c1": "z"}
    m = pairwise_metrics(TRUTH, predicted)
    assert (m.precision, m.recall, m.f1) == (1.0, 1.0, 1.0)
    assert m.true_pairs == 4  # three pairs inside A, one inside B
    assert m.predicted_pairs == 4
    assert m.entities_split == 0
    assert m.clusters_merging_entities == 0
    assert pair_errors(TRUTH, predicted) == []


def test_a_split_entity_costs_recall_not_precision():
    # a3 has been left on its own. The two pairs (a1, a3) and (a2, a3) are missed.
    predicted = {"a1": "x", "a2": "x", "a3": "w", "b1": "y", "b2": "y", "c1": "z"}
    m = pairwise_metrics(TRUTH, predicted)
    assert m.precision == 1.0
    assert m.recall == 0.5  # 2 of 4 true pairs found
    assert m.false_negative_pairs == 2
    assert m.entities_split == 1
    kinds = {(e.left_id, e.right_id): e.kind for e in pair_errors(TRUTH, predicted)}
    assert kinds == {("a1", "a3"): "missed", ("a2", "a3"): "missed"}


def test_a_false_merge_costs_precision_not_recall():
    # c1 has been merged into B's cluster, creating two pairs that are not real.
    predicted = {"a1": "x", "a2": "x", "a3": "x", "b1": "y", "b2": "y", "c1": "y"}
    m = pairwise_metrics(TRUTH, predicted)
    assert m.recall == 1.0
    assert m.predicted_pairs == 6
    assert m.false_positive_pairs == 2
    assert m.precision == round(4 / 6, 4)
    assert m.clusters_merging_entities == 1
    kinds = {(e.left_id, e.right_id): e.kind for e in pair_errors(TRUTH, predicted)}
    assert kinds == {("b1", "c1"): "false_merge", ("b2", "c1"): "false_merge"}


def test_every_record_in_its_own_cluster_is_zero_recall():
    predicted = {record_id: record_id for record_id in TRUTH}
    m = pairwise_metrics(TRUTH, predicted)
    assert m.recall == 0.0
    assert m.predicted_pairs == 0
    assert m.precision == 1.0  # nothing predicted, so nothing predicted wrongly
    assert m.f1 == 0.0


def test_records_without_a_label_are_not_scored():
    predicted = {"a1": "x", "a2": "x", "unlabelled": "x"}
    m = pairwise_metrics(TRUTH, predicted)
    assert m.records == 2
    assert m.predicted_pairs == 1
    assert m.precision == 1.0
