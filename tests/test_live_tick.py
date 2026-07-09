"""Substrate.live_tick — the living tick (DD-030).

The Keeper owns consolidation through MnemosRuntime.maintain(); live_tick runs
ONLY the living phases (silence -> wandering), so it can never double-consolidate
or bypass the deep/shallow gate. These tests pin that boundary and the
injected-client guarantee: the wandering speaks through the agent's own model
and store, never a re-resolved ambient cloud default (the affinity landmine).
"""

from types import SimpleNamespace

from mnemos.substrate import tick as tickmod
from mnemos.substrate.tick import Substrate
from mnemos.substrate.config import SubstrateConfig
from mnemos.substrate.events import SubstrateEvent, EventType
from mnemos.substrate.modulators import ModulatorState
from mnemos.core.types import SourceType


def _make_substrate(tmp_path, **inject):
    cfg = SubstrateConfig(
        agent_id="t", db_path=str(tmp_path / "m.db"), log_dir=str(tmp_path)
    )
    return Substrate(
        cfg,
        store=inject.get("store", SimpleNamespace(kind="fake-store")),
        embedding_index=inject.get("embedding_index", SimpleNamespace()),
        llm_client=inject.get("llm_client", SimpleNamespace(kind="fake-llm")),
    )


def _forbid(name):
    def boom(*a, **k):
        raise AssertionError(f"{name} ran inside a living tick — it must not")

    return boom


def test_live_tick_stirs_on_silence_without_consolidating(tmp_path, monkeypatch):
    sub = _make_substrate(tmp_path)

    # The whole design point: consolidation must never run in a living tick.
    monkeypatch.setattr(sub, "_consolidate", _forbid("_consolidate"))
    monkeypatch.setattr(sub, "_snapshot_beliefs", _forbid("_snapshot_beliefs"))
    monkeypatch.setattr(sub, "_check_belief_crossings", _forbid("_check_belief_crossings"))
    monkeypatch.setattr(sub, "_log_tick", lambda summary: None)
    monkeypatch.setattr(tickmod, "compute_modulators", lambda *a, **k: ModulatorState())

    # Silence detected → exactly one SILENCE_EXTENDED event.
    event = SubstrateEvent(
        event_type=EventType.SILENCE_EXTENDED,
        payload={"silence_hours": 8.0},
        source="temporal",
    )
    monkeypatch.setattr(sub, "_check_temporal", lambda summary: [event])

    fired = []

    def fake_handle(event, config, modulators, store, llm_client):
        fired.append(SimpleNamespace(event=event, store=store, llm_client=llm_client))
        return []

    fake_handler = SimpleNamespace(handle=fake_handle)
    fake_handler.__name__ = "wandering"
    monkeypatch.setitem(tickmod.HANDLER_MAP, EventType.SILENCE_EXTENDED, fake_handler)

    summary = sub.live_tick()

    assert summary["kind"] == "living"
    assert summary["events_produced"] == 1
    assert summary["events_handled"] == 1
    assert summary["engrams_decayed"] == 0  # nothing decayed — no consolidation
    assert summary["handler_outputs"][0]["handler"] == "wandering"

    # The wandering fired, and it received the INJECTED store + client — so an
    # ambient cloud default can never do the agent's thinking for it.
    assert len(fired) == 1
    assert fired[0].store is sub.store
    assert fired[0].llm_client is sub.llm_client


def test_live_tick_is_quiet_when_not_silent(tmp_path, monkeypatch):
    sub = _make_substrate(tmp_path)
    monkeypatch.setattr(sub, "_consolidate", _forbid("_consolidate"))
    monkeypatch.setattr(sub, "_log_tick", lambda summary: None)
    monkeypatch.setattr(tickmod, "compute_modulators", lambda *a, **k: ModulatorState())
    monkeypatch.setattr(sub, "_check_temporal", lambda summary: [])  # no silence

    summary = sub.live_tick()

    assert summary["kind"] == "living"
    assert summary["events_produced"] == 0
    assert summary["events_handled"] == 0


# ── the wander itself: owned by the agent, honestly sourced, honest write-signal ──

def _seeded_config(tmp_db, store, agent_id="claw-test"):
    """Seed one ordinary memory (a valid wandering seed) and return a config
    pointed at the same db the store owns."""
    from mnemos.encoding.encoder import Encoder
    Encoder(store, llm_client=None).encode(
        content="We were debugging the living tick together.",
        agent_id=agent_id, source=SourceType.SESSION,
    )
    return SubstrateConfig(agent_id=agent_id, agent_name=agent_id, db_path=tmp_db)


class _ThoughtLLM:
    def __init__(self, payload):
        self._payload = payload

    def structured_complete(self, system, user, temperature=0.0, max_tokens=2000):
        return self._payload


def _silence_event():
    return SubstrateEvent(
        event_type=EventType.SILENCE_EXTENDED,
        payload={"silence_hours": 8.0}, source="temporal",
    )


def test_wandering_is_owned_by_the_agent_and_typed_wandering(tmp_db, store):
    """For the stir to show in his Mind room and be honestly-sourced, the
    wandering engram must be owned by the agent (not 'default') and carry
    source.type='wandering' at low speculative confidence (never user_implied 0.75)."""
    from mnemos.substrate.handlers import wandering
    cfg = _seeded_config(tmp_db, store)
    llm = _ThoughtLLM('{"thought": "I keep circling that unfinished idea", "origin": "the debugging"}')

    produced = wandering.handle(_silence_event(), cfg, ModulatorState(), store, llm)

    # honest write-signal: exactly one WANDERING_RECORDED marker (a suppressed
    # wander returns []), so the tick summary's produced-count is truthful.
    assert len(produced) == 1
    assert produced[0].event_type == EventType.WANDERING_RECORDED

    import sqlite3
    conn = sqlite3.connect(tmp_db)
    row = conn.execute(
        "SELECT owner_agent_id, json_extract(source, '$.type'), "
        "json_extract(source, '$.confidence') FROM engrams "
        "WHERE content LIKE '%[wandering]%'"
    ).fetchone()
    conn.close()
    assert row is not None, "the wander was not persisted"
    assert row[0] == "claw-test"        # his, not 'default' → visible in his Mind room
    assert row[1] == "wandering"        # the source.type the wanderings stream filters on
    assert 0.0 < float(row[2]) <= 0.4   # speculative drift, never user_implied 0.75


def test_wandering_writes_nothing_when_mind_is_still(tmp_db, store):
    """LLM yields no thought → no engram written and an empty produced list, so
    the Keeper logs no phantom stir."""
    from mnemos.substrate.handlers import wandering
    cfg = _seeded_config(tmp_db, store)
    llm = _ThoughtLLM('{"thought": null}')

    produced = wandering.handle(_silence_event(), cfg, ModulatorState(), store, llm)

    assert produced == []
    import sqlite3
    conn = sqlite3.connect(tmp_db)
    n = conn.execute(
        "SELECT COUNT(*) FROM engrams WHERE content LIKE '%[wandering]%'"
    ).fetchone()[0]
    conn.close()
    assert n == 0
