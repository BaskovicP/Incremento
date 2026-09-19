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
