"""Completion is bounded saved progress, never a sum of daily rereads."""

import json
import sqlite3
from types import SimpleNamespace

import pytest

from backend import document_statistics as documents
from backend import paths


def test_pdf_completion_uses_read_marker_not_current_page_or_daily_activity():
    result = documents.pdf_completion(120, {"read_page": 26, "page": 119})
    assert (result["read"], result["left"], result["total"]) == (26, 94, 120)
    assert result["percent"] == pytest.approx(26 / 120 * 100)
    assert documents.pdf_completion(10, {"read_page": 999})["percent"] == 100
    assert documents.pdf_completion(10, {"read_page": -10})["read"] == 0
    assert documents.pdf_completion(None, {"read_page": 26})["percent"] is None


def test_epub_reference_pages_are_stable_and_use_saved_markers():
    metadata = {"sections": [{"text": "a" * 3000}, {"text": "b" * 4500}, {"text": "c" * 1500}]}
    assert documents.epub_completion(metadata, None)["read"] == 0
    # Merely opening the first section creates a default row, not a read marker.
    assert documents.epub_completion(metadata, {"read_section_index": 0})["read"] == 0
    progress = {"read_section_index": 1, "section_index": 2, "font_scale": 2.2}
    result = documents.epub_completion(metadata, progress)
    assert (result["read"], result["left"], result["total"]) == (5, 1, 6)
    assert result["unit"] == "estimated_pages"
    progress["font_scale"] = 0.7
    assert documents.epub_completion(metadata, progress) == result
    progress["read_anchor_json"] = json.dumps({"sectionIndex": 1, "offset": 1500})
    assert documents.epub_completion(metadata, progress)["read"] == 3
    progress["is_finished"] = 1
    assert documents.epub_completion(metadata, progress)["percent"] == 100
    assert documents.epub_completion({}, progress)["total"] is None


@pytest.fixture
def library(tmp_path, monkeypatch):
    collection_db = sqlite3.connect(":memory:")
    collection_db.executescript("CREATE TABLE notes(id, mid, flds); CREATE TABLE cards(id, nid);")
    collection_db.executemany("INSERT INTO notes VALUES (?, ?, ?)", [
        (1, 11, "<b>Book A</b>\x1fbook.pdf"),
        (2, 12, "Book B\x1fbook.epub"), (3, 11, "Missing\x1fmissing.pdf"),
        (4, 11, "Unsafe\x1f../../outside.pdf"),
    ])
    collection_db.executemany("INSERT INTO cards VALUES (?, ?)", [(1, 1), (2, 2), (3, 3), (4, 4)])
    models = {
        "Incremento PDF": {"id": 11, "flds": [{"name": "Title"}, {"name": "PDF_Filename"}]},
        "Incremento EPUB": {"id": 12, "flds": [{"name": "Title"}, {"name": "EPUB_Filename"}]},
    }
    collection = SimpleNamespace(
        db=SimpleNamespace(all=lambda sql, *args: collection_db.execute(sql, args).fetchall()),
        models=SimpleNamespace(by_name=models.get),
    )
    supplemental = sqlite3.connect(":memory:")
    supplemental.executescript("CREATE TABLE pdf_progress(card_id, read_page); INSERT INTO pdf_progress VALUES(1, 26); "
                              "CREATE TABLE epub_progress(card_id, read_section_index, is_finished, read_anchor_json); "
                              "INSERT INTO epub_progress VALUES(2, 1, 0, '');")
    profiles = []
    def connection(addon_dir, profile):
        profiles.append((addon_dir, profile))
        return supplemental
    monkeypatch.setattr(documents, "get_connection", connection)
    pdf_root = paths.get_pdf_dir(str(tmp_path), "Synthetic")
    pdf_root.mkdir(parents=True)
    (pdf_root / "book.pdf").write_bytes(b"%PDF-synthetic")
    extract = paths.get_epub_extract_root(str(tmp_path), "Synthetic") / "book.epub"
    extract.mkdir(parents=True)
    (extract / "metadata.json").write_text(json.dumps({"sections": [{"text": "x" * 1500}] * 4}))
    reads = []
    monkeypatch.setattr(documents, "_pdf_page_count", lambda path: reads.append(path) or 100)
    yield collection, profiles, reads, tmp_path
    collection_db.close()
    supplemental.close()


def test_library_includes_unopened_and_missing_documents_with_honest_unknowns(library):
    collection, profiles, reads, root = library
    rows = documents.document_progress_from_collection(collection, str(root), "Synthetic")
    assert len(rows) == 4
    assert rows[0]["title"] == "Book A"
    assert (rows[0]["read"], rows[0]["left"], rows[0]["percent"]) == (26, 74, 26)
    assert (rows[1]["read"], rows[1]["total"]) == (2, 4)
    assert all(row["percent"] is None for row in rows[2:])
    assert profiles and set(profiles) == {(str(root), "Synthetic")}
    assert len(reads) == 1 and str(reads[0]).endswith("Synthetic/pdfs/book.pdf")


def test_library_fails_closed_on_cancellation_and_symlink_escape(library):
    collection, _, reads, root = library
    assert documents.document_progress_from_collection(collection, str(root), "Synthetic", should_cancel=lambda: True) is None
    assert reads == []
    target = root / "outside.pdf"
    target.write_bytes(b"%PDF-synthetic")
    managed = paths.get_pdf_dir(str(root), "Synthetic") / "book.pdf"
    managed.unlink()
    managed.symlink_to(target)
    rows = documents.document_progress_from_collection(collection, str(root), "Synthetic")
    assert rows[0]["percent"] is None and reads == []


def test_epub_metadata_budget_and_path_containment(tmp_path):
    root = paths.get_epub_extract_root(str(tmp_path), "Synthetic")
    folder = root / "book.epub"
    folder.mkdir(parents=True)
    (folder / "metadata.json").write_text('{"sections": []}')
    assert documents._epub_metadata(str(tmp_path), "Synthetic", "../book.epub") is None
    (folder / "metadata.json").write_bytes(b" " * (documents.MAX_METADATA_BYTES + 1))
    assert documents._epub_metadata(str(tmp_path), "Synthetic", "book.epub") is None


def test_one_malformed_document_does_not_hide_the_rest_of_the_library(library):
    collection, _, _, root = library
    original = collection.db.all
    def rows(sql, *args):
        result = original(sql, *args)
        return [(cid, mid, "Damaged fields" if cid == 3 else fields) for cid, mid, fields in result]
    collection.db.all = rows
    result = documents.document_progress_from_collection(collection, str(root), "Synthetic")
    assert len(result) == 4
    assert result[2]["percent"] is None
    assert result[0]["percent"] == 26
