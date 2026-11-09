"""Link-finding and the belief check ask the half-price lane first, when
nobody waits on the memory (Tara's word, 2026-11-09).

OpenRouter serves Gemini's "flex" tier at exactly half price. Tested that
day on copies of Quill's memories: pinned to Google Vertex it answered
every ask (10 of 10, none refused) in about 100 s, judged links as the
normal lane does (86% agreement, the normal lane's own figure on the same
asks), and a cache mark there bills at half the marked price too. Google AI
Studio's half-price lane is faster but refused about a third of his
memories, so it is never asked.

So: when the caller says nobody waits, the same ask goes to Vertex's
half-price lane with a long wait. If it fails, stays silent or answers
nothing, the normal lane is asked exactly as before, so a slow lane never
costs a memory its links (law 9).
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from types import SimpleNamespace

from mnemos.encoding import encoder as encoder_module
from mnemos.encoding.encoder import Encoder
from mnemos.encoding.llm_classifier import classify_connections, evaluate_beliefs
from mnemos.llm import OpenRouterClient

GEMINI = "google/gemini-3.1-pro-preview"
USER = "## New Memory\nContent: a\n\nClassify each one."


class _Resp:
    def __init__(self, content):
        self._content = content

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps({"choices": [{"message": {"content": self._content}}]}).encode()


def _posting(monkeypatch, half_price_lane="answers"):
    """Record every ask. half_price_lane: 'answers', 'busy' (503), 'silent'
    (timeout) or 'empty' (no words)."""
    asks = []

    def fake_urlopen(req, timeout=None):
        body = json.loads(req.data.decode())
        asks.append({"body": body, "timeout": timeout})
        if body.get("service_tier") == "flex":
            if half_price_lane == "busy":
                raise urllib.error.HTTPError(req.full_url, 503, "busy", {}, io.BytesIO(b"{}"))
            if half_price_lane == "silent":
                raise TimeoutError("timed out")
            if half_price_lane == "empty":
                return _Resp("")
            return _Resp("from the half-price lane")
        return _Resp("from the normal lane")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return asks


def test_a_patient_ask_goes_to_vertex_on_the_half_price_lane(monkeypatch):
    asks = _posting(monkeypatch)
    client = OpenRouterClient(api_key="k", model=GEMINI)
    out = client.structured_complete("sys", USER, timeout=45, cache=True, half_price=True)
    assert out == "from the half-price lane"
    assert len(asks) == 1
    body = asks[0]["body"]
    assert body["service_tier"] == "flex"
    assert body["provider"] == {"only": ["google-vertex"]}     # never AI Studio
    assert asks[0]["timeout"] == OpenRouterClient.HALF_PRICE_WAIT >= 150
    # the same words, marked as on the normal lane, its last line plain
    parts = body["messages"][1]["content"]
    assert "".join(p["text"] for p in parts) == USER
    assert "cache_control" in parts[0] and "cache_control" not in parts[-1]


def test_a_lane_that_fails_is_asked_again_on_the_normal_lane(monkeypatch):
    for trouble in ("busy", "silent", "empty"):
        asks = _posting(monkeypatch, half_price_lane=trouble)
        client = OpenRouterClient(api_key="k", model=GEMINI)
        out = client.structured_complete("sys", USER, timeout=45, cache=True, half_price=True)
        assert out == "from the normal lane", trouble
        assert len(asks) == 2
        normal = asks[1]
        assert "service_tier" not in normal["body"] and "provider" not in normal["body"]
        assert normal["timeout"] == 45                       # the caller's own cap
        assert normal["body"]["messages"] == asks[0]["body"]["messages"]   # same ask


def test_an_ask_somebody_waits_on_is_unchanged(monkeypatch):
    asks = _posting(monkeypatch)
    client = OpenRouterClient(api_key="k", model=GEMINI)
    assert client.structured_complete("sys", USER, timeout=45, cache=True) == "from the normal lane"
    assert len(asks) == 1 and asks[0]["timeout"] == 45
    assert "service_tier" not in asks[0]["body"] and "provider" not in asks[0]["body"]


def test_other_models_never_take_the_lane(monkeypatch):
    asks = _posting(monkeypatch)
    client = OpenRouterClient(api_key="k", model="x-ai/grok-4.20")
    assert client.structured_complete("sys", USER, half_price=True) == "from the normal lane"
    assert len(asks) == 1 and "service_tier" not in asks[0]["body"]


class _Spy:
    takes_cache_mark = True
    takes_half_price = True

    def __init__(self):
        self.calls = []

    def structured_complete(self, system, user, temperature=0.0,
                            max_tokens=2000, timeout=None, **kw):
        self.calls.append(kw)
        return "[]"


def _memories():
    new = SimpleNamespace(id="engram_n", content="a new memory", impact="", kind="episodic")
    old = SimpleNamespace(id="engram_c", content="an old memory", impact="", kind="episodic",
                          created_at="2026-11-01T00:00:00+00:00")
    return new, [old]


def test_the_link_finder_and_the_belief_check_pass_it_on_only_when_asked():
    new, cands = _memories()
    beliefs = [SimpleNamespace(id="belief_1", content="a belief", confidence=0.5)]
    spy = _Spy()
    classify_connections(spy, new, cands, cache=True, half_price=True)
    evaluate_beliefs(spy, new, beliefs, half_price=True)
    classify_connections(spy, new, cands, cache=True)
    evaluate_beliefs(spy, new, beliefs)
    assert spy.calls == [{"cache": True, "half_price": True}, {"cache": True, "half_price": True},
                         {"cache": True}, {"cache": True}]


def test_a_client_without_the_lane_is_asked_as_before():
    class Plain:
        def __init__(self):
            self.calls = []

        def structured_complete(self, system, user, temperature=0.0,
                                max_tokens=2000, timeout=None):
            self.calls.append(1)
            return "[]"
    new, cands = _memories()
    plain = Plain()
    classify_connections(plain, new, cands, cache=True, half_price=True)
    evaluate_beliefs(plain, new, [SimpleNamespace(id="b", content="c", confidence=0.5)],
                     half_price=True)
    assert plain.calls == [1, 1]


def test_only_a_memory_nobody_waits_on_asks_the_lane(store, monkeypatch):
    links, beliefs = [], []

    def spy_links(llm_client, engram, candidates, **kwargs):
        links.append(kwargs)
        return []

    def spy_beliefs(llm_client, engram, active, **kwargs):
        beliefs.append(kwargs)
        return []
    monkeypatch.setattr(encoder_module, "classify_connections", spy_links)
    monkeypatch.setattr(encoder_module, "evaluate_beliefs", spy_beliefs)
    monkeypatch.setattr(store, "get_beliefs",
                        lambda agent_id, active_only=True: [SimpleNamespace(id="b1")])
    enc = Encoder(store, llm_client=object())
    enc.encode(content="The keeper logged the storm in the green ledger at midnight.")
    enc.encode(content="After the storm the keeper repainted the green ledger shelf.",
               half_price=True)
    assert links == [{"cache": True, "half_price": True}]     # the first had no candidates
    assert beliefs == [{}, {"half_price": True}]


def test_an_encoder_with_the_older_shape_is_called_as_before(store):
    """The house's seeding door overrides link-finding with the old
    two-argument shape; a memory somebody waits on must reach it unchanged."""
    class Unlinked(Encoder):
        def _discover_connections(self, engram, store):
            return []
    Unlinked(store, llm_client=None).encode(content="A seed laid down with no links.")
