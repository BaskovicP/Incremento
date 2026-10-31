"""Profile-local book lists and acquisition notes, shared by document identity."""

from __future__ import annotations

import sqlite3
import unicodedata
from collections.abc import Mapping
from concurrent.futures import CancelledError

try:
    from .db import get_connection
except ImportError:
    from db import get_connection


MAX_LIST_NAME = 80
MAX_REASON = 2000
MAX_SOURCE = 500
MAX_BOOK_LISTS = 64
MAX_LISTS = 500


def _text(value, limit: int, *, multiline: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError("Invalid document library text.")
    if any(ord(c) < 32 and (not multiline or c not in "\n\r\t") for c in value):
        raise ValueError("Invalid document library text.")
    return value.strip()


def normalize_document_details(value) -> dict:
    if not isinstance(value, Mapping):
        raise ValueError("Invalid book details.")
    ids = value.get("list_ids", [])
    if not isinstance(ids, (list, tuple)) or len(ids) > MAX_BOOK_LISTS:
        raise ValueError("Too many book lists.")
    if any(type(i) is not int or i <= 0 or i > 2**63 - 1 for i in ids):
        raise ValueError("Invalid book list.")
    return {"reason": _text(value.get("reason", ""), MAX_REASON, multiline=True),
            "source": _text(value.get("source", ""), MAX_SOURCE),
            "list_ids": sorted(set(ids))}


def document_key(kind: str, filename: str) -> tuple[str, str]:
    kind = str(kind).lower()
    if kind not in {"pdf", "epub"} or not isinstance(filename, str):
        raise ValueError("Invalid book identity.")
    filename = filename.removeprefix(kind + "s/")
    if (not filename or len(filename) > 500 or filename in {".", ".."}
            or any(c in filename for c in "/\\\x00")
            or any(ord(c) < 32 for c in filename)):
        raise ValueError("Invalid book identity.")
    return kind, filename


def _list_name(name: str) -> tuple[str, str]:
    name = unicodedata.normalize("NFC", _text(name, MAX_LIST_NAME))
    if not name:
        raise ValueError("Enter a list name.")
    return name, name.casefold()


def get_document_lists(addon_dir: str, profile: str) -> list[tuple[int, str]]:
    return get_connection(addon_dir, profile).execute(
        "SELECT id,name FROM document_library_lists ORDER BY name_key,id"
    ).fetchall()


def create_document_list(addon_dir: str, profile: str, name: str) -> int:
    name, key = _list_name(name)
    conn = get_connection(addon_dir, profile)
    try:
        with conn:
            if conn.execute("SELECT count(*) FROM document_library_lists").fetchone()[0] >= MAX_LISTS:
                raise ValueError("Too many document lists.")
            cursor = conn.execute("INSERT INTO document_library_lists(name,name_key) VALUES (?,?)", (name, key))
            return int(cursor.lastrowid)
    except sqlite3.IntegrityError as exc:
        raise ValueError("A list with this name already exists.") from exc


def rename_document_list(addon_dir: str, profile: str, list_id: int, name: str) -> None:
    name, key = _list_name(name)
    conn = get_connection(addon_dir, profile)
    try:
        with conn:
            if not conn.execute("UPDATE document_library_lists SET name=?,name_key=? WHERE id=?",
                                (name, key, list_id)).rowcount:
                raise ValueError("This list no longer exists.")
    except sqlite3.IntegrityError as exc:
        raise ValueError("A list with this name already exists.") from exc


def delete_document_list(addon_dir: str, profile: str, list_id: int) -> None:
    conn = get_connection(addon_dir, profile)
    with conn:
        conn.execute("DELETE FROM document_library_memberships WHERE list_id=?", (list_id,))
        conn.execute("DELETE FROM document_library_lists WHERE id=?", (list_id,))


def write_document_details(conn, kind: str, filename: str, details: dict, *, recovering=False) -> None:
    """Write inside the caller's transaction, including the import journal commit."""
    kind, filename = document_key(kind, filename)
    details = normalize_document_details(details)
    requested = details["list_ids"]
    existing = {row[0] for row in conn.execute("SELECT id FROM document_library_lists")}
    if not recovering and not set(requested).issubset(existing):
        raise ValueError("A selected list no longer exists.")
    conn.execute(
        "INSERT INTO document_library_books(kind,filename,reason,source) VALUES (?,?,?,?) "
        "ON CONFLICT(kind,filename) DO UPDATE SET reason=excluded.reason,source=excluded.source",
        (kind, filename, details["reason"], details["source"]),
    )
    conn.execute("DELETE FROM document_library_memberships WHERE kind=? AND filename=?", (kind, filename))
    conn.executemany("INSERT INTO document_library_memberships(kind,filename,list_id) VALUES (?,?,?)",
                     [(kind, filename, i) for i in requested if i in existing])


def save_document_details(addon_dir: str, profile: str, kind: str, filename: str, details: dict) -> None:
    kind, filename = document_key(kind, filename)
    details = normalize_document_details(details)
    conn = get_connection(addon_dir, profile)
    with conn:
        write_document_details(conn, kind, filename, details)


def add_documents_to_list(addon_dir: str, profile: str, documents, list_id: int, *, cancel_event=None) -> tuple:
    """Atomically add unique documents without replacing notes or other memberships."""
    list_id = normalize_document_details({"list_ids": [list_id]})["list_ids"][0]
    keys = tuple(dict.fromkeys(document_key(kind, filename) for kind, filename in documents))
    if not keys:
        return keys
    conn = get_connection(addon_dir, profile)
    with conn:
        if not conn.execute("SELECT 1 FROM document_library_lists WHERE id=?", (list_id,)).fetchone():
            raise ValueError("This list no longer exists.")
        for kind, filename in keys:
            if cancel_event is not None and cancel_event.is_set():
                raise CancelledError()
            count = conn.execute("SELECT count(*) FROM document_library_memberships "
                                 "WHERE kind=? AND filename=? AND list_id<>?", (kind, filename, list_id)).fetchone()[0]
            if count >= MAX_BOOK_LISTS:
                raise ValueError("Too many book lists.")
            conn.execute("INSERT OR IGNORE INTO document_library_books(kind,filename,reason,source) VALUES (?,?,'','')",
                         (kind, filename))
            conn.execute("INSERT OR IGNORE INTO document_library_memberships(kind,filename,list_id) VALUES (?,?,?)",
                         (kind, filename, list_id))
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError()
    return keys


def load_document_library(addon_dir: str, profile: str) -> dict:
    conn = get_connection(addon_dir, profile)
    books = {(kind, filename): {"reason": reason, "source": source, "list_ids": []}
             for kind, filename, reason, source in conn.execute(
                 "SELECT kind,filename,reason,source FROM document_library_books")}
    for kind, filename, list_id in conn.execute(
            "SELECT kind,filename,list_id FROM document_library_memberships ORDER BY list_id"):
        if (kind, filename) in books:
            books[(kind, filename)]["list_ids"].append(list_id)
    return {"lists": get_document_lists(addon_dir, profile), "books": books}


def copy_document_details(addon_dir: str, profile: str, kind: str, old_filename: str, new_filename: str) -> None:
    """Keep acquisition notes when a document is relinked; retain the Undo copy."""
    if not old_filename or old_filename == new_filename:
        return
    kind, new_filename = document_key(kind, new_filename)
    try:
        _, old_filename = document_key(kind, old_filename)
    except ValueError:
        # Legacy absolute references cannot have a managed-file library record.
        return
    conn = get_connection(addon_dir, profile)
    with conn:
        row = conn.execute("SELECT reason,source FROM document_library_books WHERE kind=? AND filename=?",
                           (kind, old_filename)).fetchone()
        if row is not None:
            ids = [r[0] for r in conn.execute(
                "SELECT list_id FROM document_library_memberships WHERE kind=? AND filename=? ORDER BY list_id",
                (kind, old_filename))]
            write_document_details(conn, kind, new_filename, {"reason": row[0], "source": row[1], "list_ids": ids})
