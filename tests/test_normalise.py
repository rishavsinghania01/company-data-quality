import pytest

from cdq.normalise import normalise_address, normalise_name, normalise_phone


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Acme Widgets Inc.", "ACME WIDGETS"),
        ("ACME WIDGETS LLC", "ACME WIDGETS"),
        ("  Acmé  Widgets & Co., Inc. ", "ACME WIDGETS"),
        ("Acme Widgets Private Limited", "ACME WIDGETS"),
        ("Northwind Traders", "NORTHWIND TRADERS"),
    ],
)
def test_name_variants_fold_to_one_canonical_form(raw, expected):
    assert normalise_name(raw).canonical == expected


def test_name_keeps_the_suffix_it_removed():
    assert normalise_name("Acme Widgets LLC").suffix == "LLC"


def test_blank_name_is_flagged_not_dropped():
    result = normalise_name("   ")
    assert result.status == "empty"
    assert result.canonical == ""


@pytest.mark.parametrize(
    "raw,e164",
    [
        ("(415) 555-0123", "+14155550123"),
        ("415-555-0123", "+14155550123"),
        ("+1 415 555 0123", "+14155550123"),
        ("4155550123", "+14155550123"),
    ],
)
def test_phone_formats_reduce_to_the_same_e164(raw, e164):
    assert normalise_phone(raw).e164 == e164


def test_phone_extension_is_separated_before_counting_digits():
    result = normalise_phone("415.555.0123 ext 42")
    assert result.e164 == "+14155550123"
    assert result.extension == "42"
    assert result.status == "ok"


def test_short_phone_is_rejected_with_a_reason():
    result = normalise_phone("555-0123")
    assert result.e164 is None
    assert result.status == "too_short"


def test_address_street_types_are_standardised():
    assert normalise_address("742 Evergreen Terrace, Suite 4").line == "742 EVERGREEN TERRACE STE 4"
    assert normalise_address("15 North Maple Street").line == "15 N MAPLE ST"
