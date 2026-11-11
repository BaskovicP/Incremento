"""AnkiWeb coordination contract (docs/architecture/shared-folder-sync.md §7; scenarios 10-11).

Anki's sync (rslib/src/sync/collection): a locally changed card has usn -1;
uploading gives it the server usn of that sync, and afterwards the
collection's own usn is that server usn + 1. So a device whose collection usn
is greater than a card's upload usn has already downloaded it, unless the
card was deleted.
"""

import itertools
import json
import sqlite3

import pytest

import sync_anki
import sync_apply
import sync_capture
import sync_exchange
import sync_records
from sync_records import CardRef


# --- Reading card references from a collection --------------------------------

def _collection(cards, *, usn=20):
    col = sqlite3.connect(":memory:")
    col.execute("CREATE TABLE col (usn INTEGER, scm INTEGER, mod INTEGER DEFAULT 1)")
    col.execute("INSERT INTO col(usn, scm) VALUES (?, 1000)", (usn,))
    col.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, guid TEXT)")
    col.execute("CREATE TABLE cards (id INTEGER PRIMARY KEY, nid INTEGER, usn INTEGER)")
    for card_id, note_id, guid, card_usn in cards:
        col.execute("INSERT OR IGNORE INTO notes VALUES (?, ?)", (note_id, guid))
        col.execute("INSERT INTO cards VALUES (?, ?, ?)", (card_id, note_id, card_usn))
    return lambda sql, *args: col.execute(sql, args).fetchall()


def test_card_refs_name_the_note_guid_and_upload_state_of_present_cards_only():
    query = _collection([(7, 70, "g7", 12), (8, 80, "g8", -1)])

    refs = sync_anki.card_refs(query, [7, 8, 9])

    assert refs == {7: CardRef(7, 70, "g7", uploaded_usn=12, collection_usn=20, collection_scm=1000),
                    8: CardRef(8, 80, "g8", uploaded_usn=None, collection_usn=20, collection_scm=1000)}


def test_card_refs_look_up_large_batches_in_bounded_chunks():
    query_log = []
    base = _collection([(card_id, card_id * 10, f"g{card_id}", 1) for card_id in range(1, 2001)])

    def query(sql, *args):
        query_log.append(len(args))
        return base(sql, *args)

    refs = sync_anki.card_refs(query, range(1, 2001))

    assert len(refs) == 2000
    assert max(query_log) <= sync_anki.MAX_SQL_VARIABLES


def test_collection_usn_reads_the_usn_anki_recorded_at_its_last_sync():
    assert sync_anki.collection_usn(_collection([], usn=57)) == 57


# --- Late or deleted -------------------------------------------------------------

class FakeAnki:
    def __init__(self, cards=(), *, usn, scm=111):
        self.cards = {card.card_id: card for card in cards}
        self.usn = usn
        self.scm = scm

    def __call__(self, card_ids):
        return {i: self.cards[i] for i in card_ids if i in self.cards}


class Device:
    def __init__(self, tmp_path, name, folder, anki, *, library_id=None):
        import db
        from db_schema import initialize_schema
        self.conn = sqlite3.connect(tmp_path / f"{name}.db", isolation_level="")
        initialize_schema(self.conn, bootstrap=db._create_tables, migrations=db._SCHEMA_MIGRATIONS)
        counter = itertools.count(1)
        sync_capture.enable_sync(self.conn, make_id=lambda: f"{name}-{next(counter)}", library_id=library_id)
        self.folder, self.anki = folder, anki

    def push(self):
        sync_capture.capture(self.conn, sync_records.FAMILIES, self.anki, now=lambda: 1000)
        sync_exchange.publish(self.conn, self.folder, anki_usn=self.anki.usn, anki_scm=self.anki.scm, now=lambda: 2000)

    def pull(self):
        sync_exchange.receive(self.conn, self.folder, sync_records.FAMILIES, now=lambda: 3000)
        return sync_apply.apply(self.conn, sync_records.FAMILIES, self.anki, collection_usn=self.anki.usn,
                                collection_scm=self.anki.scm, now=lambda: 4000)

    def statuses(self):
        return [row[0] for row in self.conn.execute("SELECT status FROM sync_inbox")]


