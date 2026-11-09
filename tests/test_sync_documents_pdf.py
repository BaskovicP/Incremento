"""Document consistency with real PDFs (docs/architecture/shared-folder-sync.md §6.1, §9 scenario 15).

Uses PyMuPDF and upstream's own annotation interchange on two devices.
"""

import importlib.util
import itertools
import json
import sys
import sysconfig
from pathlib import Path

import pytest

# As in test_pdf_annotations.py: the harness exposes backend/statistics.py as
# "statistics", but PyMuPDF needs the standard library module while importing.
_previous_statistics = sys.modules.get("statistics")
_stdlib_spec = importlib.util.spec_from_file_location(
    "_sync_stdlib_statistics", Path(sysconfig.get_path("stdlib")) / "statistics.py")
_stdlib_statistics = importlib.util.module_from_spec(_stdlib_spec)
_stdlib_spec.loader.exec_module(_stdlib_statistics)
try:
    sys.modules["statistics"] = _stdlib_statistics
    import pymupdf as fitz
finally:
    if _previous_statistics is None:
        sys.modules.pop("statistics", None)
    else:
        sys.modules["statistics"] = _previous_statistics

import db  # noqa: E402
import paths  # noqa: E402
import pdf_annotations  # noqa: E402
import sync_apply  # noqa: E402
import sync_capture  # noqa: E402
import sync_documents  # noqa: E402
import sync_exchange  # noqa: E402
import sync_records  # noqa: E402
from sync_records import CardRef  # noqa: E402

PROFILE = "Profile"
CARD_7 = CardRef(card_id=7, note_id=70, guid="guid-7", uploaded_usn=12)
RECT = {"x": 72.0, "y": 72.0, "w": 200.0, "h": 14.0}


def _anki(card_ids):
    return {7: CARD_7} if 7 in card_ids else {}


class Device:
    def __init__(self, tmp_path, name, folder, library_id=None):
        self.addon = str(tmp_path / name)
        self.folder = folder
        counter = itertools.count(1)
        sync_capture.enable_sync(self.conn, make_id=lambda: f"{name}-{next(counter)}", library_id=library_id)
        self.families = {**sync_records.FAMILIES, "document": sync_documents.DocumentFamily(self.addon, PROFILE)}

    @property
    def conn(self):
        return db.get_connection(self.addon, PROFILE)

    @property
    def pdf(self):
        return paths.get_pdf_dir(self.addon, PROFILE) / "book.pdf"

    def interchange(self):
        return pdf_annotations.sync_pdf_annotations(self.addon, PROFILE, 7, "book.pdf")

    def highlight_ids(self):
        return [row[0] for row in self.conn.execute("SELECT id FROM pdf_highlights WHERE card_id=7")]

    def native_names(self):
        with fitz.open(self.pdf) as document:
            return [annot.info.get("name") or annot.info.get("id") for page in document for annot in page.annots()]

    def sync(self):
        store = paths.get_sync_blob_dir(self.addon, PROFILE)
        sync_capture.capture(self.conn, self.families, _anki, now=lambda: 1)
        sync_exchange.publish(self.conn, self.folder, blob_store=store, now=lambda: 2)
        sync_exchange.receive(self.conn, self.folder, self.families, blob_store=store, now=lambda: 3)
        sync_apply.apply(self.conn, self.families, _anki, blob_store=store, now=lambda: 4)
        sync_capture.capture(self.conn, self.families, _anki, now=lambda: 5)
        sync_exchange.publish(self.conn, self.folder, blob_store=store, now=lambda: 6)


@pytest.fixture
def devices(tmp_path):
    db.close_connection()
    folder = tmp_path / "Cloud"
    folder.mkdir()
    a = Device(tmp_path, "a", folder)
    library = sync_capture.sync_identity(a.conn).library_id
    b = Device(tmp_path, "b", folder, library_id=library)
    yield a, b
    db.close_connection()


def _import_annotated_pdf(device):
    device.pdf.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 82), "A passage worth remembering.")
    document.save(device.pdf)
    document.close()
    with device.conn as conn:
        conn.execute("INSERT INTO content_items(content_id, kind, card_id, note_id, storage_key, created_at, "
                     "updated_at) VALUES (?, 'pdf', 7, 70, 'pdfs/book.pdf', 1, 1)", ("c" * 32,))
        conn.execute("INSERT INTO pdf_highlights(id, card_id, page, color, text, note, rects, annotation_json, "
                     "note_html) VALUES ('h1', 7, 1, 'yellow', 'A passage', '', ?, '{}', '')", (json.dumps([RECT]),))
    device.interchange()


def _deliver_document_and_delete_the_highlight(a, b):
    _import_annotated_pdf(a)
    assert len(a.native_names()) == 1, "the interchange wrote the highlight into the PDF"
    a.sync()
    # Later on A: the highlight is deleted, and A's interchange removes it from A's PDF.
    with a.conn as conn:
        conn.execute("DELETE FROM pdf_highlights WHERE id='h1'")
    a.interchange()
    a.sync()
    b.sync()


def test_a_deleted_highlight_stays_deleted_on_a_device_that_adopts_the_document(devices):
    a, b = devices
    _deliver_document_and_delete_the_highlight(a, b)
    assert b.pdf.exists()
    assert len(b.native_names()) == 1, "B received the file as it was shipped, with the native highlight"

    b.interchange()

    assert b.highlight_ids() == []
    assert b.native_names() == []


def test_without_the_adopted_baseline_the_deleted_highlight_would_come_back(devices):
    """Control: proves the hazard the shipped baseline prevents."""
    a, b = devices
    _deliver_document_and_delete_the_highlight(a, b)
    with b.conn as conn:
        conn.execute("DELETE FROM pdf_annotation_sync WHERE card_id=7")

    b.interchange()

    assert len(b.highlight_ids()) == 1, "the stale native highlight was imported as a new one"


def test_annotating_the_pdf_again_ships_highlights_not_the_file(devices):
    a, b = devices
    _import_annotated_pdf(a)
    a.sync()
    b.sync()
    published_blobs = set((a.folder / "IncrementoSync").rglob("blobs/*/*"))

    with a.conn as conn:
        conn.execute("INSERT INTO pdf_highlights(id, card_id, page, color, text, note, rects, annotation_json, "
                     "note_html) VALUES ('h2', 7, 1, 'green', 'worth', '', ?, '{}', '')",
                     (json.dumps([{**RECT, "y": 100.0}]),))
    a.interchange()
    a.sync()
    b.sync()
    b.interchange()

    assert set((a.folder / "IncrementoSync").rglob("blobs/*/*")) == published_blobs
    assert sorted(b.highlight_ids()) == ["h1", "h2"]
    assert len(b.native_names()) == 2
