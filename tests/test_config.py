"""Unit tests for ``sct_intake.config`` (env mapping and defaults)."""

from __future__ import annotations

import os

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


def test_dotenv_overrides_preset_env_var(monkeypatch, tmp_path) -> None:
    """The repo .env must win over a stale pre-set OPENAI_API_KEY.

    Regression test: the app used to call ``load_dotenv()`` without
    ``override=True``, so a machine/user-level OPENAI_API_KEY (e.g. a rotated
    key lingering in the environment) shadowed the valid key in ``.env`` and
    every live API call failed with HTTP 401 while ``integration_test.py``
    (which loads with ``override=True``) kept passing.
    """
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text(
        "OPENAI_API_KEY=sk-from-dotenv\n"
        "OPENAI_BASE_URL=https://dotenv.example/v1\n",
        encoding="utf-8",
    )

    calls: dict[str, bool] = {}
    real_load_dotenv = cfg.load_dotenv

    def _patched_load(dotenv_path=None, **kwargs):
        calls["override"] = kwargs.get("override", False)
        return real_load_dotenv(dotenv_file, **kwargs)

    monkeypatch.setattr(cfg, "_dotenv_loaded", False)
    monkeypatch.setattr(cfg, "load_dotenv", _patched_load)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-stale-env")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://stale.example/v1")

    cfg._load_dotenv_once()

    assert calls["override"] is True
    assert os.environ["OPENAI_API_KEY"] == "sk-from-dotenv"
    assert os.environ["OPENAI_BASE_URL"] == "https://dotenv.example/v1"
    assert cfg.get_config().api_key == "sk-from-dotenv"
