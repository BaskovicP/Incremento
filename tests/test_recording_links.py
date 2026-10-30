"""Passage references are supplemental, bounded, and bound to content identity."""
import sqlite3

import pytest

import db
from db_schema import initialize_schema
from recording_links import (
    add_recording_link, list_recording_links, remove_recording_link,
    replace_recording_link, normalize_source, validate_segment,
)


PDF = dict(kind="pdf", card_id=7, page=3, scroll=.25, page_y=.4, quote="Opposite angles")


def test_passage_link_round_trip_is_bidirectional_profile_scoped_and_idempotent(tmp_path):
    root = str(tmp_path)
    link = add_recording_link(root, "A", PDF, 8, start=490, end=695, label="Explanation")
    assert add_recording_link(root, "A", PDF, 8, start=490, end=695, label="Explanation") == link
    row = list_recording_links(root, "A", source=PDF)[0]
    assert row == dict(id=link, source=normalize_source(PDF), recording_card_id=8,
                       start=490., end=695., label="Explanation")
    assert list_recording_links(root, "A", recording_card_id=8) == [row]
    assert list_recording_links(root, "A", source={**PDF, "page": 4}) == []
    assert list_recording_links(root, "B", source=PDF) == []


def test_canonical_rebinding_follows_both_ends_and_never_reuses_old_card_ids(tmp_path):
    root = str(tmp_path)
    conn = db.get_connection(root, "A")
    for identity, kind, cid in [("book", "pdf", 7), ("lecture", "video", 8)]:
        conn.execute("INSERT INTO content_items VALUES (?,?,?,?,?,0,0)",
                     (identity, kind, cid, cid * 10, identity))
    conn.commit()
    link = add_recording_link(root, "A", PDF, 8, start=490, label="Explanation")
    conn.execute("UPDATE content_items SET card_id=card_id+10")
    conn.commit()
    assert list_recording_links(root, "A", source=PDF) == []
    row = list_recording_links(root, "A", source={**PDF, "card_id": 17})[0]
    assert row["recording_card_id"] == 18
    assert row["source"]["card_id"] == 17
    assert list_recording_links(root, "A", recording_card_id=8) == []
    assert add_recording_link(root, 'A', {**PDF, 'card_id': 17}, 18, start=490, label='Explanation') == link


def test_either_live_endpoint_can_remove_a_missing_recording_link_without_deleting_content(tmp_path):
    root = str(tmp_path)
    link = add_recording_link(root, "A", PDF, 8, start=10, label="Lecture")
    assert not remove_recording_link(root, "A", link, owner_card_id=99)
    assert not remove_recording_link(root, "B", link, owner_card_id=7)
    assert remove_recording_link(root, "A", link, owner_card_id=8)
    assert list_recording_links(root, "A", source=PDF) == []
    assert db.get_connection(root, "A").execute("SELECT count(*) FROM content_items").fetchone() == (0,)


def test_edit_keeps_the_source_anchor_and_requires_a_live_endpoint(tmp_path):
    root = str(tmp_path)
    link = add_recording_link(root, "A", PDF, 8, start=10, label="Lecture")
    assert not replace_recording_link(root, "A", link, owner_card_id=99,
                                      recording_card_id=9, start=20, end=30, label="Replacement")
    assert replace_recording_link(root, "A", link, owner_card_id=7,
                                  recording_card_id=9, start=20, end=30, label="Replacement")
    row = list_recording_links(root, "A", source=PDF)[0]
    assert row["source"] == normalize_source(PDF)
    assert (row["recording_card_id"], row["start"], row["end"], row["label"]) == (9, 20, 30, "Replacement")


@pytest.mark.parametrize("start,end", [(True, None), (-1, None), (float("nan"), None),
    (float("inf"), None), (0, 0), (5, 4), (0, float("nan")), (0, True), (0, 604801)])
def test_invalid_segment_never_creates_a_link(tmp_path, start, end):
    with pytest.raises(ValueError):
        add_recording_link(str(tmp_path), "A", PDF, 8, start=start, end=end, label="Lecture")
    assert list_recording_links(str(tmp_path), "A", source=PDF) == []


@pytest.mark.parametrize("change", [{"card_id": True}, {"page": 0}, {"scroll": float("nan")},
    {"page_y": 2}, {"kind": "web"}, {"quote": "x" * 2001}, {"quote": "a\0b"}])
def test_invalid_source_is_rejected(change):
    with pytest.raises(ValueError):
        normalize_source({**PDF, **change})


def test_epub_sources_keep_section_and_text_offset_instead_of_reflowed_page(tmp_path):
    source = dict(kind="epub", card_id=7, section=2, offset=314, scroll=.45, quote="Angles")
    add_recording_link(str(tmp_path), "A", source, 8, start=12, label="Proof")
    row = list_recording_links(str(tmp_path), "A", source=source)[0]
    assert row["source"] == source
    assert list_recording_links(str(tmp_path), "A", source={**source, "section": 3}) == []


def test_recording_links_have_a_per_source_budget(tmp_path):
    root = str(tmp_path)
    for i in range(200):
        add_recording_link(root, "A", PDF, 8, start=i, label=str(i))
    with pytest.raises(ValueError, match="limit"):
        add_recording_link(root, "A", PDF, 8, start=201, label="Too many")
    assert len(list_recording_links(root, "A", source=PDF)) == 200


def test_segment_duration_validation_does_not_silently_change_the_reference():
    assert validate_segment(490, 695, duration=1458) == (490., 695.)
    with pytest.raises(ValueError):
        validate_segment(490, 695, duration=600)
    with pytest.raises(ValueError):
        validate_segment(600, None, duration=600)


def test_recording_link_migration_rolls_back_table_indexes_and_ledger():
    previous = tuple(m for m in db._SCHEMA_MIGRATIONS if m[0] <= 19)
    with sqlite3.connect(":memory:") as conn:
        initialize_schema(conn, bootstrap=db._create_tables, migrations=previous)
        before = conn.execute("SELECT name,sql FROM sqlite_master ORDER BY name").fetchall()
        def fail(connection):
            db._migration_20_recording_links(connection)
            raise RuntimeError("interrupted")
        with pytest.raises(RuntimeError, match="interrupted"):
            initialize_schema(conn, bootstrap=db._create_tables,
                              migrations=previous + ((20, "recording_links", fail),))
        assert conn.execute("PRAGMA user_version").fetchone() == (19,)
        assert conn.execute("SELECT max(version) FROM schema_migrations").fetchone() == (19,)
        assert conn.execute("SELECT name,sql FROM sqlite_master ORDER BY name").fetchall() == before
