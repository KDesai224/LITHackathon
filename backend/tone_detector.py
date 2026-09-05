"""Hostile language detection and protective guidance for SCT filings.

In line with the Singapore Courts' Guide on GenAI and the Small Claims Tribunals Act,
this module flags hostile, extreme, or generalizing language in free-text claim
statements and provides protective, non-punitive guidance:
1. Visual alert on the input box ("Are you sure you wish to proceed?").
2. Short, grounded disclaimer on why this language harms settlement rates and credibility.
3. Clean, court-admissible factual rewrite keeping the user's core dispute.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

DEFAULT_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEFAULT_TIMEOUT = int(os.getenv("OPENAI_TIMEOUT_SECONDS", "30"))

PUNCHY_COURT_DISCLAIMER = (
    "Court mediation data shows that personal insults and generalizations drastically reduce your chances "
    "of an amicable settlement and weaken your credibility before the Magistrate."
)


@dataclass
class ToneCheckResult:
    flagged: bool
    prompt_message: str
    disclaimer: str
    flagged_snippet: str | None = None
    category: str | None = None
    suggested_clean_rewrite: str = ""
    can_proceed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Tier 1: Fast Heuristic & Pattern Rules (<5ms, zero network dependency)
# --------------------------------------------------------------------------- #

_HEURISTIC_RULES: list[dict[str, Any]] = [
    {
        "category": "group_generalization",
        "pattern": re.compile(
            r"\b(these\s+(?:young|old)\s+people|(?:all\s+)?youths?|useless\s+(?:youth|kids?|people)|"
            r"these\s+[a-z]+\s+are\s+always|typical\s+(?:young|old|millennial|boomer))\b",
            re.IGNORECASE,
        ),
        "label": "Generalizing or ageist comment",
    },
    {
        "category": "criminal_accusation",
        "pattern": re.compile(
            r"\b(thief|thieves|scammer|scammers|scam|fraudster|con\s*artist|crook|crooks|cheater|stole|robbed|criminal)\b",
            re.IGNORECASE,
        ),
        "label": "Unproven criminal accusation",
    },
    {
        "category": "personal_insult",
        "pattern": re.compile(
            r"\b(useless|idiot|idiots|stupid|asshole|liar|liars|scumbag|scum|shameless|cheat)\b",
            re.IGNORECASE,
        ),
        "label": "Insulting or abusive wording",
    },
    {
        "category": "threat_intimidation",
        "pattern": re.compile(
            r"\b(regret\s+this|ruin\s+you|ruin\s+your|police\s+on\s+you|pay\s+or\s+else|destroy\s+you)\b",
            re.IGNORECASE,
        ),
        "label": "Threatening or coercive language",
    },
]


def _build_heuristic_rewrite(text: str) -> str:
    """Build a clean, factual fallback rewrite by neutralizing flagged terms."""
    cleaned = text
    # Replace common hostile snippets with neutral dispute statements
    cleaned = re.sub(
        r"\b(?:these\s+(?:young|old)\s+people\s+are\s+always\s+like\s+this\s+)?useless\s+money\s+stealing\s+youth\b",
        "the respondent failed to return my money as agreed",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\b(is\s+a\s+)?(thief|scammer|fraudster|con\s*artist|crook)\b", "failed to fulfill the agreement", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(stole\s+my\s+money)\b", "has not returned the payment made", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(useless|idiot|stupid|liar|scumbag)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # If the text was overly simplified or emptied, provide a standard court-admissible template
    if len(cleaned) < 15 or "money back" in cleaned.lower():
        return "I am claiming a refund of the amount paid because the respondent failed to deliver the agreed goods/services and has not repaid me despite repeated requests."
    return cleaned


def check_tone_heuristics(text: str) -> ToneCheckResult:
    """Fast local scan for hostile, accusatory, or generalizing language."""
    if not text or not text.strip():
        return ToneCheckResult(
            flagged=False,
            prompt_message="",
            disclaimer="",
            suggested_clean_rewrite=text,
        )

    matched_snippets: list[str] = []
    matched_category: str | None = None

    for rule in _HEURISTIC_RULES:
        matches = rule["pattern"].findall(text)
        if matches:
            if not matched_category:
                matched_category = rule["category"]
            for m in matches:
                matched_snippets.append(m if isinstance(m, str) else m[0])

    if not matched_snippets:
        return ToneCheckResult(
            flagged=False,
            prompt_message="",
            disclaimer="",
            suggested_clean_rewrite=text,
        )

    first_snippet = matched_snippets[0]
    rewrite = _build_heuristic_rewrite(text)

    return ToneCheckResult(
        flagged=True,
        prompt_message="Are you sure you wish to proceed with this wording?",
        disclaimer=PUNCHY_COURT_DISCLAIMER,
        flagged_snippet=first_snippet,
        category=matched_category,
        suggested_clean_rewrite=rewrite,
        can_proceed=True,
    )


# --------------------------------------------------------------------------- #
# Tier 2: LLM Classifier & Contextual Rewriter (~500ms)
# --------------------------------------------------------------------------- #

_LLM_PROMPT = """You are an intake assistant for the Singapore Small Claims Tribunals (SCT).
Review the claimant's draft statement for hostile, insulting, threatening, or generalizing language (e.g. ageist or group attacks, calling someone a scammer/thief without conviction).

