"""Compatibility shim for OpenAI-compatible SCT field extraction.

All implementation moved to :mod:`sct_intake`. This module re-exports the same
objects so existing ``from field_extractor import extract_fields`` imports keep
working unchanged after the package split.
"""

from __future__ import annotations

from sct_intake import (
    ExtractionError,
    FieldExtractionError,
    extract_fields,
    openai_compatible_extract,
)
from sct_intake.config import DEFAULT_BASE_URL, DEFAULT_MODEL
from sct_intake.extraction import (
    EXPECTED_KEYS,
    RESERVED_CHAT_FIELDS,
    TOOL_NAME,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "EXPECTED_KEYS",
    "RESERVED_CHAT_FIELDS",
    "TOOL_NAME",
    "ExtractionError",
    "FieldExtractionError",
    "extract_fields",
    "openai_compatible_extract",
]
