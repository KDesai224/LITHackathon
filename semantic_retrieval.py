"""
``semantic_retrieval`` : chunk, embed, and semantically select the parts of
uploaded claim documents that matter, then reassemble ONE bounded text.

Pipeline (fed into ``field_extractor.extract_fields`` unchanged):
    uploaded documents (plain text, one ``str`` per file)
      -> chunking
      -> embeddings  (LOCAL model; the actual model ships later)
      -> in-memory semantic search (top-k chunks by cosine similarity)
      -> reassemble the winners in original reading order -> one text

The embedding seam is deliberately thin: retrieval code depends only on
:class:`EmbeddingModel` (``embed(texts) -> list[list[float]]``), so whichever
local model is wired in later (an HTTP service, sentence-transformers, ...)
swaps in with no changes to the search logic.  The shipped real implementation,
:class:`HTTPEmbeddingModel`, POSTs the standard OpenAI-compatible ``/embeddings``
request -- the contract a local FastAPI embedding service should implement.

Small corpora never need the model: if every document together fits the
context budget (``max_chars``), ``build_extraction_text`` just joins them and
returns without embedding anything.

Env / .env configuration (loaded at call time, never at import):
    OPENAI_EMBEDDING_BASE_URL   (default http://127.0.0.1:8000/v1)
    OPENAI_EMBEDDING_API_KEY    (optional; local servers usually need none)
    OPENAI_EMBEDDING_MODEL      (optional; only sent when set)

Composition (client_upload.py / field_extractor.py are NOT modified):
    from semantic_retrieval import build_extraction_text, default_embedding_model
    from field_extractor import extract_fields
    from client_upload import SCTCase

    text = build_extraction_text(docs, embedder=default_embedding_model())
    case = SCTCase.from_text(text, extractor=extract_fields)
    print(case.summary())

Running ``python semantic_retrieval.py`` runs a deterministic stub-embedder
self-test only (no network, no model required).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

import numpy as np
import requests
from dotenv import load_dotenv
from numpy.typing import ArrayLike

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

#: Chunking: fixed character windows.
CHUNK_CHARS = 2000
CHUNK_OVERLAP = 200

#: Default context budget handed to field_extractor.
MAX_CONTEXT_CHARS = 24_000

#: Embedding requests are batched to this many texts per HTTP call.
EMBED_BATCH = 64

REQUEST_TIMEOUT_SECONDS = 60

#: Default local OpenAI-compatible embedding endpoint (FastAPI service later).
DEFAULT_EMBEDDING_BASE_URL = "http://127.0.0.1:8000/v1"

_DOCUMENT_SEPARATOR = "\n\n---\n\n"
_CHUNK_SEPARATOR = "\n\n"


class EmbeddingError(RuntimeError):
    """Raised when an embedding provider cannot produce valid vectors."""


# --------------------------------------------------------------------------- #
# Data types
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TextChunk:
    """A single window of one document, positioned for re-assembly."""

    document_index: int
    start: int
    text: str


# --------------------------------------------------------------------------- #
# Embedding seam (the interface the local model interacts with)
# --------------------------------------------------------------------------- #


class EmbeddingModel(Protocol):
    """Contract every embedding source must satisfy.

    ``embed`` returns one vector (``list[float]``) per input text, in input
    order.  Vectors are only ever compared against vectors from the SAME model
    instance, so the dimension may be anything the provider produces.
    """

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class HTTPEmbeddingModel:
    """Real implementation: OpenAI-compatible POST to ``{base_url}/embeddings``.

    This is the client half of the local-embedding design: the actual local
    model (shipped later) is expected to sit behind a FastAPI service exposing
    ``POST /v1/embeddings`` with an OpenAI-shaped body/response, and this class
    speaks exactly that contract.  ``session`` may be injected for unit tests
    (mock transport) and for sharing a transport with future modules.
    """

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str = "",
        model: str = "",
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._session = session if session is not None else requests.Session()

    # -- EmbeddingModel ---------------------------------------------------- #
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        texts = list(texts)
        if not texts:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH):
            vectors.extend(self._embed_batch(texts[start : start + EMBED_BATCH]))
        return vectors

    # -- Internals ---------------------------------------------------------- #
    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        url = self._base_url.rstrip("/") + "/embeddings"
        payload: dict[str, Any] = {"input": batch}
        if self._model:
            payload["model"] = self._model
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            response = self._session.post(
                url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS
            )
        except requests.RequestException as exc:
            raise EmbeddingError(
                f"embeddings transport error for {url}: {exc}"
            ) from exc
        if response.status_code != 200:
            raise EmbeddingError(
                f"embeddings returned HTTP {response.status_code} from {url}: "
                f"{response.text[:500]}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise EmbeddingError("embeddings response was not valid JSON") from exc

        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list) or len(data) != len(batch):
            raise EmbeddingError(
                "embeddings response 'data' length does not match the input "
                f"(expected {len(batch)}, got {len(data) if isinstance(data, list) else 'none'})."
            )
        return [self._extract_embedding(item) for item in data]

    @staticmethod
    def _extract_embedding(item: Any) -> list[float]:
        if not isinstance(item, dict):
            raise EmbeddingError("embeddings response item was not an object.")
        embedding = item.get("embedding")
        if not isinstance(embedding, list):
            raise EmbeddingError(
                "embeddings response item missing a list-valued 'embedding'."
            )
        return [float(value) for value in embedding]


def default_embedding_model() -> HTTPEmbeddingModel:
    """Build the configured HTTP embedding client from the environment.

    Reads ``OPENAI_EMBEDDING_BASE_URL`` (falling back to
    ``http://127.0.0.1:8000/v1``), plus optional ``OPENAI_EMBEDDING_API_KEY``
    and ``OPENAI_EMBEDDING_MODEL``.  Values are read at call time so a missing
    or later-added .env never breaks imports.
    """
    load_dotenv()
    base_url = os.environ.get("OPENAI_EMBEDDING_BASE_URL") or DEFAULT_EMBEDDING_BASE_URL
    api_key = os.environ.get("OPENAI_EMBEDDING_API_KEY") or ""
    model = os.environ.get("OPENAI_EMBEDDING_MODEL") or ""
    return HTTPEmbeddingModel(base_url, api_key=api_key, model=model)


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
    """Produce the single bounded text that ``field_extractor`` should read.

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
# Deterministic stub embedder (tests + __main__ demo only)
# --------------------------------------------------------------------------- #


def _stable_hash(text: str) -> int:
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class _KeywordHashEmbedder:
    """Private deterministic stand-in for the real local embedding model.

    Produces a fixed-width bag-of-keywords vector per text, so shared
    vocabulary yields real cosine similarity.  Used ONLY by the self-test and
    demo -- never by production code.  Replace with the real model wrapper.
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


# --------------------------------------------------------------------------- #
# HTTP-mock types for the self-test (no network)
# --------------------------------------------------------------------------- #


class _StubResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self.status_code = status_code
        self.text = json.dumps(payload)
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _StubSession:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self._status_code = status_code
        self.request: dict[str, Any] = {}

    def post(self, url: str, **kwargs: Any) -> _StubResponse:
        self.request = {"url": url, **kwargs}
        return _StubResponse(self._payload, self._status_code)


# --------------------------------------------------------------------------- #
# CLI self-test (stub embedder / stub HTTP session; never a network call)
# --------------------------------------------------------------------------- #

_SCT_LIKE_DOC = (
    "Claim: John Doe (NRIC G2677383R) sold his sofa to Jane Ong for "
    "$10,000.00. Payment was due on 2026-09-02 after delivery, but Jane Ong "
    "has not paid. John Doe now claims the full amount from Jane Ong.\n"
) * 12

_UNRELATED_DOC = (
    "Recipe: cook penne until al dente, toss with basil pesto, toasted pine "
    "nuts, and grated parmesan; serve immediately with a glass of water.\n"
) * 12


def _expect_raises(exc_type: type[Exception], fn: Any, label: str) -> None:
    try:
        fn()
    except exc_type as exc:
        print(f"  ok ({label}): raised {exc_type.__name__}: {exc}")
    else:
        raise AssertionError(f"{label}: expected {exc_type.__name__} to be raised")


def _run_self_test() -> None:
    # ---- 1. Short corpus: joined as-is, no embedder needed ---------------- #
    small = ["First document.", "Second document."]
    joined = build_extraction_text(small)
    assert joined == "First document.\n\n---\n\nSecond document."
    print("  ok (short corpus): returned full join without an embedder")

    # ---- 2. Oversized corpus: semantic pruning picks the SCT-like doc ------ #
    text = build_extraction_text(
        [_SCT_LIKE_DOC, _UNRELATED_DOC],
        embedder=_KeywordHashEmbedder(),
        max_chars=1500,
    )
    assert len(text) <= 1500
    assert "John Doe" in text and "G2677383R" in text and "$10,000.00" in text
    assert "pesto" not in text
    print("  ok (pruning): semantically selected SCT content, dropped the noise")
    print("      assembled preview:")
    for line in text.splitlines()[:4]:
        print(f"        {line}")

    # ---- 3. Same oversized corpus, no embedder -> EmbeddingError ---------- #
    _expect_raises(
        EmbeddingError,
        lambda: build_extraction_text([_SCT_LIKE_DOC, _UNRELATED_DOC], max_chars=1500),
        "pruning without an embedder",
    )

    # ---- 4. Empty / blank inputs -> ValueError ----------------------------- #
    _expect_raises(ValueError, lambda: build_extraction_text([]), "empty documents")
    _expect_raises(
        ValueError,
        lambda: build_extraction_text(["", "   \n  "]),
        "blank documents",
    )
    _expect_raises(
        TypeError,
        lambda: build_extraction_text(cast(list[str], ["ok", 42])),
        "non-string document",
    )

    # ---- 5. HTTP embedding model against a stub session (no network) ------ #
    canned = {
        "model": "local-model",
        "data": [
            {"embedding": [1.0, 2.0], "index": 0},
            {"embedding": [3.0, 4.0], "index": 1},
        ],
    }
    session = _StubSession(canned)
    model = HTTPEmbeddingModel(
        "http://127.0.0.1:8000/v1",
        api_key="secret",
        model="local-model",
        session=cast(requests.Session, session),
    )
    vectors = model.embed(["alpha", "beta"])
    assert vectors == [[1.0, 2.0], [3.0, 4.0]]
    assert session.request["url"] == "http://127.0.0.1:8000/v1/embeddings"
    sent = session.request["json"]
    assert sent == {"input": ["alpha", "beta"], "model": "local-model"}
    assert session.request["headers"]["Authorization"] == "Bearer secret"

    bare_session = _StubSession(
        {"model": "local-model", "data": [{"embedding": [1.0, 2.0], "index": 0}]}
    )
    bare = HTTPEmbeddingModel(
        "http://127.0.0.1:8000/v1",
        session=cast(requests.Session, bare_session),
    )
    bare.embed(["alpha"])
    assert "Authorization" not in bare_session.request["headers"]
    assert "model" not in bare_session.request["json"]
    print("  ok (http embedder): payload/auth built correctly, vectors parsed")

    _expect_raises(
        EmbeddingError,
        lambda: HTTPEmbeddingModel(
            "http://127.0.0.1:8000/v1",
            session=cast(
                requests.Session,
                _StubSession({"error": "boom"}, status_code=500),
            ),
        ).embed(["alpha"]),
        "HTTP 500 from embedder",
    )
    _expect_raises(
        EmbeddingError,
        lambda: HTTPEmbeddingModel(
            "http://127.0.0.1:8000/v1",
            session=cast(
                requests.Session,
                _StubSession({"data": [{"embedding": [1.0, 2.0]}]}),
            ),
        ).embed(["alpha", "beta"]),
        "embedding count mismatch",
    )


def main() -> int:
    print("semantic_retrieval self-test (stub embedder, no network):")
    _run_self_test()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
