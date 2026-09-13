"""Empty-review messages follow the active language without touching collections."""
import ast
from pathlib import Path

from backend.i18n import Translator


def _empty_review(locale):
    path = Path(__file__).resolve().parents[1] / 'backend/session.py'
    function = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'start_explicit_review')
    messages = []
    namespace = {
        'INCREMENTO_DECK': 'Incremento Session',
        '_normalize_explicit_review_ids': lambda ids: ids,
        '_emit_diagnostic_event': lambda *args, **kwargs: None,
        'showInfo': messages.append,
        't': Translator(locale).t,
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace['start_explicit_review'], messages


def test_empty_review_uses_current_language_and_explicit_silence_remains_silent():
    review, messages = _empty_review('hr')
    assert review([]) is False
    assert messages == ['Nema kartica dostupnih za ponavljanje.']
    messages.clear()
    assert review([], empty_message='') is False
    assert messages == []
