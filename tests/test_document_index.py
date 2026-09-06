"""Unit tests for the reusable ``DocumentIndex`` (chunk + embed once, search)."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

import sct_intake.retrieval as sr
from sct_intake import DocumentIndex
from tests.helpers import KeywordHashEmbedder

SCT_TEXT = (
    "John Doe (NRIC G2677383R) sold his sofa to Jane Ong for $10,000.00. "
    "Payment was due on 2026-09-02 after delivery but Jane Ong has not paid. "
) * 40  # ~3600 chars -> multiple chunks

NOISE_TEXT = (
    "Recipe: cook penne until al dente, toss with basil pesto, toasted pine "
    "nuts, and grated parmesan; serve immediately. "
) * 40


def _index(documents: Sequence[str]) -> DocumentIndex:
    return DocumentIndex(documents, embedder=KeywordHashEmbedder())


def test_index_rejects_blank_corpus() -> None:
    with pytest.raises(ValueError):
        DocumentIndex([], embedder=KeywordHashEmbedder())
    with pytest.raises(ValueError):
        DocumentIndex(["", "   "], embedder=KeywordHashEmbedder())


def test_index_chunks_preserve_document_indices() -> None:
    index = _index([SCT_TEXT, NOISE_TEXT])
    chunks = index.chunks
    assert chunks
    assert all(0 <= chunk.document_index <= 1 for chunk in chunks)
    assert {chunk.document_index for chunk in chunks} == {0, 1}


class _EmptyEmbedder:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return []


def test_index_rejects_wrong_vector_count() -> None:
    with pytest.raises(sr.EmbeddingError):
        DocumentIndex([SCT_TEXT], embedder=_EmptyEmbedder())


def test_search_ranks_relevant_document_first() -> None:
    index = _index([SCT_TEXT, NOISE_TEXT])
    hits = index.search("claimant Jane Ong contract dispute sofa", k=3)
    assert hits
    assert hits[0].chunk.document_index == 0
    assert "Jane Ong" in hits[0].chunk.text or "John Doe" in hits[0].chunk.text


def test_search_skips_seen_chunks() -> None:
    index = _index([SCT_TEXT])
    first = index.search("sofa delivery payment", k=1)
    assert len(first) == 1
    seen = {first[0].index}
    second = index.search("sofa delivery payment", k=10, seen=seen)
    assert all(hit.index not in seen for hit in second)


def test_search_respects_k() -> None:
    index = _index([SCT_TEXT])
    assert index.search("sofa", k=1) == index.search("sofa", k=1)[:1]
    assert len(index.search("sofa", k=1)) == 1
    assert index.search("sofa", k=0) == []


def test_search_rejects_blank_query() -> None:
    index = _index([SCT_TEXT])
    with pytest.raises(ValueError):
        index.search("   ", k=1)


def test_seed_respects_budget_and_returns_readable_text() -> None:
    index = _index([SCT_TEXT, NOISE_TEXT])
    indices, text = index.seed(max_chars=1500)
    assert len(text) <= 1500
    assert indices
    assert "Jane Ong" in text
    assert "pesto" not in text
    assert len(set(indices)) == len(indices)


def test_seed_indices_map_back_to_searchable_chunks() -> None:
    index = _index([SCT_TEXT, NOISE_TEXT])
    indices, _text = index.seed(max_chars=2500)
    excluded = set(indices)
    hits = index.search("sofa", k=10, seen=excluded)
    assert all(hit.index not in excluded for hit in hits)
