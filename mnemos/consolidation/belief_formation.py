"""
Belief formation pass: recurring patterns across lived memories become new beliefs.

Mnemos has always had the full downstream ladder for beliefs — evaluation of new
evidence against them (encoder + belief_review), revision with asymmetric impact,
contradiction handling, stagnation flagging — but no organic way for a belief to
be *born*. Before this pass, the only beliefs in the store were onboarding
templates. This is the missing rung: during deep sleep, memories that express
the same conviction across separate moments graduate into a Belief.

Design guards (this pass rewrites who the agent is — it earns its caution):

- LLM required. Without a client the pass is a no-op, like belief_review.
  Rule-based belief formation would be a stranger guessing at convictions.
- Lived memories only. Substrate-generated engrams (reflections, consolidation
  narratives) are skipped — the same feedback-loop guard belief_review uses.
  The agent believes what it lived, not what its sleep muttered.
- Conservative by contract. The prompt instructs that most nights form nothing;
  every candidate must be grounded in several distinct memories, and formation
  is capped per cycle. Beliefs accrete slowly or they mean nothing.
- Mechanically validated. The LLM proposes; code disposes. Supporting ids must
  exist among the offered memories, meet a minimum count, and span at least
  two distinct days (default) — a conviction recurs across days, not within a
  single sitting; even a re-emerging mind is given the time to sit with things
  before they become belief. Near-duplicates of existing beliefs are dropped.
- Born tentative, with a birth certificate. New beliefs start at the model's
  tentative floor and are immediately revised to the (capped) suggested
  confidence, so revision_history opens with a full account of the formation:
  when, from how many memories, and why.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..core.belief import Belief
from ..core.types import DEFAULT_AGENT_ID
from ..encoding.llm_classifier import _extract_json

if TYPE_CHECKING:
    from ..store.sqlite_store import EngramStore

log = logging.getLogger("mnemos.consolidation.belief_formation")

# Sources that must never seed a belief — substrate talking to itself.
# Stricter than belief_review's guard: dreams are also excluded here, because
# forming a conviction from a dream is the substrate believing its own collisions.
_SUBSTRATE_SOURCES = ("substrate", "reflection", "consolidation", "dream")

_SYSTEM_PROMPT = (
    "You are the memory consolidation substrate for an AI agent, running during "
    "deep sleep. Examine the agent's lived memories for recurring convictions — "
    "patterns experienced repeatedly, across separate moments, that have earned "
    "belief-hood. Be conservative: most nights form no new beliefs. Only propose "
    "a belief when several distinct memories independently express the same "
    "underlying conviction, and never duplicate or rephrase an existing belief. "
    "Respond ONLY with a JSON array."
)


def _distinct_days(engrams: list) -> int:
    """Count distinct calendar days across engrams' created_at timestamps."""
    return len({str(getattr(e, "created_at", ""))[:10] for e in engrams})


def _content_words(text: str) -> set[str]:
    return {w.lower().strip(".,;:!?\"'") for w in text.split() if len(w) > 3}


def _is_duplicate(statement: str, existing_statements: list[str]) -> bool:
    """Word-overlap near-duplicate check against existing belief statements."""
    words = _content_words(statement)
    if not words:
        return True  # empty/degenerate statements are never new beliefs
    for other in existing_statements:
        other_words = _content_words(other)
        if not other_words:
            continue
        overlap = len(words & other_words) / min(len(words), len(other_words))
        if overlap >= 0.6:
            return True
    return False


