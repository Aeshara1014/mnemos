"""Tests for EngramStore — SQLite persistence layer."""
import pytest

from mnemos.core.engram import Connection, Engram
from mnemos.core.belief import Belief
from mnemos.core.types import ConnectionRelation, EngramState
from mnemos.store.sqlite_store import EngramStore


class TestEngramStore:
    """EngramStore CRUD operations."""

    def test_init_creates_tables(self, store):
        """Verify store init creates the schema (engrams, connections, beliefs, etc.)."""
        conn = store._get_conn()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {r[0] for r in rows}
        assert "engrams" in table_names
        assert "connections" in table_names
        assert "beliefs" in table_names

    def test_save_and_get_engram(self, store):
        """Round-trip save/get for an engram."""
        engram = Engram(content="Python prefers explicit over implicit")
        store.save_engram(engram)

        loaded = store.get_engram(engram.id)
        assert loaded is not None
        assert loaded.id == engram.id
        assert loaded.content == "Python prefers explicit over implicit"

    def test_fts_search(self, store):
        """Save engram, search by content via FTS5."""
        engram = Engram(content="Riley likes dark mode in all editors")
        store.save_engram(engram)

        results = store.search_fts("dark mode")
        assert len(results) >= 1
        assert any(e.id == engram.id for e in results)

    def test_save_and_get_connection(self, store):
        """Create a typed connection between two engrams and retrieve it."""
        e1 = Engram(content="First memory")
        e2 = Engram(content="Second memory")
        store.save_engram(e1)
        store.save_engram(e2)

        conn_obj = Connection(
            target_id=e2.id,
            relation=ConnectionRelation.SUPPORTS,
            strength=0.7,
        )
        store.save_connection(e1.id, conn_obj)

        connections = store.get_connections(e1.id)
        assert len(connections) >= 1
        assert connections[0].target_id == e2.id
        assert connections[0].relation == ConnectionRelation.SUPPORTS

    def test_save_and_get_belief(self, store):
        """Belief round-trip."""
        belief = Belief(
            content="Type hints improve code quality",
            confidence=0.7,
            domain="technical",
        )
        store.save_belief(belief)

        beliefs = store.get_beliefs()
        assert len(beliefs) >= 1
        assert any(b.id == belief.id for b in beliefs)

        matched = [b for b in beliefs if b.id == belief.id][0]
        assert matched.content == "Type hints improve code quality"
        assert matched.confidence == pytest.approx(0.7)

    def test_count_engrams(self, store):
        """Count engrams by state."""
        e1 = Engram(content="Active memory one")
        e2 = Engram(content="Active memory two")
        store.save_engram(e1)
        store.save_engram(e2)

        count = store.count_engrams()
        assert count >= 2

    def test_delete_engram(self, store):
        """Verify delete removes the engram."""
        engram = Engram(content="Temporary memory to delete")
        store.save_engram(engram)

        # Confirm it exists
        assert store.get_engram(engram.id) is not None

        store.delete_engram(engram.id)

        # Confirm it's gone
        assert store.get_engram(engram.id) is None

    def test_meta_set_get_roundtrip(self, store):
        """get_meta returns None/default when absent; set then get round-trips."""
        assert store.get_meta("nonexistent") is None
        assert store.get_meta("nonexistent", "fallback") == "fallback"

        store.set_meta("watermark", "2026-06-11T00:00:00Z")
        assert store.get_meta("watermark") == "2026-06-11T00:00:00Z"

    def test_meta_overwrite_persists_across_reopen(self, tmp_db):
        """set_meta upserts; the latest value survives a close and reopen."""
        first = EngramStore(tmp_db)
        first.set_meta("watermark", "first-value")
        first.set_meta("watermark", "second-value")
        first.close()

        reopened = EngramStore(tmp_db)
        try:
            assert reopened.get_meta("watermark") == "second-value"
            # The schema_version bookkeeping row is untouched by the meta API.
            assert reopened.get_meta("schema_version") is not None
        finally:
            reopened.close()
