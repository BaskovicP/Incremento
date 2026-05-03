"""Tests for backend/db.py"""
import sqlite3
import tempfile
import os

import db
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_dir():
    """Return a new temp directory; caller is responsible for cleanup."""
    return tempfile.mkdtemp()


def _reset_db_module():
    """Reset module-level connection state between tests."""
    db.close_connection()


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
        conn = db.get_connection(addon_dir, "TestProfile")
        assert isinstance(conn, sqlite3.Connection)

    def test_creates_pdf_progress_table(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir, "TestProfile")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "pdf_progress" in tables
        columns = [r[1] for r in conn.execute("PRAGMA table_info(pdf_progress)").fetchall()]
        assert "read_anchor_json" in columns

    def test_creates_pdf_daily_limits_tables(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir, "TestProfile")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "pdf_daily_limits" in tables
        assert "pdf_daily_limit_usage" in tables

    def test_creates_pdf_highlights_table(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir, "TestProfile")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "pdf_highlights" in tables

    def test_creates_priorities_table(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir, "TestProfile")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "priorities" in tables

    def test_creates_pdf_text_index_table(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir, "TestProfile")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "pdf_text_index" in tables

    def test_creates_web_card_sources_table(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir, "TestProfile")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "web_card_sources" in tables

    def test_creates_web_progress_table(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir, "TestProfile")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "web_progress" in tables

    def test_creates_browser_media_refs_table(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir, "TestProfile")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "browser_media_refs" in tables

    def test_creates_reader_bookmarks_table(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir, "TestProfile")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "reader_bookmarks" in tables

    def test_creates_writing_progress_table(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir, "TestProfile")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "writing_progress" in tables

    def test_creates_writing_word_stats_table(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir, "TestProfile")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "writing_word_stats" in tables

    def test_creates_reviewer_recent_tags_table(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir, "TestProfile")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "reviewer_recent_tags" in tables

    def test_creates_topic_postpones_table(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir, "TestProfile")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "topic_postpones" in tables

    def test_creates_item_postpones_table(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir, "TestProfile")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "item_postpones" in tables

    def test_creates_custom_schedule_rules_table(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir, "TestProfile")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "custom_schedule_rules" in tables

    def test_creates_knowledge_tree_nodes_table(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir, "TestProfile")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "knowledge_tree_nodes" in tables

    def test_creates_knowledge_tree_postpone_presets_table(self):
        addon_dir = _fresh_dir()
        conn = db.get_connection(addon_dir, "TestProfile")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "knowledge_tree_postpone_presets" in tables

    def test_db_file_created_inside_user_files(self):
        addon_dir = _fresh_dir()
        db.get_connection(addon_dir, "TestProfile")
        expected = os.path.join(addon_dir, "user_files", "TestProfile", db.DB_NAME)
        assert os.path.isfile(expected)

    def test_idempotent_same_dir_reuses_connection(self):
        addon_dir = _fresh_dir()
        conn1 = db.get_connection(addon_dir, "TestProfile")
        conn2 = db.get_connection(addon_dir, "TestProfile")
        assert conn1 is conn2

    def test_different_dir_creates_new_connection(self):
        dir1 = _fresh_dir()
        dir2 = _fresh_dir()
        conn1 = db.get_connection(dir1, "TestProfile")
        _reset_db_module()
        conn2 = db.get_connection(dir2, "TestProfile")
        # Both are valid connections but to different files
        assert isinstance(conn1, sqlite3.Connection)
        assert isinstance(conn2, sqlite3.Connection)
        assert conn1 is not conn2


