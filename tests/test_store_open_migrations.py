"""Store-open migration wiring (EngramStore._init_db × migrations runner).

The version stamp only ever advances honestly. Three doors: a fresh store
is born current and stamped; an un-versioned store is healed additively
and adopts versioning once; a versioned store goes through the runner —
which fails LOUDLY on a missing migration or a store from a newer build.
The first real customer of the fresh-store door is Claw's reintegration
reset; the loud doors protect every store the keeper ever reopens.
"""

import sqlite3

import pytest

from mnemos.store import migrations
from mnemos.store.sqlite_store import SCHEMA_VERSION, EngramStore


@pytest.fixture()
def clean_registry():
    """Snapshot, clear, and restore the module-global migration registry
    so tests that register migrations never leak into one another — or
    into the real (empty) production registry."""
    saved = dict(migrations._MIGRATIONS)
    migrations._MIGRATIONS.clear()
    try:
        yield migrations._MIGRATIONS
    finally:
        migrations._MIGRATIONS.clear()
        migrations._MIGRATIONS.update(saved)


def _version_row(path) -> str | None:
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        return None if row is None else row[0]
    finally:
        conn.close()


def _set_version(path, value) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
        (str(value),),
    )
    conn.commit()
    conn.close()


# ── door 1: fresh store, born current ──

def test_fresh_store_stamped_at_schema_version(tmp_path):
    path = tmp_path / "fresh.db"
    EngramStore(path).close()
    assert _version_row(path) == str(SCHEMA_VERSION)


def test_fresh_store_runs_no_migrations(tmp_path, clean_registry):
    ran = []

    @migrations.register_migration(SCHEMA_VERSION, "should never run on fresh")
    def _m(conn):  # pragma: no cover - body must not execute
        ran.append(True)

    EngramStore(tmp_path / "fresh.db").close()
    assert ran == []


# ── door 2: un-versioned store adopts versioning once ──

def test_unversioned_store_adopts_current_stamp(tmp_path):
    path = tmp_path / "old.db"
    EngramStore(path).close()
    conn = sqlite3.connect(str(path))
    conn.execute("DELETE FROM meta WHERE key = 'schema_version'")
    conn.commit()
    conn.close()

    EngramStore(path).close()  # reopen: adoption, not migration
    assert _version_row(path) == str(SCHEMA_VERSION)


# ── door 3: versioned store goes through the runner ──

def test_current_store_reopens_as_noop(tmp_path):
    path = tmp_path / "live.db"
    EngramStore(path).close()
    EngramStore(path).close()  # the everyday keeper-relight path
    assert _version_row(path) == str(SCHEMA_VERSION)


def test_old_version_applies_registered_migration_on_open(tmp_path, clean_registry):
    path = tmp_path / "behind.db"
    EngramStore(path).close()
    _set_version(path, SCHEMA_VERSION - 1)

    @migrations.register_migration(SCHEMA_VERSION, "marker table for the test")
    def _m(conn):
        conn.execute("CREATE TABLE IF NOT EXISTS _migration_marker (x INTEGER)")

    EngramStore(path).close()
    assert _version_row(path) == str(SCHEMA_VERSION)
    conn = sqlite3.connect(str(path))
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE name = '_migration_marker'"
    ).fetchone()
    conn.close()


def test_old_version_with_no_registered_migration_fails_loud(tmp_path, clean_registry):
    path = tmp_path / "orphaned.db"
    EngramStore(path).close()
    _set_version(path, SCHEMA_VERSION - 1)

    with pytest.raises(ValueError, match="no migration registered"):
        EngramStore(path)


def test_store_from_a_newer_build_is_refused(tmp_path):
    path = tmp_path / "future.db"
    EngramStore(path).close()
    _set_version(path, SCHEMA_VERSION + 1)

    with pytest.raises(ValueError, match="backward"):
        EngramStore(path)


def test_corrupt_stamp_surfaces_at_open(tmp_path):
    path = tmp_path / "corrupt.db"
    EngramStore(path).close()
    _set_version(path, "banana")

    with pytest.raises(ValueError, match="corrupt schema_version"):
        EngramStore(path)


# ── the forgot-to-bump guard ──

def test_migration_registered_beyond_schema_version_fails_loud(tmp_path, clean_registry):
    @migrations.register_migration(SCHEMA_VERSION + 1, "bump was forgotten")
    def _m(conn):  # pragma: no cover - must never run
        pass

    with pytest.raises(RuntimeError, match="bump SCHEMA_VERSION"):
        EngramStore(tmp_path / "any.db")
