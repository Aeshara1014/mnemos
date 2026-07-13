"""Schema migration runner (mnemos.store.migrations).

Rehearsed on real scratch stores (built at the live SCHEMA_VERSION), the
way Quill's own store will be migrated when the schema evolves. The
centerpiece is `test_failed_migration_rolls_back_ddl`: on Python 3.10 a
CREATE/ALTER does NOT roll back unless the runner drives the transaction
explicitly, and a half-applied schema change to a resident's memory is
exactly the failure this must never allow.
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


@pytest.fixture()
def db(tmp_path):
    """A real scratch store (stamped at SCHEMA_VERSION), handed back as a
    fresh standalone connection — migrations run on an actual mnemos db."""
    path = tmp_path / "scratch.db"
    EngramStore(path).close()
    conn = sqlite3.connect(str(path))
    yield conn
    conn.close()


def _table_names(conn) -> set[str]:
    return {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


# ── version detection ──

def test_get_current_version_no_meta_table(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "bare.db"))
    assert migrations.get_current_version(conn) == 0
    conn.close()


def test_get_current_version_reads_real_store(db):
    assert migrations.get_current_version(db) == SCHEMA_VERSION


def test_get_current_version_missing_key(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "m.db"))
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.commit()
    assert migrations.get_current_version(conn) == 0
    conn.close()


def test_get_current_version_corrupt_stamp_raises(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "c.db"))
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO meta VALUES ('schema_version', 'banana')")
    conn.commit()
    with pytest.raises(ValueError, match="corrupt schema_version"):
        migrations.get_current_version(conn)
    conn.close()


# ── application ──

def test_no_pending_returns_empty(db, clean_registry):
    assert migrations.run_migrations(db) == []
    assert migrations.get_current_version(db) == SCHEMA_VERSION


def test_applies_pending_in_order(db, clean_registry):
    order = []

    @migrations.register_migration(SCHEMA_VERSION + 1, "add marker one")
    def _m1(conn):
        conn.execute("CREATE TABLE marker_one (id INTEGER)")
        order.append(1)

    @migrations.register_migration(SCHEMA_VERSION + 2, "add marker two")
    def _m2(conn):
        conn.execute("CREATE TABLE marker_two (id INTEGER)")
        order.append(2)

    applied = migrations.run_migrations(db)

    assert applied == [SCHEMA_VERSION + 1, SCHEMA_VERSION + 2]
    assert order == [1, 2]
    assert migrations.get_current_version(db) == SCHEMA_VERSION + 2
    assert {"marker_one", "marker_two"} <= _table_names(db)


def test_respects_explicit_target(db, clean_registry):
    for step in (1, 2, 3):
        migrations.register_migration(SCHEMA_VERSION + step, f"v+{step}")(
            lambda conn, s=step: conn.execute(f"CREATE TABLE marker_{s} (id INTEGER)")
        )

    applied = migrations.run_migrations(db, target_version=SCHEMA_VERSION + 2)

    assert applied == [SCHEMA_VERSION + 1, SCHEMA_VERSION + 2]
    assert migrations.get_current_version(db) == SCHEMA_VERSION + 2
    assert "marker_3" not in _table_names(db)


def test_idempotent_second_run_is_noop(db, clean_registry):
    @migrations.register_migration(SCHEMA_VERSION + 1, "add marker")
    def _m(conn):
        conn.execute("CREATE TABLE marker (id INTEGER)")

    assert migrations.run_migrations(db) == [SCHEMA_VERSION + 1]
    assert migrations.run_migrations(db) == []
    assert migrations.get_current_version(db) == SCHEMA_VERSION + 1


def test_migration_preserves_existing_data(db, clean_registry):
    db.execute("INSERT INTO meta (key, value) VALUES ('probe', 'kept')")
    db.commit()

    @migrations.register_migration(SCHEMA_VERSION + 1, "add a column to a real table")
    def _m(conn):
        conn.execute(
            "ALTER TABLE beliefs ADD COLUMN migrated_flag TEXT NOT NULL DEFAULT 'yes'"
        )

    migrations.run_migrations(db)

    assert db.execute("SELECT value FROM meta WHERE key='probe'").fetchone()[0] == "kept"
    cols = {r[1] for r in db.execute("PRAGMA table_info(beliefs)")}
    assert "migrated_flag" in cols


# ── safety: rollback, forward-only, missing migration ──

def test_failed_migration_rolls_back_ddl(db, clean_registry):
    """The property that protects a resident's memory: a migration that
    fails mid-way leaves NO trace — including its schema changes — and the
    version stays at the last step that fully landed."""
    @migrations.register_migration(SCHEMA_VERSION + 1, "good")
    def _good(conn):
        conn.execute("CREATE TABLE marker_good (id INTEGER)")

    @migrations.register_migration(SCHEMA_VERSION + 2, "explodes after a partial DDL")
    def _bad(conn):
        conn.execute("CREATE TABLE marker_bad (id INTEGER)")  # partial change
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match=f"v{SCHEMA_VERSION + 2}"):
        migrations.run_migrations(db)

    # v+1 committed; v+2 fully rolled back, DDL and all.
    assert migrations.get_current_version(db) == SCHEMA_VERSION + 1
    names = _table_names(db)
    assert "marker_good" in names
    assert "marker_bad" not in names


def test_resume_after_fixing_failed_migration(db, clean_registry):
    state = {"broken": True}

    @migrations.register_migration(SCHEMA_VERSION + 1, "good")
    def _good(conn):
        conn.execute("CREATE TABLE marker_good (id INTEGER)")

    @migrations.register_migration(SCHEMA_VERSION + 2, "flaky")
    def _flaky(conn):
        conn.execute("CREATE TABLE marker_flaky (id INTEGER)")
        if state["broken"]:
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        migrations.run_migrations(db)
    assert migrations.get_current_version(db) == SCHEMA_VERSION + 1

    # Operator fixes the cause; re-run resumes from the failed step only.
    state["broken"] = False
    assert migrations.run_migrations(db) == [SCHEMA_VERSION + 2]
    assert migrations.get_current_version(db) == SCHEMA_VERSION + 2


def test_none_target_noops_when_db_ahead_of_registry(db, clean_registry):
    # A newer build stamped the DB past what THIS build's registry knows (a
    # code rollback). target=None means "bring to latest" — a DB already
    # ahead is a no-op, never the backward error (which is reserved for an
    # EXPLICIT lower target). Without this, a downgraded keeper wired into
    # store-open would fail to open every db a newer keeper had migrated.
    @migrations.register_migration(SCHEMA_VERSION + 1, "known to this build")
    def _m(conn):
        conn.execute("CREATE TABLE known (id INTEGER)")

    db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
               (str(SCHEMA_VERSION + 5),))
    db.commit()

    assert migrations.run_migrations(db) == []                       # None: no-op
    assert migrations.get_current_version(db) == SCHEMA_VERSION + 5   # untouched


def test_backward_target_raises(db, clean_registry):
    with pytest.raises(ValueError, match="forward-only"):
        migrations.run_migrations(db, target_version=SCHEMA_VERSION - 1)


def test_unreachable_target_raises(db, clean_registry):
    # Caller asks for a version bump whose migration was never registered.
    with pytest.raises(ValueError, match="missing its migration"):
        migrations.run_migrations(db, target_version=SCHEMA_VERSION + 1)


def test_open_transaction_refused(db, clean_registry):
    db.execute("INSERT INTO meta (key, value) VALUES ('probe', 'x')")  # opens a tx
    assert db.in_transaction
    with pytest.raises(RuntimeError, match="open transaction"):
        migrations.run_migrations(db)


# ── registry listing ──

def test_list_migrations_sorted(clean_registry):
    migrations.register_migration(6, "six")(lambda c: None)
    migrations.register_migration(4, "four")(lambda c: None)
    migrations.register_migration(5, "five")(lambda c: None)

    listed = migrations.list_migrations()
    assert [m["version"] for m in listed] == [4, 5, 6]
    assert listed[0]["description"] == "four"
