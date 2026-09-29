"""Night thoughts are not evidence against his own beliefs.

The reflection pass encoded its thoughts without skip_surprise_detection,
and with no model bound the encoder's heuristic surprise check matched
negation words as substrings — "not" inside "notice". Every night his own
reflections knocked his beliefs down 0.05 and wired CONTRADICTS edges. The
pass now skips surprise detection, like every other self-generated encode."""

from mnemos.consolidation import reflection
from mnemos.consolidation.reflection import run_reflection_pass
from mnemos.core.belief import Belief
from mnemos.core.emotional_state import EmotionalState
from mnemos.core.identity import AgentIdentity
from mnemos.core.types import ConnectionRelation
from mnemos.encoding.encoder import Encoder


THOUGHT = "I notice the lighthouse keeps its steady watch over the harbor tonight"


def test_night_thought_leaves_beliefs_untouched(store, monkeypatch):
    agent = "night-test"
    identity = AgentIdentity()
    identity.memory_profile.agent_id = agent

    belief = Belief(agent_id=agent, content="The lighthouse keeps a steady watch",
                    confidence=0.95)
    belief.last_revised = "2026-01-01T00:00:00+00:00"  # outside the 6h cooldown
    store.save_belief(belief)
    history_before = list(belief.revision_history)

    for moment in ("a quiet evening by the water", "tea on the gallery rail",
                   "a letter from down the hall"):  # the pass needs 3 recent
        Encoder(store).encode(content=moment, agent_id=agent,
                              tags=["conversation"], skip_surprise_detection=True)
    monkeypatch.setattr(reflection, "_generate_template_thoughts",
                        lambda recent: [THOUGHT])

    stats = run_reflection_pass(store, identity, EmotionalState(), llm_client=None)
    assert stats["thoughts_generated"] == 1

    after = store.get_beliefs(agent, active_only=True)[0]
    assert after.confidence == 0.95
    assert after.revision_history == history_before

    thought = next(e for e in store.get_active_engrams(agent_id=agent, limit=20)
                   if e.content == THOUGHT)
    assert thought.encoding_context.surprise_level == 0
    assert not [c for c in thought.connections
                if c.relation == ConnectionRelation.CONTRADICTS]
