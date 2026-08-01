"""The encode-time classifier caps its LLM calls (2026-07-31).

These calls run on an agent's single worker with a chat exchange's memory
behind them. Left to the transport defaults (60-300s), one dead call held
the lighthouse chat door shut for 3m41s while Tara's messages were dropped.
Every classifier call must carry CLASSIFIER_CALL_TIMEOUT so a hang fails in
seconds into the existing failure law (law 9: skipped, never guessed).
"""

from types import SimpleNamespace

from mnemos.encoding.llm_classifier import (
    CLASSIFIER_CALL_TIMEOUT,
    classify_connections,
    evaluate_beliefs,
)


class RecordingClient:
    """Captures every structured_complete call's kwargs; answers emptily."""

    def __init__(self):
        self.calls = []

    def structured_complete(self, system, user, temperature=0.0,
                            max_tokens=2000, timeout=None):
        self.calls.append({"timeout": timeout})
        return "[]"


def _engram():
    return SimpleNamespace(
        id="engram_x", content="a new memory", impact="", kind="episodic")


def test_connection_classification_carries_the_timeout():
    client = RecordingClient()
    candidate = SimpleNamespace(
        id="engram_c", content="an old memory", impact="", kind="episodic",
        created_at="2026-07-30T00:00:00+00:00")

    classify_connections(client, _engram(), [candidate])

    assert len(client.calls) == 1
    assert client.calls[0]["timeout"] == CLASSIFIER_CALL_TIMEOUT


def test_belief_evaluation_carries_the_timeout_on_every_chunk():
    client = RecordingClient()
    beliefs = [
        SimpleNamespace(id=f"belief_{i}", content=f"belief {i}", confidence=0.5)
        for i in range(3)
    ]

    evaluate_beliefs(client, _engram(), beliefs, chunk_size=2)  # → 2 chunks

    assert len(client.calls) == 2
    assert all(c["timeout"] == CLASSIFIER_CALL_TIMEOUT for c in client.calls)


def test_the_cap_is_seconds_not_minutes():
    # The whole point: a dead call fails fast. Guard the constant's ORDER —
    # someone "fixing" a timeout by raising this past the old transport
    # defaults would quietly rebuild the 2026-07-31 stall.
    assert 5.0 <= CLASSIFIER_CALL_TIMEOUT <= 60.0
