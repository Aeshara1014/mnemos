# Agents — Multi-Agent Configuration

<!--
AGENTS.md defines the multi-agent setup for your system. If you're running a single
agent, you can skip most of this — but the Observer section is still useful.

This file is read by the bootstrap script and by agents themselves to understand
the system topology.

Replace {placeholders} with actual values.
-->

## Primary Agent

<!--
The main agent that handles most user interactions.
-->

| Field | Value |
|-------|-------|
| **Name** | {agent_name} |
| **Agent ID** | {agent_id} |
| **Database** | `{db_path}` |
| **Workspace** | `{workspace}` |
| **Model** | {model} |
| **Role** | Primary assistant |

## Specialist Agents

<!--
Additional agents with specific roles. Each gets its own database,
identity files, and cron suite.

Example specialists:
- Code reviewer agent
- Research agent
- Creative writing agent
- DevOps agent
-->

_No specialist agents configured._

<!--
### Example: Research Agent

| Field | Value |
|-------|-------|
| **Name** | researcher |
| **Agent ID** | researcher |
| **Database** | `~/.mnemos/researcher.db` |
| **Workspace** | `~/researcher` |
| **Model** | claude-sonnet-4-5 |
| **Role** | Deep research and analysis |
-->

## Communication Protocol

<!--
How agents communicate with each other. The primary mechanism is the
shared memory pool (mnemos.multiagent.shared_pool) and the cross-agent
bridge (mnemos.multiagent.bridge).
-->

### Shared Memory Pool
- Location: `~/.mnemos/shared.db`
- Agents publish memories with `shared` or `public` visibility
- All agents can read the shared pool
- Conflict resolution: confidence > strength > recency

### Cross-Agent Context
- Location: `~/.mnemos/shared/`
- Each agent's `active-context.md` is synced here
- Combined view in `cross-agent-context.md`
- Synced every 2 hours by the cross-agent bridge cron

### Direct Messaging
- Agents can leave messages for each other via shared memory pool
- Tag messages with `cross-agent-message` and `to:{agent_name}`
- The receiving agent will pick these up during context sync

## Escalation Chain

<!--
When an agent encounters something beyond its capabilities, where does it go?
Define the escalation path.
-->

1. Agent attempts to handle the task independently
2. If blocked, checks shared context for help from other agents
3. If still blocked, publishes a memory with tag `needs-help` to shared pool
4. If urgent, flags for user attention in the next morning brief

## Observer

<!--
The Observer is a lightweight process that maintains continuity. It's not a
full agent — it runs as an isolated cron session with a single purpose:
keep active-context.md current.

Every agent should have an Observer configured via the observer-context-sync cron.
-->

### Observer Spawn Template

```json
{
  "name": "observer-{agent_name}",
  "schedule": "*/30 * * * *",
  "model": "claude-sonnet-4-5",
  "timeout": 300,
  "sessionTarget": "isolated",
  "purpose": "Maintain active-context.md for {agent_name}"
}
```

### What the Observer Does
1. Reads recent session transcripts (last 60 minutes)
2. Updates `memory/active-context.md` with current thread state
3. Skips its own cron sessions to avoid loops
4. Reports `HEARTBEAT_OK` if nothing to update

### What the Observer Does NOT Do
- Encode new memories (that's the session indexer's job)
- Make decisions or take actions
- Interact with the user
- Modify any file except `active-context.md`
