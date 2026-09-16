"""Daily company data quality pipeline.

Six tasks in a line: build the source extracts, land them raw, normalise the
fields, resolve entities, build the warehouse models with dbt, then run the
dbt tests. The Python stages call the same functions the CLI calls, so a local
`make run` and a scheduled run execute identical code.

The dbt steps are BashOperator rather than a dbt provider on purpose. It keeps
the dependency surface to dbt itself and makes the command reproducible outside
Airflow, which matters when you are debugging a model at 2am.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

PROJECT_ROOT = os.environ.get("CDQ_ROOT", "/opt/airflow/project")
DBT_DIR = os.path.join(PROJECT_ROOT, "dbt")

DEFAULT_ARGS = {
    "owner": "data-platform",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "depends_on_past": False,
}


def _stage(name: str):
    """Import inside the callable so the scheduler does not pay for it on parse."""

    def run(**_):
        import sys

        sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
        from cdq.config import Settings
        from cdq.ingest import build_sources, load_raw
        from cdq.pipeline import build_quality_report, normalise_records, resolve_entities

        settings = Settings.from_env()
        handlers = {
            "generate": build_sources,
            "load_raw": load_raw,
            "normalise": normalise_records,
            "resolve": resolve_entities,
            "quality": build_quality_report,
        }
        return handlers[name](settings)

    return run


with DAG(
    dag_id="company_quality_pipeline",
    description="Normalise, resolve and quality check company records from two source systems",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2026, 1, 1),
    schedule="0 6 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["data-quality", "dbt", "entity-resolution"],
) as dag:

    generate_sources = PythonOperator(
        task_id="generate_sources",
        python_callable=_stage("generate"),
    )

    load_raw_tables = PythonOperator(
        task_id="load_raw_tables",
        python_callable=_stage("load_raw"),
    )

    normalise_fields = PythonOperator(
        task_id="normalise_fields",
        python_callable=_stage("normalise"),
    )

    resolve_entities_task = PythonOperator(
        task_id="resolve_entities",
        python_callable=_stage("resolve"),
    )

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"cd {DBT_DIR} && dbt build --no-use-colors",
        env={"DBT_PROFILES_DIR": DBT_DIR, **os.environ},
    )

    quality_report = PythonOperator(
        task_id="quality_report",
        python_callable=_stage("quality"),
    )

    (
        generate_sources
        >> load_raw_tables
        >> normalise_fields
        >> resolve_entities_task
        >> dbt_build
        >> quality_report
    )
