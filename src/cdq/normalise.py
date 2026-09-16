"""Field level normalisation for company records.

Every function here is pure and returns both the cleaned value and a status
flag. The status is what the quality report counts, so a field that cannot be
cleaned is never silently dropped.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Ordered longest first so that "PRIVATE LIMITED" is stripped before "LIMITED".
LEGAL_SUFFIXES = [
    "PRIVATE LIMITED",
    "PVT LTD",
    "LIMITED LIABILITY COMPANY",
    "INCORPORATED",
    "CORPORATION",
    "COMPANY",
    "HOLDINGS",
    "GROUP",
    "LLP",
    "LLC",
    "LTD",
    "INC",
    "CORP",
    "CO",
    "PLC",
    "GMBH",
    "SA",
    "NV",
    "BV",
]

STREET_ABBREVIATIONS = {
    "STREET": "ST",
    "AVENUE": "AVE",
    "BOULEVARD": "BLVD",
    "ROAD": "RD",
    "DRIVE": "DR",
    "LANE": "LN",
    "COURT": "CT",
    "PLACE": "PL",
    "SUITE": "STE",
    "APARTMENT": "APT",
    "FLOOR": "FL",
    "NORTH": "N",
    "SOUTH": "S",
    "EAST": "E",
    "WEST": "W",
}

_PUNCT = re.compile(r"[^A-Z0-9&\s]")
_WS = re.compile(r"\s+")
_EXTENSION = re.compile(r"(?:EXT|X|EXTENSION)\.?\s*(\d{1,6})\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class NormalisedName:
    canonical: str
    suffix: str | None
    status: str  # ok | empty


@dataclass(frozen=True)
class NormalisedPhone:
    e164: str | None
    extension: str | None
    status: str  # ok | too_short | too_long | empty | non_numeric


@dataclass(frozen=True)
class NormalisedAddress:
    line: str
    status: str  # ok | empty


def _strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalise_name(raw: str | None) -> NormalisedName:
    """Fold a business name to a comparable canonical form.

    Case, accents, punctuation and legal suffixes all vary between source
    systems for the same underlying company, so all four are removed. The
    suffix that was stripped is returned rather than discarded because it is
    weak evidence when two candidates are otherwise identical.
    """
    if raw is None or not raw.strip():
        return NormalisedName("", None, "empty")

    value = _strip_accents(raw).upper()
    value = value.replace("&", " AND ")
    value = _PUNCT.sub(" ", value)
    value = _WS.sub(" ", value).strip()

    removed: str | None = None
    changed = True
    while changed:
        changed = False
        for suffix in LEGAL_SUFFIXES:
            if value.endswith(" " + suffix):
                removed = removed or suffix
                value = value[: -(len(suffix) + 1)].strip()
                changed = True
                break

    # Stripping a suffix off "Acme Widgets & Co" leaves a dangling conjunction,
    # so drop trailing connectors once the suffixes are gone.
    while True:
        tokens = value.split()
        if tokens and tokens[-1] in {"AND", "OF", "THE"}:
            value = " ".join(tokens[:-1])
            continue
        break

    if not value:
        return NormalisedName("", removed, "empty")
    return NormalisedName(value, removed, "ok")


def normalise_phone(raw: str | None, default_country: str = "1") -> NormalisedPhone:
    """Reduce a phone number to digits with a country code, keeping extensions.

    Source systems store extensions inline in half a dozen formats. Pulling the
    extension out first stops it from inflating the digit count and being
    mistaken for a longer international number.
    """
    if raw is None or not str(raw).strip():
        return NormalisedPhone(None, None, "empty")

    text = str(raw).strip()
    extension = None
    match = _EXTENSION.search(text)
    if match:
        extension = match.group(1)
        text = text[: match.start()].strip()

    digits = re.sub(r"\D", "", text)
    if not digits:
        return NormalisedPhone(None, extension, "non_numeric")

    if text.strip().startswith("+"):
        pass
    elif len(digits) == 10:
        digits = default_country + digits
    elif len(digits) == 11 and digits.startswith("0"):
        digits = default_country + digits[1:]

    if len(digits) < 10:
        return NormalisedPhone(None, extension, "too_short")
    if len(digits) > 15:
        return NormalisedPhone(None, extension, "too_long")

    return NormalisedPhone("+" + digits, extension, "ok")


def normalise_address(raw: str | None) -> NormalisedAddress:
    """Standardise street type words so that address equality is usable."""
    if raw is None or not raw.strip():
        return NormalisedAddress("", "empty")

    value = _strip_accents(raw).upper()
    value = _PUNCT.sub(" ", value)
    tokens = [STREET_ABBREVIATIONS.get(token, token) for token in _WS.split(value) if token]
    line = " ".join(tokens).strip()
    if not line:
        return NormalisedAddress("", "empty")
    return NormalisedAddress(line, "ok")
