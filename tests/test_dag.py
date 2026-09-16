"""The DAG file parses and wires the stages in the right order.

Airflow is not a project dependency, it is the runtime the DAG is deployed
into, so this test only runs where Airflow is installed: inside the image
that docker-compose builds. CI runs it there. Locally it is skipped.
"""

import os
import sys

import pytest

pytest.importorskip("airflow", reason="only runs inside the Airflow image")

DAGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dags")

EXPECTED_ORDER = [
    "generate_sources",
    "load_raw_tables",
    "normalise_fields",
    "resolve_entities",
    "evaluate_resolution",
    "dbt_build",
    "quality_report",
]


def test_the_dag_imports_and_chains_the_stages_in_order():
    sys.path.insert(0, DAGS_DIR)
    import company_quality_pipeline as module

    dag = module.dag
    assert dag.dag_id == "company_quality_pipeline"
    assert sorted(dag.task_ids) == sorted(EXPECTED_ORDER)
    for upstream, downstream in zip(EXPECTED_ORDER, EXPECTED_ORDER[1:]):
        assert downstream in dag.get_task(upstream).downstream_task_ids, (upstream, downstream)
    assert dag.get_task("generate_sources").upstream_task_ids == set()
    assert dag.get_task("quality_report").downstream_task_ids == set()


def test_dbt_runs_from_the_binary_the_environment_points_at():
    # Inside the image CDQ_DBT_BIN is the virtualenv dbt; locally it is plain "dbt".
    sys.path.insert(0, DAGS_DIR)
    import company_quality_pipeline as module

    command = module.dag.get_task("dbt_build").bash_command
    expected_bin = os.environ.get("CDQ_DBT_BIN", "dbt")
    assert f"{expected_bin} build" in command
    assert command.startswith(f"cd {module.DBT_DIR} && ")
