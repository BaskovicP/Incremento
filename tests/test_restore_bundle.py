"""Full-backup restore must reject unsafe archives before replacing a profile."""

import json
import sqlite3
import sys
import types
import zipfile
from concurrent.futures import Future
from pathlib import Path

import pytest

from backend import restore_bundle


@pytest.fixture(autouse=True)
def _synthetic_anki_package(monkeypatch):
    """SQLite fixtures below model hostile packages; real Anki is checked separately."""
    monkeypatch.setattr(restore_bundle, "_verify_anki_open", lambda *_args: None)


def _database_bytes(path: Path, *, incremento: bool = False, orphan: bool = False,
                    missing_cover: bool = False) -> bytes:
    conn = sqlite3.connect(path)
    if incremento:
        conn.execute("CREATE TABLE priorities (card_id INTEGER PRIMARY KEY)")
        conn.execute("PRAGMA user_version = 1")
    else:
        conn.execute("CREATE TABLE col (id INTEGER PRIMARY KEY, conf TEXT, models TEXT, decks TEXT, dconf TEXT, tags TEXT)")
        models = {"5": {"id": 5, "name": "Incremento PDF", "flds": [
            {"name": "Title"}, {"name": "PDF_Cover_Image"},
        ]}} if missing_cover else {}
        conn.execute("INSERT INTO col VALUES (1, ?, ?, '{}', '{}', '{}')", ("{}", json.dumps(models)))
        conn.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, mid INTEGER, flds TEXT, tags TEXT)")
        conn.execute("CREATE TABLE cards (id INTEGER PRIMARY KEY, nid INTEGER NOT NULL, did INTEGER, queue INTEGER, due INTEGER, ivl INTEGER)")
        conn.execute("CREATE TABLE revlog (id INTEGER PRIMARY KEY, cid INTEGER, ease INTEGER, ivl INTEGER)")
        if orphan:
            conn.execute("INSERT INTO cards (id, nid) VALUES (1, 99)")
        else:
            if missing_cover:
                conn.execute("INSERT INTO notes (id, mid, flds) VALUES (1, 5, ?)",
                             ("A PDF\x1fmissing-cover.png",))
            else:
                conn.execute("INSERT INTO notes (id) VALUES (1)")
            conn.execute("INSERT INTO cards (id, nid) VALUES (1, 1)")
    conn.commit()
    conn.close()
    return path.read_bytes()


def _backup(tmp_path: Path, *, extra=None, orphan=False, media=None,
            missing_cover=False) -> Path:
    anki_db = _database_bytes(tmp_path / "anki.db", orphan=orphan,
                              missing_cover=missing_cover)
    incremento_db = _database_bytes(tmp_path / "incremento.db", incremento=True)
    apkg = tmp_path / "all_decks.apkg"
    with zipfile.ZipFile(apkg, "w") as archive:
        archive.writestr("collection.anki21", anki_db)
        archive.writestr("media", json.dumps(media if media is not None else {"0": "photo.png"}))
        archive.writestr("0", b"photo")
    backup = tmp_path / "backup.zip"
    with zipfile.ZipFile(backup, "w") as archive:
        archive.write(apkg, "anki/all_decks.apkg")
        archive.writestr("user_files/Source/incremento.db", incremento_db)
        archive.writestr("user_files/Source/writing/note.md", b"saved")
        archive.writestr("config.json", "{}")
        archive.writestr("manifest.json", json.dumps({
            "schema_version": 2, "addon": "Incremento", "scope": "current_profile",
            "profile": "Source", "profile_storage_key": "Source",
            "counts": {
                "anki_cards_exported": 1,
                "user_files_copied": 2,
                "user_files_bytes": len(incremento_db) + len(b"saved"),
            },
            "database": {"schema_version": 1, "integrity_check": "ok"},
        }))
        for name, value in (extra or {}).items():
            archive.writestr(name, value)
    return backup


def test_precheck_valid_backup_reports_profile_and_counts_without_writing_target(tmp_path):
    backup = _backup(tmp_path)
    target = tmp_path / "target"

    report = restore_bundle.precheck_backup(backup, target_profile="Target")

    assert report.source_profile == "Source"
    assert report.target_profile == "Target"
    assert report.card_count == 1
    assert report.media_count == 1
    assert report.profile_file_count == 2
    assert report.profile_mismatch is True
    assert not target.exists()


def test_precheck_warns_about_pdf_cover_missing_from_older_backup(tmp_path):
    backup = _backup(tmp_path, missing_cover=True)

    report = restore_bundle.precheck_backup(backup, target_profile="Target")

    assert report.missing_cover_count == 1


