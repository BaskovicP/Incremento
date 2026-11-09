"""The sync service the desktop calls (docs/architecture/shared-folder-sync.md §7 step 5, §8; requirement 10)."""

import sqlite3
import threading

import pytest

import db
import sync_service


def _collection(cards, usn=20):
    col = sqlite3.connect(":memory:", check_same_thread=False)
    col.execute("CREATE TABLE col (usn INTEGER, scm INTEGER, mod INTEGER DEFAULT 1)")
    col.execute("INSERT INTO col(usn, scm) VALUES (?, 1000)", (usn,))
    col.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, guid TEXT)")
    col.execute("CREATE TABLE cards (id INTEGER PRIMARY KEY, nid INTEGER, usn INTEGER)")
    for card_id in cards:
        col.execute("INSERT INTO notes VALUES (?, ?)", (card_id * 10, f"g{card_id}"))
        col.execute("INSERT INTO cards VALUES (?, ?, 5)", (card_id, card_id * 10))
    return lambda sql, *args: col.execute(sql, args).fetchall()


@pytest.fixture
def folder(tmp_path):
    path = tmp_path / "Cloud"
    path.mkdir()
    return path


@pytest.fixture(autouse=True)
def _connections():
    db.close_connection()
    yield
    db.close_connection()


def _set_priority(addon, card_id, value):
    with db.get_connection(addon, "P") as conn:
        conn.execute("INSERT OR REPLACE INTO priorities(card_id, priority) VALUES (?, ?)", (card_id, value))


def _priority(addon, card_id):
    row = db.get_connection(addon, "P").execute("SELECT priority FROM priorities WHERE card_id=?",
                                                (card_id,)).fetchone()
    return None if row is None else row[0]


def test_the_first_device_creates_a_library_and_the_second_joins_it(tmp_path, folder):
    first = sync_service.configure(str(tmp_path / "a"), "P", str(folder))
    second = sync_service.configure(str(tmp_path / "b"), "P", str(folder))

    assert first.created and not second.created
    assert first.library_id == second.library_id
    assert first.device_id != second.device_id


def test_a_folder_holding_several_libraries_is_refused_rather_than_guessed(tmp_path, folder):
    for name in ("x", "y"):
        (folder / "IncrementoSync" / "v1" / name).mkdir(parents=True)
        (folder / "IncrementoSync" / "v1" / name / "library.json").write_text(
            f'{{"format":1,"library_id":"{name}"}}', "utf-8")

    with pytest.raises(sync_service.SyncSetupError, match="several"):
        sync_service.configure(str(tmp_path / "a"), "P", str(folder))


def test_a_missing_folder_is_refused(tmp_path):
    with pytest.raises(sync_service.SyncSetupError, match="folder"):
        sync_service.configure(str(tmp_path / "a"), "P", str(tmp_path / "nowhere"))


def test_sync_now_carries_a_priority_from_one_profile_to_another(tmp_path, folder):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    sync_service.configure(a, "P", str(folder))
    sync_service.configure(b, "P", str(folder))
    _set_priority(a, 7, 30.0)

    sent = sync_service.sync_now(a, "P", _collection([7]), now=lambda: 100)
    received = sync_service.sync_now(b, "P", _collection([7]), now=lambda: 200)

    assert sent.captured == 1 and sent.published == 1
    assert received.applied == 1
    assert _priority(b, 7) == 30.0
    assert sync_service.status(b, "P").last_sync == 200


def test_status_reports_what_waits_and_what_needs_a_decision(tmp_path, folder):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    sync_service.configure(a, "P", str(folder))
    sync_service.configure(b, "P", str(folder))
    _set_priority(a, 7, 30.0)
    _set_priority(a, 8, 40.0)
    sync_service.sync_now(a, "P", _collection([7, 8]))
    _set_priority(b, 7, 90.0)

    sync_service.sync_now(b, "P", _collection([7], usn=3))

    status = sync_service.status(b, "P")
    assert (status.conflicts, status.waiting_for_anki, status.waiting_for_files) == (1, 1, 0)
    [conflict] = sync_service.open_conflicts(b, "P")
    assert conflict.family == "priority" and conflict.key == "card:7"
    assert sorted(value["priority"] for value in conflict.values) == [30.0, 90.0]


