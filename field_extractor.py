"""
``field_extractor`` : a thin wrapper around an OpenAI-compatible chat endpoint.

Given an uploaded claim narrative (plain text), this module calls an
OpenAI-*compatible* server (NOT necessarily OpenAI itself) and forces ONE tool
call that fills the SCT case fields with a JSON object.

Returned dict contract (``dict[str, str]``, consumed by
``client_upload.SCTCase._from_mapping``): ``claimant_name``,
``claimant_nric``, ``respondent_name``, ``nature_of_dispute`` (restricted to
the four SCT choices), ``claim_amount``, ``date_of_cause_of_action``,
``contract_date``, ``particulars``.

Deliberately NOT included: OpenAI SDK usage (works with any compatible
endpoint), chunking/vector embeddings (separate future module), or knowledge
of ``SCTCase`` internals.

Env / .env configuration:
    OPENAI_BASE_URL   (default https://api.openai.com/v1)
    OPENAI_API_KEY    (required at call time)
    OPENAI_MODEL      (default gpt-4o-mini)

Running ``python field_extractor.py`` runs a stub-session self-test only (no
network).  It never makes a live call unless a caller invokes ``extract_fields``
/ ``openai_compatible_extract`` with an API key.

Usage:
    case = SCTCase.from_upload_file(extractor=field_extractor.extract_fields)
    case = SCTCase.from_text(upload_body, extractor=extractor.extract_fields)
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests
from dotenv import load_dotenv

try:
    from client_upload import NATURE_OF_DISPUTE_CHOICES
except ImportError:  # pragma: no cover - standalone import fallback
    NATURE_OF_DISPUTE_CHOICES = (
        "Contract for sale of goods",
        "Contract for provision of services",
        "Damage to property",
        "Lease not exceeding two years",
    )

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
TOOL_NAME = "submit_sct_fields"
REQUEST_TIMEOUT_SECONDS = 60

EXPECTED_KEYS: tuple[str, ...] = (
    "claimant_name",
    "claimant_nric",
    "respondent_name",
    "nature_of_dispute",
    "claim_amount",
    "date_of_cause_of_action",
    "contract_date",
    "particulars",
)


class FieldExtractionError(RuntimeError):
    """Raised when the OpenAI-compatible call cannot produce a valid result."""


# --------------------------------------------------------------------------- #
# Prompt construction
# --------------------------------------------------------------------------- #

_SYSTEM_PROMPT = (
    "You are an intake assistant for Singapore's Small Claims Tribunals (SCT). "
    "Given an uploaded claim document, read it and extract the fields described "
    f"by the {TOOL_NAME} function. Rules: "
    f"(1) respond ONLY by calling that single function with a JSON object - "
    "never add prose or commentary; "
    "(2) fill each field with the best-supported value found in the document; "
    "(3) use an empty string ('') for any field the document does not state; "
    "(4) nature_of_dispute must be exactly one of the four listed SCT choices; "
    "(5) dates are ISO 8601 such as '2026-09-02'; "
    "(6) amounts are plain decimal strings such as '10000.00'."
)


def _prompt(text: str) -> list[dict[str, str]]:
    """Return the pinned system + user messages for an uploaded document."""
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"Uploaded claim document:\n\n{text}"},
    ]


# --------------------------------------------------------------------------- #
# Tool-call schema (the enforcement seam for the dict[str, str] contract)
# --------------------------------------------------------------------------- #


def _build_tool_schema() -> dict[str, Any]:
    """OpenAI tool JSON schema for ONE forced ``submit_sct_fields`` call.

    ``nature_of_dispute`` is declared as a JSON-schema ``enum`` over the four
    SCT choices, so any other value is structurally rejected at the schema
    level rather than validated afterwards.  All keys are ``required``.
    """
    return {
        "type": "function",
        "function": {
            "name": TOOL_NAME,
            "description": (
                "Submit the SCT intake fields extracted from the uploaded "
                "claim document as a single JSON object."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "claimant_name": {
                        "type": "string",
                        "description": (
                            "Full name of the claimant (party bringing the claim)."
                        ),
                    },
                    "claimant_nric": {
                        "type": "string",
                        "description": (
                            "Claimant's Singapore NRIC/FIN, e.g. 'G2677383R'."
                        ),
                    },
                    "respondent_name": {
                        "type": "string",
                        "description": (
                            "Full name of the respondent (party being claimed against)."
                        ),
                    },
                    "nature_of_dispute": {
                        "type": "string",
                        "enum": list(NATURE_OF_DISPUTE_CHOICES),
                        "description": (
                            "Exactly one of the four SCT statutory categories "
                            "that best describes the dispute."
                        ),
                    },
                    "claim_amount": {
                        "type": "string",
                        "description": (
                            "Total amount claimed, plain decimal string, e.g. "
                            "'10000.00'; a leading '$' and thousand separators "
                            "are tolerated."
                        ),
                    },
                    "date_of_cause_of_action": {
                        "type": "string",
                        "description": (
                            "Date the cause of action arose, ISO 8601, e.g. "
                            "'2026-09-02'."
                        ),
                    },
                    "contract_date": {
                        "type": "string",
                        "description": (
                            "Date the contract was made, ISO 8601, or '' when "
                            "the document does not state one."
                        ),
                    },
                    "particulars": {
                        "type": "string",
                        "description": (
                            "Concise narrative of the claim's particulars as "
                            "stated in the document."
                        ),
                    },
                },
                "required": list(EXPECTED_KEYS),
                "additionalProperties": False,
            },
        },
    }


# --------------------------------------------------------------------------- #
# HTTP layer
# --------------------------------------------------------------------------- #


def _post_chat_completions(
    session: Any,
    base_url: str,
    api_key: str,
    model: str,
    prompt: list[dict[str, str]],
    tools: list[dict[str, Any]],
    tool_choice: str,
) -> dict[str, Any]:
    """POST a tool-forced chat-completions request and return the JSON body."""
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": prompt,
        "tools": tools,
        "tool_choice": {"type": "function", "function": {"name": tool_choice}},
        "temperature": 0,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        response = session.post(
            url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS
        )
    except requests.RequestException as exc:
        raise FieldExtractionError(
            f"chat-completions transport error for {url}: {exc}"
        ) from exc
    if response.status_code != 200:
        raise FieldExtractionError(
            f"chat-completions returned HTTP {response.status_code} from {url}: "
            f"{response.text[:500]}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise FieldExtractionError(
            "chat-completions response was not valid JSON"
        ) from exc


# --------------------------------------------------------------------------- #
# Response parsing
# --------------------------------------------------------------------------- #


def _parse_tool_result(response_json: dict[str, Any]) -> dict[str, str]:
    """Extract and sanity-check the forced tool call's JSON arguments."""
    try:
        message = response_json["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise FieldExtractionError(
            "response contained no choices[0].message; expected a chat "
            "completion with exactly one forced tool call."
        ) from exc

    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list) or not tool_calls:
        raise FieldExtractionError(
            f"response contained no tool call; expected exactly one forced "
            f"{TOOL_NAME!r} call."
        )
    tool_call = tool_calls[0]
    if not isinstance(tool_call, dict):
        raise FieldExtractionError("response tool_calls[0] was not an object.")

    function = tool_call.get("function", {})
    if not isinstance(function, dict):
        raise FieldExtractionError("tool call carried no function object.")
    name = function.get("name")
    if name is not None and name != TOOL_NAME:
        raise FieldExtractionError(
            f"expected forced tool call {TOOL_NAME!r}, got {name!r}."
        )
    arguments_raw = function.get("arguments")
    if not isinstance(arguments_raw, str):
        raise FieldExtractionError(
            "tool-call arguments were missing or not a JSON string."
        )

    try:
        parsed = json.loads(arguments_raw)
    except json.JSONDecodeError as exc:
        raise FieldExtractionError(
            f"tool-call arguments were not valid JSON: {arguments_raw[:200]!r}"
        ) from exc

    # ---- Schema-mismatch fallback: the JSON object shape must hold ------- #
    if not isinstance(parsed, dict):
        raise ValueError(
            "model returned JSON "
            f"{type(parsed).__name__} arguments; contract requires a JSON object."
        )

    result: dict[str, str] = {}
    for key in EXPECTED_KEYS:
        value = parsed.get(key)
        if value is None:
            result[key] = ""
            continue
        if not isinstance(value, str):
            raise ValueError(
                f"model returned non-string for {key!r}: {value!r} "
                "(contract requires dict[str, str])."
            )
        result[key] = value

    # ---- Closed-choice fallback: empty means absent; anything non-empty
    # ---- must be one of the four SCT choices (schema mismatch fallback).
    nature = result["nature_of_dispute"]
    if nature and nature not in NATURE_OF_DISPUTE_CHOICES:
        raise ValueError(
            f"nature_of_dispute: {nature!r} is not one of the SCT choices: "
            f"{', '.join(NATURE_OF_DISPUTE_CHOICES)}."
        )
    return result


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def openai_compatible_extract(
    text: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    session: requests.Session | None = None,
) -> dict[str, str]:
    """Run one forced-tool extraction against an OpenAI-compatible endpoint.

    ``session`` is an optional injected ``requests.Session`` (unit tests may
    substitute a stub; future chunking/embedding code can share one transport).
    """
    if not text or not text.strip():
        raise ValueError("upload text contained no non-blank content")

    http = session if session is not None else requests.Session()
    response_json = _post_chat_completions(
        session=http,
        base_url=base_url,
        api_key=api_key,
        model=model,
        prompt=_prompt(text),
        tools=[_build_tool_schema()],
        tool_choice=TOOL_NAME,
    )
    return _parse_tool_result(response_json)


