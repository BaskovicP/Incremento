import db
import search_repository

import pytest


def test_search_excerpt_rows_is_ranked_and_bounded(tmp_path):
    addon_dir = str(tmp_path)
    conn = db.get_connection(addon_dir, "Profile")
    conn.executemany(
        "INSERT INTO pdf_highlights(id, card_id, page, text) VALUES (?, ?, ?, ?)",
        [
            ("a", 1, 1, "prefix searchable material"),
            ("b", 2, 2, "searchable"),
            ("c", 3, 3, "unrelated"),
        ],
    )
    conn.commit()

    rows = search_repository.search_excerpt_rows(
        addon_dir, "Profile", "pdf_highlights", "search", limit=1
    )

    assert rows == [(2, 2, "searchable")]


def test_document_preview_read_model(tmp_path):
    addon_dir = str(tmp_path)
    db.replace_pdf_text_index(addon_dir, "Profile", 7, ["one", "two"])
    db.replace_epub_text_index(
        addon_dir,
        "Profile",
        8,
        [("Start", "body")],
    )

    assert 7 in search_repository.pdf_candidate_card_ids(addon_dir, "Profile")
    assert search_repository.pdf_page_text(addon_dir, "Profile", 7, 2) == "two"
    assert search_repository.epub_section_text(addon_dir, "Profile", 8, 0) == (
        "Start",
        "body",
    )


@pytest.mark.parametrize(
    ("insert_sql", "values", "kind", "expected"),
    [
        (
            "INSERT INTO pdf_card_sources(pdf_card_id, page, note_id, excerpt) "
            "VALUES (?, ?, ?, ?)",
            (7, 9, 101, "faithful PDF source"),
            "pdf_sources",
            (7, 9, "faithful PDF source", 101),
        ),
        (
            "INSERT INTO epub_card_sources(epub_card_id, section_index, note_id, excerpt) "
            "VALUES (?, ?, ?, ?)",
            (8, 2, 202, "faithful EPUB source"),
            "epub_sources",
            (8, 2, "faithful EPUB source", 202),
        ),
    ],
)
def test_source_search_rows_include_source_note_identity(
    tmp_path,
    insert_sql,
    values,
    kind,
    expected,
):
    addon_dir = str(tmp_path)
    conn = db.get_connection(addon_dir, "Profile")
    conn.execute(insert_sql, values)
    conn.commit()

    rows = search_repository.search_excerpt_rows(
        addon_dir,
        "Profile",
        kind,
        "faith",
    )

    assert rows == [expected]
