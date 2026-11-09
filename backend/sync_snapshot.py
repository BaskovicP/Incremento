"""Snapshots, retention and catching up for shared-folder sync.

See docs/architecture/shared-folder-sync.md §8. A device writes snapshots of
its view of the library below its own folder; a device deletes its own packs
only when every device's latest snapshot covers them; a device that lacks
retired history loads a snapshot that covers it; and a waiting revision whose
parent can no longer arrive is released.
"""

from __future__ import annotations

import gzip
import json
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from .sync_capture import sync_identity
    from .sync_exchange import (
        MAX_PACK_BYTES, MAX_PACK_REVISIONS, PackError, _parse, decode_snapshot_part, library_rel, sha256_bytes,
        validate_revision,
    )
    from .sync_records import SYNC_FORMAT, Family, canonical_json
    from .sync_store import Store, StoreError, as_store
except ImportError:
    from sync_capture import sync_identity  # type: ignore[no-redef]
    from sync_exchange import (  # type: ignore[no-redef]
        MAX_PACK_BYTES, MAX_PACK_REVISIONS, PackError, _parse, decode_snapshot_part, library_rel, sha256_bytes,
        validate_revision,
    )
    from sync_store import Store, StoreError, as_store  # type: ignore[no-redef]
    from sync_records import SYNC_FORMAT, Family, canonical_json  # type: ignore[no-redef]

