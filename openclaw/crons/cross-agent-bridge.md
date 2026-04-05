# Cross-Agent Bridge

Syncs shared context between agents by running the cross-agent bridge script.

## Cron Definition

| Field | Value |
|-------|-------|
| **Schedule** | `45 */2 * * *` (every 2 hours at :45) |
| **Model** | `claude-sonnet-4-5` |
| **Timeout** | 120s |
| **Session Target** | `isolated` |

## Purpose

Synchronizes context across multiple agents in the system. Each agent maintains its own
`active-context.md` — this bridge reads all agents' context files and writes a shared
summary so every agent knows what the others are working on.

This enables:
- Agents avoiding duplicate work
- Agents picking up context from other agents' conversations
- Shared awareness of system-wide activity
- Cross-agent memory publication via the shared pool

## Prompt

```
Run the cross-agent bridge sync:
python3 -m mnemos.multiagent.shared_pool sync
Then report what changed. HEARTBEAT_OK if nothing changed.
```

## Notes

- The bridge reads from each agent's `memory/active-context.md` and writes to a
  shared directory (default: `~/.mnemos/shared/`).
- Each agent's context is summarized into a `{agent_name}-summary.md` in the shared dir.
- A combined `cross-agent-context.md` is generated with all agents' current status.
- The bridge also syncs any memories published to the shared pool since the last run.
- If only one agent is configured, the bridge still runs but does minimal work.
