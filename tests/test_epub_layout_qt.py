"""Exercise EPUB control sizing with real, offscreen Qt and synthetic widgets."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


def _run_layout_check(script: str, *, scale: str = "1") -> None:
    setup = dedent('''
        import ast
        from pathlib import Path
        from typing import Any
        from PyQt6.QtCore import QPoint, QRect, QSize, Qt, QTimer
        from PyQt6.QtWidgets import QApplication, QDockWidget, QLayout, QVBoxLayout, QWidget

        # Load the production layout/visibility code without importing Anki or
        # document storage. The subprocess also avoids the main suite's Qt stubs.
        source = Path('frontend/epub_dock.py')
        names = {'_FlowLayout', '_normalize_epub_control_visibility', '_apply_epub_control_visibility',
                 '_refresh_epub_dock_minimum_width'}
        nodes = [node for node in ast.parse(source.read_text()).body
                 if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'))
        app = QApplication(['epub-layout-test'])
    ''')
    result = subprocess.run(
        [sys.executable, "-c", setup + dedent(script)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_SCALE_FACTOR": scale},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("scale", ["1", "1.5"], ids=["100-percent", "150-percent"])
@pytest.mark.parametrize("retain_hidden_size", [False, True], ids=["default-policy", "retained-size-policy"])
def test_hiding_epub_control_groups_releases_dock_minimum_width_and_show_restores_it(scale, retain_hidden_size):
    _run_layout_check(f'retain_hidden_size = {retain_hidden_size!r}\n' + dedent('''
        dock = QDockWidget('EPUB')
        dock.setMinimumWidth(300)
        container = QWidget(dock)
        column = QVBoxLayout(container)
        column.setContentsMargins(0, 0, 0, 0)
        row = QWidget(container)
        flow = _FlowLayout(row, margin=5, center_lines=True)
        column.addWidget(row)
        groups = {}
        for name, width in (('navigation', 180), ('review', 1075)):
            group = QWidget(row)
            group.setFixedSize(width, 40)
            policy = group.sizePolicy()
            policy.setRetainSizeWhenHidden(retain_hidden_size)
            group.setSizePolicy(policy)
            flow.addWidget(group)
            groups[name] = group
        dock.setWidget(container)
        dock._control_groups = groups
        dock._control_group_rows = (flow,)
        dock._control_groups_layout = column
        _epub_dock = dock
        _EPUB_CONTROL_GROUPS = (('navigation', 'Navigation'), ('review', 'Review'))
        dock.show()
        app.processEvents()
        original_width = dock.minimumSizeHint().width()
        assert original_width >= 1085

        _apply_epub_control_visibility({'review': False})
        app.processEvents()
        assert flow.minimumSize() == QSize(190, 50), flow.minimumSize()
        assert flow.sizeHint() == QSize(190, 50), flow.sizeHint()
        assert dock.minimumSizeHint().width() < original_width
        dock.resize(300, dock.height())
        app.processEvents()
        assert dock.width() == 300, dock.width()

        _apply_epub_control_visibility({'navigation': False, 'review': False})
        app.processEvents()
        assert flow.minimumSize() == QSize(10, 10), flow.minimumSize()
        assert flow.sizeHint() == QSize(10, 10), flow.sizeHint()
        assert flow.heightForWidth(300) == 10

        _apply_epub_control_visibility({})
        app.processEvents()
        assert all(not group.isHidden() for group in groups.values())
        assert dock.minimumSizeHint().width() == original_width
        dock.close()
    '''), scale=scale)


@pytest.mark.parametrize("hidden_index", [0, 1, 2], ids=["first", "middle", "last"])
def test_hidden_epub_group_adds_no_spacing_or_wrapped_line(hidden_index):
    _run_layout_check(f'hidden_index = {hidden_index}\n' + dedent('''
        host = QWidget()
        flow = _FlowLayout(host, margin=5, h_spacing=12, v_spacing=6, center_lines=True)
        groups = []
        for index in range(3):
            group = QWidget(host)
            group.setFixedSize(80, 40)
            flow.addWidget(group)
            group.setVisible(index != hidden_index)
            groups.append(group)

        # A hidden ancestor must not suppress controls that will be shown with it.
        assert not host.isVisible()
        assert flow.minimumSize() == QSize(90, 50)
        assert flow.heightForWidth(182) == 50, 'Hidden controls must not force a second line'
        rect = QRect(10, 20, 202, 100)
        flow.setGeometry(rect)
        visible = [group for group in groups if not group.isHidden()]
        assert [group.geometry().getRect() for group in visible] == [
            (25, 25, 80, 40), (117, 25, 80, 40),
        ], 'Only visible groups contribute to line centering and spacing'
    '''))


def test_pending_epub_width_refresh_does_not_touch_a_replaced_or_closed_dock():
    _run_layout_check('''
        original = QDockWidget('Original EPUB')
        original.setMinimumWidth(900)
        replacement = QDockWidget('Replacement EPUB')
        replacement.setMinimumWidth(640)
        _epub_dock = original
        _refresh_epub_dock_minimum_width()
        _epub_dock = replacement
        app.processEvents()
        assert original.minimumWidth() == 900
        assert replacement.minimumWidth() == 640

        _refresh_epub_dock_minimum_width()
        app.processEvents()
        assert replacement.minimumWidth() == 300

        replacement.setMinimumWidth(640)
        _refresh_epub_dock_minimum_width()
        _epub_dock = None
        app.processEvents()
        assert replacement.minimumWidth() == 640
    ''')


@pytest.mark.parametrize("scale", ["1", "1.5"], ids=["100-percent", "150-percent"])
@pytest.mark.parametrize("floating", [False, True], ids=["docked", "floating"])
@pytest.mark.parametrize("action", ["customize", "minimize", "expanded", "find"])
def test_real_epub_dock_can_be_narrowed_with_expanded_or_hidden_controls(scale, floating, action):
    script = f'floating = {floating!r}\naction = {action!r}\n' + dedent('''
        import sys, types
        from pathlib import Path

        # Import the whole reader, replacing only collection/session work and the
        # browser engine. All toolbar widgets, nested layouts and signals are real.
        repo = Path.cwd()
        sys.path[:0] = [str(repo / 'frontend'), str(repo / 'backend')]
        sys.modules['session'] = types.SimpleNamespace(
            INCREMENTO_EPUB_REVIEW_DECK='Synthetic Review',
            start_explicit_review=lambda *args, **kwargs: None,
        )
        import epub_dock as reader
        from PyQt6.QtCore import QObject, QPoint, QTimer, QUrl, Qt, pyqtSignal
        from PyQt6.QtWidgets import QApplication, QCheckBox, QDialog, QLabel, QMainWindow, QToolButton, QWidget

        class Profile(QObject):
            def setUrlRequestInterceptor(self, interceptor):
                pass

        class Page(QObject):
            def __init__(self, profile, dock, interceptor):
                super().__init__(dock)

            def settings(self):
                return types.SimpleNamespace(setAttribute=lambda *args: None)

        class View(QWidget):
            loadFinished = pyqtSignal(bool)
            urlChanged = pyqtSignal(QUrl)

            def setPage(self, page):
                self._page = page

        app = QApplication(['epub-dock-width-test'])
        main = QMainWindow()
        main.resize(1800, 1200)
        main.setCentralWidget(QLabel('Synthetic study area'))
        reader._active_profile = lambda: 'LayoutTest'
        main.addonManager = types.SimpleNamespace(getConfig=lambda _: {
            'epub_controls_collapsed_by_profile': {'LayoutTest': {'main': False}}})
        reader.mw = main
        reader.QWebEngineProfile = Profile
        reader._EpubRequestInterceptor = QObject
        reader._EpubDockPage = Page
        reader.QWebEngineView = View
        reader._build_epub_dock()
        dock = reader._epub_dock
        dock.setFloating(floating)
        main.show()
        dock.show()
        if floating:
            dock.resize(900, 800)

        def wait_for(predicate):
            for _ in range(50):
                app.processEvents()
                if predicate():
                    return
            raise AssertionError((dock.minimumWidth(), dock.minimumSizeHint().width(), dock.width()))

        def choose_groups(visible):
            def accept():
                dialog = app.activeModalWidget()
                assert isinstance(dialog, QDialog)
                checkboxes = dialog.findChildren(QCheckBox)
                assert len(checkboxes) == 4
                for checkbox in checkboxes:
                    checkbox.setChecked(visible)
                dialog.accept()
            QTimer.singleShot(0, accept)
            dock._customize_controls_btn.click()

        # Explicitly expanded controls remain resizable; a wide minimum on
        # startup was the bug, rather than a state to restore after customization.
        wait_for(lambda: dock.minimumSizeHint().width() <= 350)
        for _ in range(2):
            if action == 'customize':
                choose_groups(False)
                assert all(group.isHidden() for group in dock._control_groups.values())
            elif action == 'minimize':
                dock._minimize_controls_btn.click()
                assert dock._controls_expanded.isHidden()
                assert not dock._controls_compact.isHidden()
            else:
                assert not dock._controls_collapsed
                assert dock._controls_expanded.isVisible()
                assert all(group.isVisible() for group in dock._control_groups.values())
                if action == 'find':
                    assert reader.open_current_document_find()

            wait_for(lambda: dock.minimumWidth() <= 350 and dock.minimumSizeHint().width() <= 350)
            if floating:
                dock.resize(350, dock.height())
            else:
                main.resizeDocks([dock], [350], Qt.Orientation.Horizontal)
            wait_for(lambda: dock.width() == 350)

            if action in ('expanded', 'find'):
                assert not dock._controls_collapsed
                assert all(group.isVisible() for group in dock._control_groups.values())
                scroll = dock._controls_scroll
                assert scroll.height() <= 360
                assert dock._view.height() >= 150, 'Expanded controls must leave room for the document'
                assert not scroll.horizontalScrollBar().isVisible()
                group_rects = []
                for group in dock._control_groups.values():
                    group_rect = group.rect().translated(group.mapTo(dock._controls_host, QPoint(0, 0)))
                    assert all(not group_rect.intersects(other) for other in group_rects)
                    group_rects.append(group_rect)
                    controls = group.findChildren(QToolButton) + group.findChildren(QCheckBox)
                    for control in controls:
                        if control.isHidden():
                            continue
                        point = control.mapTo(dock._controls_host, QPoint(0, 0))
                        assert point.x() >= 0 and point.x() + control.width() <= scroll.viewport().width(), (
                            control.text(), point.x(), control.width(), scroll.viewport().width(),
                        )
                        local = control.mapTo(group, QPoint(0, 0))
                        assert local.y() >= 0 and local.y() + control.height() <= group.height(), control.text()
                        scroll.ensureWidgetVisible(control)
                        app.processEvents()
                        center = control.mapTo(scroll.viewport(), control.rect().center())
                        assert scroll.viewport().rect().contains(center), control.text()

            if action == 'customize':
                choose_groups(True)
            elif action == 'minimize':
                dock._show_controls_btn.click()
            wait_for(lambda: dock._controls_expanded.isVisible() and dock.minimumSizeHint().width() <= 350)
            assert all(group.isVisible() for group in dock._control_groups.values())
            if floating:
                dock.resize(1400, dock.height())
            else:
                main.resizeDocks([dock], [1400], Qt.Orientation.Horizontal)
            wait_for(lambda: dock.width() == 1400)
            if action in ('expanded', 'find'):
                for group in dock._control_groups.values():
                    row = group.layout()
                    assert len({row.itemAt(i).widget().y() for i in range(row.count())}) == 1, (
                        'Labelled sections should return to one row when there is enough width'
                    )

        main.close()
    ''')
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_SCALE_FACTOR": scale},
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
