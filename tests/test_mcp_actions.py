"""The capability audit reads registered actions without triggering them."""

from types import SimpleNamespace

from mcp_actions import describe_actions


def test_native_actions_are_discoverable_but_not_misrepresented_as_undoable_commands():
    triggered = []
    action = SimpleNamespace(text=lambda: "Restore Full Backup…", isSeparator=lambda: False,
        menu=lambda: None, property=lambda name: "root_menu_restore_full_backup", objectName=lambda: "",
        isEnabled=lambda: True, trigger=lambda: triggered.append(True))
    menu = SimpleNamespace(actions=lambda: [action])
    result = describe_actions(menu, {})
    assert result == [{"action_id": "root_menu_restore_full_backup", "label": "Restore Full Backup…",
        "ui_enabled": True, "mcp_executable": False, "reason": "Use a dedicated data tool or the native UI; generic action triggering has no undo adapter."}]
    assert triggered == []
