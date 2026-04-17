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


_badge = _load("_incremento_reviewer_priority_badge", "frontend/reviewer_priority_badge.py")

build_reviewer_priority_badge_js = _badge.build_reviewer_priority_badge_js
format_reviewer_a_factor_value = _badge.format_reviewer_a_factor_value
format_reviewer_priority_value = _badge.format_reviewer_priority_value


def test_format_reviewer_priority_value_rounds_and_clamps():
    assert format_reviewer_priority_value(57.6) == "58"
    assert format_reviewer_priority_value(-4) == "0"
    assert format_reviewer_priority_value(140) == "100"


def test_format_reviewer_priority_value_defaults_when_missing():
    assert format_reviewer_priority_value(None) == "50"
    assert format_reviewer_priority_value("not-a-number") == "50"


def test_format_reviewer_a_factor_value_uses_three_decimals():
    assert format_reviewer_a_factor_value(1.2374) == "1.237"
    assert format_reviewer_a_factor_value("2.5") == "2.500"
    assert format_reviewer_a_factor_value(None) == ""


def test_build_reviewer_priority_badge_js_includes_priority_and_topic_a_factor():
    js = build_reviewer_priority_badge_js(57.6, a_factor=1.2374)
    assert "incremento-reviewer-priority-badge" in js
    assert "incremento-reviewer-priority-badge-style" in js
    assert "Priority" in js
    assert "A-Factor" in js
    assert '"58"' in js
    assert '"1.237"' in js
    assert "position: fixed;" in js
    assert 'badge.classList.add("has-a-factor")' in js


def test_build_reviewer_priority_badge_js_keeps_a_factor_hidden_for_items():
    js = build_reviewer_priority_badge_js(57.6)
    assert 'badge.classList.remove("has-a-factor")' in js
    assert '""' in js


def test_build_reviewer_priority_badge_js_can_disable_existing_badge():
    js = build_reviewer_priority_badge_js(None)
    assert "var enabled = false;" in js
    assert "badge.remove();" in js
