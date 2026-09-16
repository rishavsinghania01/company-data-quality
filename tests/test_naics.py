from pathlib import Path

import pytest

from cdq.naics import NaicsCrosswalk

CROSSWALK = Path(__file__).resolve().parents[1] / "data" / "naics_crosswalk_2012_2022.csv"


@pytest.fixture(scope="module")
def crosswalk():
    return NaicsCrosswalk.from_csv(CROSSWALK)


def test_crosswalk_loads_every_published_row(crosswalk):
    assert len(crosswalk) > 1000


def test_code_that_did_not_change_is_reported_as_unchanged(crosswalk):
    assert crosswalk.map_code("111110").status == "unchanged"


def test_unknown_code_is_flagged_rather_than_guessed(crosswalk):
    result = crosswalk.map_code("999999")
    assert result.status == "unknown"
    assert result.code_2022 is None


def test_blank_code_is_unknown(crosswalk):
    assert crosswalk.map_code("").status == "unknown"
    assert crosswalk.map_code(None).status == "unknown"
