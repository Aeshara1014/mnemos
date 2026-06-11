"""Scope resolution for simple mode: who, with whom, where, and which store.

Extracted from simple_runtime so identity negotiation can be reasoned
about (and tested) apart from the runtime that uses it. The precedence
is always: explicit arguments > environment > config file > defaults.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .config.loader import load_config


def _slugify(value: str, fallback: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return clean or fallback


def _default_project_scope() -> str:
    cwd = Path.cwd()
    if cwd.name:
        return _slugify(cwd.name, "global")
    return "global"


@dataclass(frozen=True)
class MnemosScope:
    """Resolved identity and storage scope for simple mode."""

    agent_id: str
    person_id: str
    project_scope: str
    db_path: str


def resolve_scope(
    *,
    db_path: str | None = None,
    agent_id: str | None = None,
    person_id: str | None = None,
    project_scope: str | None = None,
) -> MnemosScope:
    """Resolve Mnemos identity from explicit args, env, config, then defaults."""

    try:
        config = load_config()
    except Exception:
        config = {}

    resolved_agent = _slugify(
        agent_id
        or os.environ.get("MNEMOS_AGENT_ID", "")
        or str(config.get("agent_id", ""))
        or "mnemos-agent",
        "mnemos-agent",
    )
    resolved_person = _slugify(
        person_id
        or os.environ.get("MNEMOS_PERSON_ID", "")
        or str(config.get("person_id", ""))
        or str(config.get("user_name", ""))
        or "user",
        "user",
    )
    resolved_project = _slugify(
        project_scope
        or os.environ.get("MNEMOS_PROJECT_SCOPE", "")
        or str(config.get("project_scope", ""))
        or _default_project_scope(),
        "global",
    )

    explicit_db = db_path or os.environ.get("MNEMOS_DB_PATH")
    if explicit_db:
        resolved_db = explicit_db
    else:
        store_config = config.get("store", {}) if isinstance(config.get("store"), dict) else {}
        configured = store_config.get("db_path")
        if configured and configured != "~/.mnemos/memory.db":
            resolved_db = str(configured)
        else:
            resolved_db = f"~/.mnemos/{resolved_agent}.db"

    return MnemosScope(
        agent_id=resolved_agent,
        person_id=resolved_person,
        project_scope=resolved_project,
        db_path=resolved_db,
    )
