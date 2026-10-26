"""Bounded startup preflight and worker-only preparation of profile storage."""

import sqlite3
import time

try:
    from . import db, migration
    from .paths import get_db_path
except ImportError:
    import db
    import migration
    from paths import get_db_path


def storage_preparation_needed(addon_dir: str, profile: str) -> bool:
    """Inspect only fixed paths and the schema version, without creating a DB."""
    if migration.profile_migration_needed(addon_dir, profile):
        return True
    path = get_db_path(addon_dir, profile)
    if not path.is_file():
        return True
    try:
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.05)
        try:
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        finally:
            conn.close()
    except (OSError, sqlite3.Error):
        # Lock contention, corruption and future schemas belong in the visible
        # worker path, where errors are propagated rather than hidden.
        return True
    return version != db._SCHEMA_MIGRATIONS[-1][0]


def prepare_storage(addon_dir: str, profile: str, *, progress=lambda _stage: None) -> dict[str, int]:
    """Prepare only the captured profile; never access Anki or share a handle."""
    started = time.monotonic()
    progress("files")
    migration.migrate_to_profile_dir(addon_dir, profile)
    files_finished = time.monotonic()
    progress("database")
    try:
        db.get_connection(addon_dir, profile)
    finally:
        db.close_current_connection(addon_dir, profile)
    finished = time.monotonic()
    return {
        "files_ms": max(0, round((files_finished - started) * 1000)),
        "database_ms": max(0, round((finished - files_finished) * 1000)),
    }
