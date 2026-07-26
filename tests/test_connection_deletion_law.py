"""The deletion law (SWEEP-B 2026-07-25, laws 3 and 9).

An edge between two memories is removed ONLY on the model's explicit,
confident word that there is no relation. Silence never deletes: a
failed call, a truncated reply, an unmentioned target, and an honest
low-confidence answer all DEFER the edge — counted, never destroyed.

Before this law, all four of those were read as "the model said NONE",
and connection reclassification did the most deleting on exactly the
nights the substrate was least able to answer. What died was lived
history — which memories were retrieved together — and every deletion
was silent, unlogged, and unrecoverable.
"""

import json

import pytest

from mnemos.core.engram import Connection, EncodingContext, Engram
from mnemos.core.types import ConnectionRelation, EngramKind
from mnemos.consolidation.connection_discovery import _reclassify_old_connections
from mnemos.store.sqlite_store import EngramStore

AGENT = "default"


class FakeClient:
    """structured_complete returns queued replies, or raises."""

    def __init__(self, replies=None, error=None):
        self.replies = list(replies or [])
        self.error = error
        self.calls = 0

    def structured_complete(self, **kwargs):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.replies.pop(0)


def _engram(store, content):
    e = Engram(
        content=content,
        content_at_encoding=content,
        kind=EngramKind.SEMANTIC,
        impact="a pin",
        owner_agent_id=AGENT,
        encoding_context=EncodingContext(session_id="law-s1"),
    )
    store.save_engram(e)
    return e


def _edge(store, source, target, relation="co_activated",
          formed_by="co_activation", strength=0.3):
    store.save_connection(source.id, Connection(
        target_id=target.id,
        relation=relation,
        strength=strength,
        formed_at="2026-07-01T00:00:00+00:00",
        formed_by=formed_by,
    ))


def _stats():
    return {
        "connections_reclassified": 0,
        "connections_removed": 0,
        "reclassify_call_failures": 0,
        "reclassify_deferred": 0,
    }


def _verdict(cid, relation, confidence, reasoning="because"):
    return {"candidate_id": cid, "relation": relation,
            "confidence": confidence, "reasoning": reasoning}


@pytest.fixture()
def store(tmp_path):
    s = EngramStore(tmp_path / "law.db")
    yield s
    s.close()


def test_a_failed_call_deletes_nothing(store):
    """The call died. Not one edge may be touched on its account."""
    a = _engram(store, "the source memory")
    b = _engram(store, "the target memory")
    _edge(store, a, b)
    stats = _stats()
    client = FakeClient(error=RuntimeError("substrate down"))
    _reclassify_old_connections(store, client, [a], batch_size=10, stats=stats)
    assert [c.target_id for c in store.get_connections(a.id)] == [b.id]
    assert stats["connections_removed"] == 0
    assert stats["reclassify_call_failures"] == 1


def test_silence_never_deletes(store):
    """Two edges sent, one mentioned. The unmentioned one survives —
    absence is a truncated tail or a model skip, never a verdict."""
    a = _engram(store, "the source memory")
    b = _engram(store, "mentioned target")
    c = _engram(store, "forgotten target")
    _edge(store, a, b)
    _edge(store, a, c)
    reply = json.dumps([_verdict(b.id, "EXTENDS", 0.9)])
    stats = _stats()
    _reclassify_old_connections(store, FakeClient([reply]), [a],
                                batch_size=10, stats=stats)
    remaining = {x.target_id: x for x in store.get_connections(a.id)}
    assert c.id in remaining                       # silence deferred it
    assert remaining[c.id].relation == "co_activated"
    assert remaining[b.id].relation == "extends"   # the verdict landed
    assert stats["connections_removed"] == 0
    assert stats["reclassify_deferred"] == 1


def test_an_honest_maybe_defers_instead_of_deleting(store):
    """The dominant healthy-night trigger: a verdict below the
    confidence line used to be filtered out before the caller saw it,
    and the resulting absence deleted the edge. It defers now."""
    a = _engram(store, "the source memory")
    b = _engram(store, "uncertain target")
    _edge(store, a, b)
    reply = json.dumps([_verdict(b.id, "PARALLELS", 0.45)])
    stats = _stats()
    _reclassify_old_connections(store, FakeClient([reply]), [a],
                                batch_size=10, stats=stats)
    kept = store.get_connections(a.id)
    assert len(kept) == 1 and kept[0].relation == "co_activated"
    assert stats["connections_removed"] == 0
    assert stats["reclassify_deferred"] == 1


