"""
Mnemos MCP Server.

Exposes Mnemos memory operations as MCP tools that any agent can call.
Uses the Anthropic MCP Python SDK (FastMCP).

Tools:
    mnemos_remember     — Encode a new memory
    mnemos_recall       — Retrieve relevant memories
    mnemos_inspect      — View full details of a memory
    mnemos_status       — Get memory system status
    mnemos_beliefs      — List current beliefs
    mnemos_forget       — Archive a specific memory
    mnemos_consolidate  — Trigger a consolidation cycle

Usage:
    mnemos serve        — Start as stdio MCP server (for agent config)
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .core.types import EngramKind, SourceType
from .store.sqlite_store import EngramStore
from .store.embedding_index import EmbeddingIndex
from .encoding.encoder import Encoder
from .retrieval.reactive import ReactiveRetriever
from .consolidation.daemon import ConsolidationDaemon
from .interface.openclaw_export import OpenClawExporter

# Global state — initialized when server starts
_store: EngramStore | None = None
_encoder: Encoder | None = None
_retriever: ReactiveRetriever | None = None
_embedding_index: EmbeddingIndex | None = None
_shared_pool = None

mcp = FastMCP("mnemos")


_llm_client = None


def _init_store(db_path: str = "~/.mnemos/memory.db") -> None:
    """Initialize the global store, helpers, and auto-detect LLM client."""
    global _store, _encoder, _retriever, _llm_client, _embedding_index, _shared_pool
    if _store is None:
        _store = EngramStore(db_path)
        # Initialize embedding index (same DB path — gracefully degrades)
        _embedding_index = EmbeddingIndex(db_path=db_path)
        # Auto-detect LLM client from env vars (before encoder, which uses it)
        from .llm import create_client
        _llm_client = create_client()
        # Initialize shared memory pool
        from .multiagent.shared_pool import SharedPool
        _shared_pool = SharedPool()  # defaults to ~/.mnemos/shared.db
        _encoder = Encoder(
            _store,
            embedding_index=_embedding_index,
            llm_client=_llm_client,
            shared_pool=_shared_pool,
        )
        _retriever = ReactiveRetriever(
            _store,
            embedding_index=_embedding_index,
            shared_store=_shared_pool._store,
        )


def _ensure_store() -> EngramStore:
    """Get the store, initializing if needed."""
    if _store is None:
        _init_store()
    return _store  # type: ignore


@mcp.tool()
def mnemos_remember(
    content: str,
    impact: str = "",
    kind: str = "semantic",
    tags: str = "",
    agent_id: str = "default",
    skip_surprise_detection: bool = False,
) -> str:
    """Encode a new memory into the Mnemos living memory system.

    Use this to store important information, user preferences, decisions,
    insights, or anything worth remembering across sessions.

    Args:
        content: What happened — the event, information, or observation.
        impact: What it meant — how it changed understanding. Optional but valuable.
            Example: "After this, I understand that patience with debugging is essential."
            When provided, this lasting insight survives even as details fade over time.
        kind: Memory type — "episodic" (experiences), "semantic" (facts/knowledge),
              "procedural" (how-to knowledge). Default: "semantic".
        tags: Comma-separated tags for categorization. Example: "python,debugging,preferences"
        agent_id: Which agent's memory to store in. Default: "default".
    """
    _ensure_store()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    engram = _encoder.encode(  # type: ignore
        content=content,
        impact=impact,
        kind=kind,
        tags=tag_list,
        source=SourceType.SESSION,
        agent_id=agent_id,
        skip_surprise_detection=skip_surprise_detection,
    )

    return (
        f"Remembered: {engram.id}\n"
        f"  Confidence: {engram.source.confidence}\n"
        f"  Connections: {len(engram.connections)} discovered\n"
        f"  Tags: {', '.join(engram.tags) or '(none)'}"
    )


@mcp.tool()
def mnemos_recall(
    query: str,
    max_results: int = 5,
    agent_id: str = "default",
) -> str:
    """Retrieve memories relevant to a query.

    Searches across all stored memories using full-text search and
    connection graph traversal. Results are scored by relevance,
    recency, strength, connections, and emotional congruence.

    Every recalled memory is reconsolidated — its connections and
    strength are updated based on this retrieval context.

    Args:
        query: What to search for. Natural language works best.
        max_results: Maximum number of results (default: 5).
        agent_id: Which agent's memory to search. Default: "default".
    """
    _ensure_store()
    emotional_state = _store.get_latest_emotional_state(agent_id)  # type: ignore

    results = _retriever.retrieve(  # type: ignore
        cue=query,
        agent_id=agent_id,
        max_results=max_results,
        emotional_state=emotional_state,
    )

    if not results:
        return "No relevant memories found."

    lines = []
    for r in results:
        # Prefer impact (the lesson) over content (what happened)
        display = r.engram.impact if r.engram.impact else r.engram.content
        if len(display) > 150:
            display = display[:147] + "..."
        pct = int(r.engram.source.confidence * 100)
        lines.append(
            f"[{r.score:.2f}] {display}\n"
            f"       id={r.engram.id[:25]}... kind={r.engram.kind} confidence={pct}%"
        )

    return f"Found {len(results)} memories:\n\n" + "\n\n".join(lines)


@mcp.tool()
def mnemos_inspect(engram_id: str) -> str:
    """View full details of a specific memory.

    Shows content, metadata, connections, version history, and
    the original content at encoding time.

    Args:
        engram_id: The memory ID to inspect.
    """
    _ensure_store()
    engram = _store.get_engram(engram_id)  # type: ignore
    if engram is None:
        return f"Memory not found: {engram_id}"

    lines = [
        f"ID: {engram.id}",
        f"Content: {engram.content}",
        f"Impact: {engram.impact or '(not yet distilled)'}",
        f"Kind: {engram.kind}",
        f"Tags: {', '.join(engram.tags) or '(none)'}",
        f"State: {engram.state}",
        f"Resolution: {engram.resolution}",
        f"Strength: {engram.strength:.4f}",
        f"Stability: {engram.stability:.4f}",
        f"Accessibility: {engram.accessibility:.4f}",
        f"Confidence: {engram.source.confidence} ({engram.source.confidence_source})",
        f"Created: {engram.created_at}",
        f"Last accessed: {engram.last_accessed}",
        f"Access count: {engram.access_count}",
        f"Reconsolidations: {engram.reconsolidation_count}",
        f"Connections: {len(engram.connections)}",
    ]
    for c in engram.connections:
        lines.append(f"  → {c.target_id[:30]}... ({c.relation}, str={c.strength:.2f})")
    lines.append(f"Versions: {len(engram.versions)}")
    if engram.content != engram.content_at_encoding:
        lines.append(f"Original: {engram.content_at_encoding[:150]}...")

    return "\n".join(lines)


@mcp.tool()
def mnemos_status(agent_id: str = "default") -> str:
    """Get memory system status and statistics.

    Shows counts of active/dormant/archived memories, connections,
    beliefs, reconsolidation events, and accessibility distribution.

    Args:
        agent_id: Which agent's status to show. Default: "default".
    """
    _ensure_store()
    stats = _store.get_stats(agent_id)  # type: ignore

    lines = [
        f"Mnemos Status (agent: {agent_id})",
        f"  Active engrams: {stats.get('engrams_active', 0)}",
        f"  Dormant: {stats.get('engrams_dormant', 0)}",
        f"  Archived: {stats.get('archived', 0)}",
        f"  Connections: {stats.get('connections', 0)}",
        f"  Active beliefs: {stats.get('beliefs_active', 0)}",
        f"  Reconsolidations: {stats.get('reconsolidation_events', 0)}",
    ]
    if "accessibility_avg" in stats:
        lines.append(f"  Avg accessibility: {stats['accessibility_avg']:.3f}")

    es = _store.get_latest_emotional_state(agent_id)  # type: ignore
    if es:
        lines.append(
            f"  Emotional state: curiosity={es.curiosity:.1f} "
            f"clarity={es.clarity:.1f} warmth={es.warmth:.1f}"
        )

    return "\n".join(lines)


@mcp.tool()
def mnemos_beliefs(agent_id: str = "default", domain: str = "") -> str:
    """List current beliefs with confidence levels.

    Args:
        agent_id: Which agent's beliefs to show. Default: "default".
        domain: Filter by domain (e.g., "engineering", "social"). Empty = all.
    """
    _ensure_store()
    beliefs = _store.get_beliefs(  # type: ignore
        agent_id=agent_id,
        domain=domain or None,
        active_only=True,
    )

    if not beliefs:
        return "No active beliefs found."

    lines = []
    for b in beliefs:
        pct = int(b.confidence * 100)
        revisions = len(b.revision_history)
        lines.append(f"- {b.content} [{b.domain}, {pct}%, {revisions} revisions]")

    return f"{len(beliefs)} active beliefs:\n\n" + "\n".join(lines)


@mcp.tool()
def mnemos_shared(
    query: str = "",
    max_results: int = 10,
    agent_id: str = "default",
) -> str:
    """Get memories shared by other agents in the shared memory pool.

    Shows what other agents have learned, decided, built, or discovered.
    Use this to stay in sync with the team's shared knowledge.

    Args:
        query: Optional search query. If empty, returns most recent shared memories.
        max_results: Maximum number of results (default: 10).
        agent_id: Your agent ID (used for attribution, not filtering).
    """
    _ensure_store()
    if not _shared_pool:
        return "Shared memory pool not initialized."

    shared = _shared_pool.get_shared(
        agent_id=agent_id,
        limit=max_results,
        query=query or None,
    )

    if not shared:
        return "No shared memories found."

    lines = []
    for engram in shared:
        display = engram.impact if engram.impact else engram.content
        if len(display) > 150:
            display = display[:147] + "..."
        pct = int(engram.source.confidence * 100)
        lines.append(
            f"[{engram.owner_agent_id}] {display}\n"
            f"       id={engram.id[:25]}... kind={engram.kind} confidence={pct}%"
        )

    return f"Found {len(shared)} shared memories:\n\n" + "\n\n".join(lines)


@mcp.tool()
def mnemos_forget(engram_id: str) -> str:
    """Archive a specific memory (soft delete).

    The memory moves to cold storage. It can be restored via resharpen
    if triggered by relevant context in the future.

    Args:
        engram_id: The memory ID to archive.
    """
    _ensure_store()
    engram = _store.get_engram(engram_id)  # type: ignore
    if engram is None:
        return f"Memory not found: {engram_id}"

    _store.archive_engram(engram, reason="user_requested")  # type: ignore
    return f"Archived: {engram_id}\n  Content was: {engram.content[:100]}..."


@mcp.tool()
def mnemos_consolidate(deep: bool = False, agent_id: str = "default") -> str:
    """Run a memory consolidation cycle.

    Shallow cycle: decay + connection discovery (fast, ~1 second)
    Deep cycle: adds softening + belief review + reflection (slower, may use LLM)

    Args:
        deep: If true, run deep consolidation with all passes.
        agent_id: Which agent's memory to consolidate. Default: "default".
    """
    _ensure_store()
    daemon = ConsolidationDaemon(store=_store, config={}, llm_client=_llm_client, embedding_index=_embedding_index)  # type: ignore
    stats = daemon.run_cycle(deep=deep, agent_id=agent_id)

    lines = [
        f"Consolidation complete ({stats.get('cycle_type', 'unknown')})",
        f"  Passes: {', '.join(stats.get('passes_run', []))}",
    ]

    if "decay" in stats:
        d = stats["decay"]
        lines.append(f"  Decay: {d.get('engrams_decayed', 0)} decayed, {d.get('engrams_archived', 0)} archived")
    if "connection_discovery" in stats:
        cd = stats["connection_discovery"]
        lines.append(f"  Connections: {cd.get('connections_created', 0)} new, {cd.get('connections_strengthened', 0)} strengthened")
    if "softening" in stats:
        lines.append(f"  Softened: {stats['softening'].get('engrams_softened', 0)} memories")
    if "reflection" in stats:
        ref = stats["reflection"]
        lines.append(f"  Thoughts: {ref.get('thoughts_generated', 0)} generated")

    errors = [k for k in stats if k.endswith("_error")]
    for e in errors:
        lines.append(f"  ERROR: {e}: {stats[e]}")

    return "\n".join(lines)


def run_server(db_path: str = "~/.mnemos/memory.db") -> None:
    """Start the MCP server in stdio mode."""
    _init_store(db_path)
    mcp.run()