def test_resolving_a_conflict_through_the_service_keeps_the_chosen_value(tmp_path, folder):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    sync_service.configure(a, "P", str(folder))
    sync_service.configure(b, "P", str(folder))
    _set_priority(a, 7, 30.0)
    sync_service.sync_now(a, "P", _collection([7]))
    _set_priority(b, 7, 90.0)
    sync_service.sync_now(b, "P", _collection([7]))
    [conflict] = sync_service.open_conflicts(b, "P")

    sync_service.resolve(b, "P", conflict.id, {"priority": 30.0}, _collection([7]))
    sync_service.sync_now(b, "P", _collection([7]))
    sync_service.sync_now(a, "P", _collection([7]))

    assert _priority(a, 7) == _priority(b, 7) == 30.0
    assert sync_service.open_conflicts(a, "P") == sync_service.open_conflicts(b, "P") == []


def test_sync_now_does_nothing_until_sync_is_configured(tmp_path):
    report = sync_service.sync_now(str(tmp_path / "a"), "P", _collection([]))

    assert report.skipped == "not configured"


def test_a_second_sync_for_the_same_profile_does_not_start_while_one_runs(tmp_path, folder, monkeypatch):
    a = str(tmp_path / "a")
    sync_service.configure(a, "P", str(folder))
    entered, release = threading.Event(), threading.Event()
    original = sync_service._run

    def slow(*args, **kwargs):
        entered.set()
        release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(sync_service, "_run", slow)
    worker = threading.Thread(target=sync_service.sync_now, args=(a, "P", _collection([])))
    worker.start()
    assert entered.wait(5)

    report = sync_service.sync_now(a, "P", _collection([]))

    release.set()
    worker.join(5)
    assert report.skipped == "already running"


def test_a_sync_stops_between_steps_when_the_profile_is_no_longer_current(tmp_path, folder):
    a = str(tmp_path / "a")
    sync_service.configure(a, "P", str(folder))
    _set_priority(a, 7, 30.0)
    calls = iter([True, False])

    report = sync_service.sync_now(a, "P", _collection([7]), is_current=lambda: next(calls, False))

    assert report.skipped == "profile changed"
    assert report.published == 0


def test_disabling_sync_stops_it_but_keeps_the_identity(tmp_path, folder):
    a = str(tmp_path / "a")
    first = sync_service.configure(a, "P", str(folder))

    sync_service.disable(a, "P")

    assert sync_service.sync_now(a, "P", _collection([])).skipped == "not configured"
    again = sync_service.configure(a, "P", str(folder))
    assert (again.library_id, again.device_id, again.created) == (first.library_id, first.device_id, False)


def test_publishing_on_close_captures_and_publishes_without_applying_anything(tmp_path, folder):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    sync_service.configure(a, "P", str(folder))
    sync_service.configure(b, "P", str(folder))
    _set_priority(b, 8, 10.0)
    sync_service.sync_now(b, "P", _collection([7, 8]))
    _set_priority(a, 7, 30.0)

    report = sync_service.publish_now(a, "P", _collection([7, 8]))

    assert (report.captured, report.published, report.received, report.applied) == (1, 1, 0, 0)
    assert _priority(a, 8) is None, "nothing received is applied while the profile closes"


def test_a_conflict_says_which_value_is_this_computers(tmp_path, folder):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    sync_service.configure(a, "P", str(folder))
    sync_service.configure(b, "P", str(folder))
    _set_priority(a, 7, 30.0)
    sync_service.sync_now(a, "P", _collection([7]))
    _set_priority(b, 7, 90.0)
    sync_service.sync_now(b, "P", _collection([7]))

    [conflict] = sync_service.open_conflicts(b, "P")

    assert conflict.values[conflict.local_index] == {"priority": 90.0}


# --- Restored backups and copied profiles (design note §8, scenario 17) ------------

import shutil  # noqa: E402
from pathlib import Path  # noqa: E402

import paths  # noqa: E402
import sync_paths  # noqa: E402


