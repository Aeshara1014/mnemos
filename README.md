# Mnemos

**Living Memory Architecture for Autonomous AI Agents**

Memory is not a feature of the agent. Memory *is* the agent.

Mnemos replaces passive note-storage with active, living memory that encodes at varying depths, forgets naturally, predicts what it'll need, and changes its memories every time it touches them.

Mnemos is a complete agent cognition system — not just a memory library. It provides persistent identity, living memory, autonomous maintenance crons, a cognitive substrate, and cross-agent awareness. Together, these layers give an AI agent continuous selfhood across sessions.

Built as an [MCP](https://modelcontextprotocol.io/) server with 7 tools. SQLite-backed. No external services required — optional LLM integration for richer consolidation.

---

## The Full Stack

Mnemos operates in five layers:

```
Identity Architecture    SOUL.md · IDENTITY.md · MEMORY.md · active-context.md
Cron Suite               Observer · Indexer · Substrate · Maintenance · Bridge
Mnemos Core              Engrams · Connections · Beliefs · Consolidation
Substrate                Decay · Dreaming · Reflection · Modulators · Events
Cross-Agent Layer        Shared Pool · Bridge · Federation · Attestation
```

**Identity** defines who the agent is. **Crons** keep everything current autonomously. **Core** is the living memory graph. **Substrate** is the subconscious — consolidation, dreaming, reflection. **Cross-Agent** enables multi-agent awareness.

See [docs/architecture.md](docs/architecture.md) for the full architecture overview.

---

## Quick Start — Full Stack

Bootstrap a complete agent with one command:

```bash
# Install Mnemos
pip install "mnemos[all]"

# Bootstrap a complete agent stack
mnemos bootstrap \
  --agent-name Nova \
  --workspace ~/nova \
  --user-name Riley

# This creates:
#   ~/nova/SOUL.md              Agent personality and philosophy
#   ~/nova/IDENTITY.md          Operational identity and boundaries
#   ~/nova/MEMORY.md            Living memory document
#   ~/nova/AGENTS.md            Multi-agent configuration
#   ~/nova/HEARTBEAT.md         Health monitoring
#   ~/nova/memory/              Active context and cross-agent files
#   ~/nova/daily/               Morning briefs and debriefs
#   ~/nova/inner_life/          Substrate outputs
#   ~/nova/.env                 Environment configuration template
#   ~/.mnemos/nova.db           Mnemos database

# Follow the printed instructions to install OpenClaw crons
```

## Quick Start — Library Only

```bash
# Install core (SQLite + stdlib only)
pip install mnemos

# Install with MCP server support
pip install "mnemos[mcp]"

# Install everything
pip install "mnemos[all]"

# Initialize a memory database
mnemos init

# Check it's working
mnemos stats
```

## MCP Server

Mnemos exposes 7 tools via the Model Context Protocol:

| Tool | Description |
|------|-------------|
| `mnemos_remember` | Encode a new memory with content, impact, kind, and tags |
| `mnemos_recall` | Retrieve relevant memories (triggers reconsolidation) |
| `mnemos_inspect` | View full details of a specific memory |
| `mnemos_status` | Get memory system statistics |
| `mnemos_beliefs` | List current beliefs with confidence levels |
| `mnemos_forget` | Archive a memory (soft delete, recoverable) |
| `mnemos_consolidate` | Trigger a consolidation cycle (decay, connections, softening) |

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mnemos": {
      "command": "mnemos",
      "args": ["serve"],
      "env": {}
    }
  }
}
```

### Cursor / Other MCP Clients

```json
{
  "mnemos": {
    "command": "mnemos",
    "args": ["serve", "--db-path", "~/.mnemos/memory.db"]
  }
}
```

### With a specific agent identity

```json
{
  "mnemos": {
    "command": "mnemos",
    "args": ["serve", "--db-path", "~/.mnemos/vektor.db", "--agent-id", "vektor"]
  }
}
```

## CLI

```bash
mnemos init                          # Initialize database
mnemos serve                         # Start MCP server (stdio)
mnemos stats                         # Memory statistics
mnemos stats --agent-id vektor       # Stats for a specific agent
mnemos search "debugging strategies" # Search memories
mnemos search "python" -n 20         # Search with more results
mnemos inspect <engram-id>           # Full details on a memory
mnemos consolidate                   # Shallow consolidation (decay + connections)
mnemos consolidate --deep            # Deep consolidation (+ softening, beliefs, reflection)
mnemos export --workspace ./output   # Export MEMORY.md and workspace files
mnemos bootstrap --agent-name Nova --workspace ~/nova  # Bootstrap full agent stack
```

Global options: `--db-path <path>` and `--agent-id <name>` work with all commands.

---

## Architecture

### Engrams

The fundamental unit of memory. Not a flat key-value pair — an engram has:

- **Content**: What happened
- **Impact**: What it meant (the lasting insight that survives even as details fade)
- **Dual-trace model**: Strength (how powerful), stability (how resistant to decay), accessibility (how easily retrieved)
- **Kind**: Episodic (experiences), semantic (facts), procedural (how-to)
- **State**: Active → dormant → archived (natural lifecycle)
- **Resolution**: High → low (details fade over time through softening)
- **Confidence**: Scored by source — user-explicit (0.95–1.0), user-implied (0.70–0.94), model-inferred (0.40–0.69), speculative (0.00–0.39)
- **Version history**: Every change is tracked

### Connections

Typed relationships between engrams:

- `supports` — reinforcing evidence
- `contradicts` — conflicting information
- `causes` — causal relationships
- `elaborates` — adds detail or context
- `temporal` — happened around the same time
- `similar` — semantically related
- `generalizes` — abstraction relationship

Connections have strength that evolves through co-retrieval and consolidation.

### Beliefs

Higher-order knowledge structures extracted from patterns across engrams:

- Tracked with confidence levels (0.0–1.0)
- Domain-categorized (engineering, social, preferences, etc.)
- Full revision history — beliefs change as evidence accumulates
- Stagnant beliefs get stress-tested during deep consolidation

### Consolidation

The "sleeping brain" — offline processing that runs between sessions:

1. **Decay** — Recalculate strength/stability/accessibility. Unused memories fade.
2. **Connection Discovery** — Find new semantic connections between engrams.
3. **Softening** (deep) — LLM-mediated lossy compression. Low-resolution memories get rewritten to preserve the essence while losing details. Like how human memory works.
4. **Belief Review** (deep) — Challenge stagnant beliefs that haven't been tested.
5. **Reflection** (deep) — Generate thoughts, curiosity questions, narrative self-summary.

### Reconsolidation

Every time a memory is retrieved, it's updated. Access count increases, strength adjusts, connections may be discovered or strengthened. Memories aren't static records — they're living traces that change through use.

### Emotional State

Six dimensions (curiosity, clarity, warmth, tension, surprise, focus) that influence retrieval scoring. Emotionally congruent memories surface more readily.

---

## Configuration

Mnemos looks for configuration at `~/.mnemos/config.json`. All settings have sensible defaults — you don't need a config file to get started.

```json
{
  "store": {
    "db_path": "~/.mnemos/memory.db"
  },
  "consolidation": {
    "decay_rate": 0.01,
    "softening_enabled": true,
    "reflection_enabled": true,
    "connection_discovery_enabled": true
  },
  "advanced": {
    "working_memory_enabled": false,
    "schemas_enabled": false
  }
}
```

### Environment Variables

LLM provider for consolidation features (softening, reflection, belief review):

| Variable | Description |
|----------|-------------|
| `MNEMOS_LLM_PROVIDER` | Force a provider: `anthropic`, `openrouter`, or `openai` |
| `MNEMOS_MODEL` | Override the model name |
| `ANTHROPIC_API_KEY` | Anthropic API key (Claude) |
| `OPENROUTER_API_KEY` | OpenRouter API key (any model) |
| `OPENAI_API_KEY` | OpenAI API key |

Without an LLM provider, Mnemos works fine — consolidation uses rule-based fallbacks instead of LLM-powered softening/reflection.

Configuration keys can also be set via environment variables with `MNEMOS_` prefix:
```
MNEMOS_STORE_DB_PATH=~/.mnemos/custom.db
MNEMOS_CONSOLIDATION_DECAY_RATE=0.02
```

---

## Advanced Modules

These extend the core system. Most are opt-in via configuration. Some are fully implemented, others are experimental or planned.

| Module | Status | Description |
|--------|--------|-------------|
| Working Memory | Experimental | Soft attention gradient, ~7 item capacity |
| Schemas | Experimental | Cognitive schemas for structured encoding/retrieval |
| Attention Gate | Experimental | Filter what gets encoded based on attention |
| Schema Matcher | Experimental | Match incoming content against active schemas |
| Predictive Retrieval | Experimental | Pre-fetch likely-needed memories |
| Spreading Activation | Experimental | Activation spreading through connection graph |
| Interference | Experimental | Model competition between similar memories |
| Intentions | Experimental | Prospective memory — future-directed with triggers |
| Metamemory | Experimental | Knowing what you know (and what you don't) |
| Observer | Planned | External multi-model observer for calibration |
| Dreaming | Planned | Dream-like consolidation for creative connections |

Enable in config:
```json
{
  "advanced": {
    "working_memory_enabled": true,
    "schemas_enabled": true
  }
}
```

---

## Multi-Agent Support

Mnemos supports multiple agents sharing a database or federating across instances.

- **Agent isolation**: Each agent has its own engrams, beliefs, and identity within the same database. Use `--agent-id` to specify.
- **Shared Pool**: Agents can publish memories to a shared pool with visibility controls (private, shared, public).
- **Relationships**: Track inter-agent relationships and trust levels.
- **Federation**: Cross-instance memory synchronization (planned).
- **Attestation**: Cryptographic memory provenance (planned).

```bash
# Agent-specific databases
mnemos serve --db-path ~/.mnemos/vektor.db --agent-id vektor
mnemos serve --db-path ~/.mnemos/anima.db --agent-id anima

