"""Real Qt library progress, filters, stage bars and guarded dialog navigation."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


@pytest.mark.parametrize("language,theme,width,font_size", [
    ("en", "dark", 1100, 13), ("hr", "light", 900, 13),
    ("zh-Hans", "dark", 900, 13), ("hr", "dark", 900, 18),
])
def test_document_filters_and_learning_views_are_visible_and_accessible(tmp_path, language, theme, width, font_size):
    script = dedent(r'''
        import os, sys, types
        package = types.ModuleType("incremento")
        package.__path__ = [os.getcwd()]
        sys.modules["incremento"] = package
        from aqt.qt import QApplication, QColor, QPalette, QLabel, QProgressBar, QCoreApplication, QEvent
        from incremento.backend.i18n import initialize_language, t
        from incremento.frontend import stats_dialog
        from incremento.frontend.stats_library import DocumentProgressPanel, CardStagePanel
        app = QApplication([])
        app.setStyle("Fusion")
        font = app.font()
        font.setPointSize(int(sys.argv[5]))
        app.setFont(font)
        palette = app.palette()
        if sys.argv[3] == "dark":
            for role, color in ((QPalette.ColorRole.Window, "#24272c"), (QPalette.ColorRole.Base, "#202328"),
                                (QPalette.ColorRole.WindowText, "#f3f5f7"), (QPalette.ColorRole.Text, "#f3f5f7"),
                                (QPalette.ColorRole.Button, "#30343b"), (QPalette.ColorRole.ButtonText, "#f3f5f7")):
                palette.setColor(role, QColor(color))
            app.setPalette(palette)
        initialize_language(sys.argv[2])
        rows = [dict(card_id=i, title=f"Synthetic book {i:03}", kind="pdf" if i % 2 else "epub",
                     read=26, left=74, total=100, percent=26, unit="pages" if i % 2 else "estimated_pages")
                for i in range(1, 124)]
        rows[0]["title"] = "<b>Literal title</b>"
        rows[1].update(read=100, left=0, percent=100)
        rows[2].update(read=0, left=None, total=None, percent=None)
        panel = DocumentProgressPanel(rows)
        panel.resize(1060, 640)
        panel.show()
        app.processEvents()
        assert panel.table.rowCount() == 50  # Bounded UI rendering, all records remain searchable.
        assert panel.next_button.isEnabled()
        panel.next_button.click()
        assert panel.table.rowCount() == 50
        panel.search.setText("Literal")
        assert panel.table.rowCount() == 1
        assert panel.table.item(0, 0).text() == "<b>Literal title</b>"
        assert panel.table.item(0, 2).text() == "26"
        assert panel.table.item(0, 3).text() == "74"
        assert panel.table.cellWidget(0, 5).format() == "26%"
        panel.kind.setCurrentIndex(panel.kind.findData("epub"))
        assert panel.table.rowCount() == 0 and panel.empty_message.isVisible()
        panel.search.clear()
        assert panel.table.rowCount() == 50
        assert all(panel.table.item(i, 1).text().startswith("EPUB") for i in range(50))
        panel.search.setText("002")
        assert panel.table.cellWidget(0, 5).value() == 1000
        panel.search.clear()
        panel.kind.setCurrentIndex(0)
        app.processEvents()
        assert panel.table.horizontalScrollBar().maximum() == 0
        # Alternating backgrounds must not disappear against dark-theme text.
        table_palette = panel.table.palette()
        assert abs(table_palette.text().color().lightness() - table_palette.alternateBase().color().lightness()) > 80
        panel.grab().save(os.path.join(sys.argv[1], "documents.png"))

        stats_dialog._active_profile = lambda: "Synthetic"
        stats_dialog.load_stats = lambda *_: {}
        stats_dialog.load_daily_history = lambda *_, **__: []
        stats_dialog.get_statistics_goals = lambda *_: {}
        stats_dialog.load_media_activity = lambda *_, **__: {}
        stats_dialog.request_daily_learning_outcomes = lambda *_, **__: None
        pending = []
        def documents(*args, **kwargs):
            pending.append((args[4], kwargs["is_current"], kwargs["cancelled"]))
        stats_dialog.request_document_progress = documents
        states = dict(new=80, learning=24, review=132, relearning=4, total=240, suspended=7, buried=2)
        stats_dialog.request_learning_card_states = lambda *args, **kwargs: args[3](states)
        from datetime import date, timedelta
        history = [{"date": (date(2026, 10, 14) - timedelta(days=59-i)).isoformat(),
                    "cards": 18, "stages": {"learning": {"again": 2, "good": 4}, "review": {"good": 12}}}
                   for i in range(60)]
        stats_dialog.request_learning_outcome_history = lambda *args, **kwargs: args[3](history)
        stats_dialog.mw = types.SimpleNamespace(col=None)
        window = stats_dialog.StatsDialog("/unused-synthetic")
        window.resize(int(sys.argv[4]), 900)
        window.show()
        app.processEvents()
        assert len(pending) == 0  # No whole-library scan just for opening Overview.
        window._view_tabs.setCurrentIndex(1)
        assert len(pending) == 1 and pending[0][1]()
        pending[0][0](rows)
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert window.findChild(DocumentProgressPanel) is not None
        assert window.findChild(DocumentProgressPanel).height() >= window._scroll.viewport().height() - 14
        window.grab().save(os.path.join(sys.argv[1], "document-window.png"))
        window._reload_statistics()
        assert not pending[0][1]() and pending[0][2]()
        assert len(pending) == 2
        window._view_tabs.setCurrentIndex(2)
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        stage = window.findChild(CardStagePanel)
        assert stage is not None
        assert len(stage.findChildren(QProgressBar)) == 4
        assert all(bar.height() >= bar.fontMetrics().height() + 4 for bar in stage.findChildren(QProgressBar))
        assert "132" in stage.findChild(QLabel, "stageReviewCount").text()
        assert window.findChild(QLabel, "learningDayDetail") is not None
        assert len(window.findChildren(stats_dialog._RecallRateChart)) == 1
        for chart in window.findChildren(stats_dialog._RecallRateChart) + window.findChildren(stats_dialog._DailyStackedChart):
            ticks = chart.date_ticks()
            assert ticks[0][0] == 0 and ticks[-1][0] == 29
            assert all(a[1] + a[2] + 8 <= b[1] for a, b in zip(ticks, ticks[1:])), ticks
        rate_chart = window.findChild(stats_dialog._RecallRateChart)
        assert rate_chart.plot_left() >= rate_chart.fontMetrics().horizontalAdvance("100%") + 8
        assert not window._scope_widget.isVisible()
        assert window._scroll.horizontalScrollBar().maximum() == 0
        assert window.width() == int(sys.argv[4])
        window.grab().save(os.path.join(sys.argv[1], "learning-window.png"))
        window._mark_closed()
        assert not pending[-1][1]() and pending[-1][2]()
        ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path), language, theme, str(width), str(font_size)],
                            cwd=Path(__file__).resolve().parents[1],
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                            capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
