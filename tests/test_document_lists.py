"""Books share profile-local list membership and acquisition notes by document."""

import sqlite3

import pytest

import db
import db_schema
import operation_journal


@pytest.fixture(autouse=True)
def close_databases():
    db.close_connection()
    yield
    db.close_connection()


@pytest.mark.parametrize("kind,filename", [("pdf", "book.pdf"), ("epub", "book.epub")])
def test_book_can_belong_to_multiple_lists_with_one_saved_reason(tmp_path, kind, filename):
    import document_lists as library

    root = str(tmp_path)
    biology = library.create_document_list(root, "A", "Biology")
    psychology = library.create_document_list(root, "A", "Psychology")
    details = {"list_ids": [biology, psychology, biology],
               "reason": "ChatGPT recommended it.\nRead chapters 1–3.",
               "source": "A favourite blog"}
    library.save_document_details(root, "A", kind, filename, details)
    db.close_connection()

    snapshot = library.load_document_library(root, "A")
    assert snapshot["books"][(kind, filename)] == {**details, "list_ids": [biology, psychology]}
    assert snapshot["lists"] == [(biology, "Biology"), (psychology, "Psychology")]
    assert library.load_document_library(root, "B") == {"lists": [], "books": {}}


def test_list_names_are_unicode_case_insensitive_and_delete_preserves_book_note(tmp_path):
    import document_lists as library

    root = str(tmp_path)
    list_id = library.create_document_list(root, "A", "  Máths  ")
    with pytest.raises(ValueError):
        library.create_document_list(root, "A", "MÁTHS")
    library.save_document_details(root, "A", "pdf", "book.pdf",
                                  {"reason": "Keep this reason", "source": "A friend", "list_ids": [list_id]})
    library.rename_document_list(root, "A", list_id, "Reference")
    assert library.load_document_library(root, "A")["lists"] == [(list_id, "Reference")]
    library.delete_document_list(root, "A", list_id)
    assert library.load_document_library(root, "A")["books"][("pdf", "book.pdf")] == {
        "reason": "Keep this reason", "source": "A friend", "list_ids": []}


def test_invalid_membership_rolls_back_reason_and_existing_membership(tmp_path):
    import document_lists as library

    root = str(tmp_path)
    maths = library.create_document_list(root, "A", "Maths")
    original = {"reason": "Original", "source": "Lecture", "list_ids": [maths]}
    library.save_document_details(root, "A", "epub", "book.epub", original)
    with pytest.raises(ValueError):
        library.save_document_details(root, "A", "epub", "book.epub",
                                      {"reason": "Changed", "list_ids": [maths, 999]})
    assert library.load_document_library(root, "A")["books"][("epub", "book.epub")] == original


def test_bulk_grouping_is_additive_shared_by_document_and_profile_scoped(tmp_path):
    import document_lists as library

    root = str(tmp_path)
    existing = library.create_document_list(root, "A", "Reference")
    target = library.create_document_list(root, "A", "Maths")
    original = {"reason": "A recommendation", "source": "Lecture", "list_ids": [existing]}
    library.save_document_details(root, "A", "pdf", "one.pdf", original)
    documents = [("pdf", "one.pdf"), ("epub", "two.epub"), ("pdf", "pdfs/one.pdf")]

    assert library.add_documents_to_list(root, "A", documents, target) == (("pdf", "one.pdf"), ("epub", "two.epub"))
    library.add_documents_to_list(root, "A", documents, target)

    books = library.load_document_library(root, "A")["books"]
    assert books == {("pdf", "one.pdf"): {**original, "list_ids": [existing, target]},
                     ("epub", "two.epub"): {"reason": "", "source": "", "list_ids": [target]}}
    assert library.load_document_library(root, "B") == {"lists": [], "books": {}}


def test_bulk_grouping_rolls_back_every_document_if_one_has_too_many_lists(tmp_path, monkeypatch):
    import document_lists as library

    monkeypatch.setattr(library, "MAX_BOOK_LISTS", 2)
    root = str(tmp_path)
    ids = [library.create_document_list(root, "A", name) for name in ("One", "Two", "Three")]
    original = {"reason": "Keep this", "source": "A friend", "list_ids": ids[:2]}
    library.save_document_details(root, "A", "pdf", "full.pdf", original)
    before = library.load_document_library(root, "A")

    with pytest.raises(ValueError):
        library.add_documents_to_list(root, "A", [("pdf", "new.pdf"), ("pdf", "full.pdf")], ids[2])

    assert library.load_document_library(root, "A") == before


