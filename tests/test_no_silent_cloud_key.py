"""Regression: no substrate silently acquires a cloud key from config files.

Plants a fake HOME holding ``~/.openclaw/openclaw.json`` and
``~/.mnemos/config.json`` with live-looking keys, then proves none of the
three former key-hunts pick them up. Each of these would FAIL before the
fork-cleanup (the code used to read exactly these files).
"""
import json
from pathlib import Path


def _plant_home(tmp_path, monkeypatch):
    """Seed the two ambient config files the old key-hunts scanned."""
    oc = tmp_path / ".openclaw"
    oc.mkdir(parents=True, exist_ok=True)
    (oc / "openclaw.json").write_text(json.dumps({
        "openRouterApiKey": "sk-planted-openclaw",
        "tools": {"web": {"search": {"perplexity": {"apiKey": "sk-planted-perplexity"}}}},
    }))
    mn = tmp_path / ".mnemos"
    mn.mkdir(parents=True, exist_ok=True)
    (mn / "config.json").write_text(json.dumps({"openRouterApiKey": "sk-planted-mnemos"}))
    monkeypatch.setenv("HOME", str(tmp_path))
    # Sanity: the plant really is where the old code would have looked.
    assert (Path.home() / ".openclaw" / "openclaw.json").exists()


def test_substrate_get_api_key_ignores_config_files(tmp_path, monkeypatch):
    _plant_home(tmp_path, monkeypatch)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from mnemos.substrate.llm import get_api_key

    assert get_api_key() == ("", "")


def test_create_client_does_not_hunt_openclaw(tmp_path, monkeypatch):
    _plant_home(tmp_path, monkeypatch)
    # Prove it's the REMOVAL — not just the dotenv gate — that closes this.
    monkeypatch.delenv("MNEMOS_DISABLE_DOTENV", raising=False)
    monkeypatch.chdir(tmp_path)  # no ambient .env in the working dir
    monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "openrouter")

    from mnemos.llm import _create_client_unchecked

    client = _create_client_unchecked()
    assert client is None, (
        f"a planted ambient config minted a client: {type(client).__name__}"
    )


def test_session_indexer_no_openclaw_fallback(tmp_path, monkeypatch):
    _plant_home(tmp_path, monkeypatch)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    from mnemos.indexer.session_indexer import SessionIndexer

    idx = SessionIndexer(agent_id="t", db_path=str(tmp_path / "t.db"))
    assert idx._get_api_key() == ""


def test_claude_code_adapter_ignores_openclaw_agent_keys(tmp_path, monkeypatch):
    """The 4th former key-hunt: index_session used to read an sk-or key out of
    ~/.openclaw/agents/<name>/agent/models.json. Prove it no longer does."""
    agent_dir = tmp_path / ".openclaw" / "agents" / "main" / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "models.json").write_text(json.dumps({
        "providers": {"openrouter": {"apiKey": "sk-or-PLANTED-EVIL"}}
    }))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    import mnemos.indexer.claude_code_adapter as adapter
    import mnemos.indexer.session_indexer as si_module

    captured = {}

    class _StubIndexer:
        min_session_messages = 999  # forces the early return, no LLM work

        def __init__(self, *args, **kwargs):
            captured["openrouter_api_key"] = kwargs.get("openrouter_api_key")

    # index_session imports SessionIndexer locally from this module at call time.
    monkeypatch.setattr(si_module, "SessionIndexer", _StubIndexer)

    transcript = tmp_path / "session.jsonl"
    transcript.write_text("")  # 0 messages -> returns right after construction

    adapter.index_session(str(transcript), agent_id="t")

    # The planted OpenClaw agent key must NOT have become the indexer's key.
    assert captured.get("openrouter_api_key") == ""
