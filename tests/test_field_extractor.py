"""Unit tests for ``field_extractor`` (schema, payloads, parsing, env wiring)."""

from __future__ import annotations

import json
from typing import Any

import pytest
import requests

import field_extractor as fe
from client_upload import NATURE_OF_DISPUTE_CHOICES

# Reusable module-level test builders shipped with the module itself.
SAMPLE_ARGUMENTS = fe._sample_arguments()


def completion(message: dict[str, Any]) -> dict[str, Any]:
    return fe._completion(message)


def tool_message(arguments: str) -> dict[str, Any]:
    return fe._tool_message(arguments)


def no_tool_completion() -> dict[str, Any]:
    return {"choices": [{"message": {"role": "assistant", "content": "hello"}}]}


# --------------------------------------------------------------------------- #
# Tool schema
# --------------------------------------------------------------------------- #


def test_build_tool_schema_shape() -> None:
    schema = fe._build_tool_schema()
    assert schema["type"] == "function"
    function = schema["function"]
    assert function["name"] == fe.TOOL_NAME
    parameters = function["parameters"]
    assert parameters["type"] == "object"
    assert set(parameters["properties"]) == set(fe.EXPECTED_KEYS)
    assert parameters["required"] == list(fe.EXPECTED_KEYS)
    assert parameters["additionalProperties"] is False


def test_build_tool_schema_nature_enum_matches_sct_choices() -> None:
    nature = fe._build_tool_schema()["function"]["parameters"]["properties"][
        "nature_of_dispute"
    ]
    assert nature["enum"] == list(NATURE_OF_DISPUTE_CHOICES)
    assert nature["type"] == "string"


def test_prompt_roles_and_content() -> None:
    messages = fe._prompt("hello world")
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "hello world" in messages[1]["content"]


# --------------------------------------------------------------------------- #
# Extra-body helpers
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "{}",
        '{"thinking": {"type": "disabled"}}',
        '{"reasoning_effort": "high"}',
    ],
)
def test_parse_extra_chat_body_accepts(raw: str | None) -> None:
    parsed = fe._parse_extra_chat_body(raw)
    assert isinstance(parsed, dict)


@pytest.mark.parametrize("raw", ["{not json", "[1, 2]", '"str"', "42", ""])
def test_parse_extra_chat_body_rejects_bad_values(raw: str) -> None:
    with pytest.raises(fe.FieldExtractionError):
        fe._parse_extra_chat_body(raw)


def test_merge_extra_chat_body_merges_and_keeps_payload_intact() -> None:
    payload = {"model": "m", "temperature": 0}
    merged = fe._merge_extra_chat_body(payload, {"thinking": {"type": "disabled"}})
    assert merged == {"model": "m", "temperature": 0, "thinking": {"type": "disabled"}}
    assert payload == {"model": "m", "temperature": 0}


def test_merge_extra_chat_body_rejects_reserved_fields() -> None:
    with pytest.raises(fe.FieldExtractionError) as exc:
        fe._merge_extra_chat_body({"model": "m"}, {"model": "x", "tools": []})
    assert "model" in str(exc.value) and "tools" in str(exc.value)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.deepseek.com",
        "https://api.deepseek.com/v1",
        "https://deepseek.com/v1/",
        "https://something.deepseek.example.org:8443/v1",
        "HTTPS://API.DEEPSEEK.COM",
    ],
)
def test_effective_extra_body_disables_thinking_on_deepseek(base_url: str) -> None:
    assert fe._effective_extra_body(base_url, None) == {
        "thinking": {"type": "disabled"}
    }


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.openai.com/v1",
        "https://example.test/v1",
        "http://127.0.0.1:8000/v1",
    ],
)
def test_effective_extra_body_leaves_other_hosts_alone(base_url: str) -> None:
    assert fe._effective_extra_body(base_url, None) == {}
    assert fe._effective_extra_body(base_url, {"foo": "bar"}) == {"foo": "bar"}


