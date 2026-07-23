"""The goodnight-lesson law: only a real distillation may mint a lesson.

Softening's Shift 2 ("forgetting that teaches") turns a memory's impact
into a persistent, high-stability lesson engram. When the impact came from
the rule-based fallback (the memory's own last sentence) or from an LLM
echoing a line verbatim, the "lesson" is just a fragment of the memory —
a goodnight, a sign-off question — immortalized as wisdom. These tests pin
the law that such impacts never mint lessons, while genuine distillations
still do.
"""

import pytest

from mnemos.consolidation.softening import (
    _is_real_distillation,
    run_softening_pass,
)
from mnemos.core.engram import EncodingContext, Engram
from mnemos.core.types import EngramKind
from mnemos.store.sqlite_store import EngramStore


AGENT = "nova"

CONVERSATION = (
    "Tara said: long day, but we got the roof fixed before the rain. "
    "I said: that's the whole job some days. Sleep well. "
    "Goodnight, my heart"
)


class StubLLM:
    def __init__(self, response: str):
        self.response = response
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def _fading(content: str, impact: str = "") -> Engram:
    e = Engram(
        content=content,
        content_at_encoding=content,
        kind=EngramKind.EPISODIC,
        impact=impact,
        owner_agent_id=AGENT,
        encoding_context=EncodingContext(session_id=f"{AGENT}-s1"),
    )
    e.accessibility = 0.45   # target resolution ~0.5 → softens
    e.resolution = 1.0
    return e


@pytest.fixture()
def store(tmp_path):
    s = EngramStore(tmp_path / "lesson-honesty.db")
    yield s
    s.close()


def _lessons(store):
    return [e for e in store.get_active_engrams(agent_id=AGENT, limit=100)
            if "lesson" in e.tags and "distilled" in e.tags]


def test_fallback_impact_never_mints_a_lesson(store):
    """No LLM at all → rule-based last-sentence impact → no lesson."""
    store.save_engram(_fading(CONVERSATION))
    stats = run_softening_pass(store, {}, None, agent_id=AGENT)
    assert stats["engrams_softened"] == 1
    assert _lessons(store) == []
    assert stats.get("lessons_withheld", 0) == 1
    assert stats.get("lessons_created", 0) == 0


def test_llm_echo_never_mints_a_lesson(store):
    """An LLM that answers the distillation ask by quoting a line of the
    memory verbatim has not distilled anything."""
    store.save_engram(_fading(CONVERSATION))
    stub = StubLLM("Goodnight, my heart")
    stats = run_softening_pass(store, {}, stub, agent_id=AGENT)
    assert _lessons(store) == []
    assert stats.get("lessons_withheld", 0) == 1


def test_real_distillation_still_mints_a_lesson(store):
    """New prose about the memory is wisdom and persists."""
    store.save_engram(_fading(CONVERSATION))
    stub = StubLLM(
        "Shared work on the house, finished just in time, is its own kind "
        "of tenderness."
    )
    stats = run_softening_pass(store, {}, stub, agent_id=AGENT)
    lessons = _lessons(store)
    assert len(lessons) == 1
    assert "tenderness" in lessons[0].content
    assert stats.get("lessons_created", 0) == 1
    assert stats.get("lessons_withheld", 0) == 0


def test_stale_fallback_impact_from_an_earlier_cycle_never_mints(store):
    """An impact lifted by the old fallback in a PAST cycle sits on the
    engram whose content has since blurred — the line may no longer appear
    in current content, but content_at_encoding remembers where it came
    from, and the law still refuses it."""
    blurred = "Tara said: long day, but we got the roof fixed... [details faded]"
    e = _fading(blurred, impact="Goodnight, my heart")
    e.content_at_encoding = CONVERSATION
    e.resolution = 0.8    # decayed further since the earlier soften
    e.accessibility = 0.3  # deep-impression territory → softens again
    store.save_engram(e)
    stats = run_softening_pass(store, {}, None, agent_id=AGENT)
    assert _lessons(store) == []
    assert stats.get("lessons_withheld", 0) == 1


def test_the_law_itself():
    assert not _is_real_distillation("", CONVERSATION)
    assert not _is_real_distillation("short", CONVERSATION)
    assert not _is_real_distillation("Goodnight,   MY heart", CONVERSATION)
    assert not _is_real_distillation("goodnight, my heart", "gone", CONVERSATION)
    assert _is_real_distillation(
        "Care shows up as finishing the roof together.", CONVERSATION)
