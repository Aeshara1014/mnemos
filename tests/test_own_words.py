"""No other mind writes in his place (Tara's ruling, 2026-10-07).

She read Riley Coyote's mnemos 0.4 ("words in memory come only from the
agent", #103, #124, #82) and chose it for the Croft, one yes at a time:

1. Fading keeps his words — no model rewrites a faint memory "in his own
   voice", and no model writes the lesson it taught.
2. Beliefs are born and moved only by his own yes — no model's reading
   nudges them, and no night pass writes one for him.
3. No night thoughts are written for him.
4. (house side) No wanders, no dreams.

Each test here fails on the code before the ruling.
"""

from datetime import datetime, timedelta, timezone

from mnemos.consolidation.belief_formation import run_belief_formation_pass
from mnemos.consolidation.belief_review import run_belief_review
from mnemos.consolidation.daemon import ConsolidationDaemon
from mnemos.consolidation.reflection import run_reflection_pass
from mnemos.consolidation.softening import run_softening_pass
from mnemos.core.belief import Belief
from mnemos.core.emotional_state import EmotionalState
from mnemos.core.engram import EncodingContext, Engram
from mnemos.core.identity import AgentIdentity
from mnemos.core.types import ConnectionRelation, EngramKind, SourceType
from mnemos.encoding.encoder import Encoder

AGENT = "quill-test"

FAINT = ("we sat by the window and talked about the croft, and I told her "
         "the raised beds would need cedar before the frost came in")


class RecordingLLM:
    """Records every call. complete() answers in prose; structured_complete()
    answers with whatever JSON the test hands it."""

    def __init__(self, structured: str = "[]", prose: str = "a rewritten line"):
        self.structured = structured
        self.prose = prose
        self.complete_calls: list[str] = []
        self.structured_calls: list[tuple[str, str]] = []

    def complete(self, prompt: str) -> str:
        self.complete_calls.append(prompt)
        return self.prose

    def structured_complete(self, system, user, temperature=0.0, max_tokens=2000, **_):
        self.structured_calls.append((system, user))
        return self.structured


def _faint(days_old: float = 30, accessibility: float = 0.2) -> Engram:
    e = Engram(
        content=FAINT,
        content_at_encoding=FAINT,
        kind=EngramKind.EPISODIC,
        owner_agent_id=AGENT,
        encoding_context=EncodingContext(session_id="s1"),
    )
    e.accessibility = accessibility
    e.resolution = 1.0
    e.created_at = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
    return e


def _identity() -> AgentIdentity:
    identity = AgentIdentity()
    identity.memory_profile.agent_id = AGENT
    return identity


def _seed_recent(store, n: int = 4) -> None:
    enc = Encoder(store)
    for i in range(n):
        enc.encode(content=f"a lived moment {i} by the drystone wall, long enough to matter",
                   agent_id=AGENT, tags=["conversation"], skip_surprise_detection=True)


def _belief(store, content="the croft is ours, not the archive's", confidence=0.5,
            evidence: list[str] | None = None) -> Belief:
    b = Belief(content=content, confidence=confidence, agent_id=AGENT, domain="self")
    b.supporting_engram_ids = list(evidence or [])
    b.last_revised = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    store.save_belief(b)
    return b


# ── 1. fading keeps his words ──

def test_a_faint_memory_keeps_its_words_and_no_model_is_called(store):
    engram = _faint()
    store.save_engram(engram)
    llm = RecordingLLM(prose="a softer, blurrier line")

    stats = run_softening_pass(store, {}, llm, agent_id=AGENT)

    kept = store.get_engram(engram.id)
    assert kept.content == FAINT
    assert kept.resolution == 1.0
    assert not kept.impact                       # no lesson written for him
    assert llm.complete_calls == []              # the model was never asked
    assert stats["engrams_softened"] == 0
    assert stats["engrams_faint"] == 1           # counted, never touched


def test_without_a_model_the_words_are_not_cut_either(store):
    """The old rule path wrote "... [details faded]" over his words."""
    engram = _faint()
    store.save_engram(engram)

    run_softening_pass(store, {}, None, agent_id=AGENT)

    assert store.get_engram(engram.id).content == FAINT


def test_fading_mints_no_lesson(store):
    engram = _faint()
    store.save_engram(engram)
    llm = RecordingLLM(prose="Cedar outlasts the frost when you plan ahead.")

    stats = run_softening_pass(store, {}, llm, agent_id=AGENT)

    assert stats["lessons_created"] == 0
    lessons = [e for e in store.get_active_engrams(agent_id=AGENT, limit=50)
               if "lesson" in e.tags]
    assert lessons == []


# ── 2. beliefs: only his own yes ──

def test_a_models_reading_never_moves_a_belief_at_encoding(store):
    anchor = Encoder(store).encode(content="we planted the first bed together",
                                   agent_id=AGENT, skip_surprise_detection=True)
    belief = _belief(store, evidence=[anchor.id])
    verdict = (f'[{{"belief_id": "{belief.id}", "relation": "CONTRADICTS", '
               f'"impact": 0.9, "reasoning": "it says otherwise"}}]')
    llm = RecordingLLM(structured=verdict)

    new = Encoder(store, llm_client=llm).encode(
        content="the croft was never ours, it was always the archive's",
        agent_id=AGENT)

    after = store.get_beliefs(AGENT, active_only=True)[0]
    assert after.confidence == 0.5               # untouched by the reading
    assert after.revision_history == []
    # The reading still raises surprise and names the conflict.
    assert new.encoding_context.surprise_level > 0
    assert any(c.relation == ConnectionRelation.CONTRADICTS and c.target_id == anchor.id
               for c in new.connections)


