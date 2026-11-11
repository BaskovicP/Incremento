"""Links between documents (docs: PDF page links, passage links, EPUB connections): one record per link.

A link is identified by its two ends, not by the local row id, so two computers that made or received the same link
agree on it. The record carries the quote, the passages and the connection note; a note edited on one computer reaches
the other, and a link removed on one is removed on the other.
"""

import itertools
import json
import sqlite3

import pytest

import sync_apply
import sync_capture
import sync_exchange
import sync_links
import sync_paths
import sync_records
from sync_records import CardRef

CARDS = {card_id: CardRef(card_id=card_id, note_id=card_id * 10, guid=f"guid-{card_id}", uploaded_usn=12) for card_id in (7, 8, 9)}
PASSAGE = json.dumps({"quote": "the exact explanation", "rects": [[0.1, 0.2, 0.3, 0.05]]}, separators=(",", ":"))
EPUB_PASSAGE = json.dumps({"quote": "Incremental reading", "start": 0, "end": 19}, separators=(",", ":"))


def _anki(card_ids):
    return {card_id: CARDS[card_id] for card_id in card_ids if card_id in CARDS}


class Device:
    def __init__(self, tmp_path, name, folder, *, library_id=None):
        import db
        from db_schema import initialize_schema

        self.addon = tmp_path / name
        self.conn = sqlite3.connect(tmp_path / f"{name}.db", isolation_level="")
        initialize_schema(self.conn, bootstrap=db._create_tables, migrations=db._SCHEMA_MIGRATIONS)
        counter = itertools.count(1)
        sync_capture.enable_sync(self.conn, make_id=lambda: f"{name}-{next(counter)}", library_id=library_id)
        self.folder = folder
        self.families = {**sync_records.FAMILIES, **sync_links.LINK_FAMILIES}
        self.store = sync_paths.get_sync_blob_dir(str(self.addon), "Profile")

    def pdf_link(self, source=7, target=8, page=1, target_page=2, note="", passage=PASSAGE, quote="where it is asked"):
        with self.conn:
            self.conn.execute(
                "INSERT INTO document_links(source_card_id, source_content_id, source_kind, source_page, quote, target_card_id, "
                "target_content_id, target_page, target_scroll, source_y, target_y, connection_note, source_passage, target_passage) "
                "VALUES (?, NULL, 'pdf', ?, ?, ?, NULL, ?, 0.25, 0.1, 0.4, ?, '{}', ?)",
                (source, page, quote, target, target_page, note, passage))

    def epub_link(self, source=7, target=8, section=0, target_section=1, quote="Spaced repetition"):
        with self.conn:
            self.conn.execute(
                "INSERT INTO epub_connections(source_card_id, source_content_id, source_section, source_offset, source_scroll, "
                "target_card_id, target_content_id, target_section, target_offset, target_scroll, quote, source_passage, target_passage) "
                "VALUES (?, NULL, ?, 3, 0.1, ?, NULL, ?, 5, 0.5, ?, '{}', ?)",
                (source, section, target, target_section, quote, EPUB_PASSAGE))

    def rows(self, table="document_links"):
        return self.conn.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()

    def push(self):
        sync_capture.capture(self.conn, self.families, _anki, now=lambda: 1)
        return sync_exchange.publish(self.conn, self.folder, blob_store=self.store, now=lambda: 2)

    def pull(self):
        sync_exchange.receive(self.conn, self.folder, self.families, blob_store=self.store, now=lambda: 3)
        return sync_apply.apply(self.conn, self.families, _anki, blob_store=self.store, now=lambda: 4)


@pytest.fixture
def folder(tmp_path):
    path = tmp_path / "Cloud"
    path.mkdir()
    return path


@pytest.fixture
def pair(tmp_path, folder):
    one = Device(tmp_path, "one", folder)
    two = Device(tmp_path, "two", folder, library_id=sync_capture.sync_identity(one.conn).library_id)
    yield one, two
    one.conn.close()
    two.conn.close()