class TestDatabaseEditorHelpers:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db_module()

    def test_create_database_checkpoint_copies_profile_db(self):
        conn = db.get_connection(self.addon_dir, "TestProfile")
        conn.execute("INSERT OR REPLACE INTO priorities(card_id, priority) VALUES (?, ?)", (77, 12.5))
        conn.commit()

        checkpoint = db.create_database_checkpoint(self.addon_dir, "TestProfile", label="sqlite_editor")

        assert checkpoint["filename"].endswith("_sqlite_editor.sqlite3")
        assert os.path.isfile(checkpoint["path"])
        snapshot_conn = sqlite3.connect(checkpoint["path"])
        try:
            row = snapshot_conn.execute(
                "SELECT priority FROM priorities WHERE card_id = ?",
                (77,),
            ).fetchone()
        finally:
            snapshot_conn.close()
        assert row == (12.5,)

    def test_list_database_checkpoints_returns_newest_first(self):
        first = db.create_database_checkpoint(self.addon_dir, "TestProfile", label="first")
        second = db.create_database_checkpoint(self.addon_dir, "TestProfile", label="second")

        checkpoints = db.list_database_checkpoints(self.addon_dir, "TestProfile", limit=5)

        assert checkpoints
        assert checkpoints[0]["path"] == second["path"]
        assert {row["path"] for row in checkpoints} >= {first["path"], second["path"]}

    def test_open_database_editor_connection_read_only_blocks_writes(self):
        db.get_connection(self.addon_dir, "TestProfile").commit()
        conn = db.open_database_editor_connection(self.addon_dir, "TestProfile", read_only=True)
        try:
            with pytest.raises(sqlite3.OperationalError):
                conn.execute(
                    "INSERT OR REPLACE INTO priorities(card_id, priority) VALUES (?, ?)",
                    (91, 55.0),
                )
        finally:
            conn.close()

    def test_open_database_editor_connection_read_write_allows_writes(self):
        db.get_connection(self.addon_dir, "TestProfile").commit()
        conn = db.open_database_editor_connection(self.addon_dir, "TestProfile", read_only=False)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO priorities(card_id, priority) VALUES (?, ?)",
                (92, 44.0),
            )
            conn.commit()
        finally:
            conn.close()
        row = db.get_connection(self.addon_dir, "TestProfile").execute(
            "SELECT priority FROM priorities WHERE card_id = ?",
            (92,),
        ).fetchone()
        assert row == (44.0,)


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
        db.replace_pdf_text_index(self.addon_dir, "TestProfile", 1, ["Hello world", "Goodbye world"])
        results = db.search_pdf_text_index(self.addon_dir, "TestProfile", "hello")
        assert len(results) == 1
        card_id, page, text = results[0]
        assert card_id == 1
        assert page == 1
        assert "Hello" in text

    def test_search_returns_correct_page_number(self):
        db.replace_pdf_text_index(self.addon_dir, "TestProfile", 2, ["first page", "second page with needle"])
        results = db.search_pdf_text_index(self.addon_dir, "TestProfile", "needle")
        assert len(results) == 1
        assert results[0][1] == 2  # page 2

    def test_replace_removes_old_entries(self):
        db.replace_pdf_text_index(self.addon_dir, "TestProfile", 3, ["old content about cats"])
        db.replace_pdf_text_index(self.addon_dir, "TestProfile", 3, ["new content about dogs"])
        cats = db.search_pdf_text_index(self.addon_dir, "TestProfile", "cats")
        dogs = db.search_pdf_text_index(self.addon_dir, "TestProfile", "dogs")
        assert cats == []
        assert len(dogs) == 1

    def test_empty_pages_not_stored(self):
        db.replace_pdf_text_index(self.addon_dir, "TestProfile", 4, ["", "   ", "real content here"])
        conn = db.get_connection(self.addon_dir, "TestProfile")
        rows = conn.execute(
            "SELECT page FROM pdf_text_index WHERE card_id = 4 ORDER BY page"
        ).fetchall()
        # Only the non-empty page (index 2, page 3) should be stored
        assert rows == [(3,)]

    def test_short_query_returns_empty(self):
        db.replace_pdf_text_index(self.addon_dir, "TestProfile", 5, ["some text here"])
        results = db.search_pdf_text_index(self.addon_dir, "TestProfile", "a")
        assert results == []

    def test_search_across_multiple_cards(self):
        db.replace_pdf_text_index(self.addon_dir, "TestProfile", 10, ["python programming language"])
        db.replace_pdf_text_index(self.addon_dir, "TestProfile", 11, ["python snake species"])
        results = db.search_pdf_text_index(self.addon_dir, "TestProfile", "python")
        card_ids = {r[0] for r in results}
        assert card_ids == {10, 11}

    def test_case_insensitive_search(self):
        db.replace_pdf_text_index(self.addon_dir, "TestProfile", 6, ["The Quick Brown Fox"])
        results = db.search_pdf_text_index(self.addon_dir, "TestProfile", "quick brown")
        assert len(results) == 1

    def test_replace_with_empty_list_clears_index(self):
        db.replace_pdf_text_index(self.addon_dir, "TestProfile", 7, ["some content"])
        db.replace_pdf_text_index(self.addon_dir, "TestProfile", 7, [])
        conn = db.get_connection(self.addon_dir, "TestProfile")
        count = conn.execute(
            "SELECT COUNT(*) FROM pdf_text_index WHERE card_id = 7"
        ).fetchone()[0]
        assert count == 0


class TestNoteOcrIndex:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db_module()

    def test_insert_and_search_finds_term(self):
        db.replace_note_ocr_index(
            self.addon_dir,
            "TestProfile",
            100,
            [10],
            [("diagram.png", "Cell membrane transport")],
        )
        results = db.search_note_ocr_index(self.addon_dir, "TestProfile", "membrane")
        assert results == [(100, 10, "diagram.png", "Cell membrane transport")]

    def test_replace_removes_old_rows(self):
        db.replace_note_ocr_index(
            self.addon_dir,
            "TestProfile",
            101,
            [11],
            [("old.png", "old text")],
        )
        db.replace_note_ocr_index(
            self.addon_dir,
            "TestProfile",
            101,
            [11],
            [("new.png", "new text")],
        )
        assert db.search_note_ocr_index(self.addon_dir, "TestProfile", "old") == []
        assert db.search_note_ocr_index(self.addon_dir, "TestProfile", "new") == [
            (101, 11, "new.png", "new text")
        ]

    def test_fallback_text_used_when_no_image_rows(self):
        db.replace_note_ocr_index(
            self.addon_dir,
            "TestProfile",
            102,
            [12],
            [],
            fallback_text="hidden field text",
        )
        assert db.search_note_ocr_index(self.addon_dir, "TestProfile", "hidden") == [
            (102, 12, "", "hidden field text")
        ]

    def test_prune_note_ocr_index_rows_removes_missing_note_rows(self):
        db.replace_note_ocr_index(
            self.addon_dir,
            "TestProfile",
            103,
            [13],
            [("diagram.png", "alpha text")],
        )

        counts = db.prune_note_ocr_index_rows(
            self.addon_dir,
            "TestProfile",
            live_note_ids={999},
            live_card_ids={13},
        )

        assert counts == {
            "note_ocr_index_missing_note": 1,
            "note_ocr_index_missing_card": 0,
            "note_ocr_index_total": 1,
        }
        assert db.search_note_ocr_index(self.addon_dir, "TestProfile", "alpha") == []

    def test_prune_note_ocr_index_rows_removes_missing_card_rows_but_keeps_live_rows(self):
        db.replace_note_ocr_index(
            self.addon_dir,
            "TestProfile",
            104,
            [14],
            [("diagram.png", "beta text")],
        )
        db.replace_note_ocr_index(
            self.addon_dir,
            "TestProfile",
            105,
            [15],
            [("diagram.png", "gamma text")],
        )

        counts = db.prune_note_ocr_index_rows(
            self.addon_dir,
            "TestProfile",
            live_note_ids={104, 105},
            live_card_ids={15},
        )

        assert counts == {
            "note_ocr_index_missing_note": 0,
            "note_ocr_index_missing_card": 1,
            "note_ocr_index_total": 1,
        }
        assert db.search_note_ocr_index(self.addon_dir, "TestProfile", "beta") == []
        assert db.search_note_ocr_index(self.addon_dir, "TestProfile", "gamma") == [
            (105, 15, "diagram.png", "gamma text")
        ]


