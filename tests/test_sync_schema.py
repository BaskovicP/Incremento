"""Schema contract for shared-folder sync (docs/architecture/shared-folder-sync.md §2, §4)."""

import sqlite3

import pytest

import db
import sync_records
from db_schema import initialize_schema


_SYNC_TABLES = {
    "sync_meta", "sync_revisions", "sync_baseline", "sync_outbox",
    "sync_inbox", "sync_receipts", "sync_conflicts", "sync_peers", "sync_seen_packs",
}


def _latest(conn):
    return initialize_schema(conn, bootstrap=db._create_tables, migrations=db._SCHEMA_MIGRATIONS)


def _tables(conn):
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_latest_schema_creates_every_sync_table():
    conn = sqlite3.connect(":memory:")

    assert _latest(conn) == 27
    assert _SYNC_TABLES <= _tables(conn)
    conn.close()


def test_sync_foundations_migration_rolls_back_tables_and_ledger():
    conn = sqlite3.connect(":memory:")
    previous = tuple(m for m in db._SCHEMA_MIGRATIONS if m[0] <= 26)
    initialize_schema(conn, bootstrap=db._create_tables, migrations=previous)

    def interrupted(connection):
        db._migration_27_sync_foundations(connection)
        raise RuntimeError("sync migration interrupted")

    with pytest.raises(RuntimeError, match="interrupted"):
        initialize_schema(conn, bootstrap=db._create_tables,
                          migrations=previous + ((27, "sync_foundations", interrupted),))

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 26
    assert conn.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 26
    assert not (_SYNC_TABLES & _tables(conn))
    conn.close()


@pytest.mark.parametrize("status", ["received", "pending_parent", "pending_blob", "pending_anki", "applied",
                                    "conflict", "obsolete", "rejected"])
def test_inbox_accepts_each_documented_status(status):
    conn = sqlite3.connect(":memory:")
    _latest(conn)

    conn.execute("INSERT INTO sync_inbox(revision_id, status, reason, received_at, updated_at) "
                 "VALUES ('a' || ?, ?, '', 1, 1)", (status, status))

    assert conn.execute("SELECT status FROM sync_inbox").fetchone() == (status,)
    conn.close()


@pytest.mark.parametrize("statement,violated", [
    ("INSERT INTO sync_inbox(revision_id, status, reason, received_at, updated_at) VALUES ('x', 'done', '', 1, 1)", "status IN"),
    ("INSERT INTO sync_revisions(id, family, key, parents, device, epoch, seq, deleted, value, deps, format, created_at)"
     " VALUES (printf('%064d', 1), 'priority', 'card:1', '[]', 'd', 1, 1, 1, '{\"priority\": 1}', '{}', 1, 1)", "deleted = 1"),
    ("INSERT INTO sync_revisions(id, family, key, parents, device, epoch, seq, deleted, value, deps, format, created_at)"
     " VALUES (printf('%064d', 1), 'priority', 'card:1', '[]', 'd', 1, 1, 0, NULL, '{}', 1, 1)", "deleted = 1"),
    ("INSERT INTO sync_outbox(revision_id, enqueued_at) VALUES ('missing', 1)", "FOREIGN KEY"),
], ids=["unknown-inbox-status", "tombstone-with-value", "live-without-value", "outbox-without-revision"])
def test_sync_tables_reject_inconsistent_rows(statement, violated):
    conn = sqlite3.connect(":memory:")
    _latest(conn)
    conn.execute("PRAGMA foreign_keys=ON")

    with pytest.raises(sqlite3.IntegrityError, match=violated):
        conn.execute(statement)
    conn.close()


def test_one_device_cannot_reuse_a_sequence_number_within_an_epoch():
    conn = sqlite3.connect(":memory:")
    _latest(conn)
    row = ("priority", "card:1", "[]", "dev", 1, 7, 0, '{"priority": 1.0}', "{}", 1, 1)
    conn.execute("INSERT INTO sync_revisions(id, family, key, parents, device, epoch, seq, deleted, value, deps, "
                 "format, created_at) VALUES (printf('%064d', 1), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", row)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO sync_revisions(id, family, key, parents, device, epoch, seq, deleted, value, deps, "
                     "format, created_at) VALUES (printf('%064d', 2), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", row)
    conn.close()


def test_every_table_and_every_column_of_a_synced_table_is_classified():
    """A new table or column must be classified before it can enter or stay out of the exchange."""
    conn = sqlite3.connect(":memory:")
    _latest(conn)
    unclassified = []
    for table in sorted(_tables(conn)):
        kind = sync_records.table_classification(table)
        if kind is None:
            unclassified.append(table)
            continue
        if kind == "synced":
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            known = sync_records.SYNCED_COLUMNS[table] | sync_records.LOCAL_COLUMNS.get(table, frozenset())
            unclassified += [f"{table}.{column}" for column in sorted(columns - known)]
            unclassified += [f"{table}.{column} (gone)" for column in sorted(known - columns)]
    conn.close()

    assert unclassified == []


def test_classification_uses_only_the_three_documented_kinds():
    assert set(sync_records.TABLE_CLASSIFICATION.values()) <= {"synced", "local", "later"}
    assert set(sync_records.SYNCED_COLUMNS) == {
        table for table, kind in sync_records.TABLE_CLASSIFICATION.items() if kind == "synced"
    }


@pytest.mark.parametrize("query", [
    "SELECT 1 FROM sync_revisions r JOIN sync_inbox i ON i.revision_id = r.id "
    "WHERE r.device=? AND r.epoch=? AND r.seq=?",
    "SELECT count(DISTINCT seq) FROM sync_revisions WHERE device=? AND seq>? AND seq<=?",
    "SELECT max(r.seq) FROM sync_revisions r JOIN sync_outbox o ON o.revision_id = r.id "
    "WHERE r.device=? AND r.epoch=? AND o.published_at IS NOT NULL",
    "SELECT i.revision_id FROM sync_inbox i JOIN sync_revisions r ON r.id = i.revision_id "
    "WHERE i.status IN ('received', 'pending_anki') ORDER BY r.device, r.epoch, r.seq",
], ids=["receipt", "history-complete", "published-through", "waiting-in-inbox"])
def test_lookups_by_device_and_sequence_use_an_index(query):
    """A full scan per received revision made a large first sync quadratic."""
    conn = sqlite3.connect(":memory:")
    _latest(conn)

    plan = " ".join(row[-1] for row in conn.execute("EXPLAIN QUERY PLAN " + query, ("d", 1, 1)[:query.count("?")]))

    assert "SCAN r" not in plan and "SCAN sync_revisions" not in plan and "SCAN i" not in plan, plan
    conn.close()
