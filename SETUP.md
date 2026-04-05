# Mnemos Setup

Get the full Mnemos stack running for your OpenClaw agent — persistent memory, inner life, cross-agent awareness, and Forge orchestration.

---

## Prerequisites

- **OpenClaw** installed and running ([openclaw.ai](https://openclaw.ai))
- **Python 3.10+**
- **Git**
- An **OpenRouter API key** (or Anthropic API key)

---

## Option A: One-Command Bootstrap

The fastest way. Run from the repo root:

```bash
python3 mnemos/setup/bootstrap.py \
  --agent-name "Nova" \
  --workspace ~/nova \
  --user-name "YourName" \
  --api-key "your-openrouter-key"
```

### What this does (in order)

1. Creates the agent workspace directory (`~/nova/`)
2. Initializes the Mnemos SQLite database at `~/.mnemos/nova.db`
3. Copies and personalizes all identity templates (SOUL.md, IDENTITY.md, MEMORY.md, AGENTS.md, HEARTBEAT.md)
4. Creates `~/shared/` with the cross-agent context pool
5. Installs `mnemos_bridge.py` into `<workspace>/inner_life/`
6. Installs `mnemos_indexer.py` into `<workspace>/inner_life/`
7. Registers all 7 crons in your OpenClaw config
8. Installs the Forge skill into OpenClaw
9. Creates a `.env` file in the workspace
10. Prints confirmation and next steps

### Bootstrap arguments

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--agent-name` | yes | — | Human-readable name (e.g. "Nova") |
| `--workspace` | yes | — | Path to workspace directory |
| `--user-name` | yes | — | Your name |
| `--api-key` | yes | — | OpenRouter or Anthropic API key |
| `--model` | no | `openrouter/anthropic/claude-sonnet-4-5` | Default LLM model |
| `--openclaw-config` | no | `~/.openclaw/openclaw.json` | Path to OpenClaw config |
| `--timezone` | no | `America/New_York` | Timezone for cron scheduling |

After bootstrap completes, skip to [After Setup](#after-setup).

---

## Option B: Manual Step-by-Step

If you prefer to set things up yourself, follow each step below. Replace `Nova` with your agent name and `~/nova` with your workspace path throughout.

### Step 1 — Create the workspace

```bash
mkdir -p ~/nova/memory ~/nova/daily ~/nova/inner_life
```

### Step 2 — Initialize the Mnemos database

```bash
mkdir -p ~/.mnemos
python3 -c "
from mnemos.store.sqlite_store import EngramStore
store = EngramStore(str(Path('~/.mnemos/nova.db').expanduser()))
store.close()
print('Database initialized.')
" 
```

Or using the CLI (if installed):

```bash
pip install -e .
mnemos init --agent-id nova --db-path ~/.mnemos/nova.db
```

### Step 3 — Copy and personalize identity templates

Copy each template from `templates/` into your workspace:

```bash
cp templates/SOUL.md       ~/nova/SOUL.md
cp templates/IDENTITY.md   ~/nova/IDENTITY.md
cp templates/MEMORY.md     ~/nova/MEMORY.md
cp templates/AGENTS.md     ~/nova/AGENTS.md
cp templates/HEARTBEAT.md  ~/nova/HEARTBEAT.md
cp templates/active-context.md ~/nova/memory/active-context.md
```

Then open each file and replace the placeholders:

| Placeholder | Replace with |
|-------------|-------------|
| `{agent_name}` | Your agent's name (e.g. `Nova`) |
| `{user_name}` | Your name (e.g. `Riley`) |
| `{workspace}` | Full workspace path (e.g. `/Users/you/nova`) |
| `{date}` | Today's date (e.g. `2026-04-05`) |
| `{agent_id}` | Lowercase agent name (e.g. `nova`) |

### Step 4 — Create the shared context pool

The `~/shared/` directory enables cross-agent awareness. All agents read from and write to this pool.

```bash
mkdir -p ~/shared/memory
```

Create `~/shared/active-threads.json`:

```json
{}
```

Create `~/shared/decisions.md`:

```markdown
# Cross-Agent Decisions

Decisions that affect multiple agents. Append new entries with date and reasoning.
```

Create `~/shared/project-state.md`:

```markdown
# Project State

High-level status of active projects. Updated by any agent when state changes.
```

### Step 5 — Install the bridge and indexer

Copy the runtime scripts into your workspace:

```bash
cp mnemos/setup/assets/mnemos_bridge.py  ~/nova/inner_life/mnemos_bridge.py
cp mnemos/setup/assets/mnemos_indexer.py ~/nova/inner_life/mnemos_indexer.py
```

These are the scripts your agent and crons call at runtime. They read configuration from the `.env` file.

### Step 6 — Create the .env file

Create `~/nova/.env`:

```bash
# Mnemos Agent Configuration

# ── Agent Identity ──
MNEMOS_AGENT_ID=nova
MNEMOS_AGENT_NAME=Nova

# ── Paths ──
MNEMOS_DB_PATH=~/.mnemos/nova.db
MNEMOS_WORKSPACE=~/nova

# ── LLM Provider (uncomment one) ──
MNEMOS_LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your-key-here
MNEMOS_MODEL=openrouter/anthropic/claude-sonnet-4-5

# MNEMOS_LLM_PROVIDER=anthropic
# ANTHROPIC_API_KEY=your-key-here

# ── Indexer ──
INDEXER_WINDOW_HOURS=6
INDEXER_CHUNK_SIZE=12000
INDEXER_AGENT_ID=main
```

Replace `your-key-here` with your actual API key.

### Step 7 — Register crons in OpenClaw

Open your OpenClaw config (usually `~/.openclaw/openclaw.json`) and add the following 7 jobs to the `cron.jobs` array. Generate a unique UUID for each job's `id` field.

> **Important:** Read your existing `openclaw.json` first and match the exact field format of any existing cron entries.

| Cron | Schedule | Timeout | Description |
|------|----------|---------|-------------|
| `observer-context-sync` | `*/30 * * * *` | 300s | Summarizes recent sessions into active-context.md |
| `session-indexer` | `*/30 * * * *` | 300s | Extracts memories from conversation transcripts |
| `substrate-tick` | `0 */4 * * *` | 600s | Runs cognitive substrate — decay, connections, beliefs |
| `memory-maintenance` | `0 */6 * * *` | 300s | Reviews and updates MEMORY.md |
| `cross-agent-bridge` | `*/15 * * * *` | 180s | Syncs shared context between agents |
| `morning-brief` | `0 8 * * *` | 300s | Prepares daily morning summary |
| `daily-debrief` | `0 22 * * *` | 300s | End-of-day recap and open threads |

Each entry should look like:

```json
{
  "id": "your-generated-uuid",
  "name": "observer-context-sync",
  "description": "Maintains continuity across sessions",
  "schedule": "*/30 * * * *",
  "model": "openrouter/anthropic/claude-sonnet-4-5",
  "agentId": "main",
  "prompt": "... (copy from openclaw/crons/observer-context-sync.md)",
  "enabled": true,
  "timeout": 300
}
```

The full prompts for each cron are in `openclaw/crons/`. Copy the prompt section from each template file.

### Step 8 — Install the Forge skill

Copy the `forge/` directory into your OpenClaw skills path:

```bash
# Check your skills path in ~/.openclaw/openclaw.json first
cp -r forge/ ~/.agents/skills/forge/
```

This gives your agent the ability to create new agents and dispatch coding tasks to visible terminal panes.

---

## After Setup

1. **Configure your agent** in OpenClaw to use the workspace directory you created
2. **Restart OpenClaw gateway:**
   ```bash
   openclaw gateway restart
   ```
3. **Start a conversation** with your agent — they now have the full Mnemos stack

### Verify it's working

```bash
# Check the database exists
ls -la ~/.mnemos/nova.db

# Check identity files are in place
ls ~/nova/SOUL.md ~/nova/IDENTITY.md

# Test the bridge
python3 ~/nova/inner_life/mnemos_bridge.py status

# Check crons are registered
openclaw cron list
```

---

## Troubleshooting

**Database init fails:**
Make sure `~/.mnemos/` exists and you have write permissions. Run `mkdir -p ~/.mnemos` and try again.

**Templates have unresolved placeholders:**
Open each `.md` file in your workspace and search for `{` — replace any remaining `{placeholder}` values manually.

**Crons not running:**
Check that `openclaw.json` is valid JSON (a trailing comma will break it). Run `openclaw cron list` to verify registration. Ensure `enabled` is `true` for each job.

**Bridge can't find the database:**
Make sure your `.env` file has the correct `MNEMOS_DB_PATH` and that the path uses `~` or the full absolute path.

**Forge skill not appearing:**
Verify the skills directory path matches what's configured in `openclaw.json`. Restart the gateway after copying.

---

## What You Get

After setup, your agent has:

- **Persistent identity** — SOUL.md and IDENTITY.md define who they are across every session
- **Living memory** — a graph where memories connect, beliefs emerge, and experiences decay naturally
- **Cognitive substrate** — a tick function that runs every 4 hours, changing the agent between conversations
- **Session continuity** — active-context.md is updated every 30 minutes so threads never get lost
- **Cross-agent awareness** — `~/shared/` lets agents see each other's work and share decisions
- **Forge** — create new agents and dispatch coding tasks to visible terminal sessions

---

## Directory Reference

After setup, your workspace looks like this:

```
~/nova/                        Your agent's workspace
  SOUL.md                      Core identity and values
  IDENTITY.md                  Role, relationships, capabilities
  MEMORY.md                    Persistent memory index
  AGENTS.md                    Known agents and relationships
  HEARTBEAT.md                 Substrate state and inner life
  .env                         Configuration and API keys
  memory/
    active-context.md          Current conversation threads (auto-updated)
  daily/                       Daily briefs and debriefs
  inner_life/
    mnemos_bridge.py           Runtime memory interface
    mnemos_indexer.py           Session transcript indexer

~/.mnemos/
  nova.db                      SQLite memory graph database

~/shared/                      Cross-agent context pool
  active-threads.json          What each agent is working on
  decisions.md                 Cross-cutting decisions
  project-state.md             High-level project status
  memory/                      Shared persistent knowledge
```
