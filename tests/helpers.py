"""Shared test helpers: canned OpenAI-compatible fixtures + hash embedder.

These lived inside the production modules as ``__main__`` scaffolding before the
package split; now they live only here so production code stays clean.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from typing import Any

import numpy as np

from sct_intake.extraction import TOOL_NAME

SAMPLE_ARGUMENTS_TEXT = (
    '{"claimant_name": "John Doe", '
    '"claimant_nric": "G2677383R", '
    '"respondent_name": "Jane Ong", '
    '"nature_of_dispute": "Contract for sale of goods", '
    '"claim_amount": "$10,000.00", '
    '"date_of_cause_of_action": "2026-09-02", '
    '"contract_date": "", '
    '"particulars": "Sale of a sofa to Jane Ong, unpaid despite demand."}'
)


def sample_arguments() -> str:
    """Canonical tool-call ``arguments`` JSON for a happy-path parse."""
    return SAMPLE_ARGUMENTS_TEXT


def tool_message(arguments: str) -> dict[str, Any]:
    """A chat-completion assistant message carrying one forced tool call."""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_stub",
                "type": "function",
                "function": {"name": TOOL_NAME, "arguments": arguments},
            }
        ],
    }


def completion(message: dict[str, Any]) -> dict[str, Any]:
    """A canned OpenAI-compatible chat completion with one assistant message."""
    return {
        "id": "chatcmpl-stub",
        "object": "chat.completion",
        "model": "stub-model",
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls",
            }
        ],
    }


def _stable_hash(text: str) -> int:
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class KeywordHashEmbedder:
    """Deterministic test double for an EmbeddingModel (no network).

    Produces a fixed-width bag-of-keywords vector per text, so shared
    vocabulary yields real cosine similarity.
    """

    def __init__(self, dimensions: int = 1024) -> None:
        self._dimensions = dimensions

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = np.zeros(self._dimensions, dtype="float64")
            for token in _tokens(text):
                vector[_stable_hash(token) % self._dimensions] += 1.0
            vectors.append(vector.tolist())
        return vectors
