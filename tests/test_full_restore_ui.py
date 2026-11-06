from pathlib import Path
from concurrent.futures import Future
import sys
from types import SimpleNamespace

import pytest

from frontend import full_restore
from frontend.full_restore import default_backup_folder


def test_restore_picker_starts_in_configured_automatic_backup_folder(tmp_path):
    folder = tmp_path / "automatic"
    folder.mkdir()
    assert default_backup_folder({"directory": str(folder)}, tmp_path) == folder


def test_restore_picker_falls_back_when_automatic_folder_is_unavailable(tmp_path):
    assert default_backup_folder({"directory": str(tmp_path / "missing")}, tmp_path) == tmp_path


@pytest.fixture
def restore_ui(tmp_path, monkeypatch):
    """Control asynchronous/UI boundaries without loading a real profile."""
    pending, warnings, information, events = [], [], [], []
    collection_busy = [False]
    progress = SimpleNamespace(visible=False)
    def show_progress():
        progress.visible = True
    def hide_progress():
        progress.visible = False
    progress.start, progress.finish = show_progress, hide_progress
    progress.update = lambda _detail: None
    stage = SimpleNamespace(
        config={}, profile_stage_dir=tmp_path / "anki-staging",
        runtime_stage_dir=tmp_path / "runtime-staging",
        cleanup=lambda: events.append("cleanup"),
    )
    window = SimpleNamespace(
        col=object(), restoring_backup=False,
        pm=SimpleNamespace(
            name="Target", profile={"autoSync": True, "autoSyncMediaMinutes": 15},
            collectionPath=lambda: str(tmp_path / "collection.anki2"),
            save=lambda: events.append("save preferences"),
        ),
        taskman=SimpleNamespace(run_in_background=lambda work, done, *, uses_collection=True:
                                pending.append((work, done, uses_collection))),
    )
    def unload(callback):
        assert not progress.visible
        events.append("unload")
        window.col = None
        callback()
    def load():
        events.append("load")
        window.col = object()
    window.unloadProfile, window.loadProfile = unload, load
    window.create_backup_now = lambda: events.append("safety backup")

    class QueryOp:
        def __init__(self, *, parent, op, success):
            self.op, self.success = op, success
        def failure(self, callback):
            self.failed = callback
            return self
        def run_in_background(self):
            def done(future):
                if error := future.exception():
                    self.failed(error)
                else:
                    self.success(future.result())
            window.taskman.run_in_background(lambda: self.op(window.col), done)

    class Prompt:
        Icon = SimpleNamespace(Warning=1)
        StandardButton = SimpleNamespace(Yes=1, No=2)
        answer = 1
        def __init__(self, _parent):
            pass
        def setWindowTitle(self, _text): pass
        def setIcon(self, _icon): pass
        def setText(self, _text): pass
        def setInformativeText(self, _text): pass
        def setStandardButtons(self, _buttons): pass
        def setDefaultButton(self, _button): pass
        def button(self, _button):
            return SimpleNamespace(setText=lambda _text: None)
        def exec(self):
            assert not progress.visible
            events.append("confirm")
            return self.answer

    report = SimpleNamespace(
        source_profile="Target", profile_mismatch=False, missing_cover_count=0,
        card_count=1, media_count=1, profile_file_count=1,
    )
    swap = SimpleNamespace(commit=lambda: events.append("commit"), rollback=lambda: events.append("rollback"))
    monkeypatch.setitem(sys.modules, "aqt.operations", SimpleNamespace(QueryOp=QueryOp))
    monkeypatch.setitem(sys.modules, "aqt.qt", SimpleNamespace(
        QFileDialog=SimpleNamespace(getOpenFileName=lambda *_: (str(tmp_path / "backup.zip"), "")),
        QMessageBox=Prompt,
    ))
    monkeypatch.setitem(sys.modules, "aqt.utils", SimpleNamespace(
        showWarning=warnings.append, showInfo=information.append, tooltip=information.append,
    ))
    monkeypatch.setattr(full_restore, "FullRestoreProgress", lambda _: progress)
    monkeypatch.setattr(full_restore, "precheck_backup", lambda *_a, **_k: report)
    monkeypatch.setattr(full_restore, "stage_backup", lambda *_: stage)
    monkeypatch.setattr(full_restore, "swap_staged_backup", lambda *_: swap)
    monkeypatch.setattr(full_restore, "close_current_connection", lambda *_: None)
    monkeypatch.setattr(full_restore, "_restore_running", False)

    def start():
        full_restore.restore_full_backup(
            window, addon_dir=str(tmp_path / "addon"), profile_key="Target", profile_name="Target",
            current_config={}, save_config=lambda _: events.append("save config"),
            backup_running=lambda: False, reset_close_gate=lambda: None,
        )
    def drain():
        for _ in range(10):
            runnable = next((index for index, (_, _, uses_collection) in enumerate(pending)
                             if not uses_collection or not collection_busy[0]), None)
            if runnable is None:
                return
            work, done, _ = pending.pop(runnable)
            future = Future()
            try:
                future.set_result(work())
            except Exception as error:
                future.set_exception(error)
            done(future)
        pytest.fail("restore did not settle within ten background tasks")
    return SimpleNamespace(**locals())


