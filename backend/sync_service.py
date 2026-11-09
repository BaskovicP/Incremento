"""What the desktop calls: set up, run, inspect and settle shared-folder sync for a profile.

See docs/architecture/shared-folder-sync.md §7 (order of operations) and §8.

The chosen folder is stored per profile in ``sync_meta``, beside the
library and device identity, rather than in the add-on-wide config. One sync
runs at a time per profile; a sync checks between steps that its profile is
still the current one and stops otherwise. ``query`` has the shape of Anki's
``col.db.all`` and is only read from.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from . import paths
    from .db import get_connection as _host_connection
    from .sync_schema import ensure_schema
    from .sync_anki import Query, card_refs, collection_scm, collection_usn
    from .sync_apply import _update_receipt, apply, resolve_conflict
    from .sync_capture import adopt_new_device_identity, capture, enable_sync, sync_identity
    from .sync_documents import DocumentFamily
    from .sync_exchange import EXCHANGE_DIR, announce, publish, receive, release_waiting, sample_card_refs
    from .sync_snapshot import catch_up, history_complete, retire_packs, sweep_blobs, write_snapshot_if_due
    from .sync_store import LocalStore, Store, StoreError, as_store
    from .sync_records import FAMILIES, Family
except ImportError:
    import paths  # type: ignore[no-redef]
    from db import get_connection as _host_connection  # type: ignore[no-redef]
    from sync_schema import ensure_schema  # type: ignore[no-redef]
    from sync_anki import Query, card_refs, collection_scm, collection_usn  # type: ignore[no-redef]
    from sync_apply import _update_receipt, apply, resolve_conflict  # type: ignore[no-redef]
    from sync_capture import (  # type: ignore[no-redef]
        adopt_new_device_identity, capture, enable_sync, sync_identity,
    )
    from sync_documents import DocumentFamily  # type: ignore[no-redef]
    from sync_exchange import (  # type: ignore[no-redef]
        EXCHANGE_DIR, announce, publish, receive, release_waiting, sample_card_refs,
    )
    from sync_snapshot import (  # type: ignore[no-redef]
        catch_up, history_complete, retire_packs, sweep_blobs, write_snapshot_if_due,
    )
    from sync_store import LocalStore, Store, StoreError, as_store  # type: ignore[no-redef]
    from sync_records import FAMILIES, Family  # type: ignore[no-redef]


#: Write a snapshot after this many revisions published or integrated since the last one ...
SNAPSHOT_EVERY_REVISIONS = 1000
#: ... or after this long, if anything changed at all.
SNAPSHOT_MAX_AGE_SECONDS = 7 * 86400
#: Unreferenced exchange blobs are swept once older than this, at most once per interval.
BLOB_GRACE_SECONDS = 30 * 86400
SWEEP_INTERVAL_SECONDS = 86400
#: Changes waiting this long for a card, file or parent may be discarded by the user.
STALE_WAITING_SECONDS = 30 * 86400
_WAITING = ("pending_anki", "pending_blob", "pending_parent")


class SyncSetupError(RuntimeError):
    """The chosen folder cannot be used; the message says why."""


@dataclass(frozen=True)
class SetupResult:
    library_id: str
    device_id: str
    created: bool


@dataclass
class SyncReport:
    skipped: str | None = None
    captured: int = 0
    published: int = 0
    received: int = 0
    applied: int = 0
    conflicts: int = 0
    problems: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SyncStatus:
    configured: bool
    folder: str | None
    last_sync: int | None
    conflicts: int
    waiting_for_anki: int
    waiting_for_files: int
    waiting_for_parents: int
    #: Changes that have waited longer than STALE_WAITING_SECONDS.
    stale_waiting: int = 0


@dataclass(frozen=True)
class Conflict:
    id: int
    family: str
    key: str
    heads: list[str]
    values: list[dict[str, Any] | None]
    #: Which of ``values`` this computer has now.
    local_index: int


_locks: dict[tuple[str, str], threading.Lock] = {}
_locks_guard = threading.Lock()
_document_families: dict[tuple[str, str], DocumentFamily] = {}


def families_for(addon_dir: str, profile: str) -> dict[str, Family]:
    with _locks_guard:
        documents = _document_families.setdefault((addon_dir, profile), DocumentFamily(addon_dir, profile))
    return {**FAMILIES, "document": documents}


def _meta(conn: Any, key: str) -> str | None:
    row = conn.execute("SELECT value FROM sync_meta WHERE key=?", (key,)).fetchone()
    return None if row is None else row[0]


def _set_meta(conn: Any, key: str, value: str | None) -> None:
    with conn:
        if value is None:
            conn.execute("DELETE FROM sync_meta WHERE key=?", (key,))
        else:
            conn.execute("INSERT OR REPLACE INTO sync_meta(key, value) VALUES (?, ?)", (key, value))


def get_connection(addon_dir: str, profile: str) -> Any:
    """The profile's database with the sync tables in place, whether or not the host's migrations made them."""
    conn = _host_connection(addon_dir, profile)
    ensure_schema(conn)
    return conn


def libraries_in(root: Path | str | Store) -> list[str]:
    """Library ids found in an exchange folder (each with a matching library.json)."""
    store = as_store(root)
    found: list[str] = []
    try:
        entries = sorted(store.listdir("/".join(EXCHANGE_DIR)), key=lambda entry: entry.name)
    except StoreError:
        return found
    for entry in entries:
        if entry.is_symlink or not entry.is_dir:
            continue
        rel = "/".join((*EXCHANGE_DIR, entry.name, "library.json"))
        descriptor = store.stat(rel)
        if descriptor is None or descriptor.is_dir or descriptor.size > 4096:
            continue
        try:
            data = store.read(rel, 4096)
            if data is not None and json.loads(data.decode("utf-8")).get("library_id") == entry.name:
                found.append(entry.name)
        except (ValueError, OSError):
            continue
    return found


def _check_same_collection(folder: Path | Store, library_id: str, query: Query) -> None:
    """Refuse to join a library whose cards belong to another Anki collection."""
    sample = sample_card_refs(folder, library_id)
    if not sample:
        return
    present = card_refs(query, sample)
    if any(ref.guid != sample[card_id] for card_id, ref in present.items()):
        raise SyncSetupError("This folder's Incremento library belongs to another Anki collection.")
    if not present:
        raise SyncSetupError("None of this library's cards are in this Anki collection yet. "
                             "Sync with AnkiWeb first, then choose the folder again.")


def configure(addon_dir: str, profile: str, folder: str, *, query: Query | None = None,
              store: Store | None = None) -> SetupResult:
    """Use ``folder`` for this profile: join the library in it, or start one.

    With ``query`` (the collection's ``col.db.all``), joining an existing
    library first checks that its cards are this collection's. ``folder`` is a
    directory, or, when a ``store`` is given (Android's document provider, a
    LAN hub), only the label under which that store is remembered.
    """
    if store is None:
        path = Path(folder)
        if not path.is_dir():
            raise SyncSetupError(f"The folder {folder} does not exist.")
        store = LocalStore(path)
    conn = get_connection(addon_dir, profile)
    libraries = libraries_in(store)
    identity = sync_identity(conn)
    created = False
    if identity is not None:
        if ensure_device_binding(addon_dir, profile):
            identity = sync_identity(conn)
            assert identity is not None
        if libraries and identity.library_id not in libraries:
            raise SyncSetupError("This folder holds another Incremento library than this profile's.")
    elif len(libraries) > 1:
        raise SyncSetupError("This folder holds several Incremento libraries; choose a folder with one.")
    else:
        if libraries and query is not None:
            _check_same_collection(store, libraries[0], query)
        identity = enable_sync(conn, library_id=libraries[0] if libraries else None)
        created = not libraries
    _bind(addon_dir, profile, identity.device_id)
    _set_meta(conn, "folder", str(folder))
    publish(conn, store)  # announces the library and this device
    return SetupResult(identity.library_id, identity.device_id, created)


def _binding_path(addon_dir: str, profile: str) -> Path:
    """Which device identity this installation owns. Lives beside the blob store, outside backups."""
    return paths.get_sync_dir(addon_dir, profile) / "device-binding.json"


def _bind(addon_dir: str, profile: str, device_id: str) -> None:
    path = _binding_path(addon_dir, profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps({"device_id": device_id}), encoding="utf-8")
    temporary.replace(path)


def ensure_device_binding(addon_dir: str, profile: str) -> bool:
    """Take a new device identity if the database came from a backup or another computer.

    The binding file is not part of backups, so a restored or copied database
    no longer matches it. Returns whether a new identity was adopted.
    """
    conn = get_connection(addon_dir, profile)
    identity = sync_identity(conn)
    if identity is None:
        return False
    try:
        bound = json.loads(_binding_path(addon_dir, profile).read_text("utf-8")).get("device_id")
    except (OSError, ValueError, AttributeError):
        bound = None
    if bound == identity.device_id:
        return False
    _bind(addon_dir, profile, adopt_new_device_identity(conn).device_id)
    return True


def disable(addon_dir: str, profile: str) -> None:
    """Stop syncing this profile. Its identity stays, so it can resume where it left off."""
    _set_meta(get_connection(addon_dir, profile), "folder", None)


def _lock(addon_dir: str, profile: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault((addon_dir, profile), threading.Lock())


def _run(addon_dir: str, profile: str, folder: Store, query: Query, is_current: Callable[[], bool],
         now: Callable[[], float], *, publish_only: bool = False) -> SyncReport:
    conn = get_connection(addon_dir, profile)
    families = families_for(addon_dir, profile)
    store = paths.get_sync_blob_dir(addon_dir, profile)
    usn, scm = collection_usn(query), collection_scm(query)
    state = f"{scm}:{query('SELECT mod FROM col')[0][0]}"

    def resolver(card_ids: Any) -> Any:
        return card_refs(query, card_ids)

    report = SyncReport()
    steps: list[Callable[[], None]] = [
        lambda: setattr(report, "captured", report.captured + capture(conn, families, resolver, now=now, collection_state=state).captured),
        lambda: setattr(report, "published", report.published + publish(
            conn, folder, anki_usn=usn, anki_scm=scm, blob_store=store, now=now).revisions_published),
        lambda: _catch_up(conn, folder, families, now),
        lambda: _receive(report, receive(conn, folder, families, blob_store=store, now=now)),
        lambda: _apply(report, apply(conn, families, resolver, collection_usn=usn, collection_scm=scm, blob_store=store,
                                    now=now)),
        # Parents that lived only in retired packs can no longer arrive: judge their children now.
        lambda: _release_retired(report, conn, folder, store, lambda: apply(
            conn, families, resolver, collection_usn=usn, collection_scm=scm, blob_store=store, now=now), now),
        # Local edits protected during apply are published in the same run.
        lambda: setattr(report, "captured", report.captured + capture(conn, families, resolver, now=now, collection_state=state).captured),
        lambda: setattr(report, "published", report.published + publish(
            conn, folder, anki_usn=usn, anki_scm=scm, blob_store=store, now=now).revisions_published),
    ]
    steps.append(lambda: _maintain(conn, folder, usn, scm, now))
    if publish_only:
        steps = steps[:2]
    for step in steps:
        if not is_current():
            report.skipped = "profile changed"
            return report
        step()
    if not publish_only:
        _set_meta(conn, "last_sync", str(int(now())))
    return report


def _catch_up(conn: Any, folder: Store, families: dict[str, Family], now: Callable[[], float]) -> None:
    catch_up(conn, folder, families, now=now())


def _release_retired(report: SyncReport, conn: Any, folder: Store, store: Path, apply_again: Callable[[], Any],
                     now: Callable[[], float]) -> None:
    if history_complete(conn, folder) and release_waiting(conn, int(now()), blob_store=store,
                                                          parents_may_be_retired=True):
        _apply(report, apply_again())


def _maintain(conn: Any, folder: Store, usn: int, scm: int, now: Callable[[], float]) -> None:
    """Snapshot when due, retire covered packs, announce progress, and now and then sweep blobs."""
    identity = sync_identity(conn)
    assert identity is not None
    timestamp = now()
    write_snapshot_if_due(conn, folder, every=SNAPSHOT_EVERY_REVISIONS, max_age=SNAPSHOT_MAX_AGE_SECONDS,
                          now=timestamp)
    retire_packs(conn, folder)
    announce(conn, folder, anki_usn=usn, anki_scm=scm)
    swept_at = float(_meta(conn, "swept_at") or 0)
    if timestamp - swept_at >= SWEEP_INTERVAL_SECONDS:
        sweep_blobs(folder, identity.library_id, now=timestamp, grace_seconds=BLOB_GRACE_SECONDS)
        _set_meta(conn, "swept_at", str(timestamp))


def sweep_blobs_now(folder: Path | Store, library_id: str, *, now: float) -> int:
    return sweep_blobs(folder, library_id, now=now, grace_seconds=BLOB_GRACE_SECONDS)


def _receive(report: SyncReport, result: Any) -> None:
    report.received += result.received
    report.problems += result.problems


def _apply(report: SyncReport, result: Any) -> None:
    report.applied += result.applied + result.merged
    report.conflicts += result.conflicts


def sync_now(addon_dir: str, profile: str, query: Query, *, is_current: Callable[[], bool] = lambda: True,
             now: Callable[[], float] = time.time, publish_only: bool = False,
             store: Store | None = None) -> SyncReport:
    """Capture, publish, receive and apply. Safe to call from a background worker."""
    conn = get_connection(addon_dir, profile)
    folder = _meta(conn, "folder") if sync_identity(conn) is not None else None
    if folder is None:
        return SyncReport(skipped="not configured")
    lock = _lock(addon_dir, profile)
    if not lock.acquire(blocking=False):
        return SyncReport(skipped="already running")
    try:
        ensure_device_binding(addon_dir, profile)
        return _run(addon_dir, profile, store or LocalStore(Path(folder)), query, is_current, now, publish_only=publish_only)
    finally:
        lock.release()


def publish_now(addon_dir: str, profile: str, query: Query, *,
                now: Callable[[], float] = time.time, store: Store | None = None) -> SyncReport:
    """Capture and publish only: quick, for a closing profile. Nothing received is applied."""
    return sync_now(addon_dir, profile, query, now=now, publish_only=True, store=store)


def status(addon_dir: str, profile: str, *, now: float | None = None) -> SyncStatus:
    conn = get_connection(addon_dir, profile)
    cutoff = (time.time() if now is None else now) - STALE_WAITING_SECONDS
    stale = conn.execute(f"SELECT count(*) FROM sync_inbox WHERE status IN ({','.join('?' * len(_WAITING))}) "
                         "AND received_at < ?", (*_WAITING, cutoff)).fetchone()[0]
    configured = sync_identity(conn) is not None and _meta(conn, "folder") is not None
    counts = dict(conn.execute("SELECT status, count(*) FROM sync_inbox GROUP BY status").fetchall())
    last = _meta(conn, "last_sync")
    open_conflicts = conn.execute("SELECT count(*) FROM sync_conflicts WHERE resolved_revision IS NULL").fetchone()[0]
    return SyncStatus(configured=configured, folder=_meta(conn, "folder"),
                      last_sync=int(last) if last is not None else None, conflicts=open_conflicts,
                      waiting_for_anki=counts.get("pending_anki", 0), waiting_for_files=counts.get("pending_blob", 0),
                      waiting_for_parents=counts.get("pending_parent", 0), stale_waiting=stale)


def discard_stale(addon_dir: str, profile: str, *, now: float | None = None) -> int:
    """Give up on changes that waited too long; they were never applied, so nothing here changes.

    They become obsolete, so they no longer hold back receipts and retention.
    """
    conn = get_connection(addon_dir, profile)
    cutoff = (time.time() if now is None else now) - STALE_WAITING_SECONDS
    timestamp = int(time.time() if now is None else now)
    with conn:
        rows = conn.execute(f"SELECT i.revision_id, r.device, r.epoch FROM sync_inbox i "
                            f"JOIN sync_revisions r ON r.id = i.revision_id "
                            f"WHERE i.status IN ({','.join('?' * len(_WAITING))}) AND i.received_at < ?",
                            (*_WAITING, cutoff)).fetchall()
        for revision, _, _ in rows:
            conn.execute("UPDATE sync_inbox SET status='obsolete', reason='discarded after waiting', updated_at=? "
                         "WHERE revision_id=?", (timestamp, revision))
        for device, epoch in {(device, epoch) for _, device, epoch in rows}:
            _update_receipt(conn, device, epoch)
    return len(rows)


def open_conflicts(addon_dir: str, profile: str) -> list[Conflict]:
    conn = get_connection(addon_dir, profile)
    conflicts = []
    for conflict_id, family, key, heads in conn.execute(
            "SELECT id, family, key, heads FROM sync_conflicts WHERE resolved_revision IS NULL ORDER BY id"):
        head_ids = json.loads(heads)
        values = []
        for head in head_ids:
            row = conn.execute("SELECT value FROM sync_revisions WHERE id=?", (head,)).fetchone()
            values.append(None if row is None or row[0] is None else json.loads(row[0]))
        base = conn.execute("SELECT revision_id FROM sync_baseline WHERE family=? AND key=?", (family, key)).fetchone()
        local = head_ids.index(base[0]) if base is not None and base[0] in head_ids else 0
        conflicts.append(Conflict(conflict_id, family, key, head_ids, values, local))
    return conflicts


def resolve(addon_dir: str, profile: str, conflict_id: int, value: dict[str, Any] | None, query: Query, *,
            now: Callable[[], float] = time.time) -> str:
    """Settle a conflict with the chosen value; published by the next sync."""
    conn = get_connection(addon_dir, profile)
    return resolve_conflict(conn, conflict_id, value, families_for(addon_dir, profile),
                            lambda card_ids: card_refs(query, card_ids), now=now)
