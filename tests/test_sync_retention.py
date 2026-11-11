"""Snapshots, retention and catching up (docs/architecture/shared-folder-sync.md §8)."""

import json
import os
import sqlite3
import time

import pytest

import db
import sync_exchange
import sync_service


def _collection(cards, usn=20):
    col = sqlite3.connect(":memory:", check_same_thread=False)
    col.execute("CREATE TABLE col (usn INTEGER, scm INTEGER, mod INTEGER DEFAULT 1)")
    col.execute("INSERT INTO col(usn, scm) VALUES (?, 1000)", (usn,))
    col.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, guid TEXT)")
    col.execute("CREATE TABLE cards (id INTEGER PRIMARY KEY, nid INTEGER, usn INTEGER)")
    for card_id in cards:
        col.execute("INSERT INTO notes VALUES (?, ?)", (card_id * 10, f"g{card_id}"))
        col.execute("INSERT INTO cards VALUES (?, ?, 5)", (card_id, card_id * 10))
    return lambda sql, *args: col.execute(sql, args).fetchall()


CARDS = _collection(range(1, 30))


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    db.close_connection()
    monkeypatch.setattr(sync_service, "SNAPSHOT_EVERY_REVISIONS", 1)
    yield
    db.close_connection()


@pytest.fixture
def folder(tmp_path):
    path = tmp_path / "Cloud"
    path.mkdir()
    return path


class Device:
    def __init__(self, tmp_path, name, folder):
        self.addon = str(tmp_path / name)
        sync_service.configure(self.addon, "P", str(folder), query=CARDS)
        identity = sync_service.sync_identity(db.get_connection(self.addon, "P"))
        self.id, self.library = identity.device_id, identity.library_id
        self.dir = sync_exchange.library_dir(folder, self.library) / "devices" / self.id

    def set(self, card, value):
        with db.get_connection(self.addon, "P") as conn:
            conn.execute("INSERT OR REPLACE INTO priorities(card_id, priority) VALUES (?, ?)", (card, value))

    def get(self, card):
        row = db.get_connection(self.addon, "P").execute("SELECT priority FROM priorities WHERE card_id=?",
                                                         (card,)).fetchone()
        return None if row is None else row[0]

    def sync(self):
        report = sync_service.sync_now(self.addon, "P", CARDS)
        assert report.problems == [], report.problems
        return report

    def packs(self):
        return sorted(path.name for path in (self.dir / "packs").glob("*.pack"))

    def device_json(self):
        return json.loads((self.dir / "device.json").read_text("utf-8"))

    def manifests(self):
        return sorted((self.dir / "snapshots").glob("*-manifest.json"))


def test_device_json_announces_what_was_published_and_retired(tmp_path, folder):
    a = Device(tmp_path, "a", folder)
    a.set(1, 10.0)
    a.set(2, 20.0)

    a.sync()

    announced = a.device_json()
    assert announced["published"] == {"epoch": 1, "last_seq": 2}
    # Alone in the library, its own snapshot covers everything it published.
    assert announced["retired"] == {"epoch": 1, "through": 2}
    assert a.packs() == []


def test_a_device_joining_a_lone_device_after_retention_gets_everything(tmp_path, folder):
    a = Device(tmp_path, "a", folder)
    a.set(1, 10.0)
    a.sync()
    assert a.packs() == []

    b = Device(tmp_path, "b", folder)
    b.sync()

    assert b.get(1) == 10.0


def test_a_snapshot_holds_every_current_head_and_the_receipts_with_its_manifest_last(tmp_path, folder):
    a, b = Device(tmp_path, "a", folder), Device(tmp_path, "b", folder)
    a.set(1, 10.0)
    a.sync()
    b.set(2, 20.0)
    b.sync()

    [manifest_path] = b.manifests()
    manifest = json.loads(manifest_path.read_text("utf-8"))
    revisions = []
    for part in manifest["parts"]:
        data = (b.dir / "snapshots" / part["name"]).read_bytes()
        assert sync_exchange.sha256_bytes(data) == part["sha256"]
        revisions += sync_exchange.decode_snapshot_part(data)["revisions"]
    assert sorted(r["key"] for r in revisions) == ["card:1", "card:2"]
    assert manifest["receipts"] == {a.id: {"1": 1}, b.id: {"1": 1}}


def test_a_device_keeps_only_its_latest_snapshot(tmp_path, folder):
    a = Device(tmp_path, "a", folder)
    a.set(1, 10.0)
    a.sync()
    a.set(1, 11.0)

    a.sync()

    assert len(a.manifests()) == 1
    assert json.loads(a.manifests()[0].read_text("utf-8"))["receipts"][a.id] == {"1": 2}


def test_packs_are_retired_once_every_devices_latest_snapshot_covers_them(tmp_path, folder):
    a, b = Device(tmp_path, "a", folder), Device(tmp_path, "b", folder)
    a.set(1, 10.0)
    a.sync()
    a.set(2, 20.0)
    a.sync()
    assert len(a.packs()) == 2
    b.sync()  # B's snapshot now records A's packs as integrated

    a.sync()

    assert a.packs() == []
    assert a.device_json()["retired"] == {"epoch": 1, "through": 2}
    assert (b.get(1), b.get(2)) == (10.0, 20.0)


def test_a_device_without_a_snapshot_blocks_retention(tmp_path, folder, monkeypatch):
    a = Device(tmp_path, "a", folder)
    monkeypatch.setattr(sync_service, "SNAPSHOT_EVERY_REVISIONS", 10**6)
    Device(tmp_path, "b", folder)  # configured but never wrote a snapshot
    monkeypatch.setattr(sync_service, "SNAPSHOT_EVERY_REVISIONS", 1)
    a.set(1, 10.0)
    a.sync()

    a.sync()

    assert len(a.packs()) == 1


