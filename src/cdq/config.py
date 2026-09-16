"""Paths and tunables, resolved from environment variables with defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    warehouse_path: Path
    raw_dir: Path
    crosswalk_path: Path
    match_threshold: float
    seed: int
    entity_count: int

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(os.environ.get("CDQ_ROOT", PROJECT_ROOT))
        return cls(
            warehouse_path=Path(os.environ.get("CDQ_WAREHOUSE", root / "warehouse" / "cdq.duckdb")),
            raw_dir=Path(os.environ.get("CDQ_RAW_DIR", root / "warehouse" / "raw")),
            crosswalk_path=Path(
                os.environ.get("CDQ_CROSSWALK", root / "data" / "naics_crosswalk_2012_2022.csv")
            ),
            match_threshold=float(os.environ.get("CDQ_MATCH_THRESHOLD", "0.80")),
            seed=int(os.environ.get("CDQ_SEED", "20260916")),
            entity_count=int(os.environ.get("CDQ_ENTITY_COUNT", "2000")),
        )
