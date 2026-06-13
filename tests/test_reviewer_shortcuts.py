import importlib.util
from pathlib import Path


def _load():
    path = Path(__file__).resolve().parents[1] / "frontend" / "reviewer_shortcuts.py"
    spec = importlib.util.spec_from_file_location(
        "_incremento_reviewer_shortcuts", path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


reviewer_shortcuts = _load()


def test_question_state_keeps_space_shortcut_even_if_hidden_answer_key_matches():
    def _on_enter():
        return None

    shortcuts = [("Space", _on_enter), ("4", lambda: None)]
    filtered = reviewer_shortcuts.filter_reviewer_shortcuts(
        shortcuts,
        state="question",
        hidden_answer_keys={"Space", "4"},
        is_on_enter_callback=lambda callback: callback is _on_enter,
    )

    assert filtered == shortcuts


def test_answer_state_keeps_on_enter_shortcut_but_hides_other_hidden_keys():
    def _on_enter():
        return None

    visible = lambda: None
    hidden = lambda: None
    shortcuts = [("Space", _on_enter), ("2", visible), ("4", hidden)]
    filtered = reviewer_shortcuts.filter_reviewer_shortcuts(
        shortcuts,
        state="answer",
        hidden_answer_keys={"Space", "4"},
        is_on_enter_callback=lambda callback: callback is _on_enter,
    )

    assert filtered == [("Space", _on_enter), ("2", visible)]


def test_answer_state_keeps_space_even_if_callback_shape_is_not_detected():
    shortcuts = [("Space", lambda: None), ("4", lambda: None)]
    filtered = reviewer_shortcuts.filter_reviewer_shortcuts(
        shortcuts,
        state="answer",
        hidden_answer_keys={"Space", "4"},
        is_on_enter_callback=lambda _callback: False,
    )

    assert filtered == [shortcuts[0]]
