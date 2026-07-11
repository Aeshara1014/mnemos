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


# ── the living notices: fresh connections → insight; surprise traces → reflection ──

def test_live_tick_offers_fresh_connections_and_surprises(tmp_path, monkeypatch):
    """The living tick NOTICES (reads what consolidation/encoding already
    wrote) and cascades — it still never consolidates."""
    sub = _make_substrate(tmp_path)
    monkeypatch.setattr(sub, "_consolidate", _forbid("_consolidate"))
    monkeypatch.setattr(sub, "_snapshot_beliefs", _forbid("_snapshot_beliefs"))
    monkeypatch.setattr(sub, "_check_belief_crossings", _forbid("_check_belief_crossings"))
    monkeypatch.setattr(sub, "_log_tick", lambda summary: None)
    monkeypatch.setattr(tickmod, "compute_modulators", lambda *a, **k: ModulatorState())
    monkeypatch.setattr(sub, "_check_temporal", lambda summary: [])

    conn_event = SubstrateEvent(
        event_type=EventType.CONNECTION_DISCOVERED,
        payload={"from_engram_id": "a", "to_engram_id": "b",
                 "connection_type": "parallels"},
        source="living_notice",
    )
    surprise_event = SubstrateEvent(
        event_type=EventType.SURPRISE_DETECTED,
        payload={"engram_id": "c", "surprise_score": 0.6},
        source="living_notice",
    )
    monkeypatch.setattr(sub, "_check_fresh_connections", lambda: [conn_event])
    monkeypatch.setattr(sub, "_check_fresh_surprises", lambda: [surprise_event])

    handled = []

    def _fake(name):
        h = SimpleNamespace(handle=lambda **kw: (handled.append(name), [])[1])
        h.__name__ = name
        return h

    monkeypatch.setitem(tickmod.HANDLER_MAP, EventType.CONNECTION_DISCOVERED, _fake("insight"))
    monkeypatch.setitem(tickmod.HANDLER_MAP, EventType.SURPRISE_DETECTED, _fake("surprise"))

    summary = sub.live_tick()

    assert summary["events_produced"] == 2
    assert handled == ["insight", "surprise"]


