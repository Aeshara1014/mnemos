"""Night tidying waits and starts with the old (Tara's ruling, 2026-10-03):
a memory rests 14 days before it may be tidied, and the night's budget goes
to the oldest, then the faintest — never to what was just lived."""
from datetime import datetime, timedelta, timezone

import pytest

from mnemos.consolidation.softening import run_softening_pass
from mnemos.core.engram import EncodingContext, Engram
from mnemos.core.types import EngramKind
from mnemos.store.sqlite_store import EngramStore

AGENT = "nova"


class StubLLM:
    def __init__(self, response: str):
        self.response = response

    def complete(self, prompt: str) -> str:
        return self.response


def _engram(content: str, *, days_old: float, accessibility: float = 0.45) -> Engram:
    e = Engram(
        content=content,
        content_at_encoding=content,
        kind=EngramKind.SEMANTIC,
        impact="set",
        owner_agent_id=AGENT,
        encoding_context=EncodingContext(session_id="s1"),
    )
    e.accessibility = accessibility
    e.resolution = 1.0
    e.created_at = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
    return e


LONG = ("a long afternoon of lens work, the calibration finally held steady "
        "through every pass and i wrote down why it mattered to me")
SHORT = "a steady hand outlasts the afternoon"


@pytest.fixture()
def store(tmp_path):
    s = EngramStore(tmp_path / "rest.db")
    yield s
    s.close()


def test_a_fresh_memory_rests(store):
    """Before, a new memory (0.5, under the ~0.62 bar) was blurred its first night."""
    fresh = _engram(LONG, days_old=1)
    store.save_engram(fresh)
    stats = run_softening_pass(store, {}, StubLLM(SHORT), agent_id=AGENT)
    assert stats.get("skipped_resting") == 1
    assert store.get_engram(fresh.id).resolution == 1.0
    assert store.get_engram(fresh.id).content == LONG


def test_after_two_weeks_it_may_be_tidied(store):
    rested = _engram(LONG, days_old=15)
    store.save_engram(rested)
    stats = run_softening_pass(store, {}, StubLLM(SHORT), agent_id=AGENT)
    assert stats["engrams_softened"] == 1
    assert store.get_engram(rested.id).resolution < 1.0


def test_the_oldest_goes_first(store):
    """With room for one, the older memory is tidied, not the more reachable newer one."""
    older = _engram(LONG, days_old=200, accessibility=0.30)
    newer = _engram(LONG.replace("lens", "glass"), days_old=20, accessibility=0.45)
    store.save_engram(older)
    store.save_engram(newer)
    run_softening_pass(store, {"max_llm_calls_per_cycle": 1}, StubLLM(SHORT), agent_id=AGENT)
    assert store.get_engram(older.id).resolution < 1.0
    assert store.get_engram(newer.id).resolution == 1.0


def test_same_age_the_faintest_goes_first(store):
    born = datetime.now(timezone.utc) - timedelta(days=60)
    faint = _engram(LONG, days_old=60, accessibility=0.20)
    bright = _engram(LONG.replace("lens", "glass"), days_old=60, accessibility=0.45)
    faint.created_at = bright.created_at = born.isoformat()
    store.save_engram(faint)
    store.save_engram(bright)
    run_softening_pass(store, {"max_llm_calls_per_cycle": 1}, StubLLM(SHORT), agent_id=AGENT)
    assert store.get_engram(faint.id).resolution < 1.0
    assert store.get_engram(bright.id).resolution == 1.0
