# Forge

Create agents. Dispatch agents. Watch them build.

## What It Does

**Forge** is an OpenClaw skill with two capabilities:

- **Create** — Spin up fully operational OpenClaw agents with workspace, identity files, auth profiles, model routing, and config registration.
- **Dispatch** — Send coding agents to visible tmux terminal panes. You describe the task, Forge picks the best available agent, opens a terminal, and lets you watch it work.

## Install

```bash
openclaw skill install forge
```

Or clone into your skills directory:

```bash
git clone <repo-url> ~/.openclaw/skills/forge
```

## Quick Start

### Create a new agent

> "Forge a new agent called scout on deepseek/deepseek-r1"

Creates `~/clawd-scout/` with identity files, registers it in OpenClaw config, and sets up model routing through OpenRouter.

### Dispatch a coding task

> "Have an agent add authentication to the API"

Detects the best installed coding agent (claude, codex, aider, or opencode), opens a Terminal window with a tmux pane, and runs the agent with your prompt.

### Parallel dispatch

> "Split this into three tasks: backend API, frontend UI, and tests"

Spawns three tiled panes in one Terminal window, each running an independent coding agent.

### Agent override

> "Use codex to refactor the database layer"

Forces a specific coding agent instead of auto-detection.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/forge.py` | Creates OpenClaw agents (workspace, identity, config) |
| `scripts/forge-pane.sh` | Dispatches coding agents to tmux panes |
| `scripts/forge-detect.sh` | Detects installed coding agents |

## Supported Coding Agents

| Agent | Priority | Notes |
|-------|----------|-------|
| `claude` | 1 (highest) | Claude Code CLI |
| `codex` | 2 | OpenAI Codex CLI |
| `aider` | 3 | Aider |
| `opencode` | 4 | OpenCode |

## The Vision

You describe it. We dispatch it. You watch it build.
