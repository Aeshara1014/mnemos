"""Tests for OllamaClient — native /api/chat, thinking off by default."""
import io
import json

import pytest

from mnemos.llm import OllamaClient, _create_client_unchecked, create_client


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def captured(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append({"url": req.full_url, "body": json.loads(req.data.decode())})
        return _FakeResponse(json.dumps(
            {"message": {"role": "assistant", "content": "a finished thought"}}
        ).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return calls


class TestOllamaClient:
    def test_posts_native_chat_with_think_off(self, captured):
        client = OllamaClient(model="qwen3.6:35b-a3b")
        out = client.complete("hello")

        assert out == "a finished thought"
        call = captured[0]
        assert call["url"] == "http://localhost:11434/api/chat"
        assert call["body"]["think"] is False
        assert call["body"]["stream"] is False
        assert call["body"]["model"] == "qwen3.6:35b-a3b"

    def test_structured_maps_temperature_and_budget_to_options(self, captured):
        OllamaClient().structured_complete("be terse", "classify", temperature=0.2,
                                           max_tokens=1500)
        body = captured[0]["body"]
        assert body["messages"][0] == {"role": "system", "content": "be terse"}
        assert body["options"]["temperature"] == 0.2
        assert body["options"]["num_predict"] == 1500

    def test_tolerates_v1_style_base_url(self, captured):
        OllamaClient(base_url="http://localhost:11434/v1/").complete("x")
        assert captured[0]["url"] == "http://localhost:11434/api/chat"

    def test_think_opt_in(self, captured):
        OllamaClient(think=True).complete("x")
        assert captured[0]["body"]["think"] is True


class TestOllamaResolution:
    def test_forced_ollama_provider(self, monkeypatch):
        monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "ollama")
        monkeypatch.setenv("MNEMOS_MODEL", "qwen3.6:35b-a3b")

        client = _create_client_unchecked()

        assert isinstance(client, OllamaClient)
        assert client._model == "qwen3.6:35b-a3b"
        assert client._think is False

    def test_think_env_opt_in(self, monkeypatch):
        monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "ollama")
        monkeypatch.setenv("MNEMOS_OLLAMA_THINK", "1")
        assert _create_client_unchecked()._think is True

    def test_affinity_gate_applies(self, monkeypatch):
        monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "ollama")
        monkeypatch.setenv("MNEMOS_MODEL", "qwen3.6:35b-a3b")
        monkeypatch.setenv("MNEMOS_AGENT_MODEL", "claude-haiku-4.5")

        assert create_client() is None  # claude agent, qwen substrate: blocked
