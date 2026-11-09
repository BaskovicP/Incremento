"""The whole engine over a Store that is not a directory (design note section 8).

If any part of the exchange still touched the filesystem, these would fail: nothing exists on disk except each
device's own profile.
"""
import json
import sqlite3
import time

import pytest

import db
import paths
import sync_service
from sync_store import MemoryStore


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


class Device:
    def __init__(self, tmp_path, name, store):
        self.addon, self.store = str(tmp_path / name), store
        sync_service.configure(self.addon, "P", f"store:{name}", query=CARDS, store=store)

    def set(self, card, value):
        with db.get_connection(self.addon, "P") as conn:
            conn.execute("INSERT OR REPLACE INTO priorities(card_id, priority) VALUES (?, ?)", (card, value))

    def get(self, card):
        row = db.get_connection(self.addon, "P").execute("SELECT priority FROM priorities WHERE card_id=?",
                                                         (card,)).fetchone()
        return None if row is None else row[0]

    def sync(self):
        report = sync_service.sync_now(self.addon, "P", CARDS, store=self.store)
        assert report.problems == [] and report.skipped is None, (report.problems, report.skipped)
        return report


def _paths(store):
    return sorted(store._files)


def test_two_devices_exchange_priorities_through_a_store_with_nothing_on_disk(tmp_path):
    store = MemoryStore()
    a, b = Device(tmp_path, "a", store), Device(tmp_path, "b", store)
    a.set(7, 30.0)

    a.sync()
    b.sync()

    assert b.get(7) == 30.0
    assert any(path.endswith("/library.json") for path in _paths(store))
    assert not any((tmp_path / name).exists() and list((tmp_path / name).rglob("IncrementoSync"))
                   for name in ("a", "b")), "no exchange folder was created on disk"


def test_a_conflict_is_settled_over_a_store(tmp_path):
    store = MemoryStore()
    a, b = Device(tmp_path, "a", store), Device(tmp_path, "b", store)
    a.set(7, 10.0)
    a.sync()
    b.sync()
    a.set(7, 20.0)
    b.set(7, 90.0)
    a.sync()
    b.sync()
    [conflict] = sync_service.open_conflicts(b.addon, "P")

    sync_service.resolve(b.addon, "P", conflict.id, {"priority": 20.0}, CARDS)
    b.sync()
    a.sync()

    assert a.get(7) == b.get(7) == 20.0


def test_a_document_travels_as_a_blob_through_a_store(tmp_path):
    store = MemoryStore()
    a, b = Device(tmp_path, "a", store), Device(tmp_path, "b", store)
    pdf = paths.get_pdf_dir(a.addon, "P") / "book.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7\n" + b"content " * 5000)
    with db.get_connection(a.addon, "P") as conn:
        conn.execute("INSERT INTO content_items(content_id, kind, card_id, note_id, storage_key, created_at, "
                     "updated_at) VALUES (?, 'pdf', 1, 10, 'pdfs/book.pdf', 1, 1)", ("d" * 32,))

    a.sync()
    b.sync()

    assert (paths.get_pdf_dir(b.addon, "P") / "book.pdf").read_bytes() == pdf.read_bytes()
    assert any("/blobs/" in path for path in _paths(store))


def test_snapshots_retention_and_a_late_device_work_over_a_store(tmp_path):
    store = MemoryStore()
    a, b = Device(tmp_path, "a", store), Device(tmp_path, "b", store)
    for card in range(1, 6):
        a.set(card, float(card))
    a.sync()
    b.sync()
    a.sync()
    b.sync()
    assert not any(path.endswith(".pack") for path in _paths(store)), "covered packs were retired"
    assert any(path.endswith("-manifest.json") for path in _paths(store))

    late = Device(tmp_path, "late", store)
    late.sync()

    assert [late.get(card) for card in range(1, 6)] == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_joining_another_collections_library_is_refused_over_a_store(tmp_path):
    store = MemoryStore()
    a = Device(tmp_path, "a", store)
    a.set(7, 10.0)
    a.sync()
    other = _collection([7])  # same ids, but this collection's guids differ below
    other_col = sqlite3.connect(":memory:", check_same_thread=False)
    other_col.execute("CREATE TABLE col (usn INTEGER, scm INTEGER, mod INTEGER DEFAULT 1)")
    other_col.execute("INSERT INTO col(usn, scm) VALUES (20, 1000)")
    other_col.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, guid TEXT)")
    other_col.execute("CREATE TABLE cards (id INTEGER PRIMARY KEY, nid INTEGER, usn INTEGER)")
    other_col.execute("INSERT INTO notes VALUES (70, 'someone-elses')")
    other_col.execute("INSERT INTO cards VALUES (7, 70, 5)")

    with pytest.raises(sync_service.SyncSetupError, match="another Anki collection"):
        sync_service.configure(str(tmp_path / "c"), "P", "store:c",
                               query=lambda sql, *args: other_col.execute(sql, args).fetchall(), store=store)
    assert other is not None


def test_unreferenced_blobs_are_swept_after_the_grace_period_over_a_store(tmp_path):
    store = MemoryStore()
    a = Device(tmp_path, "a", store)
    a.set(1, 1.0)
    a.sync()
    library = sync_service.sync_identity(db.get_connection(a.addon, "P")).library_id
    old = f"IncrementoSync/v1/{library}/blobs/aa/{'a' * 62 + 'aa'}"
    young = f"IncrementoSync/v1/{library}/blobs/bb/{'b' * 64}"
    store.write(old, b"x")
    store.write(young, b"x")
    store.touch(old, time.time() - 40 * 86400)

    removed = sync_service.sweep_blobs_now(store, library, now=time.time())

    assert removed == 1
    assert store.read(old, 10) is None and store.read(young, 10) == b"x"


def test_a_hostile_pack_in_a_store_is_rejected_like_one_in_a_folder(tmp_path):
    store = MemoryStore()
    a, b = Device(tmp_path, "a", store), Device(tmp_path, "b", store)
    a.set(7, 10.0)
    a.sync()
    identity = sync_service.sync_identity(db.get_connection(a.addon, "A".lower()[:0] or "P"))
    pack = next(path for path in _paths(store) if path.endswith(".pack"))
    payload = json.loads(store.read(pack, 10_000_000))
    payload["format"] += 1
    store.delete(pack)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    import hashlib
    name = f"000001-000000000001-{hashlib.sha256(body).hexdigest()}.pack"
    store.write(f"IncrementoSync/v1/{identity.library_id}/devices/{identity.device_id}/packs/{name}", body)

    report = sync_service.sync_now(b.addon, "P", CARDS, store=store)

    assert report.problems and "format" in report.problems[0]
    assert b.get(7) is None
