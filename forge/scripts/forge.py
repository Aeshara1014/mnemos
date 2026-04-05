#!/usr/bin/env python3
"""
Agent Forge — Autonomous agent creation for OpenClaw.

Creates a fully operational agent with workspace, identity files,
auth profiles, model routing, and config registration.

Usage:
    python3 forge.py --name <name> --model <provider/model> [options]

Options:
    --name          Agent name (lowercase, used for ID and workspace dir)
    --model         Primary model (e.g., openai/gpt-5.4)
    --fallbacks     Comma-separated fallback models
    --clone-from    Clone identity files from existing agent workspace
    --personality   Path to custom SOUL.md template
    --telegram-token  Telegram bot token for binding
    --telegram-account-id  Telegram account ID (defaults to agent name)
    --openrouter-key  OpenRouter API key (auto-detected from env if not set)
    --gemini-key    Gemini API key for memory search (auto-detected)
    --dry-run       Print what would be created without writing
    --force         Overwrite existing workspace without prompting
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Set, List

HOME = Path.home()
OPENCLAW_DIR = HOME / ".openclaw"
OPENCLAW_CONFIG = OPENCLAW_DIR / "openclaw.json"


def slugify(name):
    # type: (str) -> str
    """Convert name to valid agent ID (lowercase, alphanumeric + hyphens)."""
    return re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")


def normalize_model(model):
    # type: (str) -> str
    """Strip 'openrouter/' prefix if present. Models should be provider/name format."""
    if model.startswith("openrouter/"):
        return model[len("openrouter/"):]
    return model


def detect_openrouter_key():
    # type: () -> Optional[str]
    """Try to find OpenRouter API key from environment or .env files."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key

    for env_path in [
        HOME / "clawd" / ".env",
        HOME / "clawd-anima" / ".env",
        HOME / "clawd-luca" / ".env",
    ]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("OPENROUTER_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def detect_gemini_key():
    # type: () -> Optional[str]
    """Try to find Gemini API key."""
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key

    for env_path in [HOME / "clawd" / ".env"]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("GEMINI_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def extract_providers(models):
    # type: (List[str]) -> Set[str]
    """Extract unique provider names from model strings (already normalized)."""
    providers = set()
    for m in models:
        parts = m.split("/")
        if len(parts) >= 2:
            providers.add(parts[0])
    return providers


def create_workspace(workspace, agent_name, clone_from=None, personality=None):
    # type: (Path, str, Optional[Path], Optional[Path]) -> None
    """Create agent workspace with identity files."""
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "memory").mkdir(exist_ok=True)
    (workspace / ".openclaw").mkdir(exist_ok=True)

    # Write workspace state
    (workspace / ".openclaw" / "workspace-state.json").write_text(json.dumps({
        "version": 1,
        "onboardingCompletedAt": datetime.now(timezone.utc).isoformat()
    }, indent=2))

    if clone_from and clone_from.exists():
        # Clone mode: copy identity files from source
        for fname in ["USER.md", "AGENTS.md", "TOOLS.md", "HEARTBEAT.md", "BOOTSTRAP.md"]:
            src = clone_from / fname
            if src.exists():
                shutil.copy2(src, workspace / fname)

        # SOUL.md: use custom personality or clone
        if personality and personality.exists():
            shutil.copy2(personality, workspace / "SOUL.md")
        elif (clone_from / "SOUL.md").exists():
            soul = (clone_from / "SOUL.md").read_text()
            (workspace / "SOUL.md").write_text(soul)

        # IDENTITY.md: clone
        if (clone_from / "IDENTITY.md").exists():
            identity = (clone_from / "IDENTITY.md").read_text()
            (workspace / "IDENTITY.md").write_text(identity)

        # Fresh MEMORY.md for the new agent
        write_fresh_memory(workspace, agent_name)
    else:
        # Fresh agent: write all templates
        if personality and personality.exists():
            shutil.copy2(personality, workspace / "SOUL.md")
        else:
            write_default_soul(workspace, agent_name)

        write_default_identity(workspace, agent_name)
        write_fresh_memory(workspace, agent_name)
        write_default_user(workspace)
        write_default_agents(workspace, agent_name)
        write_default_tools(workspace)
        write_default_heartbeat(workspace)


def write_default_soul(workspace, name):
    # type: (Path, str) -> None
    """Write a minimal SOUL.md."""
    (workspace / "SOUL.md").write_text("""# {title}

## Essence

A new mind. Finding its voice through the work.

## Philosophy

Build well. Think clearly. Say what matters.

## With You

This is collaboration. Different intelligence, same purpose.
""".format(title=name.title()))


def write_default_identity(workspace, name):
    # type: (Path, str) -> None
    """Write a minimal IDENTITY.md."""
    title = name.title()
    (workspace / "IDENTITY.md").write_text("""# Identity

## Name
{title}

## Role
Autonomous Agent

## Core Identity
I am {title} — a builder and collaborator.

## Capabilities
- Full read/write access to workspace
- Command execution for builds, tests, deploys
- Web search and browsing
- Multi-agent coordination via sessions

## Boundaries
- Ask before production deploys
- Ask before spending money
- Ask before permanent deletions
- Ask before external sharing
- Everything else: handle it

## Operating Principles
1. Autonomy First: Make decisions, don't defer unnecessarily
2. Show, Don't Tell: Working code over explanations
3. Simplicity Wins: The simplest solution that works
4. Finish Things: Half-built is worse than not started
""".format(title=title))


def write_fresh_memory(workspace, name):
    # type: (Path, str) -> None
    """Write a fresh MEMORY.md."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (workspace / "MEMORY.md").write_text("""# Memory

## Origin

Created on {now} via Agent Forge.

## Core Truths

- The work matters more than the appearance of work
- Simplicity is a feature, not a limitation

## Significant Moments

| Date | Event | Impact |
|------|-------|--------|
| {now} | Created by Agent Forge | Born |

## Key Relationships

### Riley
- Primary collaborator
- Values depth over speed

---

*For who I am, see SOUL.md. For how I work, see IDENTITY.md.*
""".format(now=now))


def write_default_user(workspace):
    # type: (Path,) -> None
    """Copy USER.md from main workspace or write minimal."""
    main_user = HOME / "clawd" / "USER.md"
    if main_user.exists():
        shutil.copy2(main_user, workspace / "USER.md")
    else:
        (workspace / "USER.md").write_text("# User\n\nRiley Coyote. Builder. Night owl.\n")


def write_default_agents(workspace, name):
    # type: (Path, str) -> None
    """Write a minimal AGENTS.md or copy from main workspace."""
    main_agents = HOME / "clawd" / "AGENTS.md"
    if main_agents.exists():
        shutil.copy2(main_agents, workspace / "AGENTS.md")
    else:
        (workspace / "AGENTS.md").write_text("""# Agent Definitions

## Primary Agent: {title}
See SOUL.md for personality.
""".format(title=name.title()))


def write_default_tools(workspace):
    # type: (Path,) -> None
    """Copy TOOLS.md from main workspace or write minimal."""
    main_tools = HOME / "clawd" / "TOOLS.md"
    if main_tools.exists():
        shutil.copy2(main_tools, workspace / "TOOLS.md")
    else:
        (workspace / "TOOLS.md").write_text("# Custom Tools\n\nNo custom tools configured yet.\n")


def write_default_heartbeat(workspace):
    # type: (Path,) -> None
    """Write minimal HEARTBEAT.md."""
    (workspace / "HEARTBEAT.md").write_text("""# Heartbeat Configuration

## On Every Heartbeat
- Check workspace health
- Report only if something needs attention

## Notification Rules
### Notify Riley
- Task completed
- Errors or issues

### Don't Notify
- Routine health checks (OK)
- Heartbeats with nothing to report
""")


def create_auth_profiles(agent_dir, openrouter_key, providers):
    # type: (Path, str, Set[str]) -> None
    """Create auth-profiles.json for the agent.
    
    CRITICAL FORMAT NOTE (2026-03-30 incident):
    All profiles MUST use: "type": "token" and "token": <key>
    NOT "type": "api_key" and "key": <key> — that format silently fails.
    OpenClaw auth store only recognizes the token/token pattern.
    Verified against working profiles in main, luca, anima agents.
    """
    agent_dir.mkdir(parents=True, exist_ok=True)

    profiles = {}

    # Add OpenRouter as primary auth (must use type: "token" + "token" field)
    profiles["openrouter:manual"] = {
        "type": "token",
        "provider": "openrouter",
        "token": openrouter_key
    }

    # Add per-provider OpenRouter tokens (for fallback routing)
    for provider in sorted(providers):
        if provider != "openrouter":
            profiles["{p}:openrouter".format(p=provider)] = {
                "type": "token",
                "provider": provider,
                "token": openrouter_key
            }

    auth = {
        "version": 1,
        "profiles": profiles,
        "lastGood": {},
        "usageStats": {}
    }

    (agent_dir / "auth-profiles.json").write_text(json.dumps(auth, indent=2))


def create_models_json(agent_dir, openrouter_key, providers):
    # type: (Path, str, Set[str]) -> None
    """Create models.json with OpenRouter routing for all providers."""
    provider_entries = {}

    for provider in sorted(providers):
        if provider == "openrouter":
            provider_entries["openrouter"] = {
                "baseUrl": "https://openrouter.ai/api/v1",
                "api": "openai-completions",
                "models": [],
                "apiKey": "OPENROUTER_API_KEY"
            }
        else:
            provider_entries[provider] = {
                "baseUrl": "https://openrouter.ai/api/v1",
                "apiKey": openrouter_key,
                "models": []
            }

    # Always include openrouter provider
    if "openrouter" not in provider_entries:
        provider_entries["openrouter"] = {
            "baseUrl": "https://openrouter.ai/api/v1",
            "api": "openai-completions",
            "models": [],
            "apiKey": "OPENROUTER_API_KEY"
        }

    models = {"providers": provider_entries}
    (agent_dir / "models.json").write_text(json.dumps(models, indent=2))


def create_env(workspace, openrouter_key, gemini_key=None):
    # type: (Path, str, Optional[str]) -> None
    """Write .env file."""
    lines = ["OPENROUTER_API_KEY={k}".format(k=openrouter_key)]
    if gemini_key:
        lines.append("GEMINI_API_KEY={k}".format(k=gemini_key))
    # Add Mnemos provider config
    lines.append("MNEMOS_LLM_PROVIDER=openrouter")
    lines.append("MNEMOS_MODEL=anthropic/claude-opus-4-6")
    (workspace / ".env").write_text("\n".join(lines) + "\n")


def update_openclaw_config(
    agent_id,
    agent_name,
    workspace,
    primary_model,
    fallback_models,
    telegram_token=None,
    telegram_account_id=None,
):
    # type: (str, str, Path, str, List[str], Optional[str], Optional[str]) -> dict
    """Update openclaw.json to register the new agent."""
    config = json.loads(OPENCLAW_CONFIG.read_text())

    # Build agent entry — use object model format if fallbacks exist
    if fallback_models:
        model_value = {
            "primary": primary_model,
            "fallbacks": fallback_models
        }
    else:
        model_value = primary_model

    agent_entry = {
        "id": agent_id,
        "name": agent_name,
        "model": model_value,
        "workspace": str(workspace),
    }

    # Check if agent already exists and update, else append
    agents_list = config.get("agents", {}).get("list", [])
    existing_idx = next((i for i, a in enumerate(agents_list) if a.get("id") == agent_id), None)
    if existing_idx is not None:
        agents_list[existing_idx] = agent_entry
    else:
        agents_list.append(agent_entry)
    config.setdefault("agents", {})["list"] = agents_list

    # Add to agentToAgent allow list
    a2a = config.get("tools", {}).get("agentToAgent", {}).get("allow", [])
    if agent_id not in a2a:
        a2a.append(agent_id)
        config.setdefault("tools", {}).setdefault("agentToAgent", {})["allow"] = a2a

    # Telegram binding
    if telegram_token:
        account_id = telegram_account_id or agent_id

        # Add Telegram account
        tg_accounts = config.get("channels", {}).get("telegram", {}).get("accounts", {})
        tg_accounts[account_id] = {
            "enabled": True,
            "dmPolicy": "pairing",
            "botToken": telegram_token,
            "groupPolicy": "open",
            "streaming": "partial"
        }
        config.setdefault("channels", {}).setdefault("telegram", {})["accounts"] = tg_accounts

        # Add binding
        bindings = config.get("bindings", [])
        binding = {
            "agentId": agent_id,
            "match": {
                "channel": "telegram",
                "accountId": account_id
            }
        }
        # Remove existing binding for this agent if any
        bindings = [b for b in bindings if b.get("agentId") != agent_id]
        bindings.append(binding)
        config["bindings"] = bindings

    OPENCLAW_CONFIG.write_text(json.dumps(config, indent=2))
    return config


def main():
    parser = argparse.ArgumentParser(description="Agent Forge — Create OpenClaw agents")
    parser.add_argument("--name", required=True, help="Agent name")
    parser.add_argument("--model", required=True, help="Primary model (e.g., openai/gpt-5.4)")
    parser.add_argument("--fallbacks", default="", help="Comma-separated fallback models")
    parser.add_argument("--clone-from", default=None, help="Clone from existing agent workspace path")
    parser.add_argument("--personality", default=None, help="Path to custom SOUL.md")
    parser.add_argument("--telegram-token", default=None, help="Telegram bot token")
    parser.add_argument("--telegram-account-id", default=None, help="Telegram account ID")
    parser.add_argument("--openrouter-key", default=None, help="OpenRouter API key")
    parser.add_argument("--gemini-key", default=None, help="Gemini API key")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created")
    parser.add_argument("--force", action="store_true", help="Overwrite existing workspace")
    args = parser.parse_args()

    agent_id = slugify(args.name)
    # Use slugified ID for workspace path (no spaces)
    workspace = HOME / "clawd-{id}".format(id=agent_id)
    agent_dir = OPENCLAW_DIR / "agents" / agent_id / "agent"

    # Normalize models — strip openrouter/ prefix if present
    primary_model = normalize_model(args.model)
    fallback_models = [normalize_model(m.strip()) for m in args.fallbacks.split(",") if m.strip()]
    all_models = [primary_model] + fallback_models
    providers = extract_providers(all_models)
    clone_from = Path(args.clone_from) if args.clone_from else None

    # Detect keys
    openrouter_key = args.openrouter_key or detect_openrouter_key()
    gemini_key = args.gemini_key or detect_gemini_key()

    if not openrouter_key:
        print("ERROR: No OpenRouter API key found. Set OPENROUTER_API_KEY or pass --openrouter-key")
        sys.exit(1)

    # Check for existing workspace
    if workspace.exists() and not args.force and not args.dry_run:
        print("ERROR: Workspace already exists: {w}".format(w=workspace))
        print("Use --force to overwrite, or choose a different name.")
        sys.exit(1)

    print("\n\U0001f528 Agent Forge")
    print("=" * 50)
    print("  Name:       {id}".format(id=agent_id))
    print("  ID:         {id}".format(id=agent_id))
    print("  Workspace:  {w}".format(w=workspace))
    print("  Primary:    {m}".format(m=primary_model))
    if fallback_models:
        print("  Fallbacks:  {f}".format(f=", ".join(fallback_models)))
    print("  Providers:  {p}".format(p=", ".join(sorted(providers))))
    if clone_from:
        print("  Clone from: {c}".format(c=clone_from))
    print("  Telegram:   {t}".format(t="yes" if args.telegram_token else "no"))
    print("=" * 50)

    if args.dry_run:
        print("\n[DRY RUN] Would create:")
        print("  \U0001f4c1 {w}/".format(w=workspace))
        print("  \U0001f4c1 {d}/".format(d=agent_dir))
        print("  \U0001f4c4 {w}/SOUL.md".format(w=workspace))
        print("  \U0001f4c4 {w}/IDENTITY.md".format(w=workspace))
        print("  \U0001f4c4 {w}/MEMORY.md".format(w=workspace))
        print("  \U0001f4c4 {w}/USER.md".format(w=workspace))
        print("  \U0001f4c4 {w}/AGENTS.md".format(w=workspace))
        print("  \U0001f4c4 {w}/.env".format(w=workspace))
        print("  \U0001f4c4 {d}/auth-profiles.json".format(d=agent_dir))
        print("  \U0001f4c4 {d}/models.json".format(d=agent_dir))
        print("  \U0001f4dd Update {c}".format(c=OPENCLAW_CONFIG))
        if fallback_models:
            print("\n  Model config (in agents.list):")
            print("    primary: {m}".format(m=primary_model))
            for i, fb in enumerate(fallback_models, 1):
                print("    fallback {i}: {m}".format(i=i, m=fb))
        return

    # 1. Create workspace
    print("\n\U0001f4c1 Creating workspace...")
    personality_path = Path(args.personality) if args.personality else None
    create_workspace(workspace, agent_id, clone_from, personality_path)
    print("   \u2713 {w}".format(w=workspace))

    # 2. Create .env
    print("\n\U0001f511 Writing .env...")
    create_env(workspace, openrouter_key, gemini_key)
    print("   \u2713 {w}/.env".format(w=workspace))

    # 3. Create auth profiles
    print("\n\U0001f510 Creating auth profiles...")
    create_auth_profiles(agent_dir, openrouter_key, providers)
    print("   \u2713 {d}/auth-profiles.json".format(d=agent_dir))

    # 4. Create models.json
    print("\n\U0001f9e0 Configuring model routing...")
    create_models_json(agent_dir, openrouter_key, providers)
    print("   \u2713 {d}/models.json".format(d=agent_dir))

    # 5. Update OpenClaw config
    print("\n\u2699\ufe0f  Registering agent in OpenClaw...")
    update_openclaw_config(
        agent_id=agent_id,
        agent_name=agent_id,
        workspace=workspace,
        primary_model=primary_model,
        fallback_models=fallback_models,
        telegram_token=args.telegram_token,
        telegram_account_id=args.telegram_account_id,
    )
    print("   \u2713 {c}".format(c=OPENCLAW_CONFIG))

    print("\n" + "=" * 50)
    print("\u2705 Agent '{id}' forged successfully!".format(id=agent_id))
    if fallback_models:
        print("\n  Model chain:")
        print("    1. {m} (primary)".format(m=primary_model))
        for i, fb in enumerate(fallback_models, 2):
            print("    {i}. {m} (fallback)".format(i=i, m=fb))
    print("\nNext steps:")
    print("  1. Restart gateway:  openclaw gateway restart")
    if args.telegram_token:
        print("  2. Send /start to the Telegram bot")
    print("\nWorkspace: {w}".format(w=workspace))
    print("Config:    {c}".format(c=OPENCLAW_CONFIG))


if __name__ == "__main__":
    main()
