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


# ---------------------------------------------------------------------------
# Connection reuse / switching (covers lines 35-36)
# ---------------------------------------------------------------------------


class TestConnectionSwitching:
    def setup_method(self):
        _reset_db_module()

    def teardown_method(self):
        _reset_db_module()

    def test_switching_dir_closes_old_connection(self):
        """Getting a connection with a new dir should close the previous one."""
        dir1 = _fresh_dir()
        dir2 = _fresh_dir()
        conn1 = db.get_connection(dir1)
        # Now request a connection for a different dir — lines 32-36 execute
        conn2 = db.get_connection(dir2)
        assert conn1 is not conn2
        assert isinstance(conn2, sqlite3.Connection)

    def test_close_exception_is_swallowed(self):
        """If the old connection's close() raises, get_connection still succeeds."""
        from unittest.mock import MagicMock
        dir1 = _fresh_dir()
        # Set up a fake existing connection that raises on close
        fake_conn = MagicMock()
        fake_conn.close.side_effect = Exception("close failed")
        db._connection = fake_conn
        db._initialized_for = "/some/stale/path"
        # Requesting a new dir should try close() on the fake conn, swallow the error
        conn = db.get_connection(dir1)
        fake_conn.close.assert_called_once()
        assert isinstance(conn, sqlite3.Connection)

    def test_migration_adds_read_page_column(self):
        """If an existing DB lacks read_page, get_connection adds it (line 121)."""
        import os
        import sqlite3 as _sqlite3

        addon_dir = _fresh_dir()
        db_path = os.path.join(addon_dir, "user_files", db.DB_NAME)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        # Create DB with old schema (no read_page column)
        old_conn = _sqlite3.connect(db_path)
        old_conn.execute(
            "CREATE TABLE pdf_progress ("
            "card_id INTEGER PRIMARY KEY, "
            "page INTEGER NOT NULL DEFAULT 1, "
            "zoom REAL NOT NULL DEFAULT 1.0)"
        )
        old_conn.commit()
        old_conn.close()

        # get_connection should ADD the read_page column and commit (line 121)
        conn = db.get_connection(addon_dir)
        columns = [r[1] for r in conn.execute("PRAGMA table_info(pdf_progress)").fetchall()]
        assert "read_page" in columns


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------


class TestExportHelpers:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db_module()

    def test_export_priorities_json_empty(self):
        import json
        result = json.loads(db.export_priorities_json(self.addon_dir))
        assert result == {}

    def test_export_priorities_json_with_data(self):
        import json
        conn = db.get_connection(self.addon_dir)
        conn.execute("INSERT INTO priorities VALUES (1, 25.0)")
        conn.execute("INSERT INTO priorities VALUES (2, 75.0)")
        conn.commit()
        result = json.loads(db.export_priorities_json(self.addon_dir))
        assert result == {"1": 25.0, "2": 75.0}

    def test_export_pdf_progress_json_empty(self):
        import json
        result = json.loads(db.export_pdf_progress_json(self.addon_dir))
        assert result == {}

    def test_export_pdf_progress_json_with_data(self):
        import json
        conn = db.get_connection(self.addon_dir)
        conn.execute("INSERT INTO pdf_progress (card_id, page, zoom) VALUES (10, 3, 1.5)")
        conn.commit()
        result = json.loads(db.export_pdf_progress_json(self.addon_dir))
        assert "10" in result
        assert result["10"]["page"] == 3
        assert result["10"]["zoom"] == 1.5

    def test_export_highlights_json_empty(self):
        import json
        result = json.loads(db.export_highlights_json(self.addon_dir))
        assert result == {}

    def test_export_highlights_json_with_data(self):
        import json
        conn = db.get_connection(self.addon_dir)
        conn.execute(
            "INSERT INTO pdf_highlights VALUES ('h1', 5, 2, 'blue', 'some text', '[]')"
        )
        conn.commit()
        result = json.loads(db.export_highlights_json(self.addon_dir))
        assert "5" in result
        assert result["5"][0]["id"] == "h1"

    def test_export_stats_json_empty(self):
        import json
        result = json.loads(db.export_stats_json(self.addon_dir))
        assert result == {}

    def test_export_stats_json_with_daily_and_lifetime(self):
        import json
        conn = db.get_connection(self.addon_dir)
        conn.execute(
            "INSERT INTO stats VALUES ('daily', '2026-01-01', '{\"type\": {}}')"
        )
        conn.execute(
            "INSERT INTO stats VALUES ('lifetime', NULL, '{\"type\": {\"topics\": 3}}')"
        )
        conn.commit()
        result = json.loads(db.export_stats_json(self.addon_dir))
        assert "daily" in result
        assert result["daily"]["date"] == "2026-01-01"
        assert result["lifetime"]["type"]["topics"] == 3


# ---------------------------------------------------------------------------
# search_pdf_text_index — edge cases
# ---------------------------------------------------------------------------


class TestSearchEdgeCases:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()
        # Pre-populate with some data
        db.replace_pdf_text_index(self.addon_dir, 1, ["The quick brown fox jumps over the lazy dog"])

    def teardown_method(self):
        _reset_db_module()

    def test_query_with_only_single_char_tokens_returns_empty(self):
        """All tokens are 1 char — filtered out → return []."""
        result = db.search_pdf_text_index(self.addon_dir, "a b c")
        assert result == []

    def test_partial_multi_token_match(self):
        """Multiple tokens where not all appear → partial match via token count."""
        # "quick lazy" — both words appear in the text → match
        result = db.search_pdf_text_index(self.addon_dir, "quick lazy")
        assert len(result) == 1

    def test_limit_stops_early(self):
        """Results are truncated at the limit."""
        for cid in range(1, 10):
            db.replace_pdf_text_index(self.addon_dir, cid, [f"needle appears here page {cid}"])
        results = db.search_pdf_text_index(self.addon_dir, "needle", limit=3)
        assert len(results) <= 3


# ---------------------------------------------------------------------------
# Topic schedule
# ---------------------------------------------------------------------------


class TestTopicSchedule:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db_module()

    def test_get_default_when_not_set(self):
        a_factor, interval = db.get_topic_schedule(self.addon_dir, 42)
        assert a_factor == 3.5
        assert interval == 1

    def test_set_and_get_topic_schedule(self):
        db.set_topic_schedule(self.addon_dir, 42, 2.0, 7)
        a_factor, interval = db.get_topic_schedule(self.addon_dir, 42)
        assert a_factor == 2.0
        assert interval == 7

    def test_overwrite_existing_schedule(self):
        db.set_topic_schedule(self.addon_dir, 10, 3.0, 5)
        db.set_topic_schedule(self.addon_dir, 10, 4.5, 14)
        a_factor, interval = db.get_topic_schedule(self.addon_dir, 10)
        assert a_factor == 4.5
        assert interval == 14

    def test_rounds_a_factor_to_three_decimals(self):
        db.set_topic_schedule(self.addon_dir, 7, 2.12345, 3)
        a_factor, _ = db.get_topic_schedule(self.addon_dir, 7)
        assert a_factor == round(2.12345, 3)
