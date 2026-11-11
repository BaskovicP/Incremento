"""Shared-folder exchange contract (docs/architecture/shared-folder-sync.md §6 steps 3-4, §8; scenarios 6, 9, 14).

Two disposable profile databases stand for two devices; a temporary folder
stands for the cloud-synced exchange folder.
"""

import itertools
import json
import os
import sqlite3
from pathlib import Path

import pytest

import sync_capture
import sync_exchange
import sync_records
from sync_records import CardRef


CARD_7 = CardRef(card_id=7, note_id=70, guid="guid-7", uploaded_usn=12)
CARD_8 = CardRef(card_id=8, note_id=80, guid="guid-8", uploaded_usn=13)


def _anki(card_ids):
    return {card.card_id: card for card in (CARD_7, CARD_8) if card.card_id in card_ids}


def _device(tmp_path, name, *, library_id=None):
    """A profile database at the latest schema, with sync enabled."""
    path = tmp_path / f"{name}.db"
    conn = sqlite3.connect(path, isolation_level="")
    import db
    from db_schema import initialize_schema
    initialize_schema(conn, bootstrap=db._create_tables, migrations=db._SCHEMA_MIGRATIONS)
    counter = itertools.count(1)
    sync_capture.enable_sync(conn, make_id=lambda: f"{name}-{next(counter)}", library_id=library_id)
    return conn


@pytest.fixture
def folder(tmp_path):
    root = tmp_path / "Cloud"
    root.mkdir()
    return root


@pytest.fixture
def devices(tmp_path):
    a = _device(tmp_path, "a")
    b = _device(tmp_path, "b", library_id=sync_capture.sync_identity(a).library_id)
    yield a, b
    a.close()
    b.close()


def _priority(conn, card_id, value):
    with conn:
        conn.execute("INSERT OR REPLACE INTO priorities(card_id, priority) VALUES (?, ?)", (card_id, value))


def _capture(conn):
    return sync_capture.capture(conn, sync_records.FAMILIES, _anki, now=lambda: 1000)


def _publish(conn, folder):
    return sync_exchange.publish(conn, folder, now=lambda: 2000)


def _receive(conn, folder):
    return sync_exchange.receive(conn, folder, sync_records.FAMILIES, now=lambda: 3000)


def _library_dir(conn, folder):
    return folder / "IncrementoSync" / "v1" / sync_capture.sync_identity(conn).library_id


def _packs(conn, folder):
    identity = sync_capture.sync_identity(conn)
    return sorted((_library_dir(conn, folder) / "devices" / identity.device_id / "packs").glob("*.pack"))


def _inbox(conn):
    return conn.execute("SELECT revision_id, status FROM sync_inbox ORDER BY revision_id").fetchall()


def _outgoing_ids(conn):
    return [row[0] for row in conn.execute("SELECT id FROM sync_revisions ORDER BY seq")]


# --- Publication --------------------------------------------------------------

def test_publishing_writes_one_hash_named_pack_and_marks_the_outbox(devices, folder):
    a, _ = devices
    _priority(a, 7, 40.0)
    _priority(a, 8, 60.0)
    _capture(a)

    result = _publish(a, folder)

    packs = _packs(a, folder)
    assert result.packs_written == 1 and result.revisions_published == 2
    assert len(packs) == 1
    assert packs[0].name.startswith("000001-000000000001-")
    assert sync_exchange.sha256_file(packs[0]) == packs[0].stem.split("-")[2]
    assert a.execute("SELECT count(*) FROM sync_outbox WHERE published_at IS NULL").fetchone() == (0,)
    library = json.loads((_library_dir(a, folder) / "library.json").read_text("utf-8"))
    assert library == {"format": sync_records.SYNC_FORMAT, "library_id": sync_capture.sync_identity(a).library_id}


def test_publishing_with_nothing_new_writes_nothing(devices, folder):
    a, _ = devices
    _priority(a, 7, 40.0)
    _capture(a)
    _publish(a, folder)

    result = _publish(a, folder)

    assert (result.packs_written, result.revisions_published) == (0, 0)
    assert len(_packs(a, folder)) == 1


def test_a_crash_after_writing_a_pack_republishes_the_same_file_without_duplicates(devices, folder, monkeypatch):
    a, _ = devices
    _priority(a, 7, 40.0)
    _capture(a)
    original = sync_exchange._mark_published

    def crash(*args, **kwargs):
        raise RuntimeError("power loss")

    monkeypatch.setattr(sync_exchange, "_mark_published", crash)
    with pytest.raises(RuntimeError, match="power loss"):
        _publish(a, folder)
    first = _packs(a, folder)
    monkeypatch.setattr(sync_exchange, "_mark_published", original)

    result = _publish(a, folder)

    assert _packs(a, folder) == first
    assert result.revisions_published == 1
    assert a.execute("SELECT count(*) FROM sync_outbox WHERE published_at IS NULL").fetchone() == (0,)


