"""Apply received revisions to the profile's saved state.

See docs/architecture/shared-folder-sync.md §5 and §6 (step 5).

Each revision is applied in its own ``BEGIN IMMEDIATE`` transaction, which
also updates the baseline, the inbox outcome and the receipt: a crash leaves
it either fully applied or untouched, and an applied value is never captured
again as a local edit.

Before deciding, the live value is compared with the baseline. A difference
is a local edit that sync has not captured yet; it is captured first, so the
incoming revision becomes concurrent with it instead of overwriting it.

Order comes from ancestry only:

* the incoming revision descends from every current head: fast-forward;
* it is already an ancestor of (or equal to) a head: nothing to do;
* otherwise it is concurrent. Equal values merge into a deterministic merge
  revision that every device computes identically (device ``~merge``, never
  published, so merging cannot loop); different values open a conflict that
  keeps the local value until the user resolves it.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

try:
    from .sync_capture import (
        CardResolver, SyncIdentity, record_local_revision, revision_id, set_baseline, stored_hash, sync_identity,
    )
    from .sync_anki import deleted_after
    from .sync_blobs import has_blob
    from .sync_exchange import release_waiting
    from .sync_records import SYNC_FORMAT, CardRef, Family, canonical_json
except ImportError:
    from sync_capture import (  # type: ignore[no-redef]
        CardResolver, SyncIdentity, record_local_revision, revision_id, set_baseline, stored_hash, sync_identity,
    )
    from sync_anki import deleted_after  # type: ignore[no-redef]
    from sync_blobs import has_blob  # type: ignore[no-redef]
    from sync_exchange import release_waiting  # type: ignore[no-redef]
    from sync_records import SYNC_FORMAT, CardRef, Family, canonical_json  # type: ignore[no-redef]

MERGE_DEVICE = "~merge"
#: Upper bound on revisions visited by one ancestry check.
MAX_ANCESTRY_VISITS = 100_000
#: Revisions applied per transaction: each batch commits as a whole or not at all.
APPLY_BATCH = 200
_TERMINAL = ("applied", "conflict", "rejected", "obsolete")
_COUNTERS = {"applied": "applied", "merged": "merged", "ignored": "ignored", "conflict": "conflicts",
             "pending_anki": "pending_anki", "rejected": "rejected", "obsolete": "obsolete",
             "pending_blob": "pending_blob"}


@dataclass
class ApplyResult:
    applied: int = 0
    merged: int = 0
    ignored: int = 0
    conflicts: int = 0
    pending_anki: int = 0
    rejected: int = 0
    obsolete: int = 0
    pending_blob: int = 0


@dataclass(frozen=True)
class _Revision:
    id: str
    family: str
    key: str
    parents: list[str]
    device: str
    epoch: int
    seq: int
    value: dict[str, Any] | None
    deps: dict[str, Any]


def _load(conn: sqlite3.Connection, revision: str) -> _Revision:
    row = conn.execute("SELECT id, family, key, parents, device, epoch, seq, value, deps FROM sync_revisions "
                       "WHERE id=?", (revision,)).fetchone()
    return _Revision(row[0], row[1], row[2], json.loads(row[3]), row[4], row[5], row[6],
                     None if row[7] is None else json.loads(row[7]), json.loads(row[8]))


def is_ancestor(conn: sqlite3.Connection, ancestor: str, revision: str) -> bool:
    """Whether ``ancestor`` is reachable from ``revision`` through parents (not itself)."""
    frontier = [revision]
    seen = {revision}
    while frontier:
        current = frontier.pop()
        row = conn.execute("SELECT parents FROM sync_revisions WHERE id=?", (current,)).fetchone()
        if row is None:
            continue
        for parent in json.loads(row[0]):
            if parent == ancestor:
                return True
            if parent not in seen:
                seen.add(parent)
                if len(seen) > MAX_ANCESTRY_VISITS:
                    raise RuntimeError("revision history too deep to compare")
                frontier.append(parent)
    return False


def _open_conflict(conn: sqlite3.Connection, family: str, key: str) -> tuple[int, list[str]] | None:
    row = conn.execute("SELECT id, heads FROM sync_conflicts WHERE family=? AND key=? AND resolved_revision IS NULL",
                       (family, key)).fetchone()
    return None if row is None else (row[0], json.loads(row[1]))


def _close_conflict(conn: sqlite3.Connection, family: str, key: str, resolution: str) -> None:
    conn.execute("UPDATE sync_conflicts SET resolved_revision=? WHERE family=? AND key=? AND resolved_revision IS NULL",
                 (resolution, family, key))


def _set_live(conn: sqlite3.Connection, family: Family, key: str, value: dict[str, Any] | None) -> None:
    if value is None:
        family.delete(conn, key)
    else:
        family.write(conn, key, value)


def _merge_revision(conn: sqlite3.Connection, identity: SyncIdentity, family: str, key: str,
                    heads: list[_Revision], timestamp: int) -> str:
    """The deterministic merge of equal-valued heads, recorded if new."""
    parents = sorted(head.id for head in heads)
    first = min(heads, key=lambda head: head.id)
    merge = revision_id(library=identity.library_id, family=family, key=key, parents=parents, device=MERGE_DEVICE,
                        epoch=1, seq=0, deleted=first.value is None, value=first.value, deps=first.deps,
                        format=SYNC_FORMAT)
    conn.execute(
        "INSERT OR IGNORE INTO sync_revisions(id, family, key, parents, device, epoch, seq, deleted, value, deps, "
        "format, created_at) VALUES (?, ?, ?, ?, ?, 1, 0, ?, ?, ?, ?, ?)",
        (merge, family, key, canonical_json(parents), MERGE_DEVICE, int(first.value is None),
         None if first.value is None else canonical_json(first.value), canonical_json(first.deps), SYNC_FORMAT,
         timestamp))
    return merge


def _integrate(conn: sqlite3.Connection, identity: SyncIdentity, family: Family, incoming: _Revision,
               card: CardRef | None, timestamp: int) -> str:
    """Decide and apply one revision inside the caller's transaction. Returns the outcome."""
    key = incoming.key
    base = conn.execute("SELECT revision_id, value_hash FROM sync_baseline WHERE family=? AND key=?",
                        (family.name, key)).fetchone()
    live = family.read(conn, key)
    if (base is None and live is not None) or (base is not None and base[1] != stored_hash(family, live)):
        # A saved edit sync has not captured yet: capture it so it is not overwritten.
        local = record_local_revision(conn, identity, family, key, [base[0]] if base else [], live, card, timestamp)
        base = (local, stored_hash(family, live))
    conflict = _open_conflict(conn, family.name, key)
    heads = conflict[1] if conflict else ([base[0]] if base else [])

    if any(head == incoming.id or is_ancestor(conn, incoming.id, head) for head in heads):
        return "ignored"
    remaining = [head for head in heads if not is_ancestor(conn, head, incoming.id)]
    if not remaining:
        _set_live(conn, family, key, incoming.value)
        set_baseline(conn, family, key, incoming.id, incoming.value)
        _close_conflict(conn, family.name, key, incoming.id)
        return "applied"

    contenders = [_load(conn, head) for head in remaining] + [incoming]
    if len({stored_hash(family, revision.value) for revision in contenders}) == 1:
        merge = _merge_revision(conn, identity, family.name, key, contenders, timestamp)
        _set_live(conn, family, key, incoming.value)
        set_baseline(conn, family, key, merge, incoming.value)
        _close_conflict(conn, family.name, key, merge)
        return "merged"

    if base is not None and base[0] not in remaining:
        # The local line was continued remotely; follow it while the other head stays in conflict.
        _set_live(conn, family, key, incoming.value)
        set_baseline(conn, family, key, incoming.id, incoming.value)
    new_heads = canonical_json(sorted(remaining + [incoming.id]))
    if conflict:
        conn.execute("UPDATE sync_conflicts SET heads=? WHERE id=?", (new_heads, conflict[0]))
    else:
        conn.execute("INSERT INTO sync_conflicts(family, key, heads, created_at) VALUES (?, ?, ?, ?)",
                     (family.name, key, new_heads, timestamp))
    return "conflict"