def test_a_device_joining_after_retention_catches_up_from_a_snapshot(tmp_path, folder):
    a, b = Device(tmp_path, "a", folder), Device(tmp_path, "b", folder)
    a.set(1, 10.0)
    a.set(2, 20.0)
    a.sync()
    b.set(3, 30.0)
    b.sync()
    a.sync()
    b.sync()
    assert a.packs() == [] and b.packs() == []

    late = Device(tmp_path, "late", folder)
    late.sync()

    assert (late.get(1), late.get(2), late.get(3)) == (10.0, 20.0, 30.0)
    late.set(1, 15.0)
    late.sync()
    a.sync()
    assert a.get(1) == 15.0, "the late device's change descends from the snapshot's history"
    assert sync_service.open_conflicts(a.addon, "P") == []


def test_a_revision_whose_parent_was_retired_is_released_and_judged_concurrent(tmp_path, folder):
    a, b = Device(tmp_path, "a", folder), Device(tmp_path, "b", folder)
    a.set(1, 10.0)
    a.sync()
    b.sync()                      # B has A's first value (X) and a snapshot
    a.set(1, 20.0)                # Y, child of X
    a.sync()
    a.sync()                      # X's pack is retired: B's snapshot covers it
    late = Device(tmp_path, "late", folder)
    late.sync()                   # knows Y from A's snapshot, never X
    b.set(1, 30.0)                # Z, child of X: made by B while offline
    b.sync()

    late.sync()

    statuses = [row[0] for row in db.get_connection(late.addon, "P").execute(
        "SELECT status FROM sync_inbox WHERE status='pending_parent'")]
    assert statuses == []
    assert len(sync_service.open_conflicts(late.addon, "P")) == 1
    assert late.get(1) == 20.0


def _blob(folder, library, sha, age_days):
    path = sync_exchange.library_dir(folder, library) / "blobs" / sha[:2] / sha
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    then = time.time() - age_days * 86400
    os.utime(path, (then, then))
    return path


def test_unreferenced_blobs_are_swept_after_the_grace_period_and_others_kept(tmp_path, folder):
    a = Device(tmp_path, "a", folder)
    old_orphan = _blob(folder, a.library, "a" * 64, 40)
    young_orphan = _blob(folder, a.library, "b" * 64, 5)
    referenced = _blob(folder, a.library, "c" * 64, 40)
    pack = json.dumps({"revisions": [{"deps": {"blobs": ["c" * 64]}}]}).encode()
    name = f"000001-000000000099-{sync_exchange.sha256_bytes(pack)}.pack"
    (a.dir / "packs").mkdir(parents=True, exist_ok=True)
    (a.dir / "packs" / name).write_bytes(pack)

    removed = sync_service.sweep_blobs_now(folder, a.library, now=time.time())

    assert removed == 1
    assert not old_orphan.exists() and young_orphan.exists() and referenced.exists()


def test_retention_stops_at_the_least_advanced_snapshot(tmp_path, folder):
    a, b = Device(tmp_path, "a", folder), Device(tmp_path, "b", folder)
    a.set(1, 10.0)
    a.sync()                      # A pack 1
    b.sync()                      # B's snapshot covers A through 1, then B stays quiet
    a.set(2, 20.0)
    a.sync()                      # A pack 2
    a.set(3, 30.0)
    a.sync()                      # A pack 3; A's own snapshot covers through 3

    assert len(a.packs()) == 2, "packs 2 and 3 stay: B's snapshot only covers A through 1"
    assert a.device_json()["retired"]["through"] == 1


def test_snapshot_parts_are_compressed(tmp_path, folder):
    import gzip

    a = Device(tmp_path, "a", folder)
    for card in range(1, 25):
        a.set(card, float(card))
    a.sync()

    [manifest] = a.manifests()
    part = a.dir / "snapshots" / json.loads(manifest.read_text("utf-8"))["parts"][0]["name"]
    data = part.read_bytes()
    assert data[:2] == b"\x1f\x8b", "gzip"
    assert len(json.loads(gzip.decompress(data))["revisions"]) == 24


def test_a_snapshot_part_that_expands_beyond_the_limit_is_rejected(monkeypatch):
    import gzip

    bomb = gzip.compress(b"{" + b" " * 5_000_000 + b"}", mtime=0)
    monkeypatch.setattr(sync_exchange, "MAX_DECOMPRESSED_BYTES", 1_000_000)

    with pytest.raises(sync_exchange.PackError, match="expands"):
        sync_exchange.decode_snapshot_part(bomb)


def test_a_device_catching_up_from_a_snapshot_gets_the_documents_in_the_same_sync(tmp_path, folder):
    import paths

    a = Device(tmp_path, "a", folder)
    pdf = paths.get_pdf_dir(a.addon, "P") / "book.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7\n" + b"content " * 1000)
    with db.get_connection(a.addon, "P") as conn:
        conn.execute("INSERT INTO content_items(content_id, kind, card_id, note_id, storage_key, created_at, "
                     "updated_at) VALUES (?, 'pdf', 1, 10, 'pdfs/book.pdf', 1, 1)", ("d" * 32,))
    a.sync()
    assert a.packs() == [], "alone, A retires its packs: the document now lives only in A's snapshot"

    late = Device(tmp_path, "late", folder)
    late.sync()

    assert (paths.get_pdf_dir(late.addon, "P") / "book.pdf").read_bytes() == pdf.read_bytes()
