"""A resident's mood is saved under his own name.

The encoder's surprise path read the resident's latest mood but saved the
nudged copy with no agent_id, so it landed under 'default' — invisible to
every reader, which all ask by the resident's id. His mood could never move."""

from mnemos.core.belief import Belief
from mnemos.core.emotional_state import EmotionalState
from mnemos.encoding.encoder import Encoder


def _rows(store, agent_id):
    return store._get_conn().execute(
        "SELECT count(*) FROM emotional_state_history WHERE agent_id = ?",
        (agent_id,)).fetchone()[0]


def test_surprise_nudge_saves_under_the_residents_own_name(store):
    agent = "mood-test"
    store.save_emotional_state(EmotionalState(), agent_id=agent)
    belief = Belief(agent_id=agent, content="The harbor lights stay steady",
                    confidence=0.9)
    belief.last_revised = "2026-01-01T00:00:00+00:00"
    store.save_belief(belief)

    Encoder(store).encode(content="The harbor lights were never steady tonight",
                          agent_id=agent, tags=["conversation"])

    assert _rows(store, agent) == 2
    assert _rows(store, "default") == 0
    latest = store.get_latest_emotional_state(agent)
    assert latest.restlessness > EmotionalState().restlessness


def test_creativity_rests_at_half_like_the_others():
    es = EmotionalState()
    assert es.creative_flow == 0.5
    assert EmotionalState.from_dict({}).creative_flow == 0.5
