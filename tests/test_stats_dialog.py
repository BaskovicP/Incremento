import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


_ADDON_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_spec = importlib.util.spec_from_file_location(
    "_incremento_stats_dialog",
    os.path.join(_ADDON_ROOT, "frontend", "stats_dialog.py"),
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["_incremento_stats_dialog"] = _mod
_spec.loader.exec_module(_mod)


def test_chart_accessibility_summary_translates_empty_and_overflow_text(monkeypatch):
    from backend.i18n import Translator
    translator = Translator('zh-Hans')
    monkeypatch.setattr(_mod, 't', translator.t)
    monkeypatch.setattr(_mod, 'tn', translator.tn)
    assert _mod._accessible_chart_summary('English user label', []) == 'English user label。暂无数据。'
    text = _mod._accessible_chart_summary('English user label', [('tag1', 1), ('tag2', 2)], maximum_items=1)
    assert 'English user label' in text and 'tag1' in text
    assert '还有 1 个值' in text and 'more values' not in text


def test_ordered_type_items_includes_document_and_web_types():
    items = _mod._ordered_type_items(
        {
            "webpage": 1,
            "topics": 2,
            "pdf": 3,
            "epub": 6,
            "youtube": 4,
            "items": 5,
        }
    )

    assert items == [
        ("Topics", 2.0),
        ("Items", 5.0),
        ("PDFs", 3.0),
        ("EPUBs", 6.0),
        ("Videos", 4.0),
        ("Web pages", 1.0),
    ]


def test_ordered_type_items_keeps_unknown_types_visible():
    assert _mod._ordered_type_items({"writing_card": 2}) == [("Writing Card", 2.0)]


def test_summary_metrics_calculates_core_values():
    metrics = dict(
        _mod._summary_metrics(
            {
                "type": {"topics": 2, "epub": 1},
                "tags": {"math": 1, "reading": 2},
                "mode": {"random": 2, "priority": 1},
            },
            {"type": {"topics": 30.0, "epub": 60.0}, "tags": {}},
        )
    )

    assert metrics["Cards studied"] == "3"
    assert metrics["Review time"] == "1m 30s"
    assert metrics["Avg/card"] == "30s"
    assert metrics["Top type/tag"] == "Topics / reading"


def test_summary_metrics_tolerates_malformed_blocks():
    metrics = dict(
        _mod._summary_metrics(
            {"type": {"topics": "2", "items": -1}, "tags": {"__no_tags__": 5}},
            {"type": {"pdf": "bad"}, "tags": {"read": "15"}},
        )
    )

    assert metrics["Cards studied"] == "2"
    assert metrics["Review time"] == "15s"
    assert metrics["Top type/tag"] == "Topics / None"


def test_learning_results_show_attempts_recall_and_separate_learning_grades():
    display = _mod.learning_outcome_display({
        "cards": 2, "failed_cards": 1,
        "stages": {
            "learning": {"again": 2, "good": 1},
            "review": {"hard": 1, "easy": 1},
        },
    })

    assert display["metrics"] == [
        ("Answer attempts", "5"), ("Again / Fail", "2"),
        ("Recalled", "3"), ("Recall rate", "60%"),
    ]
    assert display["rows"] == [
        ["Learning", "3", "2", "0", "1", "0", "33.3%"],
        ["Review", "2", "0", "1", "0", "1", "100%"],
        ["Relearning", "0", "0", "0", "0", "0", "—"],
    ]
    assert "Unique cards: 2" in display["hint"]
    assert "Cards with Again: 1" in display["hint"]


def test_learning_results_empty_day_has_no_invented_recall_rate():
    display = _mod.learning_outcome_display({"stages": {}})
    assert dict(display["metrics"])["Recall rate"] == "—"
    assert dict(display["metrics"])["Again / Fail"] == "0"
    assert _mod.learning_outcome_display(None) is None


def test_today_panel_renders_backfilled_anki_answers_in_each_language(tmp_path):
    script = dedent(r'''
        import os
        import sys
        import types
        package = types.ModuleType("incremento")
        package.__path__ = [os.getcwd()]
        sys.modules["incremento"] = package
        from aqt.qt import QApplication, QCoreApplication, QEvent, QLabel, QTableWidget
        from incremento.backend.i18n import initialize_language, t
        from incremento.frontend import stats_dialog
        app = QApplication([])
        stats_dialog._active_profile = lambda: "Synthetic"
        stats_dialog.load_stats = lambda *_: {}
        stats_dialog.load_daily_history = lambda *_, **__: [{
            "date": "2026-10-13",
            "reading": {"pdf_pages": 3, "epub_pages": 2},
        }]
        stats_dialog.get_statistics_goals = lambda *_: {}
        stats_dialog.mw = types.SimpleNamespace(col=None)
        pending = []
        stats_dialog.request_daily_learning_outcomes = lambda *args, **kwargs: pending.append(args[3])
        logical_date = ["2026-10-13"]
        stats_dialog._effective_date = lambda _cutoff: logical_date[0]
        stats_dialog.load_media_activity = lambda *args, **kwargs: {
            "pages": 5 if logical_date[0] == "2026-10-13" else 0,
            "pdf_pages": 3 if logical_date[0] == "2026-10-13" else 0,
            "epub_pages": 2 if logical_date[0] == "2026-10-13" else 0,
        }
        for language in ("en", "hr", "zh-Hans"):
            initialize_language(language)
            window = stats_dialog.StatsDialog("/unused-synthetic")
            window.resize(1000, 950)
            assert any(label.text() == t("stats_learning_results_loading")
                       for label in window.findChildren(QLabel))
            assert all(label.text() != t("stats_no_scope_statistics")
                       for label in window.findChildren(QLabel))
            pending[-1]({"cards": 10, "failed_cards": 3,
                "stages": {"learning": {"again": 5, "good": 4},
                           "review": {"again": 2, "hard": 3, "good": 6, "easy": 1}}})
            window.show()
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            table = next(table for table in window.findChildren(QTableWidget)
                         if table.accessibleName() == t("stats_learning_results_title"))
            assert table.item(0, 2).text() == "5"
            assert table.item(1, 2).text() == "2"
            assert table.item(2, 6).text() == "—"
            media_panel = next(frame for frame in window.findChildren(stats_dialog.QFrame)
                               if frame.objectName() == "mediaActivityPanel")
            cards = [
                [label.text() for label in frame.findChildren(QLabel)]
                for frame in media_panel.findChildren(stats_dialog.QFrame)
            ]
            assert ["5", t("stats_pages_read")] in cards
            assert all(label.text() != t("stats_no_scope_statistics")
                       for label in window.findChildren(QLabel))
            window.grab().save(os.path.join(sys.argv[1], language + ".png"))
            # Switching back to Today after rollover must not show yesterday.
            previous_requests = len(pending)
            logical_date[0] = "2026-10-14"
            window._refresh()
            assert len(pending) == previous_requests + 1
            pending[-1]({"cards": 0, "failed_cards": 0, "stages": {}})
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            media_panel = next(frame for frame in window.findChildren(stats_dialog.QFrame)
                               if frame.objectName() == "mediaActivityPanel")
            cards = [
                [label.text() for label in frame.findChildren(QLabel)]
                for frame in media_panel.findChildren(stats_dialog.QFrame)
            ]
            assert ["0", t("stats_pages_read")] in cards
            assert dict(stats_dialog.learning_outcome_display(window._learning_outcomes)["metrics"])[t("stats_again_fail")] == "0"
            window.close()
            assert window._closed
            logical_date[0] = "2026-10-13"
        ''')
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=_ADDON_ROOT, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_reading_video_activity_is_visible_in_today_period_and_all_time():
    script = dedent(r'''
        import os, sys, types
        package = types.ModuleType("incremento")
        package.__path__ = [os.getcwd()]
        sys.modules["incremento"] = package
        from aqt.qt import QApplication, QCoreApplication, QEvent, QLabel, QFrame
        from incremento.backend.i18n import initialize_language, t
        from incremento.frontend import stats_dialog
        initialize_language("en")
        app = QApplication([])
        stats_dialog._active_profile = lambda: "Synthetic"
        stats_dialog.load_stats = lambda *_: {}
        stats_dialog.load_daily_history = lambda *_, **__: []
        stats_dialog.get_statistics_goals = lambda *_: {}
        stats_dialog.request_daily_learning_outcomes = lambda *args, **kwargs: None
        stats_dialog.request_learning_outcome_history = lambda *args, **kwargs: None
        stats_dialog.mw = types.SimpleNamespace(col=None)
        requests = []
        def media(_addon, _profile, *, days=None, day_end_time):
            requests.append((days, day_end_time))
            return {"pages": 5 if days == 1 else 15,
                    "pdf_pages": 3 if days == 1 else 9,
                    "epub_pages": 2 if days == 1 else 6,
                    "videos_watched": 1 if days == 1 else 3,
                    "video_watch_seconds": 90 if days == 1 else 330}
        stats_dialog.load_media_activity = media
        window = stats_dialog.StatsDialog("/unused-synthetic", day_end_time="05:30")
        def panel_values():
            panel = next(frame for frame in window.findChildren(QFrame)
                         if frame.objectName() == "mediaActivityPanel")
            return [label.text() for label in panel.findChildren(QLabel)]
        assert "Reading & video" in panel_values()
        assert "Videos watched" in panel_values()
        assert "Video watch time" in panel_values()
        assert "5" in panel_values() and "3" in panel_values()
        assert "2" in panel_values() and "1" in panel_values()
        assert "1m 30s" in panel_values()
        seven = next(button for button in window._scope_group.buttons()
                     if button.property("scope_key") == "7d")
        seven.click()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert "15" in panel_values() and "5m 30s" in panel_values()
        all_time = next(button for button in window._scope_group.buttons()
                        if button.property("scope_key") == "lifetime")
        all_time.click()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert "15" in panel_values() and "5m 30s" in panel_values()
        assert requests == [(1, "05:30"), (7, "05:30"), (None, "05:30")]
        window.close()
        ''')
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=_ADDON_ROOT,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_seven_and_thirty_day_learning_graphs_share_background_history_and_render(tmp_path):
    script = dedent(r'''
        import os
        import sys
        import types
        from datetime import date, timedelta
        package = types.ModuleType("incremento")
        package.__path__ = [os.getcwd()]
        sys.modules["incremento"] = package
        from aqt.qt import QApplication, QCoreApplication, QEvent, QFrame
        from incremento.backend.i18n import initialize_language, t
        from incremento.frontend import stats_dialog
        app = QApplication([])
        stats_dialog._active_profile = lambda: "Synthetic"
        stats_dialog.load_stats = lambda *_: {}
        stats_dialog.load_daily_history = lambda *_, **__: []
        stats_dialog.get_statistics_goals = lambda *_: {}
        stats_dialog.mw = types.SimpleNamespace(col=None)
        stats_dialog.request_daily_learning_outcomes = lambda *args, **kwargs: None
        pending = []
        stats_dialog.request_learning_outcome_history = lambda *args, **kwargs: pending.append((args[3], kwargs["is_current"]))
        history = [{"date": (date(2026, 10, 13) - timedelta(days=59-index)).isoformat(),
            "stages": {} if index % 6 == 0 else {"review": {"again": 4 if index < 30 else 2, "good": 6 if index < 30 else 8}}}
            for index in range(60)]
        for language in ("en", "hr", "zh-Hans"):
            initialize_language(language)
            pending.clear()
            window = stats_dialog.StatsDialog("/unused-synthetic")
            window.resize(1100, 900)
            window.show()
            seven = next(button for button in window._scope_group.buttons() if button.property("scope_key") == "7d")
            thirty = next(button for button in window._scope_group.buttons() if button.property("scope_key") == "30d")
            seven.click()
            assert len(pending) == 1 and pending[0][1]()
            pending[0][0](history)
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            chart = window.findChildren(stats_dialog._RecallRateChart)[0]
            assert len(chart._labels) == len(chart._rates) == 7
            assert any(rate is None for rate in chart._rates)
            assert "80" in chart.accessibleDescription()
            panel = next(frame for frame in window.findChildren(QFrame) if frame.objectName() == "learningHistoryPanel")
            assert panel.rect().contains(chart.geometry().bottomRight()), (panel.size(), chart.geometry())
            items = [panel.layout().itemAt(index).geometry() for index in range(panel.layout().count())]
            assert all(before.bottom() < after.top() for before, after in zip(items, items[1:])), items
            counts = next(widget for widget in panel.findChildren(stats_dialog._DailyStackedChart))
            assert counts.parentWidget().rect().contains(counts.geometry().bottomRight())
            panel.grab().save(os.path.join(sys.argv[1], language + "-7d.png"))
            thirty.click()
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            assert len(pending) == 1
            chart = window.findChildren(stats_dialog._RecallRateChart)[0]
            assert len(chart._labels) == len(chart._rates) == 30
            panel = next(frame for frame in window.findChildren(QFrame) if frame.objectName() == "learningHistoryPanel")
            assert panel.rect().contains(chart.geometry().bottomRight()), (panel.size(), chart.geometry())
            panel.grab().save(os.path.join(sys.argv[1], language + "-30d.png"))
            window.close()
            assert not pending[0][1]()
        ''')
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)], cwd=_ADDON_ROOT,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"}, capture_output=True,
        text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_recall_graph_paints_zero_percent_gaps_and_keeps_date_labels_inside_chart():
    script = dedent(r'''
        import os, sys, types
        package = types.ModuleType("incremento")
        package.__path__ = [os.getcwd()]
        sys.modules["incremento"] = package
        from aqt.qt import QApplication, QPainter, QPixmap, QMouseEvent, QEvent, QPointF, Qt
        from incremento.backend.i18n import initialize_language
        from incremento.frontend import stats_dialog
        initialize_language("en")
        app = QApplication([])
        lines, points, texts = [], [], []
        class Painter(QPainter):
            def drawLine(self, *args):
                if self.pen().color().name() == "#198b72":
                    lines.append(args)
                return super().drawLine(*args)
            def drawEllipse(self, *args):
                points.append(args)
                return super().drawEllipse(*args)
            def drawText(self, *args):
                texts.append(args)
                return super().drawText(*args)
        stats_dialog.QPainter = Painter
        chart = stats_dialog._RecallRateChart(
            ["day1", "day2", "day3", "day4", "day5"],
            [0, None, 100, 50, None], ["zero", "no answers", "perfect", "half", "no answers"])
        chart.resize(600, 205)
        chart.render(QPixmap(chart.size()))
        assert len(lines) == 1, lines
        assert len(points) == 3, points
        assert {text[-1] for text in texts if text[-1].endswith("%")} == {"0%", "25%", "50%", "75%", "100%"}
        chart.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove, QPointF(80, 50),
            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
        assert chart.toolTip() == "zero"
        texts.clear()
        labels = [f"10/{index + 1}/2026" for index in range(30)]
        bars = stats_dialog._DailyStackedChart(labels, [("Recalled", [1] * 30)], ["#198b72"])
        bars.resize(600, 205)
        bars.render(QPixmap(bars.size()))
        for args in texts:
            if args[-1] in labels:
                assert args[0] + args[2] <= bars.width(), args
                assert args[2] >= bars.fontMetrics().horizontalAdvance(args[-1]), args
        ''')
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=_ADDON_ROOT,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_tag_items_filters_internal_synthetic_tags():
    assert _mod._tag_items({"__no_tags__": 10, "science": 2, "math": "3"}) == [
        ("math", 3.0),
        ("science", 2.0),
    ]


