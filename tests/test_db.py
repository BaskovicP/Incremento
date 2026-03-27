"""Tests for backend/db.py"""
import sqlite3
import tempfile
import os

import db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_dir():
    """Return a new temp directory; caller is responsible for cleanup."""
    return tempfile.mkdtemp()


def _reset_db_module():
    """Reset module-level connection state between tests."""
    db._connection = None
    db._initialized_for = None


# ---------------------------------------------------------------------------
# get_connection — basic connectivity and table creation
# ---------------------------------------------------------------------------


class TestGetConnection:
    def setup_method(self):
        _reset_db_module()

    def teardown_method(self):
        _reset_db_module()

    def test_returns_sqlite_connection(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir)
        assert isinstance(conn, sqlite3.Connection)

    def test_creates_pdf_progress_table(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "pdf_progress" in tables

    def test_creates_pdf_highlights_table(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "pdf_highlights" in tables

    def test_creates_priorities_table(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "priorities" in tables

    def test_creates_pdf_text_index_table(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "pdf_text_index" in tables

    def test_db_file_created_inside_user_files(self):
        addon_dir = _fresh_dir()
        db.get_connection(addon_dir)
        expected = os.path.join(addon_dir, "user_files", db.DB_NAME)
        assert os.path.isfile(expected)

    def test_idempotent_same_dir_reuses_connection(self):
        addon_dir = _fresh_dir()
        conn1 = db.get_connection(addon_dir)
        conn2 = db.get_connection(addon_dir)
        assert conn1 is conn2

    def test_different_dir_creates_new_connection(self):
        dir1 = _fresh_dir()
        dir2 = _fresh_dir()
        conn1 = db.get_connection(dir1)
        _reset_db_module()
        conn2 = db.get_connection(dir2)
        # Both are valid connections but to different files
        assert isinstance(conn1, sqlite3.Connection)
        assert isinstance(conn2, sqlite3.Connection)
        assert conn1 is not conn2


# ---------------------------------------------------------------------------
# replace_pdf_text_index + search_pdf_text_index
# ---------------------------------------------------------------------------


class TestPdfTextIndex:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db_module()

    def test_insert_and_search_finds_term(self):
        db.replace_pdf_text_index(self.addon_dir, 1, ["Hello world", "Goodbye world"])
        results = db.search_pdf_text_index(self.addon_dir, "hello")
        assert len(results) == 1
        card_id, page, text = results[0]
        assert card_id == 1
        assert page == 1
        assert "Hello" in text

    def test_search_returns_correct_page_number(self):
        db.replace_pdf_text_index(self.addon_dir, 2, ["first page", "second page with needle"])
        results = db.search_pdf_text_index(self.addon_dir, "needle")
        assert len(results) == 1
        assert results[0][1] == 2  # page 2

    def test_replace_removes_old_entries(self):
        db.replace_pdf_text_index(self.addon_dir, 3, ["old content about cats"])
        db.replace_pdf_text_index(self.addon_dir, 3, ["new content about dogs"])
        cats = db.search_pdf_text_index(self.addon_dir, "cats")
        dogs = db.search_pdf_text_index(self.addon_dir, "dogs")
        assert cats == []
        assert len(dogs) == 1

    def test_empty_pages_not_stored(self):
        db.replace_pdf_text_index(self.addon_dir, 4, ["", "   ", "real content here"])
        conn = db.get_connection(self.addon_dir)
        rows = conn.execute(
            "SELECT page FROM pdf_text_index WHERE card_id = 4 ORDER BY page"
        ).fetchall()
        # Only the non-empty page (index 2, page 3) should be stored
        assert rows == [(3,)]

    def test_short_query_returns_empty(self):
        db.replace_pdf_text_index(self.addon_dir, 5, ["some text here"])
        results = db.search_pdf_text_index(self.addon_dir, "a")
        assert results == []

    def test_search_across_multiple_cards(self):
        db.replace_pdf_text_index(self.addon_dir, 10, ["python programming language"])
        db.replace_pdf_text_index(self.addon_dir, 11, ["python snake species"])
        results = db.search_pdf_text_index(self.addon_dir, "python")
        card_ids = {r[0] for r in results}
        assert card_ids == {10, 11}

    def test_case_insensitive_search(self):
        db.replace_pdf_text_index(self.addon_dir, 6, ["The Quick Brown Fox"])
        results = db.search_pdf_text_index(self.addon_dir, "quick brown")
        assert len(results) == 1

    def test_replace_with_empty_list_clears_index(self):
        db.replace_pdf_text_index(self.addon_dir, 7, ["some content"])
        db.replace_pdf_text_index(self.addon_dir, 7, [])
        conn = db.get_connection(self.addon_dir)
        count = conn.execute(
            "SELECT COUNT(*) FROM pdf_text_index WHERE card_id = 7"
        ).fetchone()[0]
        assert count == 0


# ---------------------------------------------------------------------------
# add_pdf_card_source + get_pdf_card_sources
# ---------------------------------------------------------------------------


class TestPdfCardSources:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db_module()

    def test_add_and_retrieve_card_source(self):
        db.add_pdf_card_source(self.addon_dir, pdf_card_id=1, page=3, note_id=999, excerpt="test excerpt")
        sources = db.get_pdf_card_sources(self.addon_dir, pdf_card_id=1, page=3)
        assert len(sources) == 1
        assert sources[0]["note_id"] == 999
        assert sources[0]["excerpt"] == "test excerpt"

    def test_get_pdf_page_card_counts(self):
        db.add_pdf_card_source(self.addon_dir, pdf_card_id=2, page=1, note_id=101)
        db.add_pdf_card_source(self.addon_dir, pdf_card_id=2, page=1, note_id=102)
        db.add_pdf_card_source(self.addon_dir, pdf_card_id=2, page=2, note_id=103)
        counts = db.get_pdf_page_card_counts(self.addon_dir, pdf_card_id=2)
        assert counts[1] == 2
        assert counts[2] == 1
