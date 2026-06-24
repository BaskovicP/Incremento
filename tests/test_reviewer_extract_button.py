import importlib.util
import os


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(
        name,
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", relpath)),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_button = _load("_incremento_reviewer_extract_button", "frontend/reviewer_extract_button.py")

build_reviewer_extract_button_js = _button.build_reviewer_extract_button_js


def test_build_reviewer_extract_button_js_includes_accessible_contrast_styles():
    js = build_reviewer_extract_button_js("Alt+X")

    assert "incremento-reviewer-extract-button" in js
    assert "incremento-reviewer-extract-button-style" in js
    assert '"Alt+X"' in js
    assert "linear-gradient(180deg, rgba(44, 50, 62, 0.94), rgba(24, 28, 36, 0.97))" in js
    assert "#${buttonId}:disabled" in js
    assert "opacity: 1 !important;" in js
    assert 'pycmd("incremento_extract_card")' in js


def test_build_reviewer_extract_button_js_handles_missing_shortcut():
    js = build_reviewer_extract_button_js("")

    assert 'var shortcutText = "";' in js
    assert '"Extract selected content into a new card"' in js
    assert "incremento-reviewer-extract-cell" in js


def test_build_reviewer_extract_button_js_targets_reviewer_button_row():
    js = build_reviewer_extract_button_js("Alt+X")

    assert 'document.getElementById("ansbut")' in js
    assert 'document.querySelector(\'button[data-ease]\')' in js
    assert 'document.querySelectorAll("table tr")' in js


def test_build_reviewer_extract_button_js_appends_after_answer_buttons():
    js = build_reviewer_extract_button_js("Alt+X")

    assert "row.appendChild(cell);" in js
    assert "row.insertBefore(cell" not in js
