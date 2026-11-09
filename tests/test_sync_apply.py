"""Apply contract (docs/architecture/shared-folder-sync.md §5, §6 step 5; scenarios 4, 5, 7, 8).

Two disposable profile databases stand for two devices sharing one folder.
"""

import itertools
import json
import sqlite3

import pytest

import sync_apply
import sync_capture
import sync_exchange
import sync_records
from sync_records import CardRef


CARD_7 = CardRef(card_id=7, note_id=70, guid="guid-7", uploaded_usn=12)
CARD_8 = CardRef(card_id=8, note_id=80, guid="guid-8", uploaded_usn=13)


class FakeAnki:
    def __init__(self, *cards):
        self.cards = {card.card_id: card for card in cards}

    def __call__(self, card_ids):
        return {card_id: self.cards[card_id] for card_id in card_ids if card_id in self.cards}


class Device:
    def __init__(self, tmp_path, name, folder, *, library_id=None, anki=None):
        import db
        from db_schema import initialize_schema
        self.conn = sqlite3.connect(tmp_path / f"{name}.db", isolation_level="")
        initialize_schema(self.conn, bootstrap=db._create_tables, migrations=db._SCHEMA_MIGRATIONS)
        counter = itertools.count(1)
        sync_capture.enable_sync(self.conn, make_id=lambda: f"{name}-{next(counter)}", library_id=library_id)
        self.folder = folder
        self.anki = anki or FakeAnki(CARD_7, CARD_8)

    @property
    def library_id(self):
        return sync_capture.sync_identity(self.conn).library_id

    def set(self, card_id, value):
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO priorities(card_id, priority) VALUES (?, ?)",
                              (card_id, value))

    def delete(self, card_id):
        with self.conn:
            self.conn.execute("DELETE FROM priorities WHERE card_id=?", (card_id,))

    def priority(self, card_id):
        row = self.conn.execute("SELECT priority FROM priorities WHERE card_id=?", (card_id,)).fetchone()
        return None if row is None else row[0]

    def push(self):
        sync_capture.capture(self.conn, sync_records.FAMILIES, self.anki, now=lambda: 1000)
        sync_exchange.publish(self.conn, self.folder, now=lambda: 2000)

    def pull(self):
        sync_exchange.receive(self.conn, self.folder, sync_records.FAMILIES, now=lambda: 3000)
        return sync_apply.apply(self.conn, sync_records.FAMILIES, self.anki, now=lambda: 4000)

    def sync(self):
        self.push()
        result = self.pull()
        self.push()
        return result

    def baseline(self, card_id):
        row = self.conn.execute("SELECT revision_id FROM sync_baseline WHERE key=?",
                                (f"card:{card_id}",)).fetchone()
        return None if row is None else row[0]

    def inbox(self):
        return dict(self.conn.execute("SELECT revision_id, status FROM sync_inbox").fetchall())

    def open_conflicts(self):
        return self.conn.execute("SELECT id, key, heads FROM sync_conflicts "
                                 "WHERE resolved_revision IS NULL").fetchall()

    def unpublished(self):
        return self.conn.execute("SELECT count(*) FROM sync_outbox WHERE published_at IS NULL").fetchone()[0]


@pytest.fixture
def folder(tmp_path):
    path = tmp_path / "Cloud"
    path.mkdir()
    return path


@pytest.fixture
def pair(tmp_path, folder):
    a = Device(tmp_path, "a", folder)
    b = Device(tmp_path, "b", folder, library_id=a.library_id)
    yield a, b
    a.conn.close()
    b.conn.close()


# --- Fast-forward ----------------------------------------------------------------

def test_a_received_priority_is_applied_and_is_not_published_back(pair):
    a, b = pair
    a.set(7, 40.0)
    a.push()

    result = b.pull()

    assert b.priority(7) == 40.0
    assert result.applied == 1
    assert set(b.inbox().values()) == {"applied"}
    assert b.baseline(7) == a.baseline(7)
    b.push()
    assert b.conn.execute("SELECT count(*) FROM sync_revisions WHERE device LIKE 'b-%'").fetchone() == (0,)


def test_offline_edits_to_different_cards_on_both_devices_are_both_kept(pair):
    a, b = pair
    a.set(7, 40.0)
    b.set(8, 60.0)

    a.sync()
    b.sync()
    a.sync()

    assert (a.priority(7), a.priority(8)) == (40.0, 60.0)
    assert (b.priority(7), b.priority(8)) == (40.0, 60.0)


def test_a_received_tombstone_deletes_the_priority(pair):
    a, b = pair
    a.set(7, 40.0)
    a.push()
    b.pull()
    a.delete(7)
    a.push()

    b.pull()

    assert b.priority(7) is None
    assert b.baseline(7) == a.baseline(7)


def test_a_revision_already_included_in_the_local_history_changes_nothing(pair):
    a, b = pair
    a.set(7, 40.0)
    a.push()
    b.pull()
    first = b.baseline(7)
    b.set(7, 30.0)
    b.push()
    with b.conn:
        b.conn.execute("UPDATE sync_inbox SET status='received' WHERE revision_id=?", (first,))

    result = b.pull()

    assert b.priority(7) == 30.0
    assert result.ignored == 1
    assert b.inbox()[first] == "applied"


# --- Concurrent edits ----------------------------------------------------------------

