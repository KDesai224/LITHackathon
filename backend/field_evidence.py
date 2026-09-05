"""Validate structured AI field guidance and produce an audit-log record.

The language model is deliberately limited to assessing evidence. Confidence
calculation and display decisions happen deterministically in this module.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

# Supply this schema to the model provider's structured-output feature.
# The backend still validates all returned values before using them.
FIELD_EVIDENCE_RESPONSE_SCHEMA: dict[str, Any] = {
    "name": "field_evidence_assessment",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "plain_language_label",
            "plain_language_explanation",
            "suggested_value",
            "evidence_quote",
            "citation_chunk_ids",
            "why_this_helps",
            "user_confirmation_needed",
            "assessment",
        ],
        "properties": {
            "plain_language_label": {"type": "string"},
            "plain_language_explanation": {"type": "string"},
            "suggested_value": {"type": "string"},
            "evidence_quote": {"type": "string"},
            "citation_chunk_ids": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 0,
            },
            "why_this_helps": {"type": "string"},
            "user_confirmation_needed": {"type": "boolean"},
            "assessment": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "field_question_fit",
                    "evidence_explicitness",
                    "consistency",
                    "material_conflict",
                ],
                "properties": {
                    "field_question_fit": {"type": "integer", "minimum": 0, "maximum": 100},
                    "evidence_explicitness": {
                        "type": "string",
                        "enum": ["explicit", "derived", "weak", "insufficient"],
                    },
                    "consistency": {
                        "type": "string",
                        "enum": ["consistent", "ambiguous", "conflicting"],
                    },
                    "material_conflict": {"type": "boolean"},
                },
            },
        },
    },
}

_EXPLICITNESS_SCORES = {"explicit": 100, "derived": 65, "weak": 25, "insufficient": 0}
_CONSISTENCY_SCORES = {"consistent": 100, "ambiguous": 65, "conflicting": 20}
_SOURCE_RELIABILITY_SCORES = {
    "court_record": 100,
    "signed_contract": 100,
    "invoice": 85,
    "receipt": 85,
    "correspondence": 70,
    "user_note": 40,
    "unknown": 50,
}


class EvidenceValidationError(ValueError):
    """Raised when a model response cannot be verified against retrieved text."""


def build_suggestion_audit_log(
    request: dict[str, Any], model_output: dict[str, Any]
) -> dict[str, Any]:
    """Create a validated, explainable audit record for one form-field tooltip.

    ``request`` must contain ``session_id``, ``field_id``, ``field_question``,
    and ``retrieved_chunks``. Each chunk needs ``chunk_id``, ``text``, and a
    cosine ``similarity`` in the inclusive range 0..1. It can also include
    ``document_name``, ``page``, and ``source_type``.

    The function rejects fabricated citations/quotes rather than producing an
    apparently confident answer from unsupported model output.
    """
    _require_request(request)
    _require_model_shape(model_output)

    chunks_by_id = {chunk["chunk_id"]: chunk for chunk in request["retrieved_chunks"]}
    citation_ids = model_output["citation_chunk_ids"]
    cited_chunks = _validate_citations(citation_ids, chunks_by_id, model_output["evidence_quote"])

    assessment = model_output["assessment"]
    components = {
        "field_question_fit": assessment["field_question_fit"],
        "evidence_explicitness": _EXPLICITNESS_SCORES[assessment["evidence_explicitness"]],
        "retrieval_support": _retrieval_support(cited_chunks),
        "consistency": _CONSISTENCY_SCORES[assessment["consistency"]],
        "document_reliability": _document_reliability(cited_chunks),
    }
    raw_score = round(
        0.35 * components["field_question_fit"]
        + 0.25 * components["evidence_explicitness"]
        + 0.20 * components["retrieval_support"]
        + 0.15 * components["consistency"]
        + 0.05 * components["document_reliability"]
    )
    score, caps = _apply_safety_caps(raw_score, assessment, cited_chunks)
    tier, colour, decision = _presentation(score)

    return {
        "audit_event_id": f"audit_{uuid4().hex}",
        "event_type": "field_suggestion_evaluated",
        "created_at": datetime.now(UTC).isoformat(),
        "session_id": request["session_id"],
        "field_id": request["field_id"],
        "field_question": request["field_question"],
        # These fields are both the user-facing suggestion and the audit record.
        "title": model_output["plain_language_label"],
        "explanation": model_output["plain_language_explanation"],
        "suggestion": model_output["suggested_value"],
        "quote": model_output["evidence_quote"],
        "why_this_helps": model_output["why_this_helps"],
        "confidence": {
            "score": score,
            "tier": tier,
            "colour": colour,
            "raw_score": raw_score,
            "components": components,
            "safety_caps_applied": caps,
        },
        "citations": [_citation_for_log(chunk) for chunk in cited_chunks],
        "decision": decision,
        "display_suggestion": decision == "show_suggestion",
        "needs_user_review": True,
        "source": _source_label(cited_chunks[0]) if decision == "show_suggestion" else None,
        "requires_confirmation": model_output["user_confirmation_needed"],
        "model_output_sha256": _stable_hash(model_output),
    }


def _require_request(request: dict[str, Any]) -> None:
    for key in ("session_id", "field_id", "field_question", "retrieved_chunks"):
        if not request.get(key):
            raise EvidenceValidationError(f"request.{key} is required")
    for chunk in request["retrieved_chunks"]:
        for key in ("chunk_id", "text", "similarity"):
            if key not in chunk:
                raise EvidenceValidationError(f"retrieved chunk is missing {key}")
        if not 0 <= chunk["similarity"] <= 1:
            raise EvidenceValidationError("chunk similarity must be between 0 and 1")


def _require_model_shape(output: dict[str, Any]) -> None:
    required = {
        "plain_language_label",
        "plain_language_explanation",
        "suggested_value",
        "evidence_quote",
        "citation_chunk_ids",
        "why_this_helps",
        "user_confirmation_needed",
        "assessment",
    }
    missing = required - output.keys()
    if missing:
        raise EvidenceValidationError(f"model output is missing: {', '.join(sorted(missing))}")
    assessment = output["assessment"]
    required_assessment = {"field_question_fit", "evidence_explicitness", "consistency", "material_conflict"}
    missing_assessment = required_assessment - assessment.keys()
    if missing_assessment:
        raise EvidenceValidationError("model assessment is incomplete")
    if not isinstance(assessment["field_question_fit"], int) or not 0 <= assessment["field_question_fit"] <= 100:
        raise EvidenceValidationError("field_question_fit must be an integer between 0 and 100")
    if assessment["evidence_explicitness"] not in _EXPLICITNESS_SCORES:
        raise EvidenceValidationError("unsupported evidence_explicitness")
    if assessment["consistency"] not in _CONSISTENCY_SCORES:
        raise EvidenceValidationError("unsupported consistency")


def _validate_citations(
    citation_ids: list[str], chunks_by_id: dict[str, dict[str, Any]], quote: str
) -> list[dict[str, Any]]:
    if not citation_ids:
        raise EvidenceValidationError("a substantive suggestion requires at least one citation")
    missing_ids = [chunk_id for chunk_id in citation_ids if chunk_id not in chunks_by_id]
    if missing_ids:
        raise EvidenceValidationError(f"unknown citation chunk IDs: {', '.join(missing_ids)}")
    cited_chunks = [chunks_by_id[chunk_id] for chunk_id in dict.fromkeys(citation_ids)]
    normal_quote = _normalise(quote)
    if not normal_quote or not any(normal_quote in _normalise(chunk["text"]) for chunk in cited_chunks):
        raise EvidenceValidationError("supporting_quote is not present in a cited chunk")
    return cited_chunks


def _retrieval_support(chunks: list[dict[str, Any]]) -> int:
    # Strongest cited chunk dominates; extra weak chunks cannot inflate the score.
    return round(max(chunk["similarity"] for chunk in chunks) * 100)


def _document_reliability(chunks: list[dict[str, Any]]) -> int:
    return max(_SOURCE_RELIABILITY_SCORES.get(chunk.get("source_type", "unknown"), 50) for chunk in chunks)


def _apply_safety_caps(raw_score: int, assessment: dict[str, Any], chunks: list[dict[str, Any]]) -> tuple[int, list[str]]:
    score = raw_score
    caps: list[str] = []
    if assessment["material_conflict"] or assessment["consistency"] == "conflicting":
        score = min(score, 70)
        caps.append("material_conflict_cap_70")
    if assessment["evidence_explicitness"] in {"weak", "insufficient"}:
        score = min(score, 49)
        caps.append("weak_evidence_cap_49")
    if max(chunk["similarity"] for chunk in chunks) < 0.55:
        score = min(score, 50)
        caps.append("low_retrieval_support_cap_50")
    if any(chunk.get("page") is None for chunk in chunks):
        score = min(score, 60)
        caps.append("missing_page_provenance_cap_60")
    return score, caps


def _presentation(score: int) -> tuple[str, str, str]:
    if score >= 80:
        return "high", "light_green", "show_suggestion"
    if score >= 50:
        return "medium", "yellow", "show_suggestion"
    return "low", "red", "request_user_review"


def _citation_for_log(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": chunk["chunk_id"],
        "document_id": chunk.get("document_id"),
        "document_name": chunk.get("document_name", "Unknown document"),
        "page": chunk.get("page"),
        "similarity": chunk["similarity"],
        "source_type": chunk.get("source_type", "unknown"),
    }


def _source_label(chunk: dict[str, Any]) -> str:
    return f"{chunk.get('document_name', 'Unknown document')}, page {chunk.get('page')}"


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _stable_hash(value: Any) -> str:
    # repr is sufficient for a demo audit fingerprint; do not log prompts or raw PII here.
    return sha256(repr(value).encode("utf-8")).hexdigest()
