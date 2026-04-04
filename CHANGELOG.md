# Changelog

## 0.1.0 (2026-04-05)

Initial release.

### Core Memory Engine
- Engram model with dual-trace (strength/stability/accessibility)
- 7 typed connections (supports, contradicts, causes, extends, parallels, synthesizes, grounds)
- Beliefs with confidence tracking, revision history, epistemic bounds [0.05, 0.95]
- 6-dimensional emotional state (curiosity, clarity, warmth, tension, surprise, focus)
- Graph-based identity computation
- SQLite backend with FTS5 full-text search and WAL mode

### MCP Server (9 tools)
- mnemos_setup — 10-step conversational onboarding wizard
- mnemos_remember — encode memories with impact, confidence, connection discovery
- mnemos_recall — spreading activation retrieval with emotional biasing
- mnemos_inspect — full engram details with version history
- mnemos_status — system health and statistics
- mnemos_beliefs — list beliefs with confidence and revision count
- mnemos_shared — query shared memory pool
- mnemos_forget — graceful archiving (soft delete)
- mnemos_consolidate — trigger decay, connection discovery, softening, belief review, reflection

### Cognitive Substrate
- Background tick loop (configurable interval, default 4h)
- 6 handlers: dreaming, wandering, surprise, reflection, insight, initiation
- Cognitive modulators (arousal, resolution, openness, selection_threshold, social_drive)
- Production guardrails: skip_surprise_detection on all handler outputs except surprise, per-handler throttles, confidence change caps

### CLI
- mnemos init, serve, stats, search, inspect, consolidate, export
- mnemos substrate-tick, index, bridge {status|recall|remember}
- mnemos setup-openclaw

### Multi-Agent
- Shared memory pool with visibility controls
- Agent relationship tracking with trust scores
- Per-agent isolation with optional cross-pollination

### Embedding Support
- Google Gemini embeddings (3072 dims)
- Local sentence-transformers fallback (384 dims)
- Graceful degradation to FTS5-only when no embedding backend available