MERGE_DEVICE = "~merge"
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_SNAPSHOT_PARTS = 10_000
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_PACK_NAME = re.compile(r"^(\d{6})-(\d{12})-([0-9a-f]{64})\.pack$")
_PART_NAME = re.compile(r"^(\d{12})-part(\d{4})-([0-9a-f]{64})\.snap$")
_MANIFEST_NAME = re.compile(r"^(\d{12})-manifest\.json$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

Receipts = dict[str, dict[int, int]]


@dataclass(frozen=True)
class Snapshot:
    device: str
    snapshot_id: str
    receipts: Receipts
    revisions: list[dict[str, Any]]


def _meta(conn: sqlite3.Connection, key: str, default: str = "0") -> str:
    row = conn.execute("SELECT value FROM sync_meta WHERE key=?", (key,)).fetchone()
    return default if row is None else row[0]


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    with conn:
        conn.execute("INSERT OR REPLACE INTO sync_meta(key, value) VALUES (?, ?)", (key, value))


def published_through(conn: sqlite3.Connection, device: str, epoch: int) -> int:
    """The highest sequence this device has published under its current identity."""
    return int(_meta(conn, "published_through"))


def retired_through(conn: sqlite3.Connection) -> int:
    return int(_meta(conn, "retired_through"))


def _receipts(conn: sqlite3.Connection) -> Receipts:
    identity = sync_identity(conn)
    assert identity is not None
    receipts: Receipts = {}
    for peer, epoch, max_seq in conn.execute("SELECT peer, epoch, max_seq FROM sync_receipts"):
        receipts.setdefault(peer, {})[int(epoch)] = int(max_seq)
    receipts.setdefault(identity.device_id, {})[identity.epoch] = published_through(
        conn, identity.device_id, identity.epoch)
    return receipts


def _progress(conn: sqlite3.Connection) -> int:
    return sum(seq for epochs in _receipts(conn).values() for seq in epochs.values())


# --- Writing ---------------------------------------------------------------------

def write_snapshot_if_due(conn: sqlite3.Connection, root: Path | Store, *, every: int, max_age: float,
                          now: float) -> str | None:
    """Write a snapshot when enough has happened since the last one (or it is old). Returns its id."""
    progress = _progress(conn)
    previous = int(_meta(conn, "snapshot_progress"))
    written_at = float(_meta(conn, "snapshot_at"))
    changed = progress - previous
    if changed <= 0 or (changed < every and now - written_at < max_age):
        return None
    return write_snapshot(conn, root, now=now)


def write_snapshot(conn: sqlite3.Connection, root: Path | Store, *, now: float) -> str:
    store = as_store(root)
    identity = sync_identity(conn)
    if identity is None:
        raise RuntimeError("sync is not enabled for this profile")
    heads = {row[0] for row in conn.execute("SELECT revision_id FROM sync_baseline")}
    for (heads_json,) in conn.execute("SELECT heads FROM sync_conflicts WHERE resolved_revision IS NULL"):
        heads.update(json.loads(heads_json))
    revisions = []
    for head in sorted(heads):
        row = conn.execute("SELECT id, family, key, parents, device, epoch, seq, deleted, value, deps "
                           "FROM sync_revisions WHERE id=?", (head,)).fetchone()
        if row is None:
            continue
        revisions.append({"id": row[0], "family": row[1], "key": row[2], "parents": json.loads(row[3]),
                          "device": row[4], "epoch": row[5], "seq": row[6], "deleted": bool(row[7]),
                          "value": None if row[8] is None else json.loads(row[8]), "deps": json.loads(row[9])})
    receipts = _receipts(conn)
    snapshot_id = f"{int(_meta(conn, 'snapshot_seq')) + 1:012d}"
    folder = f"{library_rel(identity.library_id)}/devices/{identity.device_id}/snapshots"
    parts = []
    for index, start in enumerate(range(0, len(revisions), MAX_PACK_REVISIONS) or [0]):
        chunk = revisions[start:start + MAX_PACK_REVISIONS]
        # Compressed deterministically (mtime 0): the same view gives the same bytes and name.
        data = gzip.compress(canonical_json({
            "format": SYNC_FORMAT, "library": identity.library_id, "device": identity.device_id,
            "snapshot": snapshot_id, "revisions": chunk}).encode("utf-8"), mtime=0)
        digest = sha256_bytes(data)
        name = f"{snapshot_id}-part{index:04d}-{digest}.snap"
        store.write(f"{folder}/{name}", data)
        parts.append({"name": name, "sha256": digest})
    manifest = {"format": SYNC_FORMAT, "library": identity.library_id, "device": identity.device_id,
                "snapshot": snapshot_id, "created_at": int(now), "parts": parts,
                "receipts": {device: {str(epoch): seq for epoch, seq in epochs.items()}
                             for device, epochs in receipts.items()}}
    store.write(f"{folder}/{snapshot_id}-manifest.json", canonical_json(manifest).encode("utf-8"))
    keep = {f"{snapshot_id}-manifest.json", *(part["name"] for part in parts)}
    stale = [entry.name for entry in store.listdir(folder) if entry.name not in keep and not entry.is_dir]
    for name in sorted(stale, key=lambda n: not n.endswith("-manifest.json")):  # manifests first
        store.delete(f"{folder}/{name}")
    _set_meta(conn, "snapshot_seq", str(int(snapshot_id)))
    _set_meta(conn, "snapshot_progress", str(sum(seq for epochs in receipts.values() for seq in epochs.values())))
    _set_meta(conn, "snapshot_at", str(now))
    return snapshot_id


# --- Reading ---------------------------------------------------------------------

def _read(store: Store, rel: str, limit: int) -> bytes | None:
    try:
        return store.read(rel, limit)
    except StoreError:
        return None


def _device_dirs(store: Store, library_id: str) -> list[str]:
    """Names of the library's device folders that have announced themselves (a device.json)."""
    devices = f"{library_rel(library_id)}/devices"
    names = []
    for entry in sorted(store.listdir(devices), key=lambda e: e.name):
        if entry.is_symlink or not entry.is_dir or not _IDENTIFIER.match(entry.name):
            continue
        announced = store.stat(f"{devices}/{entry.name}/device.json")
        if announced is not None and not announced.is_dir:
            names.append(entry.name)
    return names


def _latest_manifest(store: Store, library_id: str, device: str) -> tuple[str, dict[str, Any]] | None:
    folder = f"{library_rel(library_id)}/devices/{device}/snapshots"
    names = sorted((entry for entry in store.listdir(folder)
                    if _MANIFEST_NAME.match(entry.name) and not entry.is_symlink and not entry.is_dir
                    and entry.size <= MAX_MANIFEST_BYTES), key=lambda entry: entry.name)
    for entry in reversed(names):
        data = _read(store, f"{folder}/{entry.name}", MAX_MANIFEST_BYTES)
        if data is None:
            continue
        try:
            manifest = _parse(data)
        except PackError:
            continue
        if manifest.get("device") == device and manifest.get("snapshot") == entry.name[:12]:
            return entry.name, manifest
    return None


def manifest_receipts(manifest: dict[str, Any]) -> Receipts:
    receipts: Receipts = {}
    raw = manifest.get("receipts")
    if not isinstance(raw, dict):
        return receipts
    for device, epochs in raw.items():
        if not isinstance(device, str) or not isinstance(epochs, dict):
            continue
        for epoch, seq in epochs.items():
            if str(epoch).isdigit() and isinstance(seq, int) and not isinstance(seq, bool) and seq >= 0:
                receipts.setdefault(device, {})[int(epoch)] = seq
    return receipts


def latest_snapshot_receipts(root: Path | Store, library_id: str) -> dict[str, Receipts | None]:
    """For every device in the library: the receipts of its latest snapshot, or None without one."""
    store = as_store(root)
    result: dict[str, Receipts | None] = {}
    for device in _device_dirs(store, library_id):
        found = _latest_manifest(store, library_id, device)
        result[device] = manifest_receipts(found[1]) if found else None
    return result


def load_snapshot(root: Path | Store, library_id: str, device: str, families: Mapping[str, Family]) -> Snapshot | None:
    """A device's latest snapshot if it is complete and valid; None otherwise (perhaps still arriving)."""
    store = as_store(root)
    found = _latest_manifest(store, library_id, device)
    if found is None:
        return None
    _, manifest = found
    if manifest.get("format") != SYNC_FORMAT or manifest.get("library") != library_id:
        return None
    parts = manifest.get("parts")
    if not isinstance(parts, list) or not 0 < len(parts) <= MAX_SNAPSHOT_PARTS:
        return None
    folder = f"{library_rel(library_id)}/devices/{device}/snapshots"
    revisions: list[dict[str, Any]] = []
    for part in parts:
        if not isinstance(part, dict) or not isinstance(part.get("name"), str):
            return None
        match = _PART_NAME.match(part["name"])
        if not match or match[1] != manifest["snapshot"] or match[3] != part.get("sha256"):
            return None
        data = _read(store, f"{folder}/{part['name']}", MAX_PACK_BYTES)
        if data is None or sha256_bytes(data) != match[3]:
            return None
        try:
            payload = decode_snapshot_part(data)
            chunk = payload.get("revisions")
            if payload.get("device") != device or not isinstance(chunk, list):
                return None
            for revision in chunk:
                if not isinstance(revision, dict) or set(revision) != {
                        "id", "family", "key", "parents", "device", "epoch", "seq", "deleted", "value", "deps"}:
                    return None
                rev_device, epoch = revision["device"], revision["epoch"]
                if rev_device == MERGE_DEVICE:
                    if (epoch, revision["seq"]) != (1, 0):
                        return None
                elif not (isinstance(rev_device, str) and _IDENTIFIER.match(rev_device) and isinstance(epoch, int)
                          and not isinstance(epoch, bool) and epoch >= 1):
                    return None
                body = {key: value for key, value in revision.items() if key not in ("device", "epoch")}
                validate_revision(body, library_id=library_id, device=rev_device, epoch=epoch, families=families)
                revisions.append(revision)
        except PackError:
            return None
    return Snapshot(device, manifest["snapshot"], manifest_receipts(manifest), revisions)


# --- Catching up and completeness ---------------------------------------------------

def _peer_announcement(store: Store, library_id: str, device: str) -> tuple[int, int] | None:
    """(published through, retired through) announced in device.json."""
    rel = f"{library_rel(library_id)}/devices/{device}/device.json"
    entry = store.stat(rel)
    if entry is None or entry.is_dir or entry.size > 4096:
        return None
    data = _read(store, rel, 4096)
    if data is None:
        return None
    try:
        info = _parse(data)
    except PackError:
        return None
    published, retired = info.get("published"), info.get("retired")
    if not isinstance(published, dict) or not isinstance(retired, dict):
        return None
    through, gone = published.get("last_seq"), retired.get("through")
    if not (isinstance(through, int) and isinstance(gone, int) and not isinstance(through, bool)
            and not isinstance(gone, bool) and through >= 0 and gone >= 0):
        return None
    return through, gone


def _known_through(conn: sqlite3.Connection, device: str) -> int:
    row = conn.execute("SELECT max(max_seq) FROM sync_receipts WHERE peer=?", (device,)).fetchone()
    return int(row[0] or 0)


def catch_up(conn: sqlite3.Connection, root: Path | Store, families: Mapping[str, Family], *, now: float) -> bool:
    """Load a covering snapshot when some peer has retired history this device lacks. Returns whether it did."""
    store = as_store(root)
    identity = sync_identity(conn)
    if identity is None:
        return False
    missing: dict[str, int] = {}
    for device in _device_dirs(store, identity.library_id):
        if device == identity.device_id:
            continue
        announced = _peer_announcement(store, identity.library_id, device)
        if announced and announced[1] > _known_through(conn, device):
            missing[device] = announced[1]
    if not missing:
        return False
    candidates = []
    for device in _device_dirs(store, identity.library_id):
        snapshot = load_snapshot(store, identity.library_id, device, families)
        if snapshot and all(max(snapshot.receipts.get(device, {0: 0}).values()) >= through
                            for device, through in missing.items()):
            candidates.append(snapshot)
    if not candidates:
        return False  # perhaps still arriving; try again next sync
    best = max(candidates, key=lambda s: sum(seq for epochs in s.receipts.values() for seq in epochs.values()))
    timestamp = int(now)
    with conn:
        for revision in best.revisions:
            if conn.execute("SELECT 1 FROM sync_revisions WHERE id=?", (revision["id"],)).fetchone():
                continue
            conn.execute(
                "INSERT INTO sync_revisions(id, family, key, parents, device, epoch, seq, deleted, value, deps, "
                "format, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (revision["id"], revision["family"], revision["key"], canonical_json(sorted(revision["parents"])),
                 revision["device"], revision["epoch"], revision["seq"], int(revision["deleted"]),
                 None if revision["value"] is None else canonical_json(revision["value"]),
                 canonical_json(revision["deps"]), SYNC_FORMAT, timestamp))
            # A revision that needs files waits for them, so receiving fetches them before apply.
            status = "pending_blob" if revision["deps"].get("blobs") else "received"
            conn.execute("INSERT OR IGNORE INTO sync_inbox(revision_id, status, reason, received_at, updated_at) "
                         "VALUES (?, ?, 'from snapshot', ?, ?)", (revision["id"], status, timestamp, timestamp))
        for device, epochs in best.receipts.items():
            if device == identity.device_id:
                continue
            for epoch, seq in epochs.items():
                conn.execute("INSERT INTO sync_receipts(peer, epoch, max_seq) VALUES (?, ?, ?) "
                             "ON CONFLICT(peer, epoch) DO UPDATE SET max_seq=max(max_seq, excluded.max_seq)",
                             (device, epoch, seq))
    return True


