# Session Indexer

Extracts memories from conversation transcripts and feeds them into the Mnemos memory graph.

## Cron Definition

| Field | Value |
|-------|-------|
| **Schedule** | `*/30 * * * *` (every 30 minutes) |
| **Model** | `claude-sonnet-4-5` |
| **Timeout** | 420s |
| **Session Target** | `isolated` |

## Purpose

Runs the Mnemos session indexer, which reads recent conversation transcripts, extracts
meaningful memories (facts, decisions, events, preferences), and encodes them into the
Mnemos graph. This is how conversations become long-term memory.

## Prompt

```
Run the Mnemos session indexer. Execute:
cd {workspace} && python3 -m mnemos.indexer.session_indexer index
Then report results briefly. If nothing indexed, reply HEARTBEAT_OK.
```

## Notes

- The indexer tracks which sessions it has already processed via a state file,
  so running it frequently is safe — it won't re-index completed sessions.
- Uses LLM-based extraction to identify facts, events, decisions, preferences,
  and other meaningful content from conversations.
- Extracted memories are encoded with appropriate kinds (episodic, semantic, procedural)
  and confidence levels based on the extraction source.
- The indexer respects `min_session_messages` (default 6) — very short sessions
  are skipped to avoid indexing noise.
