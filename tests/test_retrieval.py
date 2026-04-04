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