def history_complete(conn: sqlite3.Connection, root: Path | Store) -> bool:
    """Whether every peer's unretired revisions are all known here.

    Then a parent that is still unknown lived only in a retired pack and can
    no longer arrive.
    """
    store = as_store(root)
    identity = sync_identity(conn)
    if identity is None:
        return False
    for device in _device_dirs(store, identity.library_id):
        if device == identity.device_id:
            continue
        announced = _peer_announcement(store, identity.library_id, device)
        if announced is None:
            return False
        through, gone = announced
        known = conn.execute("SELECT count(DISTINCT seq) FROM sync_revisions WHERE device=? AND seq>? AND seq<=?",
                             (device, gone, through)).fetchone()[0]
        if known != through - gone:
            return False
    return True


# --- Retention ---------------------------------------------------------------------

def retire_packs(conn: sqlite3.Connection, root: Path | Store) -> int:
    """Delete this device's packs that every device's latest snapshot covers. Returns how many."""
    store = as_store(root)
    identity = sync_identity(conn)
    if identity is None:
        return 0
    covered = []
    for device, receipts in latest_snapshot_receipts(store, identity.library_id).items():
        if receipts is None:
            return 0  # a device without a snapshot could still need everything
        covered.append(receipts.get(identity.device_id, {}).get(identity.epoch, 0))
    if not covered:
        return 0
    limit = min(covered)
    packs_rel = f"{library_rel(identity.library_id)}/devices/{identity.device_id}/packs"
    packs = sorted((int(match[2]), entry.name) for entry in store.listdir(packs_rel)
                   if (match := _PACK_NAME.match(entry.name)) and int(match[1]) == identity.epoch)
    last_published = published_through(conn, identity.device_id, identity.epoch)
    removed, retired = 0, retired_through(conn)
    for index, (first_seq, name) in enumerate(packs):
        last_seq = packs[index + 1][0] - 1 if index + 1 < len(packs) else last_published
        if last_seq <= limit:
            store.delete(f"{packs_rel}/{name}")
            removed += 1
            retired = max(retired, last_seq)
    if removed:
        _set_meta(conn, "retired_through", str(retired))
    return removed


