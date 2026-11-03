"""Composition-root contract without loading an Anki profile."""
import ast
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def _opening_adapter(kind):
    source = (ROOT / '__init__.py').read_text()
    function = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.FunctionDef) and node.name == '_open_writing_card')
    class Note(dict):
        def note_type(self):
            return {'name': kind}
    note = Note(Title='Synthetic writing', Markdown_File='writing/synthetic.md')
    opened = []
    namespace = {
        'mw': SimpleNamespace(col=SimpleNamespace(
            get_card=lambda cid: SimpleNamespace(id=cid, nid=1), get_note=lambda nid: note)),
        'WRITING_NOTE_TYPE': 'Incremento Writing', 'WRITING_FILE_FIELD': 'Markdown_File',
        '_writing_dock_mod': SimpleNamespace(show_writing_in_dock=lambda *args, **kw: opened.append((args, kw))),
        '_last_opened_writing_cid': None,
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), '__init__.py', 'exec'), namespace)
    return namespace, opened


def test_opening_writing_beside_forwards_pin_without_starting_a_review():
    namespace, opened = _opening_adapter('Incremento Writing')
    assert namespace['_open_writing_card'](77, keep_open=True)
    assert opened == [((77, 'Synthetic writing', 'writing/synthetic.md'), {'keep_open': True})]
    assert namespace['_last_opened_writing_cid'] == 77


def test_a_changed_note_type_is_not_opened_as_writing():
    namespace, opened = _opening_adapter('Basic')
    assert namespace['_open_writing_card'](77, keep_open=True) is False
    assert opened == []
    assert namespace['_last_opened_writing_cid'] is None


def test_workspace_menu_and_profile_teardown_are_registered():
    source = (ROOT / '__init__.py').read_text()
    assert 'add_workspace_menu(_menu, _workspace_layouts, _open_writing_beside, open_pdf=_open_pdf_workspace_window)' in source
    assert 'gui_hooks.profile_will_close.append(_reset_writing_workspace)' in source
    nodes = {node.name: ast.get_source_segment(source, node) for node in ast.parse(source).body
             if isinstance(node, ast.FunctionDef)}
    assert '_writing_dock_mod.reset_for_profile_switch()' in nodes['_reset_writing_workspace']
    assert nodes['_on_profile_did_open'].index('_reset_writing_workspace()') < nodes['_on_profile_did_open'].index('_paths.set_active_profile(profile)')


def test_mcp_editor_guard_includes_inactive_writing_tabs():
    tree = ast.parse((ROOT / '__init__.py').read_text())
    controller = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == '_mcp_controller' for target in node.targets))
    callback = next(keyword.value for keyword in controller.keywords if keyword.arg == 'open_writing_cards')
    namespace = {'_writing_dock_mod': SimpleNamespace(open_writing_card_ids=lambda: [11, 22],
                                                    current_writing_card_id=lambda: 22)}
    value = eval(compile(ast.Expression(callback), '<MCP writing guard>', 'eval'), namespace)
    assert value() == [11, 22]


def test_new_writing_tab_opens_the_new_card_in_the_existing_workspace():
    tree = ast.parse((ROOT / '__init__.py').read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_new_writing_tab')
    opened = []
    namespace = {'addWritingFunction': lambda: 73,
                 '_open_writing_card': lambda *args, **kwargs: opened.append((args, kwargs))}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<new writing tab>', 'exec'), namespace)
    namespace['_new_writing_tab']()
    assert opened == [((73,), {'keep_open': True})]
