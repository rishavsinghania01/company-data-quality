"""Command line entry point.

Each stage is callable on its own so that the Airflow tasks and a local run
execute exactly the same code path.
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import Settings
from .ingest import build_sources, load_raw
from .pipeline import build_quality_report, evaluate_resolution, normalise_records, resolve_entities

STAGES = {
    "generate": lambda s: build_sources(s),
    "load-raw": lambda s: load_raw(s),
    "normalise": lambda s: {"rows": normalise_records(s)},
    "resolve": lambda s: resolve_entities(s),
    "evaluate": lambda s: evaluate_resolution(s),
    "quality": lambda s: {"scorecard": build_quality_report(s)},
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cdq")
    parser.add_argument("stage", choices=sorted(STAGES) + ["all"])
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    stages = list(STAGES) if args.stage == "all" else [args.stage]

    for stage in stages:
        result = STAGES[stage](settings)
        print(f"{stage}: {json.dumps(result, default=str)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
