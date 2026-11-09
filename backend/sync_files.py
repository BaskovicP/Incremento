"""Managed local files for sync: the file of a "Local File" card.

A local file card names its file in its note (``Local_File_Path``, ``Local_File_Mode``). Mode ``managed_copy`` means the
file was copied into the profile (``files/<name>``); mode ``reference`` points at a path on one computer, which means
nothing elsewhere, so only managed copies are shared. The note travels through Anki; this family carries the file.

A record ``card:<id>/localfile`` names the note, the profile-relative path and the file's sha256 as its *version*. The
file is copied into the profile's blob store when captured; the receiving device places it where the note says. A
note whose file is missing is unavailable: neither changed nor deleted. A tombstone forgets the record, never the
user's file.

Unlike the PDF and EPUB records, which Incremento tracks in its own database, a local file card exists only as an Anki
note, so this family reads the collection through ``query`` (the shape of ``col.db.all``, set by the service for each
run). Without it the scan fails rather than report that every file is gone.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

try:
    from . import paths, sync_paths
    from .sync_anki import Query
    from .sync_blobs import has_blob, materialize, store_file
    from .sync_records import SyncScanError, card_key, split_card_key, value_hash
except ImportError:
    import paths  # type: ignore[no-redef]
    import sync_paths  # type: ignore[no-redef]
    from sync_anki import Query  # type: ignore[no-redef]
    from sync_blobs import has_blob, materialize, store_file  # type: ignore[no-redef]
    from sync_records import SyncScanError, card_key, split_card_key, value_hash  # type: ignore[no-redef]

NOTE_TYPE = "Incremento Local File"
PATH_FIELD = "Local_File_Path"
MODE_FIELD = "Local_File_Mode"
MANAGED_COPY = "managed_copy"
IDENTITY_FIELDS = ("note_id", "path", "version")
FIELDS = {*IDENTITY_FIELDS, "blob"}
MAX_FILENAME = 255
#: What the managed-copy import writes: ``files/<sanitised name>-<uuid>.<ext>``.
_PATH = re.compile(r"^files/([A-Za-z0-9._-]{1,255})$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^sha256:[0-9a-f]{64}$")


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _name(relpath: Any) -> str | None:
    """The file name inside ``files/`` that a stored path names, or None when it is not one this device may use."""
    match = _PATH.match(relpath) if isinstance(relpath, str) else None
    if match is None or match.group(1).startswith("."):
        return None
    return match.group(1)


class LocalFileFamily:
    name = "localfile"

    def __init__(self, addon_dir: str, profile: str):
        self.addon_dir = addon_dir
        self.profile = profile
        self.blob_store = sync_paths.get_sync_blob_dir(addon_dir, profile)
        #: The collection's ``col.db.all``; the service sets it before each run.
        self.query: Query | None = None
        self._hashes: dict[str, tuple[int, int, str]] = {}

    # --- keys, paths and versions -------------------------------------------------

    def _parse_key(self, key: str) -> int:
        card_id, name = split_card_key(key, "localfile")
        if name or key != f"{card_key(card_id)}/localfile":
            raise ValueError(f"not a local file key: {key!r}")
        return card_id

    def _file(self, relpath: str) -> Path | None:
        name = _name(relpath)
        return None if name is None else paths.get_local_files_dir(self.addon_dir, self.profile) / name

    def _sha(self, path: Path) -> str:
        """sha256 of a file, remembered while its size and modification time are unchanged."""
        stat = path.stat()
        cached = self._hashes.get(str(path))
        if cached and cached[:2] == (stat.st_size, stat.st_mtime_ns):
            return cached[2]
        sha = _file_sha(path)
        self._hashes[str(path)] = (stat.st_size, stat.st_mtime_ns, sha)
        return sha

    def _notes(self, card_id: int | None = None) -> list[tuple[int, int, str]]:
        """(card id, note id, stored path) of every managed-copy local file card in the collection."""
        if self.query is None:
            raise SyncScanError("local files cannot be read without the Anki collection")
        try:
            types = self.query("SELECT id FROM notetypes WHERE name = ?", NOTE_TYPE)
            if not types:
                return []
            ntid = types[0][0]
            ords = {name: ordinal for name, ordinal in self.query("SELECT name, ord FROM fields WHERE ntid = ?", ntid)}
            if PATH_FIELD not in ords or MODE_FIELD not in ords:
                return []
            where, args = (" AND c.id = ?", (card_id,)) if card_id is not None else ("", ())
            rows = self.query("SELECT c.id, n.id, n.flds FROM cards c JOIN notes n ON n.id = c.nid "
                              "WHERE n.mid = ? AND c.ord = 0" + where + " ORDER BY c.id", ntid, *args)
        except sqlite3.OperationalError as exc:
            # A collection with no note types has no local file cards; any other failure must not read as "no files".
            if "no such table" in str(exc):
                return []
            raise SyncScanError(f"the Anki collection could not be read: {exc}") from exc
        found = []
        for cid, nid, flds in rows:
            fields = str(flds).split("\x1f")
            if len(fields) <= max(ords[PATH_FIELD], ords[MODE_FIELD]):
                continue
            if fields[ords[MODE_FIELD]].strip() == MANAGED_COPY:
                found.append((int(cid), int(nid), fields[ords[PATH_FIELD]].strip()))
        return found

    def _identity(self, note: tuple[int, int, str]) -> tuple[dict[str, Any], Path] | None:
        _, note_id, relpath = note
        path = self._file(relpath)
        if path is None or path.is_symlink() or not path.is_file():
            return None
        return {"note_id": note_id, "path": relpath, "version": f"sha256:{self._sha(path)}"}, path

    # --- the Family interface ------------------------------------------------------

    def scan(self, conn: sqlite3.Connection) -> Iterable[tuple[str, dict[str, Any]]]:
        records = []
        for note in self._notes():
            found = self._identity(note)
            if found is not None:
                records.append((f"{card_key(note[0])}/localfile", found[0]))
        return records

    def read(self, conn: sqlite3.Connection, key: str) -> dict[str, Any] | None:
        notes = self._notes(self._parse_key(key))
        found = self._identity(notes[0]) if notes else None
        if found is None:
            return None
        value, path = found
        value["blob"] = store_file(self.blob_store, path)
        return value

    def unavailable(self, conn: sqlite3.Connection, key: str) -> bool:
        """The note names a managed copy but its file is not here: not a change, not a deletion."""
        notes = self._notes(self._parse_key(key))
        return bool(notes) and self._identity(notes[0]) is None

    def card_id(self, key: str) -> int | None:
        return self._parse_key(key)

    def fingerprint(self, value: dict[str, Any]) -> str:
        return value_hash({field: value[field] for field in IDENTITY_FIELDS})

    def blobs(self, value: dict[str, Any]) -> list[str]:
        return [value["blob"]] if value.get("blob") else []

    def validate(self, key: str, value: Any) -> None:
        self._parse_key(key)
        if value is None:
            return
        if not isinstance(value, dict) or set(value) != FIELDS:
            raise ValueError("local file fields")
        if not isinstance(value["note_id"], int) or isinstance(value["note_id"], bool) or value["note_id"] <= 0:
            raise ValueError("local file note id")
        if _name(value["path"]) is None:
            raise ValueError("local file path")
        if not isinstance(value["version"], str) or not _VERSION.match(value["version"]):
            raise ValueError("local file version")
        if not isinstance(value["blob"], str) or not _HEX64.match(value["blob"]):
            raise ValueError("local file blob")

    def write(self, conn: sqlite3.Connection, key: str, value: dict[str, Any]) -> None:
        """Place the file where the note says. Runs inside the caller's transaction; nothing in the database changes."""
        self._parse_key(key)
        target = self._file(value["path"])
        if target is None:
            raise ValueError("local file path")
        if not has_blob(self.blob_store, value["blob"]):
            raise FileNotFoundError(f"blob {value['blob']} is not in the local blob store")
        if target.is_symlink():
            raise ValueError("local file target is a symlink")
        if not (target.is_file() and self._sha(target) == value["blob"]):
            materialize(self.blob_store, value["blob"], target)

    def delete(self, conn: sqlite3.Connection, key: str) -> None:
        """Forget the record. The file stays: sync never deletes a user's file."""
        self._parse_key(key)


__all__ = ["LocalFileFamily"]
