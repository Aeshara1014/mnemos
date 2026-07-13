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
        Current schema version number. Returns 0 if the meta table does
        not exist or carries no ``schema_version`` row — an un-versioned
        or freshly created database.

    Raises:
        ValueError: If a ``schema_version`` row exists but is not an
            integer. A corrupt stamp is surfaced loudly, never guessed:
            re-migrating from a wrong version could apply the wrong steps.
    """
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
    except sqlite3.OperationalError:
        return 0  # no meta table — nothing has stamped a version yet
    if row is None:
        return 0
    value = row[0]  # index access works for tuple and sqlite3.Row alike
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"corrupt schema_version in meta table: {value!r}"
        ) from exc


def run_migrations(conn: sqlite3.Connection, target_version: int | None = None) -> list[int]:
    """Apply all pending migrations up to target_version, in order.

    Each migration runs inside its own explicitly-managed transaction and
    stamps the new ``schema_version`` before that transaction commits, so
    a crash or a failure leaves the database at the last version that
    fully applied — never a half-migrated state. Forward-only: a request
    to migrate below the current version is refused.

    Migration functions MUST NOT commit, roll back, or open their own
    transactions — the runner owns the transaction boundaries so it can
    roll a failed step back in full, *including its DDL* (see below).

    Args:
        conn: SQLite connection with no open transaction.
        target_version: Version to migrate to. If None, migrates to the
            highest registered migration (a no-op when none are pending).

    Returns:
        The version numbers that were applied, in ascending order (empty
        when the schema is already at or beyond the target).

    Raises:
        RuntimeError: If the connection has an open transaction, or if a
            migration fails — its transaction is rolled back first, and
            the exception names the version left in place.
        ValueError: For a backward target, or a target that no registered
            migration can reach (a schema bump missing its migration).
    """
    if conn.in_transaction:
        raise RuntimeError(
            "run_migrations requires a connection with no open "
            "transaction; commit or roll back before migrating"
        )

    current = get_current_version(conn)
    latest = max(_MIGRATIONS) if _MIGRATIONS else current

    if target_version is None:
        # "bring up to the latest registered migration." A DB already at or
        # beyond that — e.g. this build was rolled back below a version a
        # newer build already applied — is a no-op, never a backward error.
        target = max(latest, current)
    else:
        target = target_version
        if target < current:
            raise ValueError(
                f"cannot migrate backward: schema is at v{current}, target "
                f"is v{target} (migrations are forward-only — restore a "
                "backup to go back)"
            )
        if target > current and target not in _MIGRATIONS:
            # Catches the silent trap where SCHEMA_VERSION was bumped but the
            # matching migration was never registered: without this the run
            # would no-op and the caller would believe it had upgraded.
            raise ValueError(
                f"no migration registered to reach target v{target} (schema "
                f"is at v{current}); a version bump may be missing its migration"
            )

    pending = sorted(v for v in _MIGRATIONS if current < v <= target)
    if not pending:
        return []

    # Python 3.10's sqlite3 opens an implicit transaction only before DML
    # (INSERT/UPDATE/DELETE) — never before DDL (CREATE/ALTER). Relying on
    # that would let a half-finished CREATE survive a rolled-back
    # migration. So we take autocommit mode and drive BEGIN/COMMIT/ROLLBACK
    # ourselves, restoring the caller's isolation setting afterward.
    prior_isolation = conn.isolation_level
    conn.isolation_level = None
    applied: list[int] = []
    try:
        for version in pending:
            description, migrate = _MIGRATIONS[version]
            conn.execute("BEGIN")
            try:
                migrate(conn)
                conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) "
                    "VALUES ('schema_version', ?)",
                    (str(version),),
                )
                conn.execute("COMMIT")
            except Exception as exc:
                conn.execute("ROLLBACK")
                landed = applied[-1] if applied else current
                raise RuntimeError(
                    f"migration to v{version} ({description!r}) failed and "
                    f"was rolled back; schema remains at v{landed}: {exc}"
                ) from exc
            applied.append(version)
    finally:
        conn.isolation_level = prior_isolation
    return applied


def list_migrations() -> list[dict[str, str | int]]:
    """List all registered migrations.

    Returns:
        List of {"version": int, "description": str} dicts.
    """
    return [
        {"version": v, "description": desc}
        for v, (desc, _) in sorted(_MIGRATIONS.items())
    ]
