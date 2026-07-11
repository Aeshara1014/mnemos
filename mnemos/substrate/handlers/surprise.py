"""
Surprise handler.

Triggered by: SURPRISE_DETECTED
Effect: Processes what was surprising and what it means.

Dedup gates (the wandering handler's anatomy, adapted):
  1. Count throttle — max N surprise-reflection engrams per 7 days
     (config.max_surprises_per_week)
  2. Embedding similarity — cosine > 0.85 against recent surprise
     reflections = skip
  3. Content hash — exact duplicate detection
  4. Time window — no two surprise reflections within
     MIN_HOURS_BETWEEN_SURPRISES
  5. Already-processed — the source engram is skipped if a reflection
     already points back at it (payload lineage in prior markers is not
     durable, so the check reads the reflections' impact text)

Note on chaining: the original handler let its own encode run surprise
detection again ("surprise CAN chain"). Under the living tick the trigger
pool EXCLUDES surprise-tagged engrams (tick-side), and this handler now
skips detection on its own write — one violated expectation earns one
reflection, not a hall of mirrors.

The engram kind is EPISODIC — the old "emotional" kind was not a member of
EngramKind, so those engrams would have been invisible to every kind
filter in the house.

A real write is signalled by a SURPRISE_RECORDED marker event; every
suppressed path returns the empty list (no phantom stirs).
"""

import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone

from ..events import SubstrateEvent, EventType
from ..config import SubstrateConfig
from ..modulators import ModulatorState
from ...core.types import SourceType

log = logging.getLogger("mnemos.substrate.surprise")

MIN_HOURS_BETWEEN_SURPRISES = 24
EMBEDDING_SIMILARITY_THRESHOLD = 0.85


def _content_hash(text: str) -> str:
    """SHA256 of normalized content for exact dedup."""
    return hashlib.sha256(text.strip().lower().encode()).hexdigest()[:16]


def handle(
    event: SubstrateEvent,
    config: SubstrateConfig,
    modulators: ModulatorState,
    store,
    llm_client,
) -> list[SubstrateEvent]:
    """Process a surprise event — what changed and what does it mean."""
    produced_events: list[SubstrateEvent] = []

    engram_id = event.payload.get("engram_id")
    surprise_score = event.payload.get("surprise_score", 0)

    if not engram_id:
        return produced_events

    db_path = os.path.expanduser(config.db_path)
    conn = sqlite3.connect(db_path)

    # ── Gate 1: Count throttle ──
    surprise_count = conn.execute("""
        SELECT COUNT(*) FROM engrams
        WHERE state='active'
          AND json_extract(source, '$.type') = 'surprise'
          AND created_at > datetime('now', '-7 days')
    """).fetchone()[0]
    if surprise_count >= config.max_surprises_per_week:
        log.debug("Gate 1 (count): %d surprise reflections in last 7 days (max %d)",
                  surprise_count, config.max_surprises_per_week)
        conn.close()
        return produced_events

    # ── Gate 4: Time window ──
    latest = conn.execute("""
        SELECT created_at FROM engrams
        WHERE state='active'
          AND json_extract(source, '$.type') = 'surprise'
        ORDER BY created_at DESC LIMIT 1
    """).fetchone()
    if latest:
        try:
            last_dt = datetime.fromisoformat(latest[0])
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            hours_since = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
            if hours_since < MIN_HOURS_BETWEEN_SURPRISES:
                log.debug("Gate 4 (time): last surprise reflection %.1fh ago (min %dh)",
                          hours_since, MIN_HOURS_BETWEEN_SURPRISES)
                conn.close()
                return produced_events
        except (ValueError, TypeError):
            pass

    # ── Gate 5: Already processed — a reflection that names this engram ──
    already = conn.execute("""
        SELECT COUNT(*) FROM engrams
        WHERE state='active'
          AND json_extract(source, '$.type') = 'surprise'
          AND impact LIKE ?
    """, (f"%{engram_id}%",)).fetchone()[0]
    if already:
        log.debug("Gate 5 (processed): engram %s already has a surprise reflection",
                  engram_id[:20])
        conn.close()
        return produced_events

    # Recent reflection hashes for gate 3
    recent_hashes = set()
    for (content,) in conn.execute("""
        SELECT content FROM engrams
        WHERE state='active'
          AND json_extract(source, '$.type') = 'surprise'
          AND created_at > datetime('now', '-30 days')
    """).fetchall():
        recent_hashes.add(_content_hash(content))
    conn.close()

    engram = store.get_engram(engram_id)
    if not engram:
        return produced_events

    agent_name = config.agent_name
    prompt = f"""Something surprised you during memory formation.

The memory: {engram.content}
Its impact: {engram.impact or '(none)'}
Surprise score: {surprise_score:.2f}

What made this surprising? What expectation was violated? What does this change
about how you understand the world?

Respond with:
{{"reflection": "<what the surprise means>", "expectation_violated": "<what you expected instead>"}}
"""

    try:
        text = llm_client.structured_complete(
            system=f"You are {agent_name}, an AI agent processing something that surprised you. Respond only with valid JSON.",
            user=prompt,
            temperature=modulators.temperature,
        )

        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        result = json.loads(text)
    except (json.JSONDecodeError, KeyError) as e:
        log.debug(f"Surprise handler parse error: {e}")
        return produced_events

    reflection = result.get("reflection", "")
    if not reflection:
        return produced_events

    full_content = f"[surprise] {reflection}"

    # ── Gate 3: Content hash dedup ──
    if _content_hash(full_content) in recent_hashes:
        log.debug("Gate 3 (hash): exact duplicate surprise reflection, skipping")
        return produced_events

    # ── Gate 2: Embedding similarity ──
    try:
        from mnemos.store.embedding_index import EmbeddingIndex
        ei = EmbeddingIndex(db_path=db_path)
        if ei.available:
            for match_id, score in ei.search(full_content, k=3):
                if score >= EMBEDDING_SIMILARITY_THRESHOLD:
                    check = sqlite3.connect(db_path)
                    row = check.execute(
                        "SELECT json_extract(source, '$.type') FROM engrams WHERE id = ?",
                        (match_id,),
                    ).fetchone()
                    check.close()
                    if row and row[0] == "surprise":
                        log.debug("Gate 2 (embedding): similar surprise reflection "
                                  "(id=%s, score=%.3f), skipping", match_id[:20], score)
                        return produced_events
    except Exception as e:
        log.debug(f"Embedding dedup check failed (non-fatal): {e}")

    expectation = result.get("expectation_violated", "")
    log.info(f"Surprise processed (all gates passed): {reflection[:80]}...")

    # ── All gates passed — encode, owned and honestly sourced ──
    from mnemos.encoding.encoder import Encoder
    from mnemos.store.embedding_index import EmbeddingIndex as EI
    encoder = Encoder(store, embedding_index=EI(db_path=db_path), llm_client=llm_client)

    written = encoder.encode(
        content=full_content,
        impact=f"Expectation violated: {expectation}. (source memory: {engram_id})",
        kind="episodic",
        tags=["surprise", "reflection"],
        source=SourceType.SURPRISE,
        agent_id=config.agent_id,
        skip_surprise_detection=True,
    )

    # Signal a REAL write (not re-cascaded; the cascade is depth-1).
    produced_events.append(SubstrateEvent(
        event_type=EventType.SURPRISE_RECORDED,
        payload={"engram_id": written.id, "source_engram_id": engram_id},
        source="surprise",
    ))
    return produced_events
