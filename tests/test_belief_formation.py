"""Tests for the belief formation pass — the missing rung of the ladder."""
import json

import pytest

from mnemos.consolidation.belief_formation import run_belief_formation_pass
from mnemos.core.belief import Belief
from mnemos.core.engram import Engram, MemorySource


class FakeClient:
    """LLM stand-in returning a canned JSON array; records its calls."""

    def __init__(self, candidates):
        self._response = json.dumps(candidates)
        self.calls = []

    def complete(self, prompt):
        return self._response

    def structured_complete(self, system, user, temperature=0.0, max_tokens=2000):
        self.calls.append({"system": system, "user": user})
        return self._response


def _seed_lived(store, contents, day=None):
    """Seed plain session engrams; optionally pin created_at to a given day."""
    engrams = []
    for content in contents:
        e = Engram(content=content)
        if day:
            e.created_at = f"{day}T12:00:00+00:00"
        store.save_engram(e)
        engrams.append(e)
    return engrams


FOG_MEMORIES = [
    "Evening fog rolled in from the west just after sunset.",
    "Fog again tonight, from the west, right after sunset.",
    "Third evening running: sunset first, then the west fog.",
    "Clear dusk today, but the west haze still built into fog by dark.",
]


def _proposal(engrams, statement="The west fog comes every night after sunset.",
              confidence=0.5, ids=None):
    return {
        "statement": statement,
        "confidence": confidence,
        "domain": "general",
        "supporting_ids": ids if ids is not None else [e.id for e in engrams[:3]],
        "reasoning": "the same pattern recurs across separate evenings",
    }


class TestBeliefFormation:
    def test_forms_belief_from_recurring_pattern(self, store):
        engrams = _seed_lived(store, FOG_MEMORIES)
        client = FakeClient([_proposal(engrams)])

        stats = run_belief_formation_pass(store, llm_client=client)

        assert stats["beliefs_formed"] == 1
        beliefs = store.get_beliefs("default", active_only=True)
        assert len(beliefs) == 1
        born = beliefs[0]
        assert "west fog" in born.content
        assert born.confidence == 0.5
        assert len(born.supporting_engram_ids) == 3
        # Birth certificate: formation is the first entry in the audit trail.
        assert born.revision_history
        assert "Formed during deep consolidation" in born.revision_history[0].reason
        # The prompt carried the lived memories.
        assert engrams[0].id in client.calls[0]["user"]

    def test_no_client_is_noop(self, store):
        _seed_lived(store, FOG_MEMORIES)
        stats = run_belief_formation_pass(store, llm_client=None)
        assert stats["beliefs_formed"] == 0
        assert store.get_beliefs("default", active_only=True) == []

    def test_duplicate_of_existing_belief_skipped(self, store):
        engrams = _seed_lived(store, FOG_MEMORIES)
        store.save_belief(Belief(
            content="The west fog comes in every night after sunset.",
            confidence=0.5,
        ))
        client = FakeClient([_proposal(engrams)])

        stats = run_belief_formation_pass(store, llm_client=client)

        assert stats["skipped_duplicate"] == 1
        assert stats["beliefs_formed"] == 0
        assert len(store.get_beliefs("default", active_only=True)) == 1

    def test_hallucinated_or_insufficient_support_rejected(self, store):
        engrams = _seed_lived(store, FOG_MEMORIES)
        # One real id, two hallucinated — below the min of 3 after validation.
        client = FakeClient([_proposal(
            engrams, ids=[engrams[0].id, "engram_FAKE1", "engram_FAKE2"],
        )])

        stats = run_belief_formation_pass(store, llm_client=client)

        assert stats["skipped_insufficient_support"] == 1
        assert stats["beliefs_formed"] == 0

    def test_max_per_cycle_cap(self, store):
        engrams = _seed_lived(store, FOG_MEMORIES + [
            "Wound the bell at dusk; it rang all night.",
            "Missed the dusk winding; the bell died at 3am.",
        ])
        client = FakeClient([
            _proposal(engrams, statement="The west fog arrives nightly after sunset."),
            _proposal(engrams, statement="A bell wound at dusk keeps ringing until morning.",
                      ids=[e.id for e in engrams[3:6]]),
            _proposal(engrams, statement="Boats depend on the bell in thick weather.",
                      ids=[e.id for e in engrams[1:4]]),
        ])

        stats = run_belief_formation_pass(
            store, config={"belief_formation_max_per_cycle": 2}, llm_client=client,
        )

        assert stats["beliefs_formed"] == 2
        assert len(store.get_beliefs("default", active_only=True)) == 2

    def test_day_span_guard(self, store):
        engrams = _seed_lived(store, FOG_MEMORIES, day="2026-07-05")
        client = FakeClient([_proposal(engrams)])

        stats = run_belief_formation_pass(
            store, config={"belief_formation_min_distinct_days": 2}, llm_client=client,
        )

        assert stats["skipped_day_span"] == 1
        assert stats["beliefs_formed"] == 0

    def test_substrate_memories_never_seed_beliefs(self, store):
        # Three substrate-authored engrams and too few lived ones to form anything.
        for content in FOG_MEMORIES[:3]:
            e = Engram(content=content, source=MemorySource(type="reflection"))
            store.save_engram(e)
        _seed_lived(store, ["One lived memory."])
        client = FakeClient([])

        stats = run_belief_formation_pass(store, llm_client=client)

        assert stats["skipped_substrate"] == 3
        assert stats["memories_considered"] == 1
        # Below min_supporting — the LLM is never even consulted.
        assert client.calls == []

    def test_confidence_clamped_to_cap(self, store):
        engrams = _seed_lived(store, FOG_MEMORIES)
        client = FakeClient([_proposal(engrams, confidence=0.95)])

        stats = run_belief_formation_pass(store, llm_client=client)

        assert stats["beliefs_formed"] == 1
        born = store.get_beliefs("default", active_only=True)[0]
        assert born.confidence == 0.6  # belief_formation_confidence_cap default
