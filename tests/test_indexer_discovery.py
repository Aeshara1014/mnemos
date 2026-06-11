"""Indexer agent discovery: config-driven, never hardcoded personal names.

Regression for the hardcoded ("anima", "luca", "main") tuple and the
personal defaults (agent_id="claude-field", user_name="Riley", a private
project list) that lived in the Claude Code adapter.
"""

from pathlib import Path

from mnemos.core.types import DEFAULT_AGENT_ID
from mnemos.indexer.claude_code_adapter import (
    _discover_openclaw_agents,
    _resolve_agent_id,
)


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("MNEMOS_OPENCLAW_AGENTS", "nova, vektor")
    assert _discover_openclaw_agents() == ["nova", "vektor"]


def test_discovery_scans_agents_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("MNEMOS_OPENCLAW_AGENTS", raising=False)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    for agent, has_models in (("nova", True), ("vektor", True), ("empty", False)):
        d = tmp_path / ".openclaw" / "agents" / agent / "agent"
        d.mkdir(parents=True)
        if has_models:
            (d / "models.json").write_text("{}")

    assert _discover_openclaw_agents() == ["nova", "vektor"]


def test_discovery_empty_when_no_openclaw(monkeypatch, tmp_path):
    monkeypatch.delenv("MNEMOS_OPENCLAW_AGENTS", raising=False)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert _discover_openclaw_agents() == []


def test_agent_id_resolution_order(monkeypatch):
    monkeypatch.setenv("MNEMOS_AGENT_ID", "from-env")
    assert _resolve_agent_id("explicit") == "explicit"
    assert _resolve_agent_id(None) == "from-env"
    monkeypatch.delenv("MNEMOS_AGENT_ID")
    assert _resolve_agent_id(None) == DEFAULT_AGENT_ID


def test_no_personal_names_in_adapter_source():
    """The leak class must not quietly return."""
    source = (
        Path(__file__).parent.parent
        / "mnemos" / "indexer" / "claude_code_adapter.py"
    ).read_text()
    for personal in ('"anima"', '"luca"', '"Riley"', '"claude-field"'):
        assert personal not in source, f"personal default {personal} reintroduced"
