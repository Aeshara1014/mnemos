"""
OpenClaw workspace file exporter.

Generates MEMORY.md, daily logs, topic files, and belief files from the
engram store. These files are placed in an agent's workspace directory
where OpenClaw's MemoryIndexManager automatically indexes them.

This is the bridge between Mnemos's living memory and OpenClaw's
file-based memory system.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..store.sqlite_store import EngramStore


class OpenClawExporter:
    """Generates OpenClaw-compatible workspace files from the engram store.

    Usage:
        exporter = OpenClawExporter(store, "~/my-project")
        exporter.export_all(agent_id="main")
    """

    def __init__(self, store: EngramStore, workspace_dir: str) -> None:
        self._store = store
        self._workspace = Path(workspace_dir).expanduser()

    def export_all(self, agent_id: str = "default") -> dict[str, int]:
        """Export all workspace files. Returns {path: bytes_written}."""
        result: dict[str, int] = {}

        memory_md = self._export_memory_md(agent_id)
        if memory_md:
            path = self._workspace / "MEMORY.md"
            path.write_text(memory_md)
            result[str(path)] = len(memory_md)

        daily = self._export_daily_log(agent_id)
        if daily:
            mem_dir = self._workspace / "memory"
            mem_dir.mkdir(parents=True, exist_ok=True)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            path = mem_dir / f"{today}.md"
            path.write_text(daily)
            result[str(path)] = len(daily)

        beliefs_md = self._export_beliefs(agent_id)
        if beliefs_md:
            mem_dir = self._workspace / "memory"
            mem_dir.mkdir(parents=True, exist_ok=True)
            path = mem_dir / "beliefs.md"
            path.write_text(beliefs_md)
            result[str(path)] = len(beliefs_md)

        topics = self._export_topics(agent_id)
        if topics:
            topics_dir = self._workspace / "memory" / "topics"
            topics_dir.mkdir(parents=True, exist_ok=True)
            for topic_name, content in topics.items():
                safe_name = topic_name.replace(" ", "-").replace("/", "-")
                path = topics_dir / f"{safe_name}.md"
                path.write_text(content)
                result[str(path)] = len(content)

        return result

    def _export_memory_md(
        self, agent_id: str, max_entries: int = 30
    ) -> str:
        """Generate MEMORY.md from highest-accessibility engrams + identity + beliefs."""
        sections: list[str] = []
        sections.append("# Memory\n")

        # Identity section
        identity = self._store.get_identity(agent_id)
        if identity and identity.epoch_state.self_summary:
            sections.append(f"## Identity\n{identity.epoch_state.self_summary}\n")

        # Beliefs section
        beliefs = self._store.get_beliefs(agent_id, active_only=True)
        if beliefs:
            lines = []
            for b in beliefs[:10]:
                pct = int(b.confidence * 100)
                lines.append(f"- {b.content} [{b.domain}, {pct}%]")
            sections.append("## Beliefs\n" + "\n".join(lines) + "\n")

        # Key knowledge (top engrams by accessibility)
        engrams = self._store.get_active_engrams(
            agent_id=agent_id, limit=max_entries, load_connections=False
        )
        if engrams:
            lines = []
            for e in engrams:
                # Prefer impact (the lesson) over content (what happened)
                display = e.impact if e.impact else e.content
                if len(display) > 150:
                    display = display[:147] + "..."
                pct = int(e.source.confidence * 100)
                lines.append(f"- {display} [{e.kind}, {pct}%]")
            sections.append("## Key Knowledge\n" + "\n".join(lines) + "\n")

        # Emotional state
        es = self._store.get_latest_emotional_state(agent_id)
        if es:
            sections.append(
                "## Current State\n"
                f"curiosity: {es.curiosity:.1f} | "
                f"clarity: {es.clarity:.1f} | "
                f"warmth: {es.warmth:.1f} | "
                f"restlessness: {es.restlessness:.1f}\n"
            )

        # Footer
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        sections.append(f"\n*Last exported: {now}*")

        return "\n".join(sections)

    def _export_daily_log(self, agent_id: str) -> str:
        """Generate today's daily log from engrams created today."""
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        engrams = self._store.get_active_engrams(
            agent_id=agent_id, limit=200, load_connections=False
        )
        today_engrams = [
            e for e in engrams
            if e.created_at.startswith(today_str)
        ]

        if not today_engrams:
            return ""

        lines = [f"# {today_str}\n"]
        for e in today_engrams:
            content = e.content
            if len(content) > 200:
                content = content[:197] + "..."
            tags = ", ".join(e.tags) if e.tags else ""
            tag_str = f" [{tags}]" if tags else ""
            lines.append(f"- {content}{tag_str}")

        return "\n".join(lines) + "\n"

    def _export_beliefs(self, agent_id: str) -> str:
        """Generate beliefs.md with all active beliefs and revision history."""
        beliefs = self._store.get_beliefs(agent_id, active_only=True)
        if not beliefs:
            return ""

        lines = ["# Beliefs\n"]
        for b in beliefs:
            pct = int(b.confidence * 100)
            lines.append(f"## {b.content}")
            lines.append(f"- Domain: {b.domain}")
            lines.append(f"- Confidence: {pct}%")
            lines.append(f"- Created: {b.created_at[:10]}")
            lines.append(f"- Last challenged: {b.last_challenged[:10]}")
            if b.revision_history:
                lines.append(f"- Revisions: {len(b.revision_history)}")
            lines.append("")

        return "\n".join(lines)

    def _export_topics(self, agent_id: str) -> dict[str, str]:
        """Generate topic files grouped by tag clusters."""
        engrams = self._store.get_active_engrams(
            agent_id=agent_id, limit=500, load_connections=False
        )
        if not engrams:
            return {}

        # Group by most common tags
        by_tag: dict[str, list] = defaultdict(list)
        for e in engrams:
            for tag in e.tags:
                by_tag[tag].append(e)

        # Only create files for tags with 3+ engrams
        topics: dict[str, str] = {}
        for tag, tag_engrams in sorted(by_tag.items()):
            if len(tag_engrams) < 3:
                continue

            lines = [f"# {tag.title()}\n"]
            for e in tag_engrams:
                content = e.content
                if len(content) > 150:
                    content = content[:147] + "..."
                lines.append(f"- {content}")
            lines.append("")

            topics[tag] = "\n".join(lines)

        return topics