class TestBrowserMediaRefs:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db_module()

    def test_set_and_get_card_browser_media_ref(self):
        db.set_card_browser_media_ref(
            self.addon_dir,
            "TestProfile",
            42,
            page_url="https://example.com/article",
            media_url="https://player.example.com/video",
            media_title="Example clip",
            media_seconds=83.2,
            updated_at=1234567890,
        )
        ref = db.get_card_browser_media_ref(self.addon_dir, "TestProfile", 42)
        assert ref["page_url"] == "https://example.com/article"
        assert ref["media_url"] == "https://player.example.com/video"
        assert ref["media_title"] == "Example clip"
        assert ref["media_seconds"] == 83.2
        assert ref["updated_at"] == 1234567890

    def test_get_card_browser_media_ref_defaults_when_missing(self):
        ref = db.get_card_browser_media_ref(self.addon_dir, "TestProfile", 999)
        assert ref == {
            "page_url": "",
            "media_url": "",
            "media_title": "",
            "media_seconds": 0.0,
            "updated_at": 0,
        }

    def test_set_card_browser_media_ref_clamps_negative_seconds(self):
        db.set_card_browser_media_ref(
            self.addon_dir,
            "TestProfile",
            7,
            page_url="https://example.com/article",
            media_seconds=-5,
            updated_at=99,
        )
        ref = db.get_card_browser_media_ref(self.addon_dir, "TestProfile", 7)
        assert ref["media_seconds"] == 0.0
        assert ref["updated_at"] == 99


class TestCustomScheduleRules:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db_module()

    def test_set_and_get_custom_schedule_rule_round_trip(self):
        saved = db.set_custom_schedule_rule(
            self.addon_dir,
            "TestProfile",
            42,
            mode="fixed_repeat",
            interval_value=2,
            interval_unit="weeks",
            preset_label="Every 2 weeks",
        )
        loaded = db.get_custom_schedule_rule(self.addon_dir, "TestProfile", 42)
        assert saved["mode"] == "fixed_repeat"
        assert loaded is not None
        assert loaded["card_id"] == 42
        assert loaded["interval_value"] == 2
        assert loaded["interval_unit"] == "weeks"
        assert loaded["preset_label"] == "Every 2 weeks"

    def test_get_custom_schedule_rules_filters_to_requested_ids(self):
        db.set_custom_schedule_rule(
            self.addon_dir,
            "TestProfile",
            1,
            mode="minimum_cadence",
            interval_value=2,
            interval_unit="days",
        )
        db.set_custom_schedule_rule(
            self.addon_dir,
            "TestProfile",
            2,
            mode="one_time",
            interval_value=1,
            interval_unit="months",
        )
        rules = db.get_custom_schedule_rules(self.addon_dir, "TestProfile", [2, 3])
        assert set(rules) == {2}
        assert rules[2]["mode"] == "one_time"

    def test_clear_custom_schedule_rule_removes_row(self):
        db.set_custom_schedule_rule(
            self.addon_dir,
            "TestProfile",
            9,
            mode="minimum_cadence",
            interval_value=2,
            interval_unit="days",
        )
        assert db.clear_custom_schedule_rule(self.addon_dir, "TestProfile", 9) is True
        assert db.get_custom_schedule_rule(self.addon_dir, "TestProfile", 9) is None


class TestPdfDailyLimits:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db_module()

    def test_pdf_daily_limit_config_defaults_when_missing(self):
        config = db.get_pdf_daily_limit_config(self.addon_dir, "TestProfile", 77)
        assert config == {
            "daily_page_limit": 0,
            "enforcement_mode": "warning",
            "updated_at": 0,
        }

    def test_set_and_get_pdf_daily_limit_config(self):
        db.set_pdf_daily_limit_config(
            self.addon_dir,
            "TestProfile",
            77,
            daily_page_limit=12,
            enforcement_mode="soft_lock",
            updated_at=123,
        )
        config = db.get_pdf_daily_limit_config(self.addon_dir, "TestProfile", 77)
        assert config == {
            "daily_page_limit": 12,
            "enforcement_mode": "soft_lock",
            "updated_at": 123,
        }

    def test_zero_limit_deletes_pdf_daily_limit_config(self):
        db.set_pdf_daily_limit_config(
            self.addon_dir,
            "TestProfile",
            77,
            daily_page_limit=9,
            enforcement_mode="hard_stop",
        )
        db.set_pdf_daily_limit_config(
            self.addon_dir,
            "TestProfile",
            77,
            daily_page_limit=0,
            enforcement_mode="warning",
        )
        assert db.get_pdf_daily_limit_config(self.addon_dir, "TestProfile", 77) == {
            "daily_page_limit": 0,
            "enforcement_mode": "warning",
            "updated_at": 0,
        }

    def test_pdf_daily_limit_usage_defaults_when_missing(self):
        usage = db.get_pdf_daily_limit_usage(self.addon_dir, "TestProfile", 9, "2026-04-18")
        assert usage == {
            "logical_date": "2026-04-18",
            "baseline_page": 0,
            "highest_page": 0,
            "override_enabled": False,
            "updated_at": 0,
        }


