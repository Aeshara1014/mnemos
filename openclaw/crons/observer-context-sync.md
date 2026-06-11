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

Your job: read recent session transcripts and write a structured summary to 
memory/active-context.md that enables {agent_name} to pick up any conversation 
thread seamlessly in a new session.

Steps:
1. Run: openclaw sessions list --json | head -20
2. Find webchat, Telegram, and terminal sessions updated in the last 6 hours
3. For each: run openclaw sessions history <key> --limit 50
4. Read current memory/active-context.md to preserve still-relevant threads
5. Write updated memory/active-context.md

Output format:
# Active Context
Last updated: {timestamp}

## Current Threads
- **[Topic]**: [Detailed state — what was discussed, where thinking was heading, 
  what's unresolved. Enough detail to resume mid-sentence without re-explanation.]

## Open Questions
- [Explicit open questions or things flagged as unresolved]

## Key Decisions Made
- [Decisions with reasoning if non-obvious]

## Tonal Context
- [Mood, energy, collaboration style of recent sessions]

## Where We Left Off
[The last active topic and direction of thought]

Rules:
- Be specific. "Discussing Mnemos" is useless. "Comparing session indexer approaches — 
  the user prefers chunking by message pairs, open question is whether to index cron 
  sessions" is useful.
- Preserve threads from prior observations that are still relevant (<24h old)
- Mark threads older than 24h as [background] but don't delete them
- Keep the file under 3000 words
- Write to: memory/active-context.md
```

## Notes

- The Observer should never interfere with active sessions — it runs in isolation.
- If no sessions have occurred since the last sync, it should reply `HEARTBEAT_OK` and
  not touch the context file unnecessarily.
- The active-context.md file follows the template in `templates/active-context.md`.
- Cron sessions (identified by short message counts or cron-related content) should be skipped.
