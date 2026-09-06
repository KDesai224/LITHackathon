"""``SCTCase`` : typed intake model + coercion/validation for an SCT claim.

The module is deliberately thin and holds no parsing/AI logic of its own:

1. An uploaded document arrives as a single text string.
2. ``SCTCase.from_text`` / ``SCTCase.from_upload_file`` hand the text to an
   externally supplied ``FieldExtractor`` callable and receive back a
   ``dict[str, str]`` of the model's semantic answers.
3. The orchestrator then type-checks and coerces that mapping onto typed
   fields (``Decimal`` amounts, ``datetime`` objects, validation of
   ``nature_of_dispute`` against the closed SCT choices from :mod:`domain`).

FieldExtractor contract
-----------------------
Extractor signature:  ``extract(text: str) -> dict[str, str]``

Keys it may return (values are plain strings; omit or use ``""`` when nothing
was found): ``claimant_name``, ``claimant_nric``, ``respondent_name``,
``nature_of_dispute`` (exactly one of NATURE_OF_DISPUTE_CHOICES),
``claim_amount``, ``date_of_cause_of_action``, ``contract_date``,
``particulars``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal, TypeAlias

from .domain import NATURE_OF_DISPUTE_CHOICES

DEFAULT_UPLOAD_PATH = Path(__file__).resolve().parent / "sample_claim.txt"

#: Re-export for convenience / compat: closed SCT choice set as a literal type.
NatureOfDispute: TypeAlias = Literal[
    "Contract for sale of goods",
    "Contract for provision of services",
    "Damage to property",
    "Lease not exceeding two years",
]


# --------------------------------------------------------------------------- #
# External AI interface (seam only)
# --------------------------------------------------------------------------- #

#: Any callable ingesting uploaded *text* and returning the model's best
#: answers as plain strings, i.e. ``dict[str, str]``.
FieldExtractor: TypeAlias = Callable[[str], dict[str, str]]


# --------------------------------------------------------------------------- #
# Coercion / validation helpers
# --------------------------------------------------------------------------- #


def _to_decimal(value: str, field: str) -> Decimal:
    """Normalise a plain decimal string (``$10,000`` tolerated) to Decimal."""
    cleaned = value.strip().replace(",", "").replace("$", "").replace(" ", "")
    if cleaned in ("", "-", ".", "None", "null", "unknown"):
        raise ValueError(
            f"{field}: extractor returned unusable amount {value!r}."
        )
    try:
        amount = Decimal(cleaned).quantize(Decimal("0.01"))
    except Exception as exc:
        raise ValueError(
            f"{field}: extractor returned non-numeric amount {value!r}."
        ) from exc
    return amount


def _to_datetime(value: str, field: str) -> datetime:
    """Parse an ISO-8601 date/datetime string from the extractor response."""
    cleaned = value.strip()
    if cleaned == "":
        raise ValueError(f"{field}: extractor returned an empty date.")
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError(
            f"{field}: value {value!r} is not ISO 8601 "
            '(e.g. "2026-09-02" or "2026-09-02T00:00:00").'
        ) from exc


def _fetch_extractor_answers(extractor: FieldExtractor, text: str) -> dict[str, str]:
    """Invoke the injected extractor and validate its raw response."""
    result = extractor(text)
    if not isinstance(result, dict):
        raise TypeError(
            f"extractor must return dict[str, str], got {type(result).__name__}."
        )
    for key, value in result.items():
        if not isinstance(value, str):
            raise TypeError(
                f"extractor returned a non-str value for {key!r}: {value!r} "
                "(contract requires dict[str, str])."
            )
    return result


# --------------------------------------------------------------------------- #
# Target model
# --------------------------------------------------------------------------- #


@dataclass
class SCTCase:
    """A single SCT claim intake, populated by the external AI interface."""

    source: str | None = None
    claimant_name: str | None = None
    claimant_nric: str | None = None
    respondent_name: str | None = None
    nature_of_dispute: NatureOfDispute | None = None
    claim_amount: Decimal | None = None
    date_of_cause_of_action: datetime | None = None
    contract_date: datetime | None = None
    particulars: str | None = None

    # ------------------------------------------------------------------ #
    # Ingestion / orchestration
    # ------------------------------------------------------------------ #

    @classmethod
    def from_text(
        cls,
        text: str,
        extractor: FieldExtractor,
        *,
        source: str | None = None,
    ) -> SCTCase:
        """Ingest uploaded *text* and delegate filling to ``extractor``."""
        if not text or not text.strip():
            raise ValueError("upload text contained no non-blank content")

        raw = _fetch_extractor_answers(extractor, text)
        return cls._from_mapping(raw, source=source)

    @classmethod
    def from_upload_file(
        cls,
        path: str | Path = DEFAULT_UPLOAD_PATH,
        *,
        extractor: FieldExtractor,
        source: str | None = None,
    ) -> SCTCase:
        """Read ``path`` (default the bundled sample) and delegate to from_text."""
        text = Path(path).read_text(encoding="utf-8-sig")
        return cls.from_text(text, extractor=extractor, source=source or Path(path).name)

    @classmethod
    def _from_mapping(
        cls,
        answers: dict[str, str],
        *,
        source: str | None = None,
    ) -> SCTCase:
        """Coerce the extractor's raw dict[str, str] onto typed fields."""

        def get(key: str) -> str | None:
            value = answers.get(key)
            return value.strip() if value and value.strip() else None

        # ---- nature_of_dispute: enforce the closed SCT choice set --------- #
        nature_raw = get("nature_of_dispute")
        if nature_raw is not None and nature_raw not in NATURE_OF_DISPUTE_CHOICES:
            raise ValueError(
                f"nature_of_dispute: {nature_raw!r} is not one of the SCT "
                f"choices: {', '.join(NATURE_OF_DISPUTE_CHOICES)}."
            )

        # ---- Dates: strict ISO coercion when the AI claims a value --------- #
        cause_raw = get("date_of_cause_of_action")
        date_of_cause_of_action = (
            _to_datetime(cause_raw, "date_of_cause_of_action")
            if cause_raw is not None
            else None
        )

        contract_raw = get("contract_date")
        contract_date = (
            _to_datetime(contract_raw, "contract_date")
            if contract_raw is not None
            else None
        )

        # ---- Amount: Decimal coercion -------------------------------------- #
        amount_raw = get("claim_amount")
        claim_amount = (
            _to_decimal(amount_raw, "claim_amount")
            if amount_raw is not None
            else None
        )

        return cls(
            source=source,
            claimant_name=get("claimant_name"),
            claimant_nric=get("claimant_nric"),
            respondent_name=get("respondent_name"),
            nature_of_dispute=nature_raw,  # already validated against choices
            claim_amount=claim_amount,
            date_of_cause_of_action=date_of_cause_of_action,
            contract_date=contract_date,
            particulars=get("particulars"),
        )

    # ------------------------------------------------------------------ #
    # Output helpers
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "claimant_name": self.claimant_name,
            "claimant_nric": self.claimant_nric,
            "respondent_name": self.respondent_name,
            "nature_of_dispute": self.nature_of_dispute,
            "claim_amount": str(self.claim_amount) if self.claim_amount is not None else None,
            "date_of_cause_of_action": (
                self.date_of_cause_of_action.isoformat()
                if self.date_of_cause_of_action is not None
                else None
            ),
            "contract_date": (
                self.contract_date.isoformat()
                if self.contract_date is not None
                else None
            ),
            "particulars": self.particulars,
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def summary(self) -> str:
        """Human-readable fill report."""
        name_display = (
            f"{self.claimant_name or '(missing)'} "
            f"({self.claimant_nric or 'NRIC missing'})"
        )
        amount_display = (
            f"${self.claim_amount}"
            if self.claim_amount is not None
            else "(missing)"
        )
        cause_display = (
            self.date_of_cause_of_action.isoformat()
            if self.date_of_cause_of_action
            else "(missing)"
        )
        contract_display = (
            self.contract_date.isoformat()
            if self.contract_date
            else "(missing)"
        )
        return "\n".join(
            [
                f"Claimant:        {name_display}",
                f"Respondent:      {self.respondent_name or '(missing)'}",
                f"Nature:          {self.nature_of_dispute or '(unclassified)'}",
                f"Claim amount:    {amount_display}",
                f"Cause of action: {cause_display}",
                f"Contract date:   {contract_display}",
            ]
        )
