"""
``integration_test`` : end-to-end live pipeline check with real API keys.

Pipeline exercised (every module, real network call to the chat endpoint):

    uploaded documents (plain text)
      -> semantic_retrieval.build_extraction_text   (joins a small corpus)
      -> field_extractor.extract_fields             (live LLM tool call)
      -> client_upload.SCTCase.from_text            (typing/validation)
      -> asserts on the typed SCTCase fields

Configuration comes from ``.env`` / environment (never committed; ``.env`` is
gitignored):

    OPENAI_BASE_URL   (default https://api.openai.com/v1)
    OPENAI_API_KEY    (required; if missing this test skips)
    OPENAI_MODEL      (default gpt-4o-mini)

The corpus is deliberately small enough to stay under the extraction budget, so
no embedding service is needed (the local embedding model is still pending).

Run:  uv run python integration_test.py
Exit codes:  0 = passed (or skipped with no key),  1 = assertions failed.
"""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

from client_upload import SCTCase
from field_extractor import extract_fields
from semantic_retrieval import build_extraction_text

# Documents mimic two uploaded files describing one SCT claim.
DOC_A = """\
Claimant: Alicia Tan, NRIC S8123456A.
Respondent: Beng Motors Pte Ltd.
Claim amount: $2,500.00 for car repair services that were paid for but never
completed. The contract was signed on 1 August 2025.
"""

DOC_B = """\
Beng Motors Pte Ltd was engaged by Alicia Tan to replace the gearbox of her
car. This is a contract for provision of services. As of 30 November 2025 the
work was still not done, which is when the cause of action arose. Alicia Tan
now demands a refund of $2,500.00.
"""

EXPECTED = {
    "claimant_name": "Alicia Tan",
    "claimant_nric": "S8123456A",
    "respondent_name": "Beng Motors Pte Ltd",
    "nature_of_dispute": "Contract for provision of services",
    "claim_amount": Decimal("2500.00"),
    "date_of_cause_of_action": datetime.fromisoformat("2025-11-30"),
    "contract_date": datetime.fromisoformat("2025-08-01"),
}


def main() -> int:
    env_path = Path(__file__).resolve().with_name(".env")
    if not env_path.exists():
        print(
            "SKIP: no .env file found. Copy .env.example to .env and fill in "
            "real debug keys, then rerun."
        )
        return 0
    # Debug harness: values in .env override any pre-exported machine vars.
    load_dotenv(env_path, override=True)
    if not os.environ.get("OPENAI_API_KEY"):
        print(
            "SKIP: OPENAI_API_KEY is not set in .env; add it (plus "
            "OPENAI_BASE_URL / OPENAI_MODEL) and rerun."
        )
        return 0

    print("1. building extraction text from the uploaded documents...")
    text = build_extraction_text([DOC_A, DOC_B])
    print(f"   assembled {len(text)} characters")

    print("2. extracting SCT fields with the live model...")
    case = SCTCase.from_text(text, extractor=extract_fields)
    print("   extractor -> SCTCase OK")
    print(case.summary())

    print("3. asserting expected values on the typed fields...")
    checks = {
        "claimant_name": case.claimant_name,
        "claimant_nric": case.claimant_nric,
        "respondent_name": case.respondent_name,
        "nature_of_dispute": case.nature_of_dispute,
        "claim_amount": case.claim_amount,
        "date_of_cause_of_action": case.date_of_cause_of_action,
        "contract_date": case.contract_date,
    }
    failures: list[str] = []
    for field, expected in EXPECTED.items():
        actual = checks[field]
        status = "ok" if actual == expected else "FAIL"
        print(f"   [{status}] {field}: expected {expected!r}, got {actual!r}")
        if actual != expected:
            failures.append(f"{field}: expected {expected!r}, got {actual!r}")

    if not case.particulars:
        failures.append("particulars: expected a non-empty narrative")

    if failures:
        print("\nINTEGRATION TEST FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nINTEGRATION TEST PASSED: all expected fields matched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