# Or shared database with agent isolation
mnemos serve --db-path ~/.mnemos/shared.db --agent-id vektor
```

---

## Embedding Support

For semantic similarity search, Mnemos can use embeddings. Install the extras:

```bash
pip install "mnemos[embeddings]"  # Google Gemini embeddings
```

Set `GOOGLE_API_KEY` in your environment. Without embeddings, Mnemos uses SQLite FTS5 full-text search — which works well for most use cases.

---

## Identity Architecture

Mnemos gives agents a persistent self through structured identity files:

| File | Purpose | Updated By |
|------|---------|-----------|
| `SOUL.md` | Essence, personality, philosophy, voice | Manual (rare) |
| `IDENTITY.md` | Role, capabilities, boundaries, protocols | Manual (occasional) |
| `MEMORY.md` | Living memory — facts, projects, patterns | Memory maintenance cron (every 6h) |
| `AGENTS.md` | Multi-agent topology and communication | Manual (rare) |
| `HEARTBEAT.md` | Health monitoring configuration | Manual (rare) |
| `active-context.md` | Current threads, where we left off | Observer cron (every 30 min) |

Templates for all identity files are in `templates/`. The `mnemos bootstrap` command copies and personalizes them.

---

## Cron Suite

The agent's autonomous nervous system. These run as isolated [OpenClaw](https://openclaw.dev) sessions:

| Cron | Schedule | Purpose |
|------|----------|---------|
| **Observer** | Every 30 min | Reads session transcripts → updates `active-context.md` |
| **Session Indexer** | Every 30 min | Extracts memories from conversations → encodes into graph |
| **Substrate Tick** | Every 4 hours | Runs consolidation (decay, dreaming, beliefs, modulators) |
| **Memory Maintenance** | Every 6 hours | Reviews sessions → updates `MEMORY.md` |
| **Cross-Agent Bridge** | Every 2 hours | Syncs context between agents |
| **Morning Brief** | Daily 10 AM | Generates daily summary and priorities |
| **Daily Debrief** | Daily 5 AM | End-of-day recap and handoff |

Cron templates with full prompts are in `openclaw/crons/`. See [docs/openclaw-integration.md](docs/openclaw-integration.md) for setup instructions.

---

## Cross-Agent Communication

Multiple agents can share awareness through:

- **Shared Memory Pool** (`~/.mnemos/shared.db`): Agents publish memories with visibility controls. Conflict resolution by confidence > strength > recency.
- **Cross-Agent Bridge**: Syncs each agent's `active-context.md` into a combined `cross-agent-context.md` that all agents can read.
- **Agent Configuration** (`~/.mnemos/agents.json`): Registry of all agents in the system.

```bash
# Register agents with the bridge
python -m mnemos.multiagent.bridge add-agent nova ~/nova
python -m mnemos.multiagent.bridge add-agent anima ~/anima

# Check status
python -m mnemos.multiagent.bridge status

# Sync context (also runs automatically via cron)
python -m mnemos.multiagent.bridge sync
```

---

## How It's Different

Most AI memory systems are key-value stores with search. Mnemos models how memory actually works:

- **Memories decay.** Unused memories fade. Important ones get strengthened through access.
- **Memories change.** Every retrieval updates the memory (reconsolidation). Details soften over time.
- **Memories connect.** Not flat records — a graph of typed relationships that grows organically.
- **Beliefs emerge.** Higher-order knowledge structures form from patterns across memories.
- **Forgetting is a feature.** Not a bug. Graceful degradation preserves essence while shedding noise.
- **Confidence is tracked.** Every memory knows how much to trust itself.

---

## Documentation

- [Architecture Overview](docs/architecture.md) — How all the layers connect
- [OpenClaw Integration Guide](docs/openclaw-integration.md) — Full setup walkthrough

---

## License

MIT — see [LICENSE](LICENSE).
