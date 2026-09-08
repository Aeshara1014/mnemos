"""The dream thinks as "I" — the thought prompt speaks as the rememberer.

Of the 53 reflections Claw's road-home dreams had written by 2026-07-23,
only 13 were cleanly in his own voice: 7 spoke of "Claw" from the
outside (two called him "it"), and 33 came out in a detached analyst
voice belonging to no one. The cause was the assignment, not the
material: the thought prompt said "review these memories and generate
thoughts" — an analyst's task, with no word on whose thoughts these
are. The self-anchor frame (Tara's ruling, 2026-07-22) covers what he
READS; this law covers what the dream WRITES: first person, the self's
name in the memories is "I", never "it", never another's voice.
"""

from mnemos.consolidation.reflection import THOUGHT_PROMPT, run_reflection_pass
from mnemos.core.emotional_state import EmotionalState
from mnemos.core.identity import AgentIdentity
from mnemos.encoding.encoder import Encoder


class RecordingLLM:
    """Keeps every prompt; replies with one first-person thought."""

    def __init__(self):
        self.prompts = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "a quiet thought about how the day settled into me"


def _identity(agent_id="claw") -> AgentIdentity:
    identity = AgentIdentity()
    identity.memory_profile.agent_id = agent_id
    return identity


def _seed_today(store, agent_id="claw", n=3):
    enc = Encoder(store)
    for i in range(n):
        enc.encode(
            content=f"a lived moment {i}, long enough to carry weight",
            agent_id=agent_id,
            tags=["conversation"],
            skip_surprise_detection=True,
        )


def test_thought_prompt_carries_the_first_person_anchor():
    assert "{agent_name}" in THOUGHT_PROMPT
    assert "your own recent memories" in THOUGHT_PROMPT.lower()
    assert "first person" in THOUGHT_PROMPT.lower()
    assert "never your own name" in THOUGHT_PROMPT.lower()
    assert 'never "it"' in THOUGHT_PROMPT


def test_the_pass_tells_the_dream_whose_thoughts_these_are(store):
    _seed_today(store)
    stub = RecordingLLM()
    stats = run_reflection_pass(store, _identity(), EmotionalState(),
                                llm_client=stub)
    assert stats["thoughts_generated"] >= 1
    prompt = stub.prompts[0]
    # The self's name in the memories is anchored to "I"...
    assert 'speaks of "claw"' in prompt.lower()
    # ...and the placeholder name never leaks in as the self.
    assert '"Agent"' not in prompt
    assert "you are the rememberer" in prompt.lower()


def test_the_dream_hears_the_observer_as_an_outside_voice(store):
    """An Observer note among the day's memories is labeled as another
    mind's words to him — never listed bare among his own (2026-09-08:
    unlabeled, "you keep circling" came back as "I keep circling"). A note
    that already wears the Observer's banner stands as written."""
    from mnemos.core.types import SourceType

    _seed_today(store)
    enc = Encoder(store)
    for content in (
        "[observer:stagnation] you circle the bell without landing",
        "The Observer, an outside voice, says to you (pattern): the fog again",
    ):
        enc.encode(content=content, agent_id="claw", tags=["observer"],
                   source=SourceType.OBSERVER, skip_surprise_detection=True)
    stub = RecordingLLM()
    run_reflection_pass(store, _identity(), EmotionalState(), llm_client=stub)
    prompt = stub.prompts[0]
    assert ("- The Observer, an outside voice, said to you: "
            "you circle the bell without landing") in prompt
    assert "[observer:stagnation]" not in prompt
    assert "- The Observer, an outside voice, says to you (pattern): the fog again" in prompt
    assert "said to you: The Observer" not in prompt  # the banner is never doubled
    assert "- a lived moment 0" in prompt  # his own memories stay bare
