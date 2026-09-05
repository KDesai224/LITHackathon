import sys
import unittest
from pathlib import Path

# Allow both `python tests/test_field_evidence_validation.py` and unittest discovery.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.field_evidence import EvidenceValidationError, build_suggestion_audit_log


class FieldEvidenceValidationTests(unittest.TestCase):
    def test_rejects_a_quote_not_present_in_the_cited_chunk(self):
        request = {
            "session_id": "demo-session-001",
            "field_id": "claim_amount",
            "field_question": "What amount are you claiming?",
            "retrieved_chunks": [
                {
                    "chunk_id": "email-p1-c1",
                    "text": "I will arrange delivery next week.",
                    "similarity": 0.80,
                    "page": 1,
                }
            ],
        }
        model_output = {
            "plain_language_label": "Amount you want to claim",
            "plain_language_explanation": "Enter the amount you are asking the respondent to repay.",
            "suggested_value": "$500",
            "evidence_quote": "Total paid: $500",
            "citation_chunk_ids": ["email-p1-c1"],
            "why_this_helps": "It identifies an amount.",
            "user_confirmation_needed": True,
            "assessment": {
                "field_question_fit": 90,
                "evidence_explicitness": "explicit",
                "consistency": "consistent",
                "material_conflict": False,
            },
        }

        with self.assertRaisesRegex(EvidenceValidationError, "not present"):
            build_suggestion_audit_log(request, model_output)


if __name__ == "__main__":
    unittest.main()
