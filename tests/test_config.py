"""Unit tests for ``sct_intake.config`` (env mapping and defaults)."""

from __future__ import annotations

import pytest

from sct_intake import config as cfg

CHAT_ENV = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_CHAT_EXTRA_BODY")
EMBED_ENV = (
    "EMBEDDING_BACKEND",
    "OPENAI_EMBEDDING_BASE_URL",
    "OPENAI_EMBEDDING_API_KEY",
    "OPENAI_EMBEDDING_MODEL",
    "EMBEDDING_MODEL_NAME",
)


@pytest.fixture(autouse=True)
def _fresh_config(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "_dotenv_loaded", True)  # never load repo .env
    for key in CHAT_ENV + EMBED_ENV:
        monkeypatch.delenv(key, raising=False)


def test_config_defaults_when_env_unset() -> None:
    config = cfg.get_config()
    assert config.api_key is None
    assert config.base_url == cfg.DEFAULT_BASE_URL
    assert config.model == cfg.DEFAULT_MODEL
    assert config.chat_extra_body is None
    assert config.embedding_backend is None
    assert config.embedding_base_url_raw is None
    assert config.embedding_base_url == cfg.DEFAULT_EMBEDDING_BASE_URL
    assert config.embedding_api_key == ""
    assert config.embedding_model == ""
    assert config.embedding_model_name == cfg.DEFAULT_EMBEDDING_MODEL_NAME


def test_config_maps_all_env_values(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("OPENAI_MODEL", "model-x")
    monkeypatch.setenv("OPENAI_CHAT_EXTRA_BODY", '{"seed": 7}')
    monkeypatch.setenv("EMBEDDING_BACKEND", cfg.EMBEDDING_BACKEND_HTTP)
    monkeypatch.setenv("OPENAI_EMBEDDING_BASE_URL", "http://localhost:9000/v1")
    monkeypatch.setenv("OPENAI_EMBEDDING_API_KEY", "k")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "provider-model")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "local/model")

    config = cfg.get_config()
    assert config.api_key == "sk-test"
    assert config.base_url == "https://example.test/v1"
    assert config.model == "model-x"
    assert config.chat_extra_body == '{"seed": 7}'
    assert config.embedding_backend == "http"
    assert config.embedding_base_url_raw == "http://localhost:9000/v1"
    assert config.embedding_base_url == "http://localhost:9000/v1"
    assert config.embedding_api_key == "k"
    assert config.embedding_model == "provider-model"
    assert config.embedding_model_name == "local/model"
