"""Non-modal writing selection and responsive editor, using isolated real Qt."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_writing_picker_rejects_stale_results_and_opens_only_selected_existing_card():
    script = dedent('''
        import sys, types
        from PyQt6 import QtCore, QtGui, QtWidgets
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtGui, QtWidgets):
            for name in dir(module): setattr(qt, name, getattr(module, name))
        sys.modules['aqt'] = types.ModuleType('aqt')
        sys.modules['aqt.qt'] = qt
        operations = types.ModuleType('aqt.operations')
        pending = []
        class QueryOp:
            def __init__(self, **kw): self.kw = kw
            def failure(self, cb): self.failed = cb; return self
            def run_in_background(self): pending.append(self)
        operations.QueryOp = QueryOp
        sys.modules['aqt.operations'] = operations
        from frontend import writing_workspace as subject
        profile = ['A']
        subject.active_profile = lambda: profile[0]
        app = QtWidgets.QApplication([])
        main = QtWidgets.QMainWindow()
        main.col = object()
        opened = []
        dialog = subject.WritingPicker(main, open_card=opened.append)
        dialog.show()
        assert not dialog.isModal()
        pending.pop().kw['success']([(11, 'Alpha'), (22, 'Beta')])
        dialog.search.setText('beta')
        assert dialog.choices.count() == 1 and dialog.choices.item(0).text() == 'Beta'
        dialog.choices.setCurrentRow(0)
        dialog.open_selected()
        assert opened == [22]
        stale = subject.WritingPicker(main, open_card=opened.append)
        operation = pending.pop()
        stale.close()
        operation.kw['success']([(99, 'Must not appear')])
        assert stale.choices.count() == 0
        stale = subject.WritingPicker(main, open_card=opened.append)
        operation = pending.pop()
        profile[0] = 'B'
        operation.kw['success']([(99, 'Wrong profile')])
        assert stale.choices.count() == 0
        stale.open_selected()
        assert opened == [22]
        stale.close()
        main.close()
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_writing_tools_fit_narrow_panes_and_only_explicit_close_unpins():
    script = dedent('''
        import sys, tempfile
        sys.path[:0] = ['backend', 'frontend']
        from aqt.qt import QApplication, QMainWindow, QWidget, QScrollArea
        from frontend import writing_dock as writing
        from backend.i18n import Translator
        app = QApplication([])
        writing.mw = QMainWindow()
        writing.mw.setCentralWidget(QWidget())
        writing._config = lambda config=None: {}
        writing._flush_editor_state = lambda: None
        with tempfile.TemporaryDirectory() as temporary:
            writing._ADDON_DIR = temporary
            for locale in ('en', 'hr', 'zh-Hans'):
                writing.t = Translator(locale).t
                dock = writing._build_writing_dock()
                dock._title_lbl.setText('A long writing title that should wrap within the pane ' * 6)
                dock.setFloating(True)
                dock.resize(480, 700)
                dock.show()
                app.processEvents()
                assert dock.minimumSizeHint().width() <= 480, (locale, dock.minimumSizeHint())
                scroll = dock.findChild(QScrollArea)
                assert scroll.horizontalScrollBar().maximum() > 0
                scroll.horizontalScrollBar().setValue(scroll.horizontalScrollBar().maximum())
                assert scroll.horizontalScrollBar().value() > 0
                writing.set_keep_open(True)
                dock.hide()
                dock.show()
                assert writing._writing_keep_open, 'Tab/visibility changes must retain the pinned editor'
                dock.close()
                assert not writing._writing_keep_open
                writing.mw.removeDockWidget(dock)
                dock.deleteLater()
        writing.mw.close()
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
