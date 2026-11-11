"""Managed local files (docs: Local file cards, design §6.1): the file of a "Local File" card travels as a blob.

A card whose file is a managed copy (``files/<name>`` in the profile) is shared with every device; a card that only
references a path on one computer is not, because the path means nothing elsewhere. The note itself (title, path, mode)
travels through Anki; sync carries the file and places it where the note says.
"""

import itertools
import sqlite3

import pytest

import paths
import sync_apply
import sync_capture
import sync_exchange
import sync_files
import sync_paths
import sync_records
from sync_records import CardRef

NOTE_TYPE = "Incremento Local File"
FIELDS = ("Title", "Local_File_Name", "Local_File_Path", "Local_File_Mode", "Local_File_Note")
CARDS = {
    7: CardRef(card_id=7, note_id=70, guid="guid-7", uploaded_usn=12),
    8: CardRef(card_id=8, note_id=80, guid="guid-8", uploaded_usn=12),
}
DATA = b"a lecture handout\n" * 100


def _anki(card_ids):
    return {card_id: CARDS[card_id] for card_id in card_ids if card_id in CARDS}


class Device:
    """One computer: its Incremento database, its Anki collection (the note rows sync reads) and its files."""

    def __init__(self, tmp_path, name, folder, *, library_id=None):
        import db
        from db_schema import initialize_schema

        self.addon = tmp_path / name
        self.profile = "Profile"
        self.conn = sqlite3.connect(tmp_path / f"{name}.db", isolation_level="")
        initialize_schema(self.conn, bootstrap=db._create_tables, migrations=db._SCHEMA_MIGRATIONS)
        counter = itertools.count(1)
        sync_capture.enable_sync(self.conn, make_id=lambda: f"{name}-{next(counter)}", library_id=library_id)
        self.col = sqlite3.connect(":memory:")
        self.col.execute("CREATE TABLE notetypes (id INTEGER PRIMARY KEY, name TEXT)")
        self.col.execute("CREATE TABLE fields (ntid INTEGER, ord INTEGER, name TEXT)")
        self.col.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, mid INTEGER, flds TEXT)")
        self.col.execute("CREATE TABLE cards (id INTEGER PRIMARY KEY, nid INTEGER, ord INTEGER)")
        self.col.execute("INSERT INTO notetypes VALUES (1, ?)", (NOTE_TYPE,))
        for ordinal, field in enumerate(FIELDS):
            self.col.execute("INSERT INTO fields VALUES (1, ?, ?)", (ordinal, field))
        self.folder = folder
        self.family = sync_files.LocalFileFamily(str(self.addon), self.profile)
        self.family.query = lambda sql, *args: self.col.execute(sql, args).fetchall()
        self.families = {**sync_records.FAMILIES, "localfile": self.family}
        self.store = sync_paths.get_sync_blob_dir(str(self.addon), self.profile)

    @property
    def files(self):
        return paths.get_local_files_dir(str(self.addon), self.profile)

    def note(self, card_id=7, relpath="files/handout-1.pdf", mode="managed_copy"):
        flds = "\x1f".join(["Handout", relpath.rsplit("/", 1)[-1], relpath, mode, ""])
        self.col.execute("INSERT OR REPLACE INTO notes VALUES (?, 1, ?)", (card_id * 10, flds))
        self.col.execute("INSERT OR REPLACE INTO cards VALUES (?, ?, 0)", (card_id, card_id * 10))

    def add(self, name="handout-1.pdf", data=DATA, card_id=7, mode="managed_copy"):
        self.files.mkdir(parents=True, exist_ok=True)
        (self.files / name).write_bytes(data)
        self.note(card_id, f"files/{name}", mode)

    def push(self):
        sync_capture.capture(self.conn, self.families, _anki, now=lambda: 1)
        return sync_exchange.publish(self.conn, self.folder, blob_store=self.store, now=lambda: 2)

    def pull(self):
        received = sync_exchange.receive(self.conn, self.folder, self.families, blob_store=self.store, now=lambda: 3)
        applied = sync_apply.apply(self.conn, self.families, _anki, blob_store=self.store, now=lambda: 4)
        return received, applied


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


def test_a_managed_file_reaches_the_other_device_where_its_note_says(pair):
    one, two = pair
    one.add()
    two.note()  # the note arrived through Anki; its file has not

    one.push()
    two.pull()

    assert (two.files / "handout-1.pdf").read_bytes() == DATA


