"""The cycle's clock: one decay pass spends one span of lived time.

Regression pins for the day-43 hold (2026-07-24, the reintegration walk):
decay read the REAL hours since each memory was last touched and re-applied
them every cycle — the quantity never resets, so forgetting compounded
quadratically, and seven replay dreams in one morning aged a whole store by
weeks. Six engrams went dormant and the zero-tolerance gauge held the road.

The law now: a pass ages memories by ONE span — declared by the caller
(decay_elapsed_hours, the walk's walked-day clock) or measured from the
store's own last-decay stamp — and no engram absorbs more than its own
time-since-access within that span.
"""

from datetime import datetime, timedelta, timezone

import pytest

from mnemos.core.engram import Engram, EncodingContext
from mnemos.core.types import EngramKind
from mnemos.consolidation.decay import run_decay_pass
from mnemos.store.sqlite_store import EngramStore

AGENT = "default"


def _ago(**kw) -> str:
    return (datetime.now(timezone.utc) - timedelta(**kw)).isoformat()


def _engram(store, *, accessibility=1.0, stability=0.0, last_accessed=None,
            content="a durable thing learned on the road"):
    e = Engram(
        content=content,
        content_at_encoding=content,
        kind=EngramKind.SEMANTIC,
        impact="a pin for the clock",
        owner_agent_id=AGENT,
        encoding_context=EncodingContext(session_id="clock-s1"),
    )
    e.accessibility = accessibility
    e.stability = stability
    e.strength = 0.5
    if last_accessed is not None:
        e.last_accessed = last_accessed
    store.save_engram(e)
    return e.id


def _accessibility(store, engram_id):
    row = store.get_engram(engram_id)
    return row.accessibility


@pytest.fixture()
def clock_store(tmp_path):
    s = EngramStore(tmp_path / "clock.db")
    yield s
    s.close()


def test_a_declared_span_shields_an_old_clock(clock_store):
    """The walk's shield: a memory last touched 90 real days ago ages by
    the DECLARED 24 hours, not by 2160 — a March memory walking a May day
    does not absorb the whole real gap in one dream."""
    eid = _engram(clock_store, last_accessed=_ago(days=90))
    run_decay_pass(clock_store, {"decay_elapsed_hours": 24.0}, agent_id=AGENT)
    # stability 0, no connections: exp(-0.01 * 24) = 0.7866
    assert _accessibility(clock_store, eid) == pytest.approx(0.7866, abs=1e-3)


def test_rapid_refires_no_longer_compound(clock_store):
    """THE day-43 pin: cycles minutes apart must not each re-apply the
    full elapsed decay. The first measured pass spends its span; a second
    immediate pass finds a fresh stamp and spends ~nothing."""
    eid = _engram(clock_store, last_accessed=_ago(days=90))
    run_decay_pass(clock_store, {}, agent_id=AGENT)
    after_first = _accessibility(clock_store, eid)
    run_decay_pass(clock_store, {}, agent_id=AGENT)
    after_second = _accessibility(clock_store, eid)
    assert after_first < 1.0  # the first pass really decayed
    assert after_second == pytest.approx(after_first, abs=2e-3)


def test_the_stamp_measures_real_absence(clock_store):
    """Between measured passes, the span is the real gap since the LAST
    PASS — not since each memory's last access."""
    eid = _engram(clock_store, last_accessed=_ago(days=90))
    clock_store.set_meta(f"last_decay_at:{AGENT}", _ago(hours=48))
    run_decay_pass(clock_store, {}, agent_id=AGENT)
    # exp(-0.01 * 48) = 0.6188
    assert _accessibility(clock_store, eid) == pytest.approx(0.6188, abs=1e-3)


def test_a_long_outage_is_capped_at_a_week(clock_store):
    """A machine dark for a month decays as at most a week away — waking
    is never a butchery."""
    eid = _engram(clock_store, last_accessed=_ago(days=90))
    clock_store.set_meta(f"last_decay_at:{AGENT}", _ago(days=30))
    run_decay_pass(clock_store, {}, agent_id=AGENT)
    # capped: exp(-0.01 * 168) = 0.1864, nothing like exp(-0.01 * 720)
    assert _accessibility(clock_store, eid) == pytest.approx(0.1864, abs=1e-3)


def test_a_memory_touched_mid_span_only_ages_from_that_moment(clock_store):
    """No engram absorbs more than its own time-since-access in one pass:
    a memory touched 2 hours ago ages 2 hours, whatever the cycle span.
    This is what keeps a walked day's own arrivals present at the gauges."""
    eid = _engram(clock_store, last_accessed=_ago(hours=2))
    run_decay_pass(clock_store, {"decay_elapsed_hours": 24.0}, agent_id=AGENT)
    # exp(-0.01 * 2) = 0.9802 (recency floor 0.4 far below — untouched)
    assert _accessibility(clock_store, eid) == pytest.approx(0.9802, abs=1e-3)


def test_the_recency_floor_reads_the_full_clock(clock_store):
    """The 72-hour recency floor keys on time since ACCESS, not the cycle
    span: a memory touched 30 hours ago cannot decay below 0.4."""
    eid = _engram(clock_store, accessibility=0.41, last_accessed=_ago(hours=30))
    run_decay_pass(clock_store, {"decay_elapsed_hours": 24.0}, agent_id=AGENT)
    assert _accessibility(clock_store, eid) == pytest.approx(0.4, abs=1e-4)


def test_the_dormancy_gate_still_stands(clock_store):
    """The fix narrows the clock, never the gate: an engram that truly
    sinks below the threshold still goes dormant."""
    eid = _engram(clock_store, accessibility=0.06, last_accessed=_ago(days=90))
    stats = run_decay_pass(
        clock_store, {"decay_elapsed_hours": 24.0}, agent_id=AGENT
    )
    assert stats["engrams_dormant"] == 1
    assert clock_store.get_engram(eid).state == "dormant"


def test_the_books_record_the_span(clock_store):
    """Every pass writes what span it spent, and stamps the store so the
    next measured pass starts from here — in declared-span mode too."""
    _engram(clock_store, last_accessed=_ago(days=90))
    stats = run_decay_pass(
        clock_store, {"decay_elapsed_hours": 24.0}, agent_id=AGENT
    )
    assert stats["cycle_span_hours"] == 24.0
    assert clock_store.get_meta(f"last_decay_at:{AGENT}") is not None


def test_the_recency_floor_is_a_knob(clock_store):
    """recency_floor_hours (the Lighthouse's stone 3, 2026-09-11): the
    house may hold a memory easy to reach for two weeks, not three days.
    Ten days since access: under the engine's 72h default it sinks; under
    a 336h floor it cannot fall below 0.4."""
    sinks = _engram(clock_store, accessibility=0.41, last_accessed=_ago(days=10))
    run_decay_pass(clock_store, {"decay_elapsed_hours": 24.0}, agent_id=AGENT)
    assert _accessibility(clock_store, sinks) < 0.4

    held = _engram(clock_store, accessibility=0.41, last_accessed=_ago(days=10))
    run_decay_pass(clock_store, {"decay_elapsed_hours": 24.0, "recency_floor_hours": 336},
                   agent_id=AGENT)
    assert _accessibility(clock_store, held) == pytest.approx(0.4, abs=1e-4)
