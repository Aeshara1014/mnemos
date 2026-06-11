"""Affinity hint plumbing: an agent's self-declared model (e.g. from
mnemos_introduce) feeds the affinity gate when MNEMOS_AGENT_MODEL is
unset — the environment variable always takes precedence.

Covers resolve_affinity_status, the create_client gate, and the
consolidation daemon's substrate provenance.
"""

from mnemos.consolidation.daemon import ConsolidationDaemon
from mnemos.llm import create_client, resolve_affinity_status


class StubClient:
    """Minimal substrate stand-in: a model id and a no-op complete()."""

    _model = "claude-sonnet-4-6"

    def complete(self, prompt: str) -> str:
        return ""


def test_hint_used_when_env_unset():
    """With MNEMOS_AGENT_MODEL unset, the hint supplies the agent model."""
    status = resolve_affinity_status(
        None, resolve_if_missing=False, agent_model_hint="claude-opus-4-6"
    )
    assert status["agent_model"] == "claude-opus-4-6"


def test_env_beats_hint(monkeypatch):
    """MNEMOS_AGENT_MODEL always wins over a self-declared hint."""
    monkeypatch.setenv("MNEMOS_AGENT_MODEL", "gpt-5")
    status = resolve_affinity_status(
        None, resolve_if_missing=False, agent_model_hint="claude-opus-4-6"
    )
    assert status["agent_model"] == "gpt-5"


def test_create_client_gates_on_hint(monkeypatch):
    """The hint alone can block (cross-family) or admit (kin) a substrate."""
    monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    monkeypatch.setenv("MNEMOS_MODEL", "anthropic/claude-sonnet-4-5")

    # gpt agent vs claude substrate — family policy blocks the client.
    assert create_client(agent_model_hint="gpt-5") is None

    # claude agent vs claude substrate — kin, client comes through.
    assert create_client(agent_model_hint="claude-opus-4-6") is not None


def test_daemon_provenance_carries_hint(store):
    """The daemon threads its hint into substrate provenance."""
    daemon = ConsolidationDaemon(
        store=store,
        config={},
        llm_client=StubClient(),
        agent_model_hint="claude-opus-4-6",
    )
    stats = daemon.run_cycle(deep=False, agent_id="nova")

    assert stats["substrate"]["agent_model"] == "claude-opus-4-6"
    assert stats["substrate"]["affinity_allowed"] is True
