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
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import requests

from .config import get_config
from .domain import NATURE_OF_DISPUTE_CHOICES
from .errors import EmbeddingError, ExtractionError
from .retrieval import MAX_CONTEXT_CHARS, DocumentIndex

if TYPE_CHECKING:
    from .embedders import EmbeddingModel

#: Legacy alias kept as a module/public attribute for import compatibility.
FieldExtractionError = ExtractionError

TOOL_NAME = "submit_sct_fields"
SEARCH_TOOL_NAME = "search_documents"
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
    prompt: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    tool_choice: str | None = None,
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST a chat-completions request and return the JSON body.

    When ``tool_choice`` names a function the call is forced to that tool
    (today's single-shot contract); when it is ``None`` the model may choose
    any of ``tools`` on each turn (the agentic search loop).
    """
    url = base_url.rstrip("/") + "/chat/completions"
    base_payload: dict[str, Any] = {
        "model": model,
        "messages": prompt,
        "tools": tools,
        "temperature": 0,
    }
    if tool_choice is not None:
        base_payload["tool_choice"] = {
            "type": "function",
            "function": {"name": tool_choice},
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


# --------------------------------------------------------------------------- #
# Agentic retrieval loop (model-driven search over an oversized corpus)
# --------------------------------------------------------------------------- #

_AGENT_SYSTEM_PROMPT = (
    "You are an intake assistant for Singapore's Small Claims Tribunals (SCT). "
    "You are reading uploaded claim documents and must fill the SCT case fields "
    "defined by the submit_sct_fields function. Rules: "
    "(1) you may call search_documents(query) to retrieve relevant passages you "
    "have not been shown yet; use it whenever a required field is missing or "
    "the text you have is not enough; "
    "(2) never invent facts - fill a field only from text you were shown, and "
    "use an empty string ('') for any field the document does not state; "
    "(3) when you have everything you need (or can find no more), call "
    "submit_sct_fields exactly once with a single JSON object - never add "
    "prose or commentary; "
    "(4) nature_of_dispute must be exactly one of the four listed SCT choices; "
    "(5) dates are ISO 8601 such as '2026-09-02'; "
    "(6) amounts are plain decimal strings such as '10000.00'."
)


def _build_search_tool_schema() -> dict[str, Any]:
    """OpenAI tool JSON schema for the model-driven ``search_documents`` call."""
    return {
        "type": "function",
        "function": {
            "name": SEARCH_TOOL_NAME,
            "description": (
                "Search the uploaded claim documents for passages relevant to a "
                "natural-language query. Returns up to three passages you have "
                "not already been shown. Use this when a required SCT field is "
                "missing or unclear in the text provided so far."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "A natural-language description of the fact you are "
                            "looking for, e.g. \"the respondent's full name\" or "
                            "\"the amount claimed and payment date\"."
                        ),
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    }


def _parse_search_query(function: dict[str, Any]) -> str:
    """Extract and validate the ``query`` string from a search tool call."""
    arguments_raw = function.get("arguments")
    if not isinstance(arguments_raw, str):
        raise ExtractionError(
            f"{SEARCH_TOOL_NAME!r} call carried no JSON arguments."
        )
    try:
        parsed = json.loads(arguments_raw)
    except json.JSONDecodeError as exc:
        raise ExtractionError(
            f"{SEARCH_TOOL_NAME!r} arguments were not valid JSON: "
            f"{arguments_raw[:200]!r}"
        ) from exc
    if not isinstance(parsed, dict):
        raise ExtractionError(
            f"{SEARCH_TOOL_NAME!r} arguments must be a JSON object."
        )
    query = parsed.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ExtractionError(
            f"{SEARCH_TOOL_NAME!r} requires a non-empty string 'query'."
        )
    return query.strip()


def _serialize_search_results(hits: list[Any]) -> str:
    """Serialize ranked search hits into the JSON the model receives."""
    if not hits:
        return (
            "No further passages found. All available document text has "
            "already been shown to you."
        )
    return json.dumps(
        [
            {
                "document": hit.chunk.document_index + 1,
                "score": round(hit.score, 4),
                "text": hit.chunk.text,
            }
            for hit in hits
        ]
    )


def openai_compatible_extract_agentic(
    corpus: Sequence[str],
    *,
    base_url: str,
    api_key: str,
    model: str,
    embedder: EmbeddingModel | None = None,
    session: requests.Session | None = None,
    extra_body: dict[str, Any] | None = None,
    max_chars: int = MAX_CONTEXT_CHARS,
    max_searches: int = 4,
    on_search: Callable[[], None] | None = None,
) -> dict[str, str]:
    """Extract SCT fields from a corpus, letting the model search it in a loop.

    Fast path: a corpus that fits ``max_chars`` is submitted as-is with the
    single forced tool call (identical to :func:`openai_compatible_extract`).

    Oversized path: the corpus is chunked and embedded once into a
    :class:`DocumentIndex`; the model is given the best ``max_chars`` of
    context as a seed and may then call ``search_documents(query)`` up to
    ``max_searches`` times for previously-unseen passages before it must call
    ``submit_sct_fields``. Search tool results never exceed
    ``max_searches * 3`` chunks; worst-case surfaced context is roughly the
    seed (``max_chars``) plus that.

    ``on_search`` (optional) is invoked after each executed search so callers
    can count rounds. ``embedder`` is required only on the oversized path.
    """
    documents = [document for document in corpus if isinstance(document, str) and document.strip()]
    if not documents:
        raise ValueError("at least one non-blank document is required.")
    if max_chars <= 0:
        raise ValueError("max_chars must be positive.")
    if max_searches < 0:
        raise ValueError("max_searches must be non-negative.")

    if sum(len(document) for document in documents) <= max_chars:
        joined = "\n\n---\n\n".join(documents)
        return openai_compatible_extract(
            joined,
            base_url=base_url,
            api_key=api_key,
            model=model,
            session=session,
            extra_body=extra_body,
        )

    if embedder is None:
        raise EmbeddingError(
            "documents exceed the context budget and no embedder was supplied; "
            "pass embedder=default_embedding_model() (or another EmbeddingModel) "
            "so the corpus can be searched semantically."
        )

    index = DocumentIndex(documents, embedder=embedder)
    seed_indices, seed_text = index.seed(max_chars=max_chars)
    seen = set(seed_indices)

    http = session if session is not None else requests.Session()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _AGENT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Uploaded claim documents.\n\n"
                "The passages below are the initial selection most likely to "
                "name the claimant/respondent, the nature of the dispute, the "
                "amount claimed, and the relevant dates. If a required fact is "
                "missing or unclear, call search_documents with a targeted "
                "query to retrieve more.\n\n"
                f"{seed_text}"
            ),
        },
    ]
    tools = [_build_search_tool_schema(), _build_tool_schema()]
    searches = 0

    def _post_once() -> dict[str, Any]:
        last_exc: ExtractionError | None = None
        for attempt in range(2):
            try:
                return _post_chat_completions(
                    session=http,
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    prompt=messages,
                    tools=tools,
                    tool_choice=None,
                    extra_body=_effective_extra_body(base_url, extra_body),
                )
            except ExtractionError as exc:
                last_exc = exc
                if "transport error" in str(exc):
                    continue
                raise
        assert last_exc is not None
        raise last_exc

    for _turn in range(max_searches + 4):
        response_json = _post_once()
        try:
            message = response_json["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ExtractionError(
                "response contained no choices[0].message; expected a chat "
                "completion with a search_documents or submit_sct_fields "
                "tool call."
            ) from exc

        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list) or not tool_calls:
            raise ExtractionError(
                "response contained no tool call; expected "
                f"{SEARCH_TOOL_NAME!r} or {TOOL_NAME!r}."
            )
        tool_call = tool_calls[0]
        if not isinstance(tool_call, dict):
            raise ExtractionError("response tool_calls[0] was not an object.")
        function = tool_call.get("function", {})
        if not isinstance(function, dict):
            raise ExtractionError("tool call carried no function object.")
        name = function.get("name")

        messages.append(
            {
                "role": "assistant",
                "content": message.get("content"),
                "tool_calls": tool_calls,
            }
        )
        tool_call_id = tool_call.get("id")
        if not isinstance(tool_call_id, str) or not tool_call_id:
            tool_call_id = f"call_{searches}"

        if name == SEARCH_TOOL_NAME:
            if searches >= max_searches:
                tool_content = (
                    f"Search limit reached ({max_searches}). Do not search "
                    f"again - call {TOOL_NAME!r} now with the text already "
                    "provided."
                )
            else:
                query = _parse_search_query(function)
                hits = index.search(query, k=3, seen=seen)
                seen.update(hit.index for hit in hits)
                searches += 1
                if on_search is not None:
                    on_search()
                tool_content = _serialize_search_results(hits)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": tool_content,
                }
            )
            continue

        if name == TOOL_NAME:
            return _parse_tool_result(response_json)

        raise ExtractionError(
            f"unexpected tool call {name!r}; expected "
            f"{SEARCH_TOOL_NAME!r} or {TOOL_NAME!r}."
        )

    raise ExtractionError(
        f"model did not terminate the agentic extraction after "
        f"{max_searches} search(es); expected a final {TOOL_NAME!r} call."
    )


def extract_agentic(
    corpus: Sequence[str],
    *,
    embedder: EmbeddingModel | None = None,
    max_chars: int = MAX_CONTEXT_CHARS,
    max_searches: int = 4,
    on_search: Callable[[], None] | None = None,
) -> dict[str, str]:
    """Env-configured agentic extraction: ``openai_compatible_extract_agentic``
    with ``base_url``/``api_key``/``model`` from the environment.

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
    return openai_compatible_extract_agentic(
        corpus,
        base_url=config.base_url,
        api_key=config.api_key,
        model=config.model,
        embedder=embedder,
        extra_body=extra_body,
        max_chars=max_chars,
        max_searches=max_searches,
        on_search=on_search,
    )
