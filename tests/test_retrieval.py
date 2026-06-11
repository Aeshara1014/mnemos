"""Tests for reactive retrieval."""
import pytest


class TestReactiveRetriever:
    """Retrieval tests."""

    def test_recall_empty_db(self, retriever):
        """Querying an empty store returns an empty list."""
        results = retriever.retrieve("anything at all")
        assert results == []

    def test_recall_finds_match(self, encoder, retriever):
        """Encode a memory then retrieve it by cue."""
        encoder.encode(
            content="The Mnemos project uses SQLite with FTS5 for full-text search",
            kind="semantic",
            tags=["mnemos", "architecture"],
        )

        results = retriever.retrieve("SQLite full-text search")
        assert len(results) >= 1
        assert any(
            "SQLite" in r.engram.content or "FTS5" in r.engram.content
            for r in results
        )

    def test_co_retrieval_edges_are_co_activated_not_supports(
        self, store, encoder, retriever
    ):
        """Co-activation is correlation, not evidence.

        Regression for the relation-type monoculture: retrieval used to
        write co-retrieval edges as `supports` at 0.30 unconditionally,
        re-seeding the very monoculture the discovery pass was built to
        fix. They must be `co_activated` until something actually
        classifies them.
        """
        for i in range(2):
            encoder.encode(
                content=f"Spreading activation tuning note number {i} for retrieval",
                kind="semantic",
                tags=["retrieval"],
            )

        results = retriever.retrieve("spreading activation tuning retrieval")
        assert len(results) >= 2, "need co-retrieval for the edge to form"

        retrieval_edges = [
            conn
            for e in store.get_active_engrams(limit=100)
            for conn in e.connections
            if conn.formed_by == "retrieval"
        ]
        assert retrieval_edges, "co-retrieval created no edges"
        assert all(c.relation == "co_activated" for c in retrieval_edges)
        assert not any(c.relation == "supports" for c in retrieval_edges)