def test_different_concurrent_values_become_a_conflict_that_keeps_the_local_value(pair):
    a, b = pair
    a.set(7, 40.0)
    a.sync()
    b.sync()
    a.set(7, 10.0)
    b.set(7, 90.0)
    a.push()

    result = b.sync()

    assert result.conflicts == 1
    assert b.priority(7) == 90.0
    [(conflict_id, key, heads)] = b.open_conflicts()
    assert key == "card:7"
    assert sorted(json.loads(heads)) == sorted([a.baseline(7), b.baseline(7)])


def test_resolving_a_conflict_records_a_merge_both_devices_converge_on(pair):
    a, b = pair
    a.set(7, 40.0)
    a.sync()
    b.sync()
    a.set(7, 10.0)
    b.set(7, 90.0)
    a.push()
    b.sync()
    [(conflict_id, _, heads)] = b.open_conflicts()

    resolution = sync_apply.resolve_conflict(b.conn, conflict_id, {"priority": 10.0}, sync_records.FAMILIES,
                                             b.anki, now=lambda: 5000)
    b.push()
    a.sync()

    assert a.priority(7) == b.priority(7) == 10.0
    assert a.baseline(7) == b.baseline(7) == resolution
    parents = json.loads(b.conn.execute("SELECT parents FROM sync_revisions WHERE id=?", (resolution,)).fetchone()[0])
    assert sorted(parents) == sorted(json.loads(heads))
    assert b.open_conflicts() == [] and a.open_conflicts() == []


def test_equal_concurrent_values_merge_silently_to_the_same_revision_on_both_devices(pair):
    a, b = pair
    a.set(7, 40.0)
    a.sync()
    b.sync()
    a.set(7, 55.0)
    b.set(7, 55.0)

    a.push()
    b.sync()
    a.sync()

    assert a.open_conflicts() == [] and b.open_conflicts() == []
    assert a.baseline(7) == b.baseline(7)
    merge = a.baseline(7)
    assert a.conn.execute("SELECT device FROM sync_revisions WHERE id=?", (merge,)).fetchone() == ("~merge",)
    a.sync()
    b.sync()
    assert a.baseline(7) == b.baseline(7) == merge, "a merge must not cause another round of merges"


def test_a_local_edit_not_yet_captured_is_protected_from_an_incoming_change(pair):
    a, b = pair
    a.set(7, 40.0)
    a.sync()
    b.sync()
    b.set(7, 15.0)  # saved by a feature, not yet scanned by sync
    a.set(7, 60.0)
    a.push()

    b.pull()

    assert b.priority(7) == 15.0
    assert len(b.open_conflicts()) == 1
    assert b.unpublished() == 1, "the protected local edit is queued for publication"


def test_edit_versus_delete_keeps_the_edit_visible(pair):
    a, b = pair
    a.set(7, 40.0)
    a.sync()
    b.sync()
    a.delete(7)
    b.set(7, 70.0)
    a.push()

    b.sync()

    assert b.priority(7) == 70.0
    assert len(b.open_conflicts()) == 1


# --- Failure safety ------------------------------------------------------------------

def test_a_crash_during_apply_leaves_everything_as_it_was_and_the_retry_succeeds(pair, monkeypatch):
    a, b = pair
    a.set(7, 40.0)
    a.push()
    family = sync_records.FAMILIES["priority"]
    original = family.write

    def crash(*args, **kwargs):
        raise RuntimeError("power loss")

    monkeypatch.setattr(family, "write", crash)
    with pytest.raises(RuntimeError, match="power loss"):
        b.pull()

    assert b.priority(7) is None
    assert b.baseline(7) is None
    assert set(b.inbox().values()) == {"received"}
    monkeypatch.setattr(family, "write", original)
    b.pull()
    assert b.priority(7) == 40.0


# --- Anki dependency ------------------------------------------------------------------

def test_a_revision_for_a_card_not_yet_in_the_collection_waits_and_applies_later(tmp_path, folder):
    a = Device(tmp_path, "a", folder)
    b = Device(tmp_path, "b", folder, library_id=a.library_id, anki=FakeAnki(CARD_8))
    a.set(7, 40.0)
    a.push()

    result = b.pull()
    assert (result.pending_anki, b.priority(7)) == (1, None)
    assert set(b.inbox().values()) == {"pending_anki"}

    b.anki.cards[7] = CARD_7  # AnkiWeb delivered the card
    b.pull()

    assert b.priority(7) == 40.0
    a.conn.close()
    b.conn.close()


def test_a_revision_whose_card_belongs_to_another_note_is_rejected(tmp_path, folder):
    a = Device(tmp_path, "a", folder)
    other_collection = CardRef(card_id=7, note_id=70, guid="someone-elses-guid", uploaded_usn=3)
    b = Device(tmp_path, "b", folder, library_id=a.library_id, anki=FakeAnki(other_collection))
    a.set(7, 40.0)
    a.push()

    result = b.pull()

    assert result.rejected == 1
    assert b.priority(7) is None
    assert set(b.inbox().values()) == {"rejected"}
    a.conn.close()
    b.conn.close()


def test_receipts_record_the_highest_contiguous_sequence_applied_from_each_peer(pair):
    a, b = pair
    a.set(7, 40.0)
    a.set(8, 50.0)
    a.push()

    b.pull()

    identity = sync_capture.sync_identity(a.conn)
    assert b.conn.execute("SELECT peer, epoch, max_seq FROM sync_receipts").fetchall() == [
        (identity.device_id, identity.epoch, 2)]