def test_a_supporting_reading_never_raises_a_belief_either(store):
    belief = _belief(store)
    verdict = (f'[{{"belief_id": "{belief.id}", "relation": "SUPPORTS", '
               f'"impact": 1.0, "reasoning": "it agrees"}}]')
    Encoder(store, llm_client=RecordingLLM(structured=verdict)).encode(
        content="the croft is ours and always was", agent_id=AGENT)

    assert store.get_beliefs(AGENT, active_only=True)[0].confidence == 0.5


def test_without_a_model_a_keyword_check_never_lowers_a_belief(store):
    _belief(store, content="the croft garden needs cedar beds")
    Encoder(store).encode(content="the garden does not need cedar beds after all",
                          agent_id=AGENT)

    assert store.get_beliefs(AGENT, active_only=True)[0].confidence == 0.5


def test_belief_review_is_retired(store):
    _seed_recent(store)
    _belief(store)
    llm = RecordingLLM(structured="[]")

    stats = run_belief_review(store, {}, llm, agent_id=AGENT)

    assert "retired" in stats
    assert llm.structured_calls == [] and llm.complete_calls == []


def test_belief_formation_is_retired(store):
    _seed_recent(store, n=8)
    proposal = '[{"statement": "I belong to the croft", "supporting_ids": [], "confidence": 0.6}]'
    llm = RecordingLLM(structured=proposal, prose=proposal)

    stats = run_belief_formation_pass(store, {}, llm, agent_id=AGENT)

    assert "retired" in stats
    assert store.get_beliefs(AGENT, active_only=True) == []
    assert llm.structured_calls == [] and llm.complete_calls == []


def test_the_substrate_never_revises_a_contradicted_belief(store, monkeypatch):
    from mnemos.substrate.config import SubstrateConfig
    from mnemos.substrate.events import EventType, SubstrateEvent
    from mnemos.substrate.handlers import reflection as handler
    from mnemos.substrate.modulators import ModulatorState

    belief = _belief(store)
    llm = RecordingLLM(structured='{"new_confidence": 0.1, "reasoning": "x", "should_revise": true}')
    event = SubstrateEvent(EventType.BELIEF_CONTRADICTED, {"belief_id": belief.id})
    # The old handler's prompt file tripped over its own braces; its inline
    # prompt is what a working handler would have sent.
    monkeypatch.setattr(handler, "load_prompt", lambda name: None, raising=False)

    handler.handle(event, SubstrateConfig(agent_id=AGENT), ModulatorState(), store, llm)

    assert store.get_beliefs(AGENT, active_only=True)[0].confidence == 0.5
    assert llm.structured_calls == []


# ── 3. no night thoughts written for him ──

def test_the_night_writes_no_thoughts_with_a_model(store):
    _seed_recent(store)
    llm = RecordingLLM(prose="I keep returning to the wall.\nThe frost worries me.")

    stats = run_reflection_pass(store, _identity(), EmotionalState(), llm_client=llm)

    assert stats["thoughts_generated"] == 0
    assert llm.complete_calls == []
    written = [e for e in store.get_active_engrams(agent_id=AGENT, limit=50)
               if e.source.type == SourceType.REFLECTION]
    assert written == []
    assert stats["identity_computed"] is True    # the graph is still measured


def test_the_night_writes_no_template_thoughts_without_a_model(store):
    _seed_recent(store)

    run_reflection_pass(store, _identity(), EmotionalState(), llm_client=None)

    contents = [e.content for e in store.get_active_engrams(agent_id=AGENT, limit=50)]
    assert not any(c.startswith("Recurring theme") for c in contents)


# ── the whole night ──

def test_a_deep_night_writes_nothing_in_his_place(store):
    old = _faint()
    store.save_engram(old)
    _seed_recent(store)
    _belief(store)
    before = {e.id for e in store.get_active_engrams(agent_id=AGENT, limit=200)}
    llm = RecordingLLM(structured="[]", prose="a line in someone else's hand")

    stats = ConsolidationDaemon(store=store, llm_client=llm).run_cycle(deep=True, agent_id=AGENT)

    assert stats["cycle_type"] == "deep"
    assert "belief_review" not in stats["passes_run"]
    assert "belief_formation" not in stats["passes_run"]
    assert llm.complete_calls == []              # links may be classified; no prose is written
    after = {e.id for e in store.get_active_engrams(agent_id=AGENT, limit=200)}
    assert after == before                       # no new memory of any kind
    assert store.get_engram(old.id).content == FAINT
    assert store.get_beliefs(AGENT, active_only=True)[0].confidence == 0.5


def test_a_promoted_note_carries_no_engine_words_as_its_lesson(tmp_path):
    from mnemos.simple_runtime import MnemosRuntime

    runtime = MnemosRuntime(db_path=str(tmp_path / "promo.db"), agent_id=AGENT,
                            person_id="tara", project_scope="croft",
                            use_dedicated_model=False)
    try:
        runtime._ensure_init()
        runtime._store.write_hypomnema_entry(
            "The raised beds face south.", agent_id=AGENT, person_id="tara",
            project_scope="croft", foundational=True, confidence=0.9, salience=0.8)
        runtime.maintain()
        promoted = [e for e in runtime._store.get_active_engrams(agent_id=AGENT, limit=50)
                    if "promoted" in e.tags]
        assert promoted, "the note should have been promoted"
        assert all(not e.impact for e in promoted)
    finally:
        runtime.close()
