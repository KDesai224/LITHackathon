"""Unit tests for ``sct_intake.service.run_intake`` (no network)."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

import pytest

from sct_intake import SCTCase
from sct_intake.service import run_intake
from tests.helpers import KeywordHashEmbedder

CLAIM_MAPPING = {
    "claimant_name": "Alicia Tan",
    "claimant_nric": "S8123456A",
    "respondent_name": "Beng Motors Pte Ltd",
    "nature_of_dispute": "Contract for provision of services",
    "claim_amount": "$2,500.00",
    "date_of_cause_of_action": "2025-11-30",
    "contract_date": "2025-08-01",
    "particulars": "Gearbox repair paid but never completed.",
}


def stub_extractor(_text: str) -> dict[str, str]:
    return dict(CLAIM_MAPPING)


class _ExplodingEmbedder:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise AssertionError("embedder must not be called for a short corpus")


def test_run_intake_short_corpus_no_embeddings() -> None:
    case = run_intake(
        ["Alicia Tan vs Beng Motors, $2,500.00 refund claim."],
        extractor=stub_extractor,
        embedder=_ExplodingEmbedder(),
    )
    assert isinstance(case, SCTCase)
    assert case.claim_amount == Decimal("2500.00")
    assert case.claimant_name == "Alicia Tan"


def test_run_intake_returns_document_source() -> None:
    case = run_intake(
        ["Alicia Tan vs Beng Motors, $2,500.00 refund claim."],
        extractor=stub_extractor,
        document_names=["repair-invoice.pdf"],
    )
    assert case.source == "repair-invoice.pdf"


def test_run_intake_rejects_empty_documents() -> None:
    with pytest.raises(ValueError):
        run_intake([], extractor=stub_extractor)


def test_run_intake_prunes_oversized_corpus_with_embedder() -> None:
    large_claim = (CLAIM_MAPPING["particulars"] + " John Doe NRIC G2677383R. ") * 20
    text_source = [
        large_claim,
        "Baking bread with basil pesto and parmesan." * 20,
    ]
    case = run_intake(
        text_source,
        extractor=stub_extractor,
        embedder=KeywordHashEmbedder(),
        max_chars=800,
    )
    assert isinstance(case, SCTCase)
    assert case.respondent_name == "Beng Motors Pte Ltd"


def test_run_intake_uses_default_budget() -> None:
    case = run_intake(["tiny"], extractor=stub_extractor)
    assert case.claim_amount == Decimal("2500.00")
