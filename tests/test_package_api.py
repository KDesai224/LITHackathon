"""Compat checks: shim modules re-export the same objects as the package."""

from __future__ import annotations

from pathlib import Path

import client_upload
import field_extractor
import sct_intake
import semantic_retrieval
from sct_intake.errors import ExtractionError, FieldExtractionError


def test_shims_export_identical_objects() -> None:
    assert client_upload.SCTCase is sct_intake.SCTCase
    assert client_upload.NATURE_OF_DISPUTE_CHOICES is sct_intake.NATURE_OF_DISPUTE_CHOICES
    assert field_extractor.extract_fields is sct_intake.extract_fields
    assert (
        field_extractor.openai_compatible_extract
        is sct_intake.openai_compatible_extract
    )
    assert (
        semantic_retrieval.build_extraction_text is sct_intake.build_extraction_text
    )
    assert semantic_retrieval.default_embedding_model is sct_intake.default_embedding_model
    assert semantic_retrieval.TextChunk is sct_intake.TextChunk


def test_field_extraction_error_alias() -> None:
    assert FieldExtractionError is ExtractionError


def test_shim_constants_available() -> None:
    assert field_extractor.TOOL_NAME == "submit_sct_fields"
    assert semantic_retrieval.CHUNK_CHARS == sct_intake.retrieval.CHUNK_CHARS
    assert semantic_retrieval.MAX_CONTEXT_CHARS == sct_intake.MAX_CONTEXT_CHARS


def test_public_api_is_importable() -> None:
    for name in sct_intake.__all__:
        assert hasattr(sct_intake, name), name


def test_bundled_sample_exists() -> None:
    sample = Path(sct_intake.DEFAULT_UPLOAD_PATH)
    assert sample.exists() and sample.read_text(encoding="utf-8-sig").strip()
