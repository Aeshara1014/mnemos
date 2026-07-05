"""Regression: get_recent_engrams called a method that never existed.

sqlite_store.get_recent_engrams built rows with self._row_to_engram(), which
no store has ever defined — every other path uses Engram.from_dict(). Its only
data-bearing caller is belief_review, which only proceeds when active beliefs
exist... and no store ever held organic beliefs until the formation pass made
some. The newborns crashed the reviewer just by existing.
"""
from datetime import datetime, timedelta, timezone

from mnemos.consolidation.belief_review import run_belief_review
from mnemos.core.belief import Belief
from mnemos.core.engram import Engram


def test_get_recent_engrams_returns_engram_objects(store):
    for content in ("first lived thing", "second lived thing"):
        store.save_engram(Engram(content=content))

    recent = store.get_recent_engrams(
        agent_id="default",
        since=datetime.now(timezone.utc) - timedelta(days=1),
        limit=10,
    )

    assert len(recent) == 2
    assert all(isinstance(e, Engram) for e in recent)
    assert {e.content for e in recent} == {"first lived thing", "second lived thing"}


def test_belief_review_survives_real_beliefs(store, stub_llm):
    """The exact crash from the first fully-local heartbeat (2026-07-05)."""
    store.save_belief(Belief(content="The west fog comes nightly.", confidence=0.5))
    store.save_engram(Engram(content="Clear sky tonight, and still the fog came."))

    stats = run_belief_review(store, llm_client=stub_llm, agent_id="default")

    assert "memories_reviewed" in stats  # returned normally — no AttributeError
