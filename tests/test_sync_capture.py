"""Capture contract for shared-folder sync (docs/architecture/shared-folder-sync.md §4, §6; scenarios 1-3)."""

import itertools
import json
import sqlite3

import pytest

import db
import sync_capture
import sync_records
from sync_records import CardRef


PROFILE = "TestProfile"


@pytest.fixture
def conn(tmp_path):
    db.close_connection()
    connection = db.get_connection(str(tmp_path), PROFILE)
    yield connection
    db.close_connection()


class FakeAnki:
    """Stand-in for the Anki collection: which cards exist and their sync state."""

    def __init__(self, *cards):
        self.cards = {card.card_id: card for card in cards}

    def __call__(self, card_ids):
        return {card_id: self.cards[card_id] for card_id in card_ids if card_id in self.cards}


def _ids():
    counter = itertools.count(1)
    return lambda: f"id{next(counter):04d}"


def _enable(conn):
    return sync_capture.enable_sync(conn, make_id=_ids())


def _set_priority(conn, card_id, value):
    with conn:
        conn.execute("INSERT OR REPLACE INTO priorities(card_id, priority) VALUES (?, ?)", (card_id, value))


def _revisions(conn):
    rows = conn.execute("SELECT id, family, key, parents, device, epoch, seq, deleted, value, deps "
                        "FROM sync_revisions ORDER BY seq").fetchall()
    return [dict(zip(("id", "family", "key", "parents", "device", "epoch", "seq", "deleted", "value", "deps"), row))
            for row in rows]


def _capture(conn, anki):
    return sync_capture.capture(conn, sync_records.FAMILIES, anki, now=lambda: 1000)


CARD_7 = CardRef(card_id=7, note_id=70, guid="guid-7", uploaded_usn=12)
CARD_8 = CardRef(card_id=8, note_id=80, guid="guid-8", uploaded_usn=None)


def test_enabling_sync_creates_one_library_and_device_identity_and_is_idempotent(conn):
    first = _enable(conn)
    again = sync_capture.enable_sync(conn, make_id=lambda: "never-used")

    assert first == again == sync_capture.SyncIdentity(library_id="id0001", device_id="id0002", epoch=1)
    assert sync_capture.sync_identity(conn) == first


def test_capture_before_enabling_sync_fails_without_writing(conn):
    _set_priority(conn, 7, 40.0)

    with pytest.raises(sync_capture.SyncNotEnabledError):
        _capture(conn, FakeAnki(CARD_7))

    assert conn.execute("SELECT count(*) FROM sync_revisions").fetchone() == (0,)
    assert conn.execute("SELECT count(*) FROM sync_baseline").fetchone() == (0,)


def test_first_capture_records_one_parentless_revision_per_priority_with_outbox_and_baseline(conn):
    _enable(conn)
    _set_priority(conn, 7, 40.0)
    _set_priority(conn, 8, 75.5)

    result = _capture(conn, FakeAnki(CARD_7, CARD_8))

    revisions = _revisions(conn)
    assert [(r["key"], r["parents"], r["deleted"], json.loads(r["value"])) for r in revisions] == [
        ("card:7", "[]", 0, {"priority": 40.0}),
        ("card:8", "[]", 0, {"priority": 75.5}),
    ]
    assert [r["seq"] for r in revisions] == [1, 2]
    assert {r["device"] for r in revisions} == {"id0002"}
    assert json.loads(revisions[0]["deps"]) == {"card": {"card_id": 7, "note_id": 70, "guid": "guid-7",
                                                         "uploaded_usn": 12, "collection_usn": None,
                                                         "collection_scm": None}}
    assert result.captured == 2
    assert conn.execute("SELECT revision_id FROM sync_outbox ORDER BY revision_id").fetchall() == sorted(
        (r["id"],) for r in revisions)
    assert conn.execute("SELECT family, key, revision_id FROM sync_baseline ORDER BY key").fetchall() == [
        ("priority", "card:7", revisions[0]["id"]), ("priority", "card:8", revisions[1]["id"])]


def test_capture_without_changes_records_nothing(conn):
    _enable(conn)
    _set_priority(conn, 7, 40.0)
    _capture(conn, FakeAnki(CARD_7))

    result = _capture(conn, FakeAnki(CARD_7))

    assert result.captured == 0
    assert len(_revisions(conn)) == 1


def test_float_noise_below_the_normalized_precision_records_nothing(conn):
    _enable(conn)
    _set_priority(conn, 7, 40.0)
    _capture(conn, FakeAnki(CARD_7))
    _set_priority(conn, 7, 40.0000000001)

    assert _capture(conn, FakeAnki(CARD_7)).captured == 0


