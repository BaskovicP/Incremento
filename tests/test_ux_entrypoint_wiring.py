import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_command_palette_has_a_default_shortcut_and_menu_wiring():
    settings_source = (ROOT / "frontend" / "settings_dialog.py").read_text(
        encoding="utf-8"
    )
    entrypoint = (ROOT / "__init__.py").read_text(encoding="utf-8")

    assert '"id": "command_palette"' in settings_source
    assert '"default": "Ctrl+K"' in settings_source
    assert '_register_shortcut_action("command_palette"' in entrypoint
    assert 'QAction("Command Palette…"' in entrypoint


def test_versioned_onboarding_is_wired_to_first_run_and_manual_reopen():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    entrypoint = (ROOT / "__init__.py").read_text(encoding="utf-8")

    assert config["onboarding_completed_version"] == 0
    assert "_schedule_incremento_onboarding" in entrypoint
    assert 'QAction("Getting Started…"' in entrypoint


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
