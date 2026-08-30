"""Versioned schema migration runner for Incremento's profile database."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable, Iterable


Migration = tuple[int, str, Callable[[sqlite3.Connection], None]]


class DatabaseSchemaTooNewError(RuntimeError):
    """The database was created by a newer, incompatible Incremento release."""


def _current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return max(0, int(row[0] or 0)) if row else 0


def _ensure_ledger(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY, "
        "name TEXT NOT NULL, "
        "applied_at INTEGER NOT NULL)"
    )
    conn.commit()


def initialize_schema(
    conn: sqlite3.Connection,
    *,
    bootstrap: Callable[[sqlite3.Connection], None],
    migrations: Iterable[Migration],
) -> int:
    """Bring a new or legacy DB to the latest explicit schema version.

    Version zero represents every Incremento database shipped before the
    migration ledger.  ``bootstrap`` contains the old idempotent schema setup,
    so it upgrades every historical shape once before the ledger takes over.
    """
    ordered = sorted(migrations, key=lambda item: item[0])
    targets = [int(item[0]) for item in ordered]
    if any(target < 2 for target in targets) or len(targets) != len(set(targets)):
        raise ValueError("Schema migration versions must be unique integers starting at 2.")
    if targets and targets != list(range(2, targets[-1] + 1)):
        raise ValueError("Schema migration versions must be contiguous.")

    latest_supported = targets[-1] if targets else 1
    version = _current_version(conn)
    if version > latest_supported:
        raise DatabaseSchemaTooNewError(
            "This profile database was created by a newer Incremento version "
            f"(database {version}, supported through {latest_supported}). "
            "Update Incremento before opening this profile."
        )

    # Do not write even the ledger until the compatibility check above passes.
    _ensure_ledger(conn)

    if version == 0:
        bootstrap(conn)
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO schema_migrations(version, name, applied_at) "
                "VALUES (1, 'legacy_schema_baseline', ?)",
                (int(time.time()),),
            )
            conn.execute("PRAGMA user_version=1")
        version = 1

    for target, name, migration in ordered:
        if int(target) <= version:
            continue
        # Python's sqlite3 context commits all migration statements together
        # unless the migration itself uses a SQLite operation that requires an
        # implicit boundary (none of Incremento's post-ledger migrations do).
        with conn:
            migration(conn)
            conn.execute(
                "INSERT INTO schema_migrations(version, name, applied_at) "
                "VALUES (?, ?, ?)",
                (int(target), str(name), int(time.time())),
            )
            conn.execute(f"PRAGMA user_version={int(target)}")
        version = int(target)

    return version
