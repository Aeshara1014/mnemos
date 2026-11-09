"""The link-finder's ask goes marked cacheable when a memory is made
(Tara's word, 2026-11-08, the money comb's step 1).

Link-finding after each new memory was the biggest uncached call in the
house (~3¢ each, 0% cached). OpenRouter bills a marked prompt at about 29%
of the input price even the first time it is sent, with no minimum size
(her export, and a filler-text probe the same night). Only the encoder asks
for the mark: the night's discovery and re-sort send exactly what they sent
before. The words the model reads are the same; a refused mark is asked
again plain, so a memory never loses its links to it.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from types import SimpleNamespace

from mnemos.encoding import encoder as encoder_module
from mnemos.encoding.encoder import Encoder
from mnemos.encoding.llm_classifier import classify_connections
from mnemos.llm import OpenRouterClient

ANSWER = [{"candidate_id": "engram_c", "relation": "EXTENDS", "direction": "forward",
           "confidence": 0.9, "reasoning": "it goes further"}]


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._payload).encode()


def _posting(monkeypatch, refuse_marked=False):
    bodies = []

    def fake_urlopen(req, timeout=None):
        body = json.loads(req.data.decode())
        bodies.append(body)
        if refuse_marked and isinstance(body["messages"][1]["content"], list):
            raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(b"{}"))
        return _Resp({"choices": [{"message": {"content": json.dumps(ANSWER)}}]})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return bodies


def _memories():
    new = SimpleNamespace(id="engram_n", content="a new memory", impact="", kind="episodic")
    old = SimpleNamespace(id="engram_c", content="an old memory", impact="", kind="episodic",
                          created_at="2026-11-01T00:00:00+00:00")
    return new, [old]


def test_the_marked_ask_carries_the_same_words(monkeypatch):
    bodies = _posting(monkeypatch)
    client = OpenRouterClient(api_key="k", model="google/gemini-3.1-pro-preview")
    new, cands = _memories()
    classify_connections(client, new, cands)
    classify_connections(client, new, cands, cache=True)
    plain, marked = bodies[0]["messages"][1]["content"], bodies[1]["messages"][1]["content"]
    assert isinstance(plain, str)
    # 2026-11-09: in two pieces, the last line plain (a mark that closes
    # the ask bills double; tests/test_never_end_on_a_mark.py).
    assert "".join(p["text"] for p in marked) == plain
    assert marked[0]["cache_control"] == {"type": "ephemeral"}
    assert marked[-1] == {"type": "text", "text": plain[plain.rstrip().rfind("\n") + 1:]}
    assert bodies[0]["messages"][0] == bodies[1]["messages"][0]     # same instructions


def test_other_models_stay_plain(monkeypatch):
    bodies = _posting(monkeypatch)
    client = OpenRouterClient(api_key="k", model="anthropic/claude-sonnet-4-6")
    new, cands = _memories()
    classify_connections(client, new, cands, cache=True)
    assert isinstance(bodies[0]["messages"][1]["content"], str)


def test_a_refused_mark_is_asked_again_plain_and_keeps_the_links(monkeypatch):
    bodies = _posting(monkeypatch, refuse_marked=True)
    client = OpenRouterClient(api_key="k", model="google/gemini-3.1-pro-preview")
    new, cands = _memories()
    found = classify_connections(client, new, cands, cache=True)
    assert len(bodies) == 2 and isinstance(bodies[1]["messages"][1]["content"], str)
    assert [c.candidate_id for c in found] == ["engram_c"]


def test_a_client_without_marks_still_answers():
    class Plain:
        def structured_complete(self, system, user, temperature=0.0,
                                max_tokens=2000, timeout=None):
            return json.dumps(ANSWER)
    new, cands = _memories()
    assert [c.candidate_id for c in classify_connections(Plain(), new, cands, cache=True)] == ["engram_c"]


def test_only_the_encoder_asks_for_the_mark(store, monkeypatch):
    asked = []

    def spy(llm_client, engram, candidates, **kwargs):
        asked.append(kwargs)
        return []
    monkeypatch.setattr(encoder_module, "classify_connections", spy)
    first = Encoder(store, llm_client=object())
    first.encode(content="The keeper logged the storm in the green ledger at midnight.")
    first.encode(content="After the storm the keeper repainted the green ledger shelf.")
    assert asked and all(kw.get("cache") is True for kw in asked)
