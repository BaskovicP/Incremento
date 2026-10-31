"""Connection setup exports only shipped assets and cancels queued work."""

import json
from pathlib import Path
from types import SimpleNamespace
import threading
import sys
import os
import subprocess
from textwrap import dedent
from zipfile import ZipFile

import pytest

from mcp_connections import McpController, connection_snippets, export_claude_bundle


def test_runtime_rechecks_server_generation_inside_queued_main_callback():
    from mcp_runtime import McpRuntime
    from mcp_anki import AnkiToolError

    original = object()
    saved = []
    controller = SimpleNamespace(collection=original, mw=SimpleNamespace(col=original),
                                 save_config=saved.append, config={})
    def queued(callback):
        controller.collection = controller.mw.col = object()
        callback()
    controller.mw.taskman = SimpleNamespace(run_on_main=queued)
    runtime = McpRuntime(controller)
    with pytest.raises(AnkiToolError, match="collection changed"):
        runtime.call("save_settings", {"topic_maximum_interval_days": 99},
                     valid=lambda: controller.collection is original)
    assert saved == []


def test_persisted_settings_remain_journalable_when_a_native_ui_refresh_fails():
    from mcp_runtime import McpRuntime
    from config_service import normalize_config

    stored = {}
    expected = normalize_config({"topic_maximum_interval_days": 99})
    def save(value):
        stored.update(value)
        raise RuntimeError("An already-closed native widget rejected refresh")
    controller = SimpleNamespace(mw=SimpleNamespace(), save_config=save, load_config=lambda: dict(stored), config={})
    McpRuntime(controller)._call("save_settings", expected)
    assert controller.config == expected


def test_job_media_preparation_explicitly_uses_non_collection_executor(tmp_path, monkeypatch):
    submitted = []
    taskman = SimpleNamespace(run_in_background=lambda task, done, *, uses_collection=True: submitted.append(uses_collection))
    mw = SimpleNamespace(col=object(), taskman=taskman)
    controller = McpController(mw, str(tmp_path), lambda: {}, lambda _: None)
    controller.collection, controller.profile = mw.col, "A"
    controller.server = SimpleNamespace(context_id="generation", closed=threading.Event())
    monkeypatch.setitem(sys.modules, "aqt.operations", SimpleNamespace(CollectionOp=object))
    controller.start_job("owned-job")
    assert submitted == [False]


def test_native_setup_separates_clients_and_copies_complete_setup_prompts():
    script = dedent('''
        import sys
        from pathlib import Path
        from types import SimpleNamespace
        import threading
        sys.path.insert(0, str(Path('backend').resolve()))
        from aqt.qt import QApplication, QCheckBox, QDialog, QLineEdit, QPlainTextEdit, QPushButton, QTabWidget
        import i18n
        i18n.initialize_language('en')
        from frontend.mcp_connections import show_mcp_connections, connection_snippets
        app = QApplication.instance() or QApplication([])
        config = {'mcp_enabled': True, 'mcp_allow_writes': False}
        controller = SimpleNamespace(load_config=lambda: dict(config), error=False,
            server=SimpleNamespace(closed=threading.Event(), token='SYNTHETIC_TOKEN'),
            mw=SimpleNamespace(col=object()), addon_dir=str(Path.cwd()))
        controller.save_config = lambda updated: config.update(updated)
        controller.configure = lambda: setattr(controller, 'server', None)
        values = connection_snippets('SYNTHETIC_TOKEN')
        def inspect(dialog):
            tabs = dialog.findChild(QTabWidget)
            assert tabs is not None, 'Setup must separate the three clients into tabs'
            assert [tabs.tabText(i) for i in range(tabs.count())] == ['Codex', 'Claude Code', 'Claude Desktop']
            copy_buttons = []
            for index, key, label in [(0, 'codex_prompt', 'Copy setup prompt'),
                                      (1, 'claude_code_prompt', 'Copy setup prompt')]:
                tabs.setCurrentIndex(index)
                page = tabs.widget(index)
                editor = page.findChild(QPlainTextEdit)
                assert editor.toPlainText() == values[key]
                button = next(b for b in page.findChildren(QPushButton) if b.text() == label)
                copy_buttons.append(button)
                button.click()
                assert app.clipboard().text() == values[key], 'Copy must include the entire setup prompt'
            tabs.setCurrentIndex(2)
            desktop = tabs.widget(2)
            token = desktop.findChild(QLineEdit)
            assert token.echoMode() == QLineEdit.EchoMode.Password
            button = next(b for b in desktop.findChildren(QPushButton) if b.text() == 'Copy token')
            copy_buttons.append(button)
            button.click()
            assert app.clipboard().text() == 'SYNTHETIC_TOKEN'
            assert not desktop.findChildren(QPlainTextEdit), 'Desktop must not display unrelated CLI configuration'
            enabled = next(b for b in dialog.findChildren(QCheckBox) if b.text() == 'Enable local MCP connections')
            enabled.setChecked(False)
            next(b for b in dialog.findChildren(QPushButton) if b.text() == 'Apply connection settings').click()
            assert all(not b.isEnabled() for b in copy_buttons)
            assert not token.text()
            assert all(not editor.toPlainText() for editor in dialog.findChildren(QPlainTextEdit))
            print('separate client setup and clipboard: ok')
            return 0
        QDialog.exec = inspect
        show_mcp_connections(controller)
    ''')
    result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "separate client setup and clipboard: ok" in result.stdout


