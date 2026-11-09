"""The shared-folder exchange: publish captured revisions, receive other devices'.

See docs/architecture/shared-folder-sync.md §6 (steps 3-4) and §8.

Layout below the folder the user chose::

    IncrementoSync/v1/<library_id>/
      library.json                                   written once, by the first device
      devices/<device_id>/device.json                written only by that device
      devices/<device_id>/packs/<epoch>-<seq>-<sha256>.pack

A device writes only below its own ``devices/<device_id>/``, so a sync
provider never sees two devices write one file. A pack is immutable and
named by the SHA-256 of its bytes; a pack whose bytes do not match its name
has not finished arriving. Receiving validates everything before trusting
it (format, library, device, every revision's content hash, family schema)
and records revisions in the inbox. Nothing is applied here.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from .sync_blobs import fetch_exchange_blob, has_blob, put_exchange_blob
    from .sync_capture import revision_id, sync_identity
    from .sync_store import Entry, Store, StoreError, as_store
    from .sync_records import SYNC_FORMAT, Family, canonical_json, record_blobs, validate_card_deps
except ImportError:
    from sync_blobs import fetch_exchange_blob, has_blob, put_exchange_blob  # type: ignore[no-redef]
    from sync_store import Entry, Store, StoreError, as_store  # type: ignore[no-redef]
    from sync_capture import revision_id, sync_identity  # type: ignore[no-redef]
    from sync_records import (  # type: ignore[no-redef]
        SYNC_FORMAT, Family, canonical_json, record_blobs, validate_card_deps,
    )

EXCHANGE_DIR = ("IncrementoSync", "v1")
MAX_PACK_BYTES = 8 * 1024 * 1024
MAX_PACK_REVISIONS = 2000
MAX_PARENTS = 16
MAX_DEVICE_FILE_BYTES = 4096
#: A compressed snapshot part may not expand beyond this.
MAX_DECOMPRESSED_BYTES = 64 * 1024 * 1024

_PACK_NAME = re.compile(r"^(\d{6})-(\d{12})-([0-9a-f]{64})\.pack$")
_SNAPSHOT_PART_NAME = re.compile(r"^(\d{12})-part(\d{4})-([0-9a-f]{64})\.snap$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass
class PublishResult:
    packs_written: int = 0
    revisions_published: int = 0


@dataclass
class ReceiveResult:
    received: int = 0
    rejected: int = 0
    incomplete: int = 0
    problems: list[str] = field(default_factory=list)


class PackError(ValueError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def library_rel(library_id: str) -> str:
    """A library's folder below the exchange root, as a store path."""
    return "/".join((*EXCHANGE_DIR, library_id))


def library_dir(root: Path, library_id: str) -> Path:
    """The same folder as a directory path, for a folder-backed exchange (tests and tools)."""
    return Path(root).joinpath(*EXCHANGE_DIR, library_id)


def _read_or_none(store: Store, rel: str, limit: int) -> bytes | None:
    try:
        return store.read(rel, limit)
    except StoreError:
        return None


def _write_json_if_changed(store: Store, rel: str, value: Any) -> None:
    data = canonical_json(value).encode("utf-8")
    if _read_or_none(store, rel, 1_000_000) == data:
        return
    store.write(rel, data)


# --- Publication ---------------------------------------------------------------

def _pack_bytes(identity_library: str, device: str, epoch: int, rows: list[tuple]) -> bytes:
    revisions = [{"id": rid, "family": family, "key": key, "parents": json.loads(parents), "seq": seq,
                  "deleted": bool(deleted), "value": None if value is None else json.loads(value),
                  "deps": json.loads(deps)}
                 for rid, family, key, parents, seq, deleted, value, deps in rows]
    payload = {"format": SYNC_FORMAT, "library": identity_library, "device": device, "epoch": epoch,
               "first_seq": revisions[0]["seq"], "last_seq": revisions[-1]["seq"], "revisions": revisions}
    return canonical_json(payload).encode("utf-8")


