"""Anki operation dispatch and a native, profile-bound MCP connection dialog."""

from pathlib import Path
import threading

try:
    from ..backend.mcp_server import McpServer, load_or_create_token
    from ..backend.mcp_service import (
        McpService,
        ToolError,
        COLLECTION_WRITE_TOOLS,
        NATIVE_TOOLS,
        WRITE_TOOLS,
        tool_arguments,
    )
    from ..backend.mcp_undo import UndoError, UndoHistory
    from ..backend.mcp_install import connection_snippets, export_claude_bundle
    from ..backend.paths import get_active_profile
except ImportError:
    from mcp_server import McpServer, load_or_create_token
    from mcp_service import McpService, ToolError, COLLECTION_WRITE_TOOLS, NATIVE_TOOLS, WRITE_TOOLS, tool_arguments
    from mcp_undo import UndoError, UndoHistory
    from mcp_install import connection_snippets, export_claude_bundle
    from paths import get_active_profile


class McpController:
    def __init__(self, mw, addon_dir, load_config, save_config, *, actions=lambda: [], open_writing_cards=lambda: []):
        self.mw, self.addon_dir = mw, addon_dir
        self.load_config, self.save_config = load_config, save_config
        self.server = None
        self.profile, self.collection, self.config = None, None, {}
        self.error = False
        self.history = UndoHistory()
        self.actions = actions
        self.open_writing_cards = open_writing_cards
        self.job_running = False
        try:
            from .mcp_runtime import McpRuntime
        except ImportError:
            from mcp_runtime import McpRuntime
        self.runtime = McpRuntime(self)

    def configure(self, *_args):
        cfg = self.load_config()
        if not cfg.get("mcp_enabled", False) or self.mw.col is None:
            self.stop()
            self.error = False
            return
        profile = get_active_profile()
        if (
            self.server
            and not self.server.closed.is_set()
            and self.collection is self.mw.col
            and self.profile == profile
        ):
            self.server.allow_writes = bool(cfg.get("mcp_allow_writes", False))
            self.config = dict(cfg)
            return
        self.stop()
        try:
            if self.profile != profile or self.collection is not self.mw.col:
                self.history = UndoHistory(addon_dir=self.addon_dir, profile=profile)
        except (OSError, UndoError):
            self.error = True
            return
        self.profile, self.collection, self.config = profile, self.mw.col, dict(cfg)
        try:
            server = McpServer(
                load_or_create_token(self.addon_dir, profile),
                self.dispatch,
                allow_writes=bool(cfg.get("mcp_allow_writes", False)),
            )
            server.start()
            self.server = server
            self.error = False
        except (OSError, ValueError):
            self.error = True

    def stop(self, *_args):
        server, self.server = self.server, None
        self.job_running = False
        self.runtime.effects.clear()
        if server:
            server.closed.set()
            server.stop()

    def close_profile(self, *_args):
        self.stop()
        self.history = UndoHistory()
        self.runtime.effects.clear()

    def start_job(self, job_id):
        from aqt.operations import CollectionOp

        server, profile, col = self.server, self.profile, self.collection

        def current():
            return self.server is server and server is not None and not server.closed.is_set() and self.mw.col is col

        if not current():
            return
        self.job_running = True
        svc = McpService(
            self.addon_dir,
            profile,
            server.context_id,
            config=dict(self.config),
            alive=current,
            history=self.history,
            runtime=lambda action, parameters: self.runtime.call(action, parameters, valid=current),
            save_config=lambda updated: self.runtime.call("save_settings", updated, valid=current),
        )

        def work(operation_col):
            if not current() or operation_col is not col:
                raise ToolError("Profile changed before the queued job started.")
            if not server.allow_writes:
                raise ToolError("Write access was revoked.")
            result = svc.execute_operation_job(operation_col, job_id)
            if result is None:
                from anki.collection import OpChanges

                return OpChanges()
            return result

        def finished(*_):
            if current():
                self.job_running = False
                self.runtime.flush()

        def prepared(future):
            try:
                future.result()
                if current():
                    CollectionOp(parent=self.mw, op=work).success(finished).failure(finished).run_in_background()
            except Exception:
                finished()

        # Download/encode into private bounded assets without occupying Anki's
        # collection queue. The publication phase rechecks targets and captures
        # a fresh before-state inside the serialized collection operation.
        self.mw.taskman.run_in_background(lambda: svc.prepare_operation_job(job_id), prepared, uses_collection=False)

    def dispatch(self, name, args, cancelled, *, timeout=55):
        server, col, profile, config = self.server, self.collection, self.profile, dict(self.config)
        done, result = threading.Event(), {}

        def current():
            return (
                server is not None
                and self.server is server
                and not server.closed.is_set()
                and not cancelled.is_set()
                and self.mw.col is col
            )

        def finish(value=None, error=None):
            if error is not None:
                result["error"] = error
            else:
                result["value"] = value
            done.set()

        def launch():
            if not current():
                finish(error=ToolError("Connection closed or profile changed."))
                return
            try:
                values = tool_arguments(name, args, server.context_id)
                if self.job_running and name in WRITE_TOOLS:
                    raise ToolError("An MCP job is running. Poll get_background_tasks before another write.")
                config["_mcp_open_writing_card_ids"] = list(self.open_writing_cards())
                if name in NATIVE_TOOLS:
                    finish({"items": self.actions(), "execution": "discovery_only"})
                    return
                collection_write = name in COLLECTION_WRITE_TOOLS or (
                    name == "undo_change" and self.history.get(values["undo_id"])["collection"]
                )
                session_start = False
                if name == "apply_advanced_plan":
                    proposal = self.history.plans.get(values["plan_id"], {}).get("payload", {})
                    session_start = (
                        proposal.get("operation") == "native_workflow"
                        and proposal.get("arguments", {}).get("action") == "session_start"
                    )
            except UndoError as error:
                finish(error=ToolError(str(error)))
                return
            except Exception as error:
                finish(error=error)
                return
            from aqt.operations import CollectionOp, QueryOp

            svc = McpService(
                self.addon_dir,
                profile,
                server.context_id,
                config=config,
                alive=current,
                history=self.history,
                runtime=lambda action, parameters: self.runtime.call(action, parameters, valid=current),
                save_config=lambda updated: self.runtime.call("save_settings", updated, valid=current),
            )
            if name == "get_background_tasks":
                finish(svc._get_background_tasks(col))
                return
            payload = {}

            def work(operation_col):
                if operation_col is not col or not current():
                    raise ToolError("Profile changed before the operation started.")
                if name in WRITE_TOOLS and not server.allow_writes:
                    raise ToolError("Write access was revoked.")
                config["_mcp_open_writing_card_ids"] = list(self.open_writing_cards())
                value = svc.call(operation_col, name, args)
                if collection_write:
                    payload["value"] = value
                    # CollectionOp requires OpChanges even for an idempotent
                    # no-op; an empty changes object creates no Undo entry.
                    if svc.changes is None:
                        from anki.collection import OpChanges

                        return OpChanges()
                    return svc.changes
                return value

            if collection_write:

                def completed(_):
                    self.runtime.flush()
                    finish(payload["value"])

                if session_start:
                    try:
                        from ..backend.session import _run_collection_mutation_without_progress
                    except ImportError:
                        from backend.session import _run_collection_mutation_without_progress
                    _run_collection_mutation_without_progress(
                        parent=self.mw, op=work, success=completed, failure=lambda error: finish(error=error)
                    )
                    return
                op = CollectionOp(parent=self.mw, op=work).success(completed)
            else:

                def queried(value):
                    self.runtime.flush()
                    finish(value)

                op = QueryOp(parent=self.mw, op=work, success=queried)
            op.failure(lambda error: finish(error=error)).run_in_background()

        self.mw.taskman.run_on_main(launch)
        if not done.wait(timeout):
            cancelled.set()
            raise TimeoutError("MCP operation timed out.")
        if "error" in result:
            raise result["error"]
        return result["value"]


def show_mcp_connections(controller, parent=None):
    from aqt.qt import (
        QApplication,
        QCheckBox,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QLabel,
        QLineEdit,
        QPlainTextEdit,
        QPushButton,
        QTabWidget,
        QVBoxLayout,
        QWidget,
        Qt,
    )

    try:
        from ..backend.i18n import t
    except ImportError:
        from i18n import t

    dialog = QDialog(parent)
    dialog.setWindowTitle(t("mcp_connections_title"))
    dialog.resize(740, 660)
    layout = QVBoxLayout(dialog)
    hint = QLabel(t("mcp_connections_hint"))
    hint.setWordWrap(True)
    layout.addWidget(hint)
    cfg = controller.load_config()
    enabled = QCheckBox(t("mcp_connections_enable"))
    enabled.setChecked(bool(cfg.get("mcp_enabled", False)))
    layout.addWidget(enabled)
    writes = QCheckBox(t("mcp_connections_writes"))
    writes.setChecked(bool(cfg.get("mcp_allow_writes", False)))
    layout.addWidget(writes)
    apply = QPushButton(t("mcp_connections_apply"))
    layout.addWidget(apply)
    status = QLabel()
    status.setTextFormat(Qt.TextFormat.PlainText)
    status.setWordWrap(True)
    layout.addWidget(status)
    clients = QTabWidget()
    layout.addWidget(clients, 1)
    captured_profile = get_active_profile()
    captured_col = controller.mw.col

    def copy_text(value):
        if controller.mw.col is not captured_col or get_active_profile() != captured_profile:
            dialog.reject()
            return
        if controller.server is None or controller.server.closed.is_set():
            refresh()
            return
        QApplication.clipboard().setText(value)

    def code_tab(name, steps_key, copy_key, content_key):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        steps = QLabel(t(steps_key))
        steps.setWordWrap(True)
        page_layout.addWidget(steps)
        content = QPlainTextEdit()
        content.setReadOnly(True)
        content.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        content.setAccessibleName(t(content_key))
        page_layout.addWidget(content, 1)
        copy = QPushButton(t(copy_key))
        copy.clicked.connect(lambda: copy_text(content.toPlainText()))
        page_layout.addWidget(copy)
        clients.addTab(page, name)
        return content, copy

    codex_config, copy_codex = code_tab(
        "Codex", "mcp_connections_codex_steps", "mcp_connections_copy_setup_prompt", "mcp_connections_codex_prompt"
    )
    claude_command, copy_claude_code = code_tab(
        "Claude Code",
        "mcp_connections_claude_code_steps",
        "mcp_connections_copy_setup_prompt",
        "mcp_connections_claude_code_prompt",
    )
    desktop = QWidget()
    desktop_layout = QVBoxLayout(desktop)
    desktop_steps = QLabel(t("mcp_connections_claude_desktop_steps"))
    desktop_steps.setWordWrap(True)
    desktop_layout.addWidget(desktop_steps)
    token = QLineEdit()
    token.setReadOnly(True)
    token.setEchoMode(QLineEdit.EchoMode.Password)
    token.setAccessibleName(t("mcp_connections_token"))
    desktop_layout.addWidget(token)
    copy = QPushButton(t("mcp_connections_copy_token"))
    copy.clicked.connect(lambda: copy_text(token.text()))
    desktop_layout.addWidget(copy)
    export = QPushButton(t("mcp_connections_export"))
    desktop_layout.addWidget(export)
    desktop_layout.addStretch(1)
    clients.addTab(desktop, "Claude Desktop")
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    def refresh():
        live = controller.server
        active = live is not None and not live.closed.is_set()
        token.setText(live.token if active else "")
        copy.setEnabled(active)
        copy_codex.setEnabled(active)
        copy_claude_code.setEnabled(active)
        export.setEnabled(active)
        if active:
            values = connection_snippets(live.token)
            codex_config.setPlainText(values["codex_prompt"])
            claude_command.setPlainText(values["claude_code_prompt"])
        else:
            codex_config.clear()
            claude_command.clear()
        status.setText(
            t("mcp_connections_failed")
            if controller.error
            else t("mcp_connections_ready")
            if active
            else t("mcp_connections_disabled")
        )

    def save():
        if controller.mw.col is not captured_col or get_active_profile() != captured_profile:
            dialog.reject()
            return
        updated = controller.load_config()
        updated.update(mcp_enabled=enabled.isChecked(), mcp_allow_writes=writes.isChecked())
        try:
            controller.save_config(updated)
            controller.configure()
            refresh()
        except (OSError, ValueError):
            status.setText(t("mcp_connections_failed"))

    def save_bundle():
        if controller.mw.col is not captured_col or get_active_profile() != captured_profile:
            dialog.reject()
            return
        filename, _ = QFileDialog.getSaveFileName(
            dialog, t("mcp_connections_export"), "incremento.mcpb", t("mcp_connections_bundle_filter")
        )
        if not filename:
            return
        if not filename.lower().endswith(".mcpb"):
            filename += ".mcpb"
        try:
            export_claude_bundle(Path(controller.addon_dir) / "web" / "mcp", filename)
            status.setText(t("mcp_connections_exported"))
        except (OSError, ValueError):
            status.setText(t("mcp_connections_failed"))

    apply.clicked.connect(save)
    export.clicked.connect(save_bundle)
    refresh()
    dialog.exec()