@pytest.fixture
def folder(tmp_path):
    path = tmp_path / "Cloud"
    path.mkdir()
    return path


def _pair(tmp_path, folder, sender_cards, sender_usn, receiver_usn):
    a = Device(tmp_path, "a", folder, FakeAnki(sender_cards, usn=sender_usn))
    b = Device(tmp_path, "b", folder, FakeAnki((), usn=receiver_usn), library_id=sync_capture.sync_identity(
        a.conn).library_id)
    with a.conn:
        a.conn.execute("INSERT INTO priorities(card_id, priority) VALUES (7, 40)")
    return a, b


UPLOADED = CardRef(7, 70, "g7", uploaded_usn=12, collection_usn=15, collection_scm=111)
NOT_UPLOADED = CardRef(7, 70, "g7", uploaded_usn=None, collection_usn=30, collection_scm=111)


def test_publishing_announces_the_collection_usn_and_receiving_remembers_it(tmp_path, folder):
    a, b = _pair(tmp_path, folder, [UPLOADED], 15, 20)
    a.push()

    b.pull()

    device = json.loads((sync_exchange.library_dir(folder, sync_capture.sync_identity(a.conn).library_id)
                         / "devices" / "a-2" / "device.json").read_text("utf-8"))
    assert device["anki_usn"] == 15
    assert b.conn.execute("SELECT device, anki_usn FROM sync_peers").fetchall() == [("a-2", 15)]


def test_a_card_uploaded_before_the_receivers_last_sync_but_absent_was_deleted(tmp_path, folder):
    a, b = _pair(tmp_path, folder, [UPLOADED], 15, 20)
    a.push()

    result = b.pull()

    assert b.statuses() == ["obsolete"]
    assert result.obsolete == 1 and result.pending_anki == 0
    assert b.conn.execute("SELECT count(*) FROM priorities").fetchone() == (0,)
    assert b.conn.execute("SELECT max_seq FROM sync_receipts").fetchone() == (1,)


def test_a_card_uploaded_after_the_receivers_last_sync_is_still_on_its_way(tmp_path, folder):
    a, b = _pair(tmp_path, folder, [UPLOADED], 15, 12)
    a.push()

    b.pull()

    assert b.statuses() == ["pending_anki"]


def test_a_card_not_yet_uploaded_waits_until_the_sender_has_synced(tmp_path, folder):
    a, b = _pair(tmp_path, folder, [NOT_UPLOADED], 30, 50)
    a.push()

    b.pull()
    assert b.statuses() == ["pending_anki"], "the sender has not synced since capturing"

    a.anki.usn = 41  # the sender's AnkiWeb sync uploaded the card at server usn 40
    a.push()
    b.pull()

    assert b.statuses() == ["obsolete"]


def test_a_receiver_that_has_not_synced_past_the_senders_upload_keeps_waiting(tmp_path, folder):
    a, b = _pair(tmp_path, folder, [NOT_UPLOADED], 30, 35)
    a.anki.usn = 41
    a.push()

    b.pull()

    assert b.statuses() == ["pending_anki"]


def test_without_a_known_collection_usn_nothing_is_declared_deleted(tmp_path, folder):
    a, b = _pair(tmp_path, folder, [UPLOADED], 15, 20)
    a.push()
    sync_exchange.receive(b.conn, folder, sync_records.FAMILIES, now=lambda: 3000)

    sync_apply.apply(b.conn, sync_records.FAMILIES, b.anki, now=lambda: 4000)

    assert b.statuses() == ["pending_anki"]


def test_a_receiver_on_another_collection_schema_never_declares_a_card_deleted(tmp_path, folder):
    """After a schema change or full sync AnkiWeb's numbering may not compare across the two sides."""
    other_schema = CardRef(7, 70, "g7", uploaded_usn=12, collection_usn=15, collection_scm=111)
    a, b = _pair(tmp_path, folder, [other_schema], 15, 20)
    b.anki.scm = 222
    a.push()

    b.pull()

    assert b.statuses() == ["pending_anki"]


def test_card_refs_record_the_collection_schema_time():
    query = _collection([(7, 70, "g7", 12)])

    assert sync_anki.card_refs(query, [7])[7].collection_scm == 1000
