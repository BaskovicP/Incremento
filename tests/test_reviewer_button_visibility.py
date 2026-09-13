"""The More menu changes reviewer controls without interrupting a card."""

import json
import ast
import copy
from pathlib import Path
import subprocess
from types import SimpleNamespace

from backend.config_service import configured_reviewer_button_visibility

from frontend.reviewer_button_visibility import (
    add_reviewer_button_visibility_menu,
    build_reviewer_button_visibility_js,
    effective_reviewer_button_visibility,
)


class _Action:
    def __init__(self, title):
        self.title = title
        self.checkable = False
        self.checked = None
        self.enabled = True
        self.triggered = self
        self.callback = None

    def setCheckable(self, enabled):
        self.checkable = enabled

    def setChecked(self, enabled):
        self.checked = enabled

    def setEnabled(self, enabled):
        self.enabled = enabled

    def connect(self, callback):
        self.callback = callback


class _Menu:
    def __init__(self):
        self.title = None
        self.actions = []
        self.submenus = []

    def addMenu(self, title):
        submenu = _Menu()
        submenu.title = title
        self.submenus.append(submenu)
        return submenu

    def addAction(self, title):
        action = _Action(title)
        self.actions.append(action)
        return action

    def addSeparator(self):
        self.actions.append("separator")


def test_more_menu_offers_independent_checked_buttons_and_saves_one_choice():
    menu = _Menu()
    changes = []
    visibility = {"done": True, "postpone": False, "extract": True}

    add_reviewer_button_visibility_menu(
        menu, visibility, lambda key, checked: changes.append((key, checked))
    )

    assert len(menu.submenus) == 1
    submenu = menu.submenus[0]
    assert submenu.title == "Review buttons"
    assert [(action.title, action.checkable, action.checked) for action in submenu.actions] == [
        ("Show Done button", True, True),
        ("Show Postpone button", True, False),
        ("Show Extract button", True, True),
    ]
    submenu.actions[1].callback(True)
    assert changes == [("postpone", True)]


def test_hidden_button_slots_reappear_immediately_without_rebuilding_card():
    hidden = build_reviewer_button_visibility_js(
        {"done": False, "postpone": False, "extract": False}
    )
    visible = build_reviewer_button_visibility_js(
        {"done": True, "postpone": True, "extract": True}
    )
    harness = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const [hidden, visible] = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const nodes = new Map();
