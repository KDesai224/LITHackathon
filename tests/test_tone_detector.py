"""Tests for the hostile language detector and protective guidance module."""

from backend.tone_detector import (
    PUNCHY_COURT_DISCLAIMER,
    check_tone,
    check_tone_heuristics,
)


def test_clean_factual_statement():
    text = (
        "I engaged the respondent to renovate my kitchen for $8,000. "
        "I paid a $3,000 deposit on 15 March 2026, but the respondent failed to start work."
    )
    res = check_tone_heuristics(text)
    assert not res.flagged
    assert res.suggested_clean_rewrite == text


def test_user_ageist_generalization_example():
    text = "i want my money back these young people are always like this useless money stealing youth."
    res = check_tone_heuristics(text)
    assert res.flagged
    assert res.category == "group_generalization"
    assert res.prompt_message == "Are you sure you wish to proceed with this wording?"
    assert res.disclaimer == PUNCHY_COURT_DISCLAIMER
    assert "these young people" in (res.flagged_snippet or "").lower()
    assert res.suggested_clean_rewrite != text
    assert len(res.suggested_clean_rewrite) > 10


def test_criminal_accusation_and_threat():
    text = "The respondent is a thief and scammer who stole my deposit. I will ruin your business if you don't pay."
    res = check_tone_heuristics(text)
    assert res.flagged
    assert res.disclaimer == PUNCHY_COURT_DISCLAIMER
    assert res.can_proceed is True


def test_check_tone_fallback():
    # Calling check_tone directly (offline fallback)
    res = check_tone("This scammer took my funds.")
    assert res.flagged
