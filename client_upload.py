"""
``client_upload`` orchestrates the ingestion of a client's uploaded text into a
typed case model for Singapore's Small Claims Tribunal (SCT).

Design (thin instrument, no parsing/AI logic)
---------------------------------------------
The module does **not** itself scan the upload.  Its role is deliberately thin:

    1. A claim upload arrives as a single string (file today, HTTP body later).
    2. ``SCTCase.from_text`` / ``SCTCase.from_upload_file`` hand that string to
       an **externally supplied** callable -- the ``FieldExtractor``/AI
       interface -- and receive back a ``dict[str, str]`` of the model's
       semantic answers.
    3. The orchestrator then type-checks and coerces that mapping onto typed
       ``SCTCase`` fields (``Decimal`` amounts, ``datetime`` objects, and
       validation of ``nature_of_dispute`` against the four closed SCT
       choices).  No semantic re-interpretation happens here.

The generative-AI implementation (chunking/vector-embedding the text,
calling an OpenAI-compatible endpoint, and parsing the response into
``dict[str, str]``) lives in a *separate future module* and is injected here as
a plain callable -- dependency-injection style -- so this module stays
unit-testable and does not import any AI code.

FieldExtractor contract
-----------------------
Extractor signature:  ``extract(text: str) -> dict[str, str]``

Keys it may return (each value the model's best answer as a plain string;
omit or use ``""`` when it found nothing):

    ``claimant_name``            e.g. ``"John Doe"``
    ``claimant_nric``            e.g. ``"G2677383R"``
    ``respondent_name``          e.g. ``"Jane Ong"``
    ``nature_of_dispute``        exactly one of NATURE_OF_DISPUTE_CHOICES
    ``claim_amount``             decimal string, ``"10000.00"``; a leading
                                 ``$``/commas are tolerated and normalised
    ``date_of_cause_of_action``  ISO 8601 (``"2026-09-02"`` etc.)
    ``contract_date``            ISO 8601 or ``""``
    ``particulars``              the (verbatim) narrative if needed downstream

Usage
-----
    from your_ai_module import extract_fields          # future module
    case = SCTCase.from_upload_file(extractor=extract_fields)
    case = SCTCase.from_text(upload_body, extractor=extract_fields)  # HTTP path
    print(case.summary())
    case.to_json()
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Callable, Literal, TypeAlias

# --------------------------------------------------------------------------- #
# SCT domain constants
# --------------------------------------------------------------------------- #

#: Closed set of SCT nature-of-dispute options; anything else is rejected.
NatureOfDispute = Literal[
    "Contract for sale of goods",
    "Contract for provision of services",
    "Damage to property",
    "Lease not exceeding two years",
]

NATURE_OF_DISPUTE_CHOICES: tuple[NatureOfDispute, ...] = (
    "Contract for sale of goods",
    "Contract for provision of services",
    "Damage to property",
    "Lease not exceeding two years",
)

DEFAULT_UPLOAD_PATH = Path(__file__).resolve().parent / "client_upload.txt"


# --------------------------------------------------------------------------- #
# External AI interface (seam only -- no AI code is implemented here)
# --------------------------------------------------------------------------- #

#: The external generative-AI fill interface: any callable that ingests the
#: uploaded *text* and returns the model's best answers as plain strings,
#: i.e. ``dict[str, str]`` (see the module docstring for the field contract).
#:
#: The future AI module implements this by chunking/vector-embedding the text,
#: calling an OpenAI-compatible endpoint, and parsing the response into that
#: mapping.  No AI code lives in this module.
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
    except Exception as exc:  # noqa: BLE001 - surface a friendly message
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
    """A single SCT claim intake, populated by the external AI interface.

    Additional final subfields will be added later by hand as the intake
    schema settles.
    """

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
    def from_text(cls, text: str, extractor: FieldExtractor) -> SCTCase:
        """Ingest uploaded *text* and delegate filling to ``extractor``.

        ``extractor`` is the injected external generative-AI interface; the
        response it returns (``dict[str, str]``) is coerced onto typed fields.
        """
        if not text or not text.strip():
            raise ValueError("upload text contained no non-blank content")

        raw = _fetch_extractor_answers(extractor, text)
        return cls._from_mapping(raw)

    @classmethod
    def from_upload_file(
        cls,
        path: str | Path = DEFAULT_UPLOAD_PATH,
        *,
        extractor: FieldExtractor,
    ) -> SCTCase:
        """Read ``path`` (default ``client_upload.txt``) and delegate to from_text."""
        text = Path(path).read_text(encoding="utf-8-sig")
        return cls.from_text(text, extractor=extractor)

    @classmethod
    def _from_mapping(cls, answers: dict[str, str]) -> SCTCase:
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


# --------------------------------------------------------------------------- #
# Demo / CLI
# --------------------------------------------------------------------------- #


def main() -> int:
    # This module deliberately performs NO semantic extraction itself.  Before
    # this demo can run, wire your OpenAI-compatible FieldExtractor here, e.g.
    #
    #     from your_ai_module import extract_fields   # future module
    #     case = SCTCase.from_upload_file(extractor=extract_fields)
    #     print(case.summary())
    #
    # or use the injected entry points directly in your backend:
    #
    #     case = SCTCase.from_text(upload_body, extractor=extract_fields)
    print(
        "SCTCase is an orchestrator: it delegates filling to an externally "
        "injected AI FieldExtractor.\n"
        "Wire your OpenAI-compatible extractor, then e.g.:\n"
        "  case = SCTCase.from_upload_file(extractor=extract_fields)\n"
        "  print(case.summary())"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())