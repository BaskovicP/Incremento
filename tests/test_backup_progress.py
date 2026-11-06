"""Full backups and restores show progress until their background work finishes."""

import ast
import os
import subprocess
import sys
import types
from pathlib import Path
from textwrap import dedent

import pytest

from frontend import backup_progress
from frontend.backup_progress import AutomaticBackupProgress, FullRestoreProgress, ManualBackupProgress


class _Dialog:
    def __init__(self):
        self.calls = []

    def set_stage(self, stage):
        self.calls.append(("stage", stage))

    def finish(self):
        self.calls.append(("finish",))


class _Taskman:
    def __init__(self):
        self.pending = []

    def run_on_main(self, callback):
        self.pending.append(callback)


class _Window:
    def __init__(self):
        self.taskman = _Taskman()


@pytest.mark.parametrize("progress_type", [AutomaticBackupProgress, ManualBackupProgress, FullRestoreProgress])
def test_backup_shows_dedicated_progress_and_worker_stage_on_main_thread(monkeypatch, progress_type):
    window = _Window()
    dialog = _Dialog()
    monkeypatch.setattr(backup_progress, "_build_dialog", lambda **_kwargs: dialog)
    indicator = progress_type(window)

    indicator.start()
    assert indicator._dialog is dialog

    indicator.update("Creating Anki package…")
    indicator.update("Creating Anki package… exported media 200")
    assert dialog.calls == []
    assert len(window.taskman.pending) == 1
    window.taskman.pending.pop(0)()
    assert dialog.calls == [("stage", "Creating Anki package… exported media 200")]


@pytest.mark.parametrize("progress_type", [AutomaticBackupProgress, ManualBackupProgress, FullRestoreProgress])
def test_backup_finishes_once_and_drops_queued_updates_after_completion(monkeypatch, progress_type):
    window = _Window()
    dialog = _Dialog()
    monkeypatch.setattr(backup_progress, "_build_dialog", lambda **_kwargs: dialog)
    indicator = progress_type(window)
    indicator.start()
    indicator.update("Writing backup ZIP…")

    indicator.finish()
    indicator.finish()
    window.taskman.pending.pop(0)()

    assert dialog.calls == [("finish",)]