def _mark_published(conn: sqlite3.Connection, revision_ids: list[str], now: int) -> None:
    """The pack holding these revisions is written and verified: they leave the outbox.

    The highest published sequence is kept in sync_meta, for device.json and snapshots.
    """
    marks = ",".join("?" * len(revision_ids))
    with conn:
        highest = conn.execute(f"SELECT max(seq) FROM sync_revisions WHERE id IN ({marks})", revision_ids).fetchone()[0]
        conn.execute(f"DELETE FROM sync_outbox WHERE revision_id IN ({marks})", revision_ids)
        conn.execute("INSERT INTO sync_meta(key, value) VALUES ('published_through', ?) "
                     "ON CONFLICT(key) DO UPDATE SET value=max(CAST(value AS INTEGER), CAST(excluded.value AS INTEGER))",
                     (str(int(highest or 0)),))


def publish(conn: sqlite3.Connection, root: Path | Store, *, anki_usn: int | None = None, anki_scm: int | None = None,
            blob_store: Path | None = None, now: Callable[[], float] = time.time) -> PublishResult:
    """Write every unpublished revision into packs below this device's folder.

    ``anki_usn`` is the collection's usn after its last AnkiWeb sync; other
    devices use it to tell a card still on its way from a deleted one.
    """
    store = as_store(root)
    identity = sync_identity(conn)
    if identity is None:
        raise RuntimeError("sync is not enabled for this profile")
    library = library_rel(identity.library_id)
    if store.stat(f"{library}/library.json") is None:
        _write_json_if_changed(store, f"{library}/library.json",
                               {"format": SYNC_FORMAT, "library_id": identity.library_id})
    device = f"{library}/devices/{identity.device_id}"

    result = PublishResult()
    rows = conn.execute(
        "SELECT r.id, r.family, r.key, r.parents, r.seq, r.deleted, r.value, r.deps, r.epoch "
        "FROM sync_outbox o JOIN sync_revisions r ON r.id = o.revision_id "
        "WHERE o.published_at IS NULL AND r.device = ? ORDER BY r.epoch, r.seq", (identity.device_id,)).fetchall()
    batches: list[tuple[int, list[tuple]]] = []
    for row in rows:
        epoch = row[8]
        if not batches or batches[-1][0] != epoch or len(batches[-1][1]) >= MAX_PACK_REVISIONS:
            batches.append((epoch, []))
        batches[-1][1].append(row[:8])
    for epoch, batch in batches:
        # Files first: a pack never names a blob that has not been placed.
        for row in batch:
            for sha in json.loads(row[7]).get("blobs", []):
                if blob_store is None or not put_exchange_blob(store, library, blob_store, sha):
                    raise RuntimeError(f"blob {sha} of revision {row[0]} is not in the local blob store")
        data = _pack_bytes(identity.library_id, identity.device_id, epoch, batch)
        digest = sha256_bytes(data)
        rel = f"{device}/packs/{epoch:06d}-{batch[0][4]:012d}-{digest}.pack"
        existing = _read_or_none(store, rel, MAX_PACK_BYTES)
        if not (existing is not None and sha256_bytes(existing) == digest):
            store.write(rel, data)
            written = _read_or_none(store, rel, len(data))
            if written is None or sha256_bytes(written) != digest:
                raise OSError(f"pack {rel.rsplit('/', 1)[-1]} did not verify after writing")
            result.packs_written += 1
        _mark_published(conn, [row[0] for row in batch], int(now()))
        result.revisions_published += len(batch)
    announce(conn, store, anki_usn=anki_usn, anki_scm=anki_scm)
    return result


