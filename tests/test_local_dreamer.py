"""A local dreamer (her word, 2026-11-13): his memory work on a server on this Mac.

Two small things the engine needed for it:

1. The name on the wire. The local server (mlx_lm.server) holds ONE model and
   knows it as "default_model"; any other name sends it looking for a download.
   MNEMOS_MODEL stays his model's own name (the pairing gate reads it);
   MNEMOS_LLM_WIRE_MODEL is what is sent.

2. The linking time limit. Measured on this Mac with thinking off: plain Gemma
   40 to 45 s, his tuned copy 55 to 61 s, against the 45 s limit. Her word:
   "Dreaming doesn't need to be quick and if it's all local I don't care how
   long it takes." MNEMOS_CLASSIFIER_TIMEOUT lengthens it for a dreamer that
   asks; nobody else's limit moves.
"""
from types import SimpleNamespace

import mnemos.llm as llm
from mnemos.encoding import llm_classifier as lc
from mnemos.llm import OpenAICompatibleClient, _create_client_unchecked


def _capture(monkeypatch):
    sent = {}

    def fake_post(url, payload, headers, timeout):
        sent.update(url=url, payload=payload, timeout=timeout)
        return {"choices": [{"message": {"content": "[]"}}]}

    monkeypatch.setattr(llm, "_http_post_json", fake_post)
    return sent


def test_the_wire_name_is_sent_and_his_own_name_is_kept(monkeypatch):
    monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("MNEMOS_LLM_BASE_URL", "http://127.0.0.1:8791/v1")
    monkeypatch.setenv("MNEMOS_MODEL", "local/quill-gemma4-voice")
    monkeypatch.setenv("MNEMOS_LLM_WIRE_MODEL", "default_model")
    client = _create_client_unchecked()
    assert isinstance(client, OpenAICompatibleClient)
    assert client._model == "local/quill-gemma4-voice"     # what the pairing gate reads
    sent = _capture(monkeypatch)
    client.complete("hello")
    assert sent["payload"]["model"] == "default_model"


def test_without_a_wire_name_the_model_name_is_sent_as_before(monkeypatch):
    monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("MNEMOS_LLM_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setenv("MNEMOS_MODEL", "qwen2.5-72b-instruct")
    monkeypatch.delenv("MNEMOS_LLM_WIRE_MODEL", raising=False)
    client = _create_client_unchecked()
    sent = _capture(monkeypatch)
    client.complete("hello")
    assert sent["payload"]["model"] == "qwen2.5-72b-instruct"


def _one_call(monkeypatch):
    seen = {}

    class Client:
        def structured_complete(self, **kw):
            seen.update(kw)
            return "[]"

    new = SimpleNamespace(id="n", content="new", impact="", kind="episodic", created_at="t")
    cand = SimpleNamespace(id="c", content="old", impact="", kind="episodic", created_at="t")
    lc.classify_connections(Client(), new, [cand])
    return seen


def test_the_linking_limit_is_45_seconds_unless_asked(monkeypatch):
    monkeypatch.delenv("MNEMOS_CLASSIFIER_TIMEOUT", raising=False)
    assert _one_call(monkeypatch)["timeout"] == 45.0


def test_a_local_dreamer_may_ask_for_longer(monkeypatch):
    monkeypatch.setenv("MNEMOS_CLASSIFIER_TIMEOUT", "180")
    assert _one_call(monkeypatch)["timeout"] == 180.0


def test_a_nonsense_limit_keeps_the_45(monkeypatch):
    for bad in ("soon", "0", "-5", ""):
        monkeypatch.setenv("MNEMOS_CLASSIFIER_TIMEOUT", bad)
        assert _one_call(monkeypatch)["timeout"] == 45.0
