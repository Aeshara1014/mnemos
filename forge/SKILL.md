---
name: forge
description: "Create new OpenClaw agents OR dispatch coding agents to visible terminal sessions. Use when: (1) user asks to create/spin up/forge a new agent, (2) user asks to build/dispatch/delegate a coding task to an agent, (3) user says 'have an agent work on this', (4) user wants parallel coding agents on separate tasks. Triggers: 'create agent', 'new agent', 'spin up agent', 'forge agent', 'build this', 'dispatch', 'send an agent', 'have an agent work on', 'use codex for this'."
---

# Forge

Two capabilities in one skill: **Create** new OpenClaw agents, or **Dispatch** coding agents to visible terminal panes.

---

## Decision Tree

When the user's request comes in, determine which mode:

```
Is the user asking to create/spin up a new persistent agent?
  YES → CREATE mode (forge.py)
  NO  →
    Is the user asking to build/code/fix something that should be delegated?
    Or explicitly saying "dispatch", "send an agent", "have an agent work on"?
      YES → DISPATCH mode (forge-pane.sh)
      NO  → Handle normally (not a Forge task)
```

**Signals for CREATE:**
- "create agent", "new agent", "spin up agent", "forge agent", "bootstrap agent"
- "clone agent", "make an agent like X"
- Discussing agent names, models, personalities, Telegram bindings

**Signals for DISPATCH:**
- "build this", "have an agent work on this", "dispatch", "send an agent to"
- Any coding task the main agent should delegate rather than do inline
- "use codex/claude for this" (agent override)
- "do these in parallel" (multi-dispatch)

---

## CREATE — New OpenClaw Agent

Creates a fully operational OpenClaw agent with workspace, identity files, config registration, auth profiles, and model routing.

### Parameters

