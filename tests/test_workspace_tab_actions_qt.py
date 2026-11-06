"""Workspace tab actions target live panes and never rename their content."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_tab_rename_reset_save_and_close_respect_identity_and_unsaved_work(tmp_path):
    script = dedent('''
        import copy, sys, types
        from pathlib import Path
        from unittest.mock import patch
        from PyQt6 import QtCore, QtGui, QtWidgets, QtTest
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtGui, QtWidgets):
            for name in dir(module): setattr(qt, name, getattr(module, name))
        sys.modules['aqt'] = types.ModuleType('aqt')
        sys.modules['aqt.qt'] = qt
        from frontend.workspace import WorkspaceLayouts
        app = QtWidgets.QApplication([])
        main = QtWidgets.QMainWindow()
        main.setCentralWidget(QtWidgets.QLabel('Reviewer'))
        main.resize(1000, 700)
        config = {}
        class Config:
            def getConfig(self, package): return copy.deepcopy(config)
            def writeConfig(self, package, value): config.update(copy.deepcopy(value))
        main.addonManager = Config()
        class Dock(QtWidgets.QDockWidget):
            allow_close = False
            close_attempts = 0
            def closeEvent(self, event):
                self.close_attempts += 1
                if self.allow_close: super().closeEvent(event)
                else: event.ignore()
        panes = []
        for index in range(2):
            dock = Dock('Same document title', main)
            dock.setObjectName('incremento_pdf_reference_' + str(index))
            dock.card_id = 42 + index
            dock.note = {'Title': 'Same document title'}
            dock.path = Path(sys.argv[1]) / (str(index) + '.pdf')
            dock.path.write_bytes(b'Unchanged synthetic document')
            dock.setWidget(QtWidgets.QTextEdit('Unsaved text ' + str(index)))
            main.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, dock)
            panes.append(dock)
        others = []
        for index in range(2):
            other = QtWidgets.QDockWidget('Other addon ' + str(index), main)
            other.setObjectName('other_addon_' + str(index))
            other.setWidget(QtWidgets.QLabel('Other tools'))
            main.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, other)
            others.append(other)
        main.tabifyDockWidget(*others)
        main.show(); app.processEvents()
        class Session:
            def capture(self, docks, done):
                done([dict(name=d.objectName(), kind='pdf_reference', card_id=d.card_id) for d in docks])
            def restore(self, entries, current, done):
                for entry in entries:
                    dock = next(d for d in panes if d.card_id == entry['card_id'])
                    dock.setObjectName(entry['name'])
                done(panes, 0)
        manager = WorkspaceLayouts(main, session=Session(), profile=lambda: 'Synthetic')
        manager.enable_dragging()
        assert manager.arrange('tabs')
        app.processEvents()
        def tab_bar():
            return next(bar for bar in main.findChildren(QtWidgets.QTabBar)
                        if bar.count() and manager._tabs.dock_for(bar, 0) in panes)
        bar = tab_bar()
        assert bar.tabsClosable(), 'Workspace tabs must expose close buttons'
        unrelated = next(b for b in main.findChildren(QtWidgets.QTabBar)
                         if any('Other addon' in b.tabText(i) for i in range(b.count())))
        assert not unrelated.tabsClosable(), 'Other addon tabs must remain untouched'
        # Duplicate titles and native tab reordering must not confuse the target.
        bar.moveTab(0, 1)
        bar.setCurrentIndex(0); app.processEvents()
        active = next(d for d in panes if not d.visibleRegion().isEmpty())
        inactive = next(d for d in panes if d is not active)
        def menu_action(index, label, answer=None):
            bar = tab_bar()
            def choose(menu, position):
                action = next(a for a in menu.actions() if a.text() == label)
                assert action.isEnabled()
                return action
            with patch.object(QtWidgets.QMenu, 'exec', choose), patch.object(
                    QtWidgets.QInputDialog, 'getText', return_value=answer):
                bar.customContextMenuRequested.emit(bar.tabRect(index).center())
            app.processEvents()
        menu_action(1, 'Rename tab…', ('Study & notes', True))
        assert bar.tabText(1) == 'Study & notes'
        assert bar.currentIndex() == 0 and not active.visibleRegion().isEmpty()
        # Native dock captions also display the alias; source metadata stays canonical.
        assert inactive.windowTitle() == 'Study & notes'
        assert inactive.note == {'Title': 'Same document title'}
        with patch.object(QtWidgets.QInputDialog, 'getText', return_value=('Double-click label', True)) as prompt:
            QtTest.QTest.mouseDClick(bar, QtCore.Qt.MouseButton.LeftButton,
                QtCore.Qt.KeyboardModifier.NoModifier, bar.tabRect(1).center())
            app.processEvents()
            assert prompt.call_count == 1
        assert bar.tabText(1) == 'Double-click label' and not inactive.isFloating()
        menu_action(1, 'Rename tab…', ('Study & notes', True))
        # Reader title updates may refresh native tabs but cannot erase an alias.
        inactive.setWindowTitle('Updated document title'); app.processEvents()
        assert bar.tabText(1) == 'Study & notes'
        for answer in [('Cancelled', False), ('', True), ('x'*81, True)]:
            menu_action(1, 'Rename tab…', answer)
            assert bar.tabText(1) == 'Study & notes'
        menu_action(1, 'Reset tab name')
        assert bar.tabText(1) == 'Updated document title'
        menu_action(1, 'Rename tab…', ('Side notes', True))
        saved = []
        manager.save_named('Desk', saved.append)
        assert saved == [True]
        entry = next(p for p in config['workspace_layouts']['Synthetic']['Desk']['panes']
                     if p.get('tab_name') == 'Side notes')
        assert entry['kind'] == 'pdf_reference'
        menu_action(1, 'Rename tab…', ('Temporary label', True))
        manager.load_named('Desk'); app.processEvents()
        bar = tab_bar()
        assert 'Side notes' in [bar.tabText(i) for i in range(bar.count())]
        # Refreshing/renaming repeatedly must not install duplicate close handlers.
        index = next(i for i in range(bar.count()) if bar.tabText(i) == 'Side notes')
        bar.setCurrentIndex(1-index); app.processEvents()
        def click_close():
            button = bar.tabButton(index, QtWidgets.QTabBar.ButtonPosition.RightSide)
            if button is None: button = bar.tabButton(index, QtWidgets.QTabBar.ButtonPosition.LeftSide)
            assert button is not None and button.isVisible()
            QtTest.QTest.mouseClick(button, QtCore.Qt.MouseButton.LeftButton)
            app.processEvents()
        click_close()
        assert inactive.close_attempts == 1 and not inactive.isHidden(), 'A cancelled close keeps the tab'
        assert not active.visibleRegion().isEmpty()
        inactive.allow_close = True
        click_close()
        assert inactive.close_attempts == 2 and inactive.isHidden()
        assert not active.isHidden() and active.close_attempts == 0
        assert all(d.path.read_bytes() == b'Unchanged synthetic document' for d in panes)
        assert all(d.note == {'Title': 'Same document title'} for d in panes)
        assert {d.widget().toPlainText() for d in panes} == {'Unsaved text 0', 'Unsaved text 1'}
        manager.reset()
        assert all(not getattr(d, '_workspace_tab_name', '') for d in panes)
        for d in panes: d.allow_close = True
        main.close()
        from PyQt6 import sip
        if not sip.isdeleted(main):
            sip.delete(main)
    ''')
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr
