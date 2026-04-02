"""
Schema migration management for Mnemos SQLite store.

Handles schema evolution by tracking the current schema version and
applying migration functions in order. Each migration is a function
that takes a SQLite connection and applies the schema changes.

Migration strategy:
- Schema version is tracked in the `meta` table
- Migrations are ordered by version number
- Each migration is applied in a transaction
- Forward-only (no rollback support — backup before migrating)
"""

from __future__ import annotations

import sqlite3
from typing import Callable


# Migration registry: version -> (description, migration_function)
_MIGRATIONS: dict[int, tuple[str, Callable[[sqlite3.Connection], None]]] = {}


def register_migration(
    version: int,
    description: str,
) -> Callable:
    """Decorator to register a schema migration function.

    Usage:
        @register_migration(2, "Add embedding column to engrams")
        def migrate_v2(conn: sqlite3.Connection) -> None:
            conn.execute("ALTER TABLE engrams ADD COLUMN embedding BLOB")

    Args:
        version: The schema version this migration upgrades TO.
        description: Human-readable description of the migration.

    Returns:
        Decorator function.
    """
    def decorator(func: Callable[[sqlite3.Connection], None]) -> Callable:
        _MIGRATIONS[version] = (description, func)
        return func
    return decorator


def get_current_version(conn: sqlite3.Connection) -> int:
    """Get the current schema version from the meta table.

    Args:
        conn: SQLite connection.

    Returns:
        Current schema version number. Returns 0 if meta table doesn't exist.
    """
    raise NotImplementedError("Step 18: Version detection implementation")


def run_migrations(conn: sqlite3.Connection, target_version: int | None = None) -> list[int]:
    """Apply all pending migrations up to target_version.

    Args:
        conn: SQLite connection (with autocommit off).
        target_version: Version to migrate to. If None, migrates to latest.

    Returns:
        List of version numbers that were applied.

    Raises:
        RuntimeError: If a migration fails (transaction is rolled back).
    """
    raise NotImplementedError("Step 18: Migration runner implementation")


def list_migrations() -> list[dict[str, str | int]]:
    """List all registered migrations.

    Returns:
        List of {"version": int, "description": str} dicts.
    """
    return [
        {"version": v, "description": desc}
        for v, (desc, _) in sorted(_MIGRATIONS.items())
    ]
