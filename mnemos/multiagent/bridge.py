"""Cross-agent bridge for syncing context between agents.

Reads each agent's active-context.md, writes a shared summary to a shared
directory, and makes cross-agent awareness available to all agents in the system.

Usage:
    bridge = CrossAgentBridge(agents_config=[
        {"name": "vektor", "workspace": "~/vektor"},
        {"name": "nova", "workspace": "~/nova"},
    ])
    result = bridge.sync()

Or via CLI:
    python -m mnemos.multiagent.bridge sync
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CrossAgentBridge:
    """Syncs context between multiple agents.

    Each agent maintains its own active-context.md. The bridge reads all agents'
    context files and writes:
    1. Per-agent summaries to the shared directory
    2. A combined cross-agent-context.md with all agents' current status

    This enables each agent to know what the others are working on without
    direct communication.
    """

    def __init__(
        self,
        agents_config: list[dict[str, str]] | None = None,
        shared_dir: str = "~/.mnemos/shared",
        config_path: str = "~/.mnemos/agents.json",
    ) -> None:
        """Initialize the cross-agent bridge.

        Args:
            agents_config: List of agent dicts with 'name' and 'workspace' keys.
                If None, attempts to load from config_path.
            shared_dir: Directory for shared context files.
            config_path: Path to agents configuration file.
        """
        self._shared_dir = Path(shared_dir).expanduser().resolve()
        self._shared_dir.mkdir(parents=True, exist_ok=True)

        if agents_config:
            self._agents = agents_config
        else:
            self._agents = self._load_config(config_path)

    def _load_config(self, config_path: str) -> list[dict[str, str]]:
        """Load agent configuration from file.

        Args:
            config_path: Path to the agents.json config file.

        Returns:
            List of agent config dicts. Empty list if file doesn't exist.
        """
        path = Path(config_path).expanduser()
        if not path.exists():
            return []

        try:
            data = json.loads(path.read_text())
            if isinstance(data, list):
                return data
            return data.get("agents", [])
        except (json.JSONDecodeError, OSError):
            return []

    def sync(self) -> dict[str, Any]:
        """Run the cross-agent context sync.

        Reads each agent's active-context.md, writes per-agent summaries
        and a combined cross-agent context file.

        Returns:
            Result dict with sync status and what changed.
        """
        result: dict[str, Any] = {
            "timestamp": _now_iso(),
            "agents_synced": 0,
            "agents_skipped": 0,
            "changes": [],
        }

        if not self._agents:
            result["status"] = "no_agents_configured"
            return result

        agent_contexts: dict[str, str] = {}

        for agent in self._agents:
            name = agent.get("name", "unknown")
            workspace = agent.get("workspace", "")

            if not workspace:
                result["agents_skipped"] += 1
                continue

            context_path = Path(workspace).expanduser() / "memory" / "active-context.md"

            if not context_path.exists():
                result["agents_skipped"] += 1
                continue

            try:
                content = context_path.read_text()
                agent_contexts[name] = content

                # Write per-agent summary to shared dir
                summary_path = self._shared_dir / f"{name}-context.md"
                old_content = summary_path.read_text() if summary_path.exists() else ""

                if content != old_content:
                    summary_path.write_text(content)
                    result["changes"].append(f"{name}: context updated")

                result["agents_synced"] += 1

            except OSError as e:
                result["changes"].append(f"{name}: read error — {e}")
                result["agents_skipped"] += 1

        # Write combined cross-agent context
        if agent_contexts:
            combined = self._build_combined_context(agent_contexts)
            combined_path = self._shared_dir / "cross-agent-context.md"

            old_combined = combined_path.read_text() if combined_path.exists() else ""
            if combined != old_combined:
                combined_path.write_text(combined)
                result["changes"].append("cross-agent-context.md updated")

            # Also write to each agent's workspace for easy access
            for agent in self._agents:
                workspace = agent.get("workspace", "")
                if not workspace:
                    continue
                agent_context_dir = Path(workspace).expanduser() / "memory"
                if agent_context_dir.is_dir():
                    try:
                        (agent_context_dir / "cross-agent-context.md").write_text(combined)
                    except OSError:
                        pass

        result["status"] = "ok" if result["agents_synced"] > 0 else "no_active_agents"
        return result

    def _build_combined_context(self, agent_contexts: dict[str, str]) -> str:
        """Build the combined cross-agent context document.

        Args:
            agent_contexts: Dict mapping agent name to their active-context.md content.

        Returns:
            Combined markdown document.
        """
        lines = [
            "# Cross-Agent Context",
            "",
            f"_Last synced: {_now_iso()}_",
            f"_Agents: {', '.join(sorted(agent_contexts.keys()))}_",
            "",
            "---",
            "",
        ]

        for name, context in sorted(agent_contexts.items()):
            lines.append(f"## {name}")
            lines.append("")
            # Include a trimmed version — skip HTML comments and keep it brief
            trimmed = self._trim_context(context)
            lines.append(trimmed)
            lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def _trim_context(self, content: str, max_lines: int = 50) -> str:
        """Trim context content for the combined document.

        Removes HTML comments and limits length.

        Args:
            content: Raw active-context.md content.
            max_lines: Maximum lines to include.

        Returns:
            Trimmed content.
        """
        lines = []
        in_comment = False
        for line in content.split("\n"):
            if "<!--" in line:
                in_comment = True
            if not in_comment:
                lines.append(line)
            if "-->" in line:
                in_comment = False

        # Skip the header (it's already in the parent section)
        filtered = [l for l in lines if not l.startswith("# Active Context")]

        if len(filtered) > max_lines:
            filtered = filtered[:max_lines]
            filtered.append("_(truncated)_")

        return "\n".join(filtered).strip()

    def get_agent_status(self) -> list[dict[str, Any]]:
        """Get the current status of all configured agents.

        Returns:
            List of agent status dicts.
        """
        statuses = []
        for agent in self._agents:
            name = agent.get("name", "unknown")
            workspace = agent.get("workspace", "")

            status: dict[str, Any] = {"name": name, "workspace": workspace}

            if workspace:
                context_path = Path(workspace).expanduser() / "memory" / "active-context.md"
                status["has_context"] = context_path.exists()
                if context_path.exists():
                    stat = context_path.stat()
                    status["last_updated"] = datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat()
            else:
                status["has_context"] = False

            statuses.append(status)

        return statuses


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the cross-agent bridge."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="mnemos-bridge",
        description="Cross-agent context bridge for Mnemos",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("sync", help="Sync context across all configured agents")
    sub.add_parser("status", help="Show status of all configured agents")

    p_add = sub.add_parser("add-agent", help="Add an agent to the bridge config")
    p_add.add_argument("name", help="Agent name")
    p_add.add_argument("workspace", help="Agent workspace path")

    args = parser.parse_args(argv)

    if args.command == "sync":
        bridge = CrossAgentBridge()
        result = bridge.sync()
        if not result.get("changes"):
            print("HEARTBEAT_OK")
        else:
            print(f"Synced {result['agents_synced']} agents:")
            for change in result["changes"]:
                print(f"  - {change}")
        return 0

    elif args.command == "status":
        bridge = CrossAgentBridge()
        statuses = bridge.get_agent_status()
        if not statuses:
            print("No agents configured.")
            print("Add agents to ~/.mnemos/agents.json or use: mnemos bridge add-agent NAME WORKSPACE")
            return 0
        for s in statuses:
            ctx = "active" if s.get("has_context") else "no context"
            updated = s.get("last_updated", "never")
            print(f"  {s['name']}: {ctx} (updated: {updated})")
        return 0

    elif args.command == "add-agent":
        config_path = Path("~/.mnemos/agents.json").expanduser()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        agents = []
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text())
                agents = data if isinstance(data, list) else data.get("agents", [])
            except (json.JSONDecodeError, OSError):
                pass

        # Check for duplicates
        if any(a.get("name") == args.name for a in agents):
            print(f"Agent '{args.name}' already configured.")
            return 1

        agents.append({"name": args.name, "workspace": args.workspace})
        config_path.write_text(json.dumps(agents, indent=2))
        print(f"Added agent '{args.name}' with workspace '{args.workspace}'")
        return 0

    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
