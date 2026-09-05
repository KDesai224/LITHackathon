"""Unit tests for ``sct_intake.retrieval`` + ``sct_intake.embedders``."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise
from typing import Any

import numpy as np
import pytest
import requests
from hypothesis import given, settings
from hypothesis import strategies as st

import sct_intake.embedders as se
import sct_intake.retrieval as sr
from sct_intake.embedders import HTTPEmbeddingModel
from tests.helpers import KeywordHashEmbedder

SCT_TEXT = (
    "John Doe (NRIC G2677383R) sold his sofa to Jane Ong for $10,000.00. "
    "Payment was due on 2026-09-02 after delivery but Jane Ong has not paid."
) * 20

NOISE_TEXT = (
    "Recipe: cook penne until al dente, toss with basil pesto, toasted pine "
    "nuts, and grated parmesan; serve immediately."
) * 20


# --------------------------------------------------------------------------- #
# Chunking
# --------------------------------------------------------------------------- #


def test_chunk_text_empty_and_whitespace_only() -> None:
    assert sr._chunk_text("", 0) == []
    assert sr._chunk_text("   \n\t  ", 0) == []


def test_chunk_text_single_window_for_small_text() -> None:
    chunks = sr._chunk_text("x" * 100, 0)
    assert len(chunks) == 1
    assert chunks[0].text == "x" * 100
    assert chunks[0].start == 0
    assert chunks[0].document_index == 0


def test_chunk_text_windows_size_and_overlap() -> None:
    text = "a" * (sr.CHUNK_CHARS * 3 + 50)
    chunks = sr._chunk_text(text, 7)
    assert all(c.document_index == 7 for c in chunks)
    assert chunks[0].start == 0
    assert len(chunks[-1].text) <= sr.CHUNK_CHARS
    starts = [c.start for c in chunks]
    assert starts == sorted(starts)
    for left, right in pairwise(chunks):
        assert right.start == left.start + sr.CHUNK_CHARS - sr.CHUNK_OVERLAP


def test_chunk_text_no_gaps() -> None:
    text = "b" * 3000
    chunks = sr._chunk_text(text, 0)
    cursor = 0
    for chunk in chunks:
        assert chunk.start <= cursor
        cursor = max(cursor, chunk.start + len(chunk.text))
    assert cursor == len(text)


@given(st.text(min_size=1, max_size=3000))
@settings(max_examples=50)
def test_chunk_text_covers_every_character(text: str) -> None:
    if not text.strip():
        return
    chunks = sr._chunk_text(text, 0)
    assert chunks
    covered = set()
    for chunk in chunks:
        covered.update(range(chunk.start, chunk.start + len(chunk.text)))
    assert covered == set(range(len(text)))


def test_chunk_documents_tracks_indices() -> None:
    docs = ["aaaa", "", "cccccccc"]
    chunks = sr._chunk_documents(docs)
    assert [c.document_index for c in chunks] == [0, 2]
    assert [c.text for c in chunks] == ["aaaa", "cccccccc"]


def test_total_length() -> None:
    assert sr._total_length(["abc", "de", ""]) == 5


# --------------------------------------------------------------------------- #
# Vector math
# --------------------------------------------------------------------------- #


def test_normalize_unit_vector() -> None:
    unit = sr._normalize([3.0, 4.0])
    assert float(np.linalg.norm(unit)) == pytest.approx(1.0)
    assert list(unit) == pytest.approx([0.6, 0.8])


def test_normalize_zero_vector_unchanged() -> None:
    assert list(sr._normalize([0.0, 0.0])) == [0.0, 0.0]


def test_normalize_accepts_numpy_array() -> None:
    unit = sr._normalize(np.array([0.0, 2.0]))
    assert float(np.linalg.norm(unit)) == pytest.approx(1.0)


def test_cosine_similarity_identities() -> None:
    assert sr._cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert sr._cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert sr._cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_similarity_zero_vectors() -> None:
    assert sr._cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
    assert sr._cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0


def test_cosine_similarity_empty_vectors() -> None:
    assert sr._cosine_similarity([], []) == 0.0
    assert sr._cosine_similarity([], [1.0, 2.0]) == 0.0


def test_cosine_similarity_mismatched_dimensions() -> None:
    with pytest.raises(ValueError):
        sr._cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])


@st.composite
def _vector_pair(draw: Any) -> tuple[list[float], list[float]]:
    length = draw(st.integers(min_value=2, max_value=8))
    magnitudes_a = draw(
        st.lists(
            st.floats(min_value=1e-3, max_value=10, allow_nan=False, allow_infinity=False),
            min_size=length,
            max_size=length,
        )
    )
    magnitudes_b = draw(
        st.lists(
            st.floats(min_value=1e-3, max_value=10, allow_nan=False, allow_infinity=False),
            min_size=length,
            max_size=length,
        )
    )
    signs = draw(st.lists(st.booleans(), min_size=length, max_size=length))
    return (
        [value if sign else -value for value, sign in zip(magnitudes_a, signs)],
        magnitudes_b,
    )


@given(_vector_pair())
@settings(max_examples=50)
def test_cosine_similarity_matches_numpy_formula(
    pair: tuple[list[float], list[float]],
) -> None:
    a, b = pair
    result = sr._cosine_similarity(a, b)
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    assert norm_a > 0.0 and norm_b > 0.0
    expected = float(np.dot(a, b)) / (norm_a * norm_b)
    assert result == pytest.approx(expected)


# --------------------------------------------------------------------------- #
# Budget selection and reassembly
# --------------------------------------------------------------------------- #


def _chunk(text: str, doc: int = 0, start: int = 0) -> sr.TextChunk:
    return sr.TextChunk(doc, start, text)


def test_select_top_chunks_fits_all() -> None:
    scored = [(_chunk("aa", start=0), 1.0), (_chunk("bb", start=2), 0.5)]
    assert sr._select_top_chunks_within_budget(scored, max_chars=10) == [
        scored[0][0],
        scored[1][0],
    ]


def test_select_top_chunks_greedy_cap() -> None:
    scored = [
        (_chunk("x" * 6, start=0), 1.0),
        (_chunk("y" * 6, start=6), 0.5),
        (_chunk("z" * 2, start=12), 0.1),
    ]
    chosen = sr._select_top_chunks_within_budget(scored, max_chars=8)
    assert len(chosen) == 2
    assert chosen[0].text == "x" * 6
    assert chosen[1].text == "yy"  # remaining 2 chars of the next best chunk


def test_select_top_chunks_truncates_oversized_top_chunk() -> None:
    scored = [(_chunk("z" * 50, start=0), 1.0)]
    chosen = sr._select_top_chunks_within_budget(scored, max_chars=10)
    assert len(chosen) == 1
    assert chosen[0].text == "z" * 10


def test_select_top_chunks_zero_budget() -> None:
    scored = [(_chunk("z", start=0), 1.0)]
    assert sr._select_top_chunks_within_budget(scored, max_chars=0) == []


def test_join_documents_uses_separator() -> None:
    assert sr._join_documents(["a", "b"]) == "a" + sr._DOCUMENT_SEPARATOR + "b"


def test_join_chunks_in_reading_order() -> None:
    chunks = [
        _chunk("b", doc=0, start=1),
        _chunk("c", doc=1, start=0),
        _chunk("a", doc=0, start=0),
    ]
    assert sr._join_chunks_in_reading_order(chunks) == f"a{sr._CHUNK_SEPARATOR}b{sr._CHUNK_SEPARATOR}c"


# --------------------------------------------------------------------------- #
# build_extraction_text
# --------------------------------------------------------------------------- #


def test_build_short_corpus_skips_embeddings() -> None:
    text = sr.build_extraction_text(["first doc", "second doc"])
    assert text == f"first doc{sr._DOCUMENT_SEPARATOR}second doc"


def test_build_filters_blank_documents() -> None:
    text = sr.build_extraction_text(["", "  real doc  "])
    assert text == "  real doc  "


@pytest.mark.parametrize("docs", [[], ["", "   "]])
def test_build_rejects_empty_or_blank_corpus(docs: list[str]) -> None:
    with pytest.raises(ValueError):
        sr.build_extraction_text(docs)


def test_build_rejects_non_string_document() -> None:
    with pytest.raises(TypeError):
        sr.build_extraction_text(["ok", 42])  # type: ignore[list-item]


def test_build_rejects_non_positive_budget() -> None:
    with pytest.raises(ValueError):
        sr.build_extraction_text(["x"], max_chars=0)


def test_build_oversized_without_embedder_raises() -> None:
    with pytest.raises(sr.EmbeddingError):
        sr.build_extraction_text([SCT_TEXT, NOISE_TEXT], max_chars=100)


def test_build_prunes_and_keeps_relevant_facts() -> None:
    text = sr.build_extraction_text(
        [SCT_TEXT, NOISE_TEXT],
        embedder=KeywordHashEmbedder(),
        max_chars=1500,
    )
    assert len(text) <= 1500
    assert "John Doe" in text and "G2677383R" in text
    assert "pesto" not in text


class _EmptyEmbedder:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return []


def test_build_rejects_wrong_vector_count() -> None:
    with pytest.raises(sr.EmbeddingError):
        sr.build_extraction_text(
            [SCT_TEXT, NOISE_TEXT], embedder=_EmptyEmbedder(), max_chars=100
        )


class _NoQueryEmbedder:
    def __init__(self) -> None:
        self._calls = 0

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self._calls += 1
        if self._calls == 1:
            return [[0.0] * 4 for _ in texts]
        return []


def test_build_rejects_missing_query_vector() -> None:
    with pytest.raises(sr.EmbeddingError):
        sr.build_extraction_text(
            [SCT_TEXT, NOISE_TEXT], embedder=_NoQueryEmbedder(), max_chars=100
        )


def test_build_defensive_when_chunking_returns_nothing(monkeypatch) -> None:
    monkeypatch.setattr(sr, "_chunk_documents", lambda _docs: [])
    with pytest.raises(ValueError):
        sr.build_extraction_text(
            [SCT_TEXT, NOISE_TEXT], embedder=KeywordHashEmbedder(), max_chars=100
        )


# --------------------------------------------------------------------------- #
# HTTP embedding model
# --------------------------------------------------------------------------- #


def _embedding_body(vector: list[float]) -> dict[str, Any]:
    return {"model": "local", "data": [{"embedding": vector, "index": 0}]}


def test_http_embedding_payload_and_auth(make_stub) -> None:
    session = make_stub(_embedding_body([1.0, 2.0]))
    model = HTTPEmbeddingModel(
        "http://127.0.0.1:8000/v1",
        api_key="secret",
        model="local-model",
        session=session,
    )
    vectors = model.embed(["alpha"])
    assert vectors == [[1.0, 2.0]]
    call = session.calls[0]
    assert call["url"] == "http://127.0.0.1:8000/v1/embeddings"
    assert call["json"] == {"input": ["alpha"], "model": "local-model"}
    assert call["headers"]["Authorization"] == "Bearer secret"


def test_http_embedding_no_model_no_auth(make_stub) -> None:
    session = make_stub(_embedding_body([1.0, 2.0]))
    model = HTTPEmbeddingModel("http://127.0.0.1:8000/v1", session=session)
    model.embed(["alpha"])
    call = session.calls[0]
    assert "model" not in call["json"]
    assert "Authorization" not in call["headers"]


def test_http_embedding_batches(monkeypatch, make_stub) -> None:
    monkeypatch.setattr(se, "EMBED_BATCH", 2)
    first = {"model": "m", "data": [{"embedding": [0.1], "index": 0}, {"embedding": [0.2], "index": 1}]}
    second = {"model": "m", "data": [{"embedding": [0.3], "index": 0}]}
    session = make_stub([first, second])
    model = HTTPEmbeddingModel("http://127.0.0.1:8000/v1", model="m", session=session)
    vectors = model.embed(["a", "b", "c"])
    assert vectors == [[0.1], [0.2], [0.3]]
    assert len(session.calls) == 2
    assert session.calls[0]["json"]["input"] == ["a", "b"]
    assert session.calls[1]["json"]["input"] == ["c"]


def test_http_embedding_empty_input(make_stub) -> None:
    model = HTTPEmbeddingModel("http://127.0.0.1:8000/v1", session=make_stub())
    assert model.embed([]) == []
    assert model.embed(()) == []


def test_http_embedding_count_mismatch(make_stub) -> None:
    body = {"model": "m", "data": [{"embedding": [1.0], "index": 0}]}
    model = HTTPEmbeddingModel("http://127.0.0.1:8000/v1", session=make_stub(body))
    with pytest.raises(sr.EmbeddingError):
        model.embed(["a", "b"])


def test_http_embedding_item_not_object(make_stub) -> None:
    body = {"model": "m", "data": ["nope"]}
    model = HTTPEmbeddingModel("http://127.0.0.1:8000/v1", session=make_stub(body))
    with pytest.raises(sr.EmbeddingError):
        model.embed(["a"])


def test_http_embedding_missing_embedding_list(make_stub) -> None:
    body = {"model": "m", "data": [{"index": 0}]}
    model = HTTPEmbeddingModel("http://127.0.0.1:8000/v1", session=make_stub(body))
    with pytest.raises(sr.EmbeddingError):
        model.embed(["a"])


def test_http_embedding_http_error(make_stub) -> None:
    model = HTTPEmbeddingModel(
        "http://127.0.0.1:8000/v1", session=make_stub({"error": "boom"}, status_code=500)
    )
    with pytest.raises(sr.EmbeddingError):
        model.embed(["a"])


def test_http_embedding_bad_json(make_stub) -> None:
    model = HTTPEmbeddingModel("http://127.0.0.1:8000/v1", session=make_stub("nope"))
    with pytest.raises(sr.EmbeddingError):
        model.embed(["a"])


def test_http_embedding_json_decode_error(make_stub) -> None:
    model = HTTPEmbeddingModel(
        "http://127.0.0.1:8000/v1", session=make_stub("irrelevant", json_error=True)
    )
    with pytest.raises(sr.EmbeddingError):
        model.embed(["a"])


def test_http_embedding_transport_error(make_stub) -> None:
    model = HTTPEmbeddingModel(
        "http://127.0.0.1:8000/v1",
        session=make_stub(error=requests.ConnectionError("down")),
    )
    with pytest.raises(sr.EmbeddingError):
        model.embed(["a"])


# --------------------------------------------------------------------------- #
# Hash embedder double (test helper)
# --------------------------------------------------------------------------- #


def test_keyword_hash_embedder_deterministic_and_dimensional() -> None:
    embedder = KeywordHashEmbedder()
    first = embedder.embed(["hello world"])
    second = embedder.embed(["hello world"])
    assert first == second
    assert len(first[0]) == 1024


def test_keyword_hash_embedder_ranked_by_overlap() -> None:
    embedder = KeywordHashEmbedder()
    query = ["claimant Jane Ong dispute contract"]
    relevant = ["Jane Ong contract dispute claimant"]
    unrelated = ["pasta basil parmesan pine nuts pesto"]
    vectors = embedder.embed(relevant + unrelated)
    q = embedder.embed(query)[0]
    assert sr._cosine_similarity(vectors[0], q) > sr._cosine_similarity(vectors[1], q)
