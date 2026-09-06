"""SCT intake pipeline: semantic retrieval + field extraction + typed case.

Public surface (import from here or from the top-level compat shims
``client_upload``/``field_extractor``/``semantic_retrieval``):

- Domain/model: ``SCTCase``, ``FieldExtractor``, ``NatureOfDispute``,
  ``NATURE_OF_DISPUTE_CHOICES``
- Extraction: ``extract_fields``, ``openai_compatible_extract``,
  ``extract_agentic``
- Retrieval: ``build_extraction_text``, ``TextChunk``, ``ChunkHit``,
  ``DocumentIndex``, ``MAX_CONTEXT_CHARS``
- Embedders: ``EmbeddingModel``, ``HTTPEmbeddingModel``,
  ``SentenceTransformerEmbeddingModel``, ``default_embedding_model``
- Errors: ``SCTError``, ``ExtractionError``/``FieldExtractionError``,
  ``EmbeddingError``
- Orchestration: ``run_intake``, ``run_document_intake``,
  ``DocumentIntakeResult``, ``IngestedFile``
- Config: ``get_config``
"""

from __future__ import annotations

from .case import (
    DEFAULT_UPLOAD_PATH,
    FieldExtractor,
    NatureOfDispute,
    SCTCase,
)
from .config import get_config
from .domain import NATURE_OF_DISPUTE_CHOICES
from .embedders import (
    EmbeddingModel,
    HTTPEmbeddingModel,
    SentenceTransformerEmbeddingModel,
    default_embedding_model,
)
from .errors import (
    EmbeddingError,
    ExtractionError,
    FieldExtractionError,
    SCTError,
)
from .extraction import (
    extract_agentic,
    extract_fields,
    openai_compatible_extract,
)
from .retrieval import (
    MAX_CONTEXT_CHARS,
    ChunkHit,
    DocumentIndex,
    TextChunk,
    build_extraction_text,
)
from .service import (
    DocumentIntakeResult,
    IngestedFile,
    run_document_intake,
    run_intake,
)

__all__ = [
    "DEFAULT_UPLOAD_PATH",
    "MAX_CONTEXT_CHARS",
    "NATURE_OF_DISPUTE_CHOICES",
    "ChunkHit",
    "DocumentIndex",
    "DocumentIntakeResult",
    "EmbeddingError",
    "EmbeddingModel",
    "ExtractionError",
    "FieldExtractionError",
    "FieldExtractor",
    "HTTPEmbeddingModel",
    "IngestedFile",
    "NatureOfDispute",
    "SCTCase",
    "SCTError",
    "SentenceTransformerEmbeddingModel",
    "TextChunk",
    "build_extraction_text",
    "default_embedding_model",
    "extract_agentic",
    "extract_fields",
    "get_config",
    "openai_compatible_extract",
    "run_document_intake",
    "run_intake",
]