def _snapshot(addon, destination):
    """What a full backup keeps of the profile's database."""
    source = db.get_connection(addon, "P")
    target = sqlite3.connect(destination)
    source.backup(target)
    target.close()


def _restore(addon, snapshot):
    """What restoring a full backup does: the database comes back, the sync folder (not in backups) does not."""
    db.close_connection()
    database = paths.get_user_files_dir(addon, "P") / "incremento.db"
    for suffix in ("-wal", "-shm"):
        Path(str(database) + suffix).unlink(missing_ok=True)
    shutil.copyfile(snapshot, database)
    shutil.rmtree(sync_paths.get_sync_dir(addon, "P"), ignore_errors=True)


def _device_id(addon):
    return sync_service.sync_identity(db.get_connection(addon, "P")).device_id


def test_a_restored_backup_takes_a_new_device_identity_and_catches_up_with_its_own_later_work(tmp_path, folder):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    sync_service.configure(a, "P", str(folder))
    sync_service.configure(b, "P", str(folder))
    _set_priority(a, 7, 10.0)
    sync_service.sync_now(a, "P", _collection([7, 8]))
    _snapshot(a, tmp_path / "backup.db")
    old_device = _device_id(a)
    _set_priority(a, 7, 20.0)
    _set_priority(a, 8, 30.0)
    sync_service.sync_now(a, "P", _collection([7, 8]))

    _restore(a, tmp_path / "backup.db")
    report = sync_service.sync_now(a, "P", _collection([7, 8]))

    assert _device_id(a) != old_device
    assert report.problems == []
    assert (_priority(a, 7), _priority(a, 8)) == (20.0, 30.0), "the restored device caught up with its later work"
    _set_priority(a, 8, 35.0)
    sync_service.sync_now(a, "P", _collection([7, 8]))
    received = sync_service.sync_now(b, "P", _collection([7, 8]))
    assert received.problems == []
    assert (_priority(b, 7), _priority(b, 8)) == (20.0, 35.0)
    assert sync_service.open_conflicts(a, "P") == sync_service.open_conflicts(b, "P") == []


def test_a_change_not_yet_published_when_the_backup_was_made_is_published_after_the_restore(tmp_path, folder):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    sync_service.configure(a, "P", str(folder))
    sync_service.configure(b, "P", str(folder))
    _set_priority(a, 7, 10.0)
    sync_service.sync_now(a, "P", _collection([7]))
    _set_priority(a, 7, 15.0)
    from sync_capture import capture  # captured, not yet published
    from sync_records import FAMILIES
    from sync_anki import card_refs
    query = _collection([7])
    capture(db.get_connection(a, "P"), FAMILIES, lambda ids: card_refs(query, ids))
    _snapshot(a, tmp_path / "backup.db")

    _restore(a, tmp_path / "backup.db")
    sync_service.sync_now(a, "P", _collection([7]))
    sync_service.sync_now(b, "P", _collection([7]))

    assert _priority(b, 7) == 15.0
    assert sync_service.open_conflicts(b, "P") == []


def test_a_backup_restored_on_another_computer_does_not_share_the_original_devices_identity(tmp_path, folder):
    a, c = str(tmp_path / "a"), str(tmp_path / "c")
    sync_service.configure(a, "P", str(folder))
    _set_priority(a, 7, 10.0)
    sync_service.sync_now(a, "P", _collection([7]))
    _snapshot(a, tmp_path / "backup.db")
    (paths.get_user_files_dir(c, "P")).mkdir(parents=True)
    _restore(c, tmp_path / "backup.db")

    sync_service.sync_now(c, "P", _collection([7]))
    _set_priority(a, 7, 40.0)
    _set_priority(c, 7, 40.0)
    reports = [sync_service.sync_now(device, "P", _collection([7])) for device in (a, c, a)]

    assert _device_id(c) != _device_id(a)
    assert all(report.problems == [] for report in reports)
    assert _priority(a, 7) == _priority(c, 7) == 40.0


# --- Joining checks the Anki collection (design note §3) ---------------------------

def _library_with_cards(tmp_path, folder, cards):
    first = str(tmp_path / "first")
    sync_service.configure(first, "P", str(folder))
    for card in cards:
        _set_priority(first, card, 50.0)
    sync_service.sync_now(first, "P", _collection(cards))