def _update_receipt(conn: sqlite3.Connection, peer: str, epoch: int) -> None:
    row = conn.execute("SELECT max_seq FROM sync_receipts WHERE peer=? AND epoch=?", (peer, epoch)).fetchone()
    current = row[0] if row else 0
    while conn.execute(
            "SELECT 1 FROM sync_revisions r JOIN sync_inbox i ON i.revision_id = r.id "
            f"WHERE r.device=? AND r.epoch=? AND r.seq=? AND i.status IN ({','.join('?' * len(_TERMINAL))})",
            (peer, epoch, current + 1, *_TERMINAL)).fetchone():
        current += 1
    conn.execute("INSERT OR REPLACE INTO sync_receipts(peer, epoch, max_seq) VALUES (?, ?, ?)", (peer, epoch, current))


def _set_status(conn: sqlite3.Connection, revision: str, status: str, reason: str, timestamp: int) -> None:
    conn.execute("UPDATE sync_inbox SET status=?, reason=?, updated_at=? WHERE revision_id=?",
                 (status, reason[:500], timestamp, revision))


def _peer_anki_state(conn: sqlite3.Connection, device: str) -> tuple[int | None, int | None]:
    row = conn.execute("SELECT anki_usn, anki_scm FROM sync_peers WHERE device=?", (device,)).fetchone()
    return (None, None) if row is None else (row[0], row[1])