def test_bulk_grouping_cancelled_during_transaction_rolls_back_all_memberships(tmp_path):
    from concurrent.futures import CancelledError
    import threading
    import document_lists as library

    root = str(tmp_path)
    target = library.create_document_list(root, "A", "Maths")
    cancel = threading.Event()
    conn = db.get_connection(root, "A")
    conn.create_function("cancel_grouping", 0, lambda: cancel.set() or 0)
    conn.execute("CREATE TEMP TRIGGER cancel_grouping AFTER INSERT ON document_library_books "
                 "BEGIN SELECT cancel_grouping(); END")

    with pytest.raises(CancelledError):
        library.add_documents_to_list(root, "A", [("pdf", "one.pdf"), ("pdf", "two.pdf")], target,
                                      cancel_event=cancel)

    assert library.load_document_library(root, "A")["books"] == {}


@pytest.mark.parametrize("documents,target", [([("pdf", "../bad.pdf")], 1), ([("web", "one.pdf")], 1),
                                             ([("pdf", "one.pdf")], True)])
def test_bulk_grouping_validates_before_opening_storage(tmp_path, documents, target):
    import document_lists as library

    with pytest.raises(ValueError):
        library.add_documents_to_list(str(tmp_path), "A", documents, target)
    assert not (tmp_path / "user_files").exists()


@pytest.mark.parametrize("details", [
    {"reason": "x" * 2001}, {"source": "x" * 501}, {"source": "bad\x00source"},
    {"list_ids": [True]}, {"list_ids": [-1]}, {"list_ids": list(range(1, 66))},
])
def test_oversized_or_malformed_details_fail_before_writes(tmp_path, details):
    import document_lists as library

    with pytest.raises(ValueError):
        library.save_document_details(str(tmp_path), "A", "pdf", "book.pdf", details)
    assert not (tmp_path / "user_files").exists()


def test_library_migration_rolls_back_tables_journal_column_and_ledger():
    with sqlite3.connect(":memory:") as conn:
        previous = tuple(m for m in db._SCHEMA_MIGRATIONS if m[0] <= 22)
        db_schema.initialize_schema(conn, bootstrap=db._create_tables, migrations=previous)

        def interrupted(connection):
            db._migration_23_document_library(connection)
            raise RuntimeError("interrupted")

        with pytest.raises(RuntimeError, match="interrupted"):
            db_schema.initialize_schema(conn, bootstrap=db._create_tables,
                migrations=previous + ((23, "document_library", interrupted),))
        assert conn.execute("PRAGMA user_version").fetchone() == (22,)
        assert conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 'document_library_%'").fetchall() == []
        assert "document_details" not in {row[1] for row in conn.execute("PRAGMA table_info(import_journal)")}
        assert conn.execute("SELECT max(version) FROM schema_migrations").fetchone() == (22,)


@pytest.mark.parametrize("recover", [False, True], ids=["normal-import", "interrupted-import"])
@pytest.mark.parametrize("kind,filename", [("pdf", "book.pdf"), ("epub", "book.epub")])
def test_import_reason_and_lists_survive_commit_or_post_card_recovery(tmp_path, recover, kind, filename):
    import document_lists as library

    root = str(tmp_path)
    list_id = library.create_document_list(root, "A", "Research")
    details = {"reason": "Recommended for my project", "source": "ChatGPT", "list_ids": [list_id]}
    operation = operation_journal.ImportOperation(root, "A", kind, document_details=details)
    storage_key = f"{'pdfs' if kind == 'pdf' else 'epubs'}/{filename}"
    operation.track_created_relpath(storage_key)
    operation.bind_anki(card_id=12, note_id=34)
    if recover:
        operation.rollback(error_code="interrupted")
        assert operation_journal.recover_interrupted_imports(root, "A", live_card_ids={12})["recovered"] == 1
    else:
        operation.commit(storage_key=storage_key)
    assert library.load_document_library(root, "A")["books"][(kind, filename)] == details
    assert db.get_connection(root, "A").execute("SELECT state FROM import_journal").fetchone() == ("committed",)


def test_failed_pre_card_import_never_creates_book_metadata(tmp_path):
    import document_lists as library

    with pytest.raises(RuntimeError):
        with operation_journal.ImportOperation(str(tmp_path), "A", "pdf",
                document_details={"reason": "Keep if imported"}) as operation:
            operation.track_created_relpath("pdfs/book.pdf")
            raise RuntimeError("Anki rejected the note")
    assert library.load_document_library(str(tmp_path), "A")["books"] == {}


