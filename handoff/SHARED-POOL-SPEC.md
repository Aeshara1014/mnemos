# Mnemos Shared Memory Pool — Build Spec

## Overview

Implement the multi-agent shared memory pool so that multiple agents can seamlessly know what each other are doing, have done, decided, and discussed. The schema already supports this — the columns exist, they just aren't being used.

---

## Current State

### Source Code
- **Mnemos source**: `~/Documents/Repositories/memory-concepts/mnemos/`
- **Multiagent stubs**: `mnemos/multiagent/` — `shared_pool.py`, `relationships.py`, `federation.py`, `attestation.py`
- All stubs have correct interfaces but return empty / `pass`

### Databases (all SQLite)
| Agent | Path | Engrams | Size |
|-------|------|---------|------|
| Vektor | `~/.mnemos/vektor.db` | 1,057 active + 74 default | 19MB |
| Anima | `~/.mnemos/anima.db` | ~114 | 2MB |
| Luca | `~/.mnemos/memory.db` | ~58 | 3.5MB |

### Schema Already Has What We Need

**`engrams` table** — key columns:
```
id: TEXT (primary key, ULID-based)
content: TEXT (the memory text)
content_at_encoding: TEXT (original text at time of creation)
impact: TEXT (why this memory matters)
kind: TEXT (default 'episodic') — episodic, semantic, procedural
tags: TEXT (JSON array of tag strings)
owner_agent_id: TEXT (default 'default') — WHO created this
visibility: TEXT (default 'private') — WHO can see it
state: TEXT (default 'active') — active, dormant, archived
strength: REAL (0-1, how strong the memory is)
stability: REAL (0-1, how resistant to decay)
accessibility: REAL (0-1, how easy to recall)
encoding_context: TEXT (JSON — emotional state, attention, surprise, session_id, etc.)
source: TEXT (JSON — extraction type, model, confidence)
lineage: TEXT (JSON — parent engrams, supersedes, branch_id)
created_at: TEXT (ISO timestamp)
last_accessed: TEXT (ISO timestamp)
access_count: INTEGER
reconsolidation_count: INTEGER
```

**`connections` table:**
```
source_id: TEXT (engram ID)
target_id: TEXT (engram ID)
relation: TEXT — supports, grounds, extends, parallels, temporal_after, causes, contradicts, synthesizes
strength: REAL (0-1)
formed_at: TEXT (ISO timestamp)
formed_by: TEXT (what created this connection)
```

**`beliefs` table:**
```
id: TEXT
agent_id: TEXT — which agent holds this belief
content: TEXT
confidence: REAL (0-1)
domain: TEXT
created_at: TEXT
last_revised: TEXT
last_challenged: TEXT
revision_history: TEXT (JSON)
superseded_by: TEXT
supporting_engram_ids: TEXT (JSON array)
```

### Current Values
- **ALL 1,133 engrams** have `visibility = 'private'`
- **1,059 engrams** have `owner_agent_id = 'vektor'`, 74 have `'default'` (from bootstrap extraction)
- Connection types in use: supports (2250), grounds (994), extends (862), parallels (625), temporal_after (460), causes (215), contradicts (175), synthesizes (23)

### Other Tables
- `embeddings` — vector embeddings for semantic search
- `engrams_fts` — full-text search index
- `beliefs` — agent-specific belief system
- `emotional_state_history` — emotional context over time
- `consolidation_log` — memory consolidation history
- `agent_identity` — agent self-model
- `archive` — archived/decayed engrams
- `versions` — engram version history (reconsolidation)

---

## What to Build

### Priority 1: SharedPool Implementation (`mnemos/multiagent/shared_pool.py`)

The stub already has the right interface. Fill in:

```python
class SharedPool:
    def __init__(self, store: EngramStore):
        self._store = store

    def publish(self, engram: Engram, visibility: str = "shared") -> None:
        """Set engram.visibility = visibility and persist."""
        # Update the engram's visibility field in the DB
        # If visibility is 'shared', all agents on this instance can see it
        # If 'public', it's available for federation (future)

    def get_shared(self, agent_id: str, limit: int = 50, 
                   query: str = None, kind: str = None) -> list[Engram]:
        """Return engrams where:
           - owner_agent_id == agent_id AND visibility in ('private', 'shared', 'public')
           - OR visibility in ('shared', 'public') (from any agent)
           Basically: your own stuff + everything marked shared/public.
           Optional: filter by semantic query or kind."""

    def resolve_conflict(self, engram_a_id: str, engram_b_id: str) -> dict:
        """When two agents create contradictory shared engrams about the same topic:
           - Compare confidence/strength
           - Check if one supersedes the other (lineage.supersedes)
           - Return resolution: merge, keep_both, supersede_a, supersede_b"""
```

