"""
Connection discovery pass: find semantic connections between engrams
that were missed during encoding.

Phase 2 upgrade:
- Uses embedding similarity (Gemini 3072-dim) alongside FTS5 for candidate discovery
- Uses LLM classifier for typed relationship assignment (7 types + NONE)
- Can reclassify existing low-quality connections (old all-"supports" monoculture)
- Cross-session connections: memories from different conversations that relate
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..core.engram import Connection
from ..core.types import ConnectionRelation, DEFAULT_AGENT_ID
from ..encoding.llm_classifier import MIN_CONFIDENCE, classify_connections

if TYPE_CHECKING:
    from ..store.sqlite_store import EngramStore
    from ..store.embedding_index import EmbeddingIndex
    from ..llm import LLMClient

log = logging.getLogger("mnemos.consolidation.connections")


def run_connection_discovery(
    store: EngramStore,
    embedding_index: Any | None = None,
    config: dict[str, Any] | None = None,
    llm_client: Any | None = None,
    agent_id: str = DEFAULT_AGENT_ID,
) -> dict[str, Any]:
    """Find semantically related engrams and create/reclassify connections.

    Two modes:
    1. **New connections** — find engrams with few connections and discover new ones
    2. **Reclassify** — upgrade old "supports" connections using LLM classification

    Uses both FTS5 and embedding similarity for candidate discovery.
    Uses LLM classifier for typed relationship assignment.

    Args:
        store: The engram store.
        embedding_index: Embedding index for semantic search (Phase 1.5+).
        config: Configuration dict with discovery parameters.
        llm_client: LLM client for typed classification. Falls back to
            SUPPORTS if not available.

    Returns:
        Statistics dict.
    """
    config = config or {}
    max_per_pass = config.get("max_engrams_per_discovery_pass", 50)
    max_per_engram = config.get("max_connections_per_engram", 10)
    reclassify_batch = config.get("reclassify_batch_size", 20)

    stats = {
        "engrams_processed": 0,
        "connections_created": 0,
        "connections_reclassified": 0,
        "connections_removed": 0,
        "connections_strengthened": 0,
        "embedding_candidates": 0,
        "fts_candidates": 0,
        # Law 9 honesty (SWEEP-B 2026-07-25): failed calls and deferrals
        # are counted, never silent — a night where the substrate was
        # down must not read like a tidy night.
        "discovery_call_failures": 0,
        "reclassify_call_failures": 0,
        "reclassify_deferred": 0,
    }

    all_active = store.get_active_engrams(agent_id=agent_id, limit=max_per_pass * 2)

    # ── Phase A: Discover new connections for underconnected engrams ──
    underconnected = []
    for engram in all_active:
        existing = store.get_connections(engram.id)
        if len(existing) < max_per_engram:
            underconnected.append((engram, existing))

    for engram, existing_connections in underconnected[:max_per_pass]:
        stats["engrams_processed"] += 1
        existing_target_ids = {c.target_id for c in existing_connections}
        candidates = []

        # 1. Embedding-based candidates (if available)
        if embedding_index and embedding_index.available:
            emb_results = embedding_index.search(
                engram.content, k=10, exclude_ids={engram.id},
            )
            for eid, score in emb_results:
                if eid not in existing_target_ids and score > 0.3:
                    candidate = store.get_engram(eid)
                    if candidate:
                        candidates.append(candidate)
                        stats["embedding_candidates"] += 1

        # 2. FTS5 candidates (supplement, catches keyword matches embeddings miss)
        words = [w for w in engram.content.split() if len(w) > 2 and w.isalnum()]
        if words:
            query = " OR ".join(f'"{w}"' for w in words[:8])
            try:
                fts_results = store.search_fts(query, limit=10)
                for match in fts_results:
                    if match.id != engram.id and match.id not in existing_target_ids:
                        # Don't duplicate embedding candidates
                        if not any(c.id == match.id for c in candidates):
                            candidates.append(match)
                            stats["fts_candidates"] += 1
            except Exception:
                pass

        if not candidates:
            continue

        # 3. Classify relationships via LLM (or fallback)
        if llm_client:
            classifications = classify_connections(llm_client, engram, candidates)
            if classifications is None:
                # The call failed (law 9): mint nothing from it, and say so.
                stats["discovery_call_failures"] += 1
                classifications = []
            for cls in classifications:
                tag_overlap = 0
                candidate = next((c for c in candidates if c.id == cls.candidate_id), None)
                if candidate:
                    tag_overlap = len(set(engram.tags) & set(candidate.tags))

                strength = min(0.95, cls.confidence + 0.05 * tag_overlap)

                engram.add_connection(
                    target_id=cls.candidate_id,
                    relation=cls.relation,
                    strength=round(strength, 3),
                    formed_by="consolidation",
                )
                stats["connections_created"] += 1
        else:
            # Fallback: old SUPPORTS behavior
            for match in candidates[:5]:
                tag_overlap = len(set(engram.tags) & set(match.tags))
                strength = min(0.8, 0.3 + 0.1 * tag_overlap)
                engram.add_connection(
                    target_id=match.id,
                    relation=ConnectionRelation.SUPPORTS,
                    strength=strength,
                    formed_by="consolidation",
                )
                stats["connections_created"] += 1

        store.save_engram(engram)

    # ── Phase B: Reclassify unclassified connections ──
    if llm_client:
        _reclassify_old_connections(
            store, llm_client, all_active,
            batch_size=reclassify_batch, stats=stats,
        )

    return stats


# Relations that were mechanically formed rather than semantically
# classified: legacy "supports" monoculture edges and the structural
# co-activation edges written by retrieval reconsolidation.
_RECLASSIFIABLE_RELATIONS = (
    ConnectionRelation.SUPPORTS,
    "supports",
    ConnectionRelation.CO_ACTIVATED,
    "co_activated",
)

# Edges whose relation was already earned by a real LLM judgment — the
# encoder's classified mint and this pass's own successful verdicts.
# Without this filter an honest SUPPORTS edge was re-sent to the
# substrate every deep cycle forever, and every cycle was one more
# chance for it to be lost to a bad night (SWEEP-B 2026-07-25).
_CLASSIFIED_FORMED_BY = ("encoding", "consolidation_reclassified")


def _reclassify_old_connections(
    store: EngramStore,
    llm_client: Any,
    all_active: list,
    batch_size: int,
    stats: dict,
) -> None:
    """Reclassify mechanically-formed connections using LLM classification.

    Finds connections that carry no real semantic judgment — the legacy
    "supports" monoculture and retrieval's "co_activated" edges — and
    asks the substrate what each really is.

    THE DELETION LAW (SWEEP-B 2026-07-25, laws 3 and 9): an edge is
    removed ONLY on the model's explicit, confident word that there is
    no relation — verdict NONE with confidence >= MIN_CONFIDENCE.
    Silence never deletes: a failed call, a truncated reply, an
    unmentioned target, or an honest low-confidence answer all DEFER the
    edge to a future cycle, counted, never destroyed. Before this, all
    four of those were read as "the model said NONE" — and the pass did
    the most deleting on exactly the nights the substrate was least able
    to answer (only successes counted against the batch cap, so failure
    walked the whole store).
    """
    calls_made = 0

    for engram in all_active:
        if calls_made >= batch_size:
            break

        connections = store.get_connections(engram.id)
        raw_connections = [
            c for c in connections
            if c.relation in _RECLASSIFIABLE_RELATIONS
            and c.formed_by not in _CLASSIFIED_FORMED_BY
        ]

        if not raw_connections:
            continue

        # Load the target engrams
        targets = []
        for conn in raw_connections:
            target = store.get_engram(conn.target_id)
            if target:
                targets.append(target)

        if not targets:
            continue

        # One call per engram, counted whether or not it succeeds — the
        # budget is calls, not victories.
        verdicts = classify_connections(llm_client, engram, targets,
                                        include_verdicts=True)
        calls_made += 1

        if verdicts is None:
            # The call failed. Not one edge may be touched on its account.
            stats["reclassify_call_failures"] += 1
            continue

        by_target = {v.candidate_id: v for v in verdicts}

        for conn in raw_connections:
            v = by_target.get(conn.target_id)
            if v is None:
                # Unmentioned (truncated tail, skipped by the model, or
                # the target failed to load) — silence defers, always.
                stats["reclassify_deferred"] += 1
                continue
            if v.confidence < MIN_CONFIDENCE:
                # An honest "I'm not sure" — the most common verdict a
                # healthy night produces. It used to delete; it defers.
                stats["reclassify_deferred"] += 1
                continue
            if v.relation is None:
                # The model's explicit, confident NONE — the one word
                # that removes. Relation-scoped: only THIS row dies; a
                # semantic edge this pass earned earlier on the same
                # pair survives (the PK is (source, target, relation)).
                store.remove_connection(engram.id, conn.target_id,
                                        relation=conn.relation)
                stats["connections_removed"] += 1
            else:
                # A real relation, confidently judged: replace the old
                # row rather than stacking a second one beside it — the
                # PK includes relation, so save-without-remove left the
                # stale mechanical row in place forever.
                store.remove_connection(engram.id, conn.target_id,
                                        relation=conn.relation)
                conn.relation = v.relation
                conn.strength = round(v.confidence, 3)
                conn.formed_by = "consolidation_reclassified"
                store.save_connection(engram.id, conn)
                stats["connections_reclassified"] += 1
