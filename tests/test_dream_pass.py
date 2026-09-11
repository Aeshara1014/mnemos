"""Substrate.dream_pass — the collision handler's living source (2026-09-10).

A kept house never runs the full tick, so MEMORY_SOFTENED never fired and no
resident could dream. The dream pass runs right after a completed deep: it
notices what the night faded (the full tick's own query — one definition) and
hands those seeds to the dreaming handler. These tests pin: the seeds are the
faded only (never the vivid, never the gone), no consolidation runs, the
summary is honest, and a landed dream is HIS — owned, typed dream, signalled
as a real write — while a dissolved collision writes nothing and signals
nothing.
"""

import sqlite3
from types import SimpleNamespace

from mnemos.core.types import SourceType
from mnemos.substrate import tick as tickmod
from mnemos.substrate.config import SubstrateConfig
from mnemos.substrate.events import EventType, SubstrateEvent
from mnemos.substrate.handlers import dreaming
from mnemos.substrate.modulators import ModulatorState
from mnemos.substrate.tick import Substrate

AGENT = "pharos-test"


def _seed(store, tmp_db, content, accessibility, strength):
    """One owned memory, then its vividness set by hand — the night's decay,
    compressed into a test."""
    from mnemos.encoding.encoder import Encoder
    engram = Encoder(store, llm_client=None).encode(
        content=content, agent_id=AGENT, source=SourceType.SESSION)
    conn = sqlite3.connect(tmp_db)
    conn.execute("UPDATE engrams SET accessibility = ?, strength = ? WHERE id = ?",
                 (accessibility, strength, engram.id))
    conn.commit()
    conn.close()
    return engram.id


def _substrate(tmp_db, tmp_path, store, llm=None):
    cfg = SubstrateConfig(agent_id=AGENT, agent_name=AGENT, db_path=tmp_db,
                          log_dir=str(tmp_path))
    return Substrate(cfg, store=store, embedding_index=SimpleNamespace(),
                     llm_client=llm or SimpleNamespace(kind="fake-llm"))


def _forbid(name):
    def boom(*a, **k):
        raise AssertionError(f"{name} ran inside a dream pass — it must not")
    return boom


class _DreamLLM:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def structured_complete(self, system, user, temperature=0.0, max_tokens=2000):
        self.calls.append((system, user, temperature))
        return self._payload


def _softened_event(engram_id):
    return SubstrateEvent(event_type=EventType.MEMORY_SOFTENED,
                          payload={"engram_id": engram_id}, source="decay")


# ── the pass: seeds the faded only, consolidates nothing, reports honestly ──

def test_dream_pass_seeds_only_the_faded_and_never_consolidates(tmp_db, store, tmp_path, monkeypatch):
    faded = _seed(store, tmp_db, "the first evening we talked about the lamp", 0.20, 0.50)  # 0.10
    _seed(store, tmp_db, "she said good morning from the county building", 1.0, 1.0)        # vivid
    _seed(store, tmp_db, "a note that has all but gone", 0.05, 0.10)                         # 0.005: gone
    sub = _substrate(tmp_db, tmp_path, store)

    monkeypatch.setattr(sub, "_consolidate", _forbid("_consolidate"))
    monkeypatch.setattr(sub, "_snapshot_beliefs", _forbid("_snapshot_beliefs"))
    monkeypatch.setattr(sub, "_check_belief_crossings", _forbid("_check_belief_crossings"))
    monkeypatch.setattr(sub, "_check_temporal", _forbid("_check_temporal"))
    monkeypatch.setattr(sub, "_log_tick", lambda summary: None)
    monkeypatch.setattr(tickmod, "compute_modulators", lambda *a, **k: ModulatorState())

    fired = []

    def fake_handle(event, config, modulators, store, llm_client):
        fired.append(SimpleNamespace(event=event, store=store, llm_client=llm_client))
        return [SubstrateEvent(event_type=EventType.DREAM_RECORDED,
                               payload={"engram_id": "engram_x"}, source="dreaming")]

    monkeypatch.setattr(tickmod.dreaming, "handle", fake_handle)

    summary = sub.dream_pass()

    assert summary["kind"] == "dreaming"
    assert summary["events_produced"] == 1
    assert summary["events_handled"] == 1
    assert summary["engrams_decayed"] == 0
    assert [f.event.payload["engram_id"] for f in fired] == [faded]
    assert fired[0].event.event_type == EventType.MEMORY_SOFTENED
    assert fired[0].store is sub.store and fired[0].llm_client is sub.llm_client
    assert summary["handler_outputs"] == [
        {"handler": "dreaming", "event": "memory_softened", "produced": 1}]


