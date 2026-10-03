"""
Core retrieval for Mnemos — resonance-based, not search-based.

Shift 4: Instead of a weighted scoring formula, retrieval works through
spreading activation in the connection graph. FTS finds seed nodes,
activation propagates through connections weighted by relation type,
and what lights up after N hops is what's relevant.

The graph structure IS the relevance model. No formula needed.

Pipeline:
1. FTS (by the cue's telling words) + meaning search → seed nodes, each
   starting by how well it matches (Tara's ruling 2026-10-03: every seed
   used to start at 1.0, so the most-linked cluster outvoted the memory
   she meant — 30% exact recall on Quill's seeded memories)
2. Spreading activation through connection graph (3 hops, links pass a
   quarter of their old strength)
3. Emotional bias applied multiplicatively
4. Threshold → the best ~30, re-read by the reranker, which sets the order
5. Reconsolidation on all returned engrams
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from ..core.engram import Engram
from ..core.emotional_state import EmotionalState
from ..core.types import ConnectionRelation
from .reconsolidation import reconsolidate
from .search_words import fts_query, telling_words

if TYPE_CHECKING:
    from ..store.sqlite_store import EngramStore


@dataclass
class RetrievalResult:
    """A scored retrieval result wrapping an engram."""

    engram: Engram
    score: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)
    retrieval_path: str = "fts"


# How much of a link's strength passes along it (Tara's ruling 2026-10-03).
# At full strength links pulled well-linked memories past the one she meant;
# a quarter keeps neighbours coming along without outvoting the best match.
LINK_PULL = 0.25
# How many of recall's best the reranker re-reads.
RERANK_POOL = 30
# Seeds the word search and the meaning search each offer.
FTS_SEEDS = 30
MEANING_SEEDS = 20
MEANING_FLOOR = 0.3


# Activation weights by connection relation type
_RELATION_WEIGHTS: dict[str, float] = {
    ConnectionRelation.SUPPORTS: 1.0,
    ConnectionRelation.ELABORATES: 1.0,
    ConnectionRelation.CAUSES: 0.9,
    ConnectionRelation.DISTILLED_INTO: 0.9,
    ConnectionRelation.PART_OF: 0.9,
    ConnectionRelation.INSTANCE_OF: 0.9,
    ConnectionRelation.ANALOGOUS_TO: 0.8,
    ConnectionRelation.TEMPORAL_BEFORE: 0.4,
    ConnectionRelation.TEMPORAL_AFTER: 0.4,
    ConnectionRelation.CONTRADICTS: 0.5,  # Still propagate — contradictions are relevant
    ConnectionRelation.INTERFERES_WITH: 0.3,
    ConnectionRelation.CO_ACTIVATED: 0.6,  # Correlation, weaker than evidence relations
}


class ReactiveRetriever:
    """Resonance-based memory retrieval.

    Instead of scoring candidates with a weighted formula, retrieval
    works through spreading activation in the connection graph. FTS
    finds seed nodes, activation spreads through typed connections,
    and what lights up is what's relevant.

    Usage:
        retriever = ReactiveRetriever(store)
        results = retriever.retrieve("What does the user think about dark mode?")
    """

    def __init__(
        self,
        store: EngramStore,
        embedding_index: Any | None = None,
        shared_store: Any | None = None,
        activation_depth: int = 3,
        activation_decay: float = 0.5,
        activation_threshold: float = 0.1,
        reconsolidation_enabled: bool = True,
        confidence_floor: float = 0.3,
        link_pull: float = LINK_PULL,
        reranker: Any | None = "default",
        rerank_pool: int = RERANK_POOL,
    ) -> None:
        self._store = store
        self._embedding_index = embedding_index
        self._shared_store = shared_store
        self._depth = activation_depth
        self._decay = activation_decay
        self._threshold = activation_threshold
        self._reconsolidation_enabled = reconsolidation_enabled
        self._confidence_floor = confidence_floor
        self._link_pull = link_pull
        if reranker == "default":
            from .rerank import default_reranker
            reranker = default_reranker()
        self._reranker = reranker
        self._rerank_pool = rerank_pool

    def retrieve(
        self,
        cue: str,
        agent_id: str = "default",
        max_results: int = 10,
        emotional_state: EmotionalState | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve memories via resonance — spreading activation through the graph.

        Pipeline:
        1. FTS (telling words) + meaning search → seed nodes, each starting
           by how well it matches
        2. Spreading activation (3 hops, decay per hop, weighted by relation,
           a quarter of the link's strength)
        3. Emotional bias (multiplicative boost for congruent tags)
        4. Filter by threshold + confidence floor; the reranker re-reads the
           best `rerank_pool` and sets their order
        5. Reconsolidate returned engrams

        Returns:
            List of RetrievalResult in the reranker's order when it runs,
            else by activation level (descending).
        """
        if not cue or not cue.strip():
            return []

        # 1. SEED: Find entry points via FTS + embeddings. Each seed starts
        # by how well it matches — the better of its word rank and its
        # meaning closeness — never all alike.
        seeds: dict[str, Engram] = {}
        start: dict[str, float] = {}

        # FTS seeds by the cue's telling words (punctuation cleaned, common
        # words skipped, rarest first — the linking fix, Tara 2026-10-02)
        words = telling_words(cue, self._store)
        fts_q = fts_query(words) if words else _to_fts_query(cue)
        fts_results = self._store.search_fts(fts_q, limit=FTS_SEEDS)
        fts_rank = 0
        for engram in fts_results:
            if engram.owner_agent_id == agent_id:
                seeds[engram.id] = engram
                start[engram.id] = 1.0 - fts_rank / FTS_SEEDS
                fts_rank += 1

        # Shared DB seeds (cross-agent shared memories)
        if self._shared_store:
            try:
                shared_fts = self._shared_store.search_fts(fts_q, limit=20)
                for r, engram in enumerate(shared_fts):
                    if engram.visibility in ("shared", "public") and engram.id not in seeds:
                        seeds[engram.id] = engram
                        start[engram.id] = 1.0 - r / FTS_SEEDS
            except Exception:
                pass  # Shared store is optional

        # Embedding seeds (meaning matching — finds what FTS misses), and
        # every seed's meaning closeness against the best one for this cue
        if self._embedding_index and hasattr(self._embedding_index, 'search'):
            try:
                ranked = self._embedding_index.search(cue, k=FTS_SEEDS * 4)
                sims = dict(ranked)
                best = ranked[0][1] if ranked else 1.0
                span = max(1e-6, best - MEANING_FLOOR)
                offered = 0
                for eid, similarity in ranked:
                    if offered >= MEANING_SEEDS:
                        break
                    if eid in seeds or similarity <= MEANING_FLOOR:
                        continue
                    engram = self._store.get_engram(eid)
                    if engram and engram.state == "active" and engram.owner_agent_id == agent_id:
                        seeds[eid] = engram
                        start[eid] = 0.0
                        offered += 1
                for eid in seeds:
                    closeness = min(1.0, max(0.0, (sims.get(eid, MEANING_FLOOR) - MEANING_FLOOR) / span))
                    start[eid] = max(start.get(eid, 0.0), closeness)
            except Exception:
                pass  # Embeddings are optional — FTS still works

        if not seeds:
            return []

        # 2. PROPAGATE: Spreading activation through connection graph
        activation: dict[str, float] = {}

        # Seeds start by how well they match (floor at the threshold, so
        # a seed is never lost before it can be weighed)
        for seed_id in seeds:
            activation[seed_id] = max(self._threshold, start.get(seed_id, 1.0))

        # Spread through connections
        for hop in range(1, self._depth + 1):
            hop_decay = self._decay ** hop
            new_activation: dict[str, float] = defaultdict(float)

            for engram_id, current_act in list(activation.items()):
                if current_act < self._threshold:
                    continue

                connections = self._store.get_connections(engram_id)
                # Cross-DB connections: also check shared store
                if self._shared_store:
                    try:
                        connections = connections + self._shared_store.get_connections(engram_id)
                    except Exception:
                        pass
                for conn in connections:
                    # Weight by relation type
                    relation_weight = _RELATION_WEIGHTS.get(conn.relation, 0.5)
                    propagated = (current_act * hop_decay * conn.strength
                                  * relation_weight * self._link_pull)

                    if propagated > self._threshold * 0.5:
                        new_activation[conn.target_id] += propagated

            # Merge new activations (additive — multiple paths reinforce)
            for eid, act in new_activation.items():
                activation[eid] = activation.get(eid, 0.0) + act

        # 3. EMOTIONAL BIAS: multiplicative boost for congruent engrams
        if emotional_state:
            bias = emotional_state.get_retrieval_bias()
            if bias:
                for eid in list(activation.keys()):
                    engram = seeds.get(eid) or self._store.get_engram(eid)
                    if engram and engram.tags:
                        overlap = sum(bias.get(tag, 0.0) for tag in engram.tags)
                        if overlap > 0:
                            activation[eid] *= (1.0 + min(0.5, overlap))

        # 4. FILTER + LOAD: threshold, confidence floor, build results
        results: list[RetrievalResult] = []
        for eid, act_level in activation.items():
            if act_level < self._threshold:
                continue

            engram = seeds.get(eid)
            if not engram:
                engram = self._store.get_engram(eid)
            # Cross-DB: check shared store if not found in private
            if not engram and self._shared_store:
                engram = self._shared_store.get_engram(eid)

            if not engram or engram.state != "active":
                continue
            # Allow own engrams + shared/public from other agents
            if engram.owner_agent_id != agent_id and engram.visibility == "private":
                continue

            if engram.source.confidence < self._confidence_floor:
                continue

            path = "fts" if eid in seeds else "resonance"
            results.append(
                RetrievalResult(
                    engram=engram,
                    score=round(act_level, 4),
                    score_breakdown={
                        "activation": round(act_level, 4),
                        "is_seed": eid in seeds,
                    },
                    retrieval_path=path,
                )
            )

        # Sort by activation level
        results.sort(key=lambda r: r.score, reverse=True)

        # 4b. RERANK: the reranker re-reads the best few beside the cue and
        # sets their order (activation stays on each result as its score).
        if self._reranker is not None and len(results) > 1:
            pool = results[: self._rerank_pool]
            scores = self._reranker.scores(cue, [r.engram.content for r in pool])
            if scores is not None:
                for r, s in zip(pool, scores):
                    r.score_breakdown["rerank"] = round(s, 4)
                order = sorted(range(len(pool)), key=lambda i: -scores[i])
                results = [pool[i] for i in order] + results[self._rerank_pool:]
        top_results = results[:max_results]

        # 5. RECONSOLIDATE returned engrams
        if self._reconsolidation_enabled and top_results:
            co_retrieved_ids = [r.engram.id for r in top_results]
            for result in top_results:
                # Reconsolidate in the engram's home store
                target_store = self._store
                if (
                    result.engram.owner_agent_id != agent_id
                    and self._shared_store
                ):
                    target_store = self._shared_store
                result.engram = reconsolidate(
                    engram=result.engram,
                    current_context=cue,
                    co_retrieved_ids=[
                        eid for eid in co_retrieved_ids if eid != result.engram.id
                    ],
                    store=target_store,
                )

        return top_results


def _to_fts_query(cue: str) -> str:
    """Convert a natural language cue to an FTS5 OR query.

    Words are quoted for FTS5 safety (prevents operators like hyphens
    from causing errors).
    """
    words = [w for w in cue.split() if len(w) > 2 and w.isalnum()]
    if not words:
        clean = "".join(c for c in cue if c.isalnum() or c == " ").strip()
        return f'"{clean}"' if clean else '""'
    return " OR ".join(f'"{w}"' for w in words)
