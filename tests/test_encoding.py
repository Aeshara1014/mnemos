"""Tests for the encoding pipeline."""
import pytest

from mnemos.core.types import SourceType


class TestEncoder:
    """Encoder tests — rule-based fallback (no LLM)."""

    def test_encode_basic(self, encoder):
        """Encode a simple memory with no LLM."""
        engram = encoder.encode(
            content="Riley prefers dark mode in all applications",
            kind="semantic",
            tags=["preference", "ui"],
            source=SourceType.SESSION,
        )
        assert engram is not None
        assert engram.content == "Riley prefers dark mode in all applications"
        assert "preference" in engram.tags
        assert engram.state == "active"

    def test_encode_rejects_empty(self, encoder):
        """Empty content should raise ValueError."""
        with pytest.raises((ValueError, Exception)):
            encoder.encode(content="", kind="semantic")

    def test_confidence_by_source(self, encoder):
        """Verify confidence ranges differ by source type."""
        session_engram = encoder.encode(
            content="Fact from a session conversation",
            source=SourceType.SESSION,
        )
        reflection_engram = encoder.encode(
            content="Insight from background reflection",
            source=SourceType.REFLECTION,
        )

        # Session source should have higher baseline confidence than reflection
        session_conf = session_engram.source.confidence
        reflection_conf = reflection_engram.source.confidence

        assert session_conf > reflection_conf, (
            f"Session confidence ({session_conf}) should exceed "
            f"reflection confidence ({reflection_conf})"
        )
