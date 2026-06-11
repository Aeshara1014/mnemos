"""Affinity follow-through: provenance and operator visibility.

- Every consolidation cycle records WHO performed the agent's sleep
  (substrate model + affinity verdict) in consolidation_log.
- `mnemos doctor` reports the affinity configuration and verdict.
- A forced provider that cannot be honored warns loudly instead of
  silently substituting another mind (F4).
"""

import logging

import pytest

from mnemos.consolidation.daemon import ConsolidationDaemon
from mnemos.store.sqlite_store import EngramStore


class StubClient:
    """Minimal LLM client with a model identity."""

    def __init__(self, model: str):
        self._model = model

    def complete(self, prompt: str) -> str:
        return ""


def _clear_mnemos_env(monkeypatch):
    for var in (
        "MNEMOS_LLM_PROVIDER", "MNEMOS_MODEL", "MNEMOS_AGENT_MODEL",
        "MNEMOS_SUBSTRATE_AFFINITY", "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY", "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


# ── substrate provenance in consolidation_log ──


def test_cycle_records_substrate_provenance(tmp_path, monkeypatch):
    _clear_mnemos_env(monkeypatch)
    monkeypatch.setenv("MNEMOS_AGENT_MODEL", "claude-opus-4-6")

    store = EngramStore(tmp_path / "prov.db")
    try:
        daemon = ConsolidationDaemon(
            store=store, config={}, llm_client=StubClient("claude-sonnet-4-6")
        )
        stats = daemon.run_cycle(deep=False, agent_id="nova")

        assert stats["substrate"]["model"] == "claude-sonnet-4-6"
        assert stats["substrate"]["provider"] == "StubClient"
        assert stats["substrate"]["affinity_allowed"] is True
        assert stats["substrate"]["agent_model"] == "claude-opus-4-6"

        runs = store.get_consolidation_runs("cycle")
        assert runs, "cycle was not logged"
        logged = runs[0]["stats"]["substrate"]
        assert logged["model"] == "claude-sonnet-4-6"
        assert logged["affinity_policy"] == "family"
    finally:
        store.close()


def test_cycle_records_no_substrate_when_rule_based(tmp_path, monkeypatch):
    _clear_mnemos_env(monkeypatch)
    store = EngramStore(tmp_path / "prov2.db")
    try:
        daemon = ConsolidationDaemon(store=store, config={}, llm_client=None)
        stats = daemon.run_cycle(deep=False, agent_id="nova")
        assert stats["substrate"]["model"] is None
        assert "rule-based" in stats["substrate"]["note"]
    finally:
        store.close()


def test_cross_family_substrate_provenance_is_honest(tmp_path, monkeypatch):
    """A daemon handed a foreign client still records the violation."""
    _clear_mnemos_env(monkeypatch)
    monkeypatch.setenv("MNEMOS_AGENT_MODEL", "claude-opus-4-6")

    store = EngramStore(tmp_path / "prov3.db")
    try:
        daemon = ConsolidationDaemon(
            store=store, config={}, llm_client=StubClient("gpt-5")
        )
        stats = daemon.run_cycle(deep=False, agent_id="nova")
        assert stats["substrate"]["affinity_allowed"] is False
        assert "must not rewrite" in stats["substrate"]["affinity_message"]
    finally:
        store.close()


# ── doctor surfaces affinity ──


def test_doctor_reports_affinity(tmp_path, monkeypatch, capsys):
    from mnemos.cli import main

    _clear_mnemos_env(monkeypatch)
    monkeypatch.setenv("MNEMOS_AGENT_MODEL", "claude-opus-4-6")

    result = main(
        [
            "doctor",
            "--db-path", str(tmp_path / "doctor.db"),
            "--agent-id", "nova",
            "--person-id", "riley",
            "--project-scope", "demo",
        ]
    )
    out = capsys.readouterr().out
    assert result == 0
    assert "Affinity:" in out
    assert "policy=family" in out
    assert "agent=claude-opus-4-6" in out
    assert "verdict=" in out


# ── F4: forced provider must not silently substitute ──


def test_forced_anthropic_missing_package_warns(monkeypatch, tmp_path, caplog):
    import sys as _sys

    from mnemos.llm import _create_client_unchecked

    _clear_mnemos_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fallback-key-not-real")
    # Simulate the anthropic package being uninstalled.
    monkeypatch.setitem(_sys.modules, "anthropic", None)

    with caplog.at_level(logging.WARNING, logger="mnemos.llm"):
        client = _create_client_unchecked()

    assert any(
        "MNEMOS_LLM_PROVIDER=anthropic" in r.message and "not installed" in r.message
        for r in caplog.records
    ), "silent provider substitution: no warning emitted"
    # The fallback itself still happens — loudly, not silently.
    assert client is not None and type(client).__name__ == "OpenRouterClient"


def test_forced_openrouter_missing_key_warns(monkeypatch, tmp_path, caplog):
    from mnemos.llm import _create_client_unchecked

    _clear_mnemos_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "openrouter")
    # No key anywhere (env cleared; openclaw lookup may still find one on
    # a dev machine, so only assert when fallback actually occurred).
    with caplog.at_level(logging.WARNING, logger="mnemos.llm"):
        client = _create_client_unchecked()

    if client is None or type(client).__name__ != "OpenRouterClient":
        assert any(
            "MNEMOS_LLM_PROVIDER=openrouter" in r.message for r in caplog.records
        )


def test_anthropic_model_override_respected(monkeypatch, tmp_path):
    """MNEMOS_MODEL applies to the auto-detected Anthropic client too."""
    anthropic = pytest.importorskip("anthropic", reason="anthropic SDK not installed")  # noqa: F841

    from mnemos.llm import _create_client_unchecked

    _clear_mnemos_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setenv("MNEMOS_MODEL", "claude-opus-4-6")

    client = _create_client_unchecked()
    assert client is not None
    assert client._model == "claude-opus-4-6"
