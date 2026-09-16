"""The Python half of the pipeline: normalise, resolve, evaluate, report.

These stages sit between raw and dbt. They are here rather than in SQL
because name folding, phone parsing and union-find clustering are all awkward
to express in SQL and easy to unit test in Python.
"""

from __future__ import annotations

from .config import Settings
from .evaluate import pair_errors, pairwise_metrics
from .matching import Candidate, cluster, compare_within_blocks, score_pair
from .naics import NaicsCrosswalk
from .normalise import normalise_address, normalise_name, normalise_phone
from .warehouse import connect

# Thresholds the evaluate stage sweeps so the chosen one can be defended with
# a curve rather than a shrug.
SWEEP_THRESHOLDS = (0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95)

SOURCE_COLUMNS = {
    "crm_export": {
        "record_id": "crm_id",
        "name": "account_name",
        "phone": "phone",
        "address": "street_address",
        "state": "state",
        "naics": "industry_code",
    },
    "registry_extract": {
        "record_id": "filing_id",
        "name": "legal_name",
        "phone": "contact_number",
        "address": "address_line_1",
        "state": "state_code",
        "naics": "naics_code",
    },
}


def normalise_records(settings: Settings) -> int:
    crosswalk = NaicsCrosswalk.from_csv(settings.crosswalk_path)
    connection = connect(settings.warehouse_path)
    try:
        connection.execute("DROP TABLE IF EXISTS intermediate.normalised_records")
        connection.execute(
            """
            CREATE TABLE intermediate.normalised_records (
                record_id        VARCHAR,
                source_system    VARCHAR,
                name_raw         VARCHAR,
                name_canonical   VARCHAR,
                name_suffix      VARCHAR,
                name_status      VARCHAR,
                phone_raw        VARCHAR,
                phone_e164       VARCHAR,
                phone_extension  VARCHAR,
                phone_status     VARCHAR,
                address_raw      VARCHAR,
                address_line     VARCHAR,
                address_status   VARCHAR,
                state_code       VARCHAR,
                naics_raw        VARCHAR,
                naics_2022       VARCHAR,
                naics_status     VARCHAR
            )
            """
        )

        rows: list[tuple] = []
        for source, columns in SOURCE_COLUMNS.items():
            selected = connection.execute(
                f"""
                SELECT {columns['record_id']}, {columns['name']}, {columns['phone']},
                       {columns['address']}, {columns['state']}, {columns['naics']}
                FROM raw.{source}
                """
            ).fetchall()
            for record_id, name, phone, address, state, naics in selected:
                cleaned_name = normalise_name(name)
                cleaned_phone = normalise_phone(phone)
                cleaned_address = normalise_address(address)
                mapped = crosswalk.map_code(naics)
                rows.append(
                    (
                        record_id,
                        source,
                        name,
                        cleaned_name.canonical,
                        cleaned_name.suffix,
                        cleaned_name.status,
                        phone,
                        cleaned_phone.e164,
                        cleaned_phone.extension,
                        cleaned_phone.status,
                        address,
                        cleaned_address.line,
                        cleaned_address.status,
                        (state or "").upper() or None,
                        naics,
                        mapped.code_2022,
                        mapped.status,
                    )
                )

        connection.executemany(
            "INSERT INTO intermediate.normalised_records VALUES (" + ",".join(["?"] * 17) + ")",
            rows,
        )
        return len(rows)
    finally:
        connection.close()


def _load_candidates(connection) -> list[Candidate]:
    selected = connection.execute(
        """
        SELECT record_id, name_canonical, state_code, phone_e164, address_line
        FROM intermediate.normalised_records
        WHERE name_status = 'ok'
        """
    ).fetchall()
    return [Candidate(*row) for row in selected]


def resolve_entities(settings: Settings) -> dict[str, int]:
    connection = connect(settings.warehouse_path)
    try:
        candidates = _load_candidates(connection)
        assignments = cluster(candidates, threshold=settings.match_threshold)
        pairs = compare_within_blocks(candidates, settings.match_threshold)

        connection.execute("DROP TABLE IF EXISTS intermediate.entity_clusters")
        connection.execute(
            "CREATE TABLE intermediate.entity_clusters (record_id VARCHAR, cluster_id VARCHAR)"
        )
        connection.executemany(
            "INSERT INTO intermediate.entity_clusters VALUES (?, ?)",
            list(assignments.items()),
        )

        connection.execute("DROP TABLE IF EXISTS intermediate.match_pairs")
        connection.execute(
            """
            CREATE TABLE intermediate.match_pairs (
                left_id VARCHAR, right_id VARCHAR, score DOUBLE, reasons VARCHAR
            )
            """
        )
        connection.executemany(
            "INSERT INTO intermediate.match_pairs VALUES (?, ?, ?, ?)",
            [(p.left_id, p.right_id, p.score, ", ".join(p.reasons)) for p in pairs],
        )

        return {
            "records": len(candidates),
            "clusters": len(set(assignments.values())),
            "accepted_pairs": len(pairs),
        }
    finally:
        connection.close()