def test_changed_priority_records_a_child_of_the_previous_revision(conn):
    _enable(conn)
    _set_priority(conn, 7, 40.0)
    _capture(conn, FakeAnki(CARD_7))
    first = _revisions(conn)[0]
    _set_priority(conn, 7, 20.0)

    _capture(conn, FakeAnki(CARD_7))

    child = _revisions(conn)[1]
    assert json.loads(child["parents"]) == [first["id"]]
    assert json.loads(child["value"]) == {"priority": 20.0}
    assert conn.execute("SELECT revision_id FROM sync_baseline WHERE key='card:7'").fetchone() == (child["id"],)


def test_deleted_priority_of_a_live_card_records_a_tombstone(conn):
    _enable(conn)
    _set_priority(conn, 7, 40.0)
    _capture(conn, FakeAnki(CARD_7))
    first = _revisions(conn)[0]
    with conn:
        conn.execute("DELETE FROM priorities WHERE card_id=7")

    _capture(conn, FakeAnki(CARD_7))

    tombstone = _revisions(conn)[1]
    assert (tombstone["deleted"], tombstone["value"], json.loads(tombstone["parents"])) == (1, None, [first["id"]])


def test_priority_of_a_card_missing_from_anki_is_neither_captured_nor_tombstoned(conn):
    _enable(conn)
    _set_priority(conn, 7, 40.0)
    _set_priority(conn, 9, 10.0)
    _capture(conn, FakeAnki(CARD_7))
    with conn:
        conn.execute("DELETE FROM priorities WHERE card_id=7")

    result = _capture(conn, FakeAnki())

    assert [r["key"] for r in _revisions(conn)] == ["card:7"]
    assert result.skipped_missing_cards == 2
    assert conn.execute("SELECT key FROM sync_baseline").fetchall() == []


def test_failed_scan_records_nothing_and_infers_no_deletions(conn, monkeypatch):
    _enable(conn)
    _set_priority(conn, 7, 40.0)
    _capture(conn, FakeAnki(CARD_7))
    baseline = conn.execute("SELECT * FROM sync_baseline").fetchall()
    _set_priority(conn, 8, 1.0)  # a change, so the family is scanned (unchanged rows are not rescanned)

    def broken_scan(_conn):
        yield from ()
        raise sync_records.SyncScanError("priorities unreadable")

    monkeypatch.setattr(sync_records.FAMILIES["priority"], "scan", broken_scan)

    with pytest.raises(sync_records.SyncScanError):
        _capture(conn, FakeAnki(CARD_7))

    assert len(_revisions(conn)) == 1
    assert conn.execute("SELECT * FROM sync_baseline").fetchall() == baseline


def test_unreadable_table_is_a_scan_error_not_an_empty_family(conn):
    _enable(conn)
    _set_priority(conn, 7, 40.0)
    _capture(conn, FakeAnki(CARD_7))
    with conn:
        conn.execute("ALTER TABLE priorities RENAME TO priorities_moved")

    with pytest.raises(sync_records.SyncScanError):
        _capture(conn, FakeAnki(CARD_7))

    assert [r["deleted"] for r in _revisions(conn)] == [0]


def test_interrupted_capture_commits_nothing_and_the_next_capture_recovers(conn, monkeypatch):
    _enable(conn)
    _set_priority(conn, 7, 40.0)
    original = sync_capture._enqueue

    def crash(*args, **kwargs):
        raise RuntimeError("power loss")

    monkeypatch.setattr(sync_capture, "_enqueue", crash)
    with pytest.raises(RuntimeError, match="power loss"):
        _capture(conn, FakeAnki(CARD_7))

    for table in ("sync_revisions", "sync_outbox", "sync_baseline"):
        assert conn.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,), table
    monkeypatch.setattr(sync_capture, "_enqueue", original)
    assert _capture(conn, FakeAnki(CARD_7)).captured == 1
    assert conn.execute("SELECT count(*) FROM sync_outbox").fetchone() == (1,)


def test_edit_made_after_the_scan_is_captured_with_its_live_value(conn, monkeypatch):
    _enable(conn)
    _set_priority(conn, 7, 40.0)
    family = sync_records.FAMILIES["priority"]
    original_scan = family.scan

    database_path = conn.execute("PRAGMA database_list").fetchone()[2]

    def scan_then_edit(connection):
        rows = list(original_scan(connection))
        # Another writer saves a newer value after the snapshot was read.
        other = sqlite3.connect(database_path)
        with other:
            other.execute("UPDATE priorities SET priority=15 WHERE card_id=7")
        other.close()
        return rows

    monkeypatch.setattr(family, "scan", scan_then_edit)

    _capture(conn, FakeAnki(CARD_7))

    assert [json.loads(r["value"]) for r in _revisions(conn)] == [{"priority": 15.0}]