def announce(conn: sqlite3.Connection, root: Path | Store, *, anki_usn: int | None, anki_scm: int | None) -> None:
    """Write this device's device.json: its AnkiWeb state and what it has published and retired.

    Written after the packs, so a reader never sees a range announced before its packs exist here.
    """
    store = as_store(root)
    identity = sync_identity(conn)
    if identity is None:
        raise RuntimeError("sync is not enabled for this profile")
    row = conn.execute("SELECT value FROM sync_meta WHERE key='published_through'").fetchone()
    published = int(row[0]) if row else 0
    retired = conn.execute("SELECT value FROM sync_meta WHERE key='retired_through'").fetchone()
    _write_json_if_changed(
        store, f"{library_rel(identity.library_id)}/devices/{identity.device_id}/device.json",
        {"format": SYNC_FORMAT, "device_id": identity.device_id, "epoch": identity.epoch, "anki_usn": anki_usn,
         "anki_scm": anki_scm, "published": {"epoch": identity.epoch, "last_seq": int(published)},
         "retired": {"epoch": identity.epoch, "through": int(retired[0]) if retired else 0}})


# --- Receiving -----------------------------------------------------------------

def _no_constants(name: str) -> Any:
    raise PackError(f"value: {name} is not allowed")


def decode_snapshot_part(data: bytes) -> dict[str, Any]:
    """A gzip-compressed snapshot part, decompressed within MAX_DECOMPRESSED_BYTES and parsed."""
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        raw = inflater.decompress(data, MAX_DECOMPRESSED_BYTES)
    except zlib.error as exc:
        raise PackError(f"not a compressed snapshot part: {exc}") from exc
    if inflater.unconsumed_tail or not inflater.eof:
        raise PackError(f"snapshot part expands beyond {MAX_DECOMPRESSED_BYTES} bytes or is incomplete")
    return _parse(raw)