def test_effective_extra_body_respects_explicit_thinking() -> None:
    assert fe._effective_extra_body(
        "https://api.deepseek.com",
        {"thinking": {"type": "enabled"}, "seed": 7},
    ) == {"thinking": {"type": "enabled"}, "seed": 7}


# --------------------------------------------------------------------------- #
# _post_chat_completions
# --------------------------------------------------------------------------- #


def test_post_chat_completions_payload_and_url(make_stub) -> None:
    session = make_stub(completion(tool_message(SAMPLE_ARGUMENTS)))
    prompt = fe._prompt("doc")
    tools = [fe._build_tool_schema()]
    body = fe._post_chat_completions(
        session,
        "https://example.test/v1",
        api_key="secret",
        model="m",
        prompt=prompt,
        tools=tools,
        tool_choice=fe.TOOL_NAME,
    )
    call = session.calls[0]
    assert call["url"] == "https://example.test/v1/chat/completions"
    sent = call["json"]
    assert sent["model"] == "m"
    assert sent["messages"] == prompt
    assert sent["tools"] == tools
    assert sent["tool_choice"] == {
        "type": "function",
        "function": {"name": fe.TOOL_NAME},
    }
    assert sent["temperature"] == 0
    assert call["headers"]["Authorization"] == "Bearer secret"
    assert call["timeout"] == fe.REQUEST_TIMEOUT_SECONDS
    assert "choices" in body


def test_post_chat_completions_url_trailing_slash(make_stub) -> None:
    session = make_stub(completion(tool_message(SAMPLE_ARGUMENTS)))
    fe._post_chat_completions(
        session,
        "https://example.test/v1/",
        api_key="",
        model="m",
        prompt=fe._prompt("x"),
        tools=[],
        tool_choice=fe.TOOL_NAME,
    )
    assert session.calls[0]["url"] == "https://example.test/v1/chat/completions"
    assert session.calls[0]["headers"]["Authorization"] == "Bearer "


def test_post_chat_completions_includes_extra_body(make_stub) -> None:
    session = make_stub(completion(tool_message(SAMPLE_ARGUMENTS)))
    fe._post_chat_completions(
        session,
        "https://api.deepseek.com",
        api_key="",
        model="m",
        prompt=fe._prompt("x"),
        tools=[],
        tool_choice=fe.TOOL_NAME,
        extra_body={"thinking": {"type": "disabled"}},
    )
    sent = session.calls[0]["json"]
    assert sent["thinking"] == {"type": "disabled"}
    assert sent["tool_choice"]["function"]["name"] == fe.TOOL_NAME


def test_post_chat_completions_http_error(make_stub) -> None:
    session = make_stub({"error": "boom"}, status_code=429)
    with pytest.raises(fe.FieldExtractionError) as exc:
        fe._post_chat_completions(
            session,
            "https://example.test/v1",
            api_key="",
            model="m",
            prompt=fe._prompt("x"),
            tools=[],
            tool_choice=fe.TOOL_NAME,
        )
    assert "HTTP 429" in str(exc.value)


def test_post_chat_completions_invalid_json_body(make_stub) -> None:
    session = make_stub("irrelevant", json_error=True)
    with pytest.raises(fe.FieldExtractionError):
        fe._post_chat_completions(
            session,
            "https://example.test/v1",
            api_key="",
            model="m",
            prompt=fe._prompt("x"),
            tools=[],
            tool_choice=fe.TOOL_NAME,
        )


def test_post_chat_completions_transport_error(make_stub) -> None:
    session = make_stub(error=requests.ConnectionError("network down"))
    with pytest.raises(fe.FieldExtractionError):
        fe._post_chat_completions(
            session,
            "https://example.test/v1",
            api_key="",
            model="m",
            prompt=fe._prompt("x"),
            tools=[],
            tool_choice=fe.TOOL_NAME,
        )


# --------------------------------------------------------------------------- #
# _parse_tool_result
# --------------------------------------------------------------------------- #


def test_parse_tool_result_happy_path() -> None:
    expected = json.loads(SAMPLE_ARGUMENTS)
    result = fe._parse_tool_result(completion(tool_message(SAMPLE_ARGUMENTS)))
    assert result == expected
    assert set(result) == set(fe.EXPECTED_KEYS)