def test_only_a_confident_none_removes(store):
    """The one word that deletes: an explicit NONE at or above the
    confidence line. A hesitant NONE defers like everything else."""
    a = _engram(store, "the source memory")
    b = _engram(store, "truly unrelated")
    c = _engram(store, "possibly unrelated")
    _edge(store, a, b)
    _edge(store, a, c)
    reply = json.dumps([
        _verdict(b.id, "NONE", 0.9),
        _verdict(c.id, "NONE", 0.3),
    ])
    stats = _stats()
    _reclassify_old_connections(store, FakeClient([reply]), [a],
                                batch_size=10, stats=stats)
    remaining = [x.target_id for x in store.get_connections(a.id)]
    assert b.id not in remaining                   # confident NONE removed
    assert c.id in remaining                       # hesitant NONE deferred
    assert stats["connections_removed"] == 1
    assert stats["reclassify_deferred"] == 1


def test_a_truncated_reply_salvages_the_whole_verdicts(store):
    """A reply cut mid-array keeps its complete verdicts and loses only
    the tail — before, the entire batch was discarded and every absence
    read as NONE (599 such replies on the road)."""
    a = _engram(store, "the source memory")
    b = _engram(store, "judged before the cut")
    c = _engram(store, "lost to the cut")
    _edge(store, a, b)
    _edge(store, a, c)
    whole = json.dumps(_verdict(b.id, "GROUNDS", 0.8))
    truncated = f'[{whole}, {{"candidate_id": "{c.id}", "rel'
    stats = _stats()
    _reclassify_old_connections(store, FakeClient([truncated]), [a],
                                batch_size=10, stats=stats)
    remaining = {x.target_id: x for x in store.get_connections(a.id)}
    assert remaining[b.id].relation == "grounds"   # salvaged and applied
    assert remaining[c.id].relation == "co_activated"  # deferred, alive
    assert stats["connections_removed"] == 0
    assert stats["reclassify_deferred"] == 1


def test_reclassification_replaces_the_row_instead_of_stacking(store):
    """The PK is (source, target, relation): a bare save ADDED the new
    relation beside the stale mechanical row, which then came back for
    review every night forever. Remove-then-write converges."""
    a = _engram(store, "the source memory")
    b = _engram(store, "the target memory")
    _edge(store, a, b)
    reply = json.dumps([_verdict(b.id, "EXTENDS", 0.9)])
    _reclassify_old_connections(store, FakeClient([reply]), [a],
                                batch_size=10, stats=_stats())
    rows = store.get_connections(a.id)
    assert len(rows) == 1                          # replaced, not stacked
    assert rows[0].relation == "extends"
    assert rows[0].formed_by == "consolidation_reclassified"


def test_an_earned_edge_is_never_resent(store):
    """An edge already judged by the substrate — the encoder's mint or a
    previous successful reclassification — stays judged. It used to be
    re-sent every deep cycle, each one a fresh chance to lose it."""
    a = _engram(store, "the source memory")
    b = _engram(store, "the settled target")
    _edge(store, a, b, relation="supports", formed_by="consolidation_reclassified")
    client = FakeClient([json.dumps([])])
    _reclassify_old_connections(store, client, [a], batch_size=10, stats=_stats())
    assert client.calls == 0                       # nothing to ask


def test_a_confident_none_spares_the_semantic_twin(store):
    """One pair, two rows: the stale mechanical edge and a semantic edge
    an earlier night earned. Removing the mechanical one used to kill
    both (the delete was pair-wide). It is relation-scoped now."""
    a = _engram(store, "the source memory")
    b = _engram(store, "the twin-edged target")
    _edge(store, a, b, relation="co_activated", formed_by="co_activation")
    _edge(store, a, b, relation="extends", formed_by="consolidation_reclassified")
    reply = json.dumps([_verdict(b.id, "NONE", 0.9)])
    stats = _stats()
    _reclassify_old_connections(store, FakeClient([reply]), [a],
                                batch_size=10, stats=stats)
    rows = store.get_connections(a.id)
    assert len(rows) == 1
    assert rows[0].relation == "extends"           # the earned edge lives
    assert stats["connections_removed"] == 1


def test_the_budget_counts_calls_not_victories(store):
    """batch_size caps LLM CALLS. Counting only successes meant a
    failing substrate never tripped the cap — the pass made the most
    calls and the most deletions exactly when the model was down."""
    engrams = []
    for i in range(3):
        e = _engram(store, f"source {i}")
        t = _engram(store, f"target {i}")
        _edge(store, e, t)
        engrams.append(e)
    stats = _stats()
    client = FakeClient(error=RuntimeError("substrate down"))
    _reclassify_old_connections(store, client, engrams,
                                batch_size=2, stats=stats)
    assert client.calls == 2                       # the cap held
    assert stats["reclassify_call_failures"] == 2
