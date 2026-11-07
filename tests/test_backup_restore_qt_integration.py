"""Full backup/restore with real Anki, task queues, SQLite and offscreen Qt.

Only the host-window adapters, user choices and deliberate failures are faked.
The subprocess prevents the normal test suite's Anki/Qt stubs from leaking in.
"""

import os
from pathlib import Path
import subprocess
import sys

import pytest


def _run(mode, locale, outcome):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), mode, locale, outcome],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("mode", ["manual", "automatic"])
@pytest.mark.parametrize("locale", ["en", "hr", "zh-Hans"])
def test_full_backup_restores_data_after_reinstall_with_responsive_visible_progress(mode, locale):
    _run(mode, locale, "success")


def test_large_backup_and_restore_keep_processing_qt_events_and_preserve_every_file():
    _run("manual", "en", "large")


@pytest.mark.parametrize("outcome", [
    "declined", "corrupt", "reopen-failed", "swap-failed", "disk-full",
    "swap-dispatch-failed", "cleanup-dispatch-failed", "rollback-dispatch-failed",
    "swap-and-rollback-failed",
])
def test_failed_or_declined_backup_restore_preserves_current_data_and_releases_qt(outcome):
    _run("manual", "en", outcome)


def _scenario(mode, locale, outcome):
    import ast
    import copy
    from contextlib import nullcontext
    import importlib
    import json
    import random
    import shutil
    import sqlite3
    import tempfile
    from threading import Event, current_thread, main_thread
    import time
    import traceback
    from types import ModuleType, SimpleNamespace
    from unittest.mock import patch
    import weakref
    import zipfile

    # Direct script execution puts tests/ first on sys.path.
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))
    import aqt
    from anki.collection import Collection
    from aqt.qt import (
        QApplication, QEvent, QEventLoop, QFileDialog, QLabel, QMainWindow,
        QMessageBox, QObject, QProgressBar, QTimer, sip,
    )
    from aqt.taskman import TaskManager
    from backend import backup_schedule, db, paths, priority_manager
    from backend.i18n import initialize_language, t
    from frontend import backup_progress, full_restore

    initialize_language(locale)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    async_errors, messages, dialogs, stages, paints = [], [], [], [], []
    def report_error(kind, error, stack):
        async_errors.append(error)
        traceback.print_exception(kind, error, stack)
    sys.excepthook = report_error

    class PaintObserver(QObject):
        def eventFilter(self, watched, event):
            if event.type() == QEvent.Type.Paint:
                paints.append(watched)
            return False

    paint_observer = PaintObserver()
    build_dialog = backup_progress._build_dialog

    def observed_dialog(**kwargs):
        dialog = build_dialog(**kwargs)
        bar = dialog.findChild(QProgressBar)
        assert bar is not None and bar.minimum() == bar.maximum() == 0
        assert dialog.isVisible() and dialog.isEnabled()
        bar.installEventFilter(paint_observer)
        set_stage = dialog.set_stage

        def display(stage):
            assert current_thread() is main_thread()
            stages.append(stage)
            set_stage(stage)

        dialog.set_stage = display
        dialogs.append(dialog)
        return dialog

    def visible_dialogs():
        return [dialog for dialog in dialogs if not sip.isdeleted(dialog) and dialog.isVisible()]

    def spin_until(predicate):
        loop = QEventLoop()
        poll = QTimer()
        poll.setInterval(5)
        deadline = time.monotonic() + 20
        timed_out = []

        def check():
            if async_errors or predicate():
                loop.quit()
            elif time.monotonic() >= deadline:
                timed_out.append(True)
                loop.quit()

        poll.timeout.connect(check)
        poll.start()
        loop.exec()
        poll.stop()
        assert not async_errors, repr(async_errors)
        assert not timed_out, "backup/restore did not finish before its bounded deadline"
        app.processEvents()

    with tempfile.TemporaryDirectory(prefix="incremento-backup-qt-") as temporary:
        root = Path(temporary)
        addon = root / "addon"
        profile_name = "Profile ü"
        profile = paths.sanitize_profile_name(profile_name)
        paths.set_active_profile(profile_name)
        runtime = paths.get_user_files_dir(str(addon), profile)
        anki_profile = root / "Anki profile 测试"
        anki_profile.mkdir()
        collection_path = anki_profile / "collection.anki2"
        destination = root / "backups"
        destination.mkdir()
        safety_folder = anki_profile / "backups"
        safety_folder.mkdir()
        policy = backup_schedule.normalize_policy({
            "enabled": True, "directory": str(destination), "versions": 3,
        })
        stored_config = {"ui_language": locale, "automatic_backups": {profile: policy}}

        def save_config(value):
            stored_config.clear()
            stored_config.update(copy.deepcopy(value))

        class Window(QMainWindow):
            def __init__(self):
                super().__init__()
                self.col = Collection(str(collection_path))
                self.pm = SimpleNamespace(
                    name=profile_name, profile={"autoSync": True, "autoSyncMediaMinutes": 15},
                    collectionPath=lambda: str(collection_path), save=lambda: None, meta={},
                )
                self.addonManager = object()
                self.restoring_backup = False
                self.background_ops = self.safety_count = self.unloads = self.opens = 0
                self.taskman = TaskManager(self)

            def weakref(self):
                return weakref.proxy(self)

            def _increase_background_ops(self):
                self.background_ops += 1

            def _decrease_background_ops(self):
                self.background_ops -= 1

            def create_backup_now(self):
                self.safety_count += 1
                self.col.create_backup(
                    backup_folder=str(safety_folder), force=True, wait_for_completion=True,
                )

            def unloadProfile(self, callback):
                assert not visible_dialogs(), "progress must not obstruct native profile closing"
                self.unloads += 1
                db.close_current_connection(str(addon), profile)
                self.col.close(downgrade=False)
                self.col = None
                self.setEnabled(False)
                self.hide()
                QTimer.singleShot(0, callback)

            def loadProfile(self):
                self.opens += 1
                self.col = Collection(str(collection_path))
                priority_manager.get_priority(str(addon), profile, card_id)
                self.setEnabled(True)
                self.show()
                if outcome in {"reopen-failed", "rollback-dispatch-failed"} and self.opens == 1:
                    raise RuntimeError("synthetic reopen failure after opening the collection")

        window = Window()
        aqt.mw = window
        window.show()
        futures = []
        dispatch = window.taskman.run_in_background

        def tracked_dispatch(*args, **kwargs):
            rejected_phase = {
                "swap-dispatch-failed": "replace_files", "cleanup-dispatch-failed": "cleanup",
                "rollback-dispatch-failed": "rollback_files",
            }.get(outcome)
            if rejected_phase and args[0].__name__ == rejected_phase:
                raise RuntimeError("synthetic executor rejection")
            future = dispatch(*args, **kwargs)
            futures.append(future)
            return future

        window.taskman.run_in_background = tracked_dispatch
        try:
            # One real reviewed document card, including ordinary and bare-cover media.
            model = window.col.models.by_name("Basic")
            model["name"] = "Incremento PDF"
            for field in ("PDF_Cover_Image", "PDF_Filename"):
                window.col.models.add_field(model, window.col.models.new_field(field))
            window.col.models.update_dict(model)
            media = {}
            for filename in ("cover_测试.png", "inline.png", "audio.wav"):
                path = root / filename
                path.write_bytes(random.Random(filename).randbytes(128 * 1024))
                media[window.col.media.add_file(str(path))] = path.read_bytes()
            note = window.col.new_note(model)
            note["Front"] = "Original backup content"
            note["Back"] = '<img src="inline.png">[sound:audio.wav]'
            note["PDF_Cover_Image"] = "cover_测试.png"
            note["PDF_Filename"] = "source.pdf"
            deck_id = window.col.decks.id("Backup test")
            window.col.add_note(note, deck_id)
            window.col.decks.select(deck_id)
            card_id = note.card_ids()[0]
            window.col.sched.get_queued_cards(fetch_limit=1)
            card = window.col.get_card(card_id)
            card.start_timer()
            window.col.sched.answerCard(card, 3)
            schedule_fields = ("id", "nid", "did", "due", "ivl", "type", "queue", "reps", "lapses")
            expected_schedule = tuple(getattr(window.col.get_card(card_id), key) for key in schedule_fields)
            expected_revlog = window.col.db.all("SELECT id,cid,ease,ivl FROM revlog ORDER BY id")
            priority_manager.set_priority(str(addon), profile, card_id, 85)
            conn = db.get_connection(str(addon), profile)
            conn.execute("INSERT INTO pdf_progress(card_id,page,zoom) VALUES (?,7,1.25)", (card_id,))
            conn.execute(
                "INSERT INTO pdf_highlights(card_id,id,page,text,rects) VALUES (?,'saved-highlight',7,'saved text','[]')",
                (card_id,),
            )
            conn.commit()
            files = {
                "pdfs/source.pdf": b"%PDF-1.4\nsynthetic document bytes\n%%EOF",
                "epubs/source.epub": b"synthetic managed EPUB bytes",
                "writing/note.md": "Saved writing\nCafé 测试".encode(),
                "videos/source.mp4": random.Random(1).randbytes((64 if outcome == "large" else 1) * 1024 * 1024),
            }
            for filename, data in files.items():
                path = runtime / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)

            # Import just the real backup composition function, without starting the add-on.
            package_name = "backup_qt_addon"
            package = ModuleType(package_name)
            package.__path__ = [str(repo)]
            sys.modules[package_name] = package
            for suffix in ("backend", "frontend", "backend.backup_media", "backend.db",
                           "backend.export_bundle", "backend.activity_log", "frontend.backup_progress"):
                sys.modules[f"{package_name}.{suffix}"] = importlib.import_module(suffix)
            tree = ast.parse((repo / "__init__.py").read_text())
            function = next(node for node in tree.body
                            if isinstance(node, ast.FunctionDef) and node.name == "_start_full_backup")
            namespace = {
                "__name__": package_name, "__package__": package_name,
                "_ADDON_DIR": str(addon), "_paths": paths,
                "_active_profile": lambda: profile, "_current_profile_name": lambda: profile_name,
                "_backup_schedule": backup_schedule, "_full_backup_running": False,
                "_backup_idle_callbacks": [], "_load_addon_config": lambda *_: copy.deepcopy(stored_config),
                "_save_addon_config": lambda _manager, _name, value: save_config(value),
                "_record_close_backup_result": lambda *_a, **_k: None,
                "_video_dock_mod": SimpleNamespace(flush_video_progress=lambda: None),
                "mw": window, "QTimer": QTimer, "os": os, "json": json, "time": time,
                "zipfile": zipfile, "tooltip": lambda message: messages.append(("tooltip", message)),
                "showInfo": lambda message: messages.append(("info", message)), "_t": t,
            }
            exec(compile(ast.Module(body=[function], type_ignores=[]), str(repo / "__init__.py"), "exec"), namespace)
            heartbeat_counts = {"backup": 0, "restore": 0}
            responsive = {phase: Event() for phase in heartbeat_counts}
            heartbeat = QTimer()
            heartbeat.setInterval(10)

            def heartbeat_tick():
                if namespace["_full_backup_running"]:
                    heartbeat_counts["backup"] += 1
                if full_restore._restore_running:
                    heartbeat_counts["restore"] += 1
                for phase, count in heartbeat_counts.items():
                    if count >= 10:
                        responsive[phase].set()

            heartbeat.timeout.connect(heartbeat_tick)
            heartbeat.start()
            backup = destination / "manual.zip" if mode == "manual" else backup_schedule.next_backup_path(destination, profile, 3)
            with patch.object(backup_progress, "_build_dialog", observed_dialog):
                write = zipfile.ZipFile.write

                def write_after_heartbeat(*args, **kwargs):
                    # Fast disks must still exercise Qt while the worker is active.
                    assert responsive["backup"].wait(10), "backup blocked Qt's event loop"
                    return write(*args, **kwargs)

                write_failure = (patch.object(zipfile.ZipFile, "write", side_effect=OSError("synthetic disk full"))
                                 if outcome == "disk-full" else
                                 patch.object(zipfile.ZipFile, "write", write_after_heartbeat)
                                 if outcome == "large" else nullcontext())
                with write_failure:
                    if outcome == "disk-full":
                        backup.write_bytes(b"previous verified archive")
                    assert namespace["_start_full_backup"](
                        str(backup), automatic_policy=policy if mode == "automatic" else None,
                    )
                    assert visible_dialogs(), "backup must show a bar before entering the worker queue"
                    dialog_count = len(dialogs)
                    duplicate = destination / "duplicate.zip"
                    assert not namespace["_start_full_backup"](str(duplicate))
                    assert len(dialogs) == dialog_count and not duplicate.exists()
                    spin_until(lambda: not namespace["_full_backup_running"] and all(f.done() for f in futures))
                assert not visible_dialogs() and app.activeModalWidget() is None
                if outcome == "disk-full":
                    assert backup.read_bytes() == b"previous verified archive"
                    assert any("synthetic disk full" in message for _, message in messages)
                    return
                assert paints, "the Qt event loop never painted the backup progress bar"
                with zipfile.ZipFile(backup) as archive:
                    assert archive.testzip() is None
                    assert json.loads(archive.read("manifest.json"))["counts"]["anki_cards_exported"] == 1
                    for filename, data in files.items():
                        assert archive.read(f"user_files/{profile}/{filename}") == data

                # Reinstall removes local add-on data but leaves this same Anki collection.
                db.close_connection(str(addon), profile)
                shutil.rmtree(runtime)
                priority_manager.set_priority(str(addon), profile, card_id, 10)
                note["Front"] = "Current content after backup"
                window.col.update_note(note)
                (runtime / "current-only.txt").write_bytes(b"keep on failed restore")
                policy_before_restore = copy.deepcopy(stored_config["automatic_backups"])
                window.taskman.run_in_background(
                    lambda: priority_manager.get_priority(str(addon), profile, card_id),
                )
                spin_until(lambda: all(f.done() for f in futures))
                if outcome == "corrupt":
                    backup.write_bytes(b"damaged ZIP")
                busy, release = Event(), Event()

                def occupy_collection_worker():
                    busy.set()
                    assert release.wait(20)

                window.taskman.run_in_background(occupy_collection_worker)
                spin_until(busy.is_set)
                confirmations = []
                user = QTimer()
                user.setInterval(5)

                def answer_confirmation():
                    for dialog in app.topLevelWidgets():
                        if isinstance(dialog, QMessageBox) and dialog.isVisible():
                            assert not release.is_set(), "pre-check waited for the busy collection queue"
                            confirmations.append(dialog.informativeText())
                            button = QMessageBox.StandardButton.No if outcome == "declined" else QMessageBox.StandardButton.Yes
                            dialog.button(button).click()
                    if not release.is_set() and confirmations and any(
                        label.text() == t("admin_full_restore_creating_safety_backup")
                        for dialog in visible_dialogs() for label in dialog.findChildren(QLabel)
                    ):
                        assert window.safety_count == 0
                        release.set()

                user.timeout.connect(answer_confirmation)
                user.start()
                replace = full_restore.swap_staged_backup
                precheck = full_restore.precheck_backup
                allow_precheck = Event()

                def precheck_after_progress(*args, **kwargs):
                    if not allow_precheck.wait(timeout=10):
                        raise AssertionError("Progress was not checked before releasing the pre-check")
                    if outcome == "large":
                        assert responsive["restore"].wait(10), "restore blocked Qt's event loop"
                    return precheck(*args, **kwargs)

                def swap_with_failure(stage, *args):
                    if outcome in {"swap-failed", "swap-and-rollback-failed"}:
                        original_replace = os.replace
                        def fail_runtime(source, target):
                            if (Path(source) == stage.runtime or
                                    (outcome == "swap-and-rollback-failed"
                                     and Path(source).parent == stage.runtime_stage_dir
                                     and Path(source).name.startswith("previous-"))):
                                raise OSError("synthetic replacement failure")
                            return original_replace(source, target)
                        with patch.object(os, "replace", fail_runtime):
                            return replace(stage, *args)
                    return replace(stage, *args)

                with patch.object(QFileDialog, "getOpenFileName", return_value=(str(backup), "")), \
                     patch("aqt.utils.showInfo", side_effect=lambda message: messages.append(("info", message))), \
                     patch("aqt.utils.showWarning", side_effect=lambda message: messages.append(("warning", message))), \
                     patch("aqt.utils.tooltip", side_effect=lambda message: messages.append(("tooltip", message))), \
                     patch.object(full_restore, "precheck_backup", precheck_after_progress), \
                     patch.object(full_restore, "swap_staged_backup", swap_with_failure):
                    request = {
                        "addon_dir": str(addon), "profile_key": profile, "profile_name": profile_name,
                        "current_config": copy.deepcopy(stored_config), "save_config": save_config,
                        "backup_running": lambda: namespace["_full_backup_running"], "reset_close_gate": lambda: None,
                    }
                    try:
                        full_restore.restore_full_backup(window, **request)
                        assert visible_dialogs(), "restore pre-check must show progress immediately"
                        dialog_count = len(dialogs)
                        full_restore.restore_full_backup(window, **request)
                        assert len(dialogs) == dialog_count
                    finally:
                        allow_precheck.set()
                    spin_until(lambda: not full_restore._restore_running)
                release.set()
                user.stop()
                spin_until(lambda: all(f.done() for f in futures))
                assert not visible_dialogs() and app.activeModalWidget() is None
                assert len(confirmations) == (0 if outcome == "corrupt" else 1)
                if outcome in {"rollback-dispatch-failed", "swap-and-rollback-failed"}:
                    profile_stages = list(anki_profile.glob(".incremento-restore-*"))
                    runtime_stages = list(runtime.parent.glob(".incremento-restore-*"))
                    assert len(profile_stages) == len(runtime_stages) == 1, "the retained original files were deleted"
                    assert window.col is None and not full_restore._restore_running
                    warning = next(message for kind, message in messages if kind == "warning")
                    expected_error = "synthetic executor rejection" if outcome == "rollback-dispatch-failed" else "synthetic replacement failure"
                    assert expected_error in warning
                    assert str(profile_stages[0]) in warning and str(runtime_stages[0]) in warning
                    previous_collection = profile_stages[0] / "previous-0"
                    with sqlite3.connect(previous_collection.resolve().as_uri() + "?mode=ro", uri=True) as prior:
                        assert prior.execute("SELECT flds FROM notes WHERE id=?", (note.id,)).fetchone()[0].startswith("Current content after backup")
                    previous_runtime = next(runtime_stages[0].glob("previous-*"))
                    assert (previous_runtime / "current-only.txt").read_bytes() == b"keep on failed restore"
                    assert window.pm.profile == {"autoSync": False, "autoSyncMediaMinutes": 0}
                    return
                assert window.col is not None and window.isEnabled()
                assert window.background_ops == 0
                assert stored_config["automatic_backups"] == policy_before_restore
                succeeded = outcome in {"success", "large", "cleanup-dispatch-failed"}
                assert window.col.get_note(note.id)["Front"] == ("Original backup content" if succeeded else "Current content after backup")
                assert tuple(getattr(window.col.get_card(card_id), key) for key in schedule_fields) == expected_schedule
                assert window.col.db.all("SELECT id,cid,ease,ivl FROM revlog ORDER BY id") == expected_revlog
                assert priority_manager.get_priority(str(addon), profile, card_id) == (85 if succeeded else 10)
                worker_priority = window.taskman.run_in_background(
                    lambda: priority_manager.get_priority(str(addon), profile, card_id),
                )
                spin_until(worker_priority.done)
                assert worker_priority.result() == (85 if succeeded else 10)
                if succeeded:
                    assert not (runtime / "current-only.txt").exists()
                    for filename, data in files.items():
                        assert (runtime / filename).read_bytes() == data
                    for filename, data in media.items():
                        assert (Path(window.col.media.dir()) / filename).read_bytes() == data
                    restored = db.get_connection(str(addon), profile)
                    assert restored.execute("SELECT page,zoom FROM pdf_progress WHERE card_id=?", (card_id,)).fetchone() == (7, 1.25)
                    assert restored.execute("SELECT text FROM pdf_highlights WHERE card_id=?", (card_id,)).fetchone() == ("saved text",)
                    assert window.pm.profile == {"autoSync": False, "autoSyncMediaMinutes": 0}
                    if outcome == "cleanup-dispatch-failed":
                        assert any(kind == "warning" and "synthetic executor rejection" in message for kind, message in messages)
                    else:
                        assert any(kind == "info" and message == t("admin_full_restore_full_backup_restored_review_the_profile_before_syncing") for kind, message in messages)
                    assert window.safety_count == 1 and any(safety_folder.iterdir())
                else:
                    assert (runtime / "current-only.txt").read_bytes() == b"keep on failed restore"
                    assert window.pm.profile == {"autoSync": True, "autoSyncMediaMinutes": 15}
                    assert not succeeded and (outcome == "declined" or any(kind == "warning" for kind, _ in messages))
                if outcome == "cleanup-dispatch-failed":
                    runtime_stage = next(runtime.parent.glob(".incremento-restore-*"))
                    prior_runtime = next(runtime_stage.glob("previous-*"))
                    assert (prior_runtime / "current-only.txt").read_bytes() == b"keep on failed restore"
                else:
                    assert not list(anki_profile.glob(".incremento-restore-*"))
                    assert not list(runtime.parent.glob(".incremento-restore-*"))
                assert not list(destination.glob(".incremento-backup-*"))
                if outcome == "large":
                    assert heartbeat_counts["backup"] >= 10, "backup blocked Qt's event loop"
                    assert heartbeat_counts["restore"] >= 10, "restore blocked Qt's event loop"
        finally:
            if "heartbeat" in locals():
                heartbeat.stop()
            if "release" in locals():
                release.set()
            for executor in (window.taskman._collection_executor, window.taskman._no_collection_executor):
                executor.shutdown(wait=True)
            db.close_connection()
            if window.col is not None:
                window.col.close(downgrade=False)
            for dialog in visible_dialogs():
                dialog.finish()
            window.close()
            aqt.mw = None


if __name__ == "__main__":
    _scenario(*sys.argv[1:])