def test_parse_tool_result_missing_key_becomes_empty() -> None:
    arguments = json.loads(SAMPLE_ARGUMENTS)
    del arguments["contract_date"]
    result = fe._parse_tool_result(completion(tool_message(json.dumps(arguments))))
    assert result["contract_date"] == ""


def test_parse_tool_result_null_value_becomes_empty() -> None:
    arguments = json.loads(SAMPLE_ARGUMENTS)
    arguments["contract_date"] = None
    result = fe._parse_tool_result(completion(tool_message(json.dumps(arguments))))
    assert result["contract_date"] == ""


def test_parse_tool_result_empty_nature_allowed() -> None:
    arguments = json.loads(SAMPLE_ARGUMENTS)
    arguments["nature_of_dispute"] = ""
    result = fe._parse_tool_result(completion(tool_message(json.dumps(arguments))))
    assert result["nature_of_dispute"] == ""


@pytest.mark.parametrize("bad", ["Breach of contract", "lease", "Contract", "  "])
def test_parse_tool_result_rejects_non_choice_nature(bad: str) -> None:
    arguments = json.loads(SAMPLE_ARGUMENTS)
    arguments["nature_of_dispute"] = bad
    with pytest.raises(ValueError) as exc:
        fe._parse_tool_result(completion(tool_message(json.dumps(arguments))))
    assert "nature_of_dispute" in str(exc.value)
    assert "Contract for sale of goods" in str(exc.value)


def test_parse_tool_result_rejects_non_object_arguments() -> None:
    with pytest.raises(TypeError):
        fe._parse_tool_result(completion(tool_message("[1, 2]")))


def test_parse_tool_result_rejects_non_string_value() -> None:
    arguments = json.loads(SAMPLE_ARGUMENTS)
    arguments["claim_amount"] = 2500.00
    with pytest.raises(TypeError):
        fe._parse_tool_result(completion(tool_message(json.dumps(arguments))))


def test_parse_tool_result_malformed_json_arguments() -> None:
    with pytest.raises(fe.FieldExtractionError):
        fe._parse_tool_result(completion(tool_message("{not json")))


def test_parse_tool_result_arguments_not_string() -> None:
    message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": fe.TOOL_NAME, "arguments": 123},
            }
        ],
    }
    with pytest.raises(fe.FieldExtractionError):
        fe._parse_tool_result(completion(message))


def test_parse_tool_result_wrong_tool_name() -> None:
    message = fe._tool_message(SAMPLE_ARGUMENTS)
    message["tool_calls"][0]["function"]["name"] = "other_tool"
    with pytest.raises(fe.FieldExtractionError):
        fe._parse_tool_result(completion(message))


def test_parse_tool_result_missing_function_key() -> None:
    message = fe._tool_message(SAMPLE_ARGUMENTS)
    del message["tool_calls"][0]["function"]
    with pytest.raises(fe.FieldExtractionError):
        fe._parse_tool_result(completion(message))


def test_parse_tool_result_function_not_object() -> None:
    message = fe._tool_message(SAMPLE_ARGUMENTS)
    message["tool_calls"][0]["function"] = "nope"
    with pytest.raises(fe.FieldExtractionError):
        fe._parse_tool_result(completion(message))


def test_parse_tool_result_tool_call_not_object() -> None:
    message = fe._tool_message(SAMPLE_ARGUMENTS)
    message["tool_calls"][0] = "nope"
    with pytest.raises(fe.FieldExtractionError):
        fe._parse_tool_result(completion(message))


@pytest.mark.parametrize(
    "tool_calls", [[], None, "not-a-list", [{"id": "x"}]]
)
def test_parse_tool_result_missing_or_bad_tool_calls(tool_calls: Any) -> None:
    message = {"role": "assistant", "content": None, "tool_calls": tool_calls}
    with pytest.raises(fe.FieldExtractionError):
        fe._parse_tool_result(completion(message))


def test_parse_tool_result_no_message_choice() -> None:
    with pytest.raises(fe.FieldExtractionError):
        fe._parse_tool_result({"choices": []})


