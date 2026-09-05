"""Shared pytest fixtures: offline HTTP stubs for the request-based modules."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


class StubResponse:
    """Minimal stand-in for ``requests.Response`` (status/text/json only)."""

    def __init__(
        self, payload: Any, status_code: int = 200, json_error: bool = False
    ) -> None:
        self.status_code = status_code
        self.text = payload if isinstance(payload, str) else json.dumps(payload)
        self._payload = payload
        self._json_error = json_error

    def json(self) -> Any:
        if self._json_error:
            raise ValueError("response was not valid JSON")
        return self._payload


class StubSession:
    """Duck-typed ``requests.Session`` that records POSTs and answers canned.

    ``payloads`` is a list of bodies returned one per call (a single non-list
    payload is wrapped); ``error`` makes the first call raise a transport
    exception; ``json_error`` makes responses fail ``.json()``; recorded calls
    are available on ``calls``.
    """

    def __init__(
        self,
        payloads: Any = None,
        *,
        status_code: int = 200,
        error: Exception | None = None,
        json_error: bool = False,
    ) -> None:
        self._queue: list[Any] = (
            [payloads] if not isinstance(payloads, list) else list(payloads)
        )
        self.status_code = status_code
        self.error = error
        self.json_error = json_error
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> StubResponse:
        self.calls.append({"url": url, **kwargs})
        if self.error is not None:
            raise self.error
        payload = self._queue.pop(0) if self._queue else {}
        return StubResponse(payload, self.status_code, self.json_error)


@pytest.fixture
def make_stub() -> Any:
    """Factory fixture -> ``make_stub(payloads, status_code=200, error=None)``."""

    def _make(
        payloads: Any = None,
        *,
        status_code: int = 200,
        error: Exception | None = None,
        json_error: bool = False,
    ) -> StubSession:
        return StubSession(
            payloads,
            status_code=status_code,
            error=error,
            json_error=json_error,
        )

    return _make


# --------------------------------------------------------------------------- #
# Local embedding model (integration tests; lazily downloaded on first use)
# --------------------------------------------------------------------------- #

#: Local embedding model used to vectorise claim chunks. Loaded by the
#: ``embedding_model`` fixture; sentence-transformers downloads it into
#: ``~/.cache/huggingface/hub`` on first use and reuses the cache afterwards.
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

#: Output dimension of ``EMBEDDING_MODEL_NAME`` (fixed for bge-small-en-v1.5).
EMBEDDING_MODEL_DIMENSION = 384


@pytest.fixture(scope="session")
def embedding_model() -> Iterator[SentenceTransformer]:
    """Sentence-transformer model, loaded exactly once per test session.

    The first session triggers an automatic model download to the global
    Hugging Face cache; later sessions load straight from disk. The heavy
    ``sentence_transformers`` import is deferred until a test asks for the
    fixture so fast unit tests never pay the torch import cost.
    """
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    yield model