def extract_fields(text: str) -> dict[str, str]:
    """Canonical ``FieldExtractor`` entry point, configured from the env.

    Raises :class:`FieldExtractionError` at call time (not import time) if
    ``OPENAI_API_KEY`` is unset.
    """
    load_dotenv()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise FieldExtractionError(
            "OPENAI_API_KEY is not set; set OPENAI_API_KEY (and optionally "
            "OPENAI_BASE_URL / OPENAI_MODEL) in the environment or a .env file."
        )
    base_url = os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)
    model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
    return openai_compatible_extract(
        text, base_url=base_url, api_key=api_key, model=model
    )


# --------------------------------------------------------------------------- #
# CLI self-test (stub session, never a network call)
# --------------------------------------------------------------------------- #

SAMPLE_DOCUMENT = """\
I, John Doe (NRIC G2677383R), sold my sofa to Jane Ong for $10,000.00 on
2026-09-02 but she never paid. There was no written contract.
"""


def _sample_arguments() -> str:
    return json.dumps(
        {
            "claimant_name": "John Doe",
            "claimant_nric": "G2677383R",
            "respondent_name": "Jane Ong",
            "nature_of_dispute": "Contract for sale of goods",
            "claim_amount": "$10,000.00",
            "date_of_cause_of_action": "2026-09-02",
            "contract_date": "",
            "particulars": "Sale of a sofa to Jane Ong, unpaid despite demand.",
        }
    )


