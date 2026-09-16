"""NAICS vintage mapping.

Source systems were populated at different times, so the same establishment can
carry a 2012 code in one system and a 2022 code in another. Comparing industry
across sources means putting both on the same vintage first.

The crosswalk is the published Census 2012 to 2022 concordance.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MappedCode:
    code_2022: str | None
    title_2022: str | None
    status: str  # unchanged | remapped | retired | unknown


class NaicsCrosswalk:
    def __init__(self, rows: dict[str, tuple[str | None, str | None]]) -> None:
        self._rows = rows
        self._valid_2022 = {
            code for code, _ in rows.values() if code
        }

    @classmethod
    def from_csv(cls, path: str | Path) -> "NaicsCrosswalk":
        rows: dict[str, tuple[str | None, str | None]] = {}
        with open(path, newline="", encoding="utf-8-sig") as handle:
            for record in csv.DictReader(handle):
                code_2012 = (record.get("2012 NAICS Code") or "").strip()
                if not code_2012:
                    continue
                code_2022 = (record.get("2022 NAICS Code") or "").strip() or None
                title_2022 = (record.get("2022 NAICS Title") or "").strip() or None
                rows[code_2012] = (code_2022, title_2022)
        return cls(rows)

    def map_code(self, code: str | None) -> MappedCode:
        if code is None or not str(code).strip():
            return MappedCode(None, None, "unknown")

        code = str(code).strip()
        if code in self._rows:
            code_2022, title_2022 = self._rows[code]
            if code_2022 is None:
                return MappedCode(None, None, "retired")
            if code_2022 == code:
                return MappedCode(code_2022, title_2022, "unchanged")
            return MappedCode(code_2022, title_2022, "remapped")

        # Already on the 2022 vintage, so it is valid but absent from the
        # left hand side of the crosswalk.
        if code in self._valid_2022:
            return MappedCode(code, None, "unchanged")

        return MappedCode(None, None, "unknown")

    def __len__(self) -> int:
        return len(self._rows)