@pytest.mark.parametrize("extra", [
    {"user_files/Source/../../outside": b"bad"},
    {"user_files/Other/incremento.db": b"bad"},
    {"user_files/Source/writing/note.md": b"duplicate"},
])
def test_precheck_rejects_unsafe_or_ambiguous_outer_members(tmp_path, extra):
    backup = _backup(tmp_path, extra=extra)
    with pytest.raises(restore_bundle.BackupValidationError):
        restore_bundle.precheck_backup(backup, target_profile="Target")


def test_precheck_rejects_orphaned_anki_card(tmp_path):
    backup = _backup(tmp_path, orphan=True)
    with pytest.raises(restore_bundle.BackupValidationError, match="orphan"):
        restore_bundle.precheck_backup(backup, target_profile="Target")


def test_precheck_rejects_unsafe_media_name(tmp_path):
    backup = _backup(tmp_path, media={"0": "../escape.png"})
    with pytest.raises(restore_bundle.BackupValidationError, match="media"):
        restore_bundle.precheck_backup(backup, target_profile="Target")


def test_stage_and_swap_restore_profile_and_roll_back_on_failure(tmp_path):
    backup = _backup(tmp_path)
    profile_dir = tmp_path / "anki_profile"
    profile_dir.mkdir()
    collection = profile_dir / "collection.anki2"
    collection.write_bytes(b"old collection")
    media_dir = profile_dir / "collection.media"
    media_dir.mkdir()
    (media_dir / "old.png").write_bytes(b"old media")
    runtime = tmp_path / "addon" / "user_files" / "Target"
    runtime.mkdir(parents=True)
    (runtime / "old.txt").write_bytes(b"old runtime")

    report = restore_bundle.precheck_backup(backup, target_profile="Target")
    staged = restore_bundle.stage_backup(backup, report, collection, runtime)
    try:
        swap = restore_bundle.swap_staged_backup(staged, collection, media_dir, runtime)
        assert (media_dir / "photo.png").read_bytes() == b"photo"
        assert (runtime / "writing" / "note.md").read_bytes() == b"saved"
        assert not (runtime / "old.txt").exists()
        swap.rollback()
        assert collection.read_bytes() == b"old collection"
        assert (media_dir / "old.png").read_bytes() == b"old media"
        assert (runtime / "old.txt").read_bytes() == b"old runtime"
    finally:
        staged.cleanup()


def test_swap_failure_restores_every_live_path(tmp_path, monkeypatch):
    backup = _backup(tmp_path)
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    collection = profile_dir / "collection.anki2"
    collection.write_bytes(b"old collection")
    media = profile_dir / "collection.media"
    media.mkdir()
    (media / "old.png").write_bytes(b"old media")
    runtime = tmp_path / "addon" / "user_files" / "Target"
    runtime.mkdir(parents=True)
    (runtime / "old.txt").write_bytes(b"old runtime")
    report = restore_bundle.precheck_backup(backup, target_profile="Target")
    staged = restore_bundle.stage_backup(backup, report, collection, runtime)
    original_replace = restore_bundle.os.replace

    def fail_runtime_swap(source, target):
        if Path(source) == staged.runtime:
            raise OSError("disk error")
        return original_replace(source, target)

    monkeypatch.setattr(restore_bundle.os, "replace", fail_runtime_swap)
    try:
        with pytest.raises(OSError, match="disk error"):
            restore_bundle.swap_staged_backup(staged, collection, media, runtime)
        assert collection.read_bytes() == b"old collection"
        assert (media / "old.png").read_bytes() == b"old media"
        assert (runtime / "old.txt").read_bytes() == b"old runtime"
    finally:
        staged.cleanup()


def test_failed_rollback_keeps_prior_collection_in_staging(tmp_path, monkeypatch):
    backup = _backup(tmp_path)
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    collection = profile_dir / "collection.anki2"
    collection.write_bytes(b"old collection")
    media = profile_dir / "collection.media"
    media.mkdir()
    runtime = tmp_path / "addon" / "user_files" / "Target"
    runtime.mkdir(parents=True)
    staged = restore_bundle.stage_backup(
        backup,
        restore_bundle.precheck_backup(backup, target_profile="Target"),
        collection,
        runtime,
    )
    original_replace = restore_bundle.os.replace

    def fail_swap_and_rollback(source, target):
        if Path(source) == staged.runtime or Path(source) == staged.profile_stage_dir / "previous-0":
            raise OSError("disk error")
        return original_replace(source, target)

    monkeypatch.setattr(restore_bundle.os, "replace", fail_swap_and_rollback)
    with pytest.raises(restore_bundle.RestoreRollbackError, match="rollback failed"):
        restore_bundle.swap_staged_backup(staged, collection, media, runtime)
    assert (staged.profile_stage_dir / "previous-0").read_bytes() == b"old collection"


