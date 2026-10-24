"""Deletion proof, user data retention and stale index publication boundaries."""

from concurrent.futures import CancelledError, ThreadPoolExecutor
import sqlite3
from threading import Event
from types import SimpleNamespace

import pytest

import db
import paths
import pdf_search
import search_indexer
from search_repository import SearchCollection


@pytest.fixture
def pdf_library(tmp_path):
    addon, profile = str(tmp_path / "addon"), "Library"
    folder = paths.get_pdf_dir(addon, profile)
    folder.mkdir(parents=True)
    (folder / "book.pdf").write_bytes(b"%PDF-fixture")
    anki = sqlite3.connect(":memory:")
    anki.executescript("CREATE TABLE cards(id,nid); CREATE TABLE notes(id,mid,flds);")
    anki.execute("INSERT INTO cards VALUES (11,1)")
    anki.execute("INSERT INTO notes VALUES (1,1,?)", ("Title\x1fbook.pdf",))
    model = {"name": "Custom PDF", "flds": [{"name": "Title", "ord": 0}, {"name": "PDF_Filename", "ord": 1}]}
    col = SimpleNamespace(
        db=SimpleNamespace(all=lambda sql, *args: anki.execute(sql, args).fetchall()),
        models=SimpleNamespace(get=lambda mid: model),
    )
    db.replace_pdf_text_index(addon, profile, 11, ["original searchable text"])
    yield addon, profile, folder, anki, col
    anki.close()


def test_empty_pdf_field_in_custom_note_does_not_hide_ordinary_extracted_cards(pdf_library):
    addon, profile, folder, anki, col = pdf_library
    anki.execute("INSERT INTO cards VALUES (12,2)")
    anki.execute("INSERT INTO notes VALUES (2,1,?)", ("Extracted card\x1f",))
    metadata = SearchCollection(col)
    metadata.load_notes([1, 2])
    assert metadata.notes[2].pdf_filename is None
    assert pdf_search.pdf_cards_for_notes(col, [1, 2]) == {11}


def test_missing_or_unsafe_path_is_hidden_but_cannot_confirm_deletion(pdf_library):
    addon, profile, folder, anki, col = pdf_library
    for filename in ("gone.pdf", "../outside.pdf", "/outside/book.pdf"):
        anki.execute("UPDATE notes SET flds=?", ("Title\x1f" + filename,))
        assert pdf_search.prepare_pdf_index_documents(addon, profile, col, [11]) == []
        assert pdf_search.reconcile_pdf_search_indexes(addon, profile, col) == []
        assert db.search_pdf_text_index(addon, profile, "searchable")


def test_read_failure_and_cancel_never_count_as_confirmation(pdf_library):
    addon, profile, folder, anki, col = pdf_library

    def broken(*args):
        raise RuntimeError("Collection unavailable")

    failed_col = SimpleNamespace(db=SimpleNamespace(all=broken), models=col.models)
    with pytest.raises(RuntimeError, match="unavailable"):
        pdf_search.reconcile_pdf_search_indexes(addon, profile, failed_col)
    cancelled = Event()
    cancelled.set()
    with pytest.raises(CancelledError):
        pdf_search.reconcile_pdf_search_indexes(addon, profile, col, cancel=cancelled)
    assert db.search_pdf_text_index(addon, profile, "searchable")
    assert db.get_connection(addon, profile).execute("SELECT * FROM document_index_state").fetchall() == []


@pytest.mark.parametrize("retire", ["delete", "profile_close"])
def test_extractor_already_running_cannot_publish_after_deletion_or_close(pdf_library, retire):
    addon, profile, folder, anki, col = pdf_library
    jobs = pdf_search.prepare_pdf_index_documents(addon, profile, col, [11])
    started, release = Event(), Event()

    def extract(*args, **kwargs):
        started.set()
        assert release.wait(5), "Test did not release extractor"
        return ["obsolete searchable text"]

    def run():
        try:
            return search_indexer.index_pdf_documents(addon, profile, jobs, extractor=extract)
        finally:
            db.close_connection()

    with ThreadPoolExecutor(max_workers=1) as worker:
        future = worker.submit(run)
        try:
            assert started.wait(5), "Extractor did not start"
            if retire == "delete":
                anki.execute("DELETE FROM cards")
                pdf_search.reconcile_pdf_search_indexes(addon, profile, col, card_ids=[11])
            else:
                pdf_search.invalidate_pdf_index_jobs(addon, profile)
        finally:
            release.set()
        result = future.result(timeout=5)
    assert result.indexed == 0 and result.skipped == 1
    hits = db.search_pdf_text_index(addon, profile, "searchable")
    assert hits == ([] if retire == "delete" else [(11, 1, "original searchable text")])


