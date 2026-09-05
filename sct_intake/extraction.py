"""OpenAI-compatible tool-call field extraction for SCT claims.

Given uploaded claim text, calls an OpenAI-*compatible* chat endpoint (NOT
necessarily OpenAI itself) and forces ONE tool call that fills the SCT case
fields with a JSON object matching the ``SCTCase._from_mapping`` contract.

Provider quirks are handled without hardcoding in callers:
- DeepSeek ships with thinking mode enabled, which rejects a forced
  ``tool_choice``; requests to DeepSeek hosts automatically send
  ``{"thinking": {"type": "disabled"}}`` unless the caller already chose a
  ``thinking`` mode.
- Any other OpenAI-compatible request-body knob can ride along via the
  ``OPENAI_CHAT_EXTRA_BODY`` env var (or the ``extra_body`` parameter), except
  reserved fields the module owns (``model``/``messages``/``tools``/
  ``tool_choice``/``temperature``).

No OpenAI SDK, no chunking/embeddings (see :mod:`retrieval`/:mod:`embedders`).
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

import requests

from .config import get_config
from .domain import NATURE_OF_DISPUTE_CHOICES
from .errors import ExtractionError

#: Legacy alias kept as a module/public attribute for import compatibility.
FieldExtractionError = ExtractionError

TOOL_NAME = "submit_sct_fields"
REQUEST_TIMEOUT_SECONDS = 60

#: Fields the module owns; OPENAI_CHAT_EXTRA_BODY must never override these.
RESERVED_CHAT_FIELDS = frozenset(
    {"model", "messages", "tools", "tool_choice", "temperature"}
)

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
    SCT choices so any other value is structurally rejected at the schema
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
# Request-body helpers
# --------------------------------------------------------------------------- #


def _parse_extra_chat_body(raw: str | None) -> dict[str, Any]:
    """Parse the ``OPENAI_CHAT_EXTRA_BODY`` env value into a JSON object."""
    if raw is None:
        return {}
    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExtractionError(
            f"OPENAI_CHAT_EXTRA_BODY was not valid JSON: {raw[:200]!r}"
        ) from exc
    if not isinstance(body, dict):
        raise ExtractionError(
            "OPENAI_CHAT_EXTRA_BODY must be a JSON object, got "
            f"{type(body).__name__}."
        )
    return body


def _merge_extra_chat_body(
    payload: dict[str, Any], extra: dict[str, Any]
) -> dict[str, Any]:
    """Merge provider-specific extra body fields; reserved fields are protected."""
    collisions = sorted(RESERVED_CHAT_FIELDS & extra.keys())
    if collisions:
        raise ExtractionError(
            "OPENAI_CHAT_EXTRA_BODY may not override reserved fields: "
            + ", ".join(collisions)
            + "."
        )
    merged = dict(payload)
    merged.update(extra)
    return merged


def _effective_extra_body(
    base_url: str, configured: dict[str, Any] | None
) -> dict[str, Any]:
    """Provider defaults on top of any explicitly configured extra body."""
    extra = dict(configured) if configured else {}
    host = urlparse(base_url).netloc.lower()
    if "deepseek" in host and "thinking" not in extra:
        extra["thinking"] = {"type": "disabled"}
    return extra


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
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST a tool-forced chat-completions request and return the JSON body."""
    url = base_url.rstrip("/") + "/chat/completions"
    base_payload = {
        "model": model,
        "messages": prompt,
        "tools": tools,
        "tool_choice": {"type": "function", "function": {"name": tool_choice}},
        "temperature": 0,
    }
    payload = _merge_extra_chat_body(base_payload, extra_body or {})
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        response = session.post(
            url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS
        )
    except requests.RequestException as exc:
        raise ExtractionError(
            f"chat-completions transport error for {url}: {exc}"
        ) from exc
    if response.status_code != 200:
        raise ExtractionError(
            f"chat-completions returned HTTP {response.status_code} from {url}: "
            f"{response.text[:500]}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise ExtractionError(
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
        raise ExtractionError(
            "response contained no choices[0].message; expected a chat "
            "completion with exactly one forced tool call."
        ) from exc

    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list) or not tool_calls:
        raise ExtractionError(
            f"response contained no tool call; expected exactly one forced "
            f"{TOOL_NAME!r} call."
        )
    tool_call = tool_calls[0]
    if not isinstance(tool_call, dict):
        raise ExtractionError("response tool_calls[0] was not an object.")

    function = tool_call.get("function", {})
    if not isinstance(function, dict):
        raise ExtractionError("tool call carried no function object.")
    name = function.get("name")
    if name is not None and name != TOOL_NAME:
        raise ExtractionError(
            f"expected forced tool call {TOOL_NAME!r}, got {name!r}."
        )
    arguments_raw = function.get("arguments")
    if not isinstance(arguments_raw, str):
        raise ExtractionError(
            "tool-call arguments were missing or not a JSON string."
        )

    try:
        parsed = json.loads(arguments_raw)
    except json.JSONDecodeError as exc:
        raise ExtractionError(
            f"tool-call arguments were not valid JSON: {arguments_raw[:200]!r}"
        ) from exc

    # ---- Schema-mismatch fallback: the JSON object shape must hold ------- #
    if not isinstance(parsed, dict):
        raise TypeError(
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
            raise TypeError(
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
    extra_body: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Run one forced-tool extraction against an OpenAI-compatible endpoint.

    ``session`` is an optional injected ``requests.Session`` (tests substitute
    a stub; shared transports may be injected too). ``extra_body`` optionally
    adds provider-specific request-body knobs. DeepSeek hosts automatically
    disable thinking unless ``extra_body`` already sets a ``thinking`` mode.
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
        extra_body=_effective_extra_body(base_url, extra_body),
    )
    return _parse_tool_result(response_json)


def extract_fields(text: str) -> dict[str, str]:
    """Canonical ``FieldExtractor`` entry point, configured from the env.

    Raises :class:`ExtractionError` at call time (not import time) if
    ``OPENAI_API_KEY`` is unset.
    """
    config = get_config()
    if not config.api_key:
        raise ExtractionError(
            "OPENAI_API_KEY is not set; set OPENAI_API_KEY (and optionally "
            "OPENAI_BASE_URL / OPENAI_MODEL) in the environment or a .env file."
        )
    extra_body = _parse_extra_chat_body(config.chat_extra_body)
    return openai_compatible_extract(
        text,
        base_url=config.base_url,
        api_key=config.api_key,
        model=config.model,
        extra_body=extra_body,
    )
