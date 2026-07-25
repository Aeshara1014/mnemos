"""The fade gate: honest fading is consulted, not interrupted.

The keeper's ruling (2026-07-24): she is consulted before a memory
fades, and consolidation must not stop to ask. With dormancy_review set,
a memory reaching the dormancy line is HELD AT THE GATE — still active,
still recallable, tagged `fade-proposed` for the review desk — and the
cycle walks on. Without the flag, dormancy behaves exactly as before
(pinned in test_decay_clock.py). A person decides what sleeps.
"""

from datetime import datetime, timedelta, timezone

import pytest

from mnemos.core.engram import Engram, EncodingContext
from mnemos.core.types import EngramKind
from mnemos.consolidation.decay import run_decay_pass
from mnemos.store.sqlite_store import EngramStore

AGENT = "default"
REVIEW = {"decay_elapsed_hours": 24.0, "dormancy_review": True}


def _ago(**kw) -> str:
    return (datetime.now(timezone.utc) - timedelta(**kw)).isoformat()


def _sinking_engram(store, accessibility=0.06):
    e = Engram(
        content="a quiet thought fading on its own time",
        content_at_encoding="a quiet thought fading on its own time",
        kind=EngramKind.SEMANTIC,
        impact="a pin for the gate",
        owner_agent_id=AGENT,
        encoding_context=EncodingContext(session_id="gate-s1"),
    )
    e.accessibility = accessibility
    e.stability = 0.0
    e.strength = 0.5
    e.last_accessed = _ago(days=90)
    store.save_engram(e)
    return e.id


@pytest.fixture()
def gate_store(tmp_path):
    s = EngramStore(tmp_path / "gate.db")
    yield s
    s.close()


def test_the_gate_holds_a_fading_memory(gate_store):
    """Crossing the dormancy line under review: held at the gate —
    active, at the threshold, tagged for the desk — never put under."""
    eid = _sinking_engram(gate_store)
    stats = run_decay_pass(gate_store, REVIEW, agent_id=AGENT)
    e = gate_store.get_engram(eid)
    assert e.state == "active"
    assert e.accessibility == pytest.approx(0.05, abs=1e-9)
    assert "fade-proposed" in e.tags
    assert stats["fade_proposals"] == 1
    assert stats["at_fade_gate"] == 1
    assert stats["engrams_dormant"] == 0


def test_the_gate_proposes_once(gate_store):
    """Later cycles find the tag and just hold the memory here — the
    desk is never spammed with the same proposal."""
    eid = _sinking_engram(gate_store)
    run_decay_pass(gate_store, REVIEW, agent_id=AGENT)
    stats = run_decay_pass(gate_store, REVIEW, agent_id=AGENT)
    e = gate_store.get_engram(eid)
    assert e.tags.count("fade-proposed") == 1
    assert stats["fade_proposals"] == 0
    assert stats["at_fade_gate"] == 1


def test_nothing_slides_past_the_gate_to_archive(gate_store):
    """A big capped span could carry a weak memory straight through the
    dormancy band into archive territory — the gate catches it first.
    Nothing leaves the store while it waits for a word."""
    eid = _sinking_engram(gate_store, accessibility=0.012)
    gate_store.set_meta(f"last_decay_at:{AGENT}", _ago(days=30))
    stats = run_decay_pass(gate_store, {"dormancy_review": True}, agent_id=AGENT)
    e = gate_store.get_engram(eid)
    assert e is not None
    assert e.state == "active"
    assert e.accessibility == pytest.approx(0.05, abs=1e-9)
    assert "fade-proposed" in e.tags
    assert stats["engrams_archived"] == 0