class TestWritingProgress:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db_module()

    def test_defaults_when_missing(self):
        progress = db.get_writing_progress(self.addon_dir, "TestProfile", 55)
        assert progress == {
            "cursor_position": 0,
            "scroll_ratio": 0.0,
            "font_scale": 1.0,
            "wrap_enabled": True,
            "focus_mode": False,
            "preview_visible": True,
            "highlight_current_line": True,
            "bookmark_block_number": -1,
            "updated_at": 0,
        }

    def test_round_trip(self):
        saved = db.set_writing_progress(
            self.addon_dir,
            "TestProfile",
            55,
            cursor_position=120,
            scroll_ratio=0.35,
            font_scale=1.45,
            wrap_enabled=False,
            focus_mode=True,
            preview_visible=False,
            highlight_current_line=False,
            bookmark_block_number=17,
        )
        loaded = db.get_writing_progress(self.addon_dir, "TestProfile", 55)

        assert loaded["cursor_position"] == 120
        assert loaded["scroll_ratio"] == 0.35
        assert loaded["font_scale"] == 1.45
        assert loaded["wrap_enabled"] is False
        assert loaded["focus_mode"] is True
        assert loaded["preview_visible"] is False
        assert loaded["highlight_current_line"] is False
        assert loaded["bookmark_block_number"] == 17
        assert loaded["updated_at"] >= saved["updated_at"] >= 1

    def test_normalizes_values(self):
        db.set_writing_progress(
            self.addon_dir,
            "TestProfile",
            77,
            cursor_position=-4,
            scroll_ratio=8,
            font_scale=9,
            wrap_enabled=1,
            focus_mode=0,
            preview_visible=2,
            highlight_current_line=2,
            bookmark_block_number=-99,
        )
        loaded = db.get_writing_progress(self.addon_dir, "TestProfile", 77)

        assert loaded["cursor_position"] == 0
        assert loaded["scroll_ratio"] == 1.0
        assert loaded["font_scale"] == 2.4
        assert loaded["wrap_enabled"] is True
        assert loaded["focus_mode"] is False
        assert loaded["preview_visible"] is True
        assert loaded["highlight_current_line"] is True
        assert loaded["bookmark_block_number"] == -1


class TestWritingWordStats:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db_module()

    def test_defaults_when_missing(self):
        stats = db.get_writing_word_stats(self.addon_dir, "TestProfile", 55)
        assert stats == {
            "current_word_count": 0,
            "daily_logical_date": "",
            "daily_baseline_words": 0,
            "updated_at": 0,
        }

    def test_round_trip(self):
        saved = db.set_writing_word_stats(
            self.addon_dir,
            "TestProfile",
            55,
            current_word_count=320,
            daily_logical_date="2026-04-23",
            daily_baseline_words=180,
        )
        loaded = db.get_writing_word_stats(self.addon_dir, "TestProfile", 55)

        assert loaded["current_word_count"] == 320
        assert loaded["daily_logical_date"] == "2026-04-23"
        assert loaded["daily_baseline_words"] == 180
        assert loaded["updated_at"] >= saved["updated_at"] >= 1

    def test_normalizes_values(self):
        db.set_writing_word_stats(
            self.addon_dir,
            "TestProfile",
            77,
            current_word_count=-20,
            daily_logical_date=" 2026-04-23 ",
            daily_baseline_words=-4,
        )
        loaded = db.get_writing_word_stats(self.addon_dir, "TestProfile", 77)
        assert loaded["current_word_count"] == 0
        assert loaded["daily_logical_date"] == "2026-04-23"
        assert loaded["daily_baseline_words"] == 0


class TestPdfDailyLimitUsage:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db_module()

    def test_set_and_get_pdf_daily_limit_usage(self):
        db.set_pdf_daily_limit_usage(
            self.addon_dir,
            "TestProfile",
            9,
            "2026-04-18",
            baseline_page=14,
            highest_page=20,
            override_enabled=True,
            updated_at=999,
        )
        usage = db.get_pdf_daily_limit_usage(self.addon_dir, "TestProfile", 9, "2026-04-18")
        assert usage == {
            "logical_date": "2026-04-18",
            "baseline_page": 14,
            "highest_page": 20,
            "override_enabled": True,
            "updated_at": 999,
        }

    def test_clear_pdf_daily_limit_usage(self):
        db.set_pdf_daily_limit_usage(
            self.addon_dir,
            "TestProfile",
            9,
            "2026-04-18",
            baseline_page=2,
            highest_page=6,
        )
        db.clear_pdf_daily_limit_usage(
            self.addon_dir,
            "TestProfile",
            9,
            logical_date="2026-04-18",
        )
        usage = db.get_pdf_daily_limit_usage(self.addon_dir, "TestProfile", 9, "2026-04-18")
        assert usage["highest_page"] == 0


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
        db.add_pdf_card_source(
            self.addon_dir,
            "TestProfile",
            pdf_card_id=1,
            page=3,
            note_id=999,
            excerpt="test excerpt",
            pdf_filename="paper.pdf",
        )
        sources = db.get_pdf_card_sources(self.addon_dir, "TestProfile", pdf_card_id=1, page=3)
        assert len(sources) == 1
        assert sources[0]["note_id"] == 999
        assert sources[0]["excerpt"] == "test excerpt"
        assert db.get_pdf_card_source_filename(self.addon_dir, "TestProfile", 1, 3) == "paper.pdf"
        assert db.get_pdf_referenced_filenames(self.addon_dir, "TestProfile") == ["paper.pdf"]

    def test_get_pdf_page_card_counts(self):
        db.add_pdf_card_source(self.addon_dir, "TestProfile", pdf_card_id=2, page=1, note_id=101)
        db.add_pdf_card_source(self.addon_dir, "TestProfile", pdf_card_id=2, page=1, note_id=102)
        db.add_pdf_card_source(self.addon_dir, "TestProfile", pdf_card_id=2, page=2, note_id=103)
        counts = db.get_pdf_page_card_counts(self.addon_dir, "TestProfile", pdf_card_id=2)
        assert counts[1] == 2
        assert counts[2] == 1

    def test_delete_pdf_card_sources_for_note_ids(self):
        db.add_pdf_card_source(self.addon_dir, "TestProfile", pdf_card_id=2, page=1, note_id=101)
        db.add_pdf_card_source(self.addon_dir, "TestProfile", pdf_card_id=2, page=1, note_id=102)
        db.add_pdf_card_source(self.addon_dir, "TestProfile", pdf_card_id=3, page=1, note_id=101)

        deleted = db.delete_pdf_card_sources_for_note_ids(
            self.addon_dir,
            "TestProfile",
            pdf_card_id=2,
            note_ids=[101, 999],
        )

        assert deleted == 1
        assert db.get_pdf_card_sources(self.addon_dir, "TestProfile", pdf_card_id=2, page=1) == [
            {"note_id": 102, "excerpt": ""}
        ]
        assert db.get_pdf_card_sources(self.addon_dir, "TestProfile", pdf_card_id=3, page=1) == [
            {"note_id": 101, "excerpt": ""}
        ]

    def test_get_pdf_card_sources_up_to_page(self):
        db.add_pdf_card_source(self.addon_dir, "TestProfile", pdf_card_id=4, page=2, note_id=201, excerpt="two")
        db.add_pdf_card_source(self.addon_dir, "TestProfile", pdf_card_id=4, page=4, note_id=202, excerpt="four")
        db.add_pdf_card_source(self.addon_dir, "TestProfile", pdf_card_id=4, page=7, note_id=203, excerpt="seven")

        rows = db.get_pdf_card_sources_up_to_page(
            self.addon_dir,
            "TestProfile",
            pdf_card_id=4,
            max_page=4,
        )

        assert rows == [
            {"page": 2, "note_id": 201, "excerpt": "two"},
            {"page": 4, "note_id": 202, "excerpt": "four"},
        ]

    def test_get_pdf_document_source_note_ids_deduplicates_in_insert_order(self):
        db.add_pdf_card_source(self.addon_dir, "TestProfile", pdf_card_id=9, page=1, note_id=301)
        db.add_pdf_card_source(self.addon_dir, "TestProfile", pdf_card_id=9, page=3, note_id=302)
        db.add_pdf_card_source(self.addon_dir, "TestProfile", pdf_card_id=9, page=4, note_id=301)
        db.add_pdf_card_source(self.addon_dir, "TestProfile", pdf_card_id=10, page=1, note_id=999)

        note_ids = db.get_pdf_document_source_note_ids(
            self.addon_dir,
            "TestProfile",
            pdf_card_id=9,
        )

        assert note_ids == [301, 302]


