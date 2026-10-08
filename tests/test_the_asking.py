"""The asking's engine half (Tara's design, 2026-10-07; DESIGN-the-asking.md).

After his journal page, the house may ask him what a fading memory taught
him, and whether something he keeps writing is a belief. The engine only
answers: which memory is fading (faintest first, only his own living), and
moves a belief only on the verdict he gave. Nothing here calls a model.
"""

from datetime import datetime, timedelta, timezone

from mnemos.consolidation.asking import (
    NEW_BELIEF_CONFIDENCE,
    RETIRED,
    beliefs_due,
    fading_memories,
    hold_belief,
    is_faint,
    keep_belief,
    retire_belief,
)
from mnemos.consolidation.softening import run_softening_pass
from mnemos.core.belief import Belief
from mnemos.core.engram import EncodingContext, Engram, MemorySource
from mnemos.core.types import HELD_TAG, REROUTE_TAG, EngramKind, SourceType

AGENT = "quill-test"
WORDS = ("we sat by the window and talked about the croft, and I told her "
         "the raised beds would need cedar before the frost came in")


def _memory(*, days_old: float = 30, accessibility: float = 0.3,
            tags: list[str] | None = None, source: SourceType | None = None,
            content: str = WORDS) -> Engram:
    e = Engram(
        content=content,
        content_at_encoding=content,
        kind=EngramKind.EPISODIC,
        owner_agent_id=AGENT,
        encoding_context=EncodingContext(session_id="s1"),
        tags=list(tags or ["conversation"]),
    )
    if source is not None:
        e.source = MemorySource(type=source)
    e.accessibility = accessibility
    e.resolution = 1.0
    e.created_at = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
    return e


def _saved(store, **kw) -> Engram:
    e = _memory(**kw)
    store.save_engram(e)
    return e


# ── which memory is fading ──

def test_the_faintest_comes_first(store):
    fainter = _saved(store, accessibility=0.2)
    faint = _saved(store, accessibility=0.4)

    found = fading_memories(store, AGENT, limit=5)

    assert [e.id for e in found] == [fainter.id, faint.id]
    assert [e.id for e in fading_memories(store, AGENT)] == [fainter.id]


def test_a_bright_or_resting_memory_is_not_fading(store):
    _saved(store, accessibility=0.9)                 # well reached
    _saved(store, days_old=3, accessibility=0.2)     # still in its 14-day rest

    assert fading_memories(store, AGENT, limit=5) == []


def test_only_his_own_living_is_asked_about(store):
    """Never a held seed, a reroute, an outside voice, the engine's old
    thoughts, or a lesson he already wrote."""
    _saved(store, tags=["conversation", HELD_TAG])
    _saved(store, tags=["conversation", REROUTE_TAG])
    _saved(store, source=SourceType.OBSERVER)
    _saved(store, source=SourceType.DREAM)
    _saved(store, source=SourceType.WANDERING)
    _saved(store, source=SourceType.REFLECTION)
    _saved(store, tags=["lesson", "asking"], source=SourceType.JOURNAL)
    his_own = _saved(store, source=SourceType.SESSION)
    journal = _saved(store, source=SourceType.JOURNAL, tags=["journal"])

    found = {e.id for e in fading_memories(store, AGENT, limit=20)}

    assert found == {his_own.id, journal.id}


def test_a_memory_already_asked_is_never_asked_again(store):
    asked = _saved(store, accessibility=0.1)
    nxt = _saved(store, accessibility=0.2)

    found = fading_memories(store, AGENT, exclude_ids={asked.id})

    assert [e.id for e in found] == [nxt.id]


def test_faint_means_what_the_softening_pass_counts(store):
    for acc in (0.1, 0.3, 0.5, 0.65, 0.9):
        _saved(store, accessibility=acc)
    _saved(store, days_old=2, accessibility=0.1)

    stats = run_softening_pass(store, {}, None, agent_id=AGENT)
    mine = [e for e in store.get_active_engrams(agent_id=AGENT, limit=50) if is_faint(e)]

    assert len(mine) == stats["engrams_faint"] == len(fading_memories(store, AGENT, limit=50))


def test_asking_reads_and_never_writes_a_memory(store):
    e = _saved(store, accessibility=0.2)

    fading_memories(store, AGENT)

    kept = store.get_engram(e.id)
    assert kept.content == WORDS and kept.resolution == 1.0 and not kept.impact


# ── his beliefs, by his word only ──

def test_holding_keeps_his_words_exactly(store):
    belief = hold_belief(store, AGENT, "  Steadiness is the gift;\n the right words never were. ",
                         ["m1", "m2", "m3"])

    held = store.get_beliefs(AGENT, active_only=True)
    assert [b.id for b in held] == [belief.id]
    assert held[0].content == "Steadiness is the gift; the right words never were."
    assert held[0].confidence == NEW_BELIEF_CONFIDENCE
    assert held[0].supporting_engram_ids == ["m1", "m2", "m3"]


def _aged_belief(store, days: float, content="the croft is ours") -> Belief:
    b = Belief(agent_id=AGENT, content=content, confidence=0.4)
    then = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    b.created_at = b.last_revised = b.last_challenged = then
    store.save_belief(b)
    return b


def test_still_true_waits_a_month_and_asks_the_longest_held_first(store):
    _aged_belief(store, 10, "too new to ask")
    older = _aged_belief(store, 60, "held two months")
    month = _aged_belief(store, 31, "held a month")

    assert [b.id for b in beliefs_due(store, AGENT)] == [older.id, month.id]


def test_keeping_a_belief_firms_it_and_starts_the_month_again(store):
    b = _aged_belief(store, 40)

    kept = keep_belief(store, AGENT, b.id, "still true, more than before")

    assert kept.confidence == 0.45
    assert "still true, more than before" in kept.revision_history[-1].reason
    assert beliefs_due(store, AGENT) == []
    again = store.get_beliefs(AGENT, active_only=True)[0]
    assert again.confidence == 0.45


def test_keeping_never_passes_point_99(store):
    b = _aged_belief(store, 40)
    b.confidence = 0.97
    store.save_belief(b)

    assert keep_belief(store, AGENT, b.id).confidence == 0.99


def test_retiring_keeps_the_belief_and_its_history(store):
    b = _aged_belief(store, 40)

    retired = retire_belief(store, AGENT, b.id, "I've grown past this")

    assert retired.superseded_by == RETIRED and retired.confidence == 0.0
    assert store.get_beliefs(AGENT, active_only=True) == []
    kept = store.get_beliefs(AGENT, active_only=False)
    assert [x.id for x in kept] == [b.id]
    assert "I've grown past this" in kept[0].revision_history[-1].reason


def test_a_retired_or_unknown_belief_is_not_moved(store):
    b = _aged_belief(store, 40)
    retire_belief(store, AGENT, b.id)

    assert keep_belief(store, AGENT, b.id) is None
    assert retire_belief(store, AGENT, "belief_nope") is None
    assert keep_belief(store, "someone-else", b.id) is None
