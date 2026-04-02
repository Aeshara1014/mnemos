# Mnemos

**Living Memory Architecture for Autonomous AI Agents**

Memory is not a feature of the agent. Memory *is* the agent.

Mnemos replaces passive note-storage with active, living memory that encodes at varying depths, forgets naturally, predicts what it'll need, and changes its memories every time it touches them.

Built as an [MCP](https://modelcontextprotocol.io/) server with 7 tools. SQLite-backed. No external services required — optional LLM integration for richer consolidation.

---

## Quick Start

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

## How It's Different

Most AI memory systems are key-value stores with search. Mnemos models how memory actually works:

- **Memories decay.** Unused memories fade. Important ones get strengthened through access.
- **Memories change.** Every retrieval updates the memory (reconsolidation). Details soften over time.
- **Memories connect.** Not flat records — a graph of typed relationships that grows organically.
- **Beliefs emerge.** Higher-order knowledge structures form from patterns across memories.
- **Forgetting is a feature.** Not a bug. Graceful degradation preserves essence while shedding noise.
- **Confidence is tracked.** Every memory knows how much to trust itself.

---

## License

MIT — see [LICENSE](LICENSE).
