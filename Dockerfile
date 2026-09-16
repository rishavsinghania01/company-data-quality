# The Airflow image plus this project's Python dependencies, built once.
#
# The official image is extended rather than having pip run at container start,
# so that a broken dependency fails the build instead of the scheduler, and so
# that `docker compose up` on the second morning does not reinstall dbt.
# Pinning apache-airflow again in the same pip call is what the Airflow docs
# recommend: it stops pip from upgrading Airflow to satisfy a project pin.

FROM apache/airflow:2.10.4-python3.11

COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir "apache-airflow==2.10.4" -r /requirements.txt