def test_cleanup_is_idempotent_and_profile_scoped(pdf_library):
    addon, profile, folder, anki, col = pdf_library
    db.replace_pdf_text_index(addon, "Other", 11, ["other searchable text"])
    anki.execute("DELETE FROM cards")
    for _ in range(2):
        pdf_search.reconcile_pdf_search_indexes(addon, profile, col)
    assert not db.search_pdf_text_index(addon, profile, "searchable")
    assert db.search_pdf_text_index(addon, "Other", "searchable") == [(11, 1, "other searchable text")]
    assert (folder / "book.pdf").exists()


def test_search_repairs_stale_cache_and_requests_undo_rebuild_even_with_other_hits(pdf_library):
    from frontend.search_all_results import run_search

    addon, profile, folder, anki, col = pdf_library
    anki.execute("INSERT INTO cards VALUES (12,2)")
    anki.execute("INSERT INTO notes VALUES (2,1,?)", ("Other PDF\x1fbook.pdf",))
    db.replace_pdf_text_index(addon, profile, 12, ["other searchable text"])
    anki.execute("DELETE FROM cards WHERE id=11")
    filters = frozenset(["pdf_content"])
    deleted = run_search(addon, profile, col, "searchable", filters, check_pdf_cache=True)
    assert "inc://pdf/11/" not in deleted.html and "inc://pdf/12/" in deleted.html
    assert db.search_pdf_text_index(addon, profile, "searchable") == [(12, 1, "other searchable text")]
    anki.execute("INSERT INTO cards VALUES (11,1)")  # owner reappears after Undo
    restored = run_search(addon, profile, col, "searchable", filters, check_pdf_cache=True)
    assert restored.pdf_needs_index is False, "Another live PDF already matches"
    assert [job.card_id for job in restored.pdf_reindex_documents] == [11]
    search_indexer.index_pdf_documents(
        addon, profile, restored.pdf_reindex_documents, extractor=lambda *a, **kw: ["original searchable text"]
    )
    refreshed = run_search(addon, profile, col, "searchable", filters, check_pdf_cache=True)
    assert "inc://pdf/11/" in refreshed.html and "inc://pdf/12/" in refreshed.html
    assert refreshed.pdf_reindex_documents == ()


def test_failed_index_state_write_rolls_back_replacement_text(pdf_library):
    addon, profile, folder, anki, col = pdf_library
    conn = db.get_connection(addon, profile)
    conn.execute(
        "CREATE TRIGGER reject_ready BEFORE INSERT ON document_index_state "
        "WHEN new.status='ready' BEGIN SELECT RAISE(ABORT,'fixture failure'); END"
    )
    jobs = pdf_search.prepare_pdf_index_documents(addon, profile, col, [11])
    result = search_indexer.index_pdf_documents(
        addon, profile, jobs, extractor=lambda *a, **kw: ["replacement searchable text"]
    )
    assert result.failed == 1 and result.indexed == 0
    assert db.search_pdf_text_index(addon, profile, "searchable") == [(11, 1, "original searchable text")]


def test_cleanup_audit_does_not_load_note_bodies_for_healthy_documents(pdf_library):
    addon, profile, folder, anki, col = pdf_library
    original = col.db.all

    def bounded_read(sql, *args):
        assert "FROM notes" not in sql, "Only restored PDFs need full note metadata"
        return original(sql, *args)

    col.db.all = bounded_read
    assert pdf_search.reconcile_pdf_search_indexes(addon, profile, col) == []
    assert db.search_pdf_text_index(addon, profile, "searchable")
