"""Embedding providers behind one :class:`EmbeddingModel` seam.

Two real implementations are provided:

- :class:`SentenceTransformerEmbeddingModel` — an in-process local model
  (sentence-transformers, default ``BAAI/bge-small-en-v1.5``). The heavy model
  and its dependencies are imported/loaded lazily on the first ``embed()``
  call, and Hugging Face caches the weights in ``~/.cache/huggingface/hub``.
- :class:`HTTPEmbeddingModel` — OpenAI-compatible ``POST {base_url}/embeddings``
  for local FastAPI services or any compatible server.

:func:`default_embedding_model` picks the local model unless an embedding HTTP
endpoint is configured (``OPENAI_EMBEDDING_BASE_URL`` set or
``EMBEDDING_BACKEND=http``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

import numpy as np
import requests

from .config import (
    DEFAULT_EMBEDDING_MODEL_NAME,
    EMBEDDING_BACKEND_HTTP,
    get_config,
)
from .errors import EmbeddingError

#: Embedding requests are batched to this many texts per HTTP call.
EMBED_BATCH = 64

REQUEST_TIMEOUT_SECONDS = 60


class EmbeddingModel(Protocol):
    """Contract every embedding source must satisfy.

    ``embed`` returns one vector (``list[float]``) per input text, in input
    order.  Vectors are only ever compared against vectors from the SAME model
    instance, so the dimension may be anything the provider produces.
    """

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class HTTPEmbeddingModel:
    """Real implementation: OpenAI-compatible POST to ``{base_url}/embeddings``.

    Speaks exactly the contract a local FastAPI embedding service (or OpenAI)
    exposes.  ``session`` may be injected for unit tests / shared transports.
    """

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str = "",
        model: str = "",
        session: Any = None,
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
                f"(expected {len(batch)}, got "
                f"{len(data) if isinstance(data, list) else 'none'})."
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


class SentenceTransformerEmbeddingModel:
    """In-process local embeddings via sentence-transformers.

    The sentence-transformers/torch import and the model download+load happen
    lazily on the first :meth:`embed` call, so constructing this object (or the
    default factory) never touches the network or the heavy stack.
    """

    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL_NAME) -> None:
        self.model_name = model_name
        self._model: Any = None

    def _load_model(self) -> Any:
        """Create the underlying sentence-transformer (lazy; overridable)."""
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(self.model_name)

    # -- EmbeddingModel ---------------------------------------------------- #
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        text_list = list(texts)
        if not text_list:
            return []
        if self._model is None:
            self._model = self._load_model()
        vectors = self._model.encode(
            text_list,
            convert_to_numpy=True,
            normalize_embeddings=False,
        )
        array = np.asarray(vectors, dtype="float64")
        if array.ndim == 1:
            array = array.reshape(1, -1)
        return array.tolist()


def default_embedding_model() -> EmbeddingModel:
    """Pick the configured embedding provider.

    Returns an :class:`HTTPEmbeddingModel` when an embedding endpoint is
    configured (``OPENAI_EMBEDDING_BASE_URL`` set or
    ``EMBEDDING_BACKEND=http``); otherwise the local sentence-transformers
    model from ``EMBEDDING_MODEL_NAME`` (default bge-small-en-v1.5).
    """
    config = get_config()
    use_http = (
        config.embedding_backend == EMBEDDING_BACKEND_HTTP
        or config.embedding_base_url_raw is not None
    )
    if use_http:
        return HTTPEmbeddingModel(
            config.embedding_base_url,
            api_key=config.embedding_api_key,
            model=config.embedding_model,
        )
    return SentenceTransformerEmbeddingModel(config.embedding_model_name)
