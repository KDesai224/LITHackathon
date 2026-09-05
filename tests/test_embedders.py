"""Unit tests for ``sct_intake.embedders`` (factory + local adapter, no network)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from sct_intake import config as cfg
from sct_intake.embedders import (
    HTTPEmbeddingModel,
    SentenceTransformerEmbeddingModel,
    default_embedding_model,
)


@pytest.fixture(autouse=True)
def _fresh_embedding_env(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "_dotenv_loaded", True)
    for key in (
        "EMBEDDING_BACKEND",
        "OPENAI_EMBEDDING_BASE_URL",
        "OPENAI_EMBEDDING_API_KEY",
        "OPENAI_EMBEDDING_MODEL",
        "EMBEDDING_MODEL_NAME",
    ):
        monkeypatch.delenv(key, raising=False)


def test_default_backend_is_local_sentence_transformers() -> None:
    model = default_embedding_model()
    assert isinstance(model, SentenceTransformerEmbeddingModel)
    assert model.model_name == cfg.DEFAULT_EMBEDDING_MODEL_NAME


def test_local_backend_respects_model_name_env(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "other/local-model")
    model = default_embedding_model()
    assert isinstance(model, SentenceTransformerEmbeddingModel)
    assert model.model_name == "other/local-model"


def test_http_backend_when_base_url_configured(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_EMBEDDING_BASE_URL", "http://localhost:9999/v1")
    monkeypatch.setenv("OPENAI_EMBEDDING_API_KEY", "k")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "local")
    model = default_embedding_model()
    assert isinstance(model, HTTPEmbeddingModel)
    assert model._base_url == "http://localhost:9999/v1"
    assert model._api_key == "k"
    assert model._model == "local"


def test_http_backend_when_backend_forced(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_BACKEND", cfg.EMBEDDING_BACKEND_HTTP)
    model = default_embedding_model()
    assert isinstance(model, HTTPEmbeddingModel)
    assert model._base_url == cfg.DEFAULT_EMBEDDING_BASE_URL


class _FakeModel:
    def encode(self, texts: list[str], **kwargs: Any) -> Any:
        return np.asarray([[0.25] * 4 for _ in texts])


def test_sentence_transformer_embeds_and_caches(monkeypatch) -> None:
    model = SentenceTransformerEmbeddingModel("fake/model")
    fake = _FakeModel()
    monkeypatch.setattr(model, "_load_model", lambda: fake)

    first = model.embed(["hello", "world"])
    assert first == [[0.25, 0.25, 0.25, 0.25]] * 2
    second = model.embed(["again"])
    assert len(second) == 1
    assert model._model is fake  # loaded once and cached


class _FlatModel(_FakeModel):
    def encode(self, texts: list[str], **kwargs: Any) -> Any:
        return np.asarray([0.5, 0.5, 0.5, 0.5])


def test_sentence_transformer_normalises_single_vector_output(monkeypatch) -> None:
    model = SentenceTransformerEmbeddingModel("fake/model")
    monkeypatch.setattr(model, "_load_model", lambda: _FlatModel())
    vectors = model.embed(["only one"])
    assert vectors == [[0.5, 0.5, 0.5, 0.5]]


def test_sentence_transformer_empty_input_never_loads() -> None:
    model = SentenceTransformerEmbeddingModel("fake/model")
    assert model.embed([]) == []
    assert model._model is None
