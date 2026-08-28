"""Durable journal for imports spanning Anki, SQLite and profile files."""

from __future__ import annotations

import json
import shutil
import sqlite3
import time
import uuid
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

try:
    from .db import get_connection
    from .paths import get_db_path, get_user_files_dir
except ImportError:
    from db import get_connection  # type: ignore
    from paths import get_db_path, get_user_files_dir  # type: ignore


_FINAL_STATES = {"committed", "rolled_back", "failed_cleanup"}


def _normalized_relpath(value: str) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("Import journal paths must stay inside the profile directory.")
    return "/".join(path.parts)


def _decode_relpaths(raw: str) -> list[str]:
    try:
        values = json.loads(str(raw or "[]"))
    except Exception:
        values = []
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for value in values:
        try:
            relpath = _normalized_relpath(str(value or ""))
        except ValueError:
            continue
        if relpath not in normalized:
            normalized.append(relpath)
    return normalized


def _remove_created_path(profile_root: Path, relpath: str) -> bool:
    root = profile_root.resolve()
    candidate = root / _normalized_relpath(relpath)
    try:
        candidate.parent.resolve().relative_to(root)
    except ValueError:
        return False
    if not candidate.exists() and not candidate.is_symlink():
        return True
    try:
        # Never follow a replacement symlink while compensating an import.
        # Only the symlink itself was created at the journalled path.
        if candidate.is_symlink():
            candidate.unlink()
        elif candidate.is_dir():
            shutil.rmtree(candidate)
        else:
            candidate.unlink()
        return True
    except OSError:
        return False


def _remove_created_paths(profile_root: Path, relpaths: list[str]) -> bool:
    cleanup_ok = True
    for relpath in reversed(relpaths):
        if not _remove_created_path(profile_root, relpath):
            cleanup_ok = False
    return cleanup_ok


class ImportOperation:
    """Track one new content import and compensate before a card exists."""

    def __init__(self, addon_dir: str, profile: str, operation_kind: str) -> None:
        self.addon_dir = str(addon_dir)
        self.profile = str(profile)
        self.operation_kind = str(operation_kind or "unknown").strip().lower() or "unknown"
        self.operation_id = uuid.uuid4().hex
        self.content_id = uuid.uuid4().hex
        self.card_id: int | None = None
        self.note_id: int | None = None
        self._relpaths: list[str] = []
        self._finished = False
        now = int(time.time())
        conn = get_connection(self.addon_dir, self.profile)
        with conn:
            conn.execute(
                "INSERT INTO import_journal("
                "operation_id, content_id, operation_kind, state, created_at, updated_at"
                ") VALUES (?, ?, ?, 'pending', ?, ?)",
                (self.operation_id, self.content_id, self.operation_kind, now, now),
            )

    def _persist(self, *, state: str = "pending", error_code: str = "") -> None:
        conn = get_connection(self.addon_dir, self.profile)
        with conn:
            conn.execute(
                "UPDATE import_journal SET state=?, card_id=?, note_id=?, "
                "created_relpaths=?, error_code=?, updated_at=? WHERE operation_id=?",
                (
                    str(state),
                    self.card_id,
                    self.note_id,
                    json.dumps(self._relpaths, ensure_ascii=False),
                    str(error_code or "")[:120],
                    int(time.time()),
                    self.operation_id,
                ),
            )

    def track_created_relpath(self, relpath: str) -> None:
        normalized = _normalized_relpath(relpath)
        if normalized not in self._relpaths:
            self._relpaths.append(normalized)
            self._persist()

    def bind_anki(self, *, card_id: int, note_id: int | None = None) -> None:
        self.card_id = int(card_id)
        self.note_id = int(note_id) if note_id not in (None, 0) else None
        self._persist()

    def commit(self, *, storage_key: str = "") -> None:
        if self.card_id is None:
            raise RuntimeError("Cannot commit an import before its Anki card exists.")
        conn = get_connection(self.addon_dir, self.profile)
        now = int(time.time())
        with conn:
            conn.execute(
                "DELETE FROM content_items "
                "WHERE kind=? AND card_id=? AND content_id!=?",
                (self.operation_kind, self.card_id, self.content_id),
            )
            conn.execute(
                "INSERT INTO content_items("
                "content_id, kind, card_id, note_id, storage_key, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(content_id) DO UPDATE SET "
                "kind=excluded.kind, card_id=excluded.card_id, note_id=excluded.note_id, "
                "storage_key=excluded.storage_key, updated_at=excluded.updated_at",
                (
                    self.content_id,
                    self.operation_kind,
                    self.card_id,
                    self.note_id,
                    str(storage_key or ""),
                    now,
                    now,
                ),
            )
            conn.execute(
                "UPDATE import_journal SET state='committed', card_id=?, note_id=?, "
                "created_relpaths=?, error_code='', updated_at=? WHERE operation_id=?",
                (
                    self.card_id,
                    self.note_id,
                    json.dumps(self._relpaths, ensure_ascii=False),
                    now,
                    self.operation_id,
                ),
            )
        self._finished = True

    def rollback(self, *, error_code: str = "incomplete") -> None:
        if self._finished:
            return
        # Once an Anki card exists the user data is not an orphan. Preserve it
        # and make the journal recoverable instead of deleting its source file.
        if self.card_id is not None:
            self._persist(state="pending", error_code=error_code)
            self._finished = True
            return
        root = get_user_files_dir(self.addon_dir, self.profile)
        cleanup_ok = _remove_created_paths(root, self._relpaths)
        self._persist(
            state="rolled_back" if cleanup_ok else "failed_cleanup",
            error_code=error_code,
        )
        self._finished = True

    def __enter__(self) -> "ImportOperation":
        return self

    def __exit__(self, exc_type, exc, _traceback) -> bool:
        if not self._finished:
            code = exc_type.__name__ if exc_type is not None else "incomplete"
            self.rollback(error_code=code)
        return False


