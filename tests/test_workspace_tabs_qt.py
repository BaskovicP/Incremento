"""Tab groups preserve live panes and reader identity; all widgets are synthetic."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_tabs_switch_split_save_and_restore_without_retiring_readers():
    script = dedent('''
        import ast, copy, sys, types
        from pathlib import Path
        from PyQt6 import QtCore, QtGui, QtWidgets
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtGui, QtWidgets):
            for name in dir(module): setattr(qt, name, getattr(module, name))
        sys.modules['aqt'] = types.ModuleType('aqt')
        sys.modules['aqt.qt'] = qt
        from frontend.workspace import WorkspaceLayouts, add_workspace_menu
        app = QtWidgets.QApplication([])
        main = QtWidgets.QMainWindow()
        main.setCentralWidget(QtWidgets.QLabel('Reviewer'))
        main.resize(1000, 700)
        stored = {}
        class Config:
            def getConfig(self, package): return copy.deepcopy(stored)
            def writeConfig(self, package, config): stored.update(copy.deepcopy(config))
        main.addonManager = Config()
        panes, stopped = [], []
        for kind in ('pdf', 'epub', 'writing', 'web', 'video', 'add_card', 'local_file'):
            dock = QtWidgets.QDockWidget(kind, main)
            dock.setObjectName('incremento_' + kind + '_dock')
            dock.setWidget(QtWidgets.QTextEdit('Unsaved ' + kind))
            main.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, dock)
            panes.append(dock)
            if kind in ('pdf', 'epub'):
                # Exercise the shipped visibility handlers with real Qt tab signals.
                tree = ast.parse(Path('frontend/' + kind + '_dock.py').read_text())
                callback = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                                and node.name == '_on_visibility_changed')
                namespace = dict(dock=dock, _pdf_find_jobs=None, _epub_find_jobs=None,
                    _stop_current_pdf_view=lambda: stopped.append('pdf'),
                    _clear_epub_metadata_cache=lambda: stopped.append('epub'),
                    _cb_epub_view_stopped=None)
                exec(compile(ast.Module(body=[callback], type_ignores=[]), '<visibility>', 'exec'), namespace)
                dock.visibilityChanged.connect(namespace['_on_visibility_changed'])
        unrelated = QtWidgets.QDockWidget('Other addon', main)
        unrelated.setObjectName('other_addon_tools')
        unrelated.setWidget(QtWidgets.QLabel('Other tools'))
        main.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, unrelated)
        main.show(); app.processEvents()
        class Session:
            def capture(self, docks, done):
                done([dict(name=d.objectName(), kind=d.windowTitle(), card_id=42) for d in docks])
            def restore(self, entries, current, done): done(panes, 0)
        manager = WorkspaceLayouts(main, session=Session(), profile=lambda: 'Synthetic')
        menu = add_workspace_menu(main.menuBar(), manager, lambda: None)
        menu.aboutToShow.emit()
        tabs = next((a for a in menu.actions() if a.text() == 'Group as tabs'), None)
        assert tabs is not None and tabs.isEnabled(), 'The menu must expose tabbed layouts'
        contents = [dock.widget() for dock in panes]
        stopped.clear()
        tabs.trigger(); app.processEvents()
        for dock in panes:
            assert set(main.tabifiedDockWidgets(dock)) == set(panes) - {dock}
            dock.raise_(); app.processEvents()
            assert not dock.visibleRegion().isEmpty(), 'Selecting each tab must expose its live content'
        assert stopped == [], 'Inactive reader tabs must retain their current document'
        assert set(manager.visible_panes()) == set(panes), 'Inactive tabs remain open workspace panes'
        assert not main.tabifiedDockWidgets(unrelated)
        assert [dock.widget() for dock in panes] == contents
        panes[2].raise_(); app.processEvents()
        saved = []
        manager.save_named('Tabs', saved.append)
        assert saved == [True], 'Saving must include inactive tabs'
        assert len(stored['workspace_layouts']['Synthetic']['Tabs']['panes']) == len(panes)
        assert manager.arrange('columns'); app.processEvents()
        assert all(not main.tabifiedDockWidgets(dock) for dock in panes)
        assert manager.restore(); app.processEvents()
        assert set(main.tabifiedDockWidgets(panes[0])) == set(panes[1:])
        assert not panes[2].visibleRegion().isEmpty(), 'Restore must retain the selected tab'
        assert manager.arrange('rows'); app.processEvents()
        manager.load_named('Tabs', lambda ok, missing: saved.append((ok, missing)))
        app.processEvents()
        assert saved[-1] == (True, 0)
        assert set(main.tabifiedDockWidgets(panes[0])) == set(panes[1:])
        assert not panes[2].visibleRegion().isEmpty(), 'Saved workspaces must retain the selected tab'
        panes[0].close(); app.processEvents()
        assert stopped == ['pdf'], 'An explicit close must still retire the PDF'
        assert manager.restore(); app.processEvents()
        assert panes[0].isHidden(), 'Restore must leave explicitly closed tabs closed'
        assert [dock.widget() for dock in panes] == contents
        main.close()
        from PyQt6 import sip
        if not sip.isdeleted(main):
            sip.delete(main)
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr


def test_drop_in_pane_centre_creates_tabs_and_edges_still_split():
    script = dedent('''
        import sys, types
        from PyQt6 import QtCore, QtGui, QtWidgets
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtGui, QtWidgets):
            for name in dir(module): setattr(qt, name, getattr(module, name))
        sys.modules['aqt'] = types.ModuleType('aqt')
        sys.modules['aqt.qt'] = qt
        from frontend.workspace import WorkspaceLayouts
        app = QtWidgets.QApplication([])
        main = QtWidgets.QMainWindow()
        main.setCentralWidget(QtWidgets.QLabel('Reviewer'))
        main.resize(650, 500)
        panes = []
        for kind in ('pdf', 'web', 'writing'):
            dock = QtWidgets.QDockWidget(kind, main)
            dock.setObjectName('incremento_' + kind + '_dock')
            dock.setWidget(QtWidgets.QTextEdit('Live ' + kind))
            main.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, dock)
            panes.append(dock)
        target, moving, untouched = panes
        moving.setFloating(True); untouched.setFloating(True)
        main.show(); app.processEvents()
        manager = WorkspaceLayouts(main)
        manager.enable_dragging()
        drag = manager._drag
        def drop(point):
            bar = moving.titleBarWidget()
            drag.press(moving, bar, bar.mapToGlobal(QtCore.QPoint(20, 10)))
            drag.move(point)
            assert drag.outline.isVisible()
            assert drag._target[:3] == ('pane', target, 'tab')
            drag.release(point); app.processEvents()
        point = target.mapToGlobal(target.rect().center())
        drop(point)
        assert main.tabifiedDockWidgets(target) == [moving]
        assert not moving.visibleRegion().isEmpty(), 'Dropped tab becomes active'
        assert untouched.isFloating() and untouched.isVisible()
        # Escape while tearing a tab out must restore the entire group.
        bar = moving.titleBarWidget()
        start = bar.mapToGlobal(QtCore.QPoint(20, 10))
        drag.press(moving, bar, start)
        drag.move(start + QtCore.QPoint(-100, 100))
        drag.cancel(); app.processEvents()
        assert main.tabifiedDockWidgets(target) == [moving]
        assert moving.widget().toPlainText() == 'Live web'
        assert manager.restore(); app.processEvents()
        assert moving.isFloating() and not main.tabifiedDockWidgets(target)
        assert manager.dock_at(moving, 'right', target=target); app.processEvents()
        assert not main.tabifiedDockWidgets(target) and moving.x() > target.x()
        assert not manager.dock_at(moving, 'tab', target=moving)
        assert not manager.dock_at(moving, 'tab'), 'Tabs require a live target'
        target.hide()
        assert not manager.dock_at(moving, 'tab', target=target)
        main.close()
        from PyQt6 import sip
        if not sip.isdeleted(main):
            sip.delete(main)
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr
