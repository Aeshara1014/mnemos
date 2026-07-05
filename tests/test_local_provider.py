"""Tests for OpenAICompatibleClient and its create_client resolution — the
local-substrate door (LM Studio, Ollama, vLLM, mlx servers)."""
from mnemos.llm import OpenAICompatibleClient, create_client, _create_client_unchecked

_OPENAI_SHAPE = {"choices": [{"message": {"content": "a considered local reply"}}]}


class TestOpenAICompatibleClient:
    def test_complete_posts_to_base_url(self, capture_urlopen):
        calls, respond_with = capture_urlopen
        respond_with(_OPENAI_SHAPE)
        client = OpenAICompatibleClient(
            base_url="http://localhost:1234/v1/", model="qwen2.5-72b-instruct",
        )

        out = client.complete("hello there")

        assert out == "a considered local reply"
        call = calls[0]
        assert call["url"] == "http://localhost:1234/v1/chat/completions"
        assert call["body"]["model"] == "qwen2.5-72b-instruct"
        assert call["body"]["messages"][0]["content"] == "hello there"

    def test_structured_complete_carries_system_and_temperature(self, capture_urlopen):
        calls, respond_with = capture_urlopen
        respond_with(_OPENAI_SHAPE)
        OpenAICompatibleClient(base_url="http://localhost:1234/v1").structured_complete(
            "be brief", "classify this", temperature=0.2,
        )

        body = calls[0]["body"]
        assert body["messages"][0] == {"role": "system", "content": "be brief"}
        assert body["temperature"] == 0.2

    def test_no_auth_header_without_key(self, capture_urlopen):
        calls, respond_with = capture_urlopen
        respond_with(_OPENAI_SHAPE)
        OpenAICompatibleClient(base_url="http://localhost:1234/v1").complete("x")
        headers = {k.lower() for k in calls[0]["headers"]}
        assert "authorization" not in headers

    def test_auth_header_when_key_given(self, capture_urlopen):
        calls, respond_with = capture_urlopen
        respond_with(_OPENAI_SHAPE)
        OpenAICompatibleClient(
            base_url="http://localhost:1234/v1", api_key="secret",
        ).complete("x")
        headers = {k.lower(): v for k, v in calls[0]["headers"].items()}
        assert headers.get("authorization") == "Bearer secret"


class TestCreateClientResolution:
    def test_forced_local_provider_uses_base_url(self, monkeypatch):
        monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "local")
        monkeypatch.setenv("MNEMOS_LLM_BASE_URL", "http://localhost:1234/v1")
        monkeypatch.setenv("MNEMOS_MODEL", "qwen2.5-72b-instruct")

        client = _create_client_unchecked()

        assert isinstance(client, OpenAICompatibleClient)
        assert client._model == "qwen2.5-72b-instruct"
        assert client._base_url == "http://localhost:1234/v1"

    def test_forced_local_without_base_url_yields_no_substrate(self, monkeypatch):
        monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "openai-compatible")
        assert _create_client_unchecked() is None

    def test_local_intent_never_falls_back_to_ambient_cloud_key(self, monkeypatch):
        """The DD-021 case: explicit LOCAL intent + missing base_url + an
        ambient cloud key in the environment must yield NO substrate —
        never a silent cloud client."""
        monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "local")
        monkeypatch.setenv("OPENROUTER_API_KEY", "ambient-cloud-key")

        assert _create_client_unchecked() is None

    def test_explicit_base_url_outranks_ambient_cloud_key(self, monkeypatch):
        monkeypatch.setenv("MNEMOS_LLM_BASE_URL", "http://localhost:1234/v1")
        monkeypatch.setenv("OPENROUTER_API_KEY", "ambient-cloud-key")

        client = _create_client_unchecked()

        assert isinstance(client, OpenAICompatibleClient)

    def test_affinity_gate_applies_to_local_models_too(self, monkeypatch):
        """A local substrate is still a substrate — kinship is enforced."""
        monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "local")
        monkeypatch.setenv("MNEMOS_LLM_BASE_URL", "http://localhost:1234/v1")
        monkeypatch.setenv("MNEMOS_MODEL", "qwen2.5-72b-instruct")
        monkeypatch.setenv("MNEMOS_AGENT_MODEL", "claude-haiku-4.5")

        assert create_client() is None  # family violated: claude vs qwen

        monkeypatch.setenv("MNEMOS_AGENT_MODEL", "qwq-32b")  # qwen family
        client = create_client()
        assert isinstance(client, OpenAICompatibleClient)