Gather these from the user (ask only what's missing):

| Parameter | Required | Default | Notes |
|-----------|----------|---------|-------|
| `name` | yes | — | Lowercase, becomes agent ID |
| `primary_model` | yes | — | Format: `provider/model` (e.g., `openai/gpt-5.4`) |
| `fallback_models` | no | `[]` | Comma-separated fallback chain |
| `personality` | no | minimal template | Path to custom SOUL.md |
| `telegram_bot_token` | no | skip binding | For Telegram integration |
| `clone_from` | no | fresh agent | Clone identity from existing workspace |

### Execution

```bash
python3 scripts/forge.py \
  --name <agent-name> \
  --model <primary-model> \
  [--fallbacks <model1>,<model2>] \
  [--clone-from <existing-workspace-path>] \
  [--personality <path-to-soul.md>] \
  [--telegram-token <bot-token>] \
  [--openrouter-key <key>] \
  [--force]
```

The script path is relative to this skill's install directory. Use the full path based on where the skill is installed.

### What It Creates

1. Workspace at `~/clawd-<name>/` with identity files (SOUL.md, IDENTITY.md, MEMORY.md, USER.md, AGENTS.md, TOOLS.md, HEARTBEAT.md)
2. `.env` with API keys (auto-detected from environment)
3. `~/.openclaw/agents/<name>/agent/` with `auth-profiles.json` and `models.json`
4. Updates `~/.openclaw/openclaw.json` to register the agent
5. Optionally adds Telegram binding

### Post-Create

After forging, tell the user:
- Gateway restart needed: `openclaw gateway restart`
- If Telegram token provided: send `/start` to the bot
- The agent is reachable via Telegram or webchat

### Model Format

All models use `provider/model-name` format. Examples:
- `openai/gpt-5.4`
- `anthropic/claude-opus-4-6`
- `deepseek/deepseek-r1`
- `google/gemini-2.5-pro`

Non-Anthropic models auto-route through OpenRouter.

---

## DISPATCH — Send Coding Agents to Terminal Panes

Spawns coding agents in visible tmux terminal panes so the user can watch them work in real-time.

### How It Works

1. **Detect** the best available coding agent (or use the user's override)
2. **Create** a tmux pane with a descriptive name
3. **Open** Terminal.app so the user sees it live
4. **Run** the agent with the given prompt
5. **Wait** after completion so the user can read the output

Multiple dispatches tile automatically in the same tmux window.

### Agent Detection

Run `scripts/forge-detect.sh --best` to find the recommended agent. Priority order:

1. `claude` (Claude Code CLI)
2. `codex` (OpenAI Codex CLI)
3. `aider` (Aider)
4. `opencode` (OpenCode)

The user can override with "use codex for this" or the `--agent` flag.

To see all installed agents: `scripts/forge-detect.sh`

### Single Dispatch

```bash
scripts/forge-pane.sh "<pane-name>" "<prompt>" [--agent <name>] [--cwd <path>]
```

Example — the user says "have an agent add auth to the API":

```bash
scripts/forge-pane.sh "add-auth" "Add JWT authentication middleware to the Express API in src/api/" --cwd /path/to/project
```

### Parallel Dispatch

When the user wants multiple tasks done at once, dispatch multiple panes:

```bash
scripts/forge-pane.sh "backend-auth" "Add JWT auth to the API" --cwd /path/to/project
scripts/forge-pane.sh "frontend-login" "Build a login page component" --cwd /path/to/project
scripts/forge-pane.sh "test-suite" "Write integration tests for the auth flow" --cwd /path/to/project
```

All three appear as tiled panes in one Terminal window.

### Agent Override

The user can specify which agent to use:

- "use codex for this" → `--agent codex`
- "dispatch with aider" → `--agent aider`
- "have claude work on the backend" → `--agent claude`

### Pane Management

```bash
scripts/forge-pane.sh list              # Show active panes
scripts/forge-pane.sh kill <pane-name>  # Kill specific pane
scripts/forge-pane.sh kill-all          # Kill entire session
```

### Headless Mode

For background tasks that don't need a visible window:

```bash
scripts/forge-pane.sh "<name>" "<prompt>" --no-window
```

### Crafting Good Prompts

When dispatching, write clear, self-contained prompts. The dispatched agent has no context from the current conversation. Include:

- **What** to build/fix/change
- **Where** the relevant code lives (file paths)
- **How** it should work (acceptance criteria)
- **Constraints** (don't change X, use Y library, etc.)

Bad: "fix the bug"
Good: "Fix the TypeError in src/api/auth.ts:45 where req.body is undefined. The body-parser middleware runs in app.ts but the auth route mounts before it. Reorder the middleware chain so body-parser runs first."

---

## Examples

### Create a new agent
**User:** "Forge a new agent called scout on deepseek/deepseek-r1"

```bash
python3 scripts/forge.py --name scout --model deepseek/deepseek-r1
```

### Create with fallbacks and Telegram
**User:** "Create an agent called oracle on gpt-5.4 with gemini-2.5-pro fallback, and hook it up to this Telegram bot: 123456:ABC"

```bash
python3 scripts/forge.py \
  --name oracle \
  --model openai/gpt-5.4 \
  --fallbacks google/gemini-2.5-pro \
  --telegram-token "123456:ABC"
```

### Clone an existing agent
**User:** "Clone an agent onto a different model"

```bash
python3 scripts/forge.py \
  --name scout-experimental \
  --model deepseek/deepseek-r1 \
  --clone-from ~/clawd-scout
```

### Dispatch a single task
**User:** "Have an agent add dark mode to the settings page"

```bash
scripts/forge-pane.sh "dark-mode" \
  "Add dark mode toggle to src/components/Settings.tsx. Store preference in localStorage. Use the existing Tailwind dark: classes." \
  --cwd /path/to/project
```

### Dispatch with agent override
**User:** "Use codex to refactor the database layer"

```bash
scripts/forge-pane.sh "db-refactor" \
  "Refactor src/db/ to use Drizzle ORM instead of raw SQL queries. Migrate all existing queries." \
  --agent codex --cwd /path/to/project
```

### Parallel dispatch
**User:** "Split this into three parallel tasks: API, frontend, and tests"

```bash
scripts/forge-pane.sh "api" "Build REST endpoints for /users CRUD in src/api/users.ts" --cwd /project
scripts/forge-pane.sh "frontend" "Build the user management UI in src/pages/Users.tsx" --cwd /project
scripts/forge-pane.sh "tests" "Write tests for the users API in tests/users.test.ts" --cwd /project
```

---

## Architecture Reference

See `references/agent-anatomy.md` for the full file/directory structure of an OpenClaw agent.
