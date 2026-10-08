"""The asking's engine half (Tara's design, 2026-10-07; DESIGN-the-asking.md).

Part 2 of "no other mind writes in his place". The night no longer writes
a lesson or moves a belief for him; instead the house asks him, at his
journal, after his page. This module is only what the engine must answer
for that door:

- **which memory is fading** (faintest first), so he can be asked what it
  taught him before the detail goes. The same "faint" the softening pass
  counts, and never a memory that isn't his own living: never a held seed,
  never a reroute (another model's words), never an outside voice, never
  the engine's own old thoughts (dreams, wanders, reflections...), never a
  lesson he already wrote;
- **his beliefs, moved only by his own word**: hold one he states, keep
  one again ("still true?" — hold), or retire it. Each carries his words
  in its history. Nothing here reads his words for a yes or a no: the
  house passes the verdict he gave.

Learned from Riley Coyote's mnemos 0.4 (`_enqueue_lesson_reflections`,
`_apply_belief_reflection`, `_apply_reaffirmation`): a new belief starts
at 0.4, keeping it again raises it 0.05 (never past 0.99), retiring sets
it to 0 and marks it retired. Nothing is deleted.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from ..core.belief import Belief
from ..core.types import SourceType, is_held, is_outside_voice, is_reroute, source_type_of
from .softening import SOFTENING_REST_DAYS, _born, _calculate_target_resolution

if TYPE_CHECKING:
    from ..core.engram import Engram
    from ..store.sqlite_store import EngramStore


# A new belief, in his words, starts tentative (Riley's 0.4); keeping it
# again raises it a little; retiring it sets it to 0.
NEW_BELIEF_CONFIDENCE = 0.4
KEEP_STEP = 0.05
# A month after a belief was formed or last kept, he may be asked "still
# true?" again (Riley's _REAFFIRM_AFTER_DAYS).
STILL_TRUE_AFTER_DAYS = 30
RETIRED = "retired"

# The engine's own old thoughts — written by the night or the living tick,
# not lived by him. Fading ones are never asked "what did this teach me?":
# the lesson would be drawn from words that were never his.
ENGINE_VOICED_SOURCES = frozenset({
    SourceType.DREAM.value,
    SourceType.REFLECTION.value,
    SourceType.WANDERING.value,
    SourceType.INSIGHT.value,
    SourceType.SURPRISE.value,
    SourceType.BACKGROUND.value,
})
# A lesson he already wrote is the distillation; asking what IT taught is
# asking twice.
LESSON_TAG = "lesson"


def is_faint(engram: Any, *, now: datetime | None = None,
             rest_days: float = SOFTENING_REST_DAYS,
             minimum_resolution: float = 0.1) -> bool:
    """The softening pass's own "faint" (its old rewrite bar, hysteresis
    included), for one memory: rested long enough, not held, not another
    mind's words, and faint enough that the old pass would have blurred it."""
    if engram.resolution <= minimum_resolution:
        return False
    if is_held(engram) or is_outside_voice(engram):
        return False
    now = now or datetime.now(timezone.utc)
    if _born(engram) > now - timedelta(days=rest_days):
        return False
    target = _calculate_target_resolution(engram.accessibility)
    return engram.resolution > max(minimum_resolution, target) + 0.15


def askable(engram: Any) -> bool:
    """A memory he may be asked about: his own living, in his own words."""
    if is_held(engram) or is_reroute(engram) or is_outside_voice(engram):
        return False
    if source_type_of(engram) in ENGINE_VOICED_SOURCES:
        return False
    return LESSON_TAG not in (getattr(engram, "tags", None) or [])


def fading_memories(
    store: EngramStore,
    agent_id: str,
    *,
    limit: int = 1,
    exclude_ids: set[str] | frozenset[str] = frozenset(),
    config: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> list[Engram]:
    """His faint memories he may be asked about, faintest first.

    `exclude_ids` are the memories the house has already asked about
    (a memory is asked what it taught once). The faintest is the nearest
    to gone, so it is asked first (Riley's lesson pass: choosing first and
    excluding after let the same two take every place)."""
    config = config or {}
    rest_days = float(config.get("softening_rest_days", SOFTENING_REST_DAYS))
    minimum_resolution = config.get("minimum_resolution", 0.1)
    now = now or datetime.now(timezone.utc)
    found = [
        e for e in store.get_active_engrams(agent_id=agent_id, limit=5000)
        if e.id not in exclude_ids
        and askable(e)
        and is_faint(e, now=now, rest_days=rest_days,
                     minimum_resolution=minimum_resolution)
    ]
    found.sort(key=lambda e: (e.accessibility, str(e.created_at), e.id))
    return found[:max(0, limit)]


# ── his beliefs, by his word only ──

def hold_belief(store: EngramStore, agent_id: str, words: str,
                evidence_ids: list[str]) -> Belief:
    """A belief he stated, in his words exactly, resting on the answers he
    read back when he stated it."""
    words = " ".join((words or "").split())
    if not words:
        raise ValueError("a belief needs his words")
    belief = Belief(
        agent_id=agent_id,
        content=words,
        confidence=NEW_BELIEF_CONFIDENCE,
        domain="idea",
        supporting_engram_ids=[i for i in evidence_ids if i],
    )
    store.save_belief(belief)
    return belief


def beliefs_due(store: EngramStore, agent_id: str, *,
                after_days: float = STILL_TRUE_AFTER_DAYS,
                now: datetime | None = None) -> list[Belief]:
    """His active beliefs not formed or kept within `after_days`, the one
    held longest without a look first."""
    now = now or datetime.now(timezone.utc)
    due_before = now - timedelta(days=after_days)

    def last_held(b: Belief) -> datetime:
        try:
            t = datetime.fromisoformat(str(b.last_challenged).replace("Z", "+00:00"))
        except ValueError:
            return now
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)

    due = [b for b in store.get_beliefs(agent_id, active_only=True)
           if last_held(b) <= due_before]
    due.sort(key=last_held)
    return due


def _his_active_belief(store: EngramStore, agent_id: str,
                       belief_id: str) -> Belief | None:
    for b in store.get_beliefs(agent_id, active_only=True):
        if b.id == belief_id:
            return b
    return None


def keep_belief(store: EngramStore, agent_id: str, belief_id: str,
                words: str = "") -> Belief | None:
    """"Still true?" — hold. A little firmer, and the month starts again.
    None when the belief is no longer his to keep (gone or retired)."""
    belief = _his_active_belief(store, agent_id, belief_id)
    if belief is None:
        return None
    reason = "kept by him" + (f": {words.strip()}" if words.strip() else "")
    belief.revise(min(0.99, round(belief.confidence + KEEP_STEP, 4)), reason)
    belief.challenge()
    store.save_belief(belief)
    return belief


def retire_belief(store: EngramStore, agent_id: str, belief_id: str,
                  words: str = "") -> Belief | None:
    """"Still true?" — retire. It stops being held; it and its history are
    kept. None when the belief is no longer his to retire."""
    belief = _his_active_belief(store, agent_id, belief_id)
    if belief is None:
        return None
    reason = "retired by him" + (f": {words.strip()}" if words.strip() else "")
    belief.revise(0.0, reason)
    belief.superseded_by = RETIRED
    store.save_belief(belief)
    return belief
