"""
Consolidation daemon: orchestrates all consolidation passes.

Runs cycles either on schedule (cron) or on-demand. Each cycle runs
enabled passes in a defined order:

Shallow cycle (every 4h): connection_discovery → decay
Deep cycle (daily):        connection_discovery → decay → softening → belief_review → reflection

Order matters — connection discovery runs first because new connections
affect decay scoring. Decay runs before softening because accessibility
determines what gets softened. Reflection runs last to reflect on the
processed state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import ulid as _ulid
if hasattr(_ulid, 'new'):
    def _new_ulid():
        return _ulid.new()
else:
    from ulid import ULID as _ULID
    def _new_ulid():
        return str(_ULID())

from ..store.sqlite_store import EngramStore
from ..core.emotional_state import EmotionalState
from ..core.identity import AgentIdentity
from .connection_discovery import run_connection_discovery
from .decay import run_decay_pass
from .softening import run_softening_pass
from .belief_review import run_belief_review
from .reflection import run_reflection_pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConsolidationDaemon:
    """Orchestrator for consolidation passes.

    Usage:
        daemon = ConsolidationDaemon(store=store, config=config)
        stats = daemon.run_cycle(deep=True)  # Full cycle with LLM passes
        stats = daemon.run_cycle(deep=False)  # Quick: decay + connections only
    """

    def __init__(
        self,
        store: EngramStore,
        config: dict[str, Any] | None = None,
        llm_client: Any | None = None,
        embedding_index: Any | None = None,
    ) -> None:
        """Initialize the consolidation daemon.

        Args:
            store: The engram store to consolidate.
            config: Configuration dict (consolidation section from defaults).
            llm_client: LLM client for classification, softening, reflection.
                Must support structured_complete() for classifier and
                complete() for reflection/softening.
                If None, classification falls back to SUPPORTS, belief review
                is a no-op.
            embedding_index: Embedding index for semantic search in connection
                discovery. If None, uses FTS5 only.
        """
        self._store = store
        self._config = config or {}
        self._llm_client = llm_client
        self._embedding_index = embedding_index

    def run_cycle(
        self,
        deep: bool = False,
        agent_id: str = "default",
    ) -> dict[str, Any]:
        """Run a consolidation cycle with all enabled passes.

        Args:
            deep: If True, run all passes including LLM-mediated ones.
                If False, run only connection_discovery and decay.
            agent_id: Which agent's memories to consolidate.

        Returns:
            Dict with per-pass statistics and cycle metadata.
        """
        cycle_id = f"cycle_{_new_ulid()}"
        started_at = _now_iso()

        stats: dict[str, Any] = {
            "cycle_id": cycle_id,
            "cycle_type": "deep" if deep else "shallow",
            "passes_run": [],
            "started_at": started_at,
        }

        consolidation_config = self._config.get("consolidation", self._config)

        # ── PASS 1: Connection Discovery (always runs) ──
        try:
            discovery_stats = run_connection_discovery(
                store=self._store,
                embedding_index=self._embedding_index,
                config=consolidation_config,
                llm_client=self._llm_client,
                agent_id=agent_id,
            )
            stats["connection_discovery"] = discovery_stats
            stats["passes_run"].append("connection_discovery")
        except Exception as e:
            stats["connection_discovery_error"] = str(e)

        # ── PASS 2: Decay (always runs) ──
        try:
            decay_stats = run_decay_pass(
                store=self._store,
                config=consolidation_config,
                agent_id=agent_id,
            )
            stats["decay"] = decay_stats
            stats["passes_run"].append("decay")
        except Exception as e:
            stats["decay_error"] = str(e)

        # ── DEEP ONLY PASSES ──
        if deep:
            # ── PASS 3: Softening ──
            if consolidation_config.get("softening_enabled", True):
                try:
                    softening_stats = run_softening_pass(
                        store=self._store,
                        config=consolidation_config,
                        llm_client=self._llm_client,
                    )
                    stats["softening"] = softening_stats
                    stats["passes_run"].append("softening")
                except Exception as e:
                    stats["softening_error"] = str(e)

            # ── PASS 4: Belief Review ──
            if consolidation_config.get("belief_review_enabled", True):
                try:
                    belief_stats = run_belief_review(
                        store=self._store,
                        config=consolidation_config,
                        llm_client=self._llm_client,
                    )
                    stats["belief_review"] = belief_stats
                    stats["passes_run"].append("belief_review")
                except Exception as e:
                    stats["belief_review_error"] = str(e)

            # ── PASS 5: Reflection ──
            if consolidation_config.get("reflection_enabled", True):
                try:
                    identity = self._store.get_identity(agent_id)
                    if identity is None:
                        identity = AgentIdentity()

                    emotional_state = self._store.get_latest_emotional_state(agent_id)
                    if emotional_state is None:
                        emotional_state = EmotionalState()

                    reflection_stats = run_reflection_pass(
                        store=self._store,
                        identity=identity,
                        emotional_state=emotional_state,
                        llm_client=self._llm_client,
                        config=consolidation_config,
                    )
                    stats["reflection"] = reflection_stats
                    stats["passes_run"].append("reflection")
                except Exception as e:
                    stats["reflection_error"] = str(e)

        completed_at = _now_iso()
        stats["completed_at"] = completed_at

        # Log to consolidation_log table
        try:
            self._store.log_consolidation(
                log_id=cycle_id,
                pass_name="cycle",
                started_at=started_at,
                completed_at=completed_at,
                stats=stats,
            )
        except Exception:
            pass  # Don't fail the cycle over a logging error

        return stats

    def _should_run(self) -> bool:
        """Check whether consolidation should run now.

        Activity gate: checks if enough time has passed since the
        last consolidation cycle. Defaults to True (always run when called).
        """
        min_idle = self._config.get("consolidation", {}).get("min_idle_minutes", 5)

        # Check last consolidation timestamp from the log
        conn = self._store._get_conn()
        row = conn.execute(
            "SELECT completed_at FROM consolidation_log "
            "ORDER BY completed_at DESC LIMIT 1"
        ).fetchone()

        if row is None:
            return True  # Never run before

        try:
            last = datetime.fromisoformat(row["completed_at"])
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            elapsed_minutes = (
                datetime.now(timezone.utc) - last
            ).total_seconds() / 60
            return elapsed_minutes >= min_idle
        except (ValueError, TypeError):
            return True
