"""Capture: turn saved Incremento state into immutable sync revisions.

See docs/architecture/shared-folder-sync.md §4 and §6 (steps 1-2).

1. Each family is scanned in one read transaction, a consistent snapshot.
   A family that cannot be read completely aborts the capture, so a failed
   scan never looks like an empty family and never produces deletions.
2. Records whose value hash differs from the baseline are re-read inside one
   ``BEGIN IMMEDIATE`` transaction, so an edit saved after the scan is captured
   with its live value. Revisions, outbox rows, baseline updates and the next
   sequence number commit together: a crash leaves either nothing (the change
   is found again by the next scan) or a complete pending publication.

Records whose Anki card is unknown to the collection are not captured and
not tombstoned; Anki's own sync and Incremento's reconciliation own card
deletion (§5, §7).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

try:
    from .sync_records import (
        SYNC_FORMAT, CardRef, Family, SyncScanError, canonical_json, record_blobs, record_hash,
    )
except ImportError:
    from sync_records import (  # type: ignore[no-redef]
        SYNC_FORMAT, CardRef, Family, SyncScanError, canonical_json, record_blobs, record_hash,
    )

#: Resolves card ids to the cards present in the Anki collection; absent ids
#: are left out of the result.
CardResolver = Callable[[Iterable[int]], Mapping[int, CardRef]]


class SyncNotEnabledError(RuntimeError):
    """Sync has not been set up for this profile."""


@dataclass(frozen=True)
class SyncIdentity:
    library_id: str
    device_id: str
    epoch: int


@dataclass(frozen=True)
class CaptureResult:
    captured: int
    skipped_missing_cards: int


def _meta(conn: sqlite3.Connection) -> dict[str, str]:
    return dict(conn.execute("SELECT key, value FROM sync_meta").fetchall())


def sync_identity(conn: sqlite3.Connection) -> SyncIdentity | None:
    meta = _meta(conn)
    if "library_id" not in meta:
        return None
    return SyncIdentity(meta["library_id"], meta["device_id"], int(meta["epoch"]))


def _begin_immediate(conn: sqlite3.Connection) -> None:
    if conn.in_transaction:
        raise RuntimeError("sync work started inside an open transaction")
    conn.execute("BEGIN IMMEDIATE")


def enable_sync(conn: sqlite3.Connection, *, make_id: Callable[[], str] = lambda: uuid.uuid4().hex,
                library_id: str | None = None) -> SyncIdentity:
    """Create this profile's identity once; later calls return it.

    Without ``library_id`` the profile starts a new library; with it, the
    profile joins that existing library as a new device.
    """
    _begin_immediate(conn)
    try:
        existing = sync_identity(conn)
        if existing is None:
            library_id = library_id or make_id()
            device_id = make_id()
            conn.executemany("INSERT INTO sync_meta(key, value) VALUES (?, ?)", [
                ("library_id", library_id), ("device_id", device_id), ("epoch", "1"), ("next_seq", "1"),
                ("format", str(SYNC_FORMAT)),
            ])
            existing = SyncIdentity(library_id, device_id, 1)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return existing


def adopt_new_device_identity(conn: sqlite3.Connection, *,
                              make_id: Callable[[], str] = lambda: uuid.uuid4().hex) -> SyncIdentity:
    """Give this profile a new device identity in the same library.

    For a database restored from a backup or copied from another computer:
    its old identity's sequence numbers may already be used, or the identity
    may still be another device's. Revisions captured under the old identity
    but never published are re-issued under the new one, in order, and every
    reference to them (children, baseline, conflicts) follows. The old
    identity becomes an ordinary peer, so its published later work is received
    back and fast-forwards.
    """
    _begin_immediate(conn)
    try:
        old = sync_identity(conn)
        if old is None:
            raise SyncNotEnabledError("sync is not enabled for this profile")
        new = SyncIdentity(old.library_id, make_id(), 1)
        conn.executemany("UPDATE sync_meta SET value=? WHERE key=?",
                         [(new.device_id, "device_id"), ("1", "epoch"), ("1", "next_seq")])
        # The new identity has published nothing and retired nothing yet.
        conn.execute("DELETE FROM sync_meta WHERE key IN ('published_through', 'retired_through', "
                     "'snapshot_seq', 'snapshot_progress', 'snapshot_at')")
        pending = conn.execute(
            "SELECT r.id, r.family, r.key, r.parents, r.deleted, r.value, r.deps, r.created_at "
            "FROM sync_outbox o JOIN sync_revisions r ON r.id = o.revision_id "
            "WHERE o.published_at IS NULL AND r.device = ? ORDER BY r.epoch, r.seq", (old.device_id,)).fetchall()
        renamed: dict[str, str] = {}
        for seq, (old_id, family, key, parents, deleted, value, deps, created_at) in enumerate(pending, start=1):
            parent_ids = [renamed.get(parent, parent) for parent in json.loads(parents)]
            loaded_value = None if value is None else json.loads(value)
            loaded_deps = json.loads(deps)
            new_id = revision_id(library=new.library_id, family=family, key=key, parents=parent_ids,
                                 device=new.device_id, epoch=new.epoch, seq=seq, deleted=bool(deleted),
                                 value=loaded_value, deps=loaded_deps, format=SYNC_FORMAT)
            renamed[old_id] = new_id
            conn.execute("DELETE FROM sync_outbox WHERE revision_id=?", (old_id,))
            conn.execute("DELETE FROM sync_revisions WHERE id=?", (old_id,))
            conn.execute(
                "INSERT INTO sync_revisions(id, family, key, parents, device, epoch, seq, deleted, value, deps, "
                "format, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id, family, key, canonical_json(sorted(parent_ids)), new.device_id, new.epoch, seq, deleted,
                 value, deps, SYNC_FORMAT, created_at))
            _enqueue(conn, new_id, created_at)
            conn.execute("UPDATE sync_baseline SET revision_id=? WHERE revision_id=?", (new_id, old_id))
            conn.execute("UPDATE sync_conflicts SET resolved_revision=? WHERE resolved_revision=?", (new_id, old_id))
            conn.execute("UPDATE sync_conflicts SET heads=replace(heads, ?, ?) WHERE instr(heads, ?) > 0",
                         (old_id, new_id, old_id))
            conn.execute("UPDATE sync_revisions SET parents=replace(parents, ?, ?) WHERE instr(parents, ?) > 0",
                         (old_id, new_id, old_id))
        conn.execute("UPDATE sync_meta SET value=? WHERE key='next_seq'", (str(len(pending) + 1),))
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return new


def revision_id(*, library: str, family: str, key: str, parents: list[str], device: str, epoch: int, seq: int,
                deleted: bool, value: Any, deps: Any, format: int) -> str:
    """Content hash of every identifying field; equal content means the same revision."""
    fields = {"library": library, "family": family, "key": key, "parents": sorted(parents), "device": device,
              "epoch": int(epoch), "seq": int(seq), "deleted": bool(deleted), "value": value, "deps": deps,
              "format": int(format)}
    return hashlib.sha256(canonical_json(fields).encode("utf-8")).hexdigest()


def _snapshot(conn: sqlite3.Connection, family: Family,
              collection_state: str) -> tuple[dict[str, dict[str, Any]] | None, str | None]:
    """The family's records in one consistent read, or None when its raw rows match the last capture."""
    if conn.in_transaction:
        raise RuntimeError("sync work started inside an open transaction")
    conn.execute("BEGIN")
    try:
        raw_digest = getattr(family, "raw_digest", None)
        digest = raw_digest(conn) if raw_digest is not None else None
        stored = _meta(conn).get(f"raw_digest:{family.name}")
        # Unchanged rows, and (if some waited for their cards) an unchanged collection: nothing new to capture.
        unchanged = {digest} | ({f"{digest}@{collection_state}"} if collection_state else set())
        if digest is not None and stored is not None and stored in unchanged:
            return None, digest
        records: dict[str, dict[str, Any]] = {}
        for key, value in family.scan(conn):
            if key in records:
                raise SyncScanError(f"{family.name}: duplicate key {key}")
            records[key] = value
    finally:
        conn.rollback()  # read-only: ends the snapshot
    return records, digest