def test_parse_tool_result_no_choices_key() -> None:
    with pytest.raises(fe.FieldExtractionError):
        fe._parse_tool_result({})


# --------------------------------------------------------------------------- #
# openai_compatible_extract
# --------------------------------------------------------------------------- #


def test_openai_compatible_extract_rejects_blank_text(make_stub) -> None:
    with pytest.raises(ValueError):
        fe.openai_compatible_extract(
            "   ",
            base_url="https://example.test/v1",
            api_key="k",
            model="m",
            session=requests.Session(),
        )


def test_openai_compatible_extract_happy_path(make_stub) -> None:
    session = make_stub(completion(tool_message(SAMPLE_ARGUMENTS)))
    result = fe.openai_compatible_extract(
        "Alicia Tan claims $2500.00",
        base_url="https://example.test/v1",
        api_key="k",
        model="m",
        session=session,
    )
    assert result["claimant_name"] == "John Doe"
    assert session.calls[0]["url"] == "https://example.test/v1/chat/completions"


def test_openai_compatible_extract_deepseek_auto_disables_thinking(make_stub) -> None:
    session = make_stub(completion(tool_message(SAMPLE_ARGUMENTS)))
    fe.openai_compatible_extract(
        "doc",
        base_url="https://api.deepseek.com",
        api_key="k",
        model="m",
        session=session,
    )
    assert session.calls[0]["json"]["thinking"] == {"type": "disabled"}


def test_openai_compatible_extract_explicit_extra_body(make_stub) -> None:
    session = make_stub(completion(tool_message(SAMPLE_ARGUMENTS)))
    fe.openai_compatible_extract(
        "doc",
        base_url="https://api.deepseek.com",
        api_key="k",
        model="m",
        session=session,
        extra_body={"thinking": {"type": "enabled"}},
    )
    assert session.calls[0]["json"]["thinking"] == {"type": "enabled"}


# --------------------------------------------------------------------------- #
# extract_fields (env wiring, no network)
# --------------------------------------------------------------------------- #


def test_extract_fields_requires_api_key(monkeypatch) -> None:
    monkeypatch.setattr(fe, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(fe.FieldExtractionError):
        fe.extract_fields("doc")


def test_extract_fields_wires_env_to_extract(monkeypatch) -> None:
    monkeypatch.setattr(fe, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("OPENAI_MODEL", "model-x")
    monkeypatch.setenv("OPENAI_CHAT_EXTRA_BODY", '{"seed": 42}')

    captured: list[dict[str, Any]] = []

    def fake_extract(text: str, **kwargs: Any) -> dict[str, str]:
        captured.append({"text": text, **kwargs})
        return {}

    monkeypatch.setattr(fe, "openai_compatible_extract", fake_extract)
    fe.extract_fields("doc")
    assert captured[0]["text"] == "doc"
    assert captured[0]["base_url"] == "https://example.test/v1"
    assert captured[0]["model"] == "model-x"
    assert captured[0]["api_key"] == "key"
    assert captured[0]["extra_body"] == {"seed": 42}


def test_extract_fields_env_defaults(monkeypatch) -> None:
    monkeypatch.setattr(fe, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_CHAT_EXTRA_BODY", raising=False)

    captured: list[dict[str, Any]] = []

    def fake_extract(text: str, **kwargs: Any) -> dict[str, str]:
        captured.append(kwargs)
        return {}

    monkeypatch.setattr(fe, "openai_compatible_extract", fake_extract)
    fe.extract_fields("doc")
    assert captured[0]["base_url"] == fe.DEFAULT_BASE_URL
    assert captured[0]["model"] == fe.DEFAULT_MODEL
    assert captured[0]["extra_body"] == {}


def test_extract_fields_rejects_malformed_extra_body_env(monkeypatch) -> None:
    monkeypatch.setattr(fe, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.setenv("OPENAI_CHAT_EXTRA_BODY", "{not json")
    with pytest.raises(fe.FieldExtractionError):
        fe.extract_fields("doc")
