import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent


ROOT = Path(__file__).resolve().parents[1]


def test_command_palette_has_a_default_shortcut_and_menu_wiring():
    settings_source = (ROOT / "frontend" / "settings_dialog.py").read_text(
        encoding="utf-8"
    )
    entrypoint = (ROOT / "__init__.py").read_text(encoding="utf-8")

    assert '"id": "command_palette"' in settings_source
    assert '"default": "Ctrl+K"' in settings_source
    assert '_register_shortcut_action("command_palette"' in entrypoint
    assert 'QAction(_t("root_menu_command_palette")' in entrypoint


def test_versioned_onboarding_is_wired_to_first_run_and_manual_reopen():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    entrypoint = (ROOT / "__init__.py").read_text(encoding="utf-8")

    assert config["onboarding_completed_version"] == 0
    assert "_schedule_incremento_onboarding" in entrypoint
    assert 'QAction(_t("root_menu_getting_started")' in entrypoint


def test_free_study_statistics_answer_tracker_is_registered():
    entrypoint = (ROOT / "__init__.py").read_text(encoding="utf-8")

    assert (
        "gui_hooks.reviewer_did_answer_card.append("
        "_review_time_mod.on_reviewer_card_answered)"
    ) in entrypoint


def test_audio_import_is_exposed_as_a_background_add_content_action():
    entrypoint = (ROOT / "__init__.py").read_text(encoding="utf-8")
    body = entrypoint.split("def addAudioFunction() -> None:", 1)[1].split(
        "def addVideoFunction() -> None:", 1
    )[0]

    assert 'QAction(_t("root_menu_add_audio")' in entrypoint
    assert "QFileDialog.getOpenFileName" in body
    assert "CollectionOp(mw, operation)" in body
    assert "add_audio_card(" in body
    assert 'deck_name="Topics"' in body
    assert 'tags=["topic"]' in body


def test_supermemo_import_is_preflighted_off_thread_and_mutated_in_collection_op():
    entrypoint = (ROOT / "__init__.py").read_text(encoding="utf-8")
    body = entrypoint.split("def importSuperMemoFunction() -> None:", 1)[1].split(
        "def addPdfFunction() -> None:", 1
    )[0]

    assert 'QAction(_t("root_menu_import_supermemo")' in entrypoint
    assert "_utilsMenu.addAction(_importSuperMemoAction)" in entrypoint
    assert "_addContentMenu.addAction(_importSuperMemoAction)" not in entrypoint
    assert "run_in_background(prepare, prepared_done, uses_collection=False)" in body
    assert "CollectionOp(mw, operation)" in body
    assert "import_supermemo_collection(" in body
    assert 'imports_supermemo_non_undoable' in body


def test_pdf_context_rebuild_uses_anki_26_compatible_collection_operation():
    entrypoint = (ROOT / "__init__.py").read_text(encoding="utf-8")
    body = entrypoint.split("def rebuildPdfCardContextsFunction() -> None:", 1)[1].split(
        "def addPdfFunction() -> None:", 1
    )[0]

    assert 'QAction(_t("root_menu_rebuild_pdf_card_contexts")' in entrypoint
    assert "_utilsMenu.addAction(_rebuildPdfCardContextsAction)" in entrypoint
    assert "askUser(" in body
    assert "rebuild_all_pdf_context_cards(" in body
    assert "CollectionOp(mw, operation)" in body
    assert ".with_progress(" not in body
    assert "update.value = completed" in body
    assert "update.max = total" in body
    assert "progress=progress" in body
    assert ".with_backend_progress(progress_update)" in body
    assert ".run_in_background()" in body


def test_collection_operations_do_not_call_query_only_with_progress_api():
    def contains_collection_op(node: ast.AST) -> bool:
        return any(
            isinstance(child, ast.Call)
            and (
                isinstance(child.func, ast.Name)
                and child.func.id == "CollectionOp"
                or isinstance(child.func, ast.Attribute)
                and child.func.attr == "CollectionOp"
            )
            for child in ast.walk(node)
        )

    def assigned_names(node: ast.Assign | ast.AnnAssign) -> set[str]:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return {
            child.id
            for target in targets
            for child in ast.walk(target)
            if isinstance(child, ast.Name)
        }

    runtime_paths = [
        ROOT / "__init__.py",
        *sorted((ROOT / "backend").rglob("*.py")),
        *sorted((ROOT / "frontend").rglob("*.py")),
    ]
    offenders: list[str] = []
    for path in runtime_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        collection_op_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                if value is not None and contains_collection_op(value):
                    collection_op_names.update(assigned_names(node))

        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "with_progress"
            ):
                continue
            receiver = node.func.value
            receiver_names = {
                child.id for child in ast.walk(receiver) if isinstance(child, ast.Name)
            }
            if contains_collection_op(receiver) or receiver_names & collection_op_names:
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")

    assert offenders == []