def recover_interrupted_imports(
    addon_dir: str,
    profile: str,
    *,
    live_card_ids: set[int],
    content_matches: Mapping[str, tuple[int, int | None]] | None = None,
) -> dict[str, int]:
    """Resolve journal rows left pending by a previous process interruption."""
    conn = get_connection(addon_dir, profile)
    rows = conn.execute(
        "SELECT operation_id, content_id, operation_kind, card_id, note_id, "
        "created_relpaths FROM import_journal WHERE state='pending'"
    ).fetchall()
    recovered = 0
    rolled_back = 0
    failed_cleanup = 0
    root = get_user_files_dir(addon_dir, profile)
    matches = dict(content_matches or {})

    for operation_id, content_id, kind, card_id, note_id, relpaths_json in rows:
        normalized_card_id = int(card_id or 0)
        normalized_note_id = int(note_id) if note_id not in (None, 0) else None
        matched = matches.get(str(content_id or ""))
        if matched is not None:
            matched_card_id = int(matched[0] or 0)
            if matched_card_id in live_card_ids:
                normalized_card_id = matched_card_id
                normalized_note_id = (
                    int(matched[1]) if matched[1] not in (None, 0) else None
                )
        relpaths = _decode_relpaths(relpaths_json)
        now = int(time.time())
        if normalized_card_id > 0 and normalized_card_id in live_card_ids:
            with conn:
                conn.execute(
                    "DELETE FROM content_items "
                    "WHERE kind=? AND card_id=? AND content_id!=?",
                    (
                        str(kind or "unknown"),
                        normalized_card_id,
                        str(content_id or operation_id),
                    ),
                )
                conn.execute(
                    "INSERT INTO content_items("
                    "content_id, kind, card_id, note_id, storage_key, created_at, updated_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(content_id) DO UPDATE SET "
                    "kind=excluded.kind, card_id=excluded.card_id, "
                    "note_id=excluded.note_id, storage_key=excluded.storage_key, "
                    "updated_at=excluded.updated_at",
                    (
                        str(content_id or operation_id),
                        str(kind or "unknown"),
                        normalized_card_id,
                        normalized_note_id,
                        relpaths[0] if relpaths else "",
                        now,
                        now,
                    ),
                )
                conn.execute(
                    "UPDATE import_journal SET state='committed', card_id=?, note_id=?, "
                    "error_code='', updated_at=? WHERE operation_id=?",
                    (normalized_card_id, normalized_note_id, now, operation_id),
                )
            recovered += 1
            continue

        cleanup_ok = _remove_created_paths(root, relpaths)
        state = "rolled_back" if cleanup_ok else "failed_cleanup"
        with conn:
            conn.execute(
                "UPDATE import_journal SET state=?, updated_at=? WHERE operation_id=?",
                (state, now, operation_id),
            )
        if cleanup_ok:
            rolled_back += 1
        else:
            failed_cleanup += 1

    return {
        "recovered": recovered,
        "rolled_back": rolled_back,
        "failed_cleanup": failed_cleanup,
    }


