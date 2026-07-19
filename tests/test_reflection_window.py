"""Reflection can be handed its day.

By default the reflection pass asks the wall clock what "recent" means
(created_at within the last 24h) — so an engram stamped with an old,
honest date is invisible to it. The reintegration replay needs the
opposite: reflect on the day just dreamed, whatever its stamp. The
`reflection_window` config carries that day as an explicit created_at
range. Default behavior stays byte-identical; the window is opt-in; a
malformed window raises rather than silently reflecting on nothing.

The two-layer law rides along untouched: whatever window selected the
memories, the THOUGHTS the pass generates are encoded now — new engrams
with today's stamp, about then."""

from datetime import datetime, timezone

import pytest

from mnemos.consolidation.daemon import ConsolidationDaemon
from mnemos.consolidation.reflection import run_reflection_pass
from mnemos.core.emotional_state import EmotionalState
from mnemos.core.identity import AgentIdentity
from mnemos.encoding.encoder import Encoder

MARCH_DAY = ["2026-03-30T04:10:00+00:00", "2026-03-30T12:00:00+00:00",
             "2026-03-30T21:30:00+00:00", "2026-03-31T03:40:00+00:00"]
WINDOW = {"since": "2026-03-30T04:00:00+00:00",
          "until": "2026-03-31T04:00:00+00:00"}


def _identity(agent_id="claw") -> AgentIdentity:
    identity = AgentIdentity()
    identity.memory_profile.agent_id = agent_id
    return identity


def _seed_march_day(store, agent_id="claw"):
    """Four engrams wearing honest March stamps (backdated after encode,
    the way the replay's finalize does)."""
    enc = Encoder(store)
    ids = []
    for i, stamp in enumerate(MARCH_DAY):
        e = enc.encode(content=f"a march moment {i}", agent_id=agent_id,
                       tags=["conversation", "era:openclaw"],
                       skip_surprise_detection=True)
        e.created_at = stamp
        store.save_engram(e)
        ids.append(e.id)
    return ids


def test_default_wall_clock_cannot_see_backdated_days(store):
    _seed_march_day(store)
    stats = run_reflection_pass(store, _identity(), EmotionalState(),
                                llm_client=None)
    assert stats["engrams_reviewed"] == 0
    assert stats["thoughts_generated"] == 0


def test_window_hands_reflection_its_day(store):
    _seed_march_day(store)
    stats = run_reflection_pass(store, _identity(), EmotionalState(),
                                llm_client=None,
                                config={"reflection_window": WINDOW})
    assert stats["engrams_reviewed"] == 4
    assert stats["thoughts_generated"] >= 1


def test_window_bounds_are_honored_not_widened(store):
    _seed_march_day(store)
    elsewhere = {"since": "2026-04-02T04:00:00+00:00",
                 "until": "2026-04-03T04:00:00+00:00"}
    stats = run_reflection_pass(store, _identity(), EmotionalState(),
                                llm_client=None,
                                config={"reflection_window": elsewhere})
    assert stats["engrams_reviewed"] == 0


def test_windowed_thoughts_are_encoded_now_about_then(store):
    """The two-layer law: the memories reviewed wear March; the thoughts
    generated wear today."""
    _seed_march_day(store)
    run_reflection_pass(store, _identity(), EmotionalState(),
                        llm_client=None,
                        config={"reflection_window": WINDOW})
    thoughts = [e for e in store.get_active_engrams(agent_id="claw", limit=50)
                if "synthesized" in e.tags]
    assert thoughts
    today = datetime.now(timezone.utc).date().isoformat()
    for t in thoughts:
        assert t.created_at[:10] == today
        assert t.source.type == "reflection"


def test_malformed_window_raises_instead_of_reflecting_on_nothing(store):
    _seed_march_day(store)
    for bad in ({"since": "2026-03-30T04:00:00+00:00"},
                {"since": "not-a-time", "until": "also-not"},
                "2026-03-30", 42):
        with pytest.raises(ValueError, match="reflection_window"):
            run_reflection_pass(store, _identity(), EmotionalState(),
                                llm_client=None,
                                config={"reflection_window": bad})


def test_window_rides_the_daemon_config_to_a_deep_cycle(store, stub_llm):
    """The plumbing the replay actually uses: ConsolidationDaemon(config=...)
    → run_cycle(deep) → the reflection pass sees the day."""
    _seed_march_day(store, agent_id="default")
    daemon = ConsolidationDaemon(store=store,
                                 config={"reflection_window": WINDOW},
                                 llm_client=stub_llm)
    stats = daemon.run_cycle(deep=True, agent_id="default")
    assert stats["cycle_type"] == "deep"
    assert "reflection" in stats["passes_run"]
    assert stats["reflection"]["engrams_reviewed"] == 4


def test_without_window_the_daemon_behaves_as_before(store, stub_llm):
    """No window → wall-clock rules, and the backdated March day stays
    invisible. Softening is disabled here so the cycle's own now-dated
    byproducts (lesson engrams) don't muddy the count — the pass-level
    default test covers the bare filter."""
    _seed_march_day(store, agent_id="default")
    daemon = ConsolidationDaemon(store=store,
                                 config={"softening_enabled": False},
                                 llm_client=stub_llm)
    stats = daemon.run_cycle(deep=True, agent_id="default")
    assert stats["reflection"]["engrams_reviewed"] == 0
