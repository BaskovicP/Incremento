"""Floating pane borders resize live readers without moving or snapping them."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


def run_resize_scene(script, *, scale='1'):
    setup = dedent('''
        import sys, types
        from PyQt6 import QtCore, QtGui, QtWidgets, QtTest
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtGui, QtWidgets):
            for name in dir(module): setattr(qt, name, getattr(module, name))
        sys.modules['aqt'] = types.ModuleType('aqt')
        sys.modules['aqt.qt'] = qt
        from frontend.workspace import WorkspaceLayouts
        from PyQt6.QtCore import Qt, QPoint, QPointF, QRect, QEvent
        app = QtWidgets.QApplication([])
        main = QtWidgets.QMainWindow()
        main.resize(1000, 800)
        main.setCentralWidget(QtWidgets.QTextEdit('Synthetic reviewer'))
        dock = QtWidgets.QDockWidget('Synthetic PDF', main)
        dock.setObjectName('incremento_pdf_reference_test')
        content = QtWidgets.QTextEdit('Unsaved passage and reader state')
        dock.setWidget(content)
        dock.setMinimumSize(320, 240)
        dock.setMaximumSize(1000, 900)
        main.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        manager = WorkspaceLayouts(main)
        manager.enable_dragging()
        main.show()
        dock.setFloating(True)
        dock.setGeometry(-900, 100, 640, 500)
        app.processEvents()
        events = []
        dock.visibilityChanged.connect(events.append)
        dock.topLevelChanged.connect(events.append)
        original = dock.geometry()
        def mouse(widget, kind, global_pos):
            event = QtGui.QMouseEvent(kind, QPointF(widget.mapFromGlobal(global_pos)), QPointF(global_pos),
                Qt.MouseButton.NoButton if kind == QEvent.Type.MouseMove else Qt.MouseButton.LeftButton,
                Qt.MouseButton.NoButton if kind == QEvent.Type.MouseButtonRelease else Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier)
            app.sendEvent(widget, event)
        def begin(point):
            widget = dock.childAt(point) or dock
            start = dock.mapToGlobal(point)
            mouse(widget, QEvent.Type.MouseButtonPress, start)
            return widget, start
    ''')
    result = subprocess.run([sys.executable, '-c', setup + dedent(script)],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'QT_SCALE_FACTOR': scale},
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('scale', ['1', '1.5'], ids=['100-percent', '150-percent'])
@pytest.mark.parametrize('side', ['left', 'right', 'top', 'bottom', 'top_left', 'top_right', 'bottom_left', 'bottom_right'])
def test_dragging_floating_pdf_edges_and_corners_resizes_only_the_requested_sides(side, scale):
    run_resize_scene(f'side = {side!r}\n' + dedent('''
        x = 4 if 'left' in side else dock.width()-5 if 'right' in side else dock.width()//2
        y = 4 if 'top' in side else dock.height()-5 if 'bottom' in side else dock.height()//2
        widget, start = begin(QPoint(x, y))
        delta = QPoint(-70 if 'left' in side else 90 if 'right' in side else 0,
                       -50 if 'top' in side else 60 if 'bottom' in side else 0)
        mouse(widget, QEvent.Type.MouseMove, start + delta)
        mouse(widget, QEvent.Type.MouseButtonRelease, start + delta)
        app.processEvents()
        expected = original.adjusted(delta.x() if 'left' in side else 0,
            delta.y() if 'top' in side else 0, delta.x() if 'right' in side else 0,
            delta.y() if 'bottom' in side else 0)
        assert dock.geometry() == expected, (side, dock.geometry(), expected)
        assert dock.isFloating() and not dock.isMaximized() and not dock.isFullScreen()
        assert dock.widget() is content and content.toPlainText() == 'Unsaved passage and reader state'
        assert events == [] and not manager._drag.outline.isVisible()
        assert manager._drag.active_dock is None
        main.close()
    '''), scale=scale)


@pytest.mark.parametrize('side', ['left', 'top', 'bottom_right'])
def test_border_resize_respects_minimum_and_maximum_sizes_and_keeps_the_opposite_edge(side):
    run_resize_scene(f'side = {side!r}\n' + dedent('''
        point = (QPoint(4, dock.height()//2) if side == 'left' else
                 QPoint(dock.width()//2, 4) if side == 'top' else
                 QPoint(dock.width()-5, dock.height()-5))
        widget, start = begin(point)
        for delta in (QPoint(5000, 5000), QPoint(-5000, -5000)):
            mouse(widget, QEvent.Type.MouseMove, start + delta)
            size = dock.size()
            if side == 'left':
                assert size.width() == (320 if delta.x() > 0 else 1000)
                assert dock.geometry().right() == original.right()
                assert size.height() == original.height()
            elif side == 'top':
                assert size.height() == (240 if delta.y() > 0 else 900)
                assert dock.geometry().bottom() == original.bottom()
                assert size.width() == original.width()
            else:
                expected = QtCore.QSize(1000, 900) if delta.x() > 0 else QtCore.QSize(320, 240)
                assert size == expected
                assert dock.pos() == original.topLeft()
        mouse(widget, QEvent.Type.MouseButtonRelease, start)
        main.close()
    '''))


def test_resize_borders_preserve_close_float_and_content_mouse_targets():
    run_resize_scene('''
        bar = dock.titleBarWidget()
        for button in (bar.close_button, bar.float_button):
            for point in (button.rect().center(), button.rect().topLeft()+QPoint(1, 1),
                          button.rect().topRight()+QPoint(-1, 1)):
                point = button.mapTo(dock, point)
                assert dock.childAt(point) is button, 'Resize targets must not cover title-bar buttons'
        center = content.mapTo(dock, content.rect().center())
        assert dock.childAt(center) is content.viewport()
        assert manager._drag.active_dock is None
        QtTest.QTest.mouseClick(bar.float_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert not dock.isFloating()
        assert all(handle.isHidden() for handle in dock._workspace_resize_handles)
        QtTest.QTest.mouseClick(bar.float_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert dock.isFloating()
        assert all(handle.isVisible() for handle in dock._workspace_resize_handles)
        QtTest.QTest.mouseClick(bar.close_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert not dock.isVisible()
        main.close()
    ''')


def test_resize_handles_follow_signal_blocked_layout_moves_and_ignore_embedded_or_unrelated_panes():
    run_resize_scene('''
        for name, embedded in (('incremento_pdf_reference_embedded', True), ('another_addon', False)):
            other = QtWidgets.QDockWidget('Other', main)
            other.setObjectName(name)
            other.setWidget(QtWidgets.QTextEdit('Other content'))
            if embedded:
                other.setTitleBarWidget(QtWidgets.QWidget(other))
                other.setFeatures(QtWidgets.QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
            main.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, other)
            other.show()
            manager._drag.refresh()
            assert not hasattr(other, '_workspace_resize_handles')
        manager._drag.refresh()
        handles = tuple(dock._workspace_resize_handles)
        assert len(handles) == 8, 'Refreshing must not install duplicate borders'
        with QtCore.QSignalBlocker(dock):
            dock.setFloating(False)
        app.processEvents()
        assert all(handle.isHidden() for handle in handles)
        with QtCore.QSignalBlocker(dock):
            dock.setFloating(True)
            dock.setGeometry(original.adjusted(0, 0, 60, 40))
        app.processEvents()
        assert tuple(dock._workspace_resize_handles) == handles
        widget, start = begin(QPoint(dock.width()-5, dock.height()//2))
        before = dock.geometry()
        mouse(widget, QEvent.Type.MouseMove, start + QPoint(50, 0))
        mouse(widget, QEvent.Type.MouseButtonRelease, start + QPoint(50, 0))
        assert dock.geometry() == before.adjusted(0, 0, 50, 0)
        for show in (dock.showMaximized, dock.showFullScreen):
            show(); app.processEvents()
            assert all(handle.isHidden() for handle in handles)
            dock.showNormal(); app.processEvents()
            assert all(handle.isVisible() for handle in handles)
        main.close()
    ''')


@pytest.mark.parametrize('ending', ['escape', 'deactivate', 'profile-reset', 'close', 'delete'])
def test_border_resize_teardown_releases_the_gesture_without_stranding_the_reader(ending):
    run_resize_scene(f'ending = {ending!r}\n' + dedent('''
        widget, start = begin(QPoint(dock.width()-5, dock.height()-5))
        mouse(widget, QEvent.Type.MouseMove, start + QPoint(80, 60))
        resized = dock.geometry()
        assert resized.size() == original.size() + QtCore.QSize(80, 60)
        if ending == 'escape':
            QtTest.QTest.keyClick(widget, Qt.Key.Key_Escape)
        elif ending == 'deactivate':
            app.sendEvent(main, QEvent(QEvent.Type.ApplicationDeactivate))
        elif ending == 'profile-reset':
            manager.reset()
        elif ending == 'delete':
            dock.deleteLater()
            QtCore.QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            assert manager._drag.active_dock is None
            assert not manager._drag.outline.isVisible()
            main.close()
            sys.exit(0)
        else:
            dock.close()
        assert manager._drag.active_dock is None
        assert not manager._drag.outline.isVisible()
        assert QtWidgets.QWidget.mouseGrabber() is not widget
        assert dock.geometry() == (original if ending in ('escape', 'deactivate') else resized)
        mouse(widget, QEvent.Type.MouseMove, start + QPoint(150, 100))
        assert dock.geometry() == (original if ending in ('escape', 'deactivate') else resized)
        main.close()
    '''))
