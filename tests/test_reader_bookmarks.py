import pytest

import reader_bookmarks
import pdf_manager
import epub_manager
import video_manager
import web_manager


def test_pdf_bookmark_round_trips_and_sorts_by_page(tmp_path):
    addon_dir = str(tmp_path)
    second = reader_bookmarks.add_reader_bookmark(
        addon_dir, "TestProfile", 10, "pdf", {"page": 12}
    )
    first = reader_bookmarks.add_reader_bookmark(
        addon_dir, "TestProfile", 10, "pdf", {"page": 3}
    )

    rows = reader_bookmarks.list_reader_bookmarks(addon_dir, "TestProfile", 10, "pdf")

    assert [row["id"] for row in rows] == [first["id"], second["id"]]
    assert rows[0]["label"] == "Page 3"
    assert rows[1]["location"] == {"page": 12}


def test_bookmarks_are_profile_and_card_isolated(tmp_path):
    addon_dir = str(tmp_path)
    reader_bookmarks.add_reader_bookmark(addon_dir, "TestProfile", 10, "pdf", {"page": 1})
    reader_bookmarks.add_reader_bookmark(addon_dir, "OtherProfile", 10, "pdf", {"page": 2})
    reader_bookmarks.add_reader_bookmark(addon_dir, "TestProfile", 11, "pdf", {"page": 3})

    rows = reader_bookmarks.list_reader_bookmarks(addon_dir, "TestProfile", 10, "pdf")

    assert len(rows) == 1
    assert rows[0]["location"] == {"page": 1}


def test_delete_reader_bookmark_only_removes_matching_reader(tmp_path):
    addon_dir = str(tmp_path)
    pdf = reader_bookmarks.add_reader_bookmark(addon_dir, "TestProfile", 10, "pdf", {"page": 1})
    web = reader_bookmarks.add_reader_bookmark(
        addon_dir, "TestProfile", 10, "web", {"url": "https://example.com"}
    )

    assert reader_bookmarks.delete_reader_bookmark(
        addon_dir, "TestProfile", 10, "pdf", pdf["id"]
    )

    assert reader_bookmarks.list_reader_bookmarks(addon_dir, "TestProfile", 10, "pdf") == []
    assert reader_bookmarks.list_reader_bookmarks(addon_dir, "TestProfile", 10, "web")[0]["id"] == web["id"]


def test_duplicate_pdf_page_bookmark_returns_existing_row(tmp_path):
    addon_dir = str(tmp_path)
    first = reader_bookmarks.add_reader_bookmark(
        addon_dir, "TestProfile", 10, "pdf", {"page": 7}
    )
    second = reader_bookmarks.add_reader_bookmark(
        addon_dir, "TestProfile", 10, "pdf", {"page": 7}
    )

    rows = reader_bookmarks.list_reader_bookmarks(addon_dir, "TestProfile", 10, "pdf")

    assert second == first
    assert len(rows) == 1
    assert rows[0]["location"] == {"page": 7}


def test_location_normalization_for_all_reader_types(tmp_path):
    addon_dir = str(tmp_path)

    pdf = reader_bookmarks.add_reader_bookmark(addon_dir, "TestProfile", 1, "pdf", {"page": -5})
    epub = reader_bookmarks.add_reader_bookmark(
        addon_dir,
        "TestProfile",
        1,
        "epub",
        {"section_index": -2, "scroll_ratio": 2.5, "section_title": "Intro"},
    )
    web = reader_bookmarks.add_reader_bookmark(
        addon_dir,
        "TestProfile",
        1,
        "web",
        {"url": "https://example.com/a", "scroll_ratio": -1, "bookmark_payload": {"path": [1]}},
    )
    writing = reader_bookmarks.add_reader_bookmark(
        addon_dir,
        "TestProfile",
        1,
        "writing",
        {"cursor_position": -4, "block_number": -9, "scroll_ratio": 0.5},
    )
    video = reader_bookmarks.add_reader_bookmark(
        addon_dir, "TestProfile", 1, "video", {"seconds": 12.34}
    )

    assert pdf["location"] == {"page": 1}
    assert epub["location"]["section_index"] == 0
    assert epub["location"]["scroll_ratio"] == pytest.approx(1.0)
    assert web["location"]["scroll_ratio"] == pytest.approx(0.0)
    assert web["location"]["bookmark_payload"] == {"path": [1]}
    assert writing["location"] == {"cursor_position": 0, "block_number": 0, "scroll_ratio": 0.5}
    assert video["location"] == {"seconds": 12.3}
    assert video["comment_text"] == ""


def test_video_bookmark_comments_round_trip_and_clear(tmp_path):
    addon_dir = str(tmp_path)

    saved = reader_bookmarks.add_reader_bookmark(
        addon_dir, "TestProfile", 10, "video", {"seconds": 65.4}
    )
    updated = reader_bookmarks.update_reader_bookmark_comment(
        addon_dir, "TestProfile", 10, "video", saved["id"], "Important explanation"
    )

    assert updated is not None
    assert updated["comment_text"] == "Important explanation"

    rows = reader_bookmarks.list_reader_bookmarks(addon_dir, "TestProfile", 10, "video")
    assert rows == [
        {
            **saved,
            "comment_text": "Important explanation",
            "updated_at": updated["updated_at"],
        }
    ]

    cleared = reader_bookmarks.update_reader_bookmark_comment(
        addon_dir, "TestProfile", 10, "video", saved["id"], "   "
    )
    assert cleared is not None
    assert cleared["comment_text"] == ""
    assert reader_bookmarks.list_reader_bookmarks(addon_dir, "TestProfile", 10, "video")[0]["comment_text"] == ""


def test_duplicate_video_bookmark_returns_existing_row_with_comment(tmp_path):
    addon_dir = str(tmp_path)
    first = reader_bookmarks.add_reader_bookmark(
        addon_dir, "TestProfile", 10, "video", {"seconds": 90.0}
    )
    reader_bookmarks.update_reader_bookmark_comment(
        addon_dir, "TestProfile", 10, "video", first["id"], "Keep this moment"
    )

    second = reader_bookmarks.add_reader_bookmark(
        addon_dir, "TestProfile", 10, "video", {"seconds": 90.0}
    )
    rows = reader_bookmarks.list_reader_bookmarks(addon_dir, "TestProfile", 10, "video")

    assert second["id"] == first["id"]
    assert second["comment_text"] == "Keep this moment"
    assert len(rows) == 1
    assert rows[0]["comment_text"] == "Keep this moment"


def test_progress_updates_do_not_mutate_reader_bookmarks(tmp_path):
    addon_dir = str(tmp_path)
    saved = reader_bookmarks.add_reader_bookmark(
        addon_dir, "TestProfile", 10, "pdf", {"page": 7}
    )
    updated = reader_bookmarks.update_reader_bookmark_comment(
        addon_dir, "TestProfile", 10, "pdf", saved["id"], "Pinned page"
    )
    assert updated is not None

    pdf_manager.set_page(addon_dir, "TestProfile", 10, 42)
    epub_manager.set_epub_progress(
        addon_dir, "TestProfile", 10, section_index=4, scroll_ratio=0.8
    )
    video_manager.set_video_position(addon_dir, "TestProfile", 10, 90.0)
    web_manager.set_web_scroll_position(addon_dir, "TestProfile", 10, "https://example.com", 0.9)

    rows = reader_bookmarks.list_reader_bookmarks(addon_dir, "TestProfile", 10, "pdf")

    assert rows == [
        {
            **updated,
            "location": {"page": 7},
        }
    ]
