.PHONY: install run test dbt clean airflow

install:
	pip install -r requirements.txt

run:
	PYTHONPATH=src python3 -m cdq.cli all

dbt:
	cd dbt && DBT_PROFILES_DIR=. dbt build

test:
	python3 -m pytest -q

clean:
	rm -rf warehouse dbt/target dbt/logs .pytest_cache
	find . -name __pycache__ -type d -exec rm -rf {} +

airflow:
	docker compose up