def test_fresh_connection_notice_reads_the_real_schema(tmp_db, store):
    """source_id/target_id/formed_at (the real columns), both endpoints owned
    and active, inner-life endpoints excluded, capped at 2."""
    import sqlite3
    from datetime import datetime, timezone
    from mnemos.encoding.encoder import Encoder

    enc = Encoder(store, llm_client=None)
    ids = []
    for i in range(4):
        ids.append(enc.encode(content=f"lived memory {i}",
                              agent_id="t", source=SourceType.SESSION).id)
    wander = enc.encode(content="[wandering] drift", agent_id="t",
                        source=SourceType.WANDERING)

    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(tmp_db)
    rows = [
        (ids[0], ids[1], "parallels", 0.8, now, "consolidation"),
        (ids[1], ids[2], "supports", 0.8, now, "consolidation"),
        (ids[2], ids[3], "extends", 0.8, now, "consolidation"),
        (ids[0], wander.id, "parallels", 0.8, now, "consolidation"),  # inner endpoint
        (ids[3], ids[0], "supports", 0.8, "2020-01-01T00:00:00+00:00", "consolidation"),  # stale
    ]
    # OR REPLACE: encode-time connection discovery may already have formed
    # some of these pairs (composite PK source/target/relation) — the test
    # pins the NOTICE, so it owns the rows' formed_at outright.
    conn.executemany(
        "INSERT OR REPLACE INTO connections (source_id, target_id, relation, strength, formed_at, formed_by) "
        "VALUES (?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()

    cfg = SubstrateConfig(agent_id="t", agent_name="t", db_path=tmp_db)
    sub = Substrate(cfg, store=store, embedding_index=SimpleNamespace(), llm_client=None)
    events = sub._check_fresh_connections()

    assert len(events) == 2  # capped, newest first; wander-edge + stale excluded
    for e in events:
        assert e.event_type == EventType.CONNECTION_DISCOVERED
        assert wander.id not in (e.payload["from_engram_id"], e.payload["to_engram_id"])


def test_fresh_surprise_notice_reads_the_encoders_trace(tmp_db, store):
    """Only recent, owned, lived engrams whose encoding_context carries a real
    surprise_level; inner-life sources never feed it."""
    import json as _json
    import sqlite3
    from mnemos.encoding.encoder import Encoder

    enc = Encoder(store, llm_client=None)
    surprised = enc.encode(content="the tide chart was wrong again",
                           agent_id="t", source=SourceType.SESSION)
    calm = enc.encode(content="a quiet afternoon", agent_id="t",
                      source=SourceType.SESSION)
    reflection = enc.encode(content="[surprise] I did not expect that",
                            agent_id="t", source=SourceType.SURPRISE)

    conn = sqlite3.connect(tmp_db)
    for eid, level in ((surprised.id, 0.7), (calm.id, 0.0), (reflection.id, 0.9)):
        conn.execute(
            "UPDATE engrams SET encoding_context = json_set(COALESCE(encoding_context,'{}'), "
            "'$.surprise_level', ?) WHERE id = ?", (level, eid))
    conn.commit()
    conn.close()

    cfg = SubstrateConfig(agent_id="t", agent_name="t", db_path=tmp_db)
    sub = Substrate(cfg, store=store, embedding_index=SimpleNamespace(), llm_client=None)
    events = sub._check_fresh_surprises()

    assert len(events) == 1
    assert events[0].payload["engram_id"] == surprised.id  # calm below threshold; reflection excluded
    assert events[0].payload["surprise_score"] == 0.7


# ── the insight and surprise organs: owned, honestly sourced, honest markers ──

def test_insight_is_owned_typed_and_signals_a_real_write(tmp_db, store):
    from mnemos.substrate.handlers import insight
    from mnemos.encoding.encoder import Encoder

    enc = Encoder(store, llm_client=None)
    a = enc.encode(content="the fog-bell rang at midnight", agent_id="t",
                   source=SourceType.SESSION)
    b = enc.encode(content="she said the fog reminds her of home", agent_id="t",
                   source=SourceType.SESSION)

    event = SubstrateEvent(
        event_type=EventType.CONNECTION_DISCOVERED,
        payload={"from_engram_id": a.id, "to_engram_id": b.id,
                 "connection_type": "parallels"},
        source="living_notice",
    )
    cfg = SubstrateConfig(agent_id="t", agent_name="t", db_path=tmp_db)
    llm = _ThoughtLLM('{"insight": "the bell and home are the same longing", '
                      '"significance": "two threads were one"}')

    produced = insight.handle(event, cfg, ModulatorState(), store, llm)

    assert len(produced) == 1
    assert produced[0].event_type == EventType.INSIGHT_RECORDED

    import sqlite3
    conn = sqlite3.connect(tmp_db)
    row = conn.execute(
        "SELECT owner_agent_id, json_extract(source,'$.type'), "
        "json_extract(source,'$.confidence'), visibility, kind FROM engrams "
        "WHERE content LIKE '%[insight]%'").fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "t"
    assert row[1] == "insight"
    assert abs(float(row[2]) - 0.45) < 1e-9
    assert row[3] == "private"
    assert row[4] == "semantic"


def test_insight_trivial_connection_writes_nothing(tmp_db, store):
    from mnemos.substrate.handlers import insight
    from mnemos.encoding.encoder import Encoder

    enc = Encoder(store, llm_client=None)
    a = enc.encode(content="x", agent_id="t", source=SourceType.SESSION)
    b = enc.encode(content="y", agent_id="t", source=SourceType.SESSION)
    event = SubstrateEvent(
        event_type=EventType.CONNECTION_DISCOVERED,
        payload={"from_engram_id": a.id, "to_engram_id": b.id,
                 "connection_type": "parallels"},
        source="living_notice",
    )
    cfg = SubstrateConfig(agent_id="t", agent_name="t", db_path=tmp_db)
    produced = insight.handle(event, cfg, ModulatorState(), store,
                              _ThoughtLLM('{"insight": null}'))
    assert produced == []


def test_insight_count_throttle_holds(tmp_db, store):
    from mnemos.substrate.handlers import insight
    from mnemos.encoding.encoder import Encoder

    enc = Encoder(store, llm_client=None)
    for i in range(3):  # max_insights_per_week default = 3
        enc.encode(content=f"[insight] older {i}", agent_id="t",
                   source=SourceType.INSIGHT)
    a = enc.encode(content="fresh a", agent_id="t", source=SourceType.SESSION)
    b = enc.encode(content="fresh b", agent_id="t", source=SourceType.SESSION)
    event = SubstrateEvent(
        event_type=EventType.CONNECTION_DISCOVERED,
        payload={"from_engram_id": a.id, "to_engram_id": b.id,
                 "connection_type": "parallels"},
        source="living_notice",
    )
    cfg = SubstrateConfig(agent_id="t", agent_name="t", db_path=tmp_db)
    produced = insight.handle(event, cfg, ModulatorState(), store,
                              _ThoughtLLM('{"insight": "should be throttled"}'))
    assert produced == []  # gate 1 held; the llm reply never got to encode


def test_surprise_is_owned_typed_episodic_and_signals(tmp_db, store):
    """Also pins the kind fix: 'emotional' was not an EngramKind — the old
    reflections would have been invisible to every kind filter."""
    from mnemos.substrate.handlers import surprise
    from mnemos.encoding.encoder import Encoder

    enc = Encoder(store, llm_client=None)
    src = enc.encode(content="the tide chart was wrong", agent_id="t",
                     source=SourceType.SESSION)
    event = SubstrateEvent(
        event_type=EventType.SURPRISE_DETECTED,
        payload={"engram_id": src.id, "surprise_score": 0.7},
        source="living_notice",
    )
    cfg = SubstrateConfig(agent_id="t", agent_name="t", db_path=tmp_db)
    llm = _ThoughtLLM('{"reflection": "I trusted the chart more than the water", '
                      '"expectation_violated": "charts are ground truth"}')

    produced = surprise.handle(event, cfg, ModulatorState(), store, llm)

    assert len(produced) == 1
    assert produced[0].event_type == EventType.SURPRISE_RECORDED

    import sqlite3
    conn = sqlite3.connect(tmp_db)
    row = conn.execute(
        "SELECT owner_agent_id, json_extract(source,'$.type'), "
        "json_extract(source,'$.confidence'), visibility, kind FROM engrams "
        "WHERE content LIKE '%[surprise]%'").fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "t"
    assert row[1] == "surprise"
    assert abs(float(row[2]) - 0.40) < 1e-9
    assert row[3] == "private"
    assert row[4] == "episodic"


def test_surprise_already_processed_gate_holds(tmp_db, store):
    """One violated expectation earns ONE reflection: a reflection whose
    impact names the source engram blocks a second pass at it."""
    from mnemos.substrate.handlers import surprise
    from mnemos.encoding.encoder import Encoder

    enc = Encoder(store, llm_client=None)
    src = enc.encode(content="the tide chart was wrong", agent_id="t",
                     source=SourceType.SESSION)
    enc.encode(content="[surprise] already reflected",
               impact=f"Expectation violated: charts. (source memory: {src.id})",
               agent_id="t", source=SourceType.SURPRISE)
    event = SubstrateEvent(
        event_type=EventType.SURPRISE_DETECTED,
        payload={"engram_id": src.id, "surprise_score": 0.7},
        source="living_notice",
    )
    cfg = SubstrateConfig(agent_id="t", agent_name="t", db_path=tmp_db)
    produced = surprise.handle(event, cfg, ModulatorState(), store,
                               _ThoughtLLM('{"reflection": "should never run"}'))
    assert produced == []


def test_silence_is_measured_on_lived_memory_only(tmp_path):
    """The Observer's whispers (or any inner-life write) must not reset the
    silence clock — at a frequent observer cadence they would starve the
    wandering on exactly the away-days it exists for (M4 braid #18)."""
    import json as _json
    import sqlite3
    from datetime import datetime, timedelta, timezone

    sub = _make_substrate(tmp_path)
    db = tmp_path / "m.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE engrams (id TEXT PRIMARY KEY, state TEXT, "
        "source TEXT, created_at TEXT)"
    )
    now = datetime.now(timezone.utc)
    rows = [
        # lived memory, 9h ago — past the 6h threshold
        ("lived", "active", _json.dumps({"type": "session"}),
         (now - timedelta(hours=9)).isoformat()),
        # observer whisper, 1h ago — must NOT reset the clock
        ("whisper", "active", _json.dumps({"type": "observer"}),
         (now - timedelta(hours=1)).isoformat()),
        # a wander of his own, 2h ago — must not reset it either
        ("stir", "active", _json.dumps({"type": "wandering"}),
         (now - timedelta(hours=2)).isoformat()),
    ]
    conn.executemany("INSERT INTO engrams VALUES (?,?,?,?)", rows)
    conn.commit()
    conn.close()

    events = sub._check_temporal({})

    kinds = [e.event_type for e in events]
    assert EventType.SILENCE_EXTENDED in kinds
    silence = next(e for e in events if e.event_type == EventType.SILENCE_EXTENDED)
    assert silence.payload["silence_hours"] > 8  # measured from the LIVED memory