def run_belief_formation_pass(
    store: EngramStore,
    config: dict[str, Any] | None = None,
    llm_client: Any | None = None,
    agent_id: str = DEFAULT_AGENT_ID,
) -> dict[str, Any]:
    """Form new beliefs from recurring patterns across lived memories.

    Runs after belief_review (the old beliefs are stress-tested first) and
    before reflection (so a newborn belief can be part of the night's story).
    Newborn beliefs skip same-cycle review; they meet the review pass on the
    next deep cycle, like any other belief.

    Args:
        store: Engram store.
        config: Consolidation config (belief_formation_* keys).
        llm_client: LLM client. Without this, the pass is a no-op —
            no rule-based fallback, by design.
        agent_id: Agent whose memories are examined.

    Returns:
        Statistics dict.
    """
    config = config or {}
    max_per_cycle = config.get("belief_formation_max_per_cycle", 2)
    min_supporting = config.get("belief_formation_min_supporting", 3)
    min_distinct_days = config.get("belief_formation_min_distinct_days", 2)
    max_memories = config.get("belief_formation_max_memories", 60)
    max_candidates = config.get("belief_formation_max_candidates", 5)
    confidence_cap = config.get("belief_formation_confidence_cap", 0.6)

    stats = {
        "memories_considered": 0,
        "skipped_substrate": 0,
        "candidates_proposed": 0,
        "beliefs_formed": 0,
        "skipped_duplicate": 0,
        "skipped_insufficient_support": 0,
        "skipped_day_span": 0,
    }

    if not llm_client:
        log.info("No LLM client — belief formation skipped (no rule-based fallback, by design)")
        return stats

    # ── Gather lived memories ──
    engrams = store.get_active_engrams(
        agent_id=agent_id, limit=max_memories, load_connections=False
    )
    lived = []
    for engram in engrams:
        source = getattr(engram, "source_type", None) or getattr(engram, "source", None)
        kind = getattr(source, "type", source)  # MemorySource carries a .type string
        if kind and str(kind).lower() in _SUBSTRATE_SOURCES:
            stats["skipped_substrate"] += 1
            continue
        lived.append(engram)
    stats["memories_considered"] = len(lived)

    if len(lived) < min_supporting:
        log.info("Only %d lived memories — not enough to form anything", len(lived))
        return stats

    by_id = {e.id: e for e in lived}

    # ── Existing beliefs (context for the LLM, corpus for dedup) ──
    existing = store.get_beliefs(agent_id, active_only=True)
    existing_statements = [b.content for b in existing if b.content]

    # ── One structured call: the LLM proposes, code disposes ──
    memory_lines = "\n".join(f"{e.id}: {e.content}" for e in lived)
    belief_lines = "\n".join(f"- {s}" for s in existing_statements) or "(none)"
    user_prompt = (
        f"LIVED MEMORIES (id: content):\n{memory_lines}\n\n"
        f"EXISTING BELIEFS (do not duplicate or rephrase these):\n{belief_lines}\n\n"
        f"Propose at most {max_candidates} new beliefs as a JSON array:\n"
        '[{"statement": "first-person conviction, one sentence", '
        '"confidence": 0.3-0.6, '
        '"domain": "general|self|social|technical|project", '
        '"supporting_ids": ["engram_..."], '
        '"reasoning": "one line: what recurs across these memories"}]\n'
        "Return [] if nothing has earned belief-hood."
    )

    try:
        raw = llm_client.structured_complete(
            system=_SYSTEM_PROMPT, user=user_prompt, temperature=0.2, max_tokens=1500
        )
        candidates = _extract_json(raw)
    except Exception as e:
        log.warning("Belief formation LLM call failed: %s", e)
        stats["formation_error"] = str(e)
        return stats

    stats["candidates_proposed"] = len(candidates)

    # ── Mechanical validation ──
    formed_statements: list[str] = []
    for candidate in candidates:
        if stats["beliefs_formed"] >= max_per_cycle:
            break
        if not isinstance(candidate, dict):
            continue

        statement = str(candidate.get("statement", "")).strip()
        if not statement or len(statement) > 300:
            continue

        # Supporting ids must be real, offered memories — no hallucinated evidence.
        proposed_ids = candidate.get("supporting_ids") or []
        supporting = [by_id[i] for i in proposed_ids if i in by_id]
        if len(supporting) < min_supporting:
            stats["skipped_insufficient_support"] += 1
            continue

        if _distinct_days(supporting) < min_distinct_days:
            stats["skipped_day_span"] += 1
            continue

        if _is_duplicate(statement, existing_statements + formed_statements):
            stats["skipped_duplicate"] += 1
            continue

        try:
            suggested = float(candidate.get("confidence", 0.4))
        except (TypeError, ValueError):
            suggested = 0.4
        confidence = max(0.3, min(confidence_cap, suggested))

        belief = Belief(
            agent_id=agent_id,
            content=statement,
            confidence=0.3,  # tentative floor; the revise below is the birth certificate
            domain=str(candidate.get("domain", "general")) or "general",
            supporting_engram_ids=[e.id for e in supporting],
        )
        reason = (
            f"Formed during deep consolidation from {len(supporting)} recurring "
            f"memories: {str(candidate.get('reasoning', '')).strip() or 'pattern held across moments'}"
        )
        belief.revise(confidence, reason, trigger_engram_id=supporting[0].id)
        store.save_belief(belief)

        formed_statements.append(statement)
        stats["beliefs_formed"] += 1
        log.info(
            "Belief formed (%.2f, %d supporting): %s",
            belief.confidence, len(supporting), statement,
        )

    return stats