def test_zip_precheck_reaches_confirmation_while_collection_worker_is_busy(restore_ui):
    ui = restore_ui
    ui.collection_busy[0] = True
    ui.start()
    ui.drain()
    assert "confirm" in ui.events, "ZIP checking must not wait behind unrelated collection work"
    assert "safety backup" not in ui.events and "unload" not in ui.events
    assert ui.progress.visible
    ui.collection_busy[0] = False
    ui.drain()
    assert not ui.progress.visible and not full_restore._restore_running
    assert "safety backup" in ui.events and len(ui.information) == 1


@pytest.mark.parametrize("failure", ["precheck_backup", "stage_backup", "create_backup_now"])
def test_restore_failure_reports_error_releases_progress_and_preserves_profile(restore_ui, monkeypatch, failure):
    ui = restore_ui
    def fail(*_args, **_kwargs):
        raise OSError("synthetic failure")
    monkeypatch.setattr(ui.window if failure == "create_backup_now" else full_restore, failure, fail)
    ui.start()
    assert ui.progress.visible
    ui.drain()
    assert not ui.progress.visible and not full_restore._restore_running
    assert len(ui.warnings) == 1 and "synthetic failure" in ui.warnings[0]
    assert "unload" not in ui.events and "save config" not in ui.events
    assert ui.window.pm.profile == {"autoSync": True, "autoSyncMediaMinutes": 15}
    assert not ui.information


@pytest.mark.parametrize("cancel", [True, False], ids=["declined", "profile-changed"])
def test_restore_decline_or_stale_profile_cleans_staging_without_replacing_data(restore_ui, cancel):
    ui = restore_ui
    ui.start()
    if cancel:
        ui.Prompt.answer = ui.Prompt.StandardButton.No
    else:
        ui.window.pm.name = "Other"
    ui.drain()
    assert "cleanup" in ui.events
    assert "unload" not in ui.events and "save config" not in ui.events
    assert not ui.progress.visible and not full_restore._restore_running
    assert len(ui.warnings) == (0 if cancel else 1)
    assert not ui.information


def test_safety_backup_dispatch_failure_releases_restore_progress(restore_ui, monkeypatch):
    ui = restore_ui
    ui.start()
    def unavailable(*_args):
        raise RuntimeError("executor stopped")
    monkeypatch.setattr(ui.QueryOp, "run_in_background", unavailable)
    ui.drain()
    assert not ui.progress.visible and not full_restore._restore_running
    assert len(ui.warnings) == 1 and "executor stopped" in ui.warnings[0]
    assert "cleanup" in ui.events and "unload" not in ui.events


def test_successful_restore_with_failed_cleanup_shows_warning_instead_of_silent_activity(restore_ui, monkeypatch):
    ui = restore_ui
    def failed_cleanup():
        raise OSError("cleanup failed")
    monkeypatch.setattr(ui.swap, "commit", failed_cleanup)
    ui.start()
    ui.drain()
    assert not ui.progress.visible and not full_restore._restore_running
    assert len(ui.warnings) == 1 and "cleanup failed" in ui.warnings[0]
    assert "load" in ui.events and "rollback" not in ui.events
    assert ui.window.pm.profile == {"autoSync": False, "autoSyncMediaMinutes": 0}


@pytest.mark.parametrize("phase", ["replace_files", "cleanup"])
def test_restore_dispatch_failure_shows_result_and_releases_progress(restore_ui, monkeypatch, phase):
    ui = restore_ui
    dispatch = ui.window.taskman.run_in_background

    def unavailable(work, done, **kwargs):
        if work.__name__ == phase:
            raise RuntimeError("executor rejected restore phase")
        return dispatch(work, done, **kwargs)

    monkeypatch.setattr(ui.window.taskman, "run_in_background", unavailable)
    ui.start()
    ui.drain()

    assert not ui.progress.visible and not full_restore._restore_running
    assert len(ui.warnings) == 1 and "executor rejected restore phase" in ui.warnings[0]
    assert "load" in ui.events and "rollback" not in ui.events
    assert ui.window.pm.profile == {
        "autoSync": phase == "replace_files",
        "autoSyncMediaMinutes": 15 if phase == "replace_files" else 0,
    }


@pytest.mark.parametrize("change", ["collection-during-check", "collection-during-safety", "profile-during-safety"])
def test_stale_restore_never_closes_new_collection_or_overwrites_new_profile_preferences(restore_ui, change):
    ui = restore_ui
    ui.start()
    if change != "collection-during-check":
        work, done, _ = ui.pending.pop(0)
        checked = Future()
        checked.set_result(work())
        done(checked)
    if change == "profile-during-safety":
        ui.window.pm.name = "Other"
        ui.window.pm.profile = {"autoSync": False, "autoSyncMediaMinutes": 0}
    else:
        ui.window.col = object()
    preferences = dict(ui.window.pm.profile)

    ui.drain()

    assert "unload" not in ui.events and "save config" not in ui.events
    assert ui.window.pm.profile == preferences
    assert not ui.progress.visible and not full_restore._restore_running
    assert len(ui.warnings) == 1
