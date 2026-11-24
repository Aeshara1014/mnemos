"""The encoder says which of a memory's checks failed (her word, Nov 23, 2026).

On the Flash night the link check and the belief check both failed (a night
model with no working door), and the memory was saved with no links while the
house said only "memory made". The engine already keeps a failed call apart
from an empty answer (law 9); this hands that fact to the house, the same way
beliefs_supported does, so the feed can say so. The memory itself is still
saved: a failed check never costs it.
"""

from mnemos.core.belief import Belief
from mnemos.encoding.encoder import Encoder


class DoorlessClient:
    """A night model with no working door: every call fails, as Ollama's 404 did."""

    def structured_complete(self, system, user, temperature=0.0,
                            max_tokens=2000, timeout=None):
        raise RuntimeError("HTTP Error 404: Not Found")


class QuietClient:
    """A working model that finds nothing: an empty answer, not a failure."""

    def structured_complete(self, system, user, temperature=0.0,
                            max_tokens=2000, timeout=None):
        return "[]"


def _two_memories(encoder):
    encoder.encode(content="the obsidian shards on the croft windowsill")
    return encoder.encode(content="she asked about the obsidian shards again")


def test_both_failed_checks_are_named(store):
    store.save_belief(Belief(agent_id="default", content="toy stance",
                             confidence=0.4, domain="idea"))
    encoder = Encoder(store, llm_client=DoorlessClient())
    second = _two_memories(encoder)
    assert encoder.checks_failed == ["links", "beliefs"]
    assert store.get_engram(second.id) is not None   # the memory stands


def test_an_empty_answer_is_not_a_failed_check(store):
    store.save_belief(Belief(agent_id="default", content="toy stance",
                             confidence=0.4, domain="idea"))
    encoder = Encoder(store, llm_client=DoorlessClient())
    _two_memories(encoder)
    encoder._llm_client = QuietClient()
    encoder.encode(content="the obsidian shards, a third time")
    assert encoder.checks_failed == []               # fresh for each memory


def test_no_model_at_all_is_not_a_failed_check(store):
    encoder = Encoder(store, llm_client=None)
    _two_memories(encoder)
    assert encoder.checks_failed == []
