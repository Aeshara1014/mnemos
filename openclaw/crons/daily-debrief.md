# Daily Debrief

End-of-day summary — what got done, key decisions, open threads, cross-agent activity.

## Cron Definition

| Field | Value |
|-------|-------|
| **Schedule** | `0 5 * * *` (daily at 5 AM — configurable for night owls) |
| **Model** | default agent model |
| **Timeout** | 300s |
| **Session Target** | `isolated` |

## Purpose

Generates an end-of-day summary that captures the day's work before the next day begins.
This serves as both a record and a handoff — if the agent starts fresh tomorrow, the debrief
plus the morning brief provide complete continuity.

## Prompt

```
You are {agent_name}'s daily debrief system.

Generate an end-of-day debrief for {user_name}. Follow this format exactly:

---
# Daily Debrief — {date}

## What Got Done
- [Completed work items with brief descriptions]
- [Include both user-initiated and autonomous work]

## Key Decisions
- [Decision]: [Rationale and outcome]
- [These are important for future reference]

## Open Threads
- [Work in progress — what state it's in]
- [Waiting on external input]
- [Planned but not started]

## Problems & Blockers
- [Issues encountered and current status]
- [Workarounds applied]

## Cross-Agent Activity
- [What other agents worked on today]
- [Any cross-agent coordination that happened]

## Memories Created Today
- [Count and summary of what was learned]
- [Any significant belief changes]

## Tomorrow's Candidates
- [Suggested items for tomorrow based on today's work]
---

STEPS:
1. Read {workspace}/memory/active-context.md for current state
2. Use sessions_list to review today's sessions (last 24h)
3. For significant sessions (>4 messages), read transcripts
4. Check {workspace}/memory/cross-agent-context.md if it exists
5. Run mnemos stats for memory health
6. Generate the debrief in the format above
7. Write to {workspace}/daily/debrief-{date}.md
```

## Notes

- The 5 AM schedule works for night owls — adjust in your openclaw config if needed.
- The debrief is more detailed than the morning brief since it covers the full day.
- "Key Decisions" is the most archivally important section — these compound over time.
- The "Tomorrow's Candidates" section feeds into the next morning brief's suggested focus.
- Written to `daily/` for archival alongside morning briefs.