def _baseline(conn: sqlite3.Connection, family: str) -> dict[str, tuple[str, str]]:
    rows = conn.execute("SELECT key, revision_id, value_hash FROM sync_baseline WHERE family=?", (family,))
    return {key: (revision, digest) for key, revision, digest in rows}


def _enqueue(conn: sqlite3.Connection, revision: str, now: int) -> None:
    conn.execute("INSERT INTO sync_outbox(revision_id, enqueued_at) VALUES (?, ?)", (revision, now))


def stored_hash(family: Family, value: dict[str, Any] | None) -> str:
    """The baseline hash of a value; a deleted record hashes to ''."""
    return record_hash(family, value)


def record_local_revision(conn: sqlite3.Connection, identity: SyncIdentity, family: Family, key: str,
                          parents: list[str], value: dict[str, Any] | None, card: CardRef | None,
                          timestamp: int) -> str:
    """Record this device's revision, queue it and make it the baseline.

    Must run inside the caller's ``BEGIN IMMEDIATE`` transaction.
    """
    seq = int(_meta(conn)["next_seq"])
    deps: dict[str, Any] = {"card": card.to_json()} if card is not None else {}
    if blobs := record_blobs(family, value):
        deps["blobs"] = blobs
    revision = revision_id(library=identity.library_id, family=family.name, key=key, parents=parents,
                           device=identity.device_id, epoch=identity.epoch, seq=seq, deleted=value is None,
                           value=value, deps=deps, format=SYNC_FORMAT)
    conn.execute(
        "INSERT INTO sync_revisions(id, family, key, parents, device, epoch, seq, deleted, value, deps, "
        "format, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (revision, family.name, key, canonical_json(sorted(parents)), identity.device_id, identity.epoch, seq,
         int(value is None), None if value is None else canonical_json(value), canonical_json(deps),
         SYNC_FORMAT, timestamp))
    _enqueue(conn, revision, timestamp)
    set_baseline(conn, family, key, revision, value)
    conn.execute("UPDATE sync_meta SET value=? WHERE key='next_seq'", (str(seq + 1),))
    return revision