def _guid_collection(cards):
    col = sqlite3.connect(":memory:", check_same_thread=False)
    col.execute("CREATE TABLE col (usn INTEGER, scm INTEGER, mod INTEGER DEFAULT 1)")
    col.execute("INSERT INTO col(usn, scm) VALUES (20, 1000)")
    col.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, guid TEXT)")
    col.execute("CREATE TABLE cards (id INTEGER PRIMARY KEY, nid INTEGER, usn INTEGER)")
    for card_id, guid in cards.items():
        col.execute("INSERT INTO notes VALUES (?, ?)", (card_id * 10, guid))
        col.execute("INSERT INTO cards VALUES (?, ?, 5)", (card_id, card_id * 10))
    return lambda sql, *args: col.execute(sql, args).fetchall()


def test_joining_with_the_same_collection_is_accepted(tmp_path, folder):
    _library_with_cards(tmp_path, folder, [7, 8])

    result = sync_service.configure(str(tmp_path / "b"), "P", str(folder), query=_collection([7, 8]))

    assert not result.created


def test_joining_with_another_collection_is_refused_and_leaves_sync_off(tmp_path, folder):
    _library_with_cards(tmp_path, folder, [7, 8])

    with pytest.raises(sync_service.SyncSetupError, match="another Anki collection"):
        sync_service.configure(str(tmp_path / "b"), "P", str(folder),
                               query=_guid_collection({7: "someone-else", 8: "g8"}))

    assert not sync_service.status(str(tmp_path / "b"), "P").configured


def test_joining_before_the_collection_has_synced_with_ankiweb_explains_what_to_do(tmp_path, folder):
    _library_with_cards(tmp_path, folder, [1, 2, 3, 4, 5, 6])

    with pytest.raises(sync_service.SyncSetupError, match="AnkiWeb"):
        sync_service.configure(str(tmp_path / "b"), "P", str(folder), query=_collection([]))


def test_joining_a_library_without_card_data_yet_is_accepted(tmp_path, folder):
    sync_service.configure(str(tmp_path / "first"), "P", str(folder))

    result = sync_service.configure(str(tmp_path / "b"), "P", str(folder), query=_collection([]))

    assert not result.created


# --- Discarding changes that waited too long (design note §7) -----------------------

DAY = 86400


def test_changes_waiting_over_30_days_are_counted_and_can_be_discarded(tmp_path, folder):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    sync_service.configure(a, "P", str(folder))
    sync_service.configure(b, "P", str(folder))
    _set_priority(a, 7, 30.0)
    _set_priority(a, 8, 40.0)
    sync_service.sync_now(a, "P", _collection([7, 8]), now=lambda: 1000)
    sync_service.sync_now(b, "P", _collection([], usn=3), now=lambda: 1000)  # B never gets the cards
    assert sync_service.status(b, "P", now=1000 + 29 * DAY).stale_waiting == 0

    assert sync_service.status(b, "P", now=1000 + 31 * DAY).stale_waiting == 2
    discarded = sync_service.discard_stale(b, "P", now=1000 + 31 * DAY)

    status = sync_service.status(b, "P", now=1000 + 31 * DAY)
    assert discarded == 2
    assert (status.stale_waiting, status.waiting_for_anki) == (0, 0)
    assert _priority(b, 7) is None
    receipt = db.get_connection(b, "P").execute("SELECT max(max_seq) FROM sync_receipts").fetchone()[0]
    assert receipt == 2, "discarded changes no longer hold back retention"


def test_recent_waiting_changes_are_never_discarded(tmp_path, folder):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    sync_service.configure(a, "P", str(folder))
    sync_service.configure(b, "P", str(folder))
    _set_priority(a, 7, 30.0)
    sync_service.sync_now(a, "P", _collection([7]), now=lambda: 1000)
    sync_service.sync_now(b, "P", _collection([], usn=3), now=lambda: 1000)

    assert sync_service.discard_stale(b, "P", now=1000 + 10 * DAY) == 0
    assert sync_service.status(b, "P", now=1000 + 10 * DAY).waiting_for_anki == 1