def pending_import_content_ids(addon_dir: str, profile: str) -> set[str]:
    """Return stable identities that still need cross-store reconciliation."""
    rows = get_connection(addon_dir, profile).execute(
        "SELECT content_id FROM import_journal WHERE state='pending'"
    ).fetchall()
    return {
        str(row[0] or "").strip()
        for row in rows
        if row and str(row[0] or "").strip()
    }


def pending_import_recovery_needed(addon_dir: str, profile: str) -> bool:
    """Check for pending journal work without creating or migrating the DB.

    Profile-open hooks use this bounded read-only preflight before scheduling
    any Anki collection operation. A missing/legacy database has no import
    journal to recover, and a temporarily unreadable database is left for the
    next profile open instead of delaying the deck screen.
    """
    db_path = get_db_path(addon_dir, profile)
    if not db_path.is_file():
        return False
    connection = None
    try:
        connection = sqlite3.connect(
            f"{db_path.resolve().as_uri()}?mode=ro",
            uri=True,
            timeout=0.05,
        )
        connection.execute("PRAGMA query_only=ON")
        journal_exists = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='import_journal' LIMIT 1"
        ).fetchone()
        if journal_exists is None:
            return False
        return connection.execute(
            "SELECT 1 FROM import_journal WHERE state='pending' LIMIT 1"
        ).fetchone() is not None
    except (OSError, ValueError, sqlite3.Error):
        return False
    finally:
        if connection is not None:
            connection.close()


def pending_import_descriptors(addon_dir: str, profile: str) -> tuple[dict, ...]:
    """Return the minimum non-content data needed to recover pending imports."""
    rows = get_connection(addon_dir, profile).execute(
        "SELECT content_id, operation_kind, card_id, note_id, created_relpaths "
        "FROM import_journal WHERE state='pending'"
    ).fetchall()
    descriptors: list[dict] = []
    for content_id, operation_kind, card_id, note_id, relpaths_json in rows:
        normalized_content_id = str(content_id or "").strip()
        if not normalized_content_id:
            continue
        descriptors.append(
            {
                "content_id": normalized_content_id,
                "kind": str(operation_kind or "unknown").strip().lower() or "unknown",
                "card_id": int(card_id) if card_id not in (None, 0) else None,
                "note_id": int(note_id) if note_id not in (None, 0) else None,
                "relpaths": tuple(_decode_relpaths(relpaths_json)),
            }
        )
    return tuple(descriptors)


def prune_finished_journal(
    addon_dir: str,
    profile: str,
    *,
    older_than: int,
) -> int:
    conn = get_connection(addon_dir, profile)
    with conn:
        cursor = conn.execute(
            "DELETE FROM import_journal WHERE state IN (?, ?, ?) AND updated_at < ?",
            (*sorted(_FINAL_STATES), int(older_than)),
        )
    return max(0, int(cursor.rowcount or 0))