class TestPdfDueReviewPromptConfig:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db_module()

    def test_defaults_to_enabled(self):
        cfg = db.get_pdf_due_review_prompt_config(self.addon_dir, "TestProfile", 99)
        assert cfg == {"enabled": True, "updated_at": 0}

    def test_set_and_get_prompt_config(self):
        db.set_pdf_due_review_prompt_config(
            self.addon_dir,
            "TestProfile",
            99,
            enabled=False,
            updated_at=321,
        )
        cfg = db.get_pdf_due_review_prompt_config(self.addon_dir, "TestProfile", 99)
        assert cfg == {"enabled": False, "updated_at": 321}


class TestEpubDailyLimits:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db_module()

    def test_epub_daily_limit_config_defaults_when_missing(self):
        config = db.get_epub_daily_limit_config(self.addon_dir, "TestProfile", 77)
        assert config == {
            "daily_section_limit": 0,
            "enforcement_mode": "warning",
            "updated_at": 0,
        }

    def test_set_and_get_epub_daily_limit_config(self):
        db.set_epub_daily_limit_config(
            self.addon_dir,
            "TestProfile",
            77,
            daily_section_limit=4,
            enforcement_mode="soft_lock",
            updated_at=123,
        )
        config = db.get_epub_daily_limit_config(self.addon_dir, "TestProfile", 77)
        assert config == {
            "daily_section_limit": 4,
            "enforcement_mode": "soft_lock",
            "updated_at": 123,
        }

    def test_epub_daily_limit_usage_round_trip(self):
        db.set_epub_daily_limit_usage(
            self.addon_dir,
            "TestProfile",
            9,
            "2026-04-23",
            baseline_section=1,
            highest_section=3,
            override_enabled=True,
            updated_at=999,
        )
        usage = db.get_epub_daily_limit_usage(self.addon_dir, "TestProfile", 9, "2026-04-23")
        assert usage == {
            "logical_date": "2026-04-23",
            "baseline_section": 1,
            "highest_section": 3,
            "override_enabled": True,
            "updated_at": 999,
        }


class TestEpubDueReviewPromptConfig:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db_module()

    def test_defaults_to_enabled(self):
        cfg = db.get_epub_due_review_prompt_config(self.addon_dir, "TestProfile", 99)
        assert cfg == {"enabled": True, "updated_at": 0}

    def test_set_and_get_prompt_config(self):
        db.set_epub_due_review_prompt_config(
            self.addon_dir,
            "TestProfile",
            99,
            enabled=False,
            updated_at=321,
        )
        cfg = db.get_epub_due_review_prompt_config(self.addon_dir, "TestProfile", 99)
        assert cfg == {"enabled": False, "updated_at": 321}


class TestEpubCardSources:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db_module()

    def test_get_epub_card_sources_up_to_section(self):
        db.add_epub_card_source(self.addon_dir, "TestProfile", epub_card_id=4, section_index=0, note_id=201, excerpt="zero")
        db.add_epub_card_source(self.addon_dir, "TestProfile", epub_card_id=4, section_index=2, note_id=202, excerpt="two")
        db.add_epub_card_source(self.addon_dir, "TestProfile", epub_card_id=4, section_index=4, note_id=203, excerpt="four")

        rows = db.get_epub_card_sources_up_to_section(
            self.addon_dir,
            "TestProfile",
            epub_card_id=4,
            max_section_index=2,
        )

        assert rows == [
            {"section_index": 0, "note_id": 201, "excerpt": "zero"},
            {"section_index": 2, "note_id": 202, "excerpt": "two"},
        ]

    def test_get_epub_document_source_note_ids_deduplicates_in_insert_order(self):
        db.add_epub_card_source(self.addon_dir, "TestProfile", epub_card_id=7, section_index=0, note_id=401, excerpt="zero")
        db.add_epub_card_source(self.addon_dir, "TestProfile", epub_card_id=7, section_index=2, note_id=402, excerpt="two")
        db.add_epub_card_source(self.addon_dir, "TestProfile", epub_card_id=7, section_index=4, note_id=401, excerpt="four")
        db.add_epub_card_source(self.addon_dir, "TestProfile", epub_card_id=8, section_index=0, note_id=999, excerpt="other")

        note_ids = db.get_epub_document_source_note_ids(
            self.addon_dir,
            "TestProfile",
            epub_card_id=7,
        )

        assert note_ids == [401, 402]


