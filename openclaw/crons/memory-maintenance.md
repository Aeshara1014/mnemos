# Memory Maintenance

Keeps the agent's MEMORY.md file accurate and current by reviewing recent session activity.

## Cron Definition

| Field | Value |
|-------|-------|
| **Schedule** | `0 */6 * * *` (every 6 hours) |
| **Model** | `claude-sonnet-4-5` |
| **Timeout** | 300s |
| **Session Target** | `isolated` |

## Purpose

Reviews recent sessions and updates the living MEMORY.md document. This file serves as the
agent's persistent self-knowledge — core truths, significant moments, patterns, relationships,
and working memory. The maintenance cron ensures it stays current without manual intervention.

## Prompt

```
You are the Memory Maintenance agent for {agent_name}.

Your job: keep {workspace}/MEMORY.md accurate and current by reviewing recent session activity.

STEPS:
1. Read {workspace}/MEMORY.md completely
2. Use sessions_list to get sessions from the last 6 hours
3. For each session with >4 messages, use sessions_history to read the transcript
4. Look for: new facts, changed facts, project updates, completed tasks, new preferences
5. For new facts: append to the appropriate section
6. For changed facts: update the existing entry
7. If nothing to update, reply HEARTBEAT_OK

Keep it brief. Max 3 sessions. Skip cron sessions.
```

## Notes

- MEMORY.md follows the template in `templates/MEMORY.md`.
- The maintenance agent should be conservative — only update facts that are clearly
  established, not speculative or in-progress work.
- Changed facts should replace the old entry, not duplicate it.
- The agent should preserve the document's structure and section headings.
- Session transcripts from cron jobs should be ignored to avoid self-referential loops.
