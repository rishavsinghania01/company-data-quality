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


def test_split_code_is_reported_as_ambiguous_with_its_candidates(crosswalk):
    # 541711 (Research and Development in Biotechnology) was split in 2022.
    # The record alone cannot say which half applies, so no code is chosen.
    result = crosswalk.map_code("541711")
    assert result.status == "ambiguous_split"
    assert result.code_2022 is None
    assert result.candidates == ("541713", "541714")


def test_every_split_in_the_published_crosswalk_is_ambiguous(crosswalk):
    split = sorted(code for code in crosswalk._rows if len({c for c, _ in crosswalk._rows[code] if c}) > 1)
    assert split == ["211111", "452112", "541711", "541712"]
    assert all(crosswalk.map_code(code).status == "ambiguous_split" for code in split)


def test_a_repeated_identical_row_is_not_a_split():
    # The same mapping listed twice is one mapping, not an ambiguity.
    crosswalk = NaicsCrosswalk({"111110": [("111110", "Soybean Farming"), ("111110", "Soybean Farming")]})
    assert crosswalk.map_code("111110").status == "unchanged"


def test_a_code_that_moved_is_remapped_with_no_candidates():
    crosswalk = NaicsCrosswalk({"454110": [("455110", "Department Stores")]})
    result = crosswalk.map_code("454110")
    assert result.status == "remapped"
    assert result.code_2022 == "455110"
    assert result.candidates == ()
