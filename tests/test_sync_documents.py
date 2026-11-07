"""Document versions (docs/architecture/shared-folder-sync.md §6.1; design PR 8).

A document record names a card's managed PDF or EPUB and its content
version; the file travels as a content-addressed blob together with the PDF
interchange baseline. Annotation rewrites of a PDF change its bytes but not
its version, so they never re-ship the file.
"""

import hashlib
import itertools
import json
import sqlite3
from pathlib import Path

import pytest

import paths
import sync_apply
import sync_capture
import sync_documents
import sync_exchange
import sync_records
from sync_records import CardRef

CARD_7 = CardRef(card_id=7, note_id=70, guid="guid-7", uploaded_usn=12)
PDF_BYTES = b"%PDF-1.7\n" + b"pretend page content\n" * 50
DIGEST = "d" * 64


def _anki(card_ids):
    return {7: CARD_7} if 7 in card_ids else {}


class Device:
    def __init__(self, tmp_path, name, folder, *, library_id=None):
        import db
        from db_schema import initialize_schema
        self.addon = tmp_path / name
        self.profile = "Profile"
        self.conn = sqlite3.connect(tmp_path / f"{name}.db", isolation_level="")
        initialize_schema(self.conn, bootstrap=db._create_tables, migrations=db._SCHEMA_MIGRATIONS)
        counter = itertools.count(1)
        sync_capture.enable_sync(self.conn, make_id=lambda: f"{name}-{next(counter)}", library_id=library_id)
        self.folder = folder
        self.families = {**sync_records.FAMILIES,
                         "document": sync_documents.DocumentFamily(str(self.addon), self.profile)}
        self.store = paths.get_sync_blob_dir(str(self.addon), self.profile)

    @property
    def pdf_dir(self):
        return paths.get_pdf_dir(str(self.addon), self.profile)

    def import_pdf(self, data=PDF_BYTES, filename="book.pdf", digest=None):
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        (self.pdf_dir / filename).write_bytes(data)
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO content_items(content_id, kind, card_id, note_id, storage_key, "
                              "created_at, updated_at) VALUES ('c' || ?, 'pdf', 7, 70, ?, 1, 1)",
                              ("0" * 31, f"pdfs/{filename}"))
            if digest:
                self.conn.execute("INSERT OR REPLACE INTO pdf_annotation_sync(card_id, filename, document_id, "
                                  "source_path, content_digest, baseline_json) VALUES (7, ?, 'doc-a', '', ?, ?)",
                                  (filename, digest, json.dumps({"h1": {"id": "h1"}})))

    def push(self):
        sync_capture.capture(self.conn, self.families, _anki, now=lambda: 1)
        return sync_exchange.publish(self.conn, self.folder, blob_store=self.store, now=lambda: 2)

    def pull(self):
        received = sync_exchange.receive(self.conn, self.folder, self.families, blob_store=self.store, now=lambda: 3)
        applied = sync_apply.apply(self.conn, self.families, _anki, blob_store=self.store, now=lambda: 4)
        return received, applied

    def statuses(self):
        return [row[0] for row in self.conn.execute("SELECT status FROM sync_inbox")]

    def document_revisions(self):
        return self.conn.execute("SELECT value FROM sync_revisions WHERE family='document' ORDER BY seq").fetchall()


@pytest.fixture
def folder(tmp_path):
    path = tmp_path / "Cloud"
    path.mkdir()
    return path


@pytest.fixture
def pair(tmp_path, folder):
    a = Device(tmp_path, "a", folder)
    b = Device(tmp_path, "b", folder, library_id=sync_capture.sync_identity(a.conn).library_id)
    yield a, b
    a.conn.close()
    b.conn.close()


def test_a_document_record_names_the_card_file_and_content_version(pair):
    a, _ = pair
    a.import_pdf(digest=DIGEST)

    [(key, value)] = list(a.families["document"].scan(a.conn))

    assert key == "card:7/document:pdf"
    assert value == {"kind": "pdf", "content_id": "c" + "0" * 31, "note_id": 70, "path": "pdfs/book.pdf",
                     "version": f"digest:{DIGEST}"}


def test_without_an_interchange_digest_the_version_is_the_file_hash(pair):
    a, _ = pair
    a.import_pdf()

    [(_, value)] = list(a.families["document"].scan(a.conn))

    assert value["version"] == "sha256:" + hashlib.sha256(PDF_BYTES).hexdigest()


def test_capture_keeps_the_captured_bytes_in_the_local_blob_store(pair):
    a, _ = pair
    a.import_pdf(digest=DIGEST)

    a.push()

    [(value,)] = a.document_revisions()
    blob = json.loads(value)["blob"]
    assert blob == hashlib.sha256(PDF_BYTES).hexdigest()
    assert (a.store / blob[:2] / blob).read_bytes() == PDF_BYTES
    assert json.loads(value)["interchange"] == {"document_id": "doc-a", "content_digest": DIGEST,
                                                "baseline_json": json.dumps({"h1": {"id": "h1"}})}


