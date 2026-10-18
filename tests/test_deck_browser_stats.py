import importlib.util
import os
import sys
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest


_ADDON_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_spec = importlib.util.spec_from_file_location(
    "_incremento_deck_browser_stats",
    os.path.join(_ADDON_ROOT, "frontend", "deck_browser_stats.py"),
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["_incremento_deck_browser_stats"] = _mod
_spec.loader.exec_module(_mod)


class _ChartTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.totals = []
        self.percentages = []
        self._target = None

    def handle_starttag(self, tag, attrs):
        classes = dict(attrs).get("class", "").split()
        if "incremento-pie-total" in classes:
            self._target = self.totals
        elif "incremento-pie-percentage" in classes:
            self._target = self.percentages

    def handle_data(self, data):
        if self._target is not None:
            self._target.append(data)

    def handle_endtag(self, tag):
        self._target = None


@pytest.mark.parametrize(
    "counts, expected_total, expected_percentages",
    [
        ({"Incremento": 1}, "Total: 1", ["100%"]),
        (
            {"Incremento": 11, "data": 4, "health": 2, "ai": 1, "spiritual": 1},
            "Total: 19",
            ["57.9%", "21.1%", "10.5%", "5.3%", "5.3%"],
        ),
        ({}, "Total: 0", []),
        (
            {f"tag-{index}": 1 for index in range(10)},
            "Total: 10",
            ["10%"] * 7 + ["30%"],
        ),
    ],
    ids=["single-slice", "screenshot", "empty", "grouped-other-tags"],
)
def test_daily_pie_shows_total_and_count_percentages_inside_slices(
    counts, expected_total, expected_percentages,
):
    breakdown = {
        "counts": {"topics": counts},
        # Time must never affect the count total or percentage labels.
        "seconds": {"topics": {key: 999 for key in counts}},
    }

    html = _mod._chart_html("Topics by tag", _mod._pie_items(breakdown, "topics"))
    parsed = _ChartTextParser()
    parsed.feed(html)

    assert parsed.totals == [expected_total]
    assert parsed.percentages == expected_percentages
    if expected_percentages:
        pie_start = html.index('class="incremento-pie"')
        legend_start = html.index('<ul class="incremento-pie-legend">')
        assert pie_start < html.index('class="incremento-pie-percentage"') < legend_start


def test_session_timer_suffix_is_removed_without_touching_anki_study_text():
    html = (
        "Studied 0 cards in 0 seconds today (0s/card)"
        "<br/>460.0 minutes in session, 0 seconds spent reviewing (0.0%)"
    )

    assert _mod.strip_session_timer_line(html) == (
        "Studied 0 cards in 0 seconds today (0s/card)"
    )
    assert _mod.strip_session_timer_line("A session overview") == "A session overview"


def test_session_timer_suffix_handles_short_and_hhmmss_formats():
    assert _mod.strip_session_timer_line(
        "Studied today<br>12 seconds in session, 3 seconds spent reviewing (25.0%)"
    ) == "Studied today"
    assert _mod.strip_session_timer_line(
        "Studied today<br/>01:02:03 in session, 00:04:05 spent reviewing (6.6%)"
    ) == "Studied today"


def test_daily_charts_render_topics_left_items_right_with_safe_legends(monkeypatch):
    monkeypatch.setattr(
        _mod,
        "t",
        lambda key, **values: {
            "stats_topic_tag_time": "Topics by tag",
            "stats_item_tag_time": "Items by tag",
            "stats_topic_item_pie_hint": "Slices show reviewed cards",
            "stats_pie_legend_value": "{cards} cards",
            "stats_pie_total": "Total: {cards}",
            "stats_untagged": "Untagged",
            "stats_other_tags": "Other tags",
            "stats_no_scope_statistics": "No activity",
            "stats_duration_hours_minutes": "{hours}h {minutes}m",
            "stats_duration_minutes_seconds": "{minutes}m {seconds}s",
            "stats_duration_seconds": "{seconds}s",
        }[key].format(**values),
    )
    breakdown = {
        "counts": {
            "topics": {"history<script>": 3, "rare": 1},
            "items": {"vocabulary": 5, "(untagged)": 1},
        },
        "seconds": {
            "topics": {"history<script>": 1, "rare": 99},
            "items": {"vocabulary": 60, "(untagged)": 15},
        },
    }

    html = _mod.build_daily_tag_charts_html(breakdown)

    assert html.index("Topics by tag") < html.index("Items by tag")
    assert "conic-gradient(" in html
    assert "#4e79a7 0.000% 75.000%" in html
    assert "history&lt;script&gt;" in html
    assert "history<script>" not in html
    assert "3 cards" in html
    assert "99s" not in html
    assert "Untagged" in html


def test_render_replaces_session_timer_and_always_appends_two_daily_charts(monkeypatch):
    monkeypatch.setattr(
        _mod,
        "load_stats",
        lambda _addon_dir, _profile: {
            "tag_breakdown": {
                "daily": {
                    "date": "2026-10-06",
                    "counts": {"topics": {}, "items": {}},
                    "seconds": {"topics": {}, "items": {}},
                }
            }
        },
    )
    monkeypatch.setattr(_mod, "_effective_date", lambda _day_end: "2026-10-06")
    monkeypatch.setattr(_mod, "build_daily_tag_charts_html", lambda _data: "<charts/>")
    content = SimpleNamespace(
        stats=(
            "Studied today"
            "<br/>460.0 minutes in session, 0 seconds spent reviewing (0.0%)"
        )
    )

    _mod.render_deck_browser_daily_stats(
        content,
        addon_dir="/addon",
        profile="Profile",
        day_end_time="04:00",
    )

    assert content.stats == "Studied today<charts/>"


def test_render_prefers_today_rebuilt_from_anki_revlog(monkeypatch):
    stored = {
        "counts": {"topics": {}, "items": {}},
        "seconds": {"topics": {}, "items": {}},
    }
    rebuilt = {
        "counts": {"topics": {"history": 4}, "items": {"law": 7}},
        "seconds": {"topics": {}, "items": {}},
    }
    monkeypatch.setattr(
        _mod,
        "load_stats",
        lambda _addon_dir, _profile: {
            "tag_breakdown": {"daily": {"date": "2026-10-07", **stored}}
        },
    )
    monkeypatch.setattr(_mod, "_effective_date", lambda _day_end: "2026-10-07")
    monkeypatch.setattr(
        _mod,
        "daily_tag_breakdown_from_collection",
        lambda collection, _day_end: rebuilt if collection == "collection" else None,
    )
    rendered = []
    monkeypatch.setattr(
        _mod,
        "build_daily_tag_charts_html",
        lambda data: rendered.append(data) or "<charts/>",
    )
    content = SimpleNamespace(stats="Studied today")

    _mod.render_deck_browser_daily_stats(
        content,
        addon_dir="/addon",
        profile="Profile",
        day_end_time="04:00",
        collection="collection",
    )

    assert rendered == [rebuilt]
    assert content.stats == "Studied today<charts/>"


def test_hidden_charts_are_removed_without_restoring_session_timer(monkeypatch):
    monkeypatch.setattr(
        _mod,
        "load_stats",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("hidden charts must not load statistics")
        ),
    )
    content = SimpleNamespace(
        stats=(
            "Studied today"
            "<!-- incremento-daily-tag-charts:start -->old<!-- incremento-daily-tag-charts:end -->"
            "<br/>15 minutes in session, 3 seconds spent reviewing (0.3%)"
        )
    )

    _mod.render_deck_browser_daily_stats(
        content,
        addon_dir="/addon",
        profile="Profile",
        show_charts=False,
    )

    assert content.stats == "Studied today"


