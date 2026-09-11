"""Tests for turnkey context packets and visual snapshots."""

from mnemos.interface.context_packet import build_context_packet
from mnemos.interface.visual_snapshot import build_memory_visual_snapshot


def test_context_packet_orders_memory_layers(store):
    session = store.start_memory_session(
        session_id="ctx-session",
        agent_id="vektor",
        person_id="riley",
        project_scope="mnemos",
        title="Context packet test",
    )
    store.write_functional_memory(
        "Current task is building the turnkey single-agent memory system.",
        session_id=session["id"],
        agent_id="vektor",
        person_id="riley",
        project_scope="mnemos",
        memory_type="working",
        confidence=0.9,
        salience=0.9,
    )
    store.write_hypomnema_entry(
        "Hypomnema carries scoped continuity before promotion into Mnemos.",
        agent_id="vektor",
        person_id="riley",
        project_scope="mnemos",
        confidence=0.88,
        salience=0.75,
        foundational=True,
    )

    packet = build_context_packet(
        store,
        "turnkey memory system",
        agent_id="vektor",
        person_id="riley",
        project_scope="mnemos",
        session_id="ctx-session",
    )

    prompt = packet["prompt"]
    assert "### Functional Memory" in prompt
    assert "### Hypomnema" in prompt
    assert "### Mnemos Graph" in prompt
    assert "turnkey single-agent memory system" in prompt
    assert "scoped continuity" in prompt


def test_visual_snapshot_returns_mermaid(store):
    store.write_functional_memory(
        "A visible memory map should be renderable inline.",
        agent_id="vektor",
        person_id="riley",
        project_scope="mnemos",
    )

    snapshot = build_memory_visual_snapshot(
        store,
        agent_id="vektor",
        person_id="riley",
        project_scope="mnemos",
    )

    assert "```mermaid" in snapshot
    assert "Functional memory" in snapshot
    assert "Hypomnema" in snapshot


def _spy_retriever(monkeypatch, captured):
    """Replace ReactiveRetriever with a subclass that records its index arg."""
    import mnemos.interface.context_packet as cp

    base = cp.ReactiveRetriever

    class Spy(base):
        def __init__(self, store, embedding_index=None, **kwargs):
            captured.append(embedding_index)
            super().__init__(store, embedding_index=embedding_index, **kwargs)

    monkeypatch.setattr(cp, "ReactiveRetriever", Spy)


def test_embedding_index_threads_to_retriever(store, monkeypatch):
    """item 9: build_context_packet forwards embedding_index to the retriever.

    Before this, the retriever was built with no index, so semantic (embedding)
    recall was unreachable and chat recall was FTS-only.
    """
    captured: list = []
    _spy_retriever(monkeypatch, captured)

    sentinel = object()
    build_context_packet(store, "a real query", agent_id="vektor", embedding_index=sentinel)
    assert captured == [sentinel]


def test_embedding_index_defaults_to_none(store, monkeypatch):
    """Omitting the arg preserves the prior FTS-only behavior."""
    captured: list = []
    _spy_retriever(monkeypatch, captured)

    build_context_packet(store, "a real query", agent_id="vektor")
    assert captured == [None]


# ── stone 3 (the Lighthouse, 2026-09-11): a read that is not a rehearsal ──

def _touch_counts(store, agent_id="vektor"):
    conn = store._get_conn()
    return conn.execute(
        "SELECT access_count, strength, reconsolidation_count FROM engrams "
        "WHERE owner_agent_id = ? ORDER BY id", (agent_id,)).fetchall()


def test_an_unbidden_packet_leaves_no_fingerprint_and_a_deliberate_one_does(store):
    from mnemos.core.engram import Engram, MemorySource
    e = Engram(content="the lighthouse keeps a quiet flame for Tara",
               content_at_encoding="the lighthouse keeps a quiet flame for Tara",
               owner_agent_id="vektor",
               source=MemorySource(type="session", confidence=0.9))
    e.strength = 0.5
    store.save_engram(e)
    before = _touch_counts(store)

    for _ in range(20):
        packet = build_context_packet(store, "quiet flame lighthouse", agent_id="vektor",
                                      reconsolidate=False)
    assert packet["mnemos_engrams"], "the memory was still retrieved"
    assert _touch_counts(store) == before          # twenty reads, nothing touched

    build_context_packet(store, "quiet flame lighthouse", agent_id="vektor")  # the default: a rehearsal
    after = _touch_counts(store)
    assert after[0]["access_count"] == before[0]["access_count"] + 1
    assert after[0]["reconsolidation_count"] == before[0]["reconsolidation_count"] + 1
    assert after[0]["strength"] > before[0]["strength"]