def test_topic_item_pie_items_use_card_counts_and_group_long_legends(monkeypatch):
    monkeypatch.setattr(
        _mod,
        "t",
        lambda key, **_values: {
            "stats_untagged": "Untagged",
            "stats_other_tags": "Other tags",
        }.get(key, key),
    )
    breakdown = {
        "counts": {
            "topics": {
                "tag-a": 9,
                "tag-b": 8,
                "tag-c": 7,
                "tag-d": 6,
                "tag-e": 5,
                "tag-f": 4,
                "tag-g": 3,
                "tag-h": 2,
                "(untagged)": 1,
            },
            "items": {},
        },
        "seconds": {
            "topics": {
                "tag-a": 1,
                "tag-b": 2,
                "tag-c": 3,
                "tag-d": 4,
                "tag-e": 5,
                "tag-f": 6,
                "tag-g": 7,
                "tag-h": 100,
                "(untagged)": 200,
            },
            "items": {},
        },
    }

    items = _mod._topic_item_pie_items(breakdown, "topics", maximum_items=8)

    assert items[:2] == [("tag-a", 1.0, 9.0), ("tag-b", 2.0, 8.0)]
    assert items[-1] == ("Other tags", 300.0, 3.0)
    assert sum(count for _label, _seconds, count in items) == 45.0