def test_root_registers_deck_browser_renderer_last_after_addons_load():
    source = open(os.path.join(_ADDON_ROOT, "__init__.py"), encoding="utf-8").read()

    assert "deck_browser_will_render_content" in source
    assert "_install_deck_browser_stats_hook" in source
    assert "gui_hooks.main_window_did_init.append(_install_deck_browser_stats_hook)" in source


def test_deck_browser_hook_only_removes_stale_panels_and_timer_suffix():
    source = open(os.path.join(_ADDON_ROOT, "__init__.py"), encoding="utf-8").read()
    body = source.split("def _render_deck_browser_daily_stats(", 1)[1].split(
        "def _install_deck_browser_stats_hook", 1
    )[0]

    assert "_deck_browser_learning_stats.get(" not in body
    assert "show_charts=False" in body
    assert "show_learning_results=False" in body

    content = SimpleNamespace(stats=(
        "Studied today"
        "<!-- incremento-daily-learning:start -->old<!-- incremento-daily-learning:end -->"
        "<!-- incremento-daily-tag-charts:start -->old<!-- incremento-daily-tag-charts:end -->"
        "<br/>15 minutes in session, 3 seconds spent reviewing (0.3%)"
    ))
    _mod.render_deck_browser_daily_stats(
        content, addon_dir="/unused", profile="Synthetic", show_charts=False,
    )
    assert content.stats == "Studied today"


def test_daily_learning_html_shows_again_recalled_and_learning_review_split():
    html = _mod.build_daily_learning_html({
        "cards": 2, "failed_cards": 1,
        "stages": {"learning": {"again": 3}, "review": {"good": 1}},
    })

    assert "Today’s learning results" in html
    assert "Again / Fail" in html
    assert "Recalled" in html and "25%" in html
    assert "Learning" in html and "Review" in html and "Relearning" in html
    assert "3" in html and "Topic frequency choices" in html
    assert "<table" in html and '<th scope="col">' in html


def test_learning_html_does_not_show_zero_failures_when_collection_is_unavailable():
    html = _mod.build_daily_learning_html(None)
    assert "Learning results are unavailable" in html
    assert "Recall rate" not in html


def test_learning_summary_replaces_old_results_even_when_tag_pies_are_hidden():
    content = SimpleNamespace(stats="Studied today")
    options = dict(
        addon_dir="/unused", profile="Synthetic", show_charts=False,
        show_learning_results=True,
        learning_outcomes={"cards": 1, "failed_cards": 1, "stages": {"learning": {"again": 2}}},
    )
    _mod.render_deck_browser_daily_stats(content, **options)
    first = content.stats
    _mod.render_deck_browser_daily_stats(content, **options)

    assert content.stats == first
    assert first.count("Today’s learning results") == 1
    assert "Again / Fail" in first
    assert "Topics by tag" not in first
