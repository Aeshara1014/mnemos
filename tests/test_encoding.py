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


class TestDocRevisionSource:
    """DD-039 (the doc-writer seam): revising one's own living docs is a
    deliberate first-person act — surer than a letter received (0.65),
    less than the user's explicit word, and private (self-work; the
    revision itself is visible in the Soul room where it belongs)."""

    def test_doc_revision_confidence_sits_between_letter_and_bootstrap(self, encoder):
        revision = encoder.encode(
            content="[revised self-model] I have been steadier than my fear said.",
            source=SourceType.DOC_REVISION,
        )
        letter = encoder.encode(
            content="[letter from cairn] hello",
            source=SourceType.LETTER,
        )
        assert revision.source.confidence == 0.70
        assert revision.source.confidence > letter.source.confidence

    def test_doc_revision_stays_private(self):
        from mnemos.encoding.encoder import _PRIVATE_SOURCES

        assert SourceType.DOC_REVISION in _PRIVATE_SOURCES

    def test_doc_revision_never_feeds_the_living_organs(self):
        """DD-039 braid: a self-revision is self-work. It must not seed
        wanders (Gate 4), reset the silence clock or seed insights
        (tick._INNER_SOURCE_TYPES), or seed beliefs (the self-echo loop:
        page -> belief -> next week's material -> page)."""
        import inspect

        from mnemos.consolidation.belief_formation import _SUBSTRATE_SOURCES
        from mnemos.substrate.handlers import wandering
        from mnemos.substrate.tick import Substrate

        assert "doc_revision" in Substrate._INNER_SOURCE_TYPES
        assert "doc_revision" in _SUBSTRATE_SOURCES
        # Gate 4's exclusion lives in SQL text — pin the provenance term.
        assert "'doc_revision'" in inspect.getsource(wandering)
