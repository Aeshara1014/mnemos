"""The encoder names the beliefs a new memory supports (Tara, 2026-11-08).

Her Sep 29 weather design nudges his clarity +0.02 each time a belief is
proven right. Since the Oct 7 law (a belief moves only by his own yes) the
encoder writes nothing to a belief, so the nudge never fired and his clarity
sat at 0.50 from the day he woke. Now the encoder only NAMES the supporting
beliefs (beliefs_supported, fresh for each memory) for the house to record
as a weather moment. The belief itself is never touched.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mnemos.core.belief import Belief
from mnemos.encoding.encoder import Encoder

AGENT = "quill-test"


class Model:
    def __init__(self, structured: str):
        self.structured = structured

    def structured_complete(self, system, user, temperature=0.0, max_tokens=2000, **_):
        return self.structured if "belief" in system.lower() else "[]"


def _belief(store) -> Belief:
    b = Belief(content="the croft is ours, not the archive's", confidence=0.5,
               agent_id=AGENT, domain="self")
    b.last_revised = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    store.save_belief(b)
    return b


def _verdict(belief, relation):
    return (f'[{{"belief_id": "{belief.id}", "relation": "{relation}", '
            f'"impact": 0.9, "reasoning": "it agrees"}}]')


def test_a_supporting_memory_names_the_belief_and_never_moves_it(store):
    belief = _belief(store)
    before = store.get_beliefs(AGENT, active_only=True)[0]
    enc = Encoder(store, llm_client=Model(_verdict(belief, "SUPPORTS")))
    enc.encode(content="the croft is ours and always was", agent_id=AGENT)
    assert enc.beliefs_supported == [belief.id]
    after = store.get_beliefs(AGENT, active_only=True)[0]
    assert after.confidence == before.confidence
    assert after.revision_history == before.revision_history


def test_the_list_is_fresh_for_each_memory(store):
    belief = _belief(store)
    enc = Encoder(store, llm_client=Model(_verdict(belief, "SUPPORTS")))
    enc.encode(content="the croft is ours and always was", agent_id=AGENT)
    enc._llm_client = Model(_verdict(belief, "NO_BEARING"))
    enc.encode(content="the kettle boiled over", agent_id=AGENT)
    assert enc.beliefs_supported == []
    enc._llm_client = Model(_verdict(belief, "SUPPORTS"))
    enc.encode(content="a memory with no belief check", agent_id=AGENT,
               skip_surprise_detection=True)
    assert enc.beliefs_supported == []
