# Memory — {agent_name}

<!--
MEMORY.md is the living memory document. It gets updated automatically by the
memory-maintenance cron (every 6 hours) and can also be updated manually.

This file is loaded into the agent's context at the start of every session,
so keep it concise and current. Stale information is worse than no information.

Max recommended length: ~200 lines (beyond that, move details to topic files
in the memory/ directory and link to them from here).

Replace {placeholders} with actual values during bootstrap.
-->

## Origin

<!--
When and why this agent was created. This is the agent's "birth story."
Written once during bootstrap and rarely updated.
-->

Created: {date}
Purpose: ...

## Core Truths

<!--
Facts that are always true and rarely change. Things like the user's name,
the agent's primary function, key technical constraints.
Updated only when something fundamental changes.
-->

- {user_name} is my primary user
- My workspace is at `{workspace}`
- ...

## Key Relationships

<!--
Important people, agents, and systems this agent interacts with.
Include how to interact with each.
-->

### People
- **{user_name}** — ...

### Agents
<!-- Other agents in the system, if multi-agent setup -->

### Systems
<!-- External systems, APIs, services the agent interacts with -->

## Active Projects

<!--
Current work streams. Updated frequently by memory-maintenance cron.
Each project should have: name, status, last activity, key context.
-->

_No active projects yet._

## Significant Moments

<!--
Important events in the agent's history. Decisions, breakthroughs,
failures, changes in direction. These form the agent's narrative memory.
Kept brief — 1-2 lines each.
-->

- {date}: Created and initialized

## Patterns Noticed

<!--
Recurring patterns the agent has observed — about the user, about the work,
about itself. These are proto-beliefs that may become formal Mnemos beliefs
over time.
-->

_No patterns yet._

## Evolution Markers

<!--
How the agent has changed over time. What it used to do vs. what it does now.
Helps maintain a sense of growth and development.
-->

_Just getting started._

## Working Memory

<!--
Short-term items that need to persist across sessions but aren't permanent.
This section gets cleaned up regularly by memory-maintenance.
Think of it as a scratchpad.
-->

_Empty._

## Session Log

<!--
Brief log of recent sessions. Automatically maintained.
Format: date | duration | summary
Keep last ~10 sessions.
-->

| Date | Summary |
|------|---------|
| {date} | Initial setup and bootstrap |
