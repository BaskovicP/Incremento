import importlib.util
import types
from pathlib import Path


def _load():
    path = Path(__file__).resolve().parents[1] / "frontend" / "reviewer_focus.py"
    spec = importlib.util.spec_from_file_location("_incremento_reviewer_focus", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


reviewer_focus = _load()


class _Timer:
    scheduled = []

    @classmethod
    def singleShot(cls, delay, callback):
        cls.scheduled.append((delay, callback))


def _main_window(focus_calls):
    return types.SimpleNamespace(
        state="review",
        reviewer=types.SimpleNamespace(card=types.SimpleNamespace(id=123)),
        web=types.SimpleNamespace(setFocus=lambda: focus_calls.append("reviewer")),
    )


def test_focus_is_reclaimed_after_the_deferred_question_transition():
    focus_calls = []
    mw = _main_window(focus_calls)
    app = types.SimpleNamespace(
        activeModalWidget=lambda: None,
        activePopupWidget=lambda: None,
        activeWindow=lambda: mw,
    )
    _Timer.scheduled = []

    reviewer_focus.schedule_reviewer_focus_restore(
        mw,
        timer=_Timer,
        application=app,
    )

    assert focus_calls == []
    assert [delay for delay, _callback in _Timer.scheduled] == [0, 50, 150]

    for _delay, callback in _Timer.scheduled:
        callback()

    assert focus_calls == ["reviewer", "reviewer", "reviewer"]


def test_focus_recovery_retries_after_a_reader_dock_steals_focus_late():
    focus_calls = []
    mw = _main_window(focus_calls)
    floating_dock = types.SimpleNamespace(
        parentWidget=lambda: mw,
        inherits=lambda class_name: class_name == "QDockWidget",
    )
    active_window = {"value": mw}
    app = types.SimpleNamespace(
        activeModalWidget=lambda: None,
        activePopupWidget=lambda: None,
        activeWindow=lambda: active_window["value"],
    )
    _Timer.scheduled = []

    reviewer_focus.schedule_reviewer_focus_restore(
        mw,
        timer=_Timer,
        application=app,
    )

    _Timer.scheduled[0][1]()
    active_window["value"] = floating_dock
    _Timer.scheduled[1][1]()

    assert focus_calls == ["reviewer", "reviewer"]


def test_focus_recovery_is_registered_after_both_reviewer_transitions():
    hooks = types.SimpleNamespace(
        reviewer_did_show_question=[],
        reviewer_did_show_answer=[],
    )

    def callback(_card):
        return None

    reviewer_focus.register_reviewer_focus_restore_hooks(hooks, callback)

    assert hooks.reviewer_did_show_question == [callback]
    assert hooks.reviewer_did_show_answer == [callback]


def test_modal_dialog_is_never_displaced_by_focus_recovery():
    focus_calls = []
    mw = _main_window(focus_calls)
    app = types.SimpleNamespace(
        activeModalWidget=lambda: object(),
        activePopupWidget=lambda: None,
        activeWindow=lambda: mw,
    )

    assert reviewer_focus.restore_reviewer_focus(mw, application=app) is False
    assert focus_calls == []


def test_focus_is_not_stolen_outside_review_or_from_another_window():
    focus_calls = []
    mw = _main_window(focus_calls)
    mw.state = "overview"
    assert reviewer_focus.restore_reviewer_focus(mw) is False

    mw.state = "review"
    app = types.SimpleNamespace(
        activeModalWidget=lambda: None,
        activePopupWidget=lambda: None,
        activeWindow=lambda: object(),
    )
    assert reviewer_focus.restore_reviewer_focus(mw, application=app) is False
    assert focus_calls == []


def test_floating_incremento_dock_owned_by_main_window_can_return_focus():
    focus_calls = []
    mw = _main_window(focus_calls)
    floating_dock = types.SimpleNamespace(
        parentWidget=lambda: mw,
        inherits=lambda class_name: class_name == "QDockWidget",
    )
    app = types.SimpleNamespace(
        activeModalWidget=lambda: None,
        activePopupWidget=lambda: None,
        activeWindow=lambda: floating_dock,
    )

    assert reviewer_focus.restore_reviewer_focus(mw, application=app) is True
    assert focus_calls == ["reviewer"]


def test_owned_non_modal_dialog_keeps_focus():
    focus_calls = []
    mw = _main_window(focus_calls)
    child_dialog = types.SimpleNamespace(
        parentWidget=lambda: mw,
        inherits=lambda class_name: class_name == "QDialog",
    )
    app = types.SimpleNamespace(
        activeModalWidget=lambda: None,
        activePopupWidget=lambda: None,
        activeWindow=lambda: child_dialog,
    )

    assert reviewer_focus.restore_reviewer_focus(mw, application=app) is False
    assert focus_calls == []
