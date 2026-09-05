import sys
import unittest
from pathlib import Path

# Allow both `python tests/test_field_evidence.py` and unittest discovery.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.field_evidence import build_suggestion_audit_log


class FieldEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.request = {
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

    def test_explicit_receipt_returns_high_confidence_audit_log(self):
        result = build_suggestion_audit_log(
            self.request,
            {
                "plain_language_label": "Amount you want to claim",
                "plain_language_explanation": "Enter the amount you are asking the respondent to repay.",
                "suggested_value": "$500.00",
                "evidence_quote": "Total paid: $500.00",
                "citation_chunk_ids": ["receipt-p1-c1"],
                "why_this_helps": "It identifies the amount paid.",
                "user_confirmation_needed": True,
                "assessment": {
                    "field_question_fit": 95,
                    "evidence_explicitness": "explicit",
                    "consistency": "consistent",
                    "material_conflict": False,
                },
            },
        )

        self.assertEqual(result["confidence"]["tier"], "high")
        self.assertEqual(result["confidence"]["colour"], "light_green")
        self.assertTrue(result["display_suggestion"])
        self.assertEqual(result["citations"][0]["page"], 1)
        self.assertEqual(result["title"], "Amount you want to claim")
        self.assertEqual(result["suggestion"], "$500.00")
        self.assertEqual(result["source"], "Payment receipt, page 1")

    def test_conflicting_evidence_is_capped_at_medium_confidence(self):
        result = build_suggestion_audit_log(
            self.request,
            {
                "plain_language_label": "Amount you want to claim",
                "plain_language_explanation": "Enter the amount you are asking the respondent to repay.",
                "suggested_value": "$500.00",
                "evidence_quote": "Total paid: $500.00",
                "citation_chunk_ids": ["receipt-p1-c1"],
                "why_this_helps": "It identifies one stated payment amount.",
                "user_confirmation_needed": True,
                "assessment": {
                    "field_question_fit": 95,
                    "evidence_explicitness": "explicit",
                    "consistency": "conflicting",
                    "material_conflict": True,
                },
            },
        )

        self.assertEqual(result["confidence"]["tier"], "medium")
        self.assertLessEqual(result["confidence"]["score"], 70)
        self.assertIn("material_conflict_cap_70", result["confidence"]["safety_caps_applied"])


if __name__ == "__main__":
    unittest.main()
