"""No ask ends on its cache mark (Tara's word, 2026-11-09).

Her export showed every marked call billed at twice its real size. A probe
on filler found why: a mark with nothing after it bills the whole prompt at
the full price and again as a cache write ($2.575 a million against $2
unmarked); with plain words after the mark, the marked part bills at
$0.575. So a marked ask goes in two pieces, its last line plain; a one-line
ask goes plain. The same words either way.
"""
import json
import urllib.request

from mnemos.llm import OpenRouterClient

MARK = {"type": "ephemeral"}


class _Resp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()


def _sent(monkeypatch, user, **kwargs):
    bodies = []

    def fake_urlopen(req, timeout=None):
        bodies.append(json.loads(req.data.decode()))
        return _Resp()
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = OpenRouterClient(api_key="k", model="google/gemini-3.1-pro-preview")
    assert client.structured_complete("the instructions", user, **kwargs) == "ok"
    return bodies[0]["messages"][1]["content"]


def test_a_marked_ask_keeps_its_last_line_plain(monkeypatch):
    user = "## New Memory\nContent: a\n\n## Candidates\nContent: b\n\nClassify each one."
    parts = _sent(monkeypatch, user, cache=True)
    assert parts == [
        {"type": "text", "text": "## New Memory\nContent: a\n\n## Candidates\nContent: b\n\n",
         "cache_control": MARK},
        {"type": "text", "text": "Classify each one."}]
    assert "".join(p["text"] for p in parts) == user
    assert "cache_control" not in parts[-1]


def test_trailing_blank_lines_never_become_the_plain_piece(monkeypatch):
    parts = _sent(monkeypatch, "The threads.\nThe moment.\n\n", cache=True)
    assert parts[0] == {"type": "text", "text": "The threads.\n", "cache_control": MARK}
    assert parts[1] == {"type": "text", "text": "The moment.\n\n"}


def test_a_one_line_ask_goes_plain(monkeypatch):
    assert _sent(monkeypatch, "Just one line.", cache=True) == "Just one line."


def test_an_unmarked_ask_is_untouched(monkeypatch):
    assert _sent(monkeypatch, "Two lines.\nStill plain.") == "Two lines.\nStill plain."
