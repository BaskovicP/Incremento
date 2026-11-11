"""The sync tables can be created by the engine itself (design note section 8: companion mode).

Ankrimento ships the engine beside an older vendored Incremento whose migration ledger knows nothing about sync, and
upstream may later number its migrations differently. The engine therefore owns its tables and their version.
"""
import sqlite3

import pytest

import db
import sync_schema
import sync_service
from sync_schema import SYNC_TABLES, SyncSchemaError, ensure_schema

CARDS = None  # no collection check is needed here


def _shape(conn):
    """Tables, columns and indexes of the sync tables, independent of how they were created."""
    shape = {}
    for table in SYNC_TABLES:
        columns = [tuple(row[1:6]) for row in conn.execute(f"PRAGMA table_info({table})")]
        indexes = sorted(
            (row[1], row[2], row[4], tuple(info[2] for info in conn.execute(f"PRAGMA index_info({row[1]})")))
            for row in conn.execute(f"PRAGMA index_list({table})") if not row[1].startswith("sqlite_autoindex"))
        shape[table] = (columns, indexes)
    return shape


@pytest.fixture(autouse=True)
def _fresh():
    db.close_connection()
    yield
    db.close_connection()


def test_ensure_schema_creates_every_sync_table_in_a_plain_database():
    conn = sqlite3.connect(":memory:")

    ensure_schema(conn)

    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert set(SYNC_TABLES) <= names
    assert conn.execute("SELECT value FROM sync_meta WHERE key='schema'").fetchone() == (str(sync_schema.SCHEMA_VERSION),)


def test_ensure_schema_is_idempotent_and_keeps_data():
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn)
    conn.execute("INSERT INTO sync_meta(key, value) VALUES ('library_id', 'abc')")
    conn.commit()

    ensure_schema(conn)
    ensure_schema(conn)

    assert conn.execute("SELECT value FROM sync_meta WHERE key='library_id'").fetchone() == ("abc",)
    assert conn.execute("SELECT count(*) FROM sync_meta WHERE key='schema'").fetchone() == (1,)


def test_the_engines_schema_equals_the_one_upstreams_migration_creates(tmp_path):
    migrated = db.get_connection(str(tmp_path / "addon"), "P")
    plain = sqlite3.connect(":memory:")

    ensure_schema(plain)

    assert _shape(plain) == _shape(migrated)


def test_a_database_from_a_newer_engine_is_refused_not_downgraded():
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn)
    conn.execute("UPDATE sync_meta SET value=? WHERE key='schema'", (str(sync_schema.SCHEMA_VERSION + 1),))
    conn.commit()

    with pytest.raises(SyncSchemaError, match="newer"):
        ensure_schema(conn)


def test_ensure_schema_does_not_leave_a_transaction_open():
    conn = sqlite3.connect(":memory:")

    ensure_schema(conn)

    assert not conn.in_transaction


def test_the_service_creates_the_tables_when_the_hosts_migrations_did_not(tmp_path):
    addon = str(tmp_path / "addon")
    conn = db.get_connection(addon, "P")
    for table in reversed(SYNC_TABLES):  # an older host: its ledger never heard of sync
        conn.execute(f"DROP TABLE {table}")
    conn.commit()
    folder = tmp_path / "Cloud"
    folder.mkdir()

    result = sync_service.configure(addon, "P", str(folder))
    report = sync_service.sync_now(addon, "P", _collection())

    assert result.created and report.problems == []
    assert sync_service.status(addon, "P").configured


def _collection():
    col = sqlite3.connect(":memory:", check_same_thread=False)
    col.execute("CREATE TABLE col (usn INTEGER, scm INTEGER, mod INTEGER DEFAULT 1)")
    col.execute("INSERT INTO col(usn, scm) VALUES (20, 1000)")
    col.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, guid TEXT)")
    col.execute("CREATE TABLE cards (id INTEGER PRIMARY KEY, nid INTEGER, usn INTEGER)")
    return lambda sql, *args: col.execute(sql, args).fetchall()
