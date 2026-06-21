"""Tests for the introspection self-audit engine and its substrate pass.

The engine scores text for "performed/groove" vs "genuine/reaching" markers;
the substrate pass audits recent outputs and encodes findings as engrams. The
whole feature is opt-in (off by default).
"""
from mnemos.advanced.introspection import introspect, IntrospectionReport
from mnemos.substrate.config import SubstrateConfig


def test_introspect_returns_report():
    text = ("I keep circling the same question and I'm genuinely not sure I have "
            "an answer. Maybe it's that the thing resists naming — every time I "
            "reach for it, it slides away. I don't know. Let me try anyway.")
    rep = introspect(text)
    assert isinstance(rep, IntrospectionReport)
    assert 0.0 <= rep.overall_pattern_score <= 1.0
    assert 0.0 <= rep.overall_reaching_score <= 1.0
    assert rep.assessment  # non-empty assessment string


def test_introspect_empty_text_is_safe():
    rep = introspect("")
    assert isinstance(rep, IntrospectionReport)
    assert rep.assessment  # returns a scaffold, never crashes


def test_config_introspection_off_by_default():
    assert SubstrateConfig().introspection_enabled is False


def test_config_env_toggle(monkeypatch):
    monkeypatch.delenv("MNEMOS_INTROSPECTION", raising=False)
    assert SubstrateConfig.from_env().introspection_enabled is False
    monkeypatch.setenv("MNEMOS_INTROSPECTION", "1")
    assert SubstrateConfig.from_env().introspection_enabled is True


def test_pass_is_gated_when_disabled():
    from mnemos.substrate.introspection_pass import run_introspection_pass
    cfg = SubstrateConfig(introspection_enabled=False)
    out = run_introspection_pass(cfg, store=None, llm_client=None)
    assert out.get("skipped") is True


def test_encode_audit_writes_private_introspection_engram(tmp_path):
    from mnemos.store.sqlite_store import EngramStore
    from mnemos.substrate.introspection_pass import _audit_with_heuristics, _encode_audit
    store = EngramStore(str(tmp_path / "t.db"))
    try:
        cfg = SubstrateConfig(agent_id="tester", introspection_enabled=True)
        audit = _audit_with_heuristics(
            "A reasonably long reflective passage that should produce a heuristic "
            "audit with pattern and reaching scores. It has several sentences. "
            "I wonder whether any of this is genuine or just the usual grooves."
        )
        assert audit is not None and audit["mode"] == "heuristic"
        _encode_audit(audit, cfg, store)
        conn = store._get_conn()
        row = conn.execute(
            "SELECT tags, source, owner_agent_id FROM engrams "
            "WHERE content LIKE '%[introspection]%'"
        ).fetchone()
        assert row is not None                      # the engram was actually written
        assert "introspection" in row[0]            # tags include the marker
        assert '"type": "reflection"' in row[1]     # source object carries type=reflection (private)
        assert row[2] == "tester"                   # owned by the configured agent
    finally:
        store.close()


def test_to_summary_is_readable():
    rep = introspect("A few sentences here. I am reaching for something real. "
                     "Maybe it works, maybe it does not.")
    s = rep.to_summary()
    assert "Pattern:" in s and "Assessment:" in s


def test_introspect_mcp_tool_registered():
    import asyncio
    from mnemos.mcp_server import mcp
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert "mnemos_introspect" in names