### Priority 2: Auto-Publish Hook

When an engram is created via the normal encoding path, check if it should be shared:

**Always share:**
- Task completions ("I built X", "I deployed Y")
- Decisions ("We decided to use React for the frontend")
- Conversation summaries (agent-to-agent or agent-to-human)
- Error discoveries ("X is broken because Y")

**Keep private:**
- Internal reasoning / thinking traces
- Emotional state snapshots
- Working memory that's still being formed

Implementation: Add a `should_auto_share(engram) -> bool` function that checks `kind`, `tags`, and content patterns. Hook it into the encoding pipeline (`mnemos/encoding/`).

### Priority 3: Shared DB Router (v1: Single DB)

For v1, the simplest approach: **all agents read/write to one shared DB**.

- Create `~/.mnemos/shared.db` 
- Each agent's bridge/indexer writes to this DB with their `owner_agent_id`
- Query filtering handles visibility (see `get_shared` above)
- Individual DBs can remain for private/fast-access memories
- The shared DB is the "workspace memory" — what everyone knows

Alternatively: keep individual DBs but add a sync layer that copies shared engrams between them. More complex but preserves isolation. Recommend single DB for v1.

### Priority 4: Relationship Tracking (`mnemos/multiagent/relationships.py`)

Track agent-to-agent relationships:
```python
class RelationshipTracker:
    def record_interaction(self, agent_a: str, agent_b: str, 
                          interaction_type: str, context: str) -> None:
        """Record that two agents interacted (conversation, task handoff, review, etc.)"""
    
    def get_relationship(self, agent_a: str, agent_b: str) -> dict:
        """Return interaction history, trust level, collaboration patterns"""
    
    def get_collaborators(self, agent_id: str) -> list[dict]:
        """Return all agents this agent has worked with, sorted by interaction frequency"""
```

### Lower Priority: Federation & Attestation

These are for multi-instance / multi-customer scenarios. Skip for now.

---

## Key Files to Read First

1. **`mnemos/core/engram.py`** — The Engram dataclass. Understand the fields.
2. **`mnemos/store/sqlite_store.py`** — The EngramStore. All DB operations go through here. You'll need to add/modify query methods.
3. **`mnemos/encoding/encoder.py`** — Where engrams get created. Hook auto-publish here.
4. **`mnemos/retrieval/`** — How engrams are recalled. Shared pool queries need to integrate here.
5. **`mnemos/multiagent/shared_pool.py`** — The stub you're implementing.
6. **`mnemos/consolidation/`** — Memory decay, strengthening, connection discovery. Shared engrams need to participate in consolidation.

---

## Integration Points

### Bridge Scripts (existing)
- **Vektor**: `~/clawd/inner_life/mnemos_bridge.py` — CLI for remember/recall/status
- **Anima**: `~/clawd-anima/inner_life/mnemos_bridge.py`
- **Indexer**: `~/clawd/inner_life/mnemos_indexer.py` — Cron that extracts memories from session transcripts

These will need to be updated to:
1. Set `owner_agent_id` when creating engrams (most already do)
2. Set `visibility` based on `should_auto_share()`
3. Query the shared pool when recalling (not just own DB)

### OpenClaw Crons
- `mnemos-session-indexer` — runs every 30min, extracts memories from conversations
- `vektor-substrate-tick` — runs every 4h, handles decay/consolidation
- `observer-context-sync` — runs every 30min, writes active-context.md

The session indexer is the main entry point for new memories. It should auto-share relevant ones.

---

## Testing

After implementation:
1. Create a shared engram from Vektor's bridge: `python3 mnemos_bridge.py remember "Test shared memory" --visibility shared`
2. Query from Anima's bridge: should see Vektor's shared engram
3. Create a private engram from Vektor: should NOT appear in Anima's queries
4. Test auto-publish: create an engram with tags like "task_completion" — should auto-set to shared
5. Test conflict resolution: two agents create contradictory beliefs, resolve

---

## Customer Multi-Tenancy (Future Context)

Each customer instance = one shared DB. Agents within that instance share memories. No cross-customer leakage. The `visibility` field handles the scoping:
- `private` = only this agent
- `shared` = all agents in this instance/customer
- `public` = federated (opt-in, future)

Don't build multi-tenancy now, but don't make architectural decisions that prevent it. The single-DB-per-instance model naturally supports this.