def _parse(data: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(data.decode("utf-8"), parse_constant=_no_constants)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackError(f"not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise PackError("not a pack object")
    return payload


def validate_revision(revision: dict[str, Any], *, library_id: str, device: str, epoch: int,
                      families: Mapping[str, Family]) -> None:
    """Check one revision as received; raise PackError naming what is wrong.

    ``revision`` has ``id, family, key, parents, seq, deleted, value, deps``;
    ``device`` and ``epoch`` come from where it was found (pack folder or snapshot).
    """
    family = families.get(revision["family"]) if isinstance(revision["family"], str) else None
    if family is None:
        raise PackError(f"unknown family {revision['family']!r}")
    seq = revision["seq"]
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
        raise PackError("seq")
    if not isinstance(revision["key"], str) or not 0 < len(revision["key"]) <= 512:
        raise PackError("key")
    parents = revision["parents"]
    if (not isinstance(parents, list) or len(parents) > MAX_PARENTS or len(set(parents)) != len(parents)
            or not all(isinstance(p, str) and _HEX64.match(p) for p in parents)):
        raise PackError("parents")
    deleted = revision["deleted"]
    if not isinstance(deleted, bool) or (deleted != (revision["value"] is None)):
        raise PackError("value: tombstone must have no value and a live revision one")
    try:
        family.validate(revision["key"], None if deleted else revision["value"])
    except ValueError as exc:
        raise PackError(f"{'key' if 'key' in str(exc) else 'value'}: {exc}") from exc
    deps = revision["deps"]
    card_id = family.card_id(revision["key"])
    if not isinstance(deps, dict) or set(deps) - {"card", "blobs"} or ("card" in deps) != (card_id is not None):
        raise PackError("deps fields")
    if card_id is not None:
        try:
            validate_card_deps(card_id, deps)
        except ValueError as exc:
            raise PackError(f"deps: {exc}") from exc
    if deps.get("blobs", []) != record_blobs(family, None if deleted else revision["value"]):
        raise PackError("deps: blobs do not match the value")
    expected_id = revision_id(library=library_id, family=revision["family"], key=revision["key"],
                              parents=parents, device=device, epoch=epoch, seq=seq, deleted=deleted,
                              value=revision["value"], deps=revision["deps"], format=SYNC_FORMAT)
    if revision["id"] != expected_id:
        raise PackError("id does not match the revision's content")


def _validate(payload: dict[str, Any], *, library_id: str, device_dir: str, epoch: int, first_seq: int,
              families: Mapping[str, Family]) -> list[dict[str, Any]]:
    expected = {"format", "library", "device", "epoch", "first_seq", "last_seq", "revisions"}
    if set(payload) != expected:
        raise PackError("pack fields")
    if payload["format"] != SYNC_FORMAT:
        raise PackError(f"unsupported format {payload['format']!r}")
    if payload["library"] != library_id:
        raise PackError("library does not match")
    if payload["device"] != device_dir:
        raise PackError("device does not match its folder")
    if payload["epoch"] != epoch or payload["first_seq"] != first_seq:
        raise PackError("epoch or seq does not match the pack name")
    revisions = payload["revisions"]
    if not isinstance(revisions, list) or not 0 < len(revisions) <= MAX_PACK_REVISIONS:
        raise PackError("revision count")
    last_seq = payload["last_seq"]
    if not isinstance(last_seq, int) or last_seq < first_seq:
        raise PackError("seq range")
    previous = first_seq - 1
    for revision in revisions:
        if not isinstance(revision, dict) or set(revision) != {
                "id", "family", "key", "parents", "seq", "deleted", "value", "deps"}:
            raise PackError("revision fields")
        seq = revision["seq"]
        if not isinstance(seq, int) or isinstance(seq, bool) or not previous < seq <= last_seq:
            raise PackError("seq outside the pack or out of order")
        previous = seq
        validate_revision(revision, library_id=library_id, device=device_dir, epoch=epoch, families=families)
    if previous != last_seq:
        raise PackError("seq range")
    return revisions


def _store(conn: sqlite3.Connection, revisions: list[dict[str, Any]], *, device: str, epoch: int, now: int) -> int:
    """Record validated revisions and their inbox rows; returns how many were new."""
    new = 0
    conn.execute("BEGIN IMMEDIATE")
    try:
        for revision in revisions:
            known = conn.execute("SELECT 1 FROM sync_revisions WHERE id=?", (revision["id"],)).fetchone()
            if known:
                continue
            try:
                conn.execute(
                    "INSERT INTO sync_revisions(id, family, key, parents, device, epoch, seq, deleted, value, deps, "
                    "format, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (revision["id"], revision["family"], revision["key"], canonical_json(revision["parents"]),
                     device, epoch, revision["seq"], int(revision["deleted"]),
                     None if revision["value"] is None else canonical_json(revision["value"]),
                     canonical_json(revision["deps"]), SYNC_FORMAT, now))
            except sqlite3.IntegrityError as exc:
                raise PackError(f"seq reused by a different revision: {exc}") from exc
            conn.execute("INSERT INTO sync_inbox(revision_id, status, reason, received_at, updated_at) "
                         "VALUES (?, 'pending_parent', '', ?, ?)", (revision["id"], now, now))
            new += 1
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return new


def release_waiting(conn: sqlite3.Connection, now: int, *, blob_store: Path | None = None,
                    fetch: Callable[[str], bool] | None = None, parents_may_be_retired: bool = False) -> int:
    """Re-check waiting revisions: parents known and blobs present make them received.

    With ``fetch`` (receiving), a missing blob is copied from the exchange into ``blob_store`` after
    verification. Returns how many revisions became received.
    """
    released = 0
    waiting = conn.execute("SELECT i.revision_id, i.status, r.parents, r.deps FROM sync_inbox i "
                           "JOIN sync_revisions r ON r.id = i.revision_id "
                           "WHERE i.status IN ('pending_parent', 'pending_blob')").fetchall()
    with conn:
        for revision, status, parents, deps in waiting:
            if not parents_may_be_retired and not all(
                    conn.execute("SELECT 1 FROM sync_revisions WHERE id=?", (p,)).fetchone()
                    for p in json.loads(parents)):
                new_status = "pending_parent"
            else:
                missing = []
                for sha in json.loads(deps).get("blobs", []):
                    available = has_blob(blob_store, sha) or (fetch is not None and fetch(sha))
                    if not available:
                        missing.append(sha)
                new_status = "pending_blob" if missing else "received"
            if new_status != status:
                conn.execute("UPDATE sync_inbox SET status=?, updated_at=? WHERE revision_id=?",
                             (new_status, now, revision))
                released += new_status == "received"
    return released


def _record_peer(conn: sqlite3.Connection, store: Store, device_rel: str, name: str, entries: dict[str, Entry],
                 now: int, problems: list[str]) -> None:
    """Remember a peer's announced AnkiWeb state from its device.json."""
    entry = entries.get("device.json")
    if entry is None or entry.is_symlink or entry.is_dir:
        return
    if entry.size > MAX_DEVICE_FILE_BYTES:
        problems.append(f"{name}/device.json: size exceeds {MAX_DEVICE_FILE_BYTES} bytes")
        return
    data = _read_or_none(store, f"{device_rel}/device.json", MAX_DEVICE_FILE_BYTES)
    if data is None:
        return
    try:
        info = _parse(data)
    except PackError as exc:
        problems.append(f"{name}/device.json: {exc}")
        return
    usn, scm = info.get("anki_usn"), info.get("anki_scm")
    if info.get("device_id") != name or not all(
            value is None or (isinstance(value, int) and not isinstance(value, bool) and value >= 0)
            for value in (usn, scm)):
        problems.append(f"{name}/device.json: device, anki_usn or anki_scm invalid")
        return
    with conn:
        conn.execute("INSERT OR REPLACE INTO sync_peers(device, anki_usn, anki_scm, seen_at) VALUES (?, ?, ?, ?)",
                     (name, usn, scm, now))


def _remember(conn: sqlite3.Connection, device: str, name: str, outcome: str, now: int) -> None:
    with conn:
        conn.execute("INSERT OR REPLACE INTO sync_seen_packs(device, name, outcome, format, seen_at) "
                     "VALUES (?, ?, ?, ?, ?)", (device, name, outcome, SYNC_FORMAT, now))


def sample_card_refs(root: Path | Store, library_id: str, limit: int = 50) -> dict[int, str]:
    """Card ids and note GUIDs named by a library's packs: evidence of which collection it belongs to.

    Reads only complete packs (bytes matching their name) within the size
    limit; anything else is skipped, never trusted.
    """
    store = as_store(root)
    found: dict[int, str] = {}
    devices_rel = f"{library_rel(library_id)}/devices"
    for device in sorted(store.listdir(devices_rel), key=lambda entry: entry.name):
        if device.is_symlink or not device.is_dir or not _IDENTIFIER.match(device.name):
            continue
        # Packs, and snapshot parts once packs have been retired.
        files = [(f"{devices_rel}/{device.name}/packs/{entry.name}", entry, _PACK_NAME.match(entry.name))
                 for entry in sorted(store.listdir(f"{devices_rel}/{device.name}/packs"), key=lambda e: e.name)]
        files += [(f"{devices_rel}/{device.name}/snapshots/{entry.name}", entry, _SNAPSHOT_PART_NAME.match(entry.name))
                  for entry in sorted(store.listdir(f"{devices_rel}/{device.name}/snapshots"),
                                      key=lambda e: e.name)]
        for rel, entry, match in files:
            if not match or entry.is_symlink or entry.is_dir or entry.size > MAX_PACK_BYTES:
                continue
            data = _read_or_none(store, rel, MAX_PACK_BYTES)
            if data is None or sha256_bytes(data) != match[3]:
                continue
            try:
                payload = decode_snapshot_part(data) if rel.endswith(".snap") else _parse(data)
                revisions = payload.get("revisions", [])
            except PackError:
                continue
            for revision in revisions if isinstance(revisions, list) else []:
                card = revision.get("deps", {}).get("card") if isinstance(revision, dict) else None
                if (isinstance(card, dict) and isinstance(card.get("card_id"), int)
                        and isinstance(card.get("guid"), str)):
                    found[card["card_id"]] = card["guid"]
                    if len(found) >= limit:
                        return found
    return found


def receive(conn: sqlite3.Connection, root: Path | Store, families: Mapping[str, Family], *,
            blob_store: Path | None = None, now: Callable[[], float] = time.time) -> ReceiveResult:
    """Validate and record other devices' packs. Applies nothing."""
    store = as_store(root)
    identity = sync_identity(conn)
    if identity is None:
        raise RuntimeError("sync is not enabled for this profile")
    result = ReceiveResult()
    library = library_rel(identity.library_id)
    devices_rel = f"{library}/devices"
    timestamp = int(now())
    received_before = conn.execute("SELECT count(*) FROM sync_inbox").fetchone()[0]
    for device in sorted(store.listdir(devices_rel), key=lambda entry: entry.name):
        if device.name == identity.device_id:
            continue
        if device.is_symlink:
            result.problems.append(f"{device.name}: symlink not followed")
            continue
        if not device.is_dir or not _IDENTIFIER.match(device.name):
            continue
        device_rel = f"{devices_rel}/{device.name}"
        inside = {entry.name: entry for entry in store.listdir(device_rel)}
        _record_peer(conn, store, device_rel, device.name, inside, timestamp, result.problems)
        packs = inside.get("packs")
        if packs is not None and packs.is_symlink:
            result.problems.append(f"{device.name}/packs: symlink not followed")
            continue
        if packs is None or not packs.is_dir:
            continue
        names = []
        for entry in store.listdir(f"{device_rel}/packs"):
            match = _PACK_NAME.match(entry.name)
            if match:
                names.append((int(match[1]), int(match[2]), match[3], entry))
        # A rejection only stands for the format it was judged under: an upgrade reads the pack again.
        seen = {row[0] for row in conn.execute(
            "SELECT name FROM sync_seen_packs WHERE device=? AND (outcome='accepted' OR format=?)",
            (device.name, SYNC_FORMAT))}
        for epoch, first_seq, digest, entry in sorted(names, key=lambda item: item[:2]):
            label = f"{device.name}/{entry.name}"
            if entry.name in seen:
                continue  # immutable and named by its hash: already accepted or rejected
            if entry.is_symlink or entry.is_dir:
                result.problems.append(f"{label}: not a regular file (symlink not followed)")
                result.rejected += 1
                continue
            if entry.size > MAX_PACK_BYTES:
                result.problems.append(f"{label}: size exceeds {MAX_PACK_BYTES} bytes")
                result.rejected += 1
                continue
            try:
                data = store.read(f"{device_rel}/packs/{entry.name}", MAX_PACK_BYTES)
            except StoreError:
                result.problems.append(f"{label}: size exceeds {MAX_PACK_BYTES} bytes")
                result.rejected += 1
                continue
            if data is None:
                continue  # removed while we were looking
            if sha256_bytes(data) != digest:
                result.incomplete += 1
                continue
            try:
                revisions = _validate(_parse(data), library_id=identity.library_id, device_dir=device.name,
                                      epoch=epoch, first_seq=first_seq, families=families)
                _store(conn, revisions, device=device.name, epoch=epoch, now=timestamp)
                _remember(conn, device.name, entry.name, "accepted", timestamp)
            except PackError as exc:
                result.problems.append(f"{label}: {exc}")
                result.rejected += 1
                _remember(conn, device.name, entry.name, "rejected", timestamp)
    fetch = None if blob_store is None else (lambda sha: fetch_exchange_blob(store, library, sha, blob_store))
    release_waiting(conn, timestamp, blob_store=blob_store, fetch=fetch)
    result.received = conn.execute("SELECT count(*) FROM sync_inbox").fetchone()[0] - received_before
    return result
