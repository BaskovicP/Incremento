"""A large first sync in slices: each call does a bounded amount of file transfer and says whether more is left.

An app that syncs while the user waits (or while other work is queued behind it) cannot spend minutes in one call on
a library with hundreds of documents. With a time budget, a call always finishes at least one unit of work and then
stops, and calling again continues exactly where it stopped.
"""
import sqlite3

import pytest

import db
import paths
import sync_service
from sync_store import MemoryStore

DOCUMENTS = 8


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
def _fresh():
    db.close_connection()
    yield
    db.close_connection()


class Device:
    def __init__(self, tmp_path, name, store):
        self.addon, self.store = str(tmp_path / name), store
        sync_service.configure(self.addon, "P", f"store:{name}", query=CARDS, store=store)

    def add_documents(self, count):
        for index in range(1, count + 1):
            pdf = paths.get_pdf_dir(self.addon, "P") / f"book{index}.pdf"
            pdf.parent.mkdir(parents=True, exist_ok=True)
            pdf.write_bytes(b"%PDF-1.7\n" + f"book {index} ".encode() * 3000)
            with db.get_connection(self.addon, "P") as conn:
                conn.execute("INSERT INTO content_items(content_id, kind, card_id, note_id, storage_key, created_at, "
                             "updated_at) VALUES (?, 'pdf', ?, ?, ?, 1, 1)",
                             (f"{index:032x}", index, index * 10, f"pdfs/book{index}.pdf"))

    def documents(self):
        folder = paths.get_pdf_dir(self.addon, "P")
        return sorted(path.name for path in folder.glob("*.pdf")) if folder.is_dir() else []

    def sync(self, budget=None):
        report = sync_service.sync_now(self.addon, "P", CARDS, store=self.store, budget_seconds=budget)
        assert report.problems == [] and report.skipped is None, (report.problems, report.skipped)
        return report


def _until_done(device, *, limit=60, budget=0.0):
    reports = []
    for _ in range(limit):
        reports.append(device.sync(budget))
        if not reports[-1].more:
            return reports
    raise AssertionError("never finished: " + repr(reports[-3:]))


def test_without_a_budget_everything_is_sent_in_one_call(tmp_path):
    store = MemoryStore()
    a = Device(tmp_path, "a", store)
    a.add_documents(DOCUMENTS)

    report = a.sync()

    assert report.more is False and report.published >= DOCUMENTS


def test_a_budget_splits_a_big_upload_into_calls_that_each_make_progress(tmp_path):
    store = MemoryStore()
    a = Device(tmp_path, "a", store)
    a.add_documents(DOCUMENTS)

    reports = _until_done(a)

    assert len(reports) > 1, "a zero budget should stop after the first unit of work"
    assert all(report.published > 0 for report in reports[:-1]), "every call that says more is left did something"
    assert sum(report.published for report in reports) >= DOCUMENTS


def test_a_second_device_receives_everything_after_the_uploads_finish_in_slices(tmp_path):
    store = MemoryStore()
    a, b = Device(tmp_path, "a", store), Device(tmp_path, "b", store)
    a.add_documents(DOCUMENTS)
    _until_done(a)

    reports = _until_done(b)

    assert len(reports) > 1, "downloading is sliced too"
    assert b.documents() == a.documents() == [f"book{i}.pdf" for i in range(1, DOCUMENTS + 1)]
    for name in b.documents():
        assert (paths.get_pdf_dir(b.addon, "P") / name).read_bytes() == (paths.get_pdf_dir(a.addon, "P") / name).read_bytes()


def test_a_partial_upload_never_publishes_a_pack_that_names_a_missing_file(tmp_path):
    store = MemoryStore()
    a, b = Device(tmp_path, "a", store), Device(tmp_path, "b", store)
    a.add_documents(DOCUMENTS)
    a.sync(budget=0.0)  # only the first unit of work

    report = b.sync()  # a device that reads the store half-way through

    assert report.problems == []
    assert len(b.documents()) < DOCUMENTS
    for name in b.documents():  # whatever arrived is whole
        assert (paths.get_pdf_dir(b.addon, "P") / name).read_bytes() == (paths.get_pdf_dir(a.addon, "P") / name).read_bytes()


def test_the_time_of_the_last_complete_sync_is_only_recorded_when_it_was_complete(tmp_path):
    store = MemoryStore()
    a = Device(tmp_path, "a", store)
    a.add_documents(DOCUMENTS)

    first = a.sync(budget=0.0)

    assert first.more
    assert sync_service.status(a.addon, "P").last_sync is None
    _until_done(a)
    assert sync_service.status(a.addon, "P").last_sync is not None


def test_a_snapshot_for_a_store_that_is_new_waits_until_its_documents_are_there(tmp_path):
    old, new = MemoryStore(), MemoryStore()
    a = Device(tmp_path, "a", old)
    a.add_documents(DOCUMENTS)
    _until_done(a)
    sync_service.configure(a.addon, "P", "store:a-new", query=CARDS, store=new)
    a.store = new

    reports = _until_done(a)
    late = Device(tmp_path, "late", new)
    _until_done(late)

    assert len(reports) > 1
    assert late.documents() == [f"book{i}.pdf" for i in range(1, DOCUMENTS + 1)]
