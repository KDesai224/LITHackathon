"""Unit tests for the model-driven agentic extraction loop.

All chat/embedding calls are stubbed: the ``StubSession`` answers scripted
``completion()`` payloads, and ``KeywordHashEmbedder`` ranks chunks offline.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import requests

from sct_intake.errors import EmbeddingError, ExtractionError
from sct_intake.extraction import (
    SEARCH_TOOL_NAME,
    TOOL_NAME,
    openai_compatible_extract_agentic,
)
from tests.helpers import KeywordHashEmbedder, completion, sample_arguments

BIG_DOC = (
    "John Doe (NRIC G2677383R) sold his sofa to Jane Ong for $10,000.00. "
    "Payment was due on 2026-09-02 after delivery but Jane Ong has not paid. "
) * 40  # several chunks > max_chars below, forcing the search-loop path


def _search_call(query: str) -> dict[str, Any]:
    return {
        "id": "call_search",
        "type": "function",
        "function": {
            "name": SEARCH_TOOL_NAME,
            "arguments": json.dumps({"query": query}),
        },
    }


def _submit_call(arguments: str = sample_arguments()) -> dict[str, Any]:
    return {
        "id": "call_submit",
        "type": "function",
        "function": {"name": TOOL_NAME, "arguments": arguments},
    }


def _submit_completion(arguments: str = sample_arguments()) -> dict[str, Any]:
    return completion(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [_submit_call(arguments)],
        }
    )


def _search_completion(query: str) -> dict[str, Any]:
    return completion(
        {"role": "assistant", "content": None, "tool_calls": [_search_call(query)]}
    )


class _AlwaysSearchSession:
    """Every chat turn asks for another search (used for the cap test)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> Any:
        self.calls.append({"url": url, **kwargs})
        payload = _search_completion("more facts please")
        return _StubResponse(payload)

    @property
    def payload_count(self) -> int:
        return len(self.calls)


class _StubResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self.status_code = status_code
        self.text = json.dumps(payload)
        self._payload = payload

    def json(self) -> Any:
        return self._payload


# --------------------------------------------------------------------------- #
# Fast path (corpus fits the budget)
# --------------------------------------------------------------------------- #


def test_fast_path_forces_single_submit_without_search(make_stub) -> None:
    session = make_stub([_submit_completion()])
    result = openai_compatible_extract_agentic(
        ["Jane owes John $100 for a sofa that was never delivered."],
        base_url="https://example.test/v1",
        api_key="k",
        model="m",
        session=session,
        max_chars=10_000,
    )
    assert result["claimant_name"] == "John Doe"
    assert result["respondent_name"] == "Jane Ong"
    assert len(session.calls) == 1
    body = session.calls[0]["json"]
    assert body["tool_choice"] == {
        "type": "function",
        "function": {"name": TOOL_NAME},
    }
    assert body["tools"][0]["function"]["name"] == TOOL_NAME


def test_fast_path_rejects_no_tool_call(make_stub) -> None:
    session = make_stub(
        [completion({"role": "assistant", "content": "I am not sure"})]
    )
    with pytest.raises(ExtractionError):
        openai_compatible_extract_agentic(
            ["a short document"],
            base_url="https://example.test/v1",
            api_key="k",
            model="m",
            session=session,
            max_chars=10_000,
        )


# --------------------------------------------------------------------------- #
# Oversized path (search-loop engaged)
# --------------------------------------------------------------------------- #


def test_agent_loop_searches_then_submits(make_stub) -> None:
    rounds: list[int] = []

    def _on_search() -> None:
        rounds.append(1)

    session = make_stub(
        [
            _search_completion("who is the respondent and what is the amount"),
            _submit_completion(),
        ]
    )
    result = openai_compatible_extract_agentic(
        [BIG_DOC],
        base_url="https://example.test/v1",
        api_key="k",
        model="m",
        embedder=KeywordHashEmbedder(),
        session=session,
        max_chars=400,
        max_searches=4,
        on_search=_on_search,
    )
    assert result["claimant_name"] == "John Doe"
    assert result["respondent_name"] == "Jane Ong"
    assert len(rounds) == 1
    assert len(session.calls) == 2

    first = session.calls[0]["json"]
    assert "tool_choice" not in first
    tool_names = [tool["function"]["name"] for tool in first["tools"]]
    assert tool_names == [SEARCH_TOOL_NAME, TOOL_NAME]

    second = first = session.calls[1]["json"]
    roles = [message["role"] for message in second["messages"]]
    assert "tool" in roles
    tool_message = next(
        message for message in second["messages"] if message["role"] == "tool"
    )
    hits = json.loads(tool_message["content"])
    assert isinstance(hits, list)
    assert hits and "text" in hits[0]


def test_oversized_model_may_submit_without_searching(make_stub) -> None:
    session = make_stub([_submit_completion()])
    result = openai_compatible_extract_agentic(
        [BIG_DOC],
        base_url="https://example.test/v1",
        api_key="k",
        model="m",
        embedder=KeywordHashEmbedder(),
        session=session,
        max_chars=400,
        max_searches=4,
    )
    assert result["respondent_name"] == "Jane Ong"
    assert len(session.calls) == 1


def test_oversized_requires_embedder(make_stub) -> None:
    with pytest.raises(EmbeddingError):
        openai_compatible_extract_agentic(
            [BIG_DOC],
            base_url="https://example.test/v1",
            api_key="k",
            model="m",
            embedder=None,
            session=make_stub(),
            max_chars=400,
        )


def test_agent_loop_caps_searches() -> None:
    session: Any = _AlwaysSearchSession()
    with pytest.raises(ExtractionError, match="did not terminate"):
        openai_compatible_extract_agentic(
            [BIG_DOC],
            base_url="https://example.test/v1",
            api_key="k",
            model="m",
            embedder=KeywordHashEmbedder(),
            session=session,
            max_chars=400,
            max_searches=2,
        )
    # 2 searches allowed + 4 grace turns, then we give up.
    assert session.payload_count == 6


def test_agent_loop_rejects_non_tool_reply(make_stub) -> None:
    session = make_stub(
        [completion({"role": "assistant", "content": "I cannot decide"})]
    )
    with pytest.raises(ExtractionError, match="no tool call"):
        openai_compatible_extract_agentic(
            [BIG_DOC],
            base_url="https://example.test/v1",
            api_key="k",
            model="m",
            embedder=KeywordHashEmbedder(),
            session=session,
            max_chars=400,
        )


def test_agent_loop_transport_error_retries_then_raises(make_stub) -> None:
    session = make_stub(
        error=requests.ConnectionError("connection refused")
    )
    with pytest.raises(ExtractionError, match="transport error"):
        openai_compatible_extract_agentic(
            [BIG_DOC],
            base_url="https://example.test/v1",
            api_key="k",
            model="m",
            embedder=KeywordHashEmbedder(),
            session=session,
            max_chars=400,
        )
    assert len(session.calls) == 2  # one retry, then surfacing the error
