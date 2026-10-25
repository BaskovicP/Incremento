"""Real Qt layout boundaries; synthetic widgets only, never live Anki data."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


def test_workspace_arranges_live_panes_and_restores_focus_without_close_signals():
    script = dedent('''
        import sys, types
        from PyQt6 import QtCore, QtGui, QtWidgets
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtGui, QtWidgets):
            for name in dir(module): setattr(qt, name, getattr(module, name))
        sys.modules['aqt'] = types.ModuleType('aqt')
        sys.modules['aqt.qt'] = qt
        from frontend.workspace import WorkspaceLayouts, snap_rectangle
        from frontend.pdf_focus_mode import PdfFocusMode
        from PyQt6.QtWidgets import QApplication, QMainWindow, QDockWidget, QTextEdit, QLabel, QWidget, QVBoxLayout
        from PyQt6.QtCore import Qt, QRect
        app = QApplication([])
        main = QMainWindow()
        main.resize(1400, 900)
        main.setCentralWidget(QWidget())
        layout = QVBoxLayout(main.centralWidget())
        main.web = QLabel('Reviewer')
        main.bottomWeb = QLabel('Answer buttons')
        layout.addWidget(main.web)
        layout.addWidget(main.bottomWeb)
        panes = []
        for name in ('pdf_dock', 'writing_dock', 'pdf_reference_test'):
            dock = QDockWidget(name, main)
            dock.setObjectName('incremento_' + name)
            dock.setWidget(QTextEdit('Unsaved text: ' + name))
            main.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
            panes.append(dock)
        pdf, writing, reference = panes
        mode = PdfFocusMode(main, pdf, pdf.widget(), enabled=True)
        pdf._pdf_focus_mode = mode
        reference.setFloating(True)
        pdf.setFloating(True)
        main.show()
        mode.present(eligible=True, title='PDF')
        app.processEvents()
        contents = [d.widget() if d is not pdf else mode.host for d in panes]
        events = []
        for d in panes:
            d.topLevelChanged.connect(lambda value: events.append(value))
            d.visibilityChanged.connect(lambda value: events.append(value))
        manager = WorkspaceLayouts(main)
        assert manager.visible_panes() == panes
        assert manager.dock_at(writing, 'right', target=pdf)
        app.processEvents()
        assert not pdf.isFloating(), 'Dropping beside a focused reader must dock its previously floating host'
        assert not mode.active and pdf.widget() is contents[0]
        assert manager.restore()
        assert manager.beside(writing)
        app.processEvents()
        assert mode.active, 'Writing beside a focused PDF must keep the PDF in the central reading area'
        assert writing.isVisible() and not writing.isFloating()
        assert mode.host.mapTo(main, mode.host.rect().topRight()).x() < writing.x()
        assert manager.restore()
        assert manager.arrange('columns')
        app.processEvents()
        assert not mode.active
        assert all(d.isVisible() and not d.isFloating() for d in panes)
        assert pdf.x() < writing.x() < reference.x()
        assert events == [], 'Layout moves must not close a reference pane or end reading'
        assert [d.widget() for d in panes] == contents
        assert writing.widget().toPlainText() == 'Unsaved text: writing_dock'
        assert manager.restore()
        app.processEvents()
        assert mode.active and reference.isFloating()
        assert writing.isVisible() and main.bottomWeb.isVisible()
        assert not manager.restore(), 'Restore is one-shot'
        assert manager.arrange('rows')
        app.processEvents()
        assert pdf.y() < writing.y() < reference.y()
        assert manager.arrange('grid')
        app.processEvents()
        assert pdf.x() < writing.x() and reference.y() > pdf.y()
        assert manager.snap(writing, 'right')
        app.processEvents()
        assert writing.isFloating() and writing.widget() is contents[1]
        reference.close()
        assert manager.restore()
        assert not reference.isVisible(), 'Restoring a layout must not resurrect closed documents'
        manager.reset()
        assert not manager.restore()
        area = QRect(-1600, 30, 1600, 970)
        assert snap_rectangle(area, 'left') == QRect(-1600, 30, 800, 970)
        assert snap_rectangle(area, 'bottom_right') == QRect(-800, 515, 800, 485)
        assert snap_rectangle(area, 'maximize') == area
        try:
            snap_rectangle(area, 'invalid')
        except ValueError:
            pass
        else:
            raise AssertionError('Unknown layouts must fail without moving windows')
        main.close()
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('transition', ['restart', 'profile-switch', 'save-failure', 'stale-load'])
def test_named_workspace_restores_saved_documents_controls_and_window_geometry(tmp_path, transition):
    script = dedent('''
        import copy, json, sys, types
        from pathlib import Path
        from PyQt6 import QtCore, QtGui, QtWidgets
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtGui, QtWidgets):
            for name in dir(module): setattr(qt, name, getattr(module, name))
        sys.modules['aqt'] = types.ModuleType('aqt')
        sys.modules['aqt.qt'] = qt
        from frontend.workspace import WorkspaceLayouts
        from PyQt6.QtWidgets import QApplication, QMainWindow, QDockWidget, QTextEdit, QLabel
        from PyQt6.QtCore import Qt
        app = QApplication([])
        profile, pending, opened = ['A'], [], []
        path, transition = Path(sys.argv[1])/'config.json', sys.argv[2]
        class Manager:
            def getConfig(self, package):
                return json.loads(path.read_text()) if path.exists() else {'future_setting': 7}
            def writeConfig(self, package, config):
                if transition == 'save-failure': raise OSError('Synthetic failure')
                path.write_text(json.dumps(config))
        class Session:
            def capture(self, panes, done):
                pending.append(lambda: done([{'name': dock.objectName(), 'kind': 'writing',
                    'card_id': 42, 'controls': {'preview': False, 'wrap': True}} for dock in panes]))
            def restore(self, entries, current, done):
                def finish():
                    if not current(): return
                    docks = []
                    for entry in entries:
                        dock = QDockWidget('Restored writing', main)
                        dock.setObjectName(entry['name']); dock.setWidget(QTextEdit('Existing saved text'))
                        dock.controls = entry['controls']
                        main.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
                        dock.show(); docks.append(dock); opened.append(entry['card_id'])
                    done(docks, 0)
                pending.append(finish)
        main = QMainWindow(); main.resize(1200, 800); main.setCentralWidget(QLabel('Study'))
        main.addonManager = Manager()
        writing = QDockWidget('Writing', main); writing.setObjectName('incremento_writing_dock')
        writing.setWidget(QTextEdit('Existing saved text'))
        main.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, writing)
        writing.setFloating(True); writing.setGeometry(110, 120, 440, 500)
        main.show(); writing.show(); app.processEvents()
        geometry = writing.geometry()
        results = []
        manager = WorkspaceLayouts(main, session=Session(), profile=lambda: profile[0])
        manager.save_named('My desk', results.append)
        assert not path.exists(), 'Capture must finish before the config is saved'
        if transition == 'profile-switch': profile[0] = 'B'
        pending.pop()()
        if transition in ('profile-switch', 'save-failure'):
            assert not path.exists(), 'Failed and stale saves cannot create a saved workspace'
            main.close(); sys.exit(0)
        assert results == [True]
        assert main.addonManager.getConfig('incremento')['future_setting'] == 7
        writing.close(); writing.setParent(None); writing.deleteLater(); app.processEvents()
        manager = WorkspaceLayouts(main, session=Session(), profile=lambda: profile[0])
        assert manager.saved_names() == ['My desk'], 'A fresh manager loads persisted named workspaces'
        profile[0] = 'B'; assert manager.saved_names() == []
        profile[0] = 'A'
        manager.load_named('My desk', lambda ok, missing: results.append((ok, missing)))
        if transition == 'stale-load': manager.reset()
        pending.pop()(); app.processEvents()
        if transition == 'stale-load':
            assert opened == [], 'A retired restore cannot reopen panes'
        else:
            dock = main.findChild(QDockWidget, 'incremento_writing_dock')
            assert opened == [42] and dock.isVisible() and dock.isFloating()
            assert dock.geometry() == geometry
            assert dock.controls == {'preview': False, 'wrap': True}
            assert results[-1] == (True, 0)
            assert manager.delete_named('My desk')
            assert manager.saved_names() == []
        main.close()
    ''')
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path), transition],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_saved_reference_slot_remains_attached_to_its_open_window():
    script = dedent('''
        import copy, sys, types
        from PyQt6 import QtCore, QtGui, QtWidgets
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtGui, QtWidgets):
            for name in dir(module): setattr(qt, name, getattr(module, name))
        sys.modules['aqt'] = types.ModuleType('aqt')
        sys.modules['aqt.qt'] = qt
        from frontend.workspace import WorkspaceLayouts
        app = QtWidgets.QApplication([])
        main = QtWidgets.QMainWindow()
        main.setCentralWidget(QtWidgets.QLabel('Synthetic study area'))
        stored = {}
        class Manager:
            def getConfig(self, package): return copy.deepcopy(stored)
            def writeConfig(self, package, config): stored.update(copy.deepcopy(config))
        main.addonManager = Manager()
        class Session:
            def capture(self, panes, done):
                done([{'kind': 'pdf_reference', 'name': dock.objectName(), 'card_id': 42} for dock in panes])
        dock = QtWidgets.QDockWidget('PDF', main)
        dock.setObjectName('incremento_pdf_reference_nonce')
        dock.setWidget(QtWidgets.QTextEdit('Synthetic reader'))
        main.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, dock)
        main.show(); dock.show(); app.processEvents()
        manager = WorkspaceLayouts(main, session=Session(), profile=lambda: 'A')
        saved = []
        manager.save_named('Desk', saved.append)
        assert saved == [True]
        entry = stored['workspace_layouts']['A']['Desk']['panes'][0]
        assert dock._workspace_saved_name == entry['name']
        assert dock.objectName() == 'incremento_pdf_reference_nonce'
        main.close()
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