def test_copied_setup_prompts_include_execution_instructions_configuration_and_verification():
    values = connection_snippets("SYNTHETIC_TOKEN")
    codex = values["codex_prompt"]
    assert "local file or terminal tools" in codex
    assert "~/.codex/config.toml" in codex
    assert "CODEX_HOME" in codex
    assert "preserve" in codex.lower()
    assert "```toml\n" + values["codex"] + "```" in codex
    assert "get_context" in codex
    assert "local computer access" in codex
    assert values["claude_code_command"] not in codex
    claude = values["claude_code_prompt"]
    assert "run" in claude.lower()
    assert "user" in claude.lower()
    assert values["claude_code_command"] in claude
    assert "get_context" in claude
    assert "local computer access" in claude
    assert "~/.codex/config.toml" not in claude


def test_setup_provides_codex_http_and_claude_credentials_without_shell_interpolation(tmp_path):
    snippets = connection_snippets("secret_token")
    assert 'url = "http://127.0.0.1:8767/mcp"' in snippets["codex"]
    assert 'Authorization = "Bearer secret_token"' in snippets["codex"]
    claude = json.loads(snippets["claude_code"])
    assert claude["mcpServers"]["incremento"]["headers"]["Authorization"] == "Bearer secret_token"
    source = Path(__file__).resolve().parents[1] / "web" / "mcp"
    bundle = tmp_path / "incremento.mcpb"
    export_claude_bundle(source, bundle)
    with ZipFile(bundle) as archive:
        assert set(archive.namelist()) == {"manifest.json", "incremento.mjs", "LICENSE"}
        assert archive.read("LICENSE") == (source.parents[1] / "LICENSE").read_bytes()
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["server"]["type"] == "node"
        assert manifest["user_config"]["token"]["sensitive"] is True
        assert b"secret_token" not in archive.read("manifest.json")
    with pytest.raises((ValueError, FileExistsError)):
        export_claude_bundle(source, bundle)


def test_timed_out_request_cannot_execute_when_qt_eventually_drains(tmp_path):
    queued = []
    mw = SimpleNamespace(col=object(), taskman=SimpleNamespace(run_on_main=queued.append))
    controller = McpController(mw, str(tmp_path), lambda: {}, lambda cfg: None)
    server = SimpleNamespace(closed=threading.Event(), context_id="generation")
    controller.server = server
    controller.profile = "A"
    controller.collection = mw.col
    controller.config = {}
    cancelled = threading.Event()
    with pytest.raises(TimeoutError):
        controller.dispatch("get_context", {}, cancelled, timeout=0)
    assert cancelled.is_set()
    queued[0]()  # No QueryOp should be launched after its request timed out.


def test_profile_close_revokes_the_server_before_any_late_callback(tmp_path):
    mw = SimpleNamespace(col=object())
    stopped = []
    controller = McpController(mw, str(tmp_path), lambda: {}, lambda cfg: None)
    server = SimpleNamespace(closed=threading.Event(), stop=lambda: stopped.append(True))
    controller.server = server
    controller.stop()
    assert server.closed.is_set()
    assert controller.server is None
    assert stopped == [True]


def test_closing_the_profile_discards_its_undo_history(tmp_path):
    controller = McpController(SimpleNamespace(col=object()), str(tmp_path), lambda: {}, lambda _: None)
    controller.history.add("example", {}, {"value": 1}, {"value": 2})
    controller.close_profile()
    assert controller.history.items() == []


def test_late_worker_cannot_publish_old_profile_undo_into_the_new_history(tmp_path):
    controller = McpController(SimpleNamespace(col=object()), str(tmp_path), lambda: {}, lambda _: None)
    old_history = controller.history
    controller.close_profile()
    old_history.add("old-profile-change", {}, {"value": 1}, {"value": 2})
    assert controller.history.items() == []


def test_profile_switch_while_waiting_for_collection_queue_never_runs_work(tmp_path, monkeypatch):
    queued, waiting = [], threading.Event()
    operations = []
    def enqueue(callback):
        queued.append(callback)
        waiting.set()
    mw = SimpleNamespace(col=object(), taskman=SimpleNamespace(run_on_main=enqueue))
    controller = McpController(mw, str(tmp_path), lambda: {}, lambda _: None)
    controller.collection = mw.col
    controller.profile = "A"
    controller.server = SimpleNamespace(closed=threading.Event(), context_id="generation", allow_writes=True)
    class Operation:
        def __init__(self, *, parent, op, success=None):
            self.work, self.on_success = op, success
        def success(self, fn):
            self.on_success = fn
            return self
        def failure(self, fn):
            self.on_failure = fn
            return self
        def run_in_background(self):
            operations.append(self)
    with monkeypatch.context() as patch:
        patch.setitem(sys.modules, "aqt.operations", SimpleNamespace(CollectionOp=Operation, QueryOp=Operation))
        errors = []
        def request():
            try:
                controller.dispatch("update_tags", {"context_id": "generation", "note_ids": ["1"],
                    "add": ["topic"], "expected_revisions": {"1": "0"*64}}, threading.Event(), timeout=3)
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=request)
        thread.start()
        assert waiting.wait(1)
        queued[0]()
        mw.col = object()
        try:
            operations[0].work(mw.col)
        except Exception as exc:
            operations[0].on_failure(exc)
        thread.join(1)
        assert not thread.is_alive()
        assert len(errors) == 1
        assert "Profile changed" in str(errors[0])
