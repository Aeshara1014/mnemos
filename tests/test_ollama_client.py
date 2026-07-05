"""Tests for OllamaClient — native /api/chat, thinking off by default."""
from mnemos.llm import OllamaClient, _create_client_unchecked, create_client

_OLLAMA_SHAPE = {"message": {"role": "assistant", "content": "a finished thought"}}


class TestOllamaClient:
    def test_posts_native_chat_with_think_off(self, capture_urlopen):
        calls, respond_with = capture_urlopen
        respond_with(_OLLAMA_SHAPE)
        client = OllamaClient(model="qwen3.6:35b-a3b")

        out = client.complete("hello")

        assert out == "a finished thought"
        call = calls[0]
        assert call["url"] == "http://localhost:11434/api/chat"
        assert call["body"]["think"] is False
        assert call["body"]["stream"] is False
        assert call["body"]["model"] == "qwen3.6:35b-a3b"

    def test_structured_maps_temperature_and_budget_to_options(self, capture_urlopen):
        calls, respond_with = capture_urlopen
        respond_with(_OLLAMA_SHAPE)
        OllamaClient().structured_complete("be terse", "classify", temperature=0.2,
                                           max_tokens=1500)
        body = calls[0]["body"]
        assert body["messages"][0] == {"role": "system", "content": "be terse"}
        assert body["options"]["temperature"] == 0.2
        assert body["options"]["num_predict"] == 1500

    def test_tolerates_v1_style_base_url(self, capture_urlopen):
        calls, respond_with = capture_urlopen
        respond_with(_OLLAMA_SHAPE)
        OllamaClient(base_url="http://localhost:11434/v1/").complete("x")
        assert calls[0]["url"] == "http://localhost:11434/api/chat"

    def test_think_opt_in(self, capture_urlopen):
        calls, respond_with = capture_urlopen
        respond_with(_OLLAMA_SHAPE)
        OllamaClient(think=True).complete("x")
        assert calls[0]["body"]["think"] is True


class TestOllamaResolution:
    def test_forced_ollama_provider(self, monkeypatch):
        monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "ollama")
        monkeypatch.setenv("MNEMOS_MODEL", "qwen3.6:35b-a3b")

        client = _create_client_unchecked()

        assert isinstance(client, OllamaClient)
        assert client._model == "qwen3.6:35b-a3b"
        assert client._think is False

    def test_forced_ollama_without_model_yields_no_substrate(self, monkeypatch):
        """Local intent is never satisfied by guessing or by cloud keys."""
        monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "ollama")
        monkeypatch.setenv("OPENROUTER_API_KEY", "ambient-cloud-key")

        assert _create_client_unchecked() is None

    def test_think_env_opt_in(self, monkeypatch):
        monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "ollama")
        monkeypatch.setenv("MNEMOS_MODEL", "qwen3.6:35b-a3b")
        monkeypatch.setenv("MNEMOS_OLLAMA_THINK", "1")
        assert _create_client_unchecked()._think is True

    def test_affinity_gate_applies(self, monkeypatch):
        monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "ollama")
        monkeypatch.setenv("MNEMOS_MODEL", "qwen3.6:35b-a3b")
        monkeypatch.setenv("MNEMOS_AGENT_MODEL", "claude-haiku-4.5")

        assert create_client() is None  # claude agent, qwen substrate: blocked
