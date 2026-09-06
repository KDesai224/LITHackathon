"""Framework-agnostic orchestration for the SCT intake pipeline.

``run_intake`` is THE stable callable for FastAPI endpoints (or any caller):
documents -> (semantic pruning) -> field extraction -> typed ``SCTCase``.
No FastAPI code lives here so the package stays framework-agnostic.
"""

from __future__ import annotations

from collections.abc import Sequence

from .case import FieldExtractor, SCTCase
from .embedders import EmbeddingModel, default_embedding_model
from .extraction import extract_fields
from .retrieval import MAX_CONTEXT_CHARS, build_extraction_text


def run_intake(
    documents: Sequence[str],
    *,
    extractor: FieldExtractor | None = None,
    embedder: EmbeddingModel | None = None,
    document_names: Sequence[str] | None = None,
    max_chars: int = MAX_CONTEXT_CHARS,
) -> SCTCase:
    """Run one full SCT intake over uploaded claim documents.

    - A default extractor (``extract_fields``) and default embedder (the
      configured local/HTTP provider) are supplied automatically; both are
      lazy, so short corpora never touch the model or the network.
    - Short corpora that fit ``max_chars`` skip embeddings entirely.
    """
    text = build_extraction_text(
        documents,
        embedder=embedder if embedder is not None else default_embedding_model(),
        max_chars=max_chars,
    )
    source = None
    if document_names is not None:
        names = [name.strip() for name in document_names if name and name.strip()]
        if names:
            source = ", ".join(names)
    return SCTCase.from_text(text, extractor=extractor or extract_fields, source=source)
