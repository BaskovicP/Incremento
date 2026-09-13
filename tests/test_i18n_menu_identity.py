"""Menu reattachment must use stable QAction identity in every language."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


def _root_function(name, namespace):
    path = Path(__file__).parents[1] / "__init__.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


@pytest.mark.parametrize("label", ["Settings", "Postavke", "设置"])
def test_settings_action_is_not_duplicated_when_label_is_translated(label):
    action = SimpleNamespace(text=lambda: label, objectName=lambda: "incremento_open_settings")
    namespace = {"_menu": SimpleNamespace(actions=lambda: [action])}
    _root_function("_ensure_settings_menu_action", namespace)()


def test_main_menu_is_found_by_identity_with_a_changed_display_name():
    menu = object()
    action = SimpleNamespace(text=lambda: "Incremento 菜单", objectName=lambda: "incremento_menu", menu=lambda: menu)
    menubar = SimpleNamespace(actions=lambda: [action], update=lambda: None)
    namespace = {"mw": SimpleNamespace(menuBar=lambda: menubar)}
    _root_function("_build_incremento_menu", namespace)()
    assert namespace["_menu"] is menu


def test_profile_language_refresh_relabels_nested_actions_without_replacing_them():
    class Action:
        def __init__(self, key, menu=None):
            self.key, self.child, self.label = key, menu, 'before'
            self.checked = True
            self.shortcut = 'Alt+S'

        def property(self, name):
            assert name == 'incremento_translation_key'
            return self.key

        def setText(self, value):
            self.label = value

        def menu(self):
            return self.child

    leaf = Action('root_menu_settings')
    child_action = Action('root_menu_utils')
    child = SimpleNamespace(menuAction=lambda: child_action, actions=lambda: [leaf])
    child_action.child = child
    parent_action = Action('root_menu_incremento')
    menu = SimpleNamespace(menuAction=lambda: parent_action, actions=lambda: [child_action])
    translated = {'root_menu_incremento': 'Mein Menü', 'root_menu_utils': 'Werkzeuge', 'root_menu_settings': 'Einstellungen'}
    _root_function('_retranslate_incremento_menu', {'_menu': menu, '_t': translated.__getitem__})()
    assert parent_action.label == 'Mein Menü'
    assert child_action.label == 'Werkzeuge'
    assert child.actions() == [leaf]
    assert (leaf.label, leaf.checked, leaf.shortcut) == ('Einstellungen', True, 'Alt+S')
