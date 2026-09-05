"""Unit tests for ``client_upload`` (coercion, validation, SCTCase orchestration)."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import cast

import pytest
from hypothesis import given
from hypothesis import strategies as st

from client_upload import (
    NATURE_OF_DISPUTE_CHOICES,
    FieldExtractor,
    SCTCase,
    _fetch_extractor_answers,
    _to_datetime,
    _to_decimal,
)


def full_mapping() -> dict[str, str]:
    return {
        "claimant_name": "Alicia Tan",
        "claimant_nric": "S8123456A",
        "respondent_name": "Beng Motors Pte Ltd",
        "nature_of_dispute": "Contract for provision of services",
        "claim_amount": "$2,500.00",
        "date_of_cause_of_action": "2025-11-30",
        "contract_date": "2025-08-01",
        "particulars": "Gearbox repair services paid but never completed.",
    }


# --------------------------------------------------------------------------- #
# _to_decimal
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10000.00", Decimal("10000.00")),
        ("$10,000", Decimal("10000.00")),
        ("$10,000.00", Decimal("10000.00")),
        ("  1 000  ", Decimal("1000.00")),
        (".001", Decimal("0.00")),
        ("0", Decimal("0.00")),
        ("-42.5", Decimal("-42.50")),
    ],
)
def test_to_decimal_accepts_formatted_amounts(raw: str, expected: Decimal) -> None:
    assert _to_decimal(raw, "claim_amount") == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "-", ".", "None", "null", "unknown", "garbage", "1,2,3x"],
)
def test_to_decimal_rejects_unusable_amounts(raw: str) -> None:
    with pytest.raises(ValueError):
        _to_decimal(raw, "claim_amount")


@given(st.text(max_size=40, alphabet="0123456789$,. "))
def test_to_decimal_quantizes_when_it_accepts(raw: str) -> None:
    try:
        amount = _to_decimal(raw, "claim_amount")
    except ValueError:
        return
    assert amount == amount.quantize(Decimal("0.01"))


# --------------------------------------------------------------------------- #
# _to_datetime
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2025-11-30", datetime.fromisoformat("2025-11-30")),
        ("2025-11-30T14:05:06", datetime.fromisoformat("2025-11-30T14:05:06")),
        ("2025-08-01T00:00:00", datetime.fromisoformat("2025-08-01T00:00:00")),
    ],
)
def test_to_datetime_accepts_iso_forms(raw: str, expected: datetime) -> None:
    assert _to_datetime(raw, "field") == expected


@pytest.mark.parametrize("raw", ["", "  ", "2025-13-01", "not-a-date", "30/11/2025"])
def test_to_datetime_rejects_bad_values(raw: str) -> None:
    with pytest.raises(ValueError):
        _to_datetime(raw, "field")


@given(st.datetimes(timezones=st.none()))
def test_to_datetime_roundtrips_isoformat(value: datetime) -> None:
    assert _to_datetime(value.isoformat(), "field") == value


# --------------------------------------------------------------------------- #
# _fetch_extractor_answers
# --------------------------------------------------------------------------- #


def test_fetch_extractor_answers_passes_through_valid_dict() -> None:
    mapping = {"claimant_name": "A"}
    assert _fetch_extractor_answers(lambda _text: mapping, "x") is mapping


def test_fetch_extractor_answers_rejects_non_dict() -> None:
    with pytest.raises(TypeError):
        _fetch_extractor_answers(
            cast(FieldExtractor, lambda _text: ["nope"]), "x"
        )


def test_fetch_extractor_answers_rejects_non_str_values() -> None:
    with pytest.raises(TypeError):
        _fetch_extractor_answers(
            cast(FieldExtractor, lambda _text: {"claim_amount": 42}), "x"
        )


# --------------------------------------------------------------------------- #
# SCTCase.from_text / from_upload_file
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("blank", ["", "   \n\t  "])
def test_from_text_rejects_blank_upload(blank: str) -> None:
    with pytest.raises(ValueError):
        SCTCase.from_text(blank, extractor=lambda _text: full_mapping())


def test_from_text_builds_typed_case() -> None:
    case = SCTCase.from_text("upload body", extractor=lambda _text: full_mapping())
    assert case.claimant_name == "Alicia Tan"
    assert case.claimant_nric == "S8123456A"
    assert case.respondent_name == "Beng Motors Pte Ltd"
    assert case.nature_of_dispute == "Contract for provision of services"
    assert case.claim_amount == Decimal("2500.00")
    assert case.date_of_cause_of_action == datetime.fromisoformat("2025-11-30")
    assert case.contract_date == datetime.fromisoformat("2025-08-01")
    assert case.particulars


def test_from_upload_file_reads_bom_text(tmp_path) -> None:
    upload = tmp_path / "claim.txt"
    upload.write_text('\ufeffAlicia Tan\n', encoding="utf-8")
    case = SCTCase.from_upload_file(upload, extractor=lambda _text: full_mapping())
    assert case.claimant_name == "Alicia Tan"


def test_from_upload_file_missing_path_raises(tmp_path) -> None:
    missing = tmp_path / "nope.txt"
    with pytest.raises(OSError):
        SCTCase.from_upload_file(missing, extractor=lambda _text: full_mapping())


# --------------------------------------------------------------------------- #
# SCTCase._from_mapping
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("field", ["claimant_name", "claimant_nric", "respondent_name", "particulars"])
def test_from_mapping_blank_text_fields_become_none(field: str) -> None:
    mapping = full_mapping()
    mapping[field] = ""
    assert getattr(SCTCase._from_mapping(mapping), field) is None


def test_from_mapping_blank_optional_typed_fields_become_none() -> None:
    mapping = full_mapping()
    mapping["claim_amount"] = ""
    mapping["date_of_cause_of_action"] = ""
    mapping["contract_date"] = ""
    case = SCTCase._from_mapping(mapping)
    assert case.claim_amount is None
    assert case.date_of_cause_of_action is None
    assert case.contract_date is None


@pytest.mark.parametrize("choice", list(NATURE_OF_DISPUTE_CHOICES))
def test_from_mapping_accepts_each_nature_choice(choice: str) -> None:
    mapping = full_mapping()
    mapping["nature_of_dispute"] = choice
    assert SCTCase._from_mapping(mapping).nature_of_dispute == choice


def test_from_mapping_rejects_unknown_nature() -> None:
    mapping = full_mapping()
    mapping["nature_of_dispute"] = "Breach of contract"
    with pytest.raises(ValueError):
        SCTCase._from_mapping(mapping)


def test_from_mapping_rejects_bad_dates() -> None:
    mapping = full_mapping()
    mapping["date_of_cause_of_action"] = "30/11/2025"
    with pytest.raises(ValueError):
        SCTCase._from_mapping(mapping)


def test_from_mapping_rejects_bad_amount() -> None:
    mapping = full_mapping()
    mapping["claim_amount"] = "lots of money"
    with pytest.raises(ValueError):
        SCTCase._from_mapping(mapping)


def test_defaults_are_all_none() -> None:
    case = SCTCase()
    for field in (
        "claimant_name",
        "claimant_nric",
        "respondent_name",
        "nature_of_dispute",
        "claim_amount",
        "date_of_cause_of_action",
        "contract_date",
        "particulars",
    ):
        assert getattr(case, field) is None


# --------------------------------------------------------------------------- #
# Output helpers
# --------------------------------------------------------------------------- #


def test_to_dict_full_case() -> None:
    case = SCTCase._from_mapping(full_mapping())
    d = case.to_dict()
    assert d["claim_amount"] == "2500.00"
    assert d["date_of_cause_of_action"] == "2025-11-30T00:00:00"
    assert d["contract_date"] == "2025-08-01T00:00:00"
    assert d["nature_of_dispute"] == "Contract for provision of services"


def test_to_dict_empty_case_uses_none() -> None:
    d = SCTCase().to_dict()
    assert set(d.values()) == {None}


def test_to_json_roundtrips() -> None:
    case = SCTCase._from_mapping(full_mapping())
    payload = json.loads(case.to_json())
    assert payload == case.to_dict()


def test_summary_full_and_missing() -> None:
    full = SCTCase._from_mapping(full_mapping()).summary()
    assert "Alicia Tan" in full and "(S8123456A)" in full
    assert "$2500.00" in full and "2025-11-30" in full

    missing = SCTCase().summary()
    assert "(missing)" in missing and "(unclassified)" in missing