def apply(conn: sqlite3.Connection, families: Mapping[str, Family], resolve_cards: CardResolver, *,
          collection_usn: int | None = None, collection_scm: int | None = None,
          blob_store: Path | None = None,
          now: Callable[[], float] = time.time) -> ApplyResult:
    """Apply received revisions.

    ``collection_usn`` is this collection's usn after its last AnkiWeb sync.
    Without it, a revision whose card is absent always waits; with it, one
    whose card this device must already have downloaded is obsolete (§7).
    """
    identity = sync_identity(conn)
    if identity is None:
        raise RuntimeError("sync is not enabled for this profile")
    timestamp = int(now())
    result = ApplyResult()
    handled: set[str] = set()
    while True:
        waiting = [_load(conn, row[0]) for row in conn.execute(
            "SELECT i.revision_id FROM sync_inbox i JOIN sync_revisions r ON r.id = i.revision_id "
            "WHERE i.status IN ('received', 'pending_anki') ORDER BY r.device, r.epoch, r.seq")
            if row[0] not in handled]
        if not waiting:
            break
        card_ids = {found for revision in waiting
                    if revision.family in families
                    and (found := families[revision.family].card_id(revision.key)) is not None}
        cards = resolve_cards(sorted(card_ids))
        for batch_start in range(0, len(waiting), APPLY_BATCH):
            batch = waiting[batch_start:batch_start + APPLY_BATCH]
            outcomes = []
            conn.execute("BEGIN IMMEDIATE")
            try:
                for incoming in batch:
                    family = families.get(incoming.family)
                    card_id = family.card_id(incoming.key) if family is not None else None
                    card = cards.get(card_id) if card_id is not None else None
                    expected = incoming.deps.get("card") or {}
                    missing_blobs = [sha for sha in incoming.deps.get("blobs", []) if not has_blob(blob_store, sha)]
                    if family is None:
                        outcome, reason = "rejected", "unknown family"
                    elif missing_blobs:
                        outcome, reason = "pending_blob", "file not received yet"
                    elif card_id is not None and card is None:
                        peer_usn, peer_scm = _peer_anki_state(conn, incoming.device)
                        threshold = deleted_after(expected, peer_usn, sender_anki_scm=peer_scm,
                                                  receiver_scm=collection_scm)
                        if collection_usn is not None and threshold is not None and collection_usn > threshold:
                            outcome, reason = "obsolete", "card deleted before this device synced"
                        else:
                            outcome, reason = "pending_anki", "card not in the collection yet"
                    elif card is not None and (card.guid, card.note_id) != (expected.get("guid"), expected.get("note_id")):
                        outcome, reason = "rejected", "card belongs to another note"
                    else:
                        outcome = _integrate(conn, identity, family, incoming, card, timestamp)
                        reason = "already included" if outcome == "ignored" else ""
                    status = {"ignored": "applied", "merged": "applied"}.get(outcome, outcome)
                    _set_status(conn, incoming.id, status, reason, timestamp)
                    if status in _TERMINAL:
                        _update_receipt(conn, incoming.device, incoming.epoch)
                    outcomes.append((incoming.id, outcome))
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            for revision, outcome in outcomes:
                handled.add(revision)
                counter = _COUNTERS[outcome]
                setattr(result, counter, getattr(result, counter) + 1)

        if not release_waiting(conn, timestamp, blob_store=blob_store):
            break
    return result


def resolve_conflict(conn: sqlite3.Connection, conflict_id: int, value: dict[str, Any] | None,
                     families: Mapping[str, Family], resolve_cards: CardResolver, *,
                     now: Callable[[], float] = time.time) -> str:
    """Settle an open conflict with ``value`` (None deletes); the resolution descends from every head."""
    identity = sync_identity(conn)
    if identity is None:
        raise RuntimeError("sync is not enabled for this profile")
    row = conn.execute("SELECT family, key, heads FROM sync_conflicts WHERE id=? AND resolved_revision IS NULL",
                       (conflict_id,)).fetchone()
    if row is None:
        raise ValueError(f"no open conflict {conflict_id}")
    family_name, key, heads = row
    family = families[family_name]
    family.validate(key, value)
    card_id = family.card_id(key)
    card = resolve_cards([card_id]).get(card_id) if card_id is not None else None
    timestamp = int(now())
    conn.execute("BEGIN IMMEDIATE")
    try:
        _set_live(conn, family, key, value)
        resolution = record_local_revision(conn, identity, family, key, json.loads(heads), value, card, timestamp)
        conn.execute("UPDATE sync_conflicts SET resolved_revision=? WHERE id=?", (resolution, conflict_id))
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return resolution
