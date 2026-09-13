"""Automatic backups explain temporary Anki unavailability while they run."""

import ast
import os
import subprocess
import sys
import types
from pathlib import Path
from textwrap import dedent

from frontend import backup_progress
from frontend.backup_progress import AutomaticBackupProgress


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


def test_automatic_backup_shows_dedicated_progress_and_worker_stage_on_main_thread(monkeypatch):
    window = _Window()
    dialog = _Dialog()
    monkeypatch.setattr(backup_progress, "_build_dialog", lambda: dialog)
    indicator = AutomaticBackupProgress(window)

    indicator.start()
    assert indicator._dialog is dialog

    indicator.update("Creating Anki package…")
    indicator.update("Creating Anki package… exported media 200")
    assert dialog.calls == []
    assert len(window.taskman.pending) == 1
    window.taskman.pending.pop(0)()
    assert dialog.calls == [("stage", "Creating Anki package… exported media 200")]


def test_automatic_backup_finishes_once_and_drops_queued_updates_after_completion(monkeypatch):
    window = _Window()
    dialog = _Dialog()
    monkeypatch.setattr(backup_progress, "_build_dialog", lambda: dialog)
    indicator = AutomaticBackupProgress(window)
    indicator.start()
    indicator.update("Writing backup ZIP…")

    indicator.finish()
    indicator.finish()
    window.taskman.pending.pop(0)()

    assert dialog.calls == [("finish",)]


def test_automatic_backup_window_remains_visible_during_disabled_profile_close():
    script = dedent("""
        from aqt.qt import QApplication, QLabel, QProgressBar, QWidget
        from frontend.backup_progress import _build_dialog

        app = QApplication([])
        main = QWidget()
        main.show()
        main.setEnabled(False)
        dialog = _build_dialog()
        app.processEvents()

        assert dialog.isVisible() and dialog.isEnabled()
        assert "Automatic Backup" in dialog.windowTitle()
        labels = dialog.findChildren(QLabel)
        assert any("Anki is temporarily unavailable" in label.text() for label in labels)
        bar = dialog.findChild(QProgressBar)
        assert bar.minimum() == 0 and bar.maximum() == 0
        dialog.close()
        dialog.reject()
        assert dialog.isVisible()
        dialog.set_stage("Writing backup ZIP…")
        assert any(label.text() == "Writing backup ZIP…" for label in labels)
        dialog.finish()
        app.processEvents()
        assert not dialog.isVisible()
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_failed_close_backup_hides_progress_before_resuming_profile_close(
    monkeypatch, tmp_path,
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
    monkeypatch.setitem(sys.modules, progress_module.__name__, progress_module)

    pending = []
    destination = tmp_path / "backups"
    destination.mkdir()
    profile_root = tmp_path / "addon" / "user_files" / "P"
    profile_root.mkdir(parents=True)
    window = types.SimpleNamespace(
        addonManager=object(), col=object(),
        taskman=types.SimpleNamespace(
            run_in_background=lambda task, done: pending.append(done)
        ),
    )
    source = (Path(__file__).resolve().parents[1] / "__init__.py").read_text()
    function = next(
        node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == "_start_full_backup"
    )
    namespace = {
        "__name__": "incremento", "__package__": "incremento",
        "_ADDON_DIR": str(tmp_path / "addon"),
        "_active_profile": lambda: "P",
        "_current_profile_name": lambda: "P",
        "_paths": types.SimpleNamespace(get_user_files_dir=lambda *_: profile_root),
        "_backup_schedule": types.SimpleNamespace(
            validate_destination=lambda folder, _profile: Path(folder)
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
        str(destination / "backup.zip"), automatic_policy={"directory": str(destination)},
        close_triggered=True,
    )
    assert started is True
    assert events == ["show"]
    namespace["_backup_idle_callbacks"].append(lambda: events.append("resume"))

    class _Failure:
        def result(self):
            raise RuntimeError("write failed")

    pending[0](_Failure())
    assert events == ["show", "hide", "resume"]
    assert namespace["_full_backup_running"] is False
