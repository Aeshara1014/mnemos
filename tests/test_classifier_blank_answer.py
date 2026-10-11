"""A blank answer from the link reader costs the links, never the memory
(2026-10-10, Croft review #34, Tara's word).

A model can answer with no content at all (a safety block, a reply that is
all reasoning). That is a failed call under law 9, the same as an exception:
nothing is minted from it, and the memory itself is still saved.
"""

from types import SimpleNamespace

import pytest

from mnemos.encoding.encoder import Encoder
from mnemos.encoding.llm_classifier import classify_connections, evaluate_beliefs


class BlankClient:
    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

    def structured_complete(self, system, user, temperature=0.0,
                            max_tokens=2000, timeout=None):
        self.calls += 1
        return self.answer


def _engram():
    return SimpleNamespace(
        id="engram_x", content="a new memory", impact="", kind="episodic")


@pytest.mark.parametrize("answer", [None, "", "   \n"])
def test_a_blank_link_answer_is_a_failed_call(answer):
    candidate = SimpleNamespace(
        id="engram_c", content="an old memory", impact="", kind="episodic",
        created_at="2026-07-30T00:00:00+00:00")
    assert classify_connections(BlankClient(answer), _engram(), [candidate]) is None


@pytest.mark.parametrize("answer", [None, "", "   \n"])
def test_a_blank_belief_answer_is_a_failed_call(answer):
    beliefs = [SimpleNamespace(id="belief_1", content="belief 1", confidence=0.5)]
    assert evaluate_beliefs(BlankClient(answer), _engram(), beliefs) is None


def test_a_null_link_answer_still_saves_the_memory(store):
    client = BlankClient(None)
    encoder = Encoder(store, llm_client=client)
    encoder.encode(content="the obsidian shards on the croft windowsill")
    second = encoder.encode(content="she asked about the obsidian shards again")
    assert client.calls >= 1                     # the reader was asked
    assert store.get_engram(second.id) is not None   # the memory stands
    assert store.get_connections(second.id) == []