def sweep_blobs(root: Path | Store, library_id: str, *, now: float, grace_seconds: float) -> int:
    """Delete exchange blobs no pack or snapshot names, once older than the grace period. Returns how many."""
    store = as_store(root)
    library = library_rel(library_id)
    referenced: set[str] = set()
    devices = f"{library}/devices"
    for device in store.listdir(devices):
        if device.is_symlink or not device.is_dir:
            continue
        for folder, suffix in (("packs", ".pack"), ("snapshots", ".snap")):
            for entry in store.listdir(f"{devices}/{device.name}/{folder}"):
                if not entry.name.endswith(suffix):
                    continue
                if entry.is_symlink or entry.is_dir or entry.size > MAX_PACK_BYTES:
                    return 0  # cannot tell what it names: delete nothing
                data = _read(store, f"{devices}/{device.name}/{folder}/{entry.name}", MAX_PACK_BYTES)
                if data is None:
                    return 0
                if entry.name.endswith(".snap"):
                    try:
                        data = json.dumps(decode_snapshot_part(data)).encode("utf-8")
                    except PackError:
                        return 0  # unreadable (perhaps still arriving): delete nothing
                names = _blob_names(data)
                if names is None:
                    return 0  # unreadable (perhaps still arriving): delete nothing
                referenced |= names
    removed = 0
    for prefix in store.listdir(f"{library}/blobs"):
        if prefix.is_symlink or not prefix.is_dir:
            continue
        for entry in store.listdir(f"{library}/blobs/{prefix.name}"):
            if (_HEX64.match(entry.name) and entry.name not in referenced and not entry.is_dir
                    and not entry.is_symlink and now - entry.mtime > grace_seconds):
                store.delete(f"{library}/blobs/{prefix.name}/{entry.name}")
                removed += 1
    return removed


def _blob_names(data: bytes) -> set[str] | None:
    """Blob names a pack or snapshot part refers to; None when it cannot be read."""
    try:
        revisions = json.loads(data.decode("utf-8")).get("revisions", [])
    except (ValueError, AttributeError):
        return None
    names = set()
    for revision in revisions if isinstance(revisions, list) else []:
        deps = revision.get("deps") if isinstance(revision, dict) else None
        for name in deps.get("blobs", []) if isinstance(deps, dict) else []:
            if isinstance(name, str) and _HEX64.match(name):
                names.add(name)
    return names