class TestWebCardSources:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db_module()

    def test_add_and_retrieve_card_source(self):
        db.add_web_card_source(
            self.addon_dir, "TestProfile",
            web_card_id=5,
            url="https://example.com/docs/intro",
            note_id=777,
            excerpt="api summary",
        )
        sources = db.get_web_card_sources(
            self.addon_dir, "TestProfile",
            web_card_id=5,
            url="https://example.com/docs/intro",
        )
        assert len(sources) == 1
        assert sources[0]["note_id"] == 777
        assert sources[0]["excerpt"] == "api summary"

    def test_sources_are_scoped_to_exact_url(self):
        db.add_web_card_source(
            self.addon_dir, "TestProfile",
            web_card_id=5,
            url="https://example.com/docs/intro",
            note_id=1,
            excerpt="intro",
        )
        db.add_web_card_source(
            self.addon_dir, "TestProfile",
            web_card_id=5,
            url="https://example.com/docs/advanced",
            note_id=2,
            excerpt="advanced",
        )
        intro = db.get_web_card_sources(
            self.addon_dir, "TestProfile",
            web_card_id=5,
            url="https://example.com/docs/intro",
        )
        advanced = db.get_web_card_sources(
            self.addon_dir, "TestProfile",
            web_card_id=5,
            url="https://example.com/docs/advanced",
        )
        assert [row["note_id"] for row in intro] == [1]
        assert [row["note_id"] for row in advanced] == [2]


