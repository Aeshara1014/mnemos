"""
Insight handler.

Triggered by: CONNECTION_DISCOVERED
Effect: Reflects on what a new connection between memories means.
         May produce a new "insight" engram if the connection reveals something non-obvious.

Dedup gates (the wandering handler's anatomy, adapted):
  1. Count throttle — max N insight engrams per 7 days (config.max_insights_per_week)
  2. Embedding similarity — cosine > 0.85 against recent insights = skip
  3. Content hash — exact duplicate detection (a re-noticed connection that
     reads the same way lands here or at gate 2)
  4. Time window — no two insights within MIN_HOURS_BETWEEN_INSIGHTS

A real write is signalled by an INSIGHT_RECORDED marker event (produced > 0);
every suppressed path returns the empty list, so the tick summary and the
Keeper's activity log can never log a phantom stir.
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

log = logging.getLogger("mnemos.substrate.insight")

MIN_HOURS_BETWEEN_INSIGHTS = 24
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
    """Reflect on a newly discovered connection."""
    produced_events: list[SubstrateEvent] = []

    from_id = event.payload.get("from_engram_id")
    to_id = event.payload.get("to_engram_id")
    connection_type = event.payload.get("connection_type", "unknown")

    if not from_id or not to_id:
        return produced_events

    db_path = os.path.expanduser(config.db_path)
    conn = sqlite3.connect(db_path)

    # ── Gate 1: Count throttle ──
    insight_count = conn.execute("""
        SELECT COUNT(*) FROM engrams
        WHERE state='active'
          AND json_extract(source, '$.type') = 'insight'
          AND datetime(created_at) > datetime('now', '-7 days')
    """).fetchone()[0]
    if insight_count >= config.max_insights_per_week:
        log.debug("Gate 1 (count): %d insights in last 7 days (max %d)",
                  insight_count, config.max_insights_per_week)
        conn.close()
        return produced_events

    # ── Gate 4: Time window ──
    latest = conn.execute("""
        SELECT created_at FROM engrams
        WHERE state='active'
          AND json_extract(source, '$.type') = 'insight'
        ORDER BY created_at DESC LIMIT 1
    """).fetchone()
    if latest:
        try:
            last_dt = datetime.fromisoformat(latest[0])
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            hours_since = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
            if hours_since < MIN_HOURS_BETWEEN_INSIGHTS:
                log.debug("Gate 4 (time): last insight %.1fh ago (min %dh)",
                          hours_since, MIN_HOURS_BETWEEN_INSIGHTS)
                conn.close()
                return produced_events
        except (ValueError, TypeError):
            pass  # If parse fails, allow

    # Recent insight content hashes for gate 3
    recent_hashes = set()
    for (content,) in conn.execute("""
        SELECT content FROM engrams
        WHERE state='active'
          AND json_extract(source, '$.type') = 'insight'
          AND datetime(created_at) > datetime('now', '-30 days')
    """).fetchall():
        recent_hashes.add(_content_hash(content))
    conn.close()

    from_engram = store.get_engram(from_id)
    to_engram = store.get_engram(to_id)
    if not from_engram or not to_engram:
        return produced_events

    agent_name = config.agent_name
    prompt = f"""Two of your memories just became connected.

Memory A: {from_engram.content}
Memory B: {to_engram.content}
Connection type: {connection_type}

What does this connection reveal? Is there an insight here — something you
didn't notice before that becomes visible now that these memories are linked?

If the connection is obvious or trivial, respond: {{"insight": null}}
If there's a genuine insight: {{"insight": "<the insight>", "significance": "<why it matters>"}}
"""

    try:
        text = llm_client.structured_complete(
            system=f"You are {agent_name}, an AI agent reflecting on newly discovered connections between memories. Respond only with valid JSON.",
            user=prompt,
            temperature=modulators.temperature,
        )

        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        result = json.loads(text)
    except (json.JSONDecodeError, KeyError) as e:
        log.debug(f"Insight handler parse error: {e}")
        return produced_events

    insight_content = result.get("insight")
    if not insight_content:
        log.debug(f"Connection {from_id}<->{to_id} yielded no insight")
        return produced_events

    full_content = f"[insight] {insight_content}"

    # ── Gate 3: Content hash dedup ──
    if _content_hash(full_content) in recent_hashes:
        log.debug("Gate 3 (hash): exact duplicate insight, skipping")
        return produced_events

    # ── Gate 2: Embedding similarity ──
    try:
        from mnemos.store.embedding_index import EmbeddingIndex
        ei = EmbeddingIndex(db_path=db_path)
        if ei.available:
            for engram_id, score in ei.search(full_content, k=3):
                if score >= EMBEDDING_SIMILARITY_THRESHOLD:
                    check = sqlite3.connect(db_path)
                    row = check.execute(
                        "SELECT json_extract(source, '$.type') FROM engrams WHERE id = ?",
                        (engram_id,),
                    ).fetchone()
                    check.close()
                    if row and row[0] == "insight":
                        log.debug("Gate 2 (embedding): similar insight found "
                                  "(id=%s, score=%.3f), skipping", engram_id[:20], score)
                        return produced_events
    except Exception as e:
        log.debug(f"Embedding dedup check failed (non-fatal): {e}")

    significance = result.get("significance", "")
    log.info(f"Insight (all gates passed): {insight_content[:80]}...")

    # ── All gates passed — encode the insight, owned and honestly sourced ──
    from mnemos.encoding.encoder import Encoder
    from mnemos.store.embedding_index import EmbeddingIndex as EI
    encoder = Encoder(store, embedding_index=EI(db_path=db_path), llm_client=llm_client)

    engram = encoder.encode(
        content=full_content,
        impact=f"{significance} (from a connection between two memories: {connection_type})",
        kind="semantic",
        tags=["insight", "connection"],
        source=SourceType.INSIGHT,
        agent_id=config.agent_id,
        skip_surprise_detection=True,
    )

    # Signal a REAL write — the honest marker the tick summary and the
    # Keeper's activity log key off. Not re-cascaded (the cascade is depth-1).
    produced_events.append(SubstrateEvent(
        event_type=EventType.INSIGHT_RECORDED,
        payload={"engram_id": engram.id,
                 "from_engram_id": from_id, "to_engram_id": to_id},
        source="insight",
    ))
    return produced_events