def test_pie_widget_paints_totals_and_percentages_for_all_slices():
    script = dedent(
        r"""
        import os
        import sys
        import types

        package = types.ModuleType("incremento")
        package.__path__ = [os.getcwd()]
        sys.modules["incremento"] = package

        from aqt.qt import QApplication, QPainter, QPixmap
        from incremento.backend.i18n import initialize_language
        from incremento.frontend import stats_dialog

        initialize_language("en")
        app = QApplication([])
        painted_text = []

        class RecordingPainter(QPainter):
            def drawText(self, *args):
                painted_text.append(args[-1])
                return super().drawText(*args)

        stats_dialog.QPainter = RecordingPainter
        cases = [
            ([1], "Total: 1", ["100%"]),
            ([11, 4, 2, 1, 1], "Total: 19",
             ["57.9%", "21.1%", "10.5%", "5.3%", "5.3%"]),
            ([], "Total: 0", []),
            ([0], "Total: 0", []),
        ]
        for counts, total, percentages in cases:
            painted_text.clear()
            widget = stats_dialog._PieChart(
                "Topics by tag",
                [(f"tag-{i}", 999, count) for i, count in enumerate(counts)],
                stats_dialog._TAG_COLORS,
            )
            widget.resize(480, widget.minimumHeight())
            widget.render(QPixmap(widget.size()))
            assert total in painted_text, painted_text
            assert [text for text in painted_text if text.endswith("%")] == percentages
            description = widget.accessibleDescription()
            assert total in description, description
            for percentage in percentages:
                assert percentage in description, description
            widget.close()
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_statistics_dialog_defaults_to_today_and_wires_two_topic_item_pies():
    source = open(_mod.__file__, encoding="utf-8").read()

    assert '("daily", t("stats_scope_today"))' in source
    assert 'if key == "daily":' in source
    assert "_add_topic_item_tag_pies" in source
    assert 't("stats_topic_tag_time")' in source
    assert 't("stats_item_tag_time")' in source


def test_ordered_mode_items_includes_unknown_modes_without_crashing():
    assert _mod._ordered_mode_items({"priority": 1, "custom_mode": 2}) == [
        ("Priority", 1.0),
        ("Custom Mode", 2.0),
    ]


def _history_fixture():
    return [
        {
            "date": "2026-04-21",
            "counts": {
                "type": {"topics": 2, "items": 1, "writing": 1},
                "tags": {},
                "mode": {},
            },
            "seconds": {"type": {"topics": 60.0, "items": 30.0}, "tags": {}},
            "reading": {"pdf_pages": 2, "epub_pages": 1, "pages": 3},
        },
        {
            "date": "2026-04-22",
            "counts": {"type": {}, "tags": {}, "mode": {}},
            "seconds": {"type": {}, "tags": {}},
            "reading": {"pdf_pages": 0, "epub_pages": 0, "pages": 0},
        },
        {
            "date": "2026-04-23",
            "counts": {"type": {"topics": 1, "items": 3}, "tags": {}, "mode": {}},
            "seconds": {"type": {"topics": 120.0}, "tags": {}},
            "reading": {"pdf_pages": 1, "epub_pages": 3, "pages": 4},
        },
    ]


def test_history_summary_metrics_reports_cards_pages_time_and_active_days():
    assert _mod._history_summary_metrics(_history_fixture()) == [
        ("Cards studied", "8"),
        ("Pages read", "7"),
        ("Study time", "3m 30s"),
        ("Active days", "2 / 3"),
    ]


def test_history_chart_series_keeps_topics_items_other_pdf_and_epub_separate():
    series = _mod._history_chart_series(_history_fixture())

    assert series["labels"] == ["4/21/2026", "4/22/2026", "4/23/2026"]
    assert series["cards"] == [
        ("Topics", [2.0, 0.0, 1.0]),
        ("Items", [1.0, 0.0, 3.0]),
        ("Other", [1.0, 0.0, 0.0]),
    ]
    assert series["pages"] == [
        ("PDF", [2.0, 0.0, 1.0]),
        ("EPUB", [1.0, 0.0, 3.0]),
    ]
    assert series["minutes"] == [("Minutes", [1.5, 0.0, 2.0])]


def test_history_insight_reports_streak_and_active_day_averages():
    assert _mod._history_insight(_history_fixture()) == (
        "Current streak: 1 day · Active-day average: 4 cards and 3.5 pages"
    )


def test_history_insight_rounds_repeating_averages_for_readability():
    history = []
    for day, cards, pages in ((1, 4, 15), (2, 4, 16), (3, 5, 16)):
        history.append(
            {
                "date": f"2026-04-{day:02d}",
                "counts": {"type": {"items": cards}, "tags": {}, "mode": {}},
                "seconds": {"type": {}, "tags": {}},
                "reading": {"pdf_pages": pages, "epub_pages": 0},
            }
        )

    assert _mod._history_insight(history) == (
        "Current streak: 3 days · Active-day average: 4.3 cards and 15.7 pages"
    )


def test_statistics_dialog_layout_keeps_goals_and_heatmap_compact():
    source = open(_mod.__file__, encoding="utf-8").read()

    assert "QGridLayout" in source
    assert "QSizePolicy.Policy.Maximum" in source
    assert "setFixedWidth(_heatmap_viewport_width(weeks, column_width))" in source
    assert _mod._heatmap_viewport_width(1) == 280
    assert _mod._heatmap_viewport_width(6) == 280
    assert _mod._heatmap_viewport_width(6, 40) == 312
    assert _mod._heatmap_viewport_width(53) == 840


def test_goal_recommendations_use_recent_positive_medians_without_outlier_bias():
    history = []
    for index, (cards, pages, minutes) in enumerate(
        (
            (999, 999, 999),  # Older than the 30-day recommendation window.
            (10, 0, 10),
            (20, 4, 20),
            (100, 8, 200),
        )
    ):
        history.append(
            {
                "date": f"2026-03-{index + 1:02d}",
                "counts": {"type": {"items": cards}, "tags": {}, "mode": {}},
                "seconds": {"type": {"items": minutes * 60}, "tags": {}},
                "reading": {"pdf_pages": pages, "epub_pages": 0},
            }
        )
    history[1:1] = [
        {
            "date": f"2026-02-{day:02d}",
            "counts": {"type": {}, "tags": {}, "mode": {}},
            "seconds": {"type": {}, "tags": {}},
            "reading": {},
        }
        for day in range(1, 29)
    ]

    assert _mod._goal_recommendations(history, days=30) == {
        "cards": {"target": 20, "active_days": 3},
        "pages": {"target": 6, "active_days": 2},
        "minutes": {"target": 20, "active_days": 3},
    }


def test_goal_recommendations_ignore_missing_or_invalid_activity_and_bound_targets():
    assert _mod._goal_recommendations([]) == {
        metric: {"target": 0, "active_days": 0}
        for metric in ("cards", "pages", "minutes")
    }
    history = [None, {}, {
        "counts": {"type": {"items": -5}},
        "seconds": {"type": {"items": "bad"}},
        "reading": {"pdf_pages": float("nan"), "epub_pages": -2},
    }, {
        "counts": {"type": {"items": 2_000_000}},
        "seconds": {"type": {"items": 3}},
        "reading": {"pdf_pages": 2, "epub_pages": 4},
    }]

    assert _mod._goal_recommendations(history) == {
        "cards": {"target": 1_000_000, "active_days": 1},
        "pages": {"target": 6, "active_days": 1},
        "minutes": {"target": 1, "active_days": 1},
    }


def test_heatmap_column_width_fits_month_labels_at_larger_fonts():
    script = dedent(
        r"""
        import os
        import sys
        import types

        package = types.ModuleType("incremento")
        package.__path__ = [os.getcwd()]
        sys.modules["incremento"] = package
        from aqt.qt import QApplication, QFont
        from incremento.frontend.stats_dialog import _ActivityHeatmap, _heatmap_viewport_width

        app = QApplication([])
        app.setFont(QFont("Arial", 22))
        widget = _ActivityHeatmap([{"date": "2026-09-01"}])
        header = widget.horizontalHeader()
        label = widget.horizontalHeaderItem(0).text()
        column_width = header.defaultSectionSize()
        assert column_width >= header.fontMetrics().horizontalAdvance(label) + 12
        assert widget.width() == _heatmap_viewport_width(widget.columnCount(), column_width)
        widget.close()
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("outcome", ["save", "cancel", "failure"])
def test_statistics_goal_editing_persists_only_accepted_successful_changes(outcome):
    script = dedent(
        r"""
        import os
        import sys
        import types

        package = types.ModuleType("incremento")
        package.__path__ = [os.getcwd()]
        sys.modules["incremento"] = package
        from aqt.qt import QApplication, QPushButton, QTimer
        from incremento.backend.i18n import initialize_language
        from incremento.frontend import stats_dialog

        initialize_language("en")
        app = QApplication([])
        outcome = sys.argv[1]
        initial = {"cards": 0, "pages": 12, "minutes": 0}
        writes = []
        stats_dialog._active_profile = lambda: "SyntheticProfile"
        stats_dialog.load_stats = lambda *_args: {}
        stats_dialog.get_statistics_goals = lambda *_args: dict(initial)
        stats_dialog.load_daily_history = lambda *_args, **_kwargs: []
        stats_dialog.mw = types.SimpleNamespace(col=None)

        def save(addon_dir, profile, requested):
            writes.append((addon_dir, profile, dict(requested)))
            if outcome == "failure":
                raise OSError("Synthetic write failure")
            return dict(requested)

        stats_dialog.set_statistics_goals = save
        window = stats_dialog.StatsDialog("/unused-synthetic-addon")
        assert window._goal_progress_bars["cards"].isHidden()
        assert not window._goal_progress_bars["pages"].isHidden()
        edit = next(button for button in window.findChildren(QPushButton)
                    if button.text() == "Edit goals…")

        def finish_edit():
            editor = app.activeModalWidget()
            editor._checks["cards"].setChecked(True)
            editor._spins["cards"].setValue(5)
            editor._checks["pages"].setChecked(False)
            if outcome == "cancel":
                editor.reject()
            else:
                editor.accept()

        QTimer.singleShot(0, finish_edit)
        edit.click()
        expected = {"cards": 5, "pages": 0, "minutes": 0}
        if outcome == "cancel":
            assert writes == []
        else:
            assert writes == [("/unused-synthetic-addon", "SyntheticProfile", expected)]
        assert window._goals == (expected if outcome == "save" else initial)
        assert window._goal_progress_bars["cards"].isHidden() == (outcome != "save")
        assert window._goal_progress_bars["pages"].isHidden() == (outcome == "save")
        if outcome == "failure":
            assert window._goal_status.text() == "Could not save daily goals."
        assert initial == {"cards": 0, "pages": 12, "minutes": 0}
        window.close()
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script, outcome],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_statistics_goal_editor_uses_explicit_metric_choices_and_recent_pace():
    source = open(_mod.__file__, encoding="utf-8").read()

    assert "class StatisticsGoalsDialog" in source
    assert "QCheckBox" in source
    assert "_goal_recommendations" in source
    assert "stats_goal_use_suggestion" in source
    assert "stats_edit_goals" in source


def test_statistics_goal_editor_applies_suggestions_only_after_user_choice():
    script = dedent(
        r"""
        import os
        import sys
        import types

        package = types.ModuleType("incremento")
        package.__path__ = [os.getcwd()]
        sys.modules["incremento"] = package

        from aqt.qt import QApplication, QPushButton
        from incremento.backend.i18n import initialize_language
        from incremento.frontend.stats_dialog import StatisticsGoalsDialog

        initialize_language("en")
        app = QApplication([])
        history = [{
            "date": "2026-10-06",
            "counts": {"type": {"items": 10}, "tags": {}, "mode": {}},
            "seconds": {"type": {"items": 1800}, "tags": {}},
            "reading": {"pdf_pages": 20, "epub_pages": 0},
        }]
        dialog = StatisticsGoalsDialog(
            {"cards": 0, "pages": 12, "minutes": 0}, history
        )
        assert dialog.goals() == {"cards": 0, "pages": 12, "minutes": 0}

        use_cards = next(
            button for button in dialog.findChildren(QPushButton)
            if button.text() == "Use 10"
        )
        use_cards.click()
        dialog._checks["pages"].setChecked(False)
        app.processEvents()

        assert dialog.goals() == {"cards": 10, "pages": 0, "minutes": 0}
        dialog.close()
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_period_comparison_reports_current_previous_and_percent_change():
    history = []
    for index in range(14):
        cards = 1 if index < 7 else 2
        history.append(
            {
                "date": f"2026-04-{index + 1:02d}",
                "counts": {"type": {"items": cards}, "tags": {}, "mode": {}},
                "seconds": {"type": {"items": cards * 60}, "tags": {}},
                "reading": {"pdf_pages": cards, "epub_pages": 0},
            }
        )

    comparison = _mod._history_period_comparison(history, 7)

    assert comparison["cards"] == {"current": 14.0, "previous": 7.0, "percent": 100.0}
    assert comparison["pages"] == {"current": 14.0, "previous": 7.0, "percent": 100.0}
    assert comparison["seconds"] == {"current": 840.0, "previous": 420.0, "percent": 100.0}


def test_goal_progress_and_day_drilldown_keep_metrics_separate():
    row = _history_fixture()[0]

    assert _mod._daily_goal_progress(
        row,
        {"cards": 8, "pages": 6, "minutes": 3},
    ) == {
        "cards": {"value": 4.0, "target": 8.0, "ratio": 0.5},
        "pages": {"value": 3.0, "target": 6.0, "ratio": 0.5},
        "minutes": {"value": 1.5, "target": 3.0, "ratio": 0.5},
    }
    assert _mod._history_day_detail(row) == {
        "date": "2026-04-21",
        "topics": 2.0,
        "items": 1.0,
        "other_cards": 1.0,
        "cards": 4.0,
        "pdf_pages": 2.0,
        "epub_pages": 1.0,
        "pages": 3.0,
        "seconds": 90.0,
    }


def test_heatmap_model_uses_zero_to_four_intensity_and_keeps_empty_days_clickable():
    model = _mod._activity_heatmap_model(_history_fixture(), metric="cards")

    assert [cell["date"] for cell in model] == [
        "2026-04-21",
        "2026-04-22",
        "2026-04-23",
    ]
    assert all(0 <= cell["intensity"] <= 4 for cell in model)
    assert model[1]["value"] == 0.0
    assert model[1]["intensity"] == 0
    assert model[2]["detail"]["items"] == 3.0


def test_heatmap_month_labels_show_each_visible_month_once():
    cells = [
        {"date": f"2026-09-{day:02d}"} for day in range(27, 31)
    ] + [
        {"date": f"2026-10-{day:02d}"} for day in range(1, 9)
    ]

    labels = _mod._heatmap_month_labels(cells, first_weekday=6, weeks=3)

    assert [label for label in labels if label] == ["Sep", "Oct"]


def test_statistics_dialog_source_wires_goals_heatmap_comparison_drilldown_and_csv():
    source = open(_mod.__file__, encoding="utf-8").read()

    assert "StatisticsGoalsDialog" in source
    assert "_ActivityHeatmap" in source
    assert "_history_period_comparison" in source
    assert "_show_day_drilldown" in source
    assert "_export_csv" in source
