"""Centralised environment configuration for the SCT intake pipeline.

``.env`` is loaded exactly once (idempotent) and takes precedence over any
pre-set environment variables (``override=True``), so a stale machine/user-level
``OPENAI_*`` value cannot shadow the repo's ``.env``. Every accessor builds a
fresh :class:`Config` from ``os.environ`` so tests that monkeypatch environment
variables keep working without process-global cache invalidation.

Env names are unchanged from the pre-refactor flat modules for compatibility:
chat uses ``OPENAI_*``; the embedding story keeps ``OPENAI_EMBEDDING_*`` plus
the new ``EMBEDDING_BACKEND`` and ``EMBEDDING_MODEL_NAME`` knobs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_EMBEDDING_BASE_URL = "http://127.0.0.1:8000/v1"
DEFAULT_EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

#: When ``"http"``, embeddings always use HTTPEmbeddingModel; otherwise a local
#: sentence-transformers model is the default (unless an embedding base URL is
#: explicitly configured, which also selects HTTP).
EMBEDDING_BACKEND_HTTP = "http"

_dotenv_loaded = False


def _load_dotenv_once() -> None:
    global _dotenv_loaded
    if not _dotenv_loaded:
        load_dotenv(override=True)
        _dotenv_loaded = True


@dataclass(frozen=True)
class Config:
    """Resolved configuration; all values come from ``os.environ``."""

    # --- chat / field extraction -----------------------------------------
    api_key: str | None
    base_url: str
    model: str
    chat_extra_body: str | None

    # --- embeddings --------------------------------------------------------
    embedding_backend: str | None  # EMBEDDING_BACKEND (None unless set)
    embedding_base_url_raw: str | None  # OPENAI_EMBEDDING_BASE_URL (None unless set)
    embedding_base_url: str  # raw or DEFAULT_EMBEDDING_BASE_URL
    embedding_api_key: str
    embedding_model: str  # provider-side model name for HTTP (may be "")
    embedding_model_name: str  # local sentence-transformers model id


def get_config() -> Config:
    """Build a :class:`Config` from the environment (fresh per call)."""
    _load_dotenv_once()
    base_url = os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)
    model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
    embedding_raw = os.environ.get("OPENAI_EMBEDDING_BASE_URL")
    return Config(
        api_key=os.environ.get("OPENAI_API_KEY"),
        base_url=base_url,
        model=model,
        chat_extra_body=os.environ.get("OPENAI_CHAT_EXTRA_BODY"),
        embedding_backend=os.environ.get("EMBEDDING_BACKEND"),
        embedding_base_url_raw=embedding_raw,
        embedding_base_url=embedding_raw or DEFAULT_EMBEDDING_BASE_URL,
        embedding_api_key=os.environ.get("OPENAI_EMBEDDING_API_KEY", ""),
        embedding_model=os.environ.get("OPENAI_EMBEDDING_MODEL", ""),
        embedding_model_name=os.environ.get(
            "EMBEDDING_MODEL_NAME", DEFAULT_EMBEDDING_MODEL_NAME
        ),
    )
