"""OpenRouterClient reasoning cap (the Gemini-3.x tax fix).

A thinking model spends output tokens on hidden reasoning; Pro-tier models
won't allow zero, so the client caps reasoning low and reserves budget
headroom so the visible answer is never starved. These tests capture the
exact request body the client posts — no network — and assert the control
and the headroom, the property that keeps a resident's belief-formation
from silently truncating.
"""

import json
import urllib.request

import pytest

from mnemos.llm import OpenRouterClient


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._payload).encode()


@pytest.fixture()
def captured(monkeypatch):
    """Intercept the POST and hand back the parsed request body."""
    box: dict = {}

    def fake_urlopen(req, timeout=None):
        box["body"] = json.loads(req.data.decode())
        box["url"] = req.full_url
        return _FakeResp({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return box


def test_structured_complete_default_caps_reasoning_low(captured):
    client = OpenRouterClient(api_key="k", model="google/gemini-3.1-pro-preview")
    out = client.structured_complete(system="s", user="u", max_tokens=1000)
    assert out == "ok"
    assert captured["body"]["reasoning"] == {"effort": "low"}
    # low reserves 512 of headroom above the caller's requested output budget
    assert captured["body"]["max_tokens"] == 1000 + 512


def test_complete_default_caps_reasoning_low(captured):
    OpenRouterClient(api_key="k", model="m", max_tokens=500).complete("hi")
    assert captured["body"]["reasoning"] == {"effort": "low"}
    assert captured["body"]["max_tokens"] == 500 + 512


def test_high_effort_reserves_more_headroom(captured):
    client = OpenRouterClient(api_key="k", model="m", reasoning_effort="high")
    client.structured_complete(system="s", user="u", max_tokens=1000)
    assert captured["body"]["reasoning"] == {"effort": "high"}
    assert captured["body"]["max_tokens"] == 1000 + 2048


def test_reasoning_off_sends_no_field_and_no_headroom(captured):
    # None (or "") disables the cap entirely — the model's own default.
    OpenRouterClient(api_key="k", model="m", max_tokens=500,
                     reasoning_effort=None).complete("hi")
    assert "reasoning" not in captured["body"]
    assert captured["body"]["max_tokens"] == 500


def test_empty_string_effort_disables_cap(captured):
    OpenRouterClient(api_key="k", model="m", max_tokens=500,
                     reasoning_effort="").complete("hi")
    assert "reasoning" not in captured["body"]
    assert captured["body"]["max_tokens"] == 500


# ── the resolver honors MNEMOS_REASONING_EFFORT on EVERY OpenRouter path ──

@pytest.fixture()
def clean_env(tmp_path, monkeypatch):
    """A clean slate: no ambient provider/keys, no .env hunting — the
    resolver sees only what the test sets."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("MNEMOS_DISABLE_DOTENV", "1")
    for var in ("MNEMOS_LLM_PROVIDER", "MNEMOS_LLM_BASE_URL", "MNEMOS_MODEL",
                "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY",
                "MNEMOS_REASONING_EFFORT"):
        monkeypatch.delenv(var, raising=False)


def test_autodetect_openrouter_honors_reasoning_effort(clean_env, monkeypatch):
    # OPENROUTER_API_KEY set but no MNEMOS_LLM_PROVIDER → auto-detect path.
    # Regression: this branch used to ignore the effort env and pin 'low'.
    from mnemos.llm import _create_client_unchecked
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("MNEMOS_REASONING_EFFORT", "high")
    client = _create_client_unchecked()
    assert isinstance(client, OpenRouterClient)
    assert client._reasoning_effort == "high"


def test_forced_openrouter_honors_reasoning_effort(clean_env, monkeypatch):
    from mnemos.llm import _create_client_unchecked
    monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("MNEMOS_REASONING_EFFORT", "medium")
    client = _create_client_unchecked()
    assert isinstance(client, OpenRouterClient)
    assert client._reasoning_effort == "medium"


def test_openrouter_reasoning_effort_defaults_low_when_unset(clean_env, monkeypatch):
    from mnemos.llm import _create_client_unchecked
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    client = _create_client_unchecked()
    assert isinstance(client, OpenRouterClient)
    assert client._reasoning_effort == "low"
