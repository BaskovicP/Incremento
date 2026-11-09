"""Document versions for sync: a card's managed PDF or EPUB.

See docs/architecture/shared-folder-sync.md §6.1.

A record ``card:<id>/document:<pdf|epub>`` names the card's content identity,
note and profile-relative file, plus a *version*. A PDF's version is the
interchange's ``content_digest``, which leaves annotations out; without
one, and for EPUBs, it is the file's sha256. The fingerprint, which decides
whether something changed, is that identity and version, never the current
bytes. A PDF rewritten by annotation interchange therefore does not ship
again; its annotations travel as highlight records.

When a version is captured, the file is copied into the profile's blob
store, and the revision names that blob and the PDF interchange baseline of
the moment. The receiving device places the file and adopts the baseline,
so its own interchange knows which native annotations were deliberately
deleted elsewhere instead of bringing them back.

A record whose file is missing is unavailable: neither changed nor deleted.
A tombstone removes the records, never the user's file.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

try:
    from . import paths
    from .sync_blobs import blob_path, has_blob, materialize, store_file
    from .sync_records import card_key, split_card_key, value_hash
except ImportError:
    import paths  # type: ignore[no-redef]
    from sync_blobs import blob_path, has_blob, materialize, store_file  # type: ignore[no-redef]
    from sync_records import card_key, split_card_key, value_hash  # type: ignore[no-redef]

KINDS = {"pdf": ("pdfs", ".pdf"), "epub": ("epubs", ".epub")}
IDENTITY_FIELDS = ("kind", "content_id", "note_id", "path", "version")
MAX_FILENAME = 255
MAX_BASELINE_CHARS = 4 * 1024 * 1024
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^(digest|sha256):[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class DocumentFamily:
    name = "document"

    def __init__(self, addon_dir: str, profile: str):
        self.addon_dir = addon_dir
        self.profile = profile
        self.blob_store = paths.get_sync_blob_dir(addon_dir, profile)
        self._hashes: dict[str, tuple[int, int, str]] = {}

    # --- keys, paths and versions -------------------------------------------------

    def _parse_key(self, key: str) -> tuple[int, str]:
        card_id, kind = split_card_key(key, "document")
        if kind not in KINDS or f"{card_key(card_id)}/document:{kind}" != key:
            raise ValueError(f"not a document key: {key!r}")
        return card_id, kind

    def _directory(self, kind: str) -> Path:
        if kind == "pdf":
            return paths.get_pdf_dir(self.addon_dir, self.profile)
        return paths.get_epub_dir(self.addon_dir, self.profile)

    def _file(self, kind: str, relpath: str) -> Path | None:
        folder, extension = KINDS[kind]
        prefix, _, name = relpath.partition("/")
        if (prefix != folder or not name or "/" in name or "\\" in name or name.startswith(".")
                or len(name) > MAX_FILENAME or not name.lower().endswith(extension)
                or any(ord(character) < 32 for character in name)):
            return None
        return self._directory(kind) / name

    def _sha(self, path: Path) -> str:
        """sha256 of a file, remembered while its size and modification time are unchanged."""
        stat = path.stat()
        cached = self._hashes.get(str(path))
        if cached and cached[:2] == (stat.st_size, stat.st_mtime_ns):
            return cached[2]
        sha = _file_sha(path)
        self._hashes[str(path)] = (stat.st_size, stat.st_mtime_ns, sha)
        return sha

    def _interchange(self, conn: sqlite3.Connection, card_id: int, filename: str) -> dict[str, str] | None:
        row = conn.execute("SELECT filename, document_id, content_digest, baseline_json FROM pdf_annotation_sync "
                           "WHERE card_id=?", (card_id,)).fetchone()
        if row is None or row[0] != filename or not _HEX64.match(row[2] or ""):
            return None
        return {"document_id": row[1], "content_digest": row[2], "baseline_json": row[3]}

    def _rows(self, conn: sqlite3.Connection, where: str = "", args: tuple[Any, ...] = ()) -> list[tuple]:
        return conn.execute("SELECT content_id, kind, card_id, note_id, storage_key FROM content_items "
                            "WHERE kind IN ('pdf', 'epub') AND card_id IS NOT NULL" + where
                            + " ORDER BY card_id, kind", args).fetchall()

    def _identity(self, conn: sqlite3.Connection, row: tuple) -> tuple[dict[str, Any], Path] | None:
        content_id, kind, card_id, note_id, storage_key = row
        path = self._file(kind, storage_key or "")
        if path is None or path.is_symlink() or not path.is_file():
            return None
        interchange = self._interchange(conn, card_id, path.name) if kind == "pdf" else None
        version = f"digest:{interchange['content_digest']}" if interchange else f"sha256:{self._sha(path)}"
        return {"kind": kind, "content_id": content_id, "note_id": int(note_id or 0), "path": storage_key,
                "version": version}, path

    # --- the Family interface ------------------------------------------------------

    def scan(self, conn: sqlite3.Connection) -> Iterable[tuple[str, dict[str, Any]]]:
        records = []
        for row in self._rows(conn):
            found = self._identity(conn, row)
            if found is not None:
                records.append((f"{card_key(row[2])}/document:{row[1]}", found[0]))
        return records

    def read(self, conn: sqlite3.Connection, key: str) -> dict[str, Any] | None:
        card_id, kind = self._parse_key(key)
        rows = self._rows(conn, " AND card_id=? AND kind=?", (card_id, kind))
        if not rows:
            return None
        found = self._identity(conn, rows[0])
        if found is None:
            return None
        value, path = found
        value["blob"] = store_file(self.blob_store, path)
        value["interchange"] = self._interchange(conn, card_id, path.name) if kind == "pdf" else None
        return value

    def unavailable(self, conn: sqlite3.Connection, key: str) -> bool:
        """The content row exists but its file does not: not a change, not a deletion."""
        card_id, kind = self._parse_key(key)
        rows = self._rows(conn, " AND card_id=? AND kind=?", (card_id, kind))
        return bool(rows) and self._identity(conn, rows[0]) is None

    def card_id(self, key: str) -> int | None:
        return self._parse_key(key)[0]

    def fingerprint(self, value: dict[str, Any]) -> str:
        return value_hash({field: value[field] for field in IDENTITY_FIELDS})

    def blobs(self, value: dict[str, Any]) -> list[str]:
        return [value["blob"]] if value.get("blob") else []

    def validate(self, key: str, value: Any) -> None:
        _, kind = self._parse_key(key)
        if value is None:
            return
        if not isinstance(value, dict) or set(value) != {*IDENTITY_FIELDS, "blob", "interchange"}:
            raise ValueError("document fields")
        if value["kind"] != kind:
            raise ValueError("document kind does not match the key")
        if not isinstance(value["content_id"], str) or not _SAFE_ID.match(value["content_id"]):
            raise ValueError("document content id")
        if not isinstance(value["note_id"], int) or isinstance(value["note_id"], bool) or value["note_id"] <= 0:
            raise ValueError("document note id")
        if not isinstance(value["path"], str) or self._file(kind, value["path"]) is None:
            raise ValueError("document path")
        if not isinstance(value["version"], str) or not _VERSION.match(value["version"]):
            raise ValueError("document version")
        if not isinstance(value["blob"], str) or not _HEX64.match(value["blob"]):
            raise ValueError("document blob")
        interchange = value["interchange"]
        if interchange is None:
            return
        if kind != "pdf" or not isinstance(interchange, dict) or set(interchange) != {
                "document_id", "content_digest", "baseline_json"}:
            raise ValueError("document interchange fields")
        if not isinstance(interchange["document_id"], str) or not _SAFE_ID.match(interchange["document_id"]):
            raise ValueError("document interchange id")
        if not isinstance(interchange["content_digest"], str) or not _HEX64.match(interchange["content_digest"]):
            raise ValueError("document interchange digest")
        baseline = interchange["baseline_json"]
        if not isinstance(baseline, str) or len(baseline) > MAX_BASELINE_CHARS:
            raise ValueError("document interchange baseline size")
        try:
            if not isinstance(json.loads(baseline), dict):
                raise ValueError("document interchange baseline")
        except json.JSONDecodeError as exc:
            raise ValueError("document interchange baseline") from exc

    def write(self, conn: sqlite3.Connection, key: str, value: dict[str, Any]) -> None:
        """Place the file and adopt the records. Runs inside the caller's transaction."""
        card_id, kind = self._parse_key(key)
        target = self._file(kind, value["path"])
        if target is None:
            raise ValueError("document path")
        if not has_blob(self.blob_store, value["blob"]):
            raise FileNotFoundError(f"blob {value['blob']} is not in the local blob store")
        if target.is_symlink():
            raise ValueError("document target is a symlink")
        if not (target.is_file() and self._sha(target) == value["blob"]):
            materialize(self.blob_store, value["blob"], target)
        conn.execute("DELETE FROM content_items WHERE kind=? AND card_id=? AND content_id<>?",
                     (kind, card_id, value["content_id"]))
        conn.execute("INSERT INTO content_items(content_id, kind, card_id, note_id, storage_key, created_at, "
                     "updated_at) VALUES (?, ?, ?, ?, ?, strftime('%s','now'), strftime('%s','now')) "
                     "ON CONFLICT(content_id) DO UPDATE SET kind=excluded.kind, card_id=excluded.card_id, "
                     "note_id=excluded.note_id, storage_key=excluded.storage_key, updated_at=excluded.updated_at",
                     (value["content_id"], kind, card_id, value["note_id"], value["path"]))
        if kind == "pdf":
            interchange = value["interchange"]
            if interchange is None:
                conn.execute("DELETE FROM pdf_annotation_sync WHERE card_id=?", (card_id,))
            else:
                conn.execute("INSERT OR REPLACE INTO pdf_annotation_sync(card_id, filename, document_id, source_path, "
                             "content_digest, baseline_json) VALUES (?, ?, ?, '', ?, ?)",
                             (card_id, target.name, interchange["document_id"], interchange["content_digest"],
                              interchange["baseline_json"]))

    def delete(self, conn: sqlite3.Connection, key: str) -> None:
        """Forget the document's records. The file stays: sync never deletes a user's file."""
        card_id, kind = self._parse_key(key)
        conn.execute("DELETE FROM content_items WHERE kind=? AND card_id=?", (kind, card_id))
        if kind == "pdf":
            conn.execute("DELETE FROM pdf_annotation_sync WHERE card_id=?", (card_id,))


__all__ = ["DocumentFamily", "blob_path"]
