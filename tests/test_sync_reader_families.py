"""Bookmark and reading-position families (docs/architecture/shared-folder-sync.md §2, design PR 7)."""

import itertools
import json
import sqlite3

import pytest

import sync_apply
import sync_capture
import sync_exchange
import sync_records
from sync_records import CardRef

BOOKMARKS = sync_records.FAMILIES["reader_bookmark"]
POSITIONS = sync_records.FAMILIES["reading_position"]
CARD_7 = CardRef(card_id=7, note_id=70, guid="guid-7", uploaded_usn=12)


def _anki(card_ids):
    return {7: CARD_7} if 7 in card_ids else {}


@pytest.fixture
def conn():
    import db
    from db_schema import initialize_schema
    connection = sqlite3.connect(":memory:", isolation_level="")
    initialize_schema(connection, bootstrap=db._create_tables, migrations=db._SCHEMA_MIGRATIONS)
    yield connection
    connection.close()


def _bookmark(conn, bookmark_id="b1", reader="pdf", location='{"page": 3}', comment="", updated_at=100):
    with conn:
        conn.execute("INSERT OR REPLACE INTO reader_bookmarks(id, card_id, reader_type, label, comment_text, "
                     "location_json, created_at, updated_at) VALUES (?, 7, ?, 'Page 3', ?, ?, 50, ?)",
                     (bookmark_id, reader, comment, location, updated_at))


# --- Bookmarks ------------------------------------------------------------------

def test_a_bookmark_is_one_record_keyed_by_its_card_and_id(conn):
    _bookmark(conn)

    assert list(BOOKMARKS.scan(conn)) == [("card:7/bookmark:b1", {
        "reader_type": "pdf", "label": "Page 3", "comment_text": "", "location": {"page": 3}, "created_at": 50})]
    assert BOOKMARKS.card_id("card:7/bookmark:b1") == 7


def test_touching_only_a_bookmarks_updated_at_changes_nothing_that_syncs(conn):
    _bookmark(conn, updated_at=100)
    before = dict(BOOKMARKS.scan(conn))

    _bookmark(conn, updated_at=999)

    assert dict(BOOKMARKS.scan(conn)) == before


def test_writing_bookmarks_stay_local_until_writing_has_a_contract(conn):
    _bookmark(conn, reader="writing", location='{"block_number": 0, "cursor_position": 0, "scroll_ratio": 0.0}')

    assert list(BOOKMARKS.scan(conn)) == []


def test_a_written_bookmark_reads_back_and_keeps_the_device_timestamp_local(conn):
    value = {"reader_type": "epub", "label": "Section 2", "comment_text": "why",
             "location": {"section_index": 1, "scroll_ratio": 0.25}, "created_at": 70}
    BOOKMARKS.write(conn, "card:7/bookmark:b9", value)

    assert BOOKMARKS.read(conn, "card:7/bookmark:b9") == value
    BOOKMARKS.delete(conn, "card:7/bookmark:b9")
    assert BOOKMARKS.read(conn, "card:7/bookmark:b9") is None


@pytest.mark.parametrize("value", [
    {"reader_type": "comic", "label": "x", "comment_text": "", "location": {}, "created_at": 1},
    {"reader_type": "writing", "label": "x", "comment_text": "", "location": {"block_number": 0,
                                                                             "cursor_position": 0,
                                                                             "scroll_ratio": 0.0}, "created_at": 1},
    {"reader_type": "pdf", "label": "x", "comment_text": "", "location": {"page": 0}, "created_at": 1},
    {"reader_type": "pdf", "label": "x" * 161, "comment_text": "", "location": {"page": 1}, "created_at": 1},
    {"reader_type": "pdf", "label": "x", "comment_text": "c" * 241, "location": {"page": 1}, "created_at": 1},
    {"reader_type": "pdf", "label": "x", "comment_text": "", "location": {"page": 1}, "created_at": -1},
    {"reader_type": "web", "label": "x", "comment_text": "",
     "location": {"url": "https://e.org", "scroll_ratio": 0.0, "bookmark_payload": {"b": "x" * 70000}},
     "created_at": 1},
], ids=["unknown-reader", "writing", "page-zero", "long-label", "long-comment", "negative-time", "huge-payload"])
def test_incoming_bookmarks_must_be_ones_this_device_could_have_saved(value):
    with pytest.raises(ValueError):
        BOOKMARKS.validate("card:7/bookmark:b1", value)


@pytest.mark.parametrize("key", ["card:7/bookmark:", "card:7/bookmark:../x", "card:7", "card:7/pdf"])
def test_bookmark_keys_name_one_card_and_a_safe_id(key):
    with pytest.raises(ValueError):
        BOOKMARKS.validate(key, None)


# --- Reading positions ----------------------------------------------------------

def test_each_reader_contributes_one_position_record_per_card(conn):
    with conn:
        conn.execute("INSERT INTO pdf_progress(card_id, page, zoom, scroll_ratio, read_page) VALUES (7, 5, 1.5, 0.5, 4)")
        conn.execute("INSERT INTO epub_progress(card_id, section_index, scroll_ratio, is_finished, read_section_index, "
                     "font_scale) VALUES (7, 2, 0.25, 0, 1, 1.4)")
        conn.execute("INSERT INTO video_progress(card_id, position) VALUES (7, 61.5)")
        conn.execute("INSERT INTO web_progress(card_id, url, scroll_ratio) VALUES (7, 'https://e.org/a', 0.75)")

    records = dict(POSITIONS.scan(conn))

    assert records == {
        "card:7/pdf": {"page": 5, "scroll_ratio": 0.5, "read_page": 4, "read_anchor_json": ""},
        "card:7/epub": {"section_index": 2, "scroll_ratio": 0.25, "is_finished": False, "read_section_index": 1,
                        "read_anchor_json": ""},
        "card:7/video": {"position": 61.5},
        "card:7/web": {"url": "https://e.org/a", "scroll_ratio": 0.75, "bookmark_url": "", "bookmark_payload": "",
                       "media_url": "", "media_title": "", "media_seconds": 0.0},
    }