@pytest.mark.parametrize("kind", ["pdf", "epub"])
def test_invalid_import_details_do_not_touch_note_types_or_files(tmp_path, monkeypatch, kind):
    import importlib
    from unittest.mock import Mock

    manager = importlib.import_module(kind + "_manager")
    ensure = Mock()
    monkeypatch.setattr(manager, "ensure_" + kind + "_note_type", ensure)
    with pytest.raises(ValueError):
        getattr(manager, "add_" + kind + "_card")(str(tmp_path), object(), "unused." + kind, "Book",
            profile="A", document_details={"reason": "x" * 2001})
    ensure.assert_not_called()
    assert not (tmp_path / "user_files").exists()


def test_corrupted_optional_import_details_keep_the_exact_import_pending(tmp_path):
    root = str(tmp_path)
    operation = operation_journal.ImportOperation(root, "A", "pdf", document_details={"reason": "A recommendation"})
    operation.track_created_relpath("pdfs/book.pdf")
    operation.bind_anki(card_id=12, note_id=34)
    conn = db.get_connection(root, "A")
    with conn:
        conn.execute("UPDATE import_journal SET document_details='not JSON'")
    result = operation_journal.recover_interrupted_imports(root, "A", live_card_ids={12})
    assert result["recovered"] == 0
    assert conn.execute("SELECT state,error_code FROM import_journal").fetchone() == ("pending", "invalid_document_details")
    assert conn.execute("SELECT count(*) FROM document_library_books").fetchone() == (0,)


def test_replacement_file_keeps_book_details_and_original_undo_identity(tmp_path):
    import document_lists as library

    root = str(tmp_path)
    list_id = library.create_document_list(root, "A", "Reference")
    details = {"reason": "A lecturer recommended it", "source": "Lecture", "list_ids": [list_id]}
    library.save_document_details(root, "A", "pdf", "old.pdf", details)
    library.copy_document_details(root, "A", "pdf", "old.pdf", "replacement.pdf")
    snapshot = library.load_document_library(root, "A")
    assert snapshot["books"][("pdf", "replacement.pdf")] == details
    assert snapshot["books"][("pdf", "old.pdf")] == details


@pytest.mark.parametrize("kind", ["pdf", "epub"])
def test_document_manager_commits_details_under_the_actual_managed_filename(tmp_path, monkeypatch, kind):
    import importlib
    from unittest.mock import MagicMock
    import document_lists as library

    manager = importlib.import_module(kind + "_manager")
    managed = tmp_path / "user_files" / "A" / (kind + "s")
    managed.mkdir(parents=True)
    monkeypatch.setattr(manager, "get_" + kind + "_dir", lambda profile=None: str(managed))
    monkeypatch.setattr(manager, "ensure_" + kind + "_note_type", lambda *_a, **_kw: None)
    monkeypatch.setattr(manager, "render_" + kind + "_cover_media", lambda *_a, **_kw: "")
    if kind == "pdf":
        monkeypatch.setattr(manager, "extract_pdf_pages_text", lambda *_a, **_kw: ["Synthetic page"])
    else:
        monkeypatch.setattr(manager, "ensure_epub_extracted", lambda *_a, **_kw: {"title": "Book", "sections": []})
    source = tmp_path / ("book." + kind)
    source.write_bytes(b"%PDF-1.4\n" if kind == "pdf" else b"Synthetic EPUB")
    col = MagicMock()
    col.find_notes.return_value = []
    col.new_note.return_value.id = 34
    col.decks.by_name.return_value = {"id": 1}
    col.add_note.return_value = 1
    col.find_cards.return_value = [12]
    list_id = library.create_document_list(str(tmp_path), "A", "Research")
    details = {"reason": "Read for my project", "source": "A recommendation", "list_ids": [list_id]}

    assert getattr(manager, "add_" + kind + "_card")(
        str(tmp_path), col, str(source), "Book", profile="A", document_details=details) == 12

    storage_key = db.get_connection(str(tmp_path), "A").execute("SELECT storage_key FROM content_items").fetchone()[0]
    filename = storage_key.split("/", 1)[1]
    assert (managed / filename).is_file()
    assert library.load_document_library(str(tmp_path), "A")["books"][(kind, filename)] == details