def evaluate_resolution(settings: Settings) -> dict[str, object]:
    """Score the clusters in the warehouse against raw.ground_truth.

    Writes three tables under quality:

      resolution_accuracy        one row: pairwise precision, recall, F1 and the
                                 error counts at the configured threshold
      resolution_threshold_sweep the same metrics at each threshold in
                                 SWEEP_THRESHOLDS, which is the curve the
                                 configured value was chosen from
      resolution_errors          every missed pair and false merge, with both
                                 raw names, so a miss can be read rather than
                                 counted

    Skipped, with the tables left empty, when there is no ground truth. A real
    source has labels only if someone sat down and made them.
    """
    connection = connect(settings.warehouse_path)
    try:
        connection.execute("DROP TABLE IF EXISTS quality.resolution_accuracy")
        connection.execute("DROP TABLE IF EXISTS quality.resolution_threshold_sweep")
        connection.execute("DROP TABLE IF EXISTS quality.resolution_errors")
        connection.execute(
            """
            CREATE TABLE quality.resolution_accuracy (
                threshold DOUBLE, records INTEGER, true_entities INTEGER,
                predicted_clusters INTEGER, true_pairs INTEGER, predicted_pairs INTEGER,
                true_positive_pairs INTEGER, false_positive_pairs INTEGER,
                false_negative_pairs INTEGER, precision DOUBLE, recall DOUBLE, f1 DOUBLE,
                entities_split INTEGER, clusters_merging_entities INTEGER
            )
            """
        )
        connection.execute(
            "CREATE TABLE quality.resolution_threshold_sweep AS SELECT * FROM quality.resolution_accuracy"
        )
        connection.execute(
            """
            CREATE TABLE quality.resolution_errors (
                kind VARCHAR, left_id VARCHAR, right_id VARCHAR,
                left_name VARCHAR, right_name VARCHAR, score DOUBLE
            )
            """
        )

        has_truth = connection.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'raw' AND table_name = 'ground_truth'"
        ).fetchone()[0]
        if not has_truth:
            return {"status": "skipped", "reason": "no raw.ground_truth table"}

        truth = dict(connection.execute("SELECT record_id, entity_no FROM raw.ground_truth").fetchall())
        assigned = dict(connection.execute("SELECT record_id, cluster_id FROM intermediate.entity_clusters").fetchall())

        insert = "INSERT INTO quality.{} VALUES (" + ",".join(["?"] * 14) + ")"

        def row(threshold: float, metrics) -> tuple:
            return (
                threshold, metrics.records, metrics.true_entities, metrics.predicted_clusters,
                metrics.true_pairs, metrics.predicted_pairs, metrics.true_positive_pairs,
                metrics.false_positive_pairs, metrics.false_negative_pairs,
                metrics.precision, metrics.recall, metrics.f1,
                metrics.entities_split, metrics.clusters_merging_entities,
            )

        at_threshold = pairwise_metrics(truth, assigned)
        connection.execute(insert.format("resolution_accuracy"), row(settings.match_threshold, at_threshold))

        candidates = _load_candidates(connection)
        for threshold in SWEEP_THRESHOLDS:
            metrics = pairwise_metrics(truth, cluster(candidates, threshold=threshold))
            connection.execute(insert.format("resolution_threshold_sweep"), row(threshold, metrics))

        names = dict(connection.execute("SELECT record_id, name_raw FROM intermediate.normalised_records").fetchall())
        by_id = {candidate.record_id: candidate for candidate in candidates}

        def pair_score(left: str, right: str) -> float | None:
            if left in by_id and right in by_id:
                return score_pair(by_id[left], by_id[right]).score
            return None

        connection.executemany(
            "INSERT INTO quality.resolution_errors VALUES (?, ?, ?, ?, ?, ?)",
            [
                (e.kind, e.left_id, e.right_id, names.get(e.left_id), names.get(e.right_id),
                 pair_score(e.left_id, e.right_id))
                for e in pair_errors(truth, assigned)
            ],
        )

        return {
            "threshold": settings.match_threshold,
            "precision": at_threshold.precision,
            "recall": at_threshold.recall,
            "f1": at_threshold.f1,
            "false_merges": at_threshold.false_positive_pairs,
            "missed_pairs": at_threshold.false_negative_pairs,
        }
    finally:
        connection.close()


QUALITY_SQL = """
DROP TABLE IF EXISTS quality.field_quality;
CREATE TABLE quality.field_quality AS
WITH base AS (SELECT * FROM intermediate.normalised_records)
SELECT source_system, 'name' AS field, 'completeness' AS dimension,
       count(*) AS records,
       count(*) FILTER (WHERE name_status = 'ok') AS passing
FROM base GROUP BY 1
UNION ALL
SELECT source_system, 'phone', 'validity',
       count(*), count(*) FILTER (WHERE phone_status = 'ok')
FROM base GROUP BY 1
UNION ALL
SELECT source_system, 'address', 'completeness',
       count(*), count(*) FILTER (WHERE address_status = 'ok')
FROM base GROUP BY 1
UNION ALL
SELECT source_system, 'naics', 'validity',
       count(*), count(*) FILTER (WHERE naics_status IN ('unchanged', 'remapped'))
FROM base GROUP BY 1;

DROP TABLE IF EXISTS quality.source_scorecard;
CREATE TABLE quality.source_scorecard AS
SELECT
    source_system,
    sum(records)  AS checks_run,
    sum(passing)  AS checks_passed,
    round(100.0 * sum(passing) / nullif(sum(records), 0), 2) AS quality_score_pct
FROM quality.field_quality
GROUP BY 1
ORDER BY 1;
"""


def build_quality_report(settings: Settings) -> list[tuple]:
    connection = connect(settings.warehouse_path)
    try:
        for statement in [s for s in QUALITY_SQL.split(";") if s.strip()]:
            connection.execute(statement)
        return connection.execute("SELECT * FROM quality.source_scorecard").fetchall()
    finally:
        connection.close()