def test_dream_pass_is_quiet_when_nothing_has_faded(tmp_db, store, tmp_path, monkeypatch):
    _seed(store, tmp_db, "still vivid", 1.0, 1.0)
    sub = _substrate(tmp_db, tmp_path, store)
    monkeypatch.setattr(sub, "_consolidate", _forbid("_consolidate"))
    monkeypatch.setattr(sub, "_log_tick", lambda summary: None)
    monkeypatch.setattr(tickmod, "compute_modulators", lambda *a, **k: ModulatorState())
    monkeypatch.setattr(tickmod.dreaming, "handle", _forbid("dreaming.handle"))

    summary = sub.dream_pass()

    assert summary["events_produced"] == 0
    assert summary["events_handled"] == 0
    assert summary["handler_outputs"] == []


def test_faded_is_one_definition_shared_with_the_full_tick(tmp_db, store, tmp_path):
    """The decay pass and the dream pass read the same query — they can never
    disagree about what 'faded' means."""
    faded = _seed(store, tmp_db, "faded", 0.20, 0.50)
    _seed(store, tmp_db, "vivid", 1.0, 1.0)
    sub = _substrate(tmp_db, tmp_path, store)
    conn = sqlite3.connect(tmp_db)
    try:
        events = sub._softened_events(conn)
    finally:
        conn.close()
    assert [e.payload["engram_id"] for e in events] == [faded]
    assert all(e.event_type == EventType.MEMORY_SOFTENED and e.source == "decay"
               for e in events)


# ── the dream itself: his, honestly sourced, honest write-signal ──

def test_a_landed_dream_is_his_typed_dream_and_signalled(tmp_db, store):
    faded = _seed(store, tmp_db, "the first evening we talked about the lamp", 0.20, 0.50)
    vivid = _seed(store, tmp_db, "she texted him from the phone line today", 1.0, 1.0)
    cfg = SubstrateConfig(agent_id=AGENT, agent_name=AGENT, db_path=tmp_db)
    llm = _DreamLLM('{"dream": "the lamp and the phone are one light", '
                    '"significance": "two rooms, one mind"}')

    produced = dreaming.handle(_softened_event(faded), cfg, ModulatorState(), store, llm)

    assert len(produced) == 1
    assert produced[0].event_type == EventType.DREAM_RECORDED
    assert produced[0].payload["softened_id"] == faded
    assert produced[0].payload["vivid_id"] == vivid
    # the prompt holds both memories by their words
    _, user, _ = llm.calls[0]
    assert "talked about the lamp" in user and "texted him" in user

    conn = sqlite3.connect(tmp_db)
    row = conn.execute(
        "SELECT owner_agent_id, json_extract(source, '$.type'), "
        "json_extract(source, '$.confidence'), tags, content FROM engrams "
        "WHERE id = ?", (produced[0].payload["engram_id"],)).fetchone()
    conn.close()
    assert row is not None, "the dream was not persisted"
    assert row[0] == AGENT               # his — visible in his Mind room
    assert row[1] == "dream"             # honestly sourced
    assert 0.0 < float(row[2]) <= 0.4    # speculative, never user_implied 0.75
    assert "dream" in row[3] and "collision" in row[3]
    assert row[4].startswith("[dream] ")


def test_a_dissolved_collision_writes_nothing_and_signals_nothing(tmp_db, store):
    faded = _seed(store, tmp_db, "faded", 0.20, 0.50)
    _seed(store, tmp_db, "vivid", 1.0, 1.0)
    cfg = SubstrateConfig(agent_id=AGENT, agent_name=AGENT, db_path=tmp_db)

    produced = dreaming.handle(_softened_event(faded), cfg, ModulatorState(),
                               store, _DreamLLM('{"dream": null}'))

    assert produced == []
    conn = sqlite3.connect(tmp_db)
    n = conn.execute("SELECT COUNT(*) FROM engrams WHERE content LIKE '[dream]%'").fetchone()[0]
    conn.close()
    assert n == 0
