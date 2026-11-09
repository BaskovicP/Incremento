"""PDF and EPUB highlight families (docs/architecture/shared-folder-sync.md §2, §6.1; design PR 8)."""

import json
import sqlite3

import pytest

import sync_records

PDF = sync_records.FAMILIES["pdf_highlight"]
EPUB = sync_records.FAMILIES["epub_highlight"]


@pytest.fixture
def conn():
    import db
    from db_schema import initialize_schema
    connection = sqlite3.connect(":memory:", isolation_level="")
    initialize_schema(connection, bootstrap=db._create_tables, migrations=db._SCHEMA_MIGRATIONS)
    yield connection
    connection.close()


PDF_VALUE = {"page": 3, "color": "yellow", "text": "a passage", "note": "why", "note_html": "",
             "rects": [{"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.04}],
             "annotation": {"kind": "Highlight", "name": "Incremento-doc-abc"}}
EPUB_VALUE = {"section_index": 2, "color": "green", "text": "a passage", "note": "", "note_html": "",
              "start_offset": 10, "end_offset": 19, "style": "underline"}


def test_a_pdf_highlight_round_trips_with_its_geometry_and_annotation(conn):
    PDF.write(conn, "card:7/pdf_highlight:k1", PDF_VALUE)

    assert dict(PDF.scan(conn)) == {"card:7/pdf_highlight:k1": PDF_VALUE}
    assert PDF.read(conn, "card:7/pdf_highlight:k1") == PDF_VALUE
    assert PDF.card_id("card:7/pdf_highlight:k1") == 7


def test_an_epub_highlight_round_trips(conn):
    EPUB.write(conn, "card:7/epub_highlight:e1", EPUB_VALUE)

    assert dict(EPUB.scan(conn)) == {"card:7/epub_highlight:e1": EPUB_VALUE}
    EPUB.delete(conn, "card:7/epub_highlight:e1")
    assert EPUB.read(conn, "card:7/epub_highlight:e1") is None


def test_highlight_ids_with_any_characters_get_unambiguous_keys(conn):
    odd = "conflict-a/b:c%d e"
    with conn:
        conn.execute("INSERT INTO pdf_highlights(id, card_id, page, color, text, note, rects, annotation_json, "
                     "note_html) VALUES (?, 7, 1, 'yellow', '', '', '[]', '{}', '')", (odd,))

    [(key, _)] = list(PDF.scan(conn))

    assert key == "card:7/pdf_highlight:conflict-a%2Fb%3Ac%25d%20e"
    assert PDF.read(conn, key) is not None


def test_geometry_noise_below_the_normalized_precision_is_not_a_change(conn):
    with conn:
        conn.execute("INSERT INTO pdf_highlights(id, card_id, page, color, text, note, rects, annotation_json, "
                     "note_html) VALUES ('k', 7, 1, 'yellow', '', '', ?, '{}', '')",
                     (json.dumps([{"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.04}]),))
    before = dict(PDF.scan(conn))
    with conn:
        conn.execute("UPDATE pdf_highlights SET rects=?",
                     (json.dumps([{"x": 0.1000000001, "y": 0.2, "w": 0.3, "h": 0.04}]),))

    assert dict(PDF.scan(conn)) == before


@pytest.mark.parametrize("change", [
    {"page": 0}, {"color": "chartreuse"}, {"note": " padded "}, {"note_html": "<script>x</script>"},
    {"rects": [{"x": 0, "y": 0, "w": 0, "h": 1}]}, {"rects": [{"x": 0, "y": 0, "w": 1, "h": 1}] * 2001},
    {"annotation": {"kind": "Highlight", "blob": "x" * 70000}}, {"annotation": []}, {"text": "t" * 70000},
], ids=["page-zero", "unknown-color", "unnormalized-note", "unsafe-html", "empty-rect", "too-many-rects",
        "huge-annotation", "annotation-not-object", "huge-text"])
def test_incoming_pdf_highlights_must_be_ones_the_reader_could_have_saved(change):
    with pytest.raises(ValueError):
        PDF.validate("card:7/pdf_highlight:k1", {**PDF_VALUE, **change})


@pytest.mark.parametrize("change", [
    {"section_index": -1}, {"style": "wavy"}, {"color": "snapshot"}, {"start_offset": 20, "end_offset": 19},
], ids=["negative-section", "unknown-style", "snapshot-color", "reversed-range"])
def test_incoming_epub_highlights_must_be_ones_the_reader_could_have_saved(change):
    with pytest.raises(ValueError):
        EPUB.validate("card:7/epub_highlight:e1", {**EPUB_VALUE, **change})


@pytest.mark.parametrize("key", ["card:7/pdf_highlight:", "card:7/pdf_highlight:a/b", "card:7/epub_highlight:x",
                                 "card:7/pdf_highlight:" + "x" * 513])
def test_pdf_highlight_keys_name_one_card_and_one_encoded_id(key):
    with pytest.raises(ValueError):
        PDF.validate(key, None)
