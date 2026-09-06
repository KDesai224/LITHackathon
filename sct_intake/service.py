"""Framework-agnostic orchestration for the SCT intake pipeline.

``run_intake`` is THE stable callable for FastAPI endpoints (or any caller):
documents -> (semantic pruning) -> field extraction -> typed ``SCTCase``.
``run_document_intake`` additionally accepts raw uploaded files (PDF/images),
reading each one with OCR-gated text extraction before running the same field
extraction; corpora larger than the context budget are searched model-driven.
No FastAPI code lives here so the package stays framework-agnostic.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .case import FieldExtractor, SCTCase
from .embedders import EmbeddingModel, default_embedding_model
from .extraction import extract_agentic, extract_fields
from .retrieval import MAX_CONTEXT_CHARS, build_extraction_text


@dataclass
class IngestedFile:
    """Readable text and warnings for one uploaded file."""

    filename: str
    text: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class DocumentIntakeResult:
    """Outcome of ingesting raw uploaded files through field extraction."""

    case: SCTCase
    files: list[IngestedFile]
    search_rounds: int = 0


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
    return SCTCase.from_text(text, extractor=extractor or extract_fields)


def run_document_intake(
    files: Sequence[tuple[str, bytes]],
    *,
    text: str = "",
    extractor: FieldExtractor | None = None,
    embedder: EmbeddingModel | None = None,
    max_chars: int = MAX_CONTEXT_CHARS,
    max_searches: int = 4,
    engine: Any | None = None,
) -> DocumentIntakeResult:
    """Ingest raw uploaded files (and optional typed text) into an ``SCTCase``.

    Each file is read with OCR-gated text extraction (``ocr_engine``): PDFs
    contribute their embedded text layer and are OCR'd only on pages with no
    searchable text; raster images go through OCR. When the combined corpus
    fits ``max_chars`` the existing single-shot extraction is used; otherwise
    the model-driven agentic search loop (:func:`extract_agentic`) prunes and
    searches the corpus. ``ocr_engine`` is imported lazily, so callers that
    never pass raw files do not load OCR dependencies.

    ``engine`` optionally injects an OCR engine (tests). ``search_rounds`` on
    the result reports how many model-driven searches ran (0 on the fast
    path). Raises ``ValueError`` when no readable text remains.
    """
    if not files and not (text or "").strip():
        raise ValueError(
            "at least one uploaded file or a typed narrative is required."
        )

    # Lazy import keeps OCR/onnx deps off every plain-text consumer of this
    # package.
    import ocr_engine as _ocr_module

    ingested: list[IngestedFile] = []
    readable: list[str] = []
    for filename, content in files:
        result = _ocr_module.extract_text_from_bytes(
            content, filename or "document", engine=engine
        )
        ingested.append(
            IngestedFile(filename, result.full_text, list(result.warnings))
        )
        if result.full_text.strip():
            readable.append(result.full_text)

    typed = (text or "").strip()
    corpus = readable + ([typed] if typed else [])
    if not corpus:
        raise ValueError(
            "no readable text was found in the uploaded file(s) or typed "
            "narrative."
        )

    joined = "\n\n".join(corpus)
    if len(joined) <= max_chars:
        case = SCTCase.from_text(joined, extractor=extractor or extract_fields)
        return DocumentIntakeResult(case=case, files=ingested, search_rounds=0)

    rounds: list[int] = []

    def _count_search() -> None:
        rounds.append(1)

    mapping = extract_agentic(
        corpus,
        embedder=embedder if embedder is not None else default_embedding_model(),
        max_chars=max_chars,
        max_searches=max_searches,
        on_search=_count_search,
    )
    # Same-package coercion of the agent's dict[str, str] onto the typed model.
    case = SCTCase._from_mapping(mapping)
    return DocumentIntakeResult(case=case, files=ingested, search_rounds=len(rounds))