def test_non_modal_command_and_activity_dialogs_are_shown_exactly_once():
    entrypoint = (ROOT / "__init__.py").read_text(encoding="utf-8")
    palette_body = entrypoint.split("def _open_command_palette()", 1)[1].split(
        "def _open_activity_center()", 1
    )[0]
    activity_body = entrypoint.split("def _open_activity_center()", 1)[1].split(
        "class _ConfiguredShortcutFilter", 1
    )[0]

    for body in (palette_body, activity_body):
        assert body.count("dialog.show()") == 1
        assert body.count("dialog.raise_()") == 1
        assert body.count("dialog.activateWindow()") == 1


def test_full_backup_menu_configures_profile_schedule_and_hooks_only_while_open():
    entrypoint = (ROOT / "__init__.py").read_text(encoding="utf-8")
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    assert config["automatic_backups"] == {}
    assert 'QAction(_t("root_menu_configure_auto_backups")' in entrypoint
    assert 'gui_hooks.profile_did_open.append(_start_automatic_backups)' in entrypoint
    assert 'gui_hooks.profile_will_close.append(_stop_automatic_backups)' in entrypoint
    assert '_start_full_backup(str(path), automatic_policy=policy)' in entrypoint


def test_export_full_backup_action_offers_automatic_backup_configuration():
    entrypoint = (ROOT / "__init__.py").read_text(encoding="utf-8")
    export_body = entrypoint.split("def exportFunction() -> None:", 1)[1].split(
        "_auto_backup_timer:", 1
    )[0]
    assert '_t("root_backup_automatic_button")' in export_body
    assert "configureAutomaticBackupsFunction()" in export_body
    assert '_t("root_backup_export_now")' in export_body


def test_profile_close_waits_for_background_backup_before_unload():
    entrypoint = (ROOT / "__init__.py").read_text(encoding="utf-8")
    assert 'gui_hooks.main_window_did_init.append(_install_close_backup_gate)' in entrypoint
    assert '_prepare_profile_close' in entrypoint
    assert 'QAction(_t("root_menu_configure_auto_backups")' in entrypoint


def test_full_backup_uses_non_modal_activity_status_instead_of_progress_dialog():
    entrypoint = (ROOT / "__init__.py").read_text(encoding="utf-8")
    backup_body = entrypoint.split("def _start_full_backup(", 1)[1].split(
        "def exportSupportBundleFunction()", 1
    )[0]
    assert "start_activity(" in backup_body
    assert "update_activity(" in backup_body
    assert "mw.progress.start(" not in backup_body
    assert "_backup_schedule.backup_staging_directory(" in backup_body
    assert "os.replace(archive_tmp_path, path)" in backup_body


def test_automatic_backup_dialog_exposes_close_trigger():
    source = (ROOT / "frontend" / "automatic_backup_dialog.py").read_text(
        encoding="utf-8"
    )
    assert 't("admin_automatic_backup_back_up_when_this_profile_closes")' in source.replace("'", '"')
    assert '"on_close": self._on_close.isChecked()' in source


def test_automatic_backup_dialog_preserves_user_selected_retention_count():
    script = dedent("""
        import os
        import sys
        import types
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from aqt.qt import QApplication

        package = types.ModuleType("incremento")
        package.__path__ = [os.getcwd()]
        sys.modules["incremento"] = package
        from incremento.frontend.automatic_backup_dialog import AutomaticBackupDialog

        app = QApplication([])
        with TemporaryDirectory() as root:
            dialog = AutomaticBackupDialog(
                "Test", Path(root), {"directory": root, "versions": 5}
            )
            assert dialog._versions.maximum() == 20
            assert dialog._versions.value() == 5
            dialog._versions.setValue(7)
            assert dialog.policy["versions"] == 7
            dialog.close()
    """)
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
