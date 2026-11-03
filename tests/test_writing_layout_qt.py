"""Writing puts the document first at realistic pane widths, using isolated Qt."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("scale", ["1", "1.5"])
@pytest.mark.parametrize("locale", ["en", "hr", "zh-Hans"])
@pytest.mark.parametrize("widget_style", ["anki", "native"])
def test_writing_layout_keeps_the_document_large_and_controls_reachable(tmp_path, theme, scale, locale, widget_style):
    # The screenshot regression was mostly chrome: repeated headings, a tall
    # formatting row and four footer rows left too little room for the draft.
    script = dedent('''
        import sys
        sys.path[:0] = ['backend', 'frontend']
        from aqt.qt import QApplication, QMainWindow, QWidget, QScrollArea, QTabBar, QToolButton, QStyleFactory, QEvent, Qt
        from PyQt6.QtGui import QColor, QPalette, QFontDatabase, QFont
        from aqt.stylesheets import custom_styles
        from aqt.theme import ThemeManager
        from backend.i18n import Translator
        from frontend import writing_dock as writing

        app = QApplication([])
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        font.setPointSizeF(15.0)
        font.setWeight(QFont.Weight.DemiBold)
        app.setFont(font)
        palette = app.palette()
        dark = sys.argv[2] == 'dark'
        for role, color in (
            (QPalette.ColorRole.Window, '#292929' if dark else '#f5f5f5'),
            (QPalette.ColorRole.Base, '#242424' if dark else '#ffffff'),
            (QPalette.ColorRole.WindowText, '#eeeeee' if dark else '#252525'),
            (QPalette.ColorRole.Text, '#eeeeee' if dark else '#252525'),
            (QPalette.ColorRole.ButtonText, '#eeeeee' if dark else '#252525'),
        ):
            palette.setColor(role, QColor(color))
        app.setPalette(palette)
        if sys.argv[4] == 'anki':
            app.setStyle('Fusion')
            tm = ThemeManager()
            tm._night_mode_preference = dark
            app.setStyleSheet(''.join(getattr(custom_styles, name)(tm) for name in (
                'general', 'button', 'checkbox', 'menu', 'combobox', 'tabwidget',
                'table', 'spinbox', 'scrollbar', 'slider', 'splitter')))
        else:
            app.setStyle('macOS' if 'macOS' in QStyleFactory.keys() else 'Windows')
        app_style, app_sheet = app.style(), app.styleSheet()
        writing.mw = QMainWindow()
        writing.mw.setCentralWidget(QWidget())
        writing._config = lambda config=None: {}
        writing._flush_editor_state = lambda **kwargs: True
        writing._ADDON_DIR = sys.argv[1]
        writing.t = Translator(sys.argv[3]).t
        dock = writing._build_writing_dock()
        assert app.style() is app_style and app.styleSheet() == app_sheet
        assert app.font().weight() == QFont.Weight.DemiBold
        dock.setFloating(True)
        dock._writing_tabs.addTab('A very long draft title ' * 12)
        dock._title_lbl.setText('A very long draft title ' * 12)
        original = '# A calmer writing space\\n\\nKeep this **draft** and its undo history.'
        dock._editor.setPlainText(original)
        writing._refresh_markdown_preview()
        for width, height in ((824, 974), (745, 983), (320, 600), (1100, 800)):
            dock.resize(width, height)
            dock.show()
            app.processEvents()
            assert dock.width() == width, (width, dock.minimumSizeHint())
            assert dock._split.height() >= dock.widget().height() * .70, (width, dock._split.geometry())
            assert dock._split.y() <= 130
            # Normal Anki dock widths must match the side-by-side design shown
            # to the user; only genuinely narrow panes should stack.
            expected = Qt.Orientation.Vertical if width < 720 else Qt.Orientation.Horizontal
            assert dock._split.orientation() == expected
            style = dock.findChild(QToolButton, 'writing_style')
            assert style.font().weight() == QFont.Weight.Normal
            assert style.font().pointSizeF() == 13.0
            tools = dock.findChild(QScrollArea)
            assert tools.height() <= 52, tools.height()
            tools.horizontalScrollBar().setValue(0)
            bold = next(button for button in tools.findChildren(QToolButton) if button.text() == 'B')
            bounds = bold.rect()
            bounds.moveTopLeft(bold.mapTo(tools.viewport(), bounds.topLeft()))
            assert tools.viewport().rect().contains(bounds), 'Bold should be available without scrolling'
            tools.horizontalScrollBar().setValue(tools.horizontalScrollBar().maximum())
            assert tools.widget().width() >= tools.viewport().width()
            for control in (dock._progress_scope_combo, dock._progress_value_lbl,
                            dock._keep_open_checkbox, dock._preview_btn):
                bounds = control.rect()
                bounds.moveTopLeft(control.mapTo(dock.widget(), bounds.topLeft()))
                assert dock.widget().rect().contains(bounds), (width, control, bounds)
            if width == 320:
                assert dock._export_btn.isHidden()
                more = dock.findChild(QToolButton, 'writing_more').menu()
                assert any(action.menu() is dock._export_btn.menu() for action in more.actions())
        writing._apply_preview_visibility(False)
        assert dock._preview_host.isHidden()
        assert dock._editor.toPlainText() == original
        writing._apply_preview_visibility(True)
        assert not dock._preview_host.isHidden()
        dock._editor.insertPlainText('Edited ')
        dock._editor.undo()
        assert dock._editor.toPlainText() == original
        writing._set_saved_time()
        writing._set_status(writing.t('writing_autosave_failed'))
        assert not dock._status_lbl.isHidden()
        assert dock._saved_lbl.isHidden(), 'A stale saved indicator must not compete with a failed save'
        # A close control follows its draft when tabs are dragged into a new order.
        tabs = dock._writing_tabs
        close = tabs.tabButton(0, QTabBar.ButtonPosition.RightSide)
        tabs.addTab('Another draft')
        tabs.moveTab(0, 1)
        requested = []
        tabs.tabCloseRequested.disconnect(writing._close_writing_tab)
        tabs.tabCloseRequested.connect(requested.append)
        close.click()
        assert requested == [1]
        # Switching Anki's palette must also refresh the custom writing surfaces.
        palette.setColor(QPalette.ColorRole.Window, QColor('#f5f5f5' if dark else '#292929'))
        app.setPalette(palette)
        app.processEvents()
        assert (dock._editor.palette().color(QPalette.ColorRole.Text).lightness() < 128) == dark
        assert dock._editor.toPlainText() == original
        dock.close()
        dock.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    ''')
    result = subprocess.run(
        [sys.executable, '-c', script, str(tmp_path), theme, locale, widget_style],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'QT_SCALE_FACTOR': scale},
        capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