def set_baseline(conn: sqlite3.Connection, family: Family, key: str, revision: str,
                 value: dict[str, Any] | None) -> None:
    conn.execute("INSERT OR REPLACE INTO sync_baseline(family, key, revision_id, value_hash) VALUES (?, ?, ?, ?)",
                 (family.name, key, revision, stored_hash(family, value)))


def _write_digests(conn: sqlite3.Connection, digests: Mapping[str, str]) -> None:
    conn.executemany("INSERT OR REPLACE INTO sync_meta(key, value) VALUES (?, ?)",
                     [(f"raw_digest:{name}", digest) for name, digest in digests.items()])


def _store_digests(conn: sqlite3.Connection, digests: Mapping[str, str]) -> None:
    if digests:
        _begin_immediate(conn)
        try:
            _write_digests(conn, digests)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise


def capture(conn: sqlite3.Connection, families: Mapping[str, Family], resolve_cards: CardResolver, *,
            now: Callable[[], float] = time.time, collection_state: str = "") -> CaptureResult:
    """Record what changed since the last capture.

    ``collection_state`` identifies the Anki collection's state (it changes
    whenever the collection does). A family with records waiting for their
    cards is skipped while both its rows and this state are unchanged.
    """
    identity = sync_identity(conn)
    if identity is None:
        raise SyncNotEnabledError("sync is not enabled for this profile")

    # 1. Consistent snapshots, then the candidates: changed or vanished records.
    candidates: list[tuple[Family, str]] = []
    digests: dict[str, str] = {}
    for family in families.values():
        scanned, digest = _snapshot(conn, family, collection_state)
        if scanned is None:
            continue  # rows unchanged since the last complete capture
        if digest is not None:
            digests[family.name] = digest
        baseline = _baseline(conn, family.name)
        for key, value in scanned.items():
            if baseline.get(key, (None, None))[1] != record_hash(family, value):
                candidates.append((family, key))
        # Vanished records, except those whose deletion is already the baseline.
        candidates += [(family, key) for key, (_, digest) in baseline.items() if key not in scanned and digest]
    if not candidates:
        _store_digests(conn, digests)
        return CaptureResult(0, 0)
    card_ids = {found for family, key in candidates if (found := family.card_id(key)) is not None}
    cards = resolve_cards(sorted(card_ids))

    # 2. One transaction: re-read live values and record what really changed.
    timestamp = int(now())
    captured = skipped = 0
    _begin_immediate(conn)
    try:
        for family, key in sorted(candidates, key=lambda item: (item[0].name, item[1])):
            base = conn.execute("SELECT revision_id, value_hash FROM sync_baseline WHERE family=? AND key=?",
                                (family.name, key)).fetchone()
            card_id = family.card_id(key)
            card = cards.get(card_id) if card_id is not None else None
            if card_id is not None and card is None:
                skipped += 1
                # Rescan once the collection changes: the card may have arrived.
                if family.name in digests:
                    if collection_state:
                        digests[family.name] = digests[family.name].split("@")[0] + "@" + collection_state
                    else:
                        digests.pop(family.name)
                conn.execute("DELETE FROM sync_baseline WHERE family=? AND key=?", (family.name, key))
                continue
            unavailable = getattr(family, "unavailable", None)
            if unavailable is not None and unavailable(conn, key):
                continue  # e.g. a document whose file is missing: neither changed nor deleted
            live = family.read(conn, key)
            if live is None and base is None:
                continue
            if base is not None and base[1] == stored_hash(family, live):
                continue
            record_local_revision(conn, identity, family, key, [base[0]] if base is not None else [], live, card,
                                  timestamp)
            captured += 1
        _write_digests(conn, digests)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return CaptureResult(captured, skipped)