@pytest.mark.parametrize("fail_first_open", [False, True])
@pytest.mark.parametrize("missing_cover", [False, True])
def test_restore_flow_creates_safety_backup_and_rolls_back_failed_reopen(
    tmp_path, monkeypatch, fail_first_open, missing_cover
):
    from frontend import full_restore

    backup = _backup(tmp_path, missing_cover=missing_cover)
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    collection = profile_dir / "collection.anki2"
    collection.write_bytes(b"old collection")
    media = profile_dir / "collection.media"
    media.mkdir()
    (media / "old.png").write_bytes(b"old media")
    runtime = tmp_path / "addon" / "user_files" / "Target"
    runtime.mkdir(parents=True)
    (runtime / "old.txt").write_bytes(b"old runtime")

    events = []
    warnings = []
    saved_configs = []
    prompt_texts = []

    class Taskman:
        def run_in_background(self, work, done):
            future = Future()
            try:
                future.set_result(work())
            except Exception as exc:
                future.set_exception(exc)
            done(future)

    class ProfileManager:
        name = "Target"

        def __init__(self):
            self.profile = {"autoSync": True, "autoSyncMediaMinutes": 15}

        def collectionPath(self):
            return str(collection)

        def save(self):
            events.append("save profile")

    class Window:
        def __init__(self):
            self.pm = ProfileManager()
            self.taskman = Taskman()
            self.col = object()
            self.restoring_backup = False
            self.opens = 0

        def create_backup_now(self):
            events.append("safety backup")

        def unloadProfile(self, callback):
            events.append("unload")
            self.col = None
            callback()

        def loadProfile(self):
            self.opens += 1
            events.append("load")
            self.col = None if fail_first_open and self.opens == 1 else object()

    class QFileDialog:
        @staticmethod
        def getOpenFileName(*_args):
            return str(backup), "ZIP files"

    class QMessageBox:
        class Icon:
            Warning = 1

        class StandardButton:
            Yes = 1
            No = 2

        def __init__(self, _parent):
            pass

        def setWindowTitle(self, _text):
            pass

        def setIcon(self, _icon):
            pass

        def setText(self, _text):
            pass

        def setInformativeText(self, _text):
            prompt_texts.append(_text)

        def setStandardButtons(self, _buttons):
            pass

        def setDefaultButton(self, _button):
            pass

        def button(self, _button):
            return types.SimpleNamespace(setText=lambda _text: None)

        def exec(self):
            return self.StandardButton.Yes

    class QueryOp:
        def __init__(self, *, parent, op, success):
            self.parent, self.op, self.success = parent, op, success

        def failure(self, callback):
            self.on_failure = callback
            return self

        def with_progress(self):
            return self

        def run_in_background(self):
            try:
                self.success(self.op(self.parent.col))
            except Exception as exc:
                self.on_failure(exc)

    monkeypatch.setitem(sys.modules, "aqt.operations", types.SimpleNamespace(QueryOp=QueryOp))
    monkeypatch.setitem(sys.modules, "aqt.qt", types.SimpleNamespace(QFileDialog=QFileDialog, QMessageBox=QMessageBox))
    monkeypatch.setitem(sys.modules, "aqt.utils", types.SimpleNamespace(showWarning=warnings.append, tooltip=lambda message: events.append(message)))
    monkeypatch.setattr(full_restore, "get_user_files_dir", lambda *_: runtime)
    monkeypatch.setattr(full_restore, "start_activity", lambda *_a, **_k: 1)
    monkeypatch.setattr(full_restore, "update_activity", lambda *_a, **_k: None)
    monkeypatch.setattr(full_restore, "finish_activity", lambda *_a, **_k: None)
    monkeypatch.setattr(full_restore, "fail_activity", lambda *_a, **_k: None)

    window = Window()
    full_restore.restore_full_backup(
        window, addon_dir=str(tmp_path / "addon"), profile_key="Target",
        profile_name="Target", current_config={"automatic_backups": {"Target": {
            "directory": str(tmp_path)
        }}}, save_config=saved_configs.append, backup_running=lambda: False,
        reset_close_gate=lambda: None,
    )

    assert events.index("safety backup") < events.index("unload")
    assert "AnkiWeb" in prompt_texts[0]
    assert ("PDF/EPUB covers" in prompt_texts[0]) is missing_cover
    if fail_first_open:
        assert collection.read_bytes() == b"old collection"
        assert (media / "old.png").read_bytes() == b"old media"
        assert (runtime / "old.txt").read_bytes() == b"old runtime"
        assert window.pm.profile["autoSync"] is True
        assert window.pm.profile["autoSyncMediaMinutes"] == 15
        assert "previous profile was restored" in warnings[-1]
    else:
        assert (media / "photo.png").read_bytes() == b"photo"
        assert (runtime / "writing" / "note.md").read_bytes() == b"saved"
        assert window.pm.profile["autoSync"] is False
        assert window.pm.profile["autoSyncMediaMinutes"] == 0
        assert not warnings
        assert saved_configs[0]["automatic_backups"]["Target"]["directory"] == str(tmp_path)
