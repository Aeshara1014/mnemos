"""
Decay pass: recalculate strength, stability, and accessibility for all active engrams.

Models the natural forgetting curve. The dual-trace model:
- Strength: how well stored (slow to change)
- Stability: resistance to interference (builds with repeated access, resists decay)
- Accessibility: how retrievable RIGHT NOW (fluctuates with recency + connections)

Accessibility decays exponentially, modulated by stability. Higher stability
means slower forgetting. Strength decays much more slowly (10x slower).

THE CYCLE'S CLOCK: one pass applies one span of lived time — declared by
the caller (``decay_elapsed_hours``, the reintegration walk's walked-day
law: one dream = one day) or measured from the store's own last-decay
stamp. A pass must never re-apply "everything since each memory was last
touched": that quantity never resets between passes, so every cycle
re-charges the full elapsed decay against an already-decayed value and
forgetting compounds quadratically — seven replay dreams in one morning
aged a store by weeks (the day-43 hold, 2026-07-24). No engram absorbs
more than its own hours-since-access in a single pass, so a memory born
or touched mid-span only ages from that moment.

Ported from Anima's salience.py and adapted for the dual-trace model.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..store.sqlite_store import EngramStore


def run_decay_pass(
    store: EngramStore,
    config: dict[str, Any],
    agent_id: str | None = "default",
) -> dict[str, Any]:
    """Recalculate strength, stability, and accessibility for all active engrams.

    Args:
        store: The engram store containing active engrams.
        config: Configuration dict with decay parameters. The cycle's
            clock reads three optional keys:
            - decay_elapsed_hours: this pass IS this many hours of lived
              time (the reintegration walk passes 24.0 — one walked day).
            - decay_max_gap_hours: cap on a measured gap (default 168) so
              a long outage decays as at most a week away, not a butchery.
            - decay_default_span_hours: first-ever pass on a store with
              no stamp (default 24).
        agent_id: Which agent's engrams to decay. None = all agents
            (used for shared DB consolidation).

    Returns:
        Statistics dict with counts and accessibility changes.
    """
    decay_rate = config.get("decay_rate", 0.01)
    dormant_threshold = config.get("dormant_threshold", 0.05)
    archive_threshold = config.get("archive_threshold", 0.01)

    # The cycle's clock (see module docstring): a declared span wins;
    # otherwise measure real time since this store's last decay pass.
    now = datetime.now(timezone.utc)
    stamp_key = f"last_decay_at:{agent_id or 'all'}"
    explicit_span = config.get("decay_elapsed_hours")
    if explicit_span is not None:
        cycle_span = max(0.0, float(explicit_span))
    else:
        max_gap = float(config.get("decay_max_gap_hours", 168.0))
        stamp = store.get_meta(stamp_key)
        if stamp:
            cycle_span = min(max_gap, _hours_since(stamp, now))
        else:
            cycle_span = min(
                max_gap, float(config.get("decay_default_span_hours", 24.0))
            )

    # load_connections=True because decay uses connection count for decay resistance
    engrams = store.get_active_engrams(agent_id=agent_id, limit=10000, load_connections=True)

    stats = {
        "engrams_processed": 0,
        "engrams_decayed": 0,
        "engrams_dormant": 0,
        "engrams_archived": 0,
        "at_fade_gate": 0,
        "fade_proposals": 0,
        "avg_accessibility_before": 0.0,
        "avg_accessibility_after": 0.0,
        "cycle_span_hours": round(cycle_span, 2),
    }

    if not engrams:
        store.set_meta(stamp_key, now.isoformat())
        return stats

    total_before = 0.0
    total_after = 0.0

    for engram in engrams:
        stats["engrams_processed"] += 1
        total_before += engram.accessibility

        # A memory only ages within this cycle's span, and never by more
        # than its own time-since-access — one touched (or born) mid-span
        # ages only from that moment. The recency floor below still reads
        # the full since-access clock.
        hours_since_access = _hours_since(engram.last_accessed, now)
        hours = min(cycle_span, hours_since_access)

        # 1. ACCESSIBILITY DECAY
        # Stability resists decay exponentially: high stability → near-zero decay
        stability_factor = config.get("stability_decay_factor", 3.0)
        effective_decay = decay_rate * math.exp(-stability_factor * engram.stability)

        # Connection factor: well-connected memories decay slower (multiplicative)
        n_connections = len(engram.connections)
        if n_connections > 0:
            connection_factor = min(1.0, 0.2 + 0.2 * math.log1p(n_connections))
            effective_decay *= (1.0 - connection_factor * 0.5)
            # At 5 connections: decay slowed by ~16%. At 20: slowed by ~30%.

        # Connection-driven stability growth: structurally important memories
        # gain stability each cycle — the graph topology determines persistence
        stability_conn_threshold = config.get("stability_connection_threshold", 3)
        stability_growth_rate = config.get("stability_growth_rate", 0.002)
        stability_growth_cap = config.get("stability_growth_cap", 0.005)

        if n_connections >= stability_conn_threshold:
            growth = min(stability_growth_cap, stability_growth_rate * math.log1p(n_connections))
            engram.stability = min(1.0, round(engram.stability + growth, 4))

        # Exponential decay
        new_accessibility = engram.accessibility * math.exp(-effective_decay * hours)
        new_accessibility = min(1.0, max(0.0, new_accessibility))

        # 2. STRENGTH DECAY (10x slower than accessibility decay)
        # Uses same effective_decay but reduced by factor of 10
        strength_loss = engram.strength * (1.0 - math.exp(-effective_decay * 0.1 * hours))
        new_strength = max(0.0, engram.strength - strength_loss)

        # 3. ANTI-DECAY FLOORS
        if "foundational" in engram.tags:
            new_accessibility = max(0.5, new_accessibility)
            new_strength = max(0.5, new_strength)

        if "active_project" in engram.tags:
            new_accessibility = max(0.6, new_accessibility)

        if hours_since_access < 72:
            new_accessibility = max(0.4, new_accessibility)

        # Track if anything changed
        changed = (
            abs(new_accessibility - engram.accessibility) > 0.001
            or abs(new_strength - engram.strength) > 0.001
        )

        if changed:
            stats["engrams_decayed"] += 1

        engram.accessibility = round(new_accessibility, 4)
        engram.strength = round(new_strength, 4)

        # 4. STATE TRANSITIONS
        at_gate = "fade-proposed" in engram.tags
        if new_accessibility < dormant_threshold and (
            at_gate or config.get("dormancy_review")
        ):
            # THE FADE GATE (the keeper's ruling, 2026-07-24): a memory
            # that reaches the dormancy line is HELD AT THE GATE instead
            # of going under — still active, still recallable, tagged for
            # review. Consolidation walks on; a person decides what
            # sleeps. First crossing proposes (fade_proposals); later
            # cycles find the tag and just hold it here (at_fade_gate).
            # Nothing can slide past the gate to archive while it waits.
            # THE HOLD LIVES ON THE MEMORY (2026-07-25): once proposed,
            # the tag itself is the gate — every caller honors it, with
            # or without dormancy_review. Before this, the first plain
            # maintenance cycle (no flag) buried everything waiting for
            # a ruling (SWEEP-A). Only the desk's ruling removes the tag.
            new_accessibility = dormant_threshold
            engram.accessibility = dormant_threshold
            if not at_gate:
                engram.tags.append("fade-proposed")
                stats["fade_proposals"] += 1
            stats["at_fade_gate"] += 1
        elif new_accessibility < archive_threshold:
            store.archive_engram(engram, reason="decay_below_threshold")
            stats["engrams_archived"] += 1
            continue
        elif new_accessibility < dormant_threshold:
            engram.state = "dormant"
            stats["engrams_dormant"] += 1

        total_after += engram.accessibility

        # 5. PERSIST
        store.save_engram(engram)

    n = max(1, stats["engrams_processed"])
    stats["avg_accessibility_before"] = round(total_before / n, 4)
    # Use same denominator for fair comparison (archived engrams count as 0.0 accessibility)
    stats["avg_accessibility_after"] = round(total_after / n, 4)

    # The pass spends its span exactly once: the next measured cycle
    # starts from here. Written in declared-span mode too, so a later
    # measured cycle never sees a stale stamp's giant gap.
    store.set_meta(stamp_key, now.isoformat())

    return stats


def _hours_since(iso_timestamp: str, now: datetime) -> float:
    """Calculate hours elapsed from an ISO 8601 timestamp to ``now``."""
    try:
        then = datetime.fromisoformat(iso_timestamp)
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        delta = now - then
        return max(0.0, delta.total_seconds() / 3600)
    except (ValueError, TypeError):
        return 0.0