def test_a_device_writes_only_below_its_own_device_folder(devices, folder):
    a, b = devices
    _priority(a, 7, 40.0)
    _capture(a)
    _publish(a, folder)
    before = {p: p.stat().st_mtime_ns for p in folder.rglob("*") if p.is_file()}

    _receive(b, folder)
    _priority(b, 8, 10.0)
    _capture(b)
    _publish(b, folder)

    device_b = _library_dir(b, folder) / "devices" / sync_capture.sync_identity(b).device_id
    written = {p for p in folder.rglob("*") if p.is_file() and before.get(p) != p.stat().st_mtime_ns}
    assert written and all(device_b in p.parents for p in written)


# --- Receiving (dry run: nothing is applied) ---------------------------------

def test_receiving_records_validated_revisions_without_applying_them(devices, folder):
    a, b = devices
    _priority(a, 7, 40.0)
    _capture(a)
    _publish(a, folder)

    result = _receive(b, folder)

    assert result.received == 1 and result.rejected == 0
    assert _inbox(b) == [(_outgoing_ids(a)[0], "received")]
    assert b.execute("SELECT count(*) FROM priorities").fetchone() == (0,)
    assert b.execute("SELECT count(*) FROM sync_baseline").fetchone() == (0,)


def test_a_device_never_receives_its_own_packs(devices, folder):
    a, _ = devices
    _priority(a, 7, 40.0)
    _capture(a)
    _publish(a, folder)

    assert _receive(a, folder).received == 0
    assert _inbox(a) == []


def test_receiving_the_same_packs_twice_is_harmless(devices, folder):
    a, b = devices
    _priority(a, 7, 40.0)
    _capture(a)
    _publish(a, folder)
    _receive(b, folder)

    again = _receive(b, folder)

    assert again.received == 0
    assert len(_inbox(b)) == 1
    assert b.execute("SELECT count(*) FROM sync_revisions").fetchone() == (1,)


def test_a_child_that_arrives_before_its_parent_waits_and_is_released_when_the_parent_arrives(devices, folder):
    a, b = devices
    _priority(a, 7, 40.0)
    _capture(a)
    _publish(a, folder)
    parent_pack = _packs(a, folder)[0]
    _priority(a, 7, 20.0)
    _capture(a)
    _publish(a, folder)
    held = parent_pack.with_suffix(".held")
    parent_pack.rename(held)
    parent_id, child_id = _outgoing_ids(a)

    _receive(b, folder)
    assert _inbox(b) == [(child_id, "pending_parent")]

    held.rename(parent_pack)
    _receive(b, folder)

    assert dict(_inbox(b)) == {parent_id: "received", child_id: "received"}


