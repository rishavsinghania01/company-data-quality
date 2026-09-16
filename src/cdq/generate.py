"""Deterministic source data generator.

Two systems are simulated: a CRM export maintained by hand, and a registry
extract loaded from a filing feed. They overlap on roughly half their
companies, and the overlap is where the interesting work is.

The dirt is deliberate. Each pattern below exists because it is the kind of
thing that actually breaks a join:

  - the same company written with different legal suffixes
  - names with punctuation, accents and ampersands
  - phone numbers in six formats, some with extensions, some too short
  - addresses with spelled out street types
  - industry codes on two different NAICS vintages
  - a slice of rows with missing fields

Seeded so that a run is reproducible and the tests can assert exact counts.
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

BASE_NAMES = [
    "Acme Widgets", "Northwind Traders", "Contoso Manufacturing", "Fabrikam Logistics",
    "Tailspin Toys", "Wingtip Components", "Litware Foods", "Proseware Metals",
    "Adventure Works", "Blue Yonder Freight", "Coho Vineyards", "Fourth Coffee",
    "Graphic Design Institute", "Humongous Insurance", "Lucerne Publishing",
    "Margie Travel", "Nod Publishers", "Southridge Video", "Trey Research",
    "Woodgrove Bank", "Alpine Ski House", "City Power and Light", "Consolidated Messenger",
    "Fine Artists", "Lamna Healthcare", "Relecloud Systems", "School of Fine Art",
    "Tasteful Provisions", "VanArsdel Retail", "World Wide Importers",
]

SUFFIXES = ["Inc.", "LLC", "Ltd", "Corporation", "Co.", "Incorporated", "L.L.C.", ""]
STATES = ["CA", "NY", "TX", "IL", "WA", "MA", "GA", "OH", "NC", "AZ"]
STREET_TYPES = ["Street", "Avenue", "Boulevard", "Road", "Drive", "Lane"]
STREET_NAMES = ["Evergreen", "Maple", "Oak", "Cedar", "Industrial", "Harbor", "Mission", "Lincoln"]


def _phone_variant(rng: random.Random, digits: str) -> str:
    area, exchange, line = digits[:3], digits[3:6], digits[6:]
    style = rng.randint(0, 5)
    if style == 0:
        return f"({area}) {exchange}-{line}"
    if style == 1:
        return f"{area}-{exchange}-{line}"
    if style == 2:
        return f"+1 {area} {exchange} {line}"
    if style == 3:
        return f"{area}.{exchange}.{line} ext {rng.randint(10, 999)}"
    if style == 4:
        return digits
    return f"{exchange}-{line}"  # deliberately short, fails validation


def _name_variant(rng: random.Random, base: str) -> str:
    variant = base
    if rng.random() < 0.25:
        variant = variant.replace(" and ", " & ")
    if rng.random() < 0.15:
        variant = variant.upper()
    if rng.random() < 0.10:
        variant = "  " + variant + " "
    suffix = rng.choice(SUFFIXES)
    return (variant + " " + suffix).strip() if suffix else variant


REGIONS = [
    "Pacific", "Atlantic", "Midwest", "Northern", "Southern", "Eastern", "Western",
    "Central", "Coastal", "Highland", "Summit", "Riverside", "Lakeside", "Union",
]

SEGMENTS = [
    "Industries", "Partners", "Solutions", "Systems", "Enterprises", "Works",
    "Supply", "Distribution", "Services", "Brands",
]


def _company_universe(rng: random.Random, count: int) -> list[str]:
    """Build a name space large enough that blocking has something to do."""
    names: set[str] = set(BASE_NAMES)
    while len(names) < count:
        names.add(f"{rng.choice(REGIONS)} {rng.choice(BASE_NAMES).split()[0]} {rng.choice(SEGMENTS)}")
    return sorted(names)[:count]


def generate(
    out_dir: str | Path,
    naics_codes: list[str],
    seed: int = 20260916,
    entity_count: int = 2000,
) -> dict[str, int]:
    """Write crm_export.csv and registry_extract.csv. Returns row counts."""
    rng = random.Random(seed)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    entities = []
    for index, base in enumerate(_company_universe(rng, entity_count), start=1):
        digits = f"{rng.randint(200, 989)}{rng.randint(200, 989)}{rng.randint(1000, 9999)}"
        entities.append(
            {
                "entity_no": index,
                "base_name": base,
                "state": rng.choice(STATES),
                "digits": digits,
                "street": f"{rng.randint(1, 9999)} {rng.choice(STREET_NAMES)} {rng.choice(STREET_TYPES)}",
                "naics": rng.choice(naics_codes),
            }
        )

    crm_rows = []
    registry_rows = []

    for entity in entities:
        in_crm = rng.random() < 0.80
        in_registry = rng.random() < 0.75
        if not in_crm and not in_registry:
            in_crm = True

        if in_crm:
            crm_rows.append(
                {
                    "crm_id": f"CRM{entity['entity_no']:05d}",
                    "account_name": _name_variant(rng, entity["base_name"]),
                    "phone": _phone_variant(rng, entity["digits"]),
                    "street_address": entity["street"],
                    "state": entity["state"],
                    "industry_code": entity["naics"],
                    "updated_at": f"2026-0{rng.randint(1,9)}-{rng.randint(10,28)}",
                }
            )
        if in_registry:
            registry_rows.append(
                {
                    "filing_id": f"REG{entity['entity_no']:05d}",
                    "legal_name": _name_variant(rng, entity["base_name"]),
                    "contact_number": _phone_variant(rng, entity["digits"]),
                    "address_line_1": entity["street"],
                    "state_code": entity["state"].lower() if rng.random() < 0.3 else entity["state"],
                    "naics_code": entity["naics"],
                    "filed_on": f"2025-{rng.randint(10,12)}-{rng.randint(10,28)}",
                }
            )

    # A small number of rows lose a field entirely. Real extracts always have
    # these and the quality report is there to count them.
    for row in rng.sample(crm_rows, k=max(1, len(crm_rows) // 8)):
        row[rng.choice(["phone", "street_address", "industry_code"])] = ""
    for row in rng.sample(registry_rows, k=max(1, len(registry_rows) // 8)):
        row[rng.choice(["contact_number", "address_line_1", "naics_code"])] = ""

    # A handful of duplicate filings, which is what the uniqueness check finds.
    for row in rng.sample(registry_rows, k=max(1, len(registry_rows) // 10)):
        duplicate = dict(row)
        duplicate["filing_id"] = row["filing_id"].replace("REG", "RGX")
        registry_rows.append(duplicate)

    rng.shuffle(crm_rows)
    rng.shuffle(registry_rows)

    _write_csv(out_dir / "crm_export.csv", crm_rows)
    _write_csv(out_dir / "registry_extract.csv", registry_rows)
    return {"crm_export": len(crm_rows), "registry_extract": len(registry_rows)}


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