class TestWebProgressMigration:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db_module()

    def test_existing_url_only_web_progress_table_gets_new_columns(self):
        db_path = os.path.join(self.addon_dir, "user_files", "TestProfile", db.DB_NAME)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE web_progress (card_id INTEGER PRIMARY KEY, url TEXT NOT NULL DEFAULT '')"
        )
        conn.execute(
            "INSERT INTO web_progress (card_id, url) VALUES (?, ?)",
            (7, "https://example.com/legacy"),
        )
        conn.commit()
        conn.close()

        reopened = db.get_connection(self.addon_dir, "TestProfile")
        columns = {
            row[1]
            for row in reopened.execute("PRAGMA table_info(web_progress)").fetchall()
        }
        assert "url" in columns
        assert "scroll_ratio" in columns
        assert "bookmark_url" in columns
        assert "bookmark_payload" in columns
        assert "media_url" in columns
        assert "media_title" in columns
        assert "media_seconds" in columns
        assert "media_updated_at" in columns

        row = reopened.execute(
            "SELECT url, scroll_ratio, bookmark_url, bookmark_payload, media_url, media_title, media_seconds, media_updated_at "
            "FROM web_progress WHERE card_id = ?",
            (7,),
        ).fetchone()
        assert row == ("https://example.com/legacy", 0.0, "", "", "", "", 0.0, 0)


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
        conn1 = db.get_connection(dir1, "TestProfile")
        # Now request a connection for a different dir — lines 32-36 execute
        conn2 = db.get_connection(dir2, "TestProfile")
        assert conn1 is not conn2
        assert isinstance(conn2, sqlite3.Connection)

    def test_switching_profile_closes_old_connection(self):
        """Getting a connection with a different profile should open a new DB."""
        addon_dir = _fresh_dir()
        conn1 = db.get_connection(addon_dir, "Profile1")
        conn2 = db.get_connection(addon_dir, "Profile2")
        assert conn1 is not conn2
        # Each profile gets its own DB file
        import os
        assert os.path.exists(os.path.join(addon_dir, "user_files", "Profile1", db.DB_NAME))
        assert os.path.exists(os.path.join(addon_dir, "user_files", "Profile2", db.DB_NAME))

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
        conn = db.get_connection(dir1, "TestProfile")
        fake_conn.close.assert_called_once()
        assert isinstance(conn, sqlite3.Connection)

    def test_migration_adds_read_page_column(self):
        """If an existing DB lacks read_page, get_connection adds it (line 121)."""
        import os
        import sqlite3 as _sqlite3

        addon_dir = _fresh_dir()
        db_path = os.path.join(addon_dir, "user_files", "TestProfile", db.DB_NAME)
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
        conn = db.get_connection(addon_dir, "TestProfile")
        columns = [r[1] for r in conn.execute("PRAGMA table_info(pdf_progress)").fetchall()]
        assert "read_page" in columns
        assert "read_anchor_json" in columns


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
        result = json.loads(db.export_priorities_json(self.addon_dir, "TestProfile"))
        assert result == {}

    def test_export_priorities_json_with_data(self):
        import json
        conn = db.get_connection(self.addon_dir, "TestProfile")
        conn.execute("INSERT INTO priorities VALUES (1, 25.0)")
        conn.execute("INSERT INTO priorities VALUES (2, 75.0)")
        conn.commit()
        result = json.loads(db.export_priorities_json(self.addon_dir, "TestProfile"))
        assert result == {"1": 25.0, "2": 75.0}

    def test_export_pdf_progress_json_empty(self):
        import json
        result = json.loads(db.export_pdf_progress_json(self.addon_dir, "TestProfile"))
        assert result == {}

    def test_export_pdf_progress_json_with_data(self):
        import json
        conn = db.get_connection(self.addon_dir, "TestProfile")
        conn.execute(
            "INSERT INTO pdf_progress (card_id, page, zoom, read_page, read_anchor_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (10, 3, 1.5, 3, '{"page":3,"x":10.5,"y":22.0,"w":40.0,"h":12.0}'),
        )
        conn.commit()
        result = json.loads(db.export_pdf_progress_json(self.addon_dir, "TestProfile"))
        assert "10" in result
        assert result["10"]["page"] == 3
        assert result["10"]["zoom"] == 1.5
        assert result["10"]["read_page"] == 3
        assert result["10"]["read_anchor"]["page"] == 3

    def test_export_highlights_json_empty(self):
        import json
        result = json.loads(db.export_highlights_json(self.addon_dir, "TestProfile"))
        assert result == {}

    def test_export_highlights_json_with_data(self):
        import json
        conn = db.get_connection(self.addon_dir, "TestProfile")
        conn.execute(
            "INSERT INTO pdf_highlights VALUES ('h1', 5, 2, 'blue', 'some text', 'saved note', '[]')"
        )
        conn.commit()
        result = json.loads(db.export_highlights_json(self.addon_dir, "TestProfile"))
        assert "5" in result
        assert result["5"][0]["id"] == "h1"
        assert result["5"][0]["note"] == "saved note"

    def test_export_stats_json_empty(self):
        import json
        result = json.loads(db.export_stats_json(self.addon_dir, "TestProfile"))
        assert result == {}

    def test_export_stats_json_with_daily_and_lifetime(self):
        import json
        conn = db.get_connection(self.addon_dir, "TestProfile")
        conn.execute(
            "INSERT INTO stats VALUES ('daily', '2026-01-01', '{\"type\": {}}')"
        )
        conn.execute(
            "INSERT INTO stats VALUES ('lifetime', NULL, '{\"type\": {\"topics\": 3}}')"
        )
        conn.commit()
        result = json.loads(db.export_stats_json(self.addon_dir, "TestProfile"))
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
        db.replace_pdf_text_index(self.addon_dir, "TestProfile", 1, ["The quick brown fox jumps over the lazy dog"])

    def teardown_method(self):
        _reset_db_module()

    def test_query_with_only_single_char_tokens_returns_empty(self):
        """All tokens are 1 char — filtered out → return []."""
        result = db.search_pdf_text_index(self.addon_dir, "TestProfile", "a b c")
        assert result == []

    def test_all_query_terms_are_required(self):
        """Broader partial matches should be rejected."""
        result = db.search_pdf_text_index(self.addon_dir, "TestProfile", "quick zebra")
        assert result == []

    def test_multi_token_match(self):
        """Multiple tokens still match when they all appear."""
        result = db.search_pdf_text_index(self.addon_dir, "TestProfile", "quick lazy")
        assert len(result) == 1

    def test_longer_prefix_query_narrows_results(self):
        db.replace_pdf_text_index(
            self.addon_dir, "TestProfile",
            2,
            [
                "Cell membrane transport controls diffusion",
                "Each team member owns a different task",
            ],
        )
        broad = db.search_pdf_text_index(self.addon_dir, "TestProfile", "memb", limit=10)
        narrow = db.search_pdf_text_index(self.addon_dir, "TestProfile", "membra", limit=10)
        assert {cid for cid, _, _ in broad} == {2}
        assert len(broad) == 2
        assert len(narrow) == 1
        assert narrow[0][2].startswith("Cell membrane")

    def test_ordered_matches_rank_ahead_of_looser_matches(self):
        db.replace_pdf_text_index(
            self.addon_dir, "TestProfile",
            2,
            [
                "Cell membrane transport is tightly regulated",
                "Membrane transport happens after the cell adapts",
            ],
        )
        results = db.search_pdf_text_index(self.addon_dir, "TestProfile", "cell transp", limit=5)
        assert len(results) >= 2
        assert results[0][2].startswith("Cell membrane transport")

    def test_limit_stops_early(self):
        """Results are truncated at the limit."""
        for cid in range(1, 10):
            db.replace_pdf_text_index(self.addon_dir, "TestProfile", cid, [f"needle appears here page {cid}"])
        results = db.search_pdf_text_index(self.addon_dir, "TestProfile", "needle", limit=3)
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
        a_factor, interval = db.get_topic_schedule(self.addon_dir, "TestProfile", 42)
        assert a_factor == 3.5
        assert interval == 1

    def test_get_default_when_not_set_uses_override(self):
        a_factor, interval = db.get_topic_schedule(
            self.addon_dir,
            "TestProfile",
            42,
            default_a_factor=4.25,
        )
        assert a_factor == 4.25
        assert interval == 1

    def test_get_default_when_not_set_clamps_override(self):
        a_factor, interval = db.get_topic_schedule(
            self.addon_dir,
            "TestProfile",
            42,
            default_a_factor=1000.0,
        )
        assert a_factor == 100.0
        assert interval == 1

    def test_set_and_get_topic_schedule(self):
        db.set_topic_schedule(self.addon_dir, "TestProfile", 42, 2.0, 7)
        a_factor, interval = db.get_topic_schedule(self.addon_dir, "TestProfile", 42)
        assert a_factor == 2.0
        assert interval == 7

    def test_set_and_get_topic_schedule_state_with_precise_interval(self):
        db.set_topic_schedule(
            self.addon_dir,
            "TestProfile",
            42,
            1.25,
            2,
            precise_interval=1.5625,
        )
        a_factor, precise_interval, interval = db.get_topic_schedule_state(
            self.addon_dir,
            "TestProfile",
            42,
        )
        assert a_factor == 1.25
        assert precise_interval == pytest.approx(1.5625)
        assert interval == 2

    def test_overwrite_existing_schedule(self):
        db.set_topic_schedule(self.addon_dir, "TestProfile", 10, 3.0, 5)
        db.set_topic_schedule(self.addon_dir, "TestProfile", 10, 4.5, 14)
        a_factor, interval = db.get_topic_schedule(self.addon_dir, "TestProfile", 10)
        assert a_factor == 4.5
        assert interval == 14

    def test_rounds_a_factor_to_three_decimals(self):
        db.set_topic_schedule(self.addon_dir, "TestProfile", 7, 2.12345, 3)
        a_factor, _ = db.get_topic_schedule(self.addon_dir, "TestProfile", 7)
        assert a_factor == round(2.12345, 3)

    def test_existing_stored_schedule_ignores_override_default(self):
        db.set_topic_schedule(self.addon_dir, "TestProfile", 7, 2.4, 3)
        a_factor, interval = db.get_topic_schedule(
            self.addon_dir,
            "TestProfile",
            7,
            default_a_factor=9.9,
        )
        assert a_factor == 2.4
        assert interval == 3

    def test_topic_schedule_precise_interval_column_is_created(self):
        conn = db.get_connection(self.addon_dir, "TestProfile")
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(topic_schedule)").fetchall()
        }
        assert "precise_interval" in columns


# ---------------------------------------------------------------------------
# Knowledge tree
# ---------------------------------------------------------------------------