def test_display_preferences_such_as_zoom_and_font_scale_do_not_sync(conn):
    with conn:
        conn.execute("INSERT INTO pdf_progress(card_id, page, zoom) VALUES (7, 5, 1.0)")
    before = dict(POSITIONS.scan(conn))

    with conn:
        conn.execute("UPDATE pdf_progress SET zoom=2.5, appearance_mode='dark' WHERE card_id=7")

    assert dict(POSITIONS.scan(conn)) == before


def test_writing_a_position_keeps_this_devices_zoom(conn):
    with conn:
        conn.execute("INSERT INTO pdf_progress(card_id, page, zoom) VALUES (7, 1, 2.5)")

    POSITIONS.write(conn, "card:7/pdf", {"page": 9, "scroll_ratio": 0.1, "read_page": 8, "read_anchor_json": ""})

    assert conn.execute("SELECT page, zoom FROM pdf_progress WHERE card_id=7").fetchone() == (9, 2.5)


def test_writing_a_position_for_a_new_card_uses_the_tables_defaults_for_local_columns(conn):
    POSITIONS.write(conn, "card:7/epub", {"section_index": 3, "scroll_ratio": 0.0, "is_finished": True,
                                          "read_section_index": 3, "read_anchor_json": ""})

    assert conn.execute("SELECT section_index, is_finished, font_scale FROM epub_progress").fetchone() == (3, 1, 1.0)


@pytest.mark.parametrize("key,value", [
    ("card:7/pdf", {"page": 0, "scroll_ratio": 0.0, "read_page": 0, "read_anchor_json": ""}),
    ("card:7/pdf", {"page": 1, "scroll_ratio": 1.5, "read_page": 0, "read_anchor_json": ""}),
    ("card:7/pdf", {"page": 1, "scroll_ratio": 0.0, "read_page": 0}),
    ("card:7/pdf", {"page": 1, "scroll_ratio": 0.0, "read_page": 0, "read_anchor_json": "{not json"}),
    ("card:7/video", {"position": -1.0}),
    ("card:7/epub", {"section_index": 0, "scroll_ratio": 0.0, "is_finished": 1, "read_section_index": 0,
                     "read_anchor_json": ""}),
    ("card:7/web", {"url": "u" * 5000, "scroll_ratio": 0.0, "bookmark_url": "", "bookmark_payload": "",
                    "media_url": "", "media_title": "", "media_seconds": 0.0}),
    ("card:7/writing", {"position": 0.0}),
], ids=["page-zero", "ratio-above-one", "missing-field", "anchor-not-json", "negative-seconds",
        "finished-not-bool", "long-url", "unsupported-reader"])
def test_incoming_positions_must_be_ones_a_reader_could_have_saved(key, value):
    with pytest.raises(ValueError):
        POSITIONS.validate(key, value)


# --- End to end -----------------------------------------------------------------

def _device(tmp_path, name, folder, library_id=None):
    import db
    from db_schema import initialize_schema
    connection = sqlite3.connect(tmp_path / f"{name}.db", isolation_level="")
    initialize_schema(connection, bootstrap=db._create_tables, migrations=db._SCHEMA_MIGRATIONS)
    counter = itertools.count(1)
    sync_capture.enable_sync(connection, make_id=lambda: f"{name}-{next(counter)}", library_id=library_id)
    return connection


def _sync(conn, folder):
    sync_capture.capture(conn, sync_records.FAMILIES, _anki, now=lambda: 1)
    sync_exchange.publish(conn, folder, now=lambda: 2)
    sync_exchange.receive(conn, folder, sync_records.FAMILIES, now=lambda: 3)
    sync_apply.apply(conn, sync_records.FAMILIES, _anki, now=lambda: 4)
    sync_capture.capture(conn, sync_records.FAMILIES, _anki, now=lambda: 5)
    sync_exchange.publish(conn, folder, now=lambda: 6)


def test_a_bookmark_and_the_reading_position_follow_the_reader_but_zoom_stays(tmp_path):
    folder = tmp_path / "Cloud"
    folder.mkdir()
    laptop = _device(tmp_path, "laptop", folder)
    desktop = _device(tmp_path, "desktop", folder, sync_capture.sync_identity(laptop).library_id)
    with desktop:
        desktop.execute("INSERT INTO pdf_progress(card_id, page, zoom) VALUES (7, 1, 2.0)")
    _sync(desktop, folder)
    _sync(laptop, folder)
    with laptop:
        laptop.execute("UPDATE pdf_progress SET page=42, read_page=41, zoom=0.8 WHERE card_id=7")
    _bookmark(laptop, comment="key argument")

    _sync(laptop, folder)
    _sync(desktop, folder)

    assert desktop.execute("SELECT page, read_page, zoom FROM pdf_progress WHERE card_id=7").fetchone() == (42, 41, 2.0)
    assert desktop.execute("SELECT id, comment_text FROM reader_bookmarks").fetchall() == [("b1", "key argument")]
    assert desktop.execute("SELECT count(*) FROM sync_conflicts").fetchone() == (0,)
    laptop.close()
    desktop.close()
