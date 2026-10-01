"""Night thoughts join the meaning index; worn beliefs stop guarding their words.

2026-09-30: the reflection pass encoded its thoughts with a bare Encoder —
no meaning index, no link reader — so every night thought could be found
only by its exact words. And a belief the evidence had knocked to nothing
still told the night "do not rephrase me", blocking a truer wording."""

from mnemos.consolidation import reflection
from mnemos.consolidation.belief_formation import run_belief_formation_pass
from mnemos.consolidation.reflection import run_reflection_pass
from mnemos.core.belief import Belief
from mnemos.core.emotional_state import EmotionalState
from mnemos.core.identity import AgentIdentity
from mnemos.encoding.encoder import Encoder

from tests.test_belief_formation import FOG_MEMORIES, FakeClient, _proposal, _seed_lived

THOUGHT = "I keep returning to the harbor light and what it asks of me"


class RecordingIndex:
    def __init__(self):
        self.indexed = []

    def index_engram(self, engram_id, content):
        self.indexed.append((engram_id, content))
        return True

    def search(self, *args, **kwargs):
        return []


def test_a_night_thought_gets_the_meaning_index(store, monkeypatch):
    agent = "night-index"
    identity = AgentIdentity()
    identity.memory_profile.agent_id = agent
    for moment in ("a quiet evening by the water", "tea on the gallery rail",
                   "a letter from down the hall"):
        Encoder(store).encode(content=moment, agent_id=agent,
                              tags=["conversation"], skip_surprise_detection=True)
    monkeypatch.setattr(reflection, "_generate_template_thoughts",
                        lambda recent: [THOUGHT])
    index = RecordingIndex()

    stats = run_reflection_pass(store, identity, EmotionalState(), llm_client=None,
                                embedding_index=index)
    assert stats["thoughts_generated"] == 1
    assert [c for _, c in index.indexed] == [THOUGHT]


def test_a_worn_out_belief_no_longer_blocks_a_truer_wording(store):
    engrams = _seed_lived(store, FOG_MEMORIES)
    store.save_belief(Belief(content="The west fog comes in every night after sunset.",
                             confidence=0.0))
    client = FakeClient([_proposal(engrams)])

    stats = run_belief_formation_pass(store, llm_client=client)

    assert stats["beliefs_formed"] == 1
    assert "every night after sunset" not in client.calls[0]["user"].split(
        "EXISTING BELIEFS")[1].split("Propose")[0]
    worn = [b for b in store.get_beliefs("default", active_only=True) if b.confidence == 0.0]
    assert len(worn) == 1                        # kept on record, untouched


def test_a_living_belief_still_guards_its_words(store):
    engrams = _seed_lived(store, FOG_MEMORIES)
    store.save_belief(Belief(content="The west fog comes in every night after sunset.",
                             confidence=0.3))
    stats = run_belief_formation_pass(store, llm_client=FakeClient([_proposal(engrams)]))
    assert stats["skipped_duplicate"] == 1
