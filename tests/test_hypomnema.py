"""Tests for the scoped hypomnema continuity layer."""

import pytest


class TestHypomnemaStore:
    def test_init_creates_hypomnema_table(self, store):
        conn = store._get_conn()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {r[0] for r in rows}

        assert "hypomnema_entries" in table_names

    def test_write_and_search_hypomnema(self, store):
        entry_id = store.write_hypomnema_entry(
            "Riley and Vektor keep functional memory, hypomnema, and Mnemos distinct.",
            agent_id="vektor",
            person_id="riley",
            project_scope="codex-test",
            domain="foundational",
            tags="memory,continuity",
            confidence=0.9,
            salience=0.8,
            foundational=True,
        )

        results = store.search_hypomnema(
            "functional memory mnemos",
            agent_id="vektor",
            person_id="riley",
            project_scope="codex-test",
        )

        assert results[0]["id"] == entry_id
        assert results[0]["tags"] == ["memory", "continuity"]
        assert results[0]["foundational"] is True

    def test_revise_hypomnema_keeps_revision_history(self, store):
        entry_id = store.write_hypomnema_entry(
            "Hypomnema is just a note.",
            agent_id="vektor",
            person_id="riley",
            project_scope="codex-test",
        )

        store.revise_hypomnema_entry(
            entry_id,
            "Hypomnema is scoped continuity that can revise before promotion.",
            reason="sharpen definition",
            agent_id="vektor",
            person_id="riley",
            project_scope="codex-test",
            confidence=0.85,
            salience=0.7,
        )

        entry = store.get_hypomnema_entry(
            entry_id,
            agent_id="vektor",
            person_id="riley",
            project_scope="codex-test",
        )

        assert entry["revision_count"] == 1
        assert entry["confidence"] == pytest.approx(0.85)
        assert entry["revisions"][0]["prior_content"] == "Hypomnema is just a note."

    def test_revise_hypomnema_tags_kept_by_default_replaced_when_given(self, store):
        """tags=None keeps the entry's tags (the long-standing behavior);
        a value replaces them, normalized like a first write — so a caller
        deepening one entry across revisions can carry the union forward
        instead of freezing the labels at day one."""
        scope = dict(agent_id="vektor", person_id="riley", project_scope="codex-test")
        entry_id = store.write_hypomnema_entry(
            "Hypomnema is just a note.", tags=["memory", "continuity"], **scope
        )

        store.revise_hypomnema_entry(
            entry_id, "Sharpened, same labels.", reason="no tag change", **scope
        )
        entry = store.get_hypomnema_entry(entry_id, **scope)
        assert entry["tags"] == ["memory", "continuity"]

        store.revise_hypomnema_entry(
            entry_id,
            "Deepened — the arc grew a new anchor.",
            reason="carry the union forward",
            tags=["memory", "continuity", " trust "],  # normalized like a write
            **scope,
        )
        entry = store.get_hypomnema_entry(entry_id, **scope)
        assert entry["tags"] == ["memory", "continuity", "trust"]
        assert entry["revision_count"] == 2

    def test_supersede_hypomnema_hides_original_from_active_search(self, store):
        entry_id = store.write_hypomnema_entry(
            "Old continuity claim",
            agent_id="vektor",
            person_id="riley",
            project_scope="codex-test",
        )

        replacement_id = store.supersede_hypomnema_entry(
            entry_id,
            "New continuity claim",
            reason="better evidence",
            agent_id="vektor",
            person_id="riley",
            project_scope="codex-test",
        )

        active = store.search_hypomnema(
            "",
            agent_id="vektor",
            person_id="riley",
            project_scope="codex-test",
        )
        inactive = store.get_hypomnema_entry(
            entry_id,
            agent_id="vektor",
            person_id="riley",
            project_scope="codex-test",
        )

        assert [entry["id"] for entry in active] == [replacement_id]
        assert inactive["active"] is False
        assert inactive["superseded_by"] == replacement_id

    def test_promotion_candidates_require_stability_thresholds(self, store):
        low_id = store.write_hypomnema_entry(
            "Interesting but weak continuity",
            agent_id="vektor",
            person_id="riley",
            project_scope="codex-test",
            confidence=0.7,
            salience=0.6,
            foundational=True,
        )
        high_id = store.write_hypomnema_entry(
            "Foundational continuity ready for Mnemos.",
            agent_id="vektor",
            person_id="riley",
            project_scope="codex-test",
            confidence=0.9,
            salience=0.8,
            foundational=True,
        )

        candidates = store.get_hypomnema_promotion_candidates(
            agent_id="vektor",
            person_id="riley",
            project_scope="codex-test",
        )

        assert [entry["id"] for entry in candidates] == [high_id]
        assert low_id not in [entry["id"] for entry in candidates]
