"""Land the source files and the crosswalk into the raw schema.

Raw tables are loaded as text with no casting. Anything that parses the value
belongs downstream, so that a bad value shows up as a failed test in staging
rather than as a load error with no record of what arrived.
"""

from __future__ import annotations

from pathlib import Path

from .config import Settings
from .generate import generate
from .naics import NaicsCrosswalk
from .warehouse import connect

RAW_SOURCES = {
    "crm_export": "crm_export.csv",
    "registry_extract": "registry_extract.csv",
}


def build_sources(settings: Settings) -> dict[str, int]:
    crosswalk = NaicsCrosswalk.from_csv(settings.crosswalk_path)
    codes = sorted(crosswalk._rows.keys())  # noqa: SLF001 - generator needs real codes
    return generate(settings.raw_dir, codes, seed=settings.seed, entity_count=settings.entity_count)


def load_raw(settings: Settings) -> dict[str, int]:
    connection = connect(settings.warehouse_path)
    counts: dict[str, int] = {}
    try:
        for table, filename in RAW_SOURCES.items():
            path = Path(settings.raw_dir) / filename
            connection.execute(f"DROP TABLE IF EXISTS raw.{table}")
            connection.execute(
                f"""
                CREATE TABLE raw.{table} AS
                SELECT * FROM read_csv_auto('{path.as_posix()}', header=true, all_varchar=true)
                """
            )
            counts[table] = connection.execute(f"SELECT count(*) FROM raw.{table}").fetchone()[0]

        connection.execute("DROP TABLE IF EXISTS raw.naics_crosswalk")
        connection.execute(
            f"""
            CREATE TABLE raw.naics_crosswalk AS
            SELECT
                "2012 NAICS Code"  AS code_2012,
                "2012 NAICS Title" AS title_2012,
                "2022 NAICS Code"  AS code_2022,
                "2022 NAICS Title" AS title_2022
            FROM read_csv_auto('{Path(settings.crosswalk_path).as_posix()}', header=true, all_varchar=true)
            """
        )
        counts["naics_crosswalk"] = connection.execute(
            "SELECT count(*) FROM raw.naics_crosswalk"
        ).fetchone()[0]
    finally:
        connection.close()
    return counts
