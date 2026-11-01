"""Read-only discovery of the real Incremento menu and shortcut registry.

Actions without a data-level undo adapter remain discoverable, never executable
through a generic trigger/eval tool. The native UI retains its consent flows.
"""


def describe_actions(menu, shortcut_actions):
    result, seen, menus = [], set(), set()

    def add(action, fallback=None):
        if id(action) in seen or len(result) >= 500:
            return
        seen.add(id(action))
        key = action.property("incremento_translation_key") if hasattr(action, "property") else None
        key = key or (action.objectName() if hasattr(action, "objectName") else None) or fallback
        label = action.text().replace("&", "") if hasattr(action, "text") else str(key or "")
        if not key or not label:
            return
        result.append({"action_id": str(key), "label": str(label), "ui_enabled": bool(action.isEnabled()),
            "mcp_executable": False, "reason": "Use a dedicated data tool or the native UI; generic action triggering has no undo adapter."})

    def visit(current):
        if current is None or id(current) in menus:
            return
        menus.add(id(current))
        for action in current.actions():
            if action.isSeparator():
                continue
            submenu = action.menu()
            if submenu is not None:
                visit(submenu)
            else:
                add(action)

    visit(menu)
    for key, targets in shortcut_actions.items():
        for action in targets:
            add(action, key)
    return result
