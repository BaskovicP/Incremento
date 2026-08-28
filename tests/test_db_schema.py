import sqlite3

import pytest

import db_schema


def _bootstrap(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE baseline(id INTEGER PRIMARY KEY)")


def test_failed_migration_rolls_back_schema_ledger_and_user_version():
    conn = sqlite3.connect(":memory:")
    try:
        assert db_schema.initialize_schema(
            conn,
            bootstrap=_bootstrap,
            migrations=(),
        ) == 1

        def failing_migration(connection: sqlite3.Connection) -> None:
            # Match Incremento's executescript-based DDL migration convention.
            connection.executescript(
                "BEGIN IMMEDIATE; CREATE TABLE should_rollback(value TEXT);"
            )
            raise RuntimeError("simulated migration interruption")

        with pytest.raises(RuntimeError, match="interruption"):
            db_schema.initialize_schema(
                conn,
                bootstrap=_bootstrap,
                migrations=((2, "failing", failing_migration),),
            )

        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        assert conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1,)]
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='should_rollback'"
        ).fetchone() is None
    finally:
        conn.close()


def test_successful_migration_is_recorded_once():
    conn = sqlite3.connect(":memory:")
    try:
        def add_table(connection: sqlite3.Connection) -> None:
            connection.execute("CREATE TABLE added(value TEXT)")

        migrations = ((2, "add_table", add_table),)
        assert db_schema.initialize_schema(
            conn,
            bootstrap=_bootstrap,
            migrations=migrations,
        ) == 2
        assert db_schema.initialize_schema(
            conn,
            bootstrap=_bootstrap,
            migrations=migrations,
        ) == 2
        assert conn.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1, "legacy_schema_baseline"), (2, "add_table")]
    finally:
        conn.close()
