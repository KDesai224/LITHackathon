"""Run a representative ClaimBuddy field-evidence evaluation and print its audit log."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.field_evidence import build_suggestion_audit_log


request = {
    "session_id": "demo-session-001",
    "field_id": "amount_paid",
    "field_question": "What amount did you pay the respondent?",
    "retrieved_chunks": [
        {
            "chunk_id": "receipt-p1-c1",
            "document_id": "receipt-1",
            "document_name": "Payment receipt",
            "page": 1,
            "source_type": "receipt",
            "similarity": 0.94,
            "text": "Payment receipt. Total paid: $500.00 on 10 June 2026.",
        }
    ],
}

# This mimics a validated structured response from the AI model.
model_output = {
    "plain_language_label": "Amount you want to claim",
    "plain_language_explanation": "Enter the amount you are asking the respondent to repay.",
    "suggested_value": "$500.00",
    "evidence_quote": "Total paid: $500.00",
    "citation_chunk_ids": ["receipt-p1-c1"],
    "why_this_helps": "It identifies the amount paid to the respondent.",
    "user_confirmation_needed": True,
    "assessment": {
        "field_question_fit": 95,
        "evidence_explicitness": "explicit",
        "consistency": "consistent",
        "material_conflict": False,
    },
}

audit_log = build_suggestion_audit_log(request, model_output)
print(json.dumps(audit_log, indent=2))