const document = {
  getElementById: id => nodes.get(id),
  createElement: () => ({remove() { nodes.delete(this.id); }}),
  head: {appendChild(node) { nodes.set(node.id, node); }},
};
const context = vm.createContext({document});
vm.runInContext(hidden, context);
const style = nodes.get('incremento-reviewer-button-visibility');
for (const id of ['incremento-topic-done-cell', 'incremento-topic-postpone-cell', 'incremento-reviewer-extract-cell']) {
  assert.match(style.textContent, new RegExp('#' + id + '\\s*\\{\\s*display:\\s*none'));
}
assert.doesNotMatch(style.textContent, /#ansbut|button\[data-ease\]/);
vm.runInContext(visible, context);
assert.equal(nodes.has('incremento-reviewer-button-visibility'), false);
"""
    result = subprocess.run(
        ["node", "-e", harness], input=json.dumps([hidden, visible]),
        text=True, capture_output=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_group_collapse_restores_individual_button_preferences():
    preferences = {"done": False, "postpone": True, "extract": True}
    assert effective_reviewer_button_visibility(preferences, False) == {
        "done": False, "postpone": False, "extract": False,
    }
    assert effective_reviewer_button_visibility(preferences, True) == preferences
    assert preferences == {"done": False, "postpone": True, "extract": True}


def test_more_menu_offers_group_toggle_and_keeps_individual_preferences():
    menu = _Menu()
    changes = []
    add_reviewer_button_visibility_menu(
        menu, {"done": False, "postpone": True, "extract": True},
        lambda key, checked: changes.append((key, checked)),
        group_visible=False,
        on_group_toggle=lambda checked: changes.append(("group", checked)),
    )
    submenu = menu.submenus[0]
    assert submenu.actions[0].title == "Show review button group"
    assert submenu.actions[0].checked is False
    assert [(action.title, action.checked) for action in submenu.actions[2:]] == [
        ("Show Done button", False),
        ("Show Postpone button", True),
        ("Show Extract button", True),
    ]
    assert all(action.enabled is False for action in submenu.actions[2:])
    submenu.actions[0].callback(True)
    assert changes == [("group", True)]


def test_reviewer_shortcut_toggles_only_group_for_current_profile():
    source = (Path(__file__).resolve().parents[1] / "__init__.py").read_text()
    node = next(item for item in ast.parse(source).body
                if isinstance(item, ast.FunctionDef)
                and item.name == "_toggle_reviewer_button_group")
    reviewer = SimpleNamespace(card=SimpleNamespace(id=42))
    mw = SimpleNamespace(state="review", reviewer=reviewer, addonManager=object())
    config = {"reviewer_button_group_visible": True,
              "reviewer_button_visibility": {"done": False, "postpone": True, "extract": True},
              "future_setting": "keep"}
    writes = []
    updates = []

    def save(_manager, _name, value):
        writes.append(copy.deepcopy(value))
        config.clear()
        config.update(value)

    namespace = {
        "mw": mw,
        "_load_addon_config": lambda *_: copy.deepcopy(config),
        "_save_addon_config": save,
        "configured_reviewer_button_group_visible": lambda cfg: cfg.get("reviewer_button_group_visible", True),
        "_sync_reviewer_button_visibility": updates.append,
        "__name__": "incremento",
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), "__init__.py", "exec"), namespace)
    toggle = namespace[node.name]
    toggle()
    assert writes[-1] == {
        "reviewer_button_group_visible": False,
        "reviewer_button_visibility": {
            "done": False, "postpone": True, "extract": True,
        },
        "future_setting": "keep",
    }
    toggle()
    assert writes[-1]["reviewer_button_group_visible"] is True
    assert updates == [reviewer, reviewer]
    mw.state = "deckBrowser"
    toggle()
    assert len(writes) == 2


def test_more_menu_hook_syncs_visibility_and_postpone_slot_has_stable_id():
    source = (Path(__file__).resolve().parents[1] / "__init__.py").read_text()
    assert 'id="incremento-topic-postpone-cell"' in source
    assert "gui_hooks.reviewer_will_show_context_menu.append(_add_reviewer_button_visibility_menu)" in source
    assert "build_reviewer_button_visibility_js(" in source
    assert "effective_reviewer_button_visibility(" in source


def test_group_shortcut_uses_existing_configurable_action_registration():
    source = (Path(__file__).resolve().parents[1] / "__init__.py").read_text()
    assert 'qconnect(_reviewer_buttons_shortcut.activated, _toggle_reviewer_button_group)' in source
    assert '_register_shortcut_action("toggle_reviewer_buttons", _reviewer_buttons_shortcut)' in source


def test_more_menu_saves_only_selected_button_and_ignores_stale_profile():
    source = (Path(__file__).resolve().parents[1] / "__init__.py").read_text()
    node = next(
        item for item in ast.parse(source).body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_add_reviewer_button_visibility_menu"
    )
    reviewer = SimpleNamespace(card=SimpleNamespace(id=42))
    mw = SimpleNamespace(state="review", reviewer=reviewer, addonManager=object())
    profile = ["Profile A"]
    config = {"reviewer_button_visibility": {
        "done": True, "postpone": True, "extract": True,
    }, "future_setting": "keep"}
    writes = []
    updates = []

    def save(_manager, _name, value):
        writes.append(copy.deepcopy(value))
        config.clear()
        config.update(value)

    namespace = {
        "mw": mw,
        "_active_profile": lambda: profile[0],
        "_load_addon_config": lambda *_: copy.deepcopy(config),
        "_save_addon_config": save,
        "configured_reviewer_button_visibility": configured_reviewer_button_visibility,
        "configured_reviewer_button_group_visible": lambda cfg: cfg.get("reviewer_button_group_visible", True),
        "add_reviewer_button_visibility_menu": add_reviewer_button_visibility_menu,
        "_sync_reviewer_button_visibility": updates.append,
        "__name__": "incremento",
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), "__init__.py", "exec"), namespace)
    menu = _Menu()
    namespace[node.name](reviewer, menu)
    actions = {action.title: action for action in menu.submenus[0].actions if isinstance(action, _Action)}
    actions["Show Done button"].callback(False)
    assert writes == [{"reviewer_button_visibility": {
        "done": False, "postpone": True, "extract": True,
    }, "future_setting": "keep"}]
    assert updates == [reviewer]

    actions["Show review button group"].callback(False)
    assert writes[-1] == {
        "reviewer_button_visibility": {
            "done": False, "postpone": True, "extract": True,
        },
        "reviewer_button_group_visible": False,
        "future_setting": "keep",
    }
    assert updates == [reviewer, reviewer]

    profile[0] = "Profile B"
    actions["Show Postpone button"].callback(False)
    actions["Show review button group"].callback(True)
    assert len(writes) == 2
    assert len(updates) == 2