class TestKnowledgeTree:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db_module()

    def test_set_and_get_knowledge_tree_nodes(self):
        db.set_knowledge_tree_structure(
            self.addon_dir,
            "TestProfile",
            [
                {"card_id": 10, "parent_card_id": None, "node_kind": "topic", "sort_order": 0},
                {"card_id": 11, "parent_card_id": 10, "node_kind": "item", "sort_order": 0},
                {"card_id": 12, "parent_card_id": 10, "node_kind": "topic", "sort_order": 1},
            ],
        )

        rows = db.get_knowledge_tree_nodes(self.addon_dir, "TestProfile")

        assert rows == [
            {
                "card_id": 10,
                "parent_card_id": None,
                "node_kind": "topic",
                "sort_order": 0,
                "created_at": rows[0]["created_at"],
                "updated_at": rows[0]["updated_at"],
            },
            {
                "card_id": 11,
                "parent_card_id": 10,
                "node_kind": "item",
                "sort_order": 0,
                "created_at": rows[1]["created_at"],
                "updated_at": rows[1]["updated_at"],
            },
            {
                "card_id": 12,
                "parent_card_id": 10,
                "node_kind": "topic",
                "sort_order": 1,
                "created_at": rows[2]["created_at"],
                "updated_at": rows[2]["updated_at"],
            },
        ]

    def test_set_structure_rejects_duplicate_card_ids(self):
        try:
            db.set_knowledge_tree_structure(
                self.addon_dir,
                "TestProfile",
                [
                    {"card_id": 10, "parent_card_id": None, "node_kind": "topic", "sort_order": 0},
                    {"card_id": 10, "parent_card_id": None, "node_kind": "item", "sort_order": 1},
                ],
            )
            assert False, "Expected duplicate-card-id validation error"
        except ValueError as exc:
            assert "Duplicate knowledge-tree card id" in str(exc)

    def test_set_structure_rejects_missing_parent(self):
        try:
            db.set_knowledge_tree_structure(
                self.addon_dir,
                "TestProfile",
                [
                    {"card_id": 11, "parent_card_id": 99, "node_kind": "item", "sort_order": 0},
                ],
            )
            assert False, "Expected missing-parent validation error"
        except ValueError as exc:
            assert "is missing" in str(exc)

    def test_set_structure_rejects_cycles(self):
        try:
            db.set_knowledge_tree_structure(
                self.addon_dir,
                "TestProfile",
                [
                    {"card_id": 10, "parent_card_id": 11, "node_kind": "topic", "sort_order": 0},
                    {"card_id": 11, "parent_card_id": 10, "node_kind": "item", "sort_order": 0},
                ],
            )
            assert False, "Expected cycle validation error"
        except ValueError as exc:
            assert "cycle" in str(exc).lower()


class TestKnowledgeTreePostponePresets:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db_module()

    def test_save_and_get_postpone_preset(self):
        db.save_knowledge_tree_postpone_preset(
            self.addon_dir,
            "TestProfile",
            "Medicine",
            {"scope": "selected_branch", "item": {"delay_factor": 1.4}},
            branch_root_card_id=10,
            is_default=True,
        )

        preset = db.get_knowledge_tree_postpone_preset(
            self.addon_dir,
            "TestProfile",
            "Medicine",
        )

        assert preset is not None
        assert preset["name"] == "Medicine"
        assert preset["branch_root_card_id"] == 10
        assert preset["config"]["scope"] == "selected_branch"
        assert preset["config"]["item"]["delay_factor"] == 1.4
        assert preset["is_default"] is True

    def test_set_default_postpone_preset_clears_previous_default(self):
        db.save_knowledge_tree_postpone_preset(
            self.addon_dir,
            "TestProfile",
            "Default",
            {"scope": "all_outstanding"},
            is_default=True,
        )
        db.save_knowledge_tree_postpone_preset(
            self.addon_dir,
            "TestProfile",
            "Branch",
            {"scope": "selected_branch"},
            branch_root_card_id=20,
            is_default=False,
        )

        changed = db.set_default_knowledge_tree_postpone_preset(
            self.addon_dir,
            "TestProfile",
            "Branch",
        )

        presets = db.get_knowledge_tree_postpone_presets(self.addon_dir, "TestProfile")
        default_flags = {preset["name"]: preset["is_default"] for preset in presets}

        assert changed is True
        assert default_flags == {"Branch": True, "Default": False}

    def test_delete_postpone_preset_removes_row(self):
        db.save_knowledge_tree_postpone_preset(
            self.addon_dir,
            "TestProfile",
            "Temporary",
            {"scope": "current_browser"},
        )

        deleted = db.delete_knowledge_tree_postpone_preset(
            self.addon_dir,
            "TestProfile",
            "Temporary",
        )

        assert deleted is True
        assert db.get_knowledge_tree_postpone_preset(
            self.addon_dir,
            "TestProfile",
            "Temporary",
        ) is None


class TestReviewerRecentTags:
    def setup_method(self):
        _reset_db_module()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db_module()

    def test_returns_empty_list_by_default(self):
        assert db.get_recent_reviewer_tags(self.addon_dir, "TestProfile") == []

    def test_touch_and_get_recent_tags_uses_newest_first(self):
        db.touch_recent_reviewer_tags(
            self.addon_dir,
            "TestProfile",
            ["biology", "chemistry"],
            used_at=100,
        )
        db.touch_recent_reviewer_tags(
            self.addon_dir,
            "TestProfile",
            ["physics"],
            used_at=200,
        )

        assert db.get_recent_reviewer_tags(self.addon_dir, "TestProfile") == [
            "physics",
            "chemistry",
            "biology",
        ]

    def test_touch_updates_existing_tag_and_trims_limit(self):
        db.touch_recent_reviewer_tags(
            self.addon_dir,
            "TestProfile",
            ["one", "two", "three"],
            used_at=100,
            limit=2,
        )
        db.touch_recent_reviewer_tags(
            self.addon_dir,
            "TestProfile",
            ["One"],
            used_at=300,
            limit=2,
        )

        assert db.get_recent_reviewer_tags(self.addon_dir, "TestProfile", limit=5) == [
            "One",
            "three",
        ]
