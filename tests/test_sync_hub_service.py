"""A profile that syncs through a hub: paired once with a code, then synced like any other folder.

The desktop add-on calls ``sync_now(addon, profile, query)`` with no store; the service works out from what was
configured where to sync. Here that is a hub.
"""

import json
import os
import sqlite3

import pytest

import db
import sync_http
import sync_paths
import sync_service
from sync_http import Hub, KeyBook, Pairing


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


CARDS = _collection(range(1, 30))


@pytest.fixture(autouse=True)
def _fresh():
    db.close_connection()
    yield
    db.close_connection()


@pytest.fixture
def hub(tmp_path):
    book = KeyBook(tmp_path / "keys.json")
    root = tmp_path / "HubFolder"
    root.mkdir()
    server = Hub(root, book.as_mapping(), host="127.0.0.1", port=0)
    server.start()
    server.book = book
    yield server
    server.stop()


def _code(hub, name):
    return Pairing("127.0.0.1", hub.port, name, hub.book.add(name)).code()


def _set(addon, card, value):
    with db.get_connection(addon, "P") as conn:
        conn.execute("INSERT OR REPLACE INTO priorities(card_id, priority) VALUES (?, ?)", (card, value))


def _get(addon, card):
    row = db.get_connection(addon, "P").execute("SELECT priority FROM priorities WHERE card_id=?", (card,)).fetchone()
    return None if row is None else row[0]


def test_two_profiles_pair_with_a_hub_and_sync_with_no_store_argument(hub, tmp_path):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    sync_service.configure_hub(a, "P", _code(hub, "desktop"), query=CARDS)
    sync_service.configure_hub(b, "P", _code(hub, "laptop"), query=CARDS)

    _set(a, 7, 31.0)
    for addon in (a, b):
        report = sync_service.sync_now(addon, "P", CARDS)
        assert report.problems == [] and report.skipped is None, (report.problems, report.skipped)

    assert _get(b, 7) == 31.0


def test_the_publish_on_close_also_goes_through_the_hub(hub, tmp_path):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    sync_service.configure_hub(a, "P", _code(hub, "desktop"), query=CARDS)
    sync_service.configure_hub(b, "P", _code(hub, "laptop"), query=CARDS)

    _set(a, 9, 12.5)
    sync_service.publish_now(a, "P", CARDS)
    sync_service.sync_now(b, "P", CARDS)

    assert _get(b, 9) == 12.5


def test_the_pairing_is_remembered_in_the_profile_and_only_the_owner_can_read_it(hub, tmp_path):
    addon = str(tmp_path / "a")
    code = _code(hub, "desktop")

    sync_service.configure_hub(addon, "P", code, query=CARDS)

    saved = sync_paths.get_sync_dir(addon, "P") / "hub.json"
    assert Pairing.from_code(json.loads(saved.read_text(encoding="utf-8"))["code"]) == Pairing.from_code(code)
    if os.name != "nt":
        assert saved.stat().st_mode & 0o077 == 0
    status = sync_service.status(addon, "P")
    assert status.configured and status.folder.startswith("hub:desktop")
    assert Pairing.from_code(code).key.hex() not in status.folder


def test_a_bad_code_and_an_unreachable_hub_are_setup_errors_the_dialog_can_show(hub, tmp_path):
    addon = str(tmp_path / "a")

    with pytest.raises(sync_service.SyncSetupError, match="pairing code"):
        sync_service.configure_hub(addon, "P", "nonsense", query=CARDS)
    unreachable = Pairing("127.0.0.1", 9, "desktop", sync_http.new_key()).code()
    with pytest.raises(sync_service.SyncSetupError, match="hub"):
        sync_service.configure_hub(addon, "P", unreachable, query=CARDS)
    assert not sync_service.status(addon, "P").configured
    assert not (sync_paths.get_sync_dir(addon, "P") / "hub.json").exists()
    # An unreachable hub is not an empty one: no library may be invented for it.
    assert sync_service.sync_identity(db.get_connection(addon, "P")) is None


def test_a_hub_that_does_not_know_this_device_is_a_setup_error(hub, tmp_path):
    addon = str(tmp_path / "a")
    stranger = Pairing("127.0.0.1", hub.port, "stranger", sync_http.new_key()).code()

    with pytest.raises(sync_service.SyncSetupError, match="hub"):
        sync_service.configure_hub(addon, "P", stranger, query=CARDS)


def test_syncing_when_the_pairing_file_is_missing_says_so(hub, tmp_path):
    addon = str(tmp_path / "a")
    sync_service.configure_hub(addon, "P", _code(hub, "desktop"), query=CARDS)
    (sync_paths.get_sync_dir(addon, "P") / "hub.json").unlink()

    with pytest.raises(sync_service.SyncSetupError, match="pair"):
        sync_service.sync_now(addon, "P", CARDS)


def test_choosing_a_folder_after_a_hub_syncs_through_the_folder_again(hub, tmp_path):
    addon, folder = str(tmp_path / "a"), tmp_path / "Cloud"
    folder.mkdir()
    sync_service.configure_hub(addon, "P", _code(hub, "desktop"), query=CARDS)
    _set(addon, 3, 3.0)
    sync_service.sync_now(addon, "P", CARDS)

    sync_service.configure(addon, "P", str(folder), query=CARDS)
    report = sync_service.sync_now(addon, "P", CARDS)

    assert report.problems == []
    assert any(folder.rglob("library.json")), "the folder, not the hub, received the library"
    other = str(tmp_path / "b")
    sync_service.configure(other, "P", str(folder), query=CARDS)
    sync_service.sync_now(other, "P", CARDS)
    assert _get(other, 3) == 3.0
