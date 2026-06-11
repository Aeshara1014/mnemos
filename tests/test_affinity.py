"""Substrate affinity: the mind that maintains the memories must be kin
to the mind that lives them.

Tests the family detector, the policy matrix, and the create_client gate.
"""

import pytest

from mnemos.affinity import (
    AffinityCheck,
    check_affinity,
    model_family,
    normalize_model_id,
)


# ── normalization ──

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("anthropic/claude-sonnet-4-5", "claude-sonnet-4-5"),
        ("openrouter/openai/gpt-5", "gpt-5"),
        ("  Claude-Opus-4-6 ", "claude-opus-4-6"),
        (None, ""),
        ("", ""),
    ],
)
def test_normalize_model_id(raw, expected):
    assert normalize_model_id(raw) == expected


# ── family detection ──

@pytest.mark.parametrize(
    "model, family",
    [
        ("claude-sonnet-4-6", "claude"),
        ("anthropic/claude-opus-4-6", "claude"),
        ("gpt-5.2", "gpt"),
        ("openai/gpt-4o-mini", "gpt"),
        ("o3-mini", "gpt"),
        ("chatgpt-4o-latest", "gpt"),
        ("gemini-2.5-pro", "gemini"),
        ("gemma-3-27b", "gemma"),
        ("meta-llama/llama-4-maverick", "llama"),
        ("qwen-3-235b", "qwen"),
        ("mistral-large-2", "mistral"),
        ("mixtral-8x22b", "mistral"),
        ("deepseek-r2", "deepseek"),
        ("x-ai/grok-4", "grok"),
        ("totally-novel-model-9000", "unknown"),
        (None, "unknown"),
    ],
)
def test_model_family(model, family):
    assert model_family(model) == family


# ── policy matrix ──

def test_family_policy_same_family_allowed():
    c = check_affinity("claude-opus-4-6", "anthropic/claude-sonnet-4-5", "family")
    assert c.allowed and c.agent_family == c.substrate_family == "claude"


def test_family_policy_cross_family_blocked():
    c = check_affinity("claude-opus-4-6", "openai/gpt-4o-mini", "family")
    assert not c.allowed
    assert "must not rewrite" in c.message


def test_family_policy_unknown_family_allowed_with_warning():
    c = check_affinity("claude-opus-4-6", "totally-novel-model-9000", "family")
    assert c.allowed and "unenforceable" in c.message.lower()


def test_strict_policy_exact_match_allowed():
    c = check_affinity("claude-sonnet-4-5", "anthropic/claude-sonnet-4-5", "strict")
    assert c.allowed


def test_strict_policy_same_family_different_model_blocked():
    c = check_affinity("claude-opus-4-6", "claude-sonnet-4-5", "strict")
    assert not c.allowed


def test_open_policy_always_allows_but_reports():
    c = check_affinity("claude-opus-4-6", "gpt-5", "open")
    assert c.allowed
    assert "different mind" in c.message


def test_unset_agent_model_allows_with_guidance():
    c = check_affinity("", "claude-sonnet-4-5", "family")
    assert c.allowed and "MNEMOS_AGENT_MODEL" in c.message


def test_unknown_policy_falls_back_to_family():
    c = check_affinity("claude-opus-4-6", "gpt-5", "lenient-ish")
    assert c.policy == "family"
    assert not c.allowed


def test_check_serializes():
    c = check_affinity("claude-opus-4-6", "claude-sonnet-4-5", "family")
    assert isinstance(c, AffinityCheck)
    d = c.to_dict()
    assert d["allowed"] is True and d["policy"] == "family"


# ── the create_client gate ──

def _clear_mnemos_env(monkeypatch):
    for var in (
        "MNEMOS_LLM_PROVIDER", "MNEMOS_MODEL", "MNEMOS_AGENT_MODEL",
        "MNEMOS_SUBSTRATE_AFFINITY", "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY", "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


def test_create_client_blocks_cross_family_substrate(monkeypatch, tmp_path):
    from mnemos.llm import create_client

    _clear_mnemos_env(monkeypatch)
    monkeypatch.chdir(tmp_path)  # ensure no .env leakage
    monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    monkeypatch.setenv("MNEMOS_MODEL", "anthropic/claude-sonnet-4-5")
    monkeypatch.setenv("MNEMOS_AGENT_MODEL", "gpt-5")
    monkeypatch.setenv("MNEMOS_SUBSTRATE_AFFINITY", "family")
    assert create_client() is None, "cross-family substrate must be refused"


def test_create_client_allows_same_family_substrate(monkeypatch, tmp_path):
    from mnemos.llm import create_client

    _clear_mnemos_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    monkeypatch.setenv("MNEMOS_MODEL", "anthropic/claude-sonnet-4-5")
    monkeypatch.setenv("MNEMOS_AGENT_MODEL", "claude-opus-4-6")
    monkeypatch.setenv("MNEMOS_SUBSTRATE_AFFINITY", "family")
    assert create_client() is not None


def test_create_client_unset_agent_model_does_not_break_existing_users(monkeypatch, tmp_path):
    from mnemos.llm import create_client

    _clear_mnemos_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    monkeypatch.setenv("MNEMOS_MODEL", "anthropic/claude-sonnet-4-5")
    assert create_client() is not None