def test_an_annotation_rewrite_of_the_same_content_does_not_ship_the_file_again(pair):
    a, _ = pair
    a.import_pdf(digest=DIGEST)
    a.push()

    (a.pdf_dir / "book.pdf").write_bytes(PDF_BYTES + b"% new annotation appearance\n")
    a.push()

    assert len(a.document_revisions()) == 1


def test_a_document_whose_file_is_missing_is_neither_captured_nor_deleted(pair):
    a, _ = pair
    a.import_pdf(digest=DIGEST)
    a.push()
    (a.pdf_dir / "book.pdf").unlink()

    result = sync_capture.capture(a.conn, a.families, _anki, now=lambda: 1)

    assert result.captured == 0
    assert len(a.document_revisions()) == 1


def test_publishing_places_the_blob_beside_the_packs_and_the_other_device_adopts_the_document(pair):
    a, b = pair
    a.import_pdf(digest=DIGEST)
    a.push()

    b.pull()

    assert (b.pdf_dir / "book.pdf").read_bytes() == PDF_BYTES
    assert b.conn.execute("SELECT content_id, kind, card_id, note_id, storage_key FROM content_items").fetchall() == [
        ("c" + "0" * 31, "pdf", 7, 70, "pdfs/book.pdf")]
    assert b.conn.execute("SELECT filename, document_id, source_path, content_digest, baseline_json "
                          "FROM pdf_annotation_sync").fetchall() == [
        ("book.pdf", "doc-a", "", DIGEST, json.dumps({"h1": {"id": "h1"}}))]
    b.push()
    assert b.conn.execute("SELECT count(*) FROM sync_revisions WHERE device LIKE 'b-%'").fetchone() == (0,)


def test_a_document_waits_for_its_blob_and_adopts_it_once_the_blob_arrives(pair):
    a, b = pair
    a.import_pdf(digest=DIGEST)
    a.push()
    blobs = list((a.folder / "IncrementoSync").rglob("blobs/*/*"))
    held = {blob: blob.read_bytes() for blob in blobs}
    for blob in blobs:
        blob.unlink()

    b.pull()
    assert b.statuses() == ["pending_blob"]
    assert not (b.pdf_dir / "book.pdf").exists()

    for blob, data in held.items():
        blob.write_bytes(data)
    b.pull()

    assert b.statuses() == ["applied"]
    assert (b.pdf_dir / "book.pdf").read_bytes() == PDF_BYTES


def test_a_blob_whose_bytes_do_not_match_its_name_is_never_adopted(pair):
    a, b = pair
    a.import_pdf(digest=DIGEST)
    a.push()
    [blob] = list((a.folder / "IncrementoSync").rglob("blobs/*/*"))
    blob.write_bytes(b"%PDF-1.7 tampered")

    b.pull()

    assert b.statuses() == ["pending_blob"]
    assert not (b.pdf_dir / "book.pdf").exists()


def test_a_document_tombstone_removes_the_record_but_never_the_users_file(pair):
    a, b = pair
    a.import_pdf(digest=DIGEST)
    a.push()
    b.pull()
    with a.conn:
        a.conn.execute("DELETE FROM content_items")
    a.push()

    b.pull()

    assert b.conn.execute("SELECT count(*) FROM content_items").fetchone() == (0,)
    assert (b.pdf_dir / "book.pdf").exists()


VALID = {"kind": "pdf", "content_id": "c" + "0" * 31, "note_id": 70, "path": "pdfs/book.pdf",
         "version": f"digest:{DIGEST}", "blob": "b" * 64,
         "interchange": {"document_id": "doc-a", "content_digest": DIGEST, "baseline_json": "{}"}}


@pytest.mark.parametrize("change", [
    {"path": "pdfs/../escape.pdf"}, {"path": "pdfs/sub/book.pdf"}, {"path": "epubs/book.pdf"},
    {"path": "pdfs/book.exe"}, {"path": "pdfs/.hidden.pdf"}, {"path": "pdfs/" + "x" * 300 + ".pdf"},
    {"kind": "epub"}, {"version": "anything"}, {"blob": "../../etc"}, {"note_id": 0},
    {"interchange": {"document_id": "doc-a", "content_digest": DIGEST, "baseline_json": "[not json"}},
    {"interchange": {"document_id": "doc-a", "content_digest": "nothex", "baseline_json": "{}"}},
], ids=["traversal", "subfolder", "wrong-folder", "wrong-extension", "hidden", "too-long", "kind-mismatch",
        "bad-version", "bad-blob", "bad-note", "bad-baseline", "bad-digest"])
def test_incoming_documents_must_name_a_safe_managed_file(pair, change):
    a, _ = pair
    with pytest.raises(ValueError):
        a.families["document"].validate("card:7/document:pdf", {**VALID, **change})


def test_backups_leave_out_the_sync_blob_store():
    import export_bundle

    assert export_bundle.should_skip_user_file("sync/blobs/ab/" + "ab" * 32)
    assert not export_bundle.should_skip_user_file("pdfs/book.pdf")