@pytest.mark.parametrize("mode", ["automatic", "manual", "restore"])
def test_backup_window_remains_visible_during_disabled_profile_close(mode):
    script = dedent("""
        from aqt.qt import QApplication, QLabel, QProgressBar, QWidget
        from frontend.backup_progress import _build_dialog

        app = QApplication([])
        main = QWidget()
        main.show()
        main.setEnabled(False)
        mode = __MODE__
        dialog = _build_dialog(restore=mode == "restore", manual=mode == "manual")
        app.processEvents()

        assert dialog.isVisible() and dialog.isEnabled()
        expected_title = {"restore": "Restore Full Backup", "manual": "Full Backup",
                          "automatic": "Incremento Automatic Backup"}[mode]
        assert dialog.windowTitle() == expected_title
        assert app.activeModalWidget() is dialog
        labels = dialog.findChildren(QLabel)
        expected_text = {"restore": "Checking backup", "manual": "Preparing backup",
                         "automatic": "Anki is temporarily unavailable"}[mode]
        assert any(expected_text in label.text() for label in labels)
        bar = dialog.findChild(QProgressBar)
        assert bar.minimum() == 0 and bar.maximum() == 0
        assert bar.accessibleName()
        dialog.close()
        dialog.reject()
        assert dialog.isVisible()
        dialog.set_stage("Writing backup ZIP…")
        assert any(label.text() == "Writing backup ZIP…" for label in labels)
        dialog.finish()
        app.processEvents()
        assert not dialog.isVisible()
        assert app.activeModalWidget() is None
    """).replace("__MODE__", repr(mode))
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("automatic", [False, True], ids=["manual", "automatic"])
@pytest.mark.parametrize("outcome", ["success", "failure", "profile-changed", "start-failed"])
def test_full_backup_keeps_progress_until_completion_and_hides_it_before_resuming_close(
    monkeypatch, tmp_path, automatic, outcome,
):
    events = []
    activity = types.ModuleType("incremento.backend.activity_log")
    activity.start_activity = lambda *_args, **_kwargs: 1
    activity.update_activity = lambda *_args, **_kwargs: None
    activity.finish_activity = lambda *_args, **_kwargs: None
    activity.fail_activity = lambda *_args, **_kwargs: None
    for name, module in {
        "incremento.backend.activity_log": activity,
        "incremento.backend.backup_media": types.ModuleType("backup_media"),
        "incremento.backend.db": types.ModuleType("db"),
        "incremento.backend.export_bundle": types.ModuleType("export_bundle"),
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    database = sys.modules["incremento.backend.db"]
    for name in (
        "get_connection", "DB_NAME", "export_priorities_json",
        "export_pdf_progress_json", "export_highlights_json", "export_stats_json",
    ):
        setattr(database, name, object())
    sys.modules["incremento.backend.backup_media"].FullBackupPackageExporter = object
    sys.modules["incremento.backend.export_bundle"].snapshot_tree = object()
    sys.modules["incremento.backend.export_bundle"].snapshot_database = object()

    progress_module = types.ModuleType("incremento.frontend.backup_progress")

    class _Indicator:
        def __init__(self, _window):
            pass

        def start(self):
            events.append("show")

        def update(self, _stage):
            pass

        def finish(self):
            events.append("hide")

    progress_module.AutomaticBackupProgress = _Indicator
    progress_module.ManualBackupProgress = _Indicator
    monkeypatch.setitem(sys.modules, progress_module.__name__, progress_module)

    pending = []
    destination = tmp_path / "backups"
    destination.mkdir()
    profile_root = tmp_path / "addon" / "user_files" / "P"
    profile_root.mkdir(parents=True)
    def run_in_background(task, done):
        if outcome == "start-failed":
            raise RuntimeError("executor stopped")
        pending.append(done)

    window = types.SimpleNamespace(
        addonManager=object(), col=object(),
        taskman=types.SimpleNamespace(
            run_in_background=run_in_background
        ),
    )
    source = (Path(__file__).resolve().parents[1] / "__init__.py").read_text()
    function = next(
        node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == "_start_full_backup"
    )
    active_profile = ["P"]
    namespace = {
        "__name__": "incremento", "__package__": "incremento",
        "_ADDON_DIR": str(tmp_path / "addon"),
        "_active_profile": lambda: active_profile[0],
        "_current_profile_name": lambda: "P",
        "_paths": types.SimpleNamespace(get_user_files_dir=lambda *_: profile_root),
        "_backup_schedule": types.SimpleNamespace(
            validate_destination=lambda folder, _profile: Path(folder),
            backup_staging_directory=lambda _destination, *, automatic: tmp_path,
        ),
        "_load_addon_config": lambda *_: {},
        "_video_dock_mod": types.SimpleNamespace(flush_video_progress=lambda: None),
        "_full_backup_running": False,
        "_backup_idle_callbacks": [],
        "_record_close_backup_result": lambda *_args, **_kwargs: None,
        "mw": window,
        "os": os,
        "QTimer": types.SimpleNamespace(singleShot=lambda _delay, callback: callback()),
        "tooltip": lambda _message: None,
        "_t": __import__("backend.i18n", fromlist=["Translator"]).Translator("en").t,
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), "__init__.py", "exec"), namespace)

    started = namespace["_start_full_backup"](
        str(destination / "backup.zip"),
        automatic_policy={"directory": str(destination)} if automatic else None,
        close_triggered=automatic,
    )
    if outcome == "start-failed":
        assert started is False
        assert events == ["show", "hide"]
        assert namespace["_full_backup_running"] is False
        return
    assert started is True
    assert events == ["show"]
    namespace["_backup_idle_callbacks"].append(lambda: events.append("resume"))

    class _Result:
        def result(self):
            if outcome == "failure":
                raise RuntimeError("write failed")
            return {"retention_error": None}

    if outcome == "profile-changed":
        active_profile[0] = "Other"
    pending[0](_Result())
    assert events == ["show", "hide", "resume"]
    assert namespace["_full_backup_running"] is False