def test_a_reference_to_a_path_on_one_computer_is_not_shared(pair):
    one, two = pair
    one.note(relpath="/home/me/handout.pdf", mode="reference")

    assert list(one.family.scan(one.conn)) == []


def test_a_note_whose_file_is_missing_is_unavailable_not_deleted(pair):
    one, _ = pair
    one.note()  # a managed copy named by the note, but the file is not on this device yet

    assert list(one.family.scan(one.conn)) == []
    assert one.family.unavailable(one.conn, "card:7/localfile") is True


def test_the_version_is_the_files_sha256_and_an_unchanged_file_ships_once(pair):
    one, _ = pair
    one.add()

    first = one.push()
    again = one.push()

    assert first.revisions_published == 1
    assert again.revisions_published == 0


def test_a_replaced_file_ships_again(pair):
    one, two = pair
    one.add()
    one.push()
    one.add(data=b"a corrected handout\n" * 10)

    published = one.push()
    two.note()
    two.pull()

    assert published.revisions_published == 1
    assert (two.files / "handout-1.pdf").read_bytes() == b"a corrected handout\n" * 10


def test_two_cards_keep_their_own_files(pair):
    one, two = pair
    one.add("a.txt", b"first", card_id=7)
    one.add("b.txt", b"second", card_id=8)
    two.note(7, "files/a.txt")
    two.note(8, "files/b.txt")

    one.push()
    two.pull()

    assert (two.files / "a.txt").read_bytes() == b"first"
    assert (two.files / "b.txt").read_bytes() == b"second"


@pytest.mark.parametrize("path", ["files/../escape.txt", "files/sub/dir.txt", "/etc/passwd", "files/.hidden", "files/", "x.txt", "files/a\x00b"])
def test_a_path_outside_the_files_folder_is_refused(pair, path):
    one, _ = pair
    value = {"note_id": 70, "path": path, "version": "sha256:" + "a" * 64, "blob": "a" * 64}

    with pytest.raises(ValueError):
        one.family.validate("card:7/localfile", value)


def test_a_record_with_unexpected_fields_is_refused(pair):
    one, _ = pair
    value = {"note_id": 70, "path": "files/a.txt", "version": "sha256:" + "a" * 64, "blob": "a" * 64, "extra": 1}

    with pytest.raises(ValueError):
        one.family.validate("card:7/localfile", value)


def test_a_key_of_another_family_is_refused(pair):
    one, _ = pair

    with pytest.raises(ValueError):
        one.family.card_id("card:7/document:pdf")


def test_deleting_the_record_never_deletes_the_users_file(pair):
    one, _ = pair
    one.add()

    one.family.delete(one.conn, "card:7/localfile")

    assert (one.files / "handout-1.pdf").read_bytes() == DATA


def test_a_symlink_is_never_followed(pair, tmp_path):
    one, _ = pair
    one.files.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "secret.txt"
    outside.write_text("private")
    try:
        (one.files / "link.txt").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are not available here")
    one.note(7, "files/link.txt")

    assert list(one.family.scan(one.conn)) == []


def test_without_a_collection_the_scan_fails_instead_of_reporting_no_files(pair):
    one, _ = pair
    one.family.query = None

    with pytest.raises(sync_records.SyncScanError):
        list(one.family.scan(one.conn))


def test_a_collection_without_note_types_has_no_local_files(pair):
    one, _ = pair
    one.col.execute("DROP TABLE notetypes")

    assert list(one.family.scan(one.conn)) == []


def test_a_collection_that_cannot_be_read_fails_the_scan_instead_of_reporting_no_files(pair):
    one, _ = pair

    def broken(sql, *args):
        raise sqlite3.OperationalError("database is locked")

    one.family.query = broken

    with pytest.raises(sync_records.SyncScanError, match="locked"):
        list(one.family.scan(one.conn))


def test_the_service_syncs_local_files_and_hands_its_collection_to_them(tmp_path):
    import sync_service

    families = sync_service.families_for(str(tmp_path / "svc"), "P")

    assert isinstance(families["localfile"], sync_files.LocalFileFamily)
    assert sync_service.families_for(str(tmp_path / "svc"), "P")["localfile"] is families["localfile"]