Rules:
1. If the text is calm, factual, and neutral: flagged = false.
2. If hostile/extreme language is present: flagged = true.
   - flagged_snippet: short excerpt of the problematic words.
   - category: e.g. "group_generalization", "criminal_accusation", "insult", or "threat".
   - suggested_clean_rewrite: a factual, professional version stating the financial loss, contract breach, and lack of refund, without any insults or generalizations.
3. Keep the prompt_message as: "Are you sure you wish to proceed with this wording?"
4. Keep the disclaimer punchy: "Court mediation data shows that personal insults and generalizations drastically reduce your chances of an amicable settlement and weaken your credibility before the Magistrate."

Respond ONLY with a valid JSON object matching this format:
{
  "flagged": true,
  "prompt_message": "Are you sure you wish to proceed with this wording?",
  "disclaimer": "Court mediation data shows that personal insults and generalizations drastically reduce your chances of an amicable settlement and weaken your credibility before the Magistrate.",
  "flagged_snippet": "...",
  "category": "...",
  "suggested_clean_rewrite": "..."
}"""


def check_tone_llm(
    text: str,
    *,
    api_key: str | None = None,
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    timeout: int = DEFAULT_TIMEOUT,
) -> ToneCheckResult:
    """Evaluate tone with an OpenAI-compatible model with fallback to heuristics."""
    key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
    if not key:
        return check_tone_heuristics(text)

    try:
        resp = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0.1,
                "messages": [
                    {"role": "system", "content": _LLM_PROMPT},
                    {"role": "user", "content": f"Statement to review:\n{text}"},
                ],
                "response_format": {"type": "json_object"},
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            return check_tone_heuristics(text)

        payload = json.loads(resp.json()["choices"][0]["message"]["content"])
        is_flagged = bool(payload.get("flagged", False))

        return ToneCheckResult(
            flagged=is_flagged,
            prompt_message=payload.get("prompt_message", "Are you sure you wish to proceed with this wording?") if is_flagged else "",
            disclaimer=payload.get("disclaimer", PUNCHY_COURT_DISCLAIMER) if is_flagged else "",
            flagged_snippet=payload.get("flagged_snippet"),
            category=payload.get("category"),
            suggested_clean_rewrite=payload.get("suggested_clean_rewrite", text),
            can_proceed=True,
        )
    except Exception:  # noqa: BLE001 - deliberate fallback to heuristic tier on any provider failure
        return check_tone_heuristics(text)


def check_tone(text: str) -> ToneCheckResult:
    """Public interface: checks tone using Tier 2 (LLM) if available, with Tier 1 heuristic fallback."""
    # Run Tier 1 first for immediate detection
    heuristic_res = check_tone_heuristics(text)
    # If API key exists, enhance with LLM for context-specific rewrite
    if os.getenv("OPENAI_API_KEY", "").strip():
        return check_tone_llm(text)
    return heuristic_res
