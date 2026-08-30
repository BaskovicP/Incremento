import sqlite3

import pytest

import db_schema
from db_schema import DatabaseSchemaTooNewError, initialize_schema


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


def test_future_database_version_fails_before_any_schema_write():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA user_version=99")

    with pytest.raises(DatabaseSchemaTooNewError, match="newer Incremento version"):
        initialize_schema(
            conn,
            bootstrap=lambda _conn: (_ for _ in ()).throw(AssertionError("bootstrap")),
            migrations=[(2, "second", lambda _conn: None)],
        )

    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "schema_migrations" not in tables


@pytest.mark.parametrize(
    "migrations",
    [
        [(2, "one", lambda _conn: None), (2, "duplicate", lambda _conn: None)],
        [(3, "gap", lambda _conn: None)],
        [(1, "reserved-baseline", lambda _conn: None)],
    ],
)
def test_invalid_migration_ledger_definitions_fail_closed(migrations):
    conn = sqlite3.connect(":memory:")
    with pytest.raises(ValueError):
        initialize_schema(conn, bootstrap=lambda _conn: None, migrations=migrations)


def test_statistics_history_migration_rolls_back_all_new_tables_on_failure():
    import db

    conn = sqlite3.connect(":memory:")

    def bootstrap(connection: sqlite3.Connection) -> None:
        connection.execute(
            "CREATE TABLE stats(scope TEXT PRIMARY KEY, date TEXT, data TEXT NOT NULL)"
        )

    def failing_statistics_migration(connection: sqlite3.Connection) -> None:
        db._migration_6_statistics_history(connection)
        raise RuntimeError("simulated statistics migration interruption")

    migrations = [
        (2, "noop_2", lambda _conn: None),
        (3, "noop_3", lambda _conn: None),
        (4, "noop_4", lambda _conn: None),
        (5, "noop_5", lambda _conn: None),
        (6, "statistics_history", failing_statistics_migration),
    ]

    with pytest.raises(RuntimeError, match="interruption"):
        initialize_schema(conn, bootstrap=bootstrap, migrations=migrations)

    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "stats_daily_history" not in tables
    assert "reading_page_history" not in tables
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 5


def test_statistics_history_schema_rejects_invalid_rows(tmp_path):
    import db

    db.close_connection()
    conn = db.get_connection(str(tmp_path), "TestProfile")
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO reading_page_history "
                "(logical_date, document_type, card_id, page_number, recorded_at) "
                "VALUES ('2026-04-23', 'web', 1, 1, 0)"
            )
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO reading_page_history "
                "(logical_date, document_type, card_id, page_number, recorded_at) "
                "VALUES ('2026-04-23', 'pdf', 1, 0, 0)"
            )
    finally:
        conn.rollback()
        db.close_connection()
