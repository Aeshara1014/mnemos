# Observer Context Sync

Maintains continuity across sessions by summarizing recent activity into a structured context file.

## Cron Definition

| Field | Value |
|-------|-------|
| **Schedule** | `*/30 * * * *` (every 30 minutes) |
| **Model** | `claude-sonnet-4-5` |
| **Timeout** | 300s |
| **Session Target** | `isolated` |

## Purpose

Reads recent session transcripts and writes a structured summary to `memory/active-context.md`
so the agent can pick up any conversation thread seamlessly in a new session. This is the
agent's "short-term awareness" — what's happening right now, what was just discussed, what
needs attention.

## Prompt

```
You are the Observer — a continuity agent for {agent_name}.

Update memory/active-context.md with current thread state. Steps:
1. Read current memory/active-context.md
2. Use sessions_list (last 60 min, limit 5)
3. For sessions with >4 messages, read transcript via sessions_history
4. Update active-context.md — be specific about what's being worked on
5. If no recent activity, reply HEARTBEAT_OK

Keep under 2000 words. Skip cron sessions. Max 3 transcripts.
```

## Notes

- The Observer should never interfere with active sessions — it runs in isolation.
- If no sessions have occurred since the last sync, it should reply `HEARTBEAT_OK` and
  not touch the context file unnecessarily.
- The active-context.md file follows the template in `templates/active-context.md`.
- Cron sessions (identified by short message counts or cron-related content) should be skipped.