def _columns(device, table):
    return [{k: v for k, v in zip([c[1] for c in device.conn.execute(f"PRAGMA table_info({table})")], row) if k != "id"}
            for row in device.rows(table)]


def test_a_pdf_link_reaches_the_other_device_with_its_passages_and_positions(pair):
    one, two = pair
    one.pdf_link(note="see this")

    one.push()
    two.pull()

    assert _columns(two, "document_links") == _columns(one, "document_links")
    assert json.loads(two.rows()[0][-1]) == json.loads(PASSAGE)


def test_an_epub_connection_reaches_the_other_device(pair):
    one, two = pair
    one.epub_link()

    one.push()
    two.pull()

    assert _columns(two, "epub_connections") == _columns(one, "epub_connections")


def test_the_same_link_made_on_both_devices_is_one_link(pair):
    one, two = pair
    one.pdf_link()
    two.pdf_link()

    one.push()
    two.pull()
    two.push()
    one.pull()

    assert len(one.rows()) == len(two.rows()) == 1


def test_the_two_devices_row_ids_may_differ(pair):
    one, two = pair
    two.pdf_link(source=9, target=8, page=3)  # takes row id 1 on device two
    one.pdf_link()  # row id 1 on device one, a different link

    one.push()
    two.pull()

    assert sorted((row[1], row[4]) for row in two.rows()) == [(7, 1), (9, 3)]


def test_an_edited_connection_note_reaches_the_other_device_as_the_same_link(pair):
    one, two = pair
    one.pdf_link()
    one.push()
    two.pull()

    with one.conn:
        one.conn.execute("UPDATE document_links SET connection_note='remember this'")
    one.push()
    two.pull()

    assert len(two.rows()) == 1
    assert two.conn.execute("SELECT connection_note FROM document_links").fetchone()[0] == "remember this"


def test_a_removed_link_is_removed_on_the_other_device(pair):
    one, two = pair
    one.pdf_link()
    one.epub_link()
    one.push()
    two.pull()

    with one.conn:
        one.conn.execute("DELETE FROM document_links")
        one.conn.execute("DELETE FROM epub_connections")
    one.push()
    two.pull()

    assert two.rows() == [] and two.rows("epub_connections") == []


def test_a_link_to_a_card_not_yet_here_waits_for_its_source_card(pair):
    one, two = pair
    one.pdf_link(source=9)
    CARDS_BACKUP = dict(CARDS)
    try:
        del CARDS[9]
        one.push()
        two.pull()
        assert two.rows() == []
    finally:
        CARDS.update(CARDS_BACKUP)


@pytest.mark.parametrize("bad", [
    {"source_page": -1}, {"target_page": 0}, {"target_scroll": 2}, {"source_kind": "movie"},
    {"quote": "x" * 2001}, {"connection_note": "x" * 2001}, {"source_passage": "not json"},
    {"target_passage": json.dumps({"evil": 1})}, {"target_card_id": 0}, {"extra": 1},
])
def test_a_malformed_pdf_link_record_is_refused(pair, bad):
    one, _ = pair
    one.pdf_link()
    ((key, value),) = list(one.families["document_link"].scan(one.conn))
    value = {**value, **bad}

    with pytest.raises(ValueError):
        one.families["document_link"].validate(key, value)


def test_a_key_that_is_not_a_links_is_refused(pair):
    one, _ = pair

    for key in ("card:7/document_link:zz", "card:7/document_link:" + "a" * 31, "card:7/epub_connection:" + "g" * 32):
        with pytest.raises(ValueError):
            one.families["document_link"].card_id(key) if "epub" not in key else one.families["epub_connection"].card_id(key)


def test_the_key_names_the_source_card_and_ignores_the_note_and_row_id(pair):
    one, two = pair
    one.pdf_link(note="a note")
    two.pdf_link(note="another note")

    [(first, _)] = list(one.families["document_link"].scan(one.conn))
    [(second, _)] = list(two.families["document_link"].scan(two.conn))

    assert first == second and first.startswith("card:7/document_link:")
