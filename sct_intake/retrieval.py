"""Chunk, embed, and semantically select the parts of uploaded claim documents
that matter, then reassemble ONE bounded text.

Retrieval depends only on the :class:`EmbeddingModel` protocol from
:mod:`embedders`; the concrete local/HTTP providers live there and never leak
into this module.

Small corpora never need the model: if every document together fits the
context budget (``max_chars``), :func:`build_extraction_text` just joins them
and returns without embedding anything.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

from .embedders import EmbeddingModel
from .errors import EmbeddingError

#: Chunking: fixed character windows.
CHUNK_CHARS = 2000
CHUNK_OVERLAP = 200

#: Default context budget handed to the field extractor.
MAX_CONTEXT_CHARS = 24_000

_DOCUMENT_SEPARATOR = "\n\n---\n\n"
_CHUNK_SEPARATOR = "\n\n"


@dataclass(frozen=True)
class TextChunk:
    """A single window of one document, positioned for re-assembly."""

    document_index: int
    start: int
    text: str


@dataclass(frozen=True)
class ChunkHit:
    """One ranked search result: a chunk plus its position and score."""

    index: int
    chunk: TextChunk
    score: float


# --------------------------------------------------------------------------- #
# Chunking
# --------------------------------------------------------------------------- #


def _chunk_text(text: str, document_index: int) -> list[TextChunk]:
    """Slide a ``CHUNK_CHARS`` window (with ``CHUNK_OVERLAP``) over ``text``."""
    chunks: list[TextChunk] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(length, start + CHUNK_CHARS)
        window = text[start:end]
        if window.strip():
            chunks.append(TextChunk(document_index, start, window))
        if end >= length:
            break
        start = max(start + 1, end - CHUNK_OVERLAP)
    return chunks


def _chunk_documents(documents: Sequence[str]) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    for index, document in enumerate(documents):
        chunks.extend(_chunk_text(document, index))
    return chunks


def _total_length(documents: Sequence[str]) -> int:
    return sum(len(document) for document in documents)


# --------------------------------------------------------------------------- #
# Retrieval query
# --------------------------------------------------------------------------- #


def _build_retrieval_query() -> str:
    """A pinned query describing what the SCT intake needs to find."""
    return (
        "Find the passages stating the claimant and respondent names and the "
        "claimant's NRIC; the nature of the dispute (contract for sale of "
        "goods, contract for provision of services, damage to property, or "
        "lease not exceeding two years); the amount of money claimed; the "
        "date the cause of action arose; and the date the contract was made."
    )


# --------------------------------------------------------------------------- #
# Vector math
# --------------------------------------------------------------------------- #


def _normalize(vector: ArrayLike) -> np.ndarray:
    """Return ``vector`` as a unit-norm numpy array (zeros stay zeros)."""
    array = np.asarray(vector, dtype="float64")
    norm = float(np.linalg.norm(array))
    if norm == 0.0:
        return array
    return array / norm


def _cosine_similarity(a: ArrayLike, b: ArrayLike) -> float:
    """Cosine similarity between two vectors (each normalised internally)."""
    unit_a = _normalize(a)
    unit_b = _normalize(b)
    if unit_a.size == 0 or unit_b.size == 0:
        return 0.0
    return float(np.dot(unit_a, unit_b))


# --------------------------------------------------------------------------- #
# Budget selection + reassembly
# --------------------------------------------------------------------------- #


def _select_top_chunks_within_budget(
    scored: list[tuple[TextChunk, float]], max_chars: int
) -> list[TextChunk]:
    """Take the best chunks greedily until the character budget is exhausted.

    The top chunk is always kept; if a chunk only partly fits, its tail is
    trimmed to the remaining budget and selection stops.
    """
    selected: list[TextChunk] = []
    used = 0
    for chunk, _score in scored:
        size = len(chunk.text)
        if used + size <= max_chars:
            selected.append(chunk)
            used += size
            continue
        room = max_chars - used
        if room > 0:
            selected.append(TextChunk(chunk.document_index, chunk.start, chunk.text[:room]))
            used += room
        break
    return selected


def _join_documents(documents: Sequence[str]) -> str:
    return _DOCUMENT_SEPARATOR.join(documents)


def _join_chunks_in_reading_order(chunks: Sequence[TextChunk]) -> str:
    """Re-sort selected chunks back into document/reading order and join."""
    ordered = sorted(chunks, key=lambda chunk: (chunk.document_index, chunk.start))
    joined = _CHUNK_SEPARATOR.join(chunk.text for chunk in ordered)
    return joined


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #


def build_extraction_text(
    documents: Sequence[str],
    *,
    embedder: EmbeddingModel | None = None,
    max_chars: int = MAX_CONTEXT_CHARS,
) -> str:
    """Produce the single bounded text that a field extractor should read.

    - Blank/short corpora that fit ``max_chars`` are joined and returned as-is
      (no embeddings needed, so ``embedder`` may be ``None``).
    - Oversized corpora are chunked and embedded, the generic SCT query is
      embedded, the top chunks within ``max_chars`` are selected by cosine
      similarity, re-sorted into original reading order, and joined.
    """
    if not isinstance(documents, (list, tuple)) or not documents:
        raise ValueError("at least one document is required.")
    if any(not isinstance(document, str) for document in documents):
        raise TypeError("documents must be plain strings.")
    documents = [document for document in documents if document.strip()]
    if not documents:
        raise ValueError("documents contained no non-blank content.")
    if max_chars <= 0:
        raise ValueError("max_chars must be positive.")

    if _total_length(documents) <= max_chars:
        return _join_documents(documents)

    if embedder is None:
        raise EmbeddingError(
            "documents exceed the context budget and no embedder was supplied; "
            "pass embedder=default_embedding_model() (or another EmbeddingModel) "
            "so the corpus can be pruned by semantic search."
        )

    chunks = _chunk_documents(documents)
    if not chunks:
        raise ValueError("documents produced no chunkable content.")

    vectors = embedder.embed([chunk.text for chunk in chunks])
    if len(vectors) != len(chunks):
        raise EmbeddingError(
            f"embedder returned {len(vectors)} vectors for {len(chunks)} chunks."
        )

    unit_vectors = [_normalize(vector) for vector in vectors]

    query_vectors = embedder.embed([_build_retrieval_query()])
    if not query_vectors:
        raise EmbeddingError("embedder returned no vector for the retrieval query.")
    unit_query = _normalize(query_vectors[0])

    scored: list[tuple[TextChunk, float]] = []
    for index, chunk in enumerate(chunks):
        similarity = _cosine_similarity(unit_vectors[index], unit_query)
        scored.append((chunk, similarity))
    scored.sort(key=lambda pair: pair[1], reverse=True)

    selected = _select_top_chunks_within_budget(scored, max_chars)
    joined = _join_chunks_in_reading_order(selected)
    if len(joined) > max_chars:  # final guard for separator overhead
        joined = joined[:max_chars]
    return joined


# --------------------------------------------------------------------------- #
# Reusable document index (chunk + embed once, search many times)
# --------------------------------------------------------------------------- #


class DocumentIndex:
    """A chunked, embedded corpus that supports repeated semantic search.

    All chunk vectors are computed once at construction; each :meth:`search`
    embeds only the query, and :meth:`seed` provides the same top-within-budget
    context ``build_extraction_text`` assembles for an oversized corpus, so an
    agentic extractor can start from today's seed and then refine with targeted
    queries against previously-unseen chunks.
    """

    def __init__(
        self,
        documents: Sequence[str],
        *,
        embedder: EmbeddingModel,
    ) -> None:
        documents = [doc for doc in documents if doc.strip()]
        if not documents:
            raise ValueError("documents contained no non-blank content.")
        self._chunks = _chunk_documents(documents)
        if not self._chunks:
            raise ValueError("documents produced no chunkable content.")

        vectors = embedder.embed([chunk.text for chunk in self._chunks])
        if len(vectors) != len(self._chunks):
            raise EmbeddingError(
                f"embedder returned {len(vectors)} vectors for "
                f"{len(self._chunks)} chunks."
            )
        self._unit_vectors = [_normalize(vector) for vector in vectors]
        self._embedder = embedder

    @property
    def chunks(self) -> list[TextChunk]:
        """Every chunk in the index, in reading order."""
        return list(self._chunks)

    def search(
        self,
        query: str,
        *,
        k: int = 3,
        seen: set[int] | None = None,
    ) -> list[ChunkHit]:
        """Return the top ``k`` chunks for ``query``, skipping any in ``seen``."""
        if not query or not query.strip():
            raise ValueError("query must be a non-empty string.")
        if k <= 0:
            return []
        query_vectors = self._embedder.embed([query])
        if not query_vectors:
            raise EmbeddingError("embedder returned no vector for the search query.")
        unit_query = _normalize(query_vectors[0])

        excluded = set(seen) if seen else set()
        scored: list[tuple[int, TextChunk, float]] = []
        for index, (chunk, vector) in enumerate(
            zip(self._chunks, self._unit_vectors)
        ):
            if index in excluded:
                continue
            scored.append(
                (index, chunk, _cosine_similarity(vector, unit_query))
            )
        scored.sort(key=lambda triple: triple[2], reverse=True)
        return [
            ChunkHit(index, chunk, score)
            for index, chunk, score in scored[:k]
        ]

    def seed(self, max_chars: int = MAX_CONTEXT_CHARS) -> tuple[list[int], str]:
        """Return ``(chunk indices, joined text)`` for the best chunks within
        ``max_chars`` using the pinned SCT retrieval query."""
        query_vectors = self._embedder.embed([_build_retrieval_query()])
        if not query_vectors:
            raise EmbeddingError("embedder returned no vector for the retrieval query.")
        unit_query = _normalize(query_vectors[0])

        scored: list[tuple[TextChunk, float]] = []
        for chunk, vector in zip(self._chunks, self._unit_vectors):
            scored.append((chunk, _cosine_similarity(vector, unit_query)))
        scored.sort(key=lambda pair: pair[1], reverse=True)

        selected = _select_top_chunks_within_budget(scored, max_chars)
        by_start = {
            (chunk.document_index, chunk.start): index
            for index, chunk in enumerate(self._chunks)
        }
        indices: list[int] = []
        for chunk in selected:
            position = by_start[(chunk.document_index, chunk.start)]
            if position not in indices:
                indices.append(position)
        joined = _join_chunks_in_reading_order(selected)
        if len(joined) > max_chars:  # final guard for separator overhead
            joined = joined[:max_chars]
        return indices, joined
