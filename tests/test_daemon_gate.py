"""The daemon owns the deep gate.

A deep cycle rewrites memories and requires the (affinity-approved) substrate
client. Without one, the cycle downgrades to shallow — from EVERY entry point
— and cycle_type records what actually ran, never what was merely requested.
Before this gate, the CLI path ran degraded pseudo-deep under a refused
pairing: mechanical softening rewrote memories and heuristic reflection wrote
template thoughts into the graph, while the log claimed a deep cycle.
"""
import json

from mnemos.consolidation.daemon import ConsolidationDaemon


class TestDaemonDeepGate:
    def test_deep_without_client_downgrades_and_says_so(self, store):
        daemon = ConsolidationDaemon(store=store, config={}, llm_client=None)

        stats = daemon.run_cycle(deep=True, agent_id="default")

        assert stats["cycle_type"] == "shallow"
        assert "deep_downgraded" in stats
        for pass_name in ("softening", "belief_review", "belief_formation", "reflection"):
            assert pass_name not in stats["passes_run"]
        assert "connection_discovery" in stats["passes_run"]
        assert "decay" in stats["passes_run"]

    def test_deep_with_client_runs_deep(self, store, stub_llm):
        daemon = ConsolidationDaemon(store=store, config={}, llm_client=stub_llm)

        stats = daemon.run_cycle(deep=True, agent_id="default")

        assert stats["cycle_type"] == "deep"
        assert "deep_downgraded" not in stats
        assert "softening" in stats["passes_run"]
        assert "belief_formation" in stats["passes_run"]

    def test_shallow_request_is_not_marked_downgraded(self, store):
        daemon = ConsolidationDaemon(store=store, config={}, llm_client=None)

        stats = daemon.run_cycle(deep=False, agent_id="default")

        assert stats["cycle_type"] == "shallow"
        assert "deep_downgraded" not in stats

    def test_logged_cycle_type_matches_what_ran(self, store):
        """The durable record never claims a deep that didn't happen."""
        daemon = ConsolidationDaemon(store=store, config={}, llm_client=None)
        daemon.run_cycle(deep=True, agent_id="default")

        conn = store._get_conn()
        row = conn.execute(
            "SELECT stats FROM consolidation_log WHERE pass_name='cycle' "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        logged = json.loads(row[0] if not hasattr(row, "keys") else row["stats"])
        assert logged["cycle_type"] == "shallow"
        assert "deep_downgraded" in logged
