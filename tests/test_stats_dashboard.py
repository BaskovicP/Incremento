"""Render the real Qt dashboard with synthetic, profile-independent history."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


@pytest.mark.parametrize("language,theme,width,font_size", [
    ("en", "dark", 1100, 13), ("en", "light", 900, 13),
    ("hr", "dark", 900, 13), ("zh-Hans", "light", 900, 13),
    ("hr", "light", 900, 18),
])
def test_progress_is_first_visible_interactive_and_fits_the_window(tmp_path, language, theme, width, font_size):
    script = dedent(r'''
        import os, sys, types
        from datetime import date, timedelta
        package = types.ModuleType("incremento")
        package.__path__ = [os.getcwd()]
        sys.modules["incremento"] = package
        from aqt.qt import QApplication, QColor, QPalette, QLabel, QPushButton, QCoreApplication, QEvent, QPoint, Qt
        from PyQt6.QtTest import QTest
        from incremento.backend.i18n import initialize_language, t
        from incremento.frontend import stats_dialog
        app = QApplication([])
        app.setStyle("Fusion")
        font = app.font()
        font.setPointSize(int(sys.argv[5]))
        app.setFont(font)
        palette = app.palette()
        dark = sys.argv[3] == "dark"
        for role, color in ((QPalette.ColorRole.Window, "#24272c" if dark else "#f5f6f8"),
                            (QPalette.ColorRole.Base, "#202328" if dark else "#ffffff"),
                            (QPalette.ColorRole.WindowText, "#f3f5f7" if dark else "#20242b"),
                            (QPalette.ColorRole.Text, "#f3f5f7" if dark else "#20242b"),
                            (QPalette.ColorRole.Button, "#30343b" if dark else "#e7ebf0"),
                            (QPalette.ColorRole.ButtonText, "#f3f5f7" if dark else "#20242b")):
            palette.setColor(role, QColor(color))
        app.setPalette(palette)
        initialize_language(sys.argv[2])
        current = ["2026-10-14"]
        profile = ["Synthetic"]
        history = []
        for index in range(730):
            day = date(2026, 10, 14) - timedelta(days=729-index)
            pages = 26 if index == 729 else (index % 9 + 1 if index > 701 and index % 4 else 0)
            history.append({"date": day.isoformat(),
                "reading": {"pdf_pages": pages, "epub_pages": 0 if index == 729 else pages // 3},
                "counts": {"type": {"items": 0 if index == 729 else pages * 2}},
                "seconds": {"type": {"pdf": 7200 if index == 729 else pages * 60}}})
        reads = []
        def read_history(*args, **kwargs):
            reads.append(current[0])
            return history if current[0] == "2026-10-14" else [{"date": current[0]}]
        stats_dialog._active_profile = lambda: profile[0]
        stats_dialog._effective_date = lambda _: current[0]
        stats_dialog.load_stats = lambda *_: {"daily": {"date": current[0], "counts": {}},
            "time": {"daily": {"date": current[0], "seconds": {"type": {"pdf": 7200}}}}}
        stats_dialog.load_daily_history = read_history
        stats_dialog.get_statistics_goals = lambda *_: {"pages": 40, "minutes": 90, "cards": 20}
        stats_dialog.set_statistics_goals = lambda *args: args[2]
        stats_dialog.load_media_activity = lambda *args, **kwargs: {"pages": 26, "pdf_pages": 26}
        pending = []
        stats_dialog.request_daily_learning_outcomes = lambda *args, **kwargs: pending.append(kwargs["is_current"])
        stats_dialog.request_learning_outcome_history = lambda *args, **kwargs: None
        stats_dialog.mw = types.SimpleNamespace(col=None)
        window = stats_dialog.StatsDialog("/unused-synthetic")
        window.resize(int(sys.argv[4]), 900)
        window.show()
        app.processEvents()
        assert window.width() == int(sys.argv[4])
        def dashboard():
            return window.findChild(stats_dialog.QWidget, "progressDashboard")
        panel = dashboard()
        assert panel is not None, "Reading graphs must be visible on Today, without changing scope"
        assert window._clayout.itemAt(0).widget() is panel
        assert panel.findChild(QLabel, "progressPagesValue").text() == "26"
        assert panel.findChild(QLabel, "progressTimeValue").text() == t("stats_duration_hours_minutes", hours=2, minutes=0)
        from incremento.frontend.stats_dashboard import ProgressChart
        charts = panel.findChildren(ProgressChart)
        assert len(charts) == 2
        assert charts[0].goal == 40 and charts[1].goal == 0
        assert charts[0].model["totals"]["pages"] == charts[1].model["cumulative"]["pages"][-1]
        assert panel.rect().contains(charts[1].mapTo(panel, charts[1].rect().bottomRight()))
        assert charts[0].isVisible() and charts[1].isVisible()
        assert window.rect().contains(charts[1].mapTo(window, charts[1].rect().bottomRight()))
        assert window._scroll.horizontalScrollBar().maximum() == 0
        panel.grab().save(os.path.join(sys.argv[1], "dashboard.png"))
        window.grab().save(os.path.join(sys.argv[1], "window.png"))
        # Keyboard users can inspect the same exact dates/values as mouse users.
        charts[0].setFocus()
        QTest.keyClick(charts[0], Qt.Key.Key_Home)
        detail = panel.findChild(QLabel, "progressDayDetail")
        assert "10/8/2026" in detail.text() or "8. 10. 2026." in detail.text() or "2026/10/8" in detail.text(), detail.text()
        QTest.keyClick(charts[0], Qt.Key.Key_End)
        assert "26" in detail.text()
        plot, _ = charts[1]._plot()
        point = QPoint(int(plot.left() + plot.width() * 2.5 / 7), int(plot.center().y()))
        QTest.mouseClick(charts[1], Qt.MouseButton.LeftButton, pos=point)
        assert charts[0].selected == charts[1].selected == 2
        assert detail.text() == charts[0].detail(2)
        QTest.keyClick(charts[0], Qt.Key.Key_End)
        minute_button = next(b for b in panel.findChildren(QPushButton) if b.property("metric") == "minutes")
        minute_button.click()
        assert charts[0].metric == charts[1].metric == "minutes"
        assert charts[0].goal == 90
        assert "2h 0m" in detail.text() or sys.argv[2] != "en"
        # Goal edits immediately change the graph, without reopening statistics.
        window._save_goals({"pages": 10, "minutes": 0, "cards": 0})
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert dashboard().findChildren(ProgressChart)[0].goal == 0
        for scope, points in (("7d", 7), ("30d", 30), ("365d", 53), ("lifetime", 30)):
            window._scroll.verticalScrollBar().setValue(window._scroll.verticalScrollBar().maximum())
            next(b for b in window._scope_group.buttons() if b.property("scope_key") == scope).click()
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            assert len(dashboard().findChildren(ProgressChart)[0].model["buckets"]) == points
            assert window._scroll.verticalScrollBar().value() == 0, "Changing scope must reveal its overview"
        window._reload_statistics()
        assert not pending[0]() and pending[-1](), "Refresh must invalidate older requests on the same day"
        # Rollover reloads history; a stale profile or closed dialog never reads it.
        current[0] = "2026-10-15"
        window._refresh()
        assert reads == ["2026-10-14", "2026-10-14", "2026-10-15"], reads
        profile[0] = "OtherSynthetic"
        window._reload_statistics()
        assert len(reads) == 3
        window.close()
        profile[0] = "Synthetic"
        window._reload_statistics()
        assert len(reads) == 3
    ''')
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), language, theme, str(width), str(font_size)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=35,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_large_font_chart_labels_and_empty_state_are_not_clipped(tmp_path):
    script = dedent(r'''
        import os, sys, types
        package = types.ModuleType("incremento")
        package.__path__ = [os.getcwd()]
        sys.modules["incremento"] = package
        from aqt.qt import QApplication, QFont, QLabel, QPainter, QPixmap, QRectF, Qt
        from incremento.backend.i18n import initialize_language, t
        from incremento.frontend import stats_dashboard, stats_dialog
        from incremento.frontend.stats_progress import progress_model
        app = QApplication([])
        app.setFont(QFont("Arial", 18))
        initialize_language("hr")
        text_boxes = []
        class Painter(QPainter):
            def drawText(self, *args):
                if isinstance(args[0], QRectF):
                    text_boxes.append((QRectF(args[0]), args[-1], self.fontMetrics().height(), args[1]))
                return super().drawText(*args)
        stats_dashboard.QPainter = Painter
        history = [{"date": "2026-10-14", "reading": {"pdf_pages": 26, "epub_pages": 4}}]
        for empty in (False, True):
            model = progress_model([] if empty else history, end_date="2026-10-14", days=7)
            chart = stats_dashboard.ProgressChart(model, cumulative=False,
                format_value=lambda metric, value: stats_dialog._format_count(value), on_selected=lambda _: None)
            chart.set_metric("pages", 40)
            chart.resize(380, 194)
            text_boxes.clear()
            pixmap = QPixmap(chart.size())
            chart.render(pixmap)
            pixmap.save(os.path.join(sys.argv[1], "empty.png" if empty else "large.png"))
            assert text_boxes
            for rect, text, height, flags in text_boxes:
                assert rect.height() >= height, (text, rect.height(), height)
                assert rect.top() >= 0 and rect.bottom() <= chart.height(), (text, rect, chart.size())
                if not flags & Qt.TextFlag.TextWordWrap:
                    assert rect.width() >= chart.fontMetrics().horizontalAdvance(text), (text, rect)
                else:
                    needed = chart.fontMetrics().boundingRect(rect.toRect(), int(flags), text).height()
                    assert needed <= rect.height(), (text, needed, rect.height())
            if empty:
                assert chart.values() == [0] * 7
            chart.close()
        panel = stats_dashboard.ProgressDashboard(model, totals=model["totals"],
            scope_label=t("stats_scope_today"), graph_label=t("stats_scope_7_days"), goals={},
            comparison=None, comparison_days=7, format_value=lambda metric, value: str(int(value)))
        panel.resize(900, panel.sizeHint().height())
        panel.show()
        app.processEvents()
        empty_labels = [label for label in panel.findChildren(QLabel) if label.objectName() == "progressEmptyMessage"]
        assert len(empty_labels) == 2 and all(label.isVisible() for label in empty_labels)
        for label in empty_labels:
            assert label.text() == t("stats_progress_empty")
            needed = label.heightForWidth(label.width())
            assert label.height() >= needed, (label.size(), needed)
        panel.grab().save(os.path.join(sys.argv[1], "empty-dashboard.png"))
        panel.close()
    ''')
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
