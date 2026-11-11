"""The sync engine's own tables and their version.

The tables are created here, not only by a numbered migration of the host's ledger, so the engine works in a host whose
migrations know nothing about sync (Ankrimento ships it beside an older vendored Incremento) and cannot collide with
migration numbers upstream assigns later. Upstream's migration runs this same script, so both paths give the same
tables. Every statement is ``IF NOT EXISTS``: running it again changes nothing.

The engine's own version is the ``schema`` row of ``sync_meta``. A database written by a newer engine is refused rather
than used with older code.
"""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

SYNC_TABLES = (
    "sync_meta", "sync_revisions", "sync_baseline", "sync_outbox", "sync_inbox", "sync_receipts", "sync_peers",
    "sync_seen_packs", "sync_conflicts",
)

SYNC_SCHEMA = """
        CREATE TABLE IF NOT EXISTS sync_meta (
            key TEXT PRIMARY KEY CHECK(length(key) BETWEEN 1 AND 64),
            value TEXT NOT NULL CHECK(length(value) <= 4096)
        );
        CREATE TABLE IF NOT EXISTS sync_revisions (
            id TEXT PRIMARY KEY CHECK(length(id) = 64),
            family TEXT NOT NULL CHECK(length(family) BETWEEN 1 AND 64),
            key TEXT NOT NULL CHECK(length(key) BETWEEN 1 AND 512),
            parents TEXT NOT NULL DEFAULT '[]',
            device TEXT NOT NULL CHECK(length(device) BETWEEN 1 AND 64),
            epoch INTEGER NOT NULL CHECK(epoch >= 1),
            seq INTEGER NOT NULL CHECK(seq >= 0),
            deleted INTEGER NOT NULL CHECK(deleted IN (0, 1)),
            value TEXT,
            deps TEXT NOT NULL DEFAULT '{}',
            format INTEGER NOT NULL CHECK(format >= 1),
            created_at INTEGER NOT NULL,
            CHECK((deleted = 1) = (value IS NULL)),
            -- Deterministic merges of equal values (device '~merge', seq 0) are
            -- computed identically on every device and never published.
            CHECK((device = '~merge') = (seq = 0))
        );
        CREATE UNIQUE INDEX IF NOT EXISTS sync_revisions_by_device_seq ON sync_revisions(device, epoch, seq)
            WHERE device <> '~merge';
        CREATE INDEX IF NOT EXISTS sync_revisions_by_record ON sync_revisions(family, key);
        -- The unique index above is partial, so plain lookups by position cannot use it.
        CREATE INDEX IF NOT EXISTS sync_revisions_by_position ON sync_revisions(device, epoch, seq);
        CREATE TABLE IF NOT EXISTS sync_baseline (
            family TEXT NOT NULL,
            key TEXT NOT NULL,
            revision_id TEXT NOT NULL REFERENCES sync_revisions(id),
            value_hash TEXT NOT NULL,
            PRIMARY KEY(family, key)
        );
        CREATE TABLE IF NOT EXISTS sync_outbox (
            revision_id TEXT PRIMARY KEY REFERENCES sync_revisions(id),
            enqueued_at INTEGER NOT NULL,
            published_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS sync_inbox (
            revision_id TEXT PRIMARY KEY CHECK(length(revision_id) BETWEEN 1 AND 64),
            status TEXT NOT NULL CHECK(status IN ('received', 'pending_parent', 'pending_blob', 'pending_anki', 'applied',
                                                  'conflict', 'obsolete', 'rejected')),
            reason TEXT NOT NULL DEFAULT '' CHECK(length(reason) <= 500),
            received_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        -- Waiting revisions are found by status among everything ever received.
        CREATE INDEX IF NOT EXISTS sync_inbox_by_status ON sync_inbox(status);
        CREATE TABLE IF NOT EXISTS sync_receipts (
            peer TEXT NOT NULL CHECK(length(peer) BETWEEN 1 AND 64),
            epoch INTEGER NOT NULL CHECK(epoch >= 1),
            max_seq INTEGER NOT NULL CHECK(max_seq >= 0),
            PRIMARY KEY(peer, epoch)
        );
        CREATE TABLE IF NOT EXISTS sync_peers (
            device TEXT PRIMARY KEY CHECK(length(device) BETWEEN 1 AND 64),
            anki_usn INTEGER CHECK(anki_usn >= 0),
            anki_scm INTEGER CHECK(anki_scm >= 0),
            seen_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sync_seen_packs (
            device TEXT NOT NULL CHECK(length(device) BETWEEN 1 AND 64),
            name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 128),
            outcome TEXT NOT NULL CHECK(outcome IN ('accepted', 'rejected')),
            format INTEGER NOT NULL,
            seen_at INTEGER NOT NULL,
            PRIMARY KEY(device, name)
        );
        CREATE TABLE IF NOT EXISTS sync_conflicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            family TEXT NOT NULL,
            key TEXT NOT NULL,
            heads TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            resolved_revision TEXT REFERENCES sync_revisions(id)
        );
    
""" + f"""
        INSERT OR IGNORE INTO sync_meta(key, value) VALUES ('schema', '{SCHEMA_VERSION}');
"""


class SyncSchemaError(RuntimeError):
    """The database's sync tables cannot be used by this engine."""


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the sync tables if they are missing; refuse a database from a newer engine."""
    present = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if set(SYNC_TABLES) <= present:
        _check_version(conn)
        return
    if conn.in_transaction:
        raise RuntimeError("sync schema setup started with an active transaction")
    conn.executescript("BEGIN IMMEDIATE;\n" + SYNC_SCHEMA + "\nCOMMIT;")
    _check_version(conn)


def _check_version(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT value FROM sync_meta WHERE key='schema'").fetchone()
    version = int(row[0]) if row and row[0].isdigit() else 0
    if version > SCHEMA_VERSION:
        raise SyncSchemaError(f"The sync data was written by a newer version of the engine (schema {version}).")
    if row is None:  # tables made by upstream's migration 25 before the row existed
        with conn:
            conn.execute("INSERT OR IGNORE INTO sync_meta(key, value) VALUES ('schema', ?)", (str(SCHEMA_VERSION),))
