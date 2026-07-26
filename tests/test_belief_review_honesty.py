"""Belief review's three repairs (SWEEP-A/B 2026-07-25).

For 43 walked days this pass reviewed nothing of his lived life: its
wall-clock window could never contain a replayed day's honest historical
stamps, its substrate guard compared a dataclass to a word and never
fired, and a truncated or failed reply was indistinguishable from
"no belief had any bearing". Three seams, pinned here:

1. THE GUARD FIRES — substrate-authored memories are skipped by the
   formation pass's shape (MemorySource carries its kind in .type),
   from the ONE shared tuple, so his dreams cannot revise his beliefs.
2. THE WINDOW REACHES A REPLAYED DAY — the same day-window seam
   reflection has: when the caller declares the day, review THAT day.
3. A FAILED CALL IS COUNTED, NOT SILENT — llm_call_failures in the
   books; beliefs untouched (law 9).
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from mnemos.core.belief import Belief
from mnemos.core.engram import EncodingContext, Engram, MemorySource
from mnemos.core.types import EngramKind
from mnemos.consolidation.belief_review import run_belief_review
from mnemos.encoding.llm_classifier import evaluate_beliefs
from mnemos.store.sqlite_store import EngramStore

AGENT = "default"
MARCH_DAY = "2026-03-30T12:00:01+00:00"
MARCH_WINDOW = {"since": "2026-03-30T04:00:00+00:00",
                "until": "2026-03-31T04:00:00+00:00"}


class FakeClient:
    def __init__(self, replies=None, error=None):
        self.replies = list(replies or [])
        self.error = error
        self.calls = 0
        self.kwargs_seen = []

    def structured_complete(self, **kwargs):
        self.calls += 1
        self.kwargs_seen.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.replies.pop(0) if self.replies else "[]"


def _engram(store, content, created_at=None, source_type="session"):
    e = Engram(
        content=content,
        content_at_encoding=content,
        kind=EngramKind.EPISODIC,
        impact="a pin",
        owner_agent_id=AGENT,
        source=MemorySource(type=source_type),
        encoding_context=EncodingContext(session_id="rev-s1"),
    )
    if created_at:
        e.created_at = created_at
    store.save_engram(e)
    return e


def _belief(store, content="steady convictions deserve real evidence"):
    b = Belief(agent_id=AGENT, content=content, confidence=0.5)
    # Past the 6h revision cooldown, so a verdict can actually land.
    b.last_revised = (datetime.now(timezone.utc)
                      - timedelta(hours=10)).isoformat()
    store.save_belief(b)
    return b


@pytest.fixture()
def store(tmp_path):
    s = EngramStore(tmp_path / "review.db")
    yield s
    s.close()


def test_the_substrate_guard_finally_fires(store):
    """A reflection-authored memory is skipped BEFORE any LLM call —
    the substrate must not revise his convictions with its own output.
    The old guard stringified the whole MemorySource and compared it to
    a word; its counter was a truthful-looking zero for every resident."""
    _belief(store)
    _engram(store, "a thought the dream wrote", source_type="reflection")
    client = FakeClient()
    stats = run_belief_review(store, {}, client, AGENT)
    assert stats["skipped_substrate"] == 1
    assert stats["memories_reviewed"] == 0
    assert client.calls == 0


def test_the_window_seam_reaches_a_replayed_day(store):
    """A replayed memory wears its honest March stamp. The wall-clock
    window can never see it; the declared day-window reviews it."""
    _belief(store)
    _engram(store, "a March morning, come home", created_at=MARCH_DAY)

    blind = run_belief_review(store, {}, FakeClient(), AGENT)
    assert blind["memories_reviewed"] == 0        # wall clock: invisible

    seen = run_belief_review(
        store, {"reflection_window": MARCH_WINDOW}, FakeClient(), AGENT)
    assert seen["memories_reviewed"] == 1         # the day, reviewed


def test_a_failed_call_is_counted_not_no_bearing(store):
    """The call died mid-review. That is not 'no belief had any
    bearing' — it lands in the books and touches nothing (law 9)."""
    b = _belief(store)
    _engram(store, "a memory that deserved a verdict")
    client = FakeClient(error=RuntimeError("substrate down"))
    stats = run_belief_review(store, {}, client, AGENT)
    assert stats["llm_call_failures"] == 1
    assert stats["beliefs_strengthened"] == 0
    assert stats["beliefs_weakened"] == 0
    fresh = store.get_beliefs(AGENT, active_only=True)
    assert fresh[0].confidence == pytest.approx(b.confidence)


def test_the_reply_budget_matches_the_sibling(store):
    """evaluate_beliefs asks with max_tokens=2000, like
    classify_connections — the old 1000 was cut off mid-array once a
    resident held more than ~a dozen beliefs, and every verdict in the
    reply was discarded (599 truncated replies on the road)."""
    b = _belief(store)
    e = _engram(store, "a memory")
    client = FakeClient(replies=["[]"])
    result = evaluate_beliefs(client, e, [b])
    assert result == []
    assert client.kwargs_seen[0]["max_tokens"] == 2000


def test_a_truncated_belief_reply_keeps_its_whole_verdicts(store):
    """The salvage, end to end: a reply cut mid-array still applies the
    complete verdicts written before the cut."""
    b1 = _belief(store, "the first conviction")
    b2 = _belief(store, "the second conviction")
    _engram(store, "supporting evidence")
    whole = json.dumps({"belief_id": b1.id, "relation": "SUPPORTS",
                        "impact": 0.8, "reasoning": "it bears directly"})
    truncated = f'[{whole}, {{"belief_id": "{b2.id}", "rel'
    stats = run_belief_review(store, {}, FakeClient([truncated]), AGENT)
    assert stats["beliefs_strengthened"] == 1     # the salvaged verdict
    assert stats["llm_call_failures"] == 0