def test_revision_ids_are_content_hashes_of_every_identifying_field():
    base = dict(library="lib", family="priority", key="card:7", parents=["p"], device="dev", epoch=1, seq=3,
                deleted=False, value={"priority": 40.0}, deps={"card": None}, format=sync_records.SYNC_FORMAT)

    same = sync_capture.revision_id(**dict(base))
    assert same == sync_capture.revision_id(**dict(base))
    assert len(same) == 64
    for field, other in [("library", "lib2"), ("family", "bookmark"), ("key", "card:8"), ("parents", []),
                         ("device", "dev2"), ("epoch", 2), ("seq", 4), ("value", {"priority": 41.0}),
                         ("deps", {"card": {"card_id": 7}})]:
        assert sync_capture.revision_id(**{**base, field: other}) != same, field


def test_sequence_numbers_continue_after_the_profile_database_is_reopened(conn, tmp_path):
    _enable(conn)
    _set_priority(conn, 7, 40.0)
    _capture(conn, FakeAnki(CARD_7))
    db.close_connection()
    reopened = db.get_connection(str(tmp_path), PROFILE)
    _set_priority(reopened, 8, 10.0)

    _capture(reopened, FakeAnki(CARD_7, CARD_8))

    assert [r["seq"] for r in _revisions(reopened)] == [1, 2]


def test_a_card_not_yet_uploaded_to_ankiweb_is_captured_with_a_null_uploaded_usn(conn):
    _enable(conn)
    _set_priority(conn, 8, 10.0)

    _capture(conn, FakeAnki(CARD_8))

    assert json.loads(_revisions(conn)[0]["deps"])["card"]["uploaded_usn"] is None


def test_a_deleted_priority_is_tombstoned_once_not_on_every_capture(conn):
    _enable(conn)
    _set_priority(conn, 7, 40.0)
    _capture(conn, FakeAnki(CARD_7))
    with conn:
        conn.execute("DELETE FROM priorities WHERE card_id=7")
    _capture(conn, FakeAnki(CARD_7))

    again = _capture(conn, FakeAnki(CARD_7))

    assert again.captured == 0
    assert [r["deleted"] for r in _revisions(conn)] == [0, 1]


# --- Skipping families whose rows have not changed ---------------------------------

def _count_scans(monkeypatch, family_name):
    family = sync_records.FAMILIES[family_name]
    calls = []
    original = family.scan
    monkeypatch.setattr(family, "scan", lambda connection: calls.append(1) or original(connection))
    return calls


def test_a_family_whose_rows_have_not_changed_is_not_rescanned(conn, monkeypatch):
    _enable(conn)
    _set_priority(conn, 7, 40.0)
    _capture(conn, FakeAnki(CARD_7))
    scans = _count_scans(monkeypatch, "priority")

    result = _capture(conn, FakeAnki(CARD_7))

    assert result.captured == 0
    assert scans == []


def test_a_changed_row_makes_the_family_scan_again(conn, monkeypatch):
    _enable(conn)
    _set_priority(conn, 7, 40.0)
    _capture(conn, FakeAnki(CARD_7))
    _set_priority(conn, 7, 41.0)

    assert _capture(conn, FakeAnki(CARD_7)).captured == 1


def test_a_record_waiting_for_its_card_is_captured_when_the_card_arrives_without_any_row_change(conn):
    _enable(conn)
    _set_priority(conn, 7, 40.0)
    _set_priority(conn, 8, 50.0)
    assert _capture(conn, FakeAnki(CARD_7)).skipped_missing_cards == 1

    result = _capture(conn, FakeAnki(CARD_7, CARD_8))

    assert result.captured == 1
    assert [r["key"] for r in _revisions(conn)] == ["card:7", "card:8"]


def test_rows_waiting_for_cards_are_not_rescanned_while_the_collection_is_unchanged(conn, monkeypatch):
    _enable(conn)
    _set_priority(conn, 7, 40.0)
    _set_priority(conn, 8, 50.0)  # its card is not in the collection
    sync_capture.capture(conn, sync_records.FAMILIES, FakeAnki(CARD_7), now=lambda: 1, collection_state="mod-1")
    scans = _count_scans(monkeypatch, "priority")

    sync_capture.capture(conn, sync_records.FAMILIES, FakeAnki(CARD_7), now=lambda: 2, collection_state="mod-1")
    assert scans == []

    result = sync_capture.capture(conn, sync_records.FAMILIES, FakeAnki(CARD_7, CARD_8), now=lambda: 3,
                                  collection_state="mod-2")
    assert scans == [1] and result.captured == 1