def test_a_pack_whose_bytes_do_not_match_its_name_has_not_arrived_yet(devices, folder):
    a, b = devices
    _priority(a, 7, 40.0)
    _capture(a)
    _publish(a, folder)
    pack = _packs(a, folder)[0]
    complete = pack.read_bytes()
    pack.write_bytes(complete[: len(complete) // 2])

    first = _receive(b, folder)
    assert (first.received, first.rejected, first.incomplete) == (0, 0, 1)
    assert _inbox(b) == []

    pack.write_bytes(complete)
    assert _receive(b, folder).received == 1


def test_a_pack_removed_from_the_folder_deletes_nothing(devices, folder):
    a, b = devices
    _priority(a, 7, 40.0)
    _capture(a)
    _publish(a, folder)
    _receive(b, folder)
    for pack in _packs(a, folder):
        pack.unlink()

    _receive(b, folder)

    assert len(_inbox(b)) == 1
    assert b.execute("SELECT count(*) FROM sync_revisions").fetchone() == (1,)


# --- Hostile and malformed input ---------------------------------------------

def _forge_pack(folder, conn, device_id, payload: bytes, *, epoch=1, first_seq=1):
    digest = sync_exchange.sha256_bytes(payload)
    packs = _library_dir(conn, folder) / "devices" / device_id / "packs"
    packs.mkdir(parents=True, exist_ok=True)
    path = packs / f"{epoch:06d}-{first_seq:012d}-{digest}.pack"
    path.write_bytes(payload)
    return path


def _valid_pack_payload(a, folder):
    _priority(a, 7, 40.0)
    _capture(a)
    _publish(a, folder)
    pack = _packs(a, folder)[0]
    payload = json.loads(pack.read_bytes())
    pack.unlink()
    return payload


def _encode(payload):
    return sync_records.canonical_json(payload).encode("utf-8")


@pytest.mark.parametrize("mutate,reason", [
    (lambda p: p.update(format=sync_records.SYNC_FORMAT + 1), "format"),
    (lambda p: p.update(library="another-library"), "library"),
    (lambda p: p.update(device="someone-else"), "device"),
    (lambda p: p["revisions"][0].update(family="unknown_family"), "family"),
    (lambda p: p["revisions"][0].update(value={"priority": 40.0, "extra": 1}), "value"),
    (lambda p: p["revisions"][0].update(value={"priority": "NaN"}), "value"),
    (lambda p: p["revisions"][0].update(key="../../etc/passwd"), "key"),
    (lambda p: p["revisions"][0].update(seq=999), "seq"),
    (lambda p: p["revisions"][0]["value"].update(priority=99.0), "id"),
], ids=["future-format", "other-library", "spoofed-device", "unknown-family", "extra-field", "non-numeric",
        "traversal-key", "seq-outside-pack", "tampered-value"])
def test_malformed_or_hostile_packs_are_rejected_without_writing_revisions(devices, folder, mutate, reason):
    a, b = devices
    payload = _valid_pack_payload(a, folder)
    mutate(payload)
    _forge_pack(folder, a, sync_capture.sync_identity(a).device_id, _encode(payload))

    result = _receive(b, folder)

    assert result.received == 0 and result.rejected >= 1
    assert any(reason in problem for problem in result.problems), result.problems
    assert b.execute("SELECT count(*) FROM sync_revisions").fetchone() == (0,)


def test_an_oversized_pack_is_rejected_before_it_is_parsed(devices, folder, monkeypatch):
    a, b = devices
    monkeypatch.setattr(sync_exchange, "MAX_PACK_BYTES", 64)
    payload = _valid_pack_payload(a, folder)
    _forge_pack(folder, a, sync_capture.sync_identity(a).device_id, _encode(payload))

    result = _receive(b, folder)

    assert result.received == 0
    assert any("size" in problem for problem in result.problems)


@pytest.mark.parametrize("name", ["notapack.txt", "1-2-3.pack", "000001-000000000001-xyz.pack",
                                  "000001-000000000001-" + "0" * 64 + ".pack.tmp"])
def test_files_that_are_not_pack_names_are_ignored(devices, folder, name):
    a, b = devices
    packs = _library_dir(a, folder) / "devices" / "intruder" / "packs"
    packs.mkdir(parents=True)
    (packs / name).write_bytes(b"{}")

    result = _receive(b, folder)

    assert (result.received, result.rejected) == (0, 0)


def test_a_device_folder_that_is_a_symlink_is_not_followed(devices, folder, tmp_path):
    a, b = devices
    outside = tmp_path / "outside"
    outside.mkdir()
    link = _library_dir(a, folder) / "devices" / "linked"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not available to this user")

    result = _receive(b, folder)

    assert any("symlink" in problem for problem in result.problems)


def test_a_pack_handled_once_is_not_read_again(devices, folder, monkeypatch):
    a, b = devices
    _priority(a, 7, 40.0)
    _capture(a)
    _publish(a, folder)
    _receive(b, folder)
    parsed = []
    original = sync_exchange._parse
    monkeypatch.setattr(sync_exchange, "_parse", lambda data: parsed.append(1) or original(data))

    _priority(a, 8, 60.0)
    _capture(a)
    _publish(a, folder)
    _receive(b, folder)

    assert len(parsed) == 1 + 1, "only the new pack (and A's device.json) are parsed"
    assert len(_inbox(b)) == 2


def test_a_rejected_pack_is_reported_once_not_on_every_sync(devices, folder):
    a, b = devices
    payload = _valid_pack_payload(a, folder)
    payload["format"] = sync_records.SYNC_FORMAT + 1
    _forge_pack(folder, a, sync_capture.sync_identity(a).device_id, _encode(payload))

    first = _receive(b, folder)
    again = _receive(b, folder)

    assert first.rejected == 1 and again.rejected == 0


def test_a_pack_that_was_still_arriving_is_read_once_it_is_complete(devices, folder):
    a, b = devices
    _priority(a, 7, 40.0)
    _capture(a)
    _publish(a, folder)
    pack = _packs(a, folder)[0]
    complete = pack.read_bytes()
    pack.write_bytes(complete[:10])
    _receive(b, folder)

    pack.write_bytes(complete)

    assert _receive(b, folder).received == 1


def test_a_pack_rejected_by_an_older_format_is_read_again_after_an_upgrade(devices, folder, monkeypatch):
    a, b = devices
    payload = _valid_pack_payload(a, folder)
    payload["format"] = sync_records.SYNC_FORMAT + 1
    _forge_pack(folder, a, sync_capture.sync_identity(a).device_id, _encode(payload))
    _receive(b, folder)

    monkeypatch.setattr(sync_exchange, "SYNC_FORMAT", sync_records.SYNC_FORMAT + 1)
    again = _receive(b, folder)

    assert again.rejected == 1, "re-judged under the new format (here still rejected: its ids use the old one)"


def test_published_revisions_leave_the_outbox_and_the_published_range_is_still_announced(devices, folder):
    a, _ = devices
    _priority(a, 7, 40.0)
    _priority(a, 8, 50.0)
    _capture(a)

    _publish(a, folder)

    assert a.execute("SELECT count(*) FROM sync_outbox").fetchone() == (0,)
    device = json.loads((_library_dir(a, folder) / "devices" / sync_capture.sync_identity(a).device_id
                         / "device.json").read_text("utf-8"))
    assert device["published"] == {"epoch": 1, "last_seq": 2}
