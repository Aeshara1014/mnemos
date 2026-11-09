"""The belief check asks marked cacheable (Tara's word, 2026-11-08).

It never hit a cache (0 of 224 calls Nov 1-8). Marked, its words bill at
about 29% of the input price even the first time, with no minimum size.
Same words; a client that can't take the mark is asked as before.
"""

from __future__ import annotations

from types import SimpleNamespace

from mnemos.encoding.llm_classifier import evaluate_beliefs


class Client:
    def __init__(self, takes_mark):
        self.calls = []
        if takes_mark:
            self.takes_cache_mark = True

    def structured_complete(self, system, user, temperature=0.0,
                            max_tokens=2000, timeout=None, **kw):
        self.calls.append(kw)
        return "[]"


def _call(client):
    engram = SimpleNamespace(id="engram_x", content="a new memory", impact="")
    beliefs = [SimpleNamespace(id="belief_1", content="a belief", confidence=0.5)]
    evaluate_beliefs(client, engram, beliefs)


def test_the_belief_check_asks_for_the_mark():
    client = Client(True)
    _call(client)
    assert client.calls == [{"cache": True}]


def test_a_client_without_marks_is_asked_as_before():
    client = Client(False)
    _call(client)
    assert client.calls == [{}]
