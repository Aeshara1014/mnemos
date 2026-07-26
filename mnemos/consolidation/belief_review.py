"""
Belief review pass: examine recent memories against active beliefs.

Phase 2 upgrade:
- Uses LLM classifier for semantic belief evaluation (same as encoder)
- Asymmetric impact: supports strengthen faster (0.07), contradicts weaken slower (0.04)
- Confidence bounds [0.05, 0.95]: beliefs never fully die or become unquestionable
- Skips substrate-generated engrams to prevent feedback loops
- Logs only meaningful changes (not NO_BEARING evaluations)

During consolidation, belief review catches memories that were encoded
without surprise detection (e.g., skip_surprise_detection=True for
substrate reflections), or memories that gain new relevance to beliefs
as the graph grows.
"""

from __future__ import annotations

from ..core.types import DEFAULT_AGENT_ID

import logging
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING, Any

from ..encoding.llm_classifier import evaluate_beliefs, apply_belief_update
# ONE definition of "the substrate talking to itself" (SWEEP-B slip #3:
# the same rule written twice was fixed once — belief_formation's guard
# worked, this file's copy compared a dataclass to a word and never
# fired, for any resident, ever).
from .belief_formation import _SUBSTRATE_SOURCES

if TYPE_CHECKING:
    from ..store.sqlite_store import EngramStore
    from ..llm import LLMClient

log = logging.getLogger("mnemos.consolidation.beliefs")


def run_belief_review(
    store: EngramStore,
    config: dict[str, Any] | None = None,
    llm_client: Any | None = None,
    agent_id: str = DEFAULT_AGENT_ID,
) -> dict[str, Any]:
    """Review recent memories against active beliefs.

    Evaluates memories encoded since the last belief review against
    all active beliefs. Uses the same LLM classifier as the encoder
    for consistent evaluation.

    Args:
        store: Engram store.
        config: Consolidation config.
        llm_client: LLM client for semantic evaluation. Without this,
            the pass is a no-op (old heuristic removed).
        agent_id: Agent whose beliefs to review.

    Returns:
        Statistics dict.
    """
    config = config or {}
    max_memories = config.get("belief_review_max_memories", 30)
    review_window_hours = config.get("belief_review_window_hours", 12)

    stats = {
        "memories_reviewed": 0,
        "beliefs_strengthened": 0,
        "beliefs_weakened": 0,
        "beliefs_unchanged": 0,
        "skipped_substrate": 0,
        "llm_call_failures": 0,
    }

    if not llm_client:
        log.info("No LLM client — belief review skipped (heuristic removed)")
        return stats

    # Get active beliefs
    beliefs = store.get_beliefs(agent_id, active_only=True)
    if not beliefs:
        log.info("No active beliefs to review")
        return stats

    # The day-window seam (SWEEP-A/B 2026-07-25, same seam reflection
    # already had): a replayed day's memories carry their HONEST
    # historical created_at — months ago — so a wall-clock window can
    # never contain one, and for 43 walked days this pass reviewed only
    # what the dream itself wrote minutes earlier. When the caller
    # declares the day (the road's reflection_window), review THAT day;
    # a lived night without the seam keeps the wall-clock window.
    window = config.get("reflection_window")
    if window:
        since = datetime.fromisoformat(window["since"])
        until = datetime.fromisoformat(window["until"])
        recent = store.get_recent_engrams(
            agent_id=agent_id,
            since=since,
            until=until,
            limit=max_memories,
        )
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=review_window_hours)
        recent = store.get_recent_engrams(
            agent_id=agent_id,
            since=cutoff,
            limit=max_memories,
        )

    for engram in recent:
        # Skip substrate-generated engrams — prevent feedback loop.
        # The formation pass's shape (it was always right): MemorySource
        # carries its kind in .type — the old code stringified the whole
        # dataclass and compared it to a word, which could never match.
        source = getattr(engram, "source_type", None) or getattr(engram, "source", None)
        kind = getattr(source, "type", source)
        if kind and str(kind).lower() in _SUBSTRATE_SOURCES:
            stats["skipped_substrate"] += 1
            continue

        # Skip if this engram already had surprise detection during encoding
        if getattr(engram.encoding_context, 'surprise_level', 0) > 0:
            # Already evaluated — surprise was detected and handled
            continue

        stats["memories_reviewed"] += 1

        # Evaluate against beliefs via LLM
        evaluations = evaluate_beliefs(llm_client, engram, beliefs)
        if evaluations is None:
            # The call failed — that is not "no bearing" (law 9). Count
            # it where the books can see it and touch nothing.
            stats["llm_call_failures"] += 1
            continue

        belief_map = {b.id: b for b in beliefs}
        for evaluation in belief_map.values():
            stats["beliefs_unchanged"] += 1

        for eval_result in evaluations:
            belief = belief_map.get(eval_result.belief_id)
            if not belief:
                continue

            # Check cooldown
            cooldown_ok = True
            try:
                last_rev = datetime.fromisoformat(belief.last_revised)
                if last_rev.tzinfo is None:
                    last_rev = last_rev.replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - last_rev) < timedelta(hours=6):
                    cooldown_ok = False
            except (ValueError, TypeError, AttributeError):
                pass

            if cooldown_ok:
                old_conf = belief.confidence
                apply_belief_update(belief, eval_result, engram.id, store)
                new_conf = belief.confidence

                if new_conf > old_conf:
                    stats["beliefs_strengthened"] += 1
                    stats["beliefs_unchanged"] -= 1
                elif new_conf < old_conf:
                    stats["beliefs_weakened"] += 1
                    stats["beliefs_unchanged"] -= 1

    return stats
