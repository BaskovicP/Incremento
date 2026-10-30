"""Profile upgrades must finish before use without freezing the Qt event loop."""

from concurrent.futures import CancelledError
import ast
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from textwrap import dedent

import pytest

import db
import db_schema
import profile_startup as storage
from frontend import profile_startup as ui


@pytest.fixture(autouse=True)
def isolated_connections():
    db.close_connection()
    yield
    db.close_connection()


def _old_database(root, profile="A"):
    path = storage.get_db_path(str(root), profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        db_schema.initialize_schema(conn, bootstrap=db._create_tables,
            migrations=tuple(m for m in db._SCHEMA_MIGRATIONS if m[0] <= 18))
        conn.execute("INSERT INTO pdf_text_index VALUES(7, 1, 'preserved text')")
    return path


def test_current_profile_preflight_is_read_only_and_does_not_enumerate_content(tmp_path, monkeypatch):
    storage.prepare_storage(str(tmp_path), "A")
    db.close_connection()
    queries = []
    connect = sqlite3.connect

    def inspected_connect(*args, **kwargs):
        assert kwargs["uri"] and "mode=ro" in args[0]
        conn = connect(*args, **kwargs)
        conn.set_trace_callback(queries.append)
        return conn

    monkeypatch.setattr(storage.sqlite3, "connect", inspected_connect)
    assert storage.storage_preparation_needed(str(tmp_path), "A") is False
    assert queries == ["PRAGMA user_version"]


def test_old_profile_is_upgraded_once_with_stage_timings_and_preserved_search(tmp_path, monkeypatch):
    path = _old_database(tmp_path)
    assert storage.storage_preparation_needed(str(tmp_path), "A")
    ticks = iter([1.0, 1.25, 2.0])
    monkeypatch.setattr(storage.time, "monotonic", lambda: next(ticks))
    stages = []
    result = storage.prepare_storage(str(tmp_path), "A", progress=stages.append)

    assert stages == ["files", "database"]
    assert result == {"files_ms": 250, "database_ms": 750}
    assert db._connection_manager.connection_count() == 0
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone() == (23,)
        assert conn.execute("SELECT text FROM pdf_text_fts WHERE pdf_text_fts MATCH 'preserved'").fetchall() == [
            ("preserved text",)]
    assert not storage.storage_preparation_needed(str(tmp_path), "A")
    assert storage.storage_preparation_needed(str(tmp_path), "B")


def test_preparation_moves_legacy_storage_before_opening_the_captured_profile(tmp_path):
    path = _old_database(tmp_path)
    legacy = path.parent.parent / "incremento.db"
    path.rename(legacy)

    storage.prepare_storage(str(tmp_path), "B")

    target = storage.get_db_path(str(tmp_path), "B")
    assert not legacy.exists() and not path.exists()
    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT text FROM pdf_text_index").fetchall() == [("preserved text",)]
        assert conn.execute("PRAGMA user_version").fetchone() == (23,)


def test_failed_upgrade_rolls_back_and_closes_the_worker_connection(tmp_path, monkeypatch):
    path = _old_database(tmp_path)

    def interrupted(conn):
        db._migration_19_search_fts_keys(conn)
        raise OSError("synthetic full disk")

    monkeypatch.setattr(db, "_SCHEMA_MIGRATIONS", tuple(
        (version, name, interrupted if version == 19 else migrate)
        for version, name, migrate in db._SCHEMA_MIGRATIONS))
    with pytest.raises(OSError, match="synthetic full disk"):
        storage.prepare_storage(str(tmp_path), "A")

    assert db._connection_manager.connection_count() == 0
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone() == (18,)
        assert conn.execute("SELECT text FROM pdf_text_fts").fetchall() == [("preserved text",)]
    assert storage.storage_preparation_needed(str(tmp_path), "A")


def test_future_database_is_never_downgraded_or_silently_accepted(tmp_path):
    path = _old_database(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version=999")
    assert storage.storage_preparation_needed(str(tmp_path), "A")
    with pytest.raises(db_schema.DatabaseSchemaTooNewError):
        storage.prepare_storage(str(tmp_path), "A")
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone() == (999,)


def test_current_profile_opens_without_a_preparation_dialog(tmp_path, monkeypatch):
    storage.prepare_storage(str(tmp_path), "A")
    monkeypatch.setattr(ui, "_run_preparation", lambda *_: pytest.fail("unexpected startup dialog"))
    assert ui.prepare_profile_storage(object(), str(tmp_path), "A") is None


def test_profile_open_waits_for_background_preparation_and_returns_its_timings(tmp_path, monkeypatch):
    _old_database(tmp_path)
    window = object()
    stages = []

    def run(actual_window, work):
        assert actual_window is window
        return work(stages.append)

    monkeypatch.setattr(ui, "_run_preparation", run)
    result = ui.prepare_profile_storage(window, str(tmp_path), "A")
    assert stages == ["files", "database"]
    assert result.keys() == {"files_ms", "database_ms"}
    assert not storage.storage_preparation_needed(str(tmp_path), "A")


def test_profile_open_does_not_hide_preparation_failure(tmp_path, monkeypatch):
    def fail(*_args):
        raise CancelledError()
    monkeypatch.setattr(ui, "_run_preparation", fail)
    with pytest.raises(CancelledError):
        ui.prepare_profile_storage(object(), str(tmp_path), "A")


def test_profile_open_prepares_storage_before_starting_dependent_services():
    source = (Path(__file__).parents[1] / "__init__.py").read_text()
    function = next(node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == "_on_profile_did_open")
    calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
    preparation = next(node for node in calls
        if isinstance(node.func, ast.Name) and node.func.id == "_prepare_profile_storage")
    recorder = next(node for node in calls
        if isinstance(node.func, ast.Attribute) and node.func.attr == "DiagnosticRecorder")
    assert preparation.lineno < recorder.lineno
    assert "migrate_to_profile_dir(" not in ast.get_source_segment(source, function)


def test_profile_switch_stops_postpone_pollers_before_waiting_for_storage():
    from unittest.mock import Mock

    source = (Path(__file__).parents[1] / "__init__.py").read_text()
    tree = ast.parse(source)
    stop = next(node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_stop_postpone_runtime_timers")
    timers = [Mock(), Mock()]
    namespace = {"_topic_postpone_timer": timers[0], "_item_skip_timer": timers[1]}
    exec(compile(ast.Module(body=[stop], type_ignores=[]), "__init__.py", "exec"), namespace)
    namespace[stop.name]()
    for timer in timers:
        timer.stop.assert_called_once_with()
    function = next(node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_on_profile_did_open")
    calls = {node.func.id: node.lineno for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert calls["_stop_postpone_runtime_timers"] < calls["_prepare_profile_storage"]
    assert calls["_prepare_profile_storage"] < calls["_initialize_topic_postpone_runtime"]
    assert calls["_prepare_profile_storage"] < calls["_initialize_item_skip_runtime"]


def test_support_diagnostics_keep_only_bounded_preparation_durations():
    import diagnostics

    assert diagnostics._sanitize_event_data("profile_storage_prepared", {
        "files_ms": -1, "database_ms": 1234,
        "profile": "private", "path": "/private/book.pdf", "text": "private text",
    }) == {"files_ms": 0, "database_ms": 1234}


def test_stale_profile_preparation_cannot_activate_the_previous_profiles_services():
    from types import SimpleNamespace
    from unittest.mock import Mock

    source = (Path(__file__).parents[1] / "__init__.py").read_text()
    function = next(node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == "_on_profile_did_open")
    namespace = {node.id: Mock(name=node.id) for node in ast.walk(function) if isinstance(node, ast.Name)}
    window = SimpleNamespace(col=object(), addonManager=object(), taskman=object())
    def switched(*_args):
        window.col = object()
        return {"files_ms": 1, "database_ms": 2}
    namespace.update(mw=window, _current_profile_name=lambda: "A",
        _diagnostic_recorder=None, _pdf_search_lifecycle=None, _prepare_profile_storage=switched)
    exec(compile(ast.Module(body=[function], type_ignores=[]), "__init__.py", "exec"), namespace)
    namespace[function.name]()
    namespace["_diagnostics_mod"].DiagnosticRecorder.assert_not_called()
    namespace["_initialize_topic_postpone_runtime"].assert_not_called()
    namespace["_initialize_item_skip_runtime"].assert_not_called()


def test_preflight_does_not_create_missing_profile_storage(tmp_path):
    assert storage.storage_preparation_needed(str(tmp_path), "Missing")
    assert not (tmp_path / "user_files").exists()


def test_real_qt_preparation_keeps_paint_and_timers_alive_and_releases_modal_state(tmp_path):
    root = str(Path(__file__).parents[1])
    program = dedent('''
        import sys
        import threading
        import weakref
        from concurrent.futures import CancelledError
        from aqt.qt import QApplication, QLabel, QMainWindow, QTimer
        from aqt.taskman import TaskManager
        from backend.i18n import initialize_language
        from frontend import profile_startup as ui

        app = QApplication.instance() or QApplication([])
        class Window(QMainWindow):
            def weakref(self):
                return weakref.ref(self)
        window = Window()
        window.taskman = TaskManager(window)
        # A hidden parent reproduces the reported "Anki hasn't opened" case.
        assert not window.isVisible()
        main_thread = threading.get_ident()
        dialogs = []
        build = ui._create_dialog
        def create(parent):
            dialog = build(parent)
            dialogs.append(dialog)
            return dialog
        ui._create_dialog = create

        pulse = threading.Event()
        observations = []
        timer = QTimer()
        def tick():
            modal = QApplication.activeModalWidget()
            if modal is not None and dialogs and modal is dialogs[-1]:
                observations.append((modal.isVisible(), modal.isEnabled()))
                modal.reject()
                assert modal.isVisible(), 'Escape hid the startup explanation'
                modal.close()
                assert modal.isVisible(), 'Close hid the startup explanation'
                pulse.set()
        timer.timeout.connect(tick)
        timer.start(5)
        def work(progress):
            assert threading.get_ident() != main_thread
            assert pulse.wait(3), 'Qt stopped processing events during preparation'
            progress('database')
            return {'files_ms': 1, 'database_ms': 2}
        assert ui._run_preparation(window, work) == {'files_ms': 1, 'database_ms': 2}
        timer.stop()
        assert observations and all(visible and enabled for visible, enabled in observations)
        app.processEvents()
        assert QApplication.activeModalWidget() is None
        assert not window.isVisible(), 'Preparation changed the main window visibility'

        def fail(progress):
            raise OSError('synthetic upgrade failure')
        try:
            ui._run_preparation(window, fail)
        except OSError as error:
            assert str(error) == 'synthetic upgrade failure'
        else:
            raise AssertionError('failure was hidden')
        app.processEvents()
        assert QApplication.activeModalWidget() is None
        assert window.isEnabled()
        for locale in ('en', 'hr', 'zh-Hans'):
            initialize_language(locale)
            dialog = build(window)
            font = dialog.font()
            font.setPointSizeF(font.pointSizeF() * 1.5)
            dialog.setFont(font)
            dialog.set_stage('database')
            dialog.show()
            app.processEvents()
            for label in dialog.findChildren(QLabel):
                assert label.height() >= label.heightForWidth(label.width()), (locale, label.text())
            dialog.dispose()
            app.processEvents()
        # Forced profile/application teardown must retire queued worker updates.
        release = threading.Event()
        def retired_work(progress):
            assert release.wait(3)
            progress('database')
            return {}
        QTimer.singleShot(20, lambda: dialogs[-1].accept())
        try:
            ui._run_preparation(window, retired_work)
        except CancelledError:
            pass
        else:
            raise AssertionError('unfinished preparation was treated as ready')
        finally:
            release.set()
        window.taskman._no_collection_executor.shutdown(wait=True)
        window.taskman._collection_executor.shutdown(wait=True)
        app.processEvents()
        assert QApplication.activeModalWidget() is None
        print('responsive preparation, failure cleanup, and hidden-parent visibility verified')
    ''')
    result = subprocess.run([sys.executable, "-c", program], cwd=root,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": root},
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