class _StubResponse:
    """Minimal stand-in for ``requests.Response`` (status/text/json only)."""

    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self.status_code = status_code
        self.text = json.dumps(payload)
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _StubSession:
    """Duck-typed ``requests.Session`` that records the POST and answers canned."""

    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self._status_code = status_code
        self.request: dict[str, Any] = {}

    def post(self, url: str, **kwargs: Any) -> _StubResponse:
        self.request = {"url": url, **kwargs}
        return _StubResponse(self._payload, self._status_code)


def _completion(message: dict[str, Any]) -> dict[str, Any]:
    """A canned OpenAI-compatible chat completion with one assistant message."""
    return {
        "id": "chatcmpl-stub",
        "object": "chat.completion",
        "model": "stub-model",
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls",
            }
        ],
    }


def _tool_message(arguments: str) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_stub",
                "type": "function",
                "function": {"name": TOOL_NAME, "arguments": arguments},
            }
        ],
    }


def _expect_raises(exc_type: type[Exception], fn: Any, label: str) -> None:
    try:
        fn()
    except exc_type as exc:
        print(f"  ok ({label}): raised {exc_type.__name__}: {exc}")
    else:
        raise AssertionError(f"{label}: expected {exc_type.__name__} to be raised")


def _run_smoke_test() -> None:
    base_url = "https://example.test/v1"
    api_key = "stub-key"

    def extract(payload: dict[str, Any], status_code: int = 200) -> _StubSession:
        session = _StubSession(payload, status_code)
        openai_compatible_extract(
            SAMPLE_DOCUMENT,
            base_url=base_url,
            api_key=api_key,
            model="stub-model",
            session=session,
        )
        return session

    # ---- Happy path: forced tool call -> exact dict[str, str] ----------- #
    session = extract(_completion(_tool_message(_sample_arguments())))
    assert session.request["url"] == base_url + "/chat/completions"
    body = session.request["json"]
    assert body["tool_choice"] == {
        "type": "function",
        "function": {"name": TOOL_NAME},
    }
    assert body["messages"][0]["role"] == "system"

    result = _parse_tool_result(_completion(_tool_message(_sample_arguments())))
    assert set(result) == set(EXPECTED_KEYS)
    assert result["claimant_name"] == "John Doe"
    assert result["nature_of_dispute"] == "Contract for sale of goods"
    assert result["claim_amount"] == "$10,000.00"
    assert result["contract_date"] == ""
    print("  ok (happy path): parsed forced tool call ->")
    for key, value in result.items():
        print(f"      {key}: {value!r}")

    # ---- Empty nature_of_dispute counts as absent ('' flows to None) ---- #
    empty_nature = json.loads(_sample_arguments())
    empty_nature["nature_of_dispute"] = ""
    parsed = _parse_tool_result(_completion(_tool_message(json.dumps(empty_nature))))
    assert parsed["nature_of_dispute"] == ""
    print("  ok (empty enum): nature_of_dispute '' passes through as absent")

    # ---- Schema-mismatch fallbacks raise --------------------------------- #
    bad_nature = json.loads(_sample_arguments())
    bad_nature["nature_of_dispute"] = "Breach of contract"
    _expect_raises(
        ValueError,
        lambda: _parse_tool_result(
            _completion(_tool_message(json.dumps(bad_nature)))
        ),
        "out-of-enum nature_of_dispute",
    )
    _expect_raises(
        ValueError,
        lambda: _parse_tool_result(_completion(_tool_message("[1, 2]"))),
        "non-object arguments",
    )
    _expect_raises(
        FieldExtractionError,
        lambda: _parse_tool_result(_completion(_tool_message("{not json"))),
        "malformed JSON arguments",
    )
    _expect_raises(
        FieldExtractionError,
        lambda: _parse_tool_result(
            _completion({"role": "assistant", "content": "no tool call here"})
        ),
        "missing tool call",
    )
    _expect_raises(
        FieldExtractionError,
        lambda: extract(
            {"error": {"message": "bad schema"}}, status_code=400
        ),
        "HTTP 400",
    )


def main() -> int:
    print("field_extractor self-test (stub session, no network):")
    _run_smoke_test()
    load_dotenv()
    if not os.environ.get("OPENAI_API_KEY"):
        print()
        print("No OPENAI_API_KEY is configured; no live call was attempted.")
        print('set "OPENAI_BASE_URL" (default https://api.openai.com/v1),')
        print('"OPENAI_API_KEY", and "OPENAI_MODEL" (default gpt-4o-mini) to')
        print("enable live extraction.")
    else:
        print()
        print("OPENAI_API_KEY is set; live usage example:")
        print("  case = SCTCase.from_upload_file(extractor=extract_fields)")
        print("  print(case.summary())")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
