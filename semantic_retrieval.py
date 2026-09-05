"""Compatibility shim for semantic retrieval and embedding providers.

All implementation moved to :mod:`sct_intake`. This module re-exports the same
objects so existing ``from semantic_retrieval import build_extraction_text``
imports keep working unchanged after the package split.
"""

from __future__ import annotations

from sct_intake import (
    EmbeddingError,
    EmbeddingModel,
    HTTPEmbeddingModel,
    SentenceTransformerEmbeddingModel,
    TextChunk,
    build_extraction_text,
    default_embedding_model,
)
from sct_intake.config import (
    DEFAULT_EMBEDDING_BASE_URL,
    DEFAULT_EMBEDDING_MODEL_NAME,
)
from sct_intake.retrieval import CHUNK_CHARS, CHUNK_OVERLAP, MAX_CONTEXT_CHARS

__all__ = [
    "CHUNK_CHARS",
    "CHUNK_OVERLAP",
    "DEFAULT_EMBEDDING_BASE_URL",
    "DEFAULT_EMBEDDING_MODEL_NAME",
    "MAX_CONTEXT_CHARS",
    "EmbeddingError",
    "EmbeddingModel",
    "HTTPEmbeddingModel",
    "SentenceTransformerEmbeddingModel",
    "TextChunk",
    "build_extraction_text",
    "default_embedding_model",
]
