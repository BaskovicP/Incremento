"""Profile isolation and Settings failure safety for imported UI translations."""
import ast
import copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend import i18n, language_packs


def root_function(name, namespace):
    path = Path(__file__).parents[1] / '__init__.py'
    tree = ast.parse(path.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace[name]


def pack(text='Fertig'):
    return {'version': 1, 'locale': 'de', 'name': 'Deutsch', 'translations': {
        'addon': {'settings_done': text}, 'reader': {}, 'extension': {}}}


@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('failure_stage', ['config', 'after_pack'])
def test_config_failure_restores_previous_pack_or_removes_new_import(tmp_path, existing, failure_stage):
    if existing:
        language_packs.save_pack(str(tmp_path), 'A', pack('Alt'))
    def fail(*args):
        raise OSError('synthetic config failure')
    save_calls = []
    def save_pack(*args):
        language_packs.save_pack(*args)
        save_calls.append(True)
        if failure_stage == 'after_pack' and len(save_calls) == 1:
            raise OSError('synthetic directory fsync failure')
    persistence = SimpleNamespace(load_pack=language_packs.load_pack, save_pack=save_pack,
                                  delete_pack=language_packs.delete_pack)
    namespace = {'_language_packs': persistence, '_ADDON_DIR': str(tmp_path),
                 '_save_addon_config': fail, 'mw': SimpleNamespace(addonManager=object())}
    save = root_function('_save_settings_with_language_pack', namespace)
    with pytest.raises(OSError):
        save({'ui_language': 'custom:de'}, pack(), 'A')
    assert language_packs.load_pack(str(tmp_path), 'A', 'de') == (pack('Alt') if existing else None)
    assert language_packs.list_packs(str(tmp_path), 'B') == []


def test_successful_import_persists_pack_and_choice_without_changing_active_language(tmp_path):
    writes = []
    namespace = {'_language_packs': language_packs, '_ADDON_DIR': str(tmp_path),
                 '_save_addon_config': lambda *args: writes.append(copy.deepcopy(args[-1])),
                 'mw': SimpleNamespace(addonManager=object())}
    i18n.initialize_language('en')
    try:
        root_function('_save_settings_with_language_pack', namespace)({'ui_language': 'custom:de'}, pack(), 'A')
        assert writes == [{'ui_language': 'custom:de'}]
        assert language_packs.load_pack(str(tmp_path), 'A', 'de') == pack()
        assert i18n.t('settings_done') == 'Done'
    finally:
        i18n.initialize_language('en')


def test_profile_transition_uses_frozen_preference_and_clears_absent_profile_pack(tmp_path):
    language_packs.save_pack(str(tmp_path), 'A', pack())
    updates = []
    namespace = {'_language_packs': language_packs, '_ADDON_DIR': str(tmp_path),
                 '_startup_ui_language_choice': 'custom:de',
                 '_initialize_language': i18n.initialize_language,
                 '_anki_language': SimpleNamespace(current_lang='hr'),
                 '_retranslate_incremento_menu': lambda: updates.append(i18n.t('settings_done'))}
    activate = root_function('_activate_profile_language', namespace)
    try:
        activate('A')
        assert i18n.t('settings_done') == 'Fertig'
        activate('B')
        assert i18n.t('settings_done') == 'Done'
        activate('A')
        activate(None)
        assert i18n.t('settings_done') == 'Done'
        assert updates == ['Fertig', 'Done', 'Fertig', 'Done']
    finally:
        i18n.initialize_language('en')


def test_settings_profile_switch_rejects_the_import_before_any_persistence(tmp_path):
    import builtins

    path = Path(__file__).parents[1] / '__init__.py'
    function = next(node for node in ast.parse(path.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name == 'openSettingsFunction')
    namespace = {node.id: Mock(name=node.id) for node in ast.walk(function) if isinstance(node, ast.Name)}
    namespace.update(vars(builtins))
    profiles = iter(['A', 'B'])
    def open_dialog(_shortcuts, **kwargs):
        assert kwargs['language_pack_context'] == (str(tmp_path), 'A')
        return SimpleNamespace(exec=lambda: True)
    namespace.update({
        '_current_profile_name': lambda: next(profiles), '_ADDON_DIR': str(tmp_path),
        '_load_addon_config': lambda *_: {}, 'copy': copy,
        'mw': SimpleNamespace(addonManager=object(), col=SimpleNamespace(models=SimpleNamespace(all_names_and_ids=lambda: []))),
        'IncrementoSettingsDialog': open_dialog, '_t': i18n.t,
    })
    root_function('openSettingsFunction', namespace)()
    namespace['_save_settings_with_language_pack'].assert_not_called()
    namespace['showInfo'].assert_called_once_with(i18n.t('settings_language_profile_changed'))
