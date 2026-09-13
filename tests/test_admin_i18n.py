"""Administrative prompts translate without changing their confirmation protocol."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.i18n import Translator


@pytest.mark.parametrize('answer,unlocks', [('OTKLJUČAJ', False), ('UNLOCK', True)])
def test_database_unlock_phrase_is_stable_in_croatian(answer, unlocks):
    path = Path(__file__).resolve().parents[1] / 'frontend/sqlite_editor_dialog.py'
    tree = ast.parse(path.read_text())
    function = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_unlock_writes')
    prompts, statuses, connections = [], [], []

    def get_text(_parent, title, prompt):
        prompts.append((title, prompt))
        return answer, True

    namespace = {'QInputDialog': SimpleNamespace(getText=get_text), 't': Translator('hr').t}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)
    dialog = SimpleNamespace(
        _read_only=True, _UNLOCK_PHRASE='UNLOCK',
        _sql_status=SimpleNamespace(setText=statuses.append),
        _open_connection=lambda **kwargs: connections.append(kwargs),
        _refresh_header=lambda: None, _refresh_current_view=lambda: None,
    )
    namespace['_unlock_writes'](dialog)
    assert prompts[0][0] == 'Omogući upis u bazu'
    assert 'UNLOCK' in prompts[0][1]
    assert connections == ([{'read_only': False}] if unlocks else [])
    assert statuses == (['Upis u SQL omogućen je za ovu sesiju uređivača.'] if unlocks else ['Omogućivanje upisa je otkazano. Potvrdni izraz ne odgovara.'])
