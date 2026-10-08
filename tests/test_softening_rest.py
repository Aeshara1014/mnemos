"""Night tidying waits (Tara's ruling, 2026-10-03): a memory rests 14 days
before the night may even count it as faint. Since 2026-10-07 the night
rewrites nothing (fading keeps his words), so there is no budget to spend
and no order to spend it in; the rest still holds for what is counted."""
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


def test_after_two_weeks_it_is_counted_faint_and_kept_whole(store):
    rested = _engram(LONG, days_old=15)
    store.save_engram(rested)
    stats = run_softening_pass(store, {}, StubLLM(SHORT), agent_id=AGENT)
    assert stats["engrams_faint"] == 1
    assert stats["engrams_softened"] == 0
    kept = store.get_engram(rested.id)
    assert kept.content == LONG and kept.resolution == 1.0
