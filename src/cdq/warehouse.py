"""Warehouse access.

DuckDB by default so the project runs with no database server. The dbt profile
points at the same file, which is why the Python stages and the dbt models can
hand work to each other.
"""

from __future__ import annotations

from pathlib import Path

import duckdb


def connect(path: str | Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(path))
    for schema in ("raw", "intermediate", "quality"):
        connection.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    return connection
