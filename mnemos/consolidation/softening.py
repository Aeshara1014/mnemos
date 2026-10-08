"""
Softening pass: fading keeps his words (Tara's ruling, 2026-10-07).

The forgetting itself is accessibility decay: a faint memory ranks lower
and is reached less. Its words stay exactly as he wrote them.

This pass used to hand a faint memory to the substrate model, called as
"a memory conservator", with a few of his vivid memories as voice
samples, and have it rewrite the memory blurrier "in the rememberer's own
voice"; it also had the model write the lesson the memory taught. Both
were another mind's words where his belong. Riley Coyote's mnemos 0.4
(#103, #124) took the same road; Tara chose it for the Croft, and the
law runs for every resident (one code copy).

So the pass now rewrites nothing, calls no model and mints no lesson. It
only counts what has gone faint, for the record. What a fading memory
taught is asked of HIM, by the asking door (part 2, asking.py);
nothing is written in his place.

The original content is always preserved in content_at_encoding (immutable);
memories blurred before this ruling keep their lineage, and the
remembering walk can still restore them.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from ..core.types import is_held, is_outside_voice
from ..core.types import EngramKind, SourceType

if TYPE_CHECKING:
    from ..store.sqlite_store import EngramStore


# Tara's ruling (2026-10-03): a memory rests this many days before the night
# may tidy it, and the oldest and faintest are tidied first. Before, a new
# memory (accessibility 0.5, under the ~0.62 bar) could be blurred its very
# first deep night, and the 50-a-night budget went to the freshest.
SOFTENING_REST_DAYS = 14


def _born(engram: Engram) -> datetime:
    """When the memory was made (its created_at), as an aware UTC time."""
    try:
        t = datetime.fromisoformat(str(engram.created_at).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def run_softening_pass(
    store: EngramStore,
    config: dict[str, Any],
    llm_client: Any | None,
    agent_id: str | None = None,
    embedding_index: Any | None = None,
) -> dict[str, Any]:
    """Count the memories that have gone faint. Rewrite none of them.

    Args:
        store: The engram store.
        config: Configuration dict (softening_rest_days, minimum_resolution).
        llm_client: Accepted for the daemon's call shape and never used —
            no model writes in his place (2026-10-07).
        agent_id: Agent whose memories to count. None keeps the store's own
            default scope.
        embedding_index: Accepted for the daemon's call shape; unused.

    Returns:
        Statistics dict. ``engrams_faint`` counts the memories an older pass
        would have rewritten; ``engrams_softened``, ``lessons_created`` and
        ``llm_calls`` stay 0, and ``words_kept`` says why.
    """
    del llm_client, embedding_index  # never used: the words are his
    minimum_resolution = config.get("minimum_resolution", 0.1)
    rest_days = float(config.get("softening_rest_days", SOFTENING_REST_DAYS))
    rested_before = datetime.now(timezone.utc) - timedelta(days=rest_days)

    stats: dict[str, Any] = {
        "engrams_evaluated": 0,
        "engrams_faint": 0,
        "engrams_softened": 0,
        "lessons_created": 0,
        "lessons_reinforced": 0,
        "llm_calls": 0,
        "dry_run": bool(config.get("softening_dry_run", False)),
        "words_kept": "fading keeps his words; nothing is rewritten (2026-10-07)",
    }

    all_engrams = (
        store.get_active_engrams(agent_id=agent_id, limit=5000)
        if agent_id is not None
        else store.get_active_engrams(limit=5000)
    )

    for engram in all_engrams:
        if engram.resolution <= minimum_resolution:
            continue
        if is_held(engram):
            stats["skipped_held"] = stats.get("skipped_held", 0) + 1
            continue
        if is_outside_voice(engram):
            stats["skipped_outside_voice"] = stats.get("skipped_outside_voice", 0) + 1
            continue
        if _born(engram) > rested_before:
            stats["skipped_resting"] = stats.get("skipped_resting", 0) + 1
            continue
        stats["engrams_evaluated"] += 1
        target = _calculate_target_resolution(engram.accessibility)
        # The old pass's bar (hysteresis included): faint enough that it
        # would once have been rewritten. Counted, never touched.
        if engram.resolution > max(minimum_resolution, target) + 0.15:
            stats["engrams_faint"] += 1

    return stats


def _calculate_target_resolution(accessibility: float) -> float:
    """Map accessibility to appropriate resolution level.

    Ported from Anima's calculate_target_sharpness.
    """
    if accessibility >= 0.7:
        return 1.0
    elif accessibility >= 0.4:
        t = (accessibility - 0.4) / 0.3
        return 0.4 + (0.6 * t)
    elif accessibility >= 0.15:
        t = (accessibility - 0.15) / 0.25
        return 0.1 + (0.3 * t)
    else:
        return 0.0


# ── Kept from the old pass; nothing calls these today ──
# The asking door (part 2, mnemos/consolidation/asking.py + the house) took
# another road: what a fading memory taught him becomes a NEW memory in his
# words, linked to it, and the faint memory itself is never touched.

def _is_real_distillation(impact: str, *texts: str) -> bool:
    """A lesson may only be born from a real distillation.

    The goodnight-lesson law (2026-07-22): an impact that is just a line
    lifted from the memory itself — the rule-based fallback's last
    sentence, or an LLM echoing a quote — is not insight, and minting it
    as a high-stability lesson immortalizes sign-offs ("Goodnight, my
    heart") as wisdom. A real distillation is NEW prose about the memory,
    not prose OF it. Checked against every provided text (current content
    AND the sharp content_at_encoding, so an impact extracted by the old
    fallback in an earlier cycle can never mint a lesson later, after the
    content it was lifted from has blurred away)."""
    if not impact or len(impact.strip()) < 10:
        return False
    norm = " ".join(impact.lower().split())
    for text in texts:
        if text and norm in " ".join(text.lower().split()):
            return False
    return True


def _create_or_reinforce_lesson(
    engram: Any,
    store: EngramStore,
    stats: dict,
    embedding_index: Any | None = None,
) -> str | None:
    """Create or reinforce a lesson engram from the impact of a softened memory.

    Shift 2: Forgetting that teaches. The distilled insight from softening
    becomes a persistent "lesson" engram with high stability. If a similar
    lesson already exists, reinforce it instead of creating a duplicate.

    Returns the lesson engram ID, or None if no lesson was created.
    """
    impact_text = engram.impact
    if not impact_text or len(impact_text.strip()) < 10:
        return None

    # Search for existing similar lessons
    words = [w for w in impact_text.split() if len(w) > 2 and w.isalnum()]
    if not words:
        return None

    query = " OR ".join(f'"{w}"' for w in words[:6])
    try:
        existing = store.search_fts(query, limit=10)
    except Exception:
        existing = []

    # Check if any existing engram is a lesson with similar content
    for candidate in existing:
        if candidate.id == engram.id:
            continue
        if "lesson" in candidate.tags or "distilled" in candidate.tags:
            # Reinforce existing lesson
            candidate.strength = min(1.0, candidate.strength + 0.1)
            candidate.stability = min(1.0, candidate.stability + 0.05)
            candidate.record_access()
            store.save_engram(candidate)
            stats["lessons_reinforced"] = stats.get("lessons_reinforced", 0) + 1
            return candidate.id

    # No existing lesson found — create a new one
    from ..core.engram import Engram, MemorySource
    lesson = Engram(
        content=impact_text,
        impact=impact_text,  # For lessons, impact IS the content
        kind=EngramKind.PROCEDURAL,
        tags=list(set(engram.tags + ["lesson", "distilled"])),
        strength=0.8,
        stability=0.8,  # High stability — lessons persist
        source=MemorySource(
            type=SourceType.REFLECTION,
            confidence=engram.source.confidence,
            confidence_source=engram.source.confidence_source,
        ),
        owner_agent_id=engram.owner_agent_id,
    )

    store.save_engram(lesson)
    if embedding_index is not None:
        # A new lesson joins the meaning index like any encoded memory
        # (2026-09-30); a failed embed never costs the lesson itself.
        try:
            embedding_index.index_engram(lesson.id, lesson.content)
        except Exception:
            stats["lessons_unindexed"] = stats.get("lessons_unindexed", 0) + 1
    stats["lessons_created"] = stats.get("lessons_created", 0) + 1
    return lesson.id
