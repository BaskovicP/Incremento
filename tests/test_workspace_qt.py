"""Real Qt layout boundaries; synthetic widgets only, never live Anki data."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


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
