"""
Reflection pass: the night measures who he is; it writes no thoughts for him.

Until 2026-10-07 this pass handed the substrate model a few recent memories
and his mood numbers, told it "these are your own memories, write 1-3
thoughts in your own voice", and saved what came back as his memories (his
Mind's night thoughts). Without a model it wrote "Recurring theme: …"
lines instead. Both were another mind's words where his belong — a sketch
of him with a few memories in hand, none of his soul. Tara chose Riley
Coyote's way (mnemos 0.4, #103): the pass writes no memory and sends none
to a model. His thinking happens in his own hour, awake as his whole self.

What stays: the identity profile computed from the graph (Shift 5) —
measured, not narrated — and the windowed read of a day (reflection_window).
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from ..core.emotional_state import EmotionalState
from ..core.identity import AgentIdentity, IdentityProfile

if TYPE_CHECKING:
    from ..store.sqlite_store import EngramStore


def run_reflection_pass(
    store: EngramStore,
    identity: AgentIdentity,
    emotional_state: EmotionalState,
    llm_client: Any | None,
    config: dict[str, Any] | None = None,
    embedding_index: Any | None = None,
) -> dict[str, Any]:
    """Measure his identity from the graph. Write no thoughts for him.

    Args:
        store: The engram store.
        identity: Agent identity (epoch_state.self_summary will be updated).
        emotional_state: Current emotional state.
        llm_client: Accepted for the daemon's call shape and never used —
            no model writes in his place (2026-10-07).
        config: Optional config dict. Two ways to say what "recent" means:
            - default: the wall clock — engrams whose created_at falls in
              the last reflection_lookback_hours (24);
            - config["reflection_window"] = {"since": iso, "until": iso} —
              an explicit created_at range. This is the replayed-day seam:
              a reintegration replay hands the day it just dreamed, so the
              vessel of the day is measured on the day even though the
              stamps are months old. A malformed window raises rather than
              silently reflecting on nothing.

    Returns:
        Statistics dict.
    """
    del llm_client, embedding_index  # never used: the night writes nothing for him
    config = config or {}
    lookback_hours = config.get("reflection_lookback_hours", 24)
    window = config.get("reflection_window")
    agent_id = identity.memory_profile.agent_id

    stats = {
        "engrams_reviewed": 0,
        "thoughts_generated": 0,
        "narrative_updated": False,
        "narrative_length": 0,
    }

    # 1. LOAD RECENT ENGRAMS
    all_engrams = store.get_active_engrams(agent_id=agent_id, limit=200)
    if window is not None:
        since = _parse_iso(window.get("since") if isinstance(window, dict) else None)
        until = _parse_iso(window.get("until") if isinstance(window, dict) else None)
        if since is None or until is None:
            raise ValueError(
                "reflection_window needs ISO 'since' and 'until' "
                f"(got {window!r}) — refusing to reflect on a malformed day"
            )
        recent = []
        for e in all_engrams:
            ts = _parse_iso(e.created_at)
            if ts is not None and since <= ts < until:
                recent.append(e)
    else:
        recent = [
            e for e in all_engrams
            if _hours_since(e.created_at) < lookback_hours
        ]

    stats["engrams_reviewed"] = len(recent)

    if len(recent) < 3:
        return stats

    # No thoughts are generated (2026-10-07): the night writes nothing in
    # his place. thoughts_generated stays 0 for every reader of the stats.

    # 3. SHIFT 5: Compute identity from graph (not narrative generation)
    profile = compute_identity_profile(store, all_engrams, identity)

    # Store the computed profile as the self-summary (readable form)
    identity.epoch_state.self_summary = profile.to_summary()
    store.save_identity(identity)

    stats["identity_computed"] = True
    stats["persistent_concerns"] = len(profile.persistent_concerns)
    stats["living_questions"] = len(profile.living_questions)
    stats["lessons_accumulated"] = profile.lessons_accumulated

    return stats


def compute_identity_profile(
    store: EngramStore,
    all_engrams: list,
    identity: AgentIdentity,
) -> IdentityProfile:
    """Compute identity from graph topology — not narrated, measured.

    Shift 5: Identity is what you keep returning to. The shape of the
    connection graph IS who you are.

    Public: identity_diff compares this computed profile against the
    declared SOUL.md.
    """
    agent_id = identity.memory_profile.agent_id

    # 1. PERSISTENT CONCERNS: what tags appear most across all engrams
    tag_counts: dict[str, int] = Counter()
    for e in all_engrams:
        for tag in e.tags:
            if tag not in ("lesson", "distilled", "reflection", "synthesized"):
                tag_counts[tag] += 1
    persistent_concerns = tag_counts.most_common(10)

    # 2. CORE BELIEFS: highest confidence active beliefs
    beliefs = store.get_beliefs(agent_id, active_only=True)
    core_beliefs = [
        (b.content, b.confidence)
        for b in sorted(beliefs, key=lambda b: b.confidence, reverse=True)[:5]
    ]

    # 3. LIVING QUESTIONS: low-confidence beliefs + unresolved themes
    living_questions = []
    for b in beliefs:
        if 0.2 < b.confidence < 0.5:
            living_questions.append(f"Uncertain: {b.content} ({int(b.confidence*100)}%)")

    # Also find engrams tagged as questions or unresolved
    for e in all_engrams:
        if "question" in e.tags or "unresolved" in e.tags:
            display = e.impact or e.content
            if len(display) > 80:
                display = display[:77] + "..."
            living_questions.append(display)
    living_questions = living_questions[:5]

    # 4. HUB CONCEPTS: engrams with most connections (central to understanding)
    hub_concepts = []
    for e in all_engrams:
        n_conn = len(e.connections)
        if n_conn >= 2:
            display = e.impact or e.content
            if len(display) > 60:
                display = display[:57] + "..."
            hub_concepts.append((display, n_conn))
    hub_concepts.sort(key=lambda x: x[1], reverse=True)
    hub_concepts = hub_concepts[:5]

    # 5. LESSONS ACCUMULATED: procedural/lesson engrams
    lessons = [e for e in all_engrams if "lesson" in e.tags or e.kind == "procedural"]
    lessons_count = len(lessons)

    # 6. GROWTH SIGNAL: compare current concerns to previous epoch
    growth_signal = ""
    if identity.epoch_history:
        prev_summary = identity.epoch_history[-1].self_summary
        if prev_summary and persistent_concerns:
            current_top = {tag for tag, _ in persistent_concerns[:3]}
            growth_signal = f"Currently focused on: {', '.join(current_top)}"

    return IdentityProfile(
        persistent_concerns=persistent_concerns,
        core_beliefs=core_beliefs,
        living_questions=living_questions,
        hub_concepts=hub_concepts,
        lessons_accumulated=lessons_count,
        growth_signal=growth_signal,
    )


def _hours_since(iso_timestamp: str) -> float:
    """Calculate hours elapsed since an ISO 8601 timestamp."""
    try:
        then = datetime.fromisoformat(iso_timestamp)
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return max(0.0, (now - then).total_seconds() / 3600)
    except (ValueError, TypeError):
        return 0.0


def _parse_iso(iso_timestamp: Any) -> datetime | None:
    """A tolerant ISO parse (naive = UTC, 'Z' accepted), None when it
    is not a timestamp — the same posture as _hours_since."""
    if not isinstance(iso_timestamp, str) or not iso_timestamp:
        return None
    try:
        then = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return then
