# The Airflow image plus this project's Python dependencies, built once.
#
# The official image is extended rather than having pip run at container start,
# so that a broken dependency fails the build instead of the scheduler, and so
# that `docker compose up` on the second morning does not reinstall dbt.
#
# dbt does not go into Airflow's environment. dbt-core 1.12 requires
# protobuf >= 6 and Airflow 2.10's OpenTelemetry exporter requires protobuf < 5,
# so pip cannot install both in one place (CI proved it: ResolutionImpossible).
# dbt gets its own virtualenv and the DAG calls that binary through CDQ_DBT_BIN.
# duckdb is installed in both environments at the same pin, because both open
# the same warehouse file and DuckDB's file format follows the library version.
#
# All pins come from requirements.txt so there is one place to bump them.
# Pinning apache-airflow again in the same pip call is what the Airflow docs
# recommend: it stops pip from upgrading Airflow to satisfy a project pin.

FROM apache/airflow:2.10.4-python3.11

COPY requirements.txt /requirements.txt

RUN pip install --no-cache-dir "apache-airflow==2.10.4" \
        $(grep -E '^(duckdb|pytest)==' /requirements.txt)

# The image sets PIP_USER=true so that plain pip installs land in ~/.local;
# inside a virtualenv that flag makes pip refuse to install, so it is unset here.
RUN python -m venv /opt/airflow/dbt-venv \
    && PIP_USER=false /opt/airflow/dbt-venv/bin/pip install --no-cache-dir \
        $(grep -E '^(dbt-core|dbt-duckdb|duckdb)==' /requirements.txt)

ENV CDQ_DBT_BIN=/opt/airflow/dbt-venv/bin/dbt
