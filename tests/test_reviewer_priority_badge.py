import ast
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


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
configured_reviewer_priority_badge_card_types = _badge.configured_reviewer_priority_badge_card_types
should_show_reviewer_priority_badge = _badge.should_show_reviewer_priority_badge
format_reviewer_a_factor_value = _badge.format_reviewer_a_factor_value
format_reviewer_priority_value = _badge.format_reviewer_priority_value
format_reviewer_saved_time_value = _badge.format_reviewer_saved_time_value
get_reviewer_priority_palette = _badge.get_reviewer_priority_palette


def test_badge_visibility_defaults_to_topics_and_items():
    assert configured_reviewer_priority_badge_card_types({}) == {
        "topics": True,
        "items": True,
    }
    assert configured_reviewer_priority_badge_card_types(
        {"reviewer_priority_badge_card_types": {"topics": False}}
    ) == {"topics": False, "items": True}


@pytest.mark.parametrize(
    ("topic_enabled", "item_enabled"),
    [(False, True), (True, False), (False, False)],
)
def test_badge_visibility_uses_existing_topic_classification(topic_enabled, item_enabled):
    config = {
        "reviewer_priority_badge_card_types": {
            "topics": topic_enabled,
            "items": item_enabled,
        }
    }
    assert should_show_reviewer_priority_badge(is_topic=True, config=config) is topic_enabled
    assert should_show_reviewer_priority_badge(is_topic=False, config=config) is item_enabled


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


def test_format_reviewer_saved_time_value_uses_clock_format():
    assert format_reviewer_saved_time_value(83.2) == "1:23"
    assert format_reviewer_saved_time_value(3661) == "1:01:01"
    assert format_reviewer_saved_time_value(None) == ""


def test_build_reviewer_priority_badge_js_includes_priority_and_topic_a_factor():
    js = build_reviewer_priority_badge_js(
        57.6,
        a_factor=1.2374,
        browser_time_seconds=83.2,
        custom_schedule_text="Every 2 days · Minimum cadence",
    )
    assert "incremento-reviewer-priority-badge" in js
    assert "incremento-reviewer-priority-badge-style" in js
    assert "incremento-reviewer-priority-badge-spacer" in js
    assert "Priority" in js
    assert "A-Factor" in js
    assert "Saved" in js
    assert "Schedule" in js
    assert '"58"' in js
    assert '"1.237"' in js
    assert '"1:23"' in js
    assert '"Every 2 days \\u00b7 Minimum cadence"' in js
    assert "position: fixed;" in js
    assert "height: 82px;" in js
    assert "--incremento-priority-accent" in js
    assert "--incremento-priority-soft" in js
    assert 'badge.classList.add("has-a-factor")' in js
    assert 'badge.classList.add("has-browser-time")' in js
    assert 'badge.classList.add("has-schedule")' in js


def test_get_reviewer_priority_palette_respects_priority_direction():
    low_priority_palette = get_reviewer_priority_palette(10, lower_is_more_important=True)
    high_priority_palette = get_reviewer_priority_palette(90, lower_is_more_important=False)

    assert low_priority_palette["accent"] == high_priority_palette["accent"]
    assert low_priority_palette["background"].startswith("#")
    assert low_priority_palette["border"].startswith("#")
    assert low_priority_palette["glow"].startswith("rgba(")


def test_build_reviewer_priority_badge_js_keeps_a_factor_hidden_for_items():
    js = build_reviewer_priority_badge_js(57.6)
    assert 'badge.classList.remove("has-a-factor")' in js
    assert 'badge.classList.remove("has-browser-time")' in js
    assert '""' in js


def test_build_reviewer_priority_badge_js_uses_directional_palette():
    palette = get_reviewer_priority_palette(90, lower_is_more_important=False)
    js = build_reviewer_priority_badge_js(90, lower_is_more_important=False)
    assert palette["accent"] in js
    assert palette["background"] in js


def test_build_reviewer_priority_badge_js_can_disable_existing_badge():
    js = build_reviewer_priority_badge_js(None)
    assert "var enabled = false;" in js
    assert "badge.remove();" in js
    assert "spacer.remove();" in js


def test_reviewer_hides_existing_badge_when_next_card_type_is_disabled():
    path = Path(__file__).resolve().parents[1] / "__init__.py"
    function = next(
        node for node in ast.parse(path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_sync_reviewer_priority_badge"
    )
    scripts: list[str] = []
    fetched_priorities: list[int] = []
    card = SimpleNamespace(id=17, nid=21)
    config = {"reviewer_priority_badge_card_types": {"topics": False, "items": True}}
    namespace = {
        "mw": SimpleNamespace(
            addonManager=None,
            reviewer=SimpleNamespace(card=card, web=SimpleNamespace(eval=scripts.append)),
            col=SimpleNamespace(
                get_note=lambda _nid: SimpleNamespace(mid=1),
                models=SimpleNamespace(get=lambda _mid: {"name": "Basic"}),
            ),
        ),
        "_is_topic_card": lambda _card: False,
        "should_show_reviewer_priority_badge": should_show_reviewer_priority_badge,
        "_load_addon_config": lambda _manager, _package: config,
        "get_priority": lambda _addon_dir, _profile, card_id: (
            fetched_priorities.append(card_id) or 50
        ),
        "get_card_browser_media_ref": lambda *_args: {},
        "get_custom_schedule_rule": lambda *_args: None,
        "_format_custom_schedule_rule": lambda _rule: "",
        "_active_profile": lambda: "TestProfile",
        "_ADDON_DIR": "/tmp/incremento-badge-test",
        "WEB_NOTE_TYPE": "Incremento Web",
        "configured_priority_lower_is_more_important": lambda: True,
        "build_reviewer_priority_badge_js": build_reviewer_priority_badge_js,
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)

    namespace["_sync_reviewer_priority_badge"]()
    assert fetched_priorities == [17]
    assert "var enabled = true;" in scripts[-1]

    namespace["_is_topic_card"] = lambda _card: True
    namespace["_sync_reviewer_priority_badge"]()
    assert fetched_priorities == [17]
    assert "var enabled = false;" in scripts[-1]
    assert "badge.remove();" in scripts[-1]
    assert "spacer.remove();" in scripts[-1]

    namespace["_is_topic_card"] = lambda _card: False
    namespace["_load_addon_config"] = lambda *_args: (_ for _ in ()).throw(
        RuntimeError("config unavailable")
    )
    namespace["_sync_reviewer_priority_badge"]()
    assert "var enabled = true;" in scripts[-1]
