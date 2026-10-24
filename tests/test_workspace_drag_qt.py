"""Drive title-bar gestures in offscreen Qt, without touching the user's desktop."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_drag_preview_drop_escape_and_profile_reset_preserve_live_content():
    script = dedent('''
        import sys, types
        from PyQt6 import QtCore, QtGui, QtWidgets, QtTest
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtGui, QtWidgets):
            for name in dir(module): setattr(qt, name, getattr(module, name))
        sys.modules['aqt'] = types.ModuleType('aqt')
        sys.modules['aqt.qt'] = qt
        from frontend.workspace import WorkspaceLayouts
        from frontend.workspace_drag import edge_placement, WorkspaceDrag
        from PyQt6.QtCore import Qt, QRect, QPoint, QPointF, QEvent
        from PyQt6.QtWidgets import QApplication, QMainWindow, QDockWidget, QTextEdit
        app = QApplication([])
        area = QRect(-1000, 20, 1000, 800)
        assert edge_placement(QPoint(-999, 400), area) == 'left'
        assert edge_placement(QPoint(-1, 21), area) == 'top_right'
        assert edge_placement(QPoint(-500, 400), area) is None
        assert edge_placement(QPoint(-1001, 400), area) is None
        main = QMainWindow()
        main.setCentralWidget(QTextEdit('Reviewer'))
        main.resize(900, 700)
        dock = QDockWidget('Synthetic PDF', main)
        dock.setObjectName('incremento_pdf_reference_test')
        content = QTextEdit('Unsaved text and live reader state')
        dock.setWidget(content)
        main.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        unrelated = QDockWidget('Other addon', main)
        unrelated.setWidget(QTextEdit())
        main.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, unrelated)
        manager = WorkspaceLayouts(main)
        manager.enable_dragging()
        main.show()
        app.processEvents()
        bar = dock.titleBarWidget()
        assert bar is not None and unrelated.titleBarWidget() is None
        drag = manager._drag
        original_screen_at = QApplication.screenAt
        fake_screen = types.SimpleNamespace(geometry=lambda: QRect(-1000, 0, 1000, 840),
            availableGeometry=lambda: QRect(-1000, 30, 1000, 770))
        QApplication.screenAt = staticmethod(lambda point: fake_screen)
        proposed = drag._drop_target(QPoint(-999, 1))
        assert proposed is not None, 'The macOS menu-bar edge must still offer snapping'
        assert proposed[2:] == ('top_left', QRect(-1000, 30, 500, 385))
        QApplication.screenAt = original_screen_at
        events = []
        dock.visibilityChanged.connect(events.append)
        start = bar.mapToGlobal(QPoint(30, 12))
        screen = dock.screen().availableGeometry()
        target = QPoint(screen.left()+1, screen.center().y())
        def mouse(kind, global_pos, buttons):
            local = bar.mapFromGlobal(global_pos)
            event = QtGui.QMouseEvent(kind, QPointF(local), QPointF(global_pos),
                Qt.MouseButton.LeftButton if kind != QEvent.Type.MouseMove else Qt.MouseButton.NoButton,
                buttons, Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(bar, event)
        mouse(QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton)
        mouse(QEvent.Type.MouseMove, target, Qt.MouseButton.LeftButton)
        assert drag.outline.isVisible(), 'Dragging to a screen edge previews the proposed bounds'
        assert drag.outline.geometry().width() == screen.width() // 2
        assert not drag.outline.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        mouse(QEvent.Type.MouseButtonRelease, target, Qt.MouseButton.NoButton)
        app.processEvents()
        assert not drag.outline.isVisible() and dock.isFloating()
        assert abs(dock.frameGeometry().left() - screen.left()) <= 2
        assert abs(dock.frameGeometry().width() - screen.width() // 2) <= 2
        assert dock.widget() is content and content.toPlainText() == 'Unsaved text and live reader state'
        assert events == [], 'Moving is not a document-close event'
        assert manager.restore() and not dock.isFloating()
        start = bar.mapToGlobal(QPoint(30, 12))
        mouse(QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton)
        mouse(QEvent.Type.MouseMove, target, Qt.MouseButton.LeftButton)
        QtTest.QTest.keyClick(bar, Qt.Key.Key_Escape)
        assert not dock.isFloating() and not drag.outline.isVisible()
        mouse(QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton)
        mouse(QEvent.Type.MouseMove, target, Qt.MouseButton.LeftButton)
        manager.reset()
        assert not drag.outline.isVisible() and drag.active_dock is None
        main.close()
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr


def test_drops_on_all_four_pane_edges_preserve_other_windows_and_can_restore():
    script = dedent('''
        import sys, types
        from PyQt6 import QtCore, QtGui, QtWidgets
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtGui, QtWidgets):
            for name in dir(module): setattr(qt, name, getattr(module, name))
        sys.modules['aqt'] = types.ModuleType('aqt')
        sys.modules['aqt.qt'] = qt
        from frontend.workspace import WorkspaceLayouts
        from PyQt6.QtCore import Qt, QPoint
        app = QtWidgets.QApplication([])
        main = QtWidgets.QMainWindow()
        main.setCentralWidget(QtWidgets.QLabel('Reviewer'))
        main.resize(1000, 800)
        manager = WorkspaceLayouts(main)
        panes = []
        for index in range(3):
            dock = QtWidgets.QDockWidget(str(index), main)
            dock.setObjectName('incremento_pdf_reference_' + str(index))
            dock.setWidget(QtWidgets.QTextEdit('Content ' + str(index)))
            main.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
            panes.append(dock)
        target, moving, untouched = panes
        moving.setFloating(True)
        untouched.setFloating(True)
        main.show()
        app.processEvents()
        content = moving.widget()
        manager.enable_dragging()
        for side in ('right', 'left', 'top', 'bottom'):
            assert manager.dock_at(moving, side, target=target)
            app.processEvents()
            assert not moving.isFloating()
            assert moving.widget() is content
            assert untouched.isVisible() and untouched.isFloating()
            if side == 'right': assert moving.x() > target.x()
            if side == 'left': assert moving.x() < target.x()
            if side == 'top': assert moving.y() < target.y()
            if side == 'bottom': assert moving.y() > target.y()
            assert manager.restore()
            app.processEvents()
            assert moving.isFloating() and untouched.isFloating()
        # Resizing is not dragging; editor mouse events cannot start a snap.
        assert manager._drag.active_dock is None
        assert content is moving.widget()
        moving.setMinimumWidth(moving.screen().availableGeometry().width())
        original = moving.geometry()
        assert not manager.snap(moving, 'left')
        assert moving.geometry() == original
        main.close()
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr
