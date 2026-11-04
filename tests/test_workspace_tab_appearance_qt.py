"""Tab appearance survives native tab recreation without changing source documents."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


@pytest.mark.parametrize('theme', ['native', 'styled'])
def test_right_click_resizes_group_and_colors_individual_tabs_with_saved_workspace_restore(tmp_path, theme):
    script = dedent('''
        import copy, sys, types
        from unittest.mock import patch
        from PyQt6 import QtCore, QtGui, QtWidgets, QtTest
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtGui, QtWidgets):
            for name in dir(module): setattr(qt, name, getattr(module, name))
        sys.modules['aqt'] = types.ModuleType('aqt')
        sys.modules['aqt.qt'] = qt
        from frontend.workspace import WorkspaceLayouts
        app = QtWidgets.QApplication([])
        if sys.argv[1] == 'styled':
            app.setStyleSheet('QTabBar::tab { background:#333333; color:white; border:1px solid #555555; '
                'padding:4px 8px; min-width:8ex; } QTabBar::tab:selected { background:#225599; }')
        main = QtWidgets.QMainWindow()
        main.setCentralWidget(QtWidgets.QLabel('Reviewer'))
        main.resize(1200, 700)
        config = {}
        class Config:
            def getConfig(self, package): return copy.deepcopy(config)
            def writeConfig(self, package, value): config.update(copy.deepcopy(value))
        main.addonManager = Config()
        panes = []
        for i in range(2):
            dock = QtWidgets.QDockWidget('Same title', main)
            dock.setObjectName('incremento_pdf_reference_' + str(i))
            dock.card_id = i + 42
            dock.setWidget(QtWidgets.QTextEdit('Unsaved document ' + str(i)))
            main.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, dock)
            panes.append(dock)
        others = [QtWidgets.QDockWidget('Other addon ' + str(i), main) for i in range(2)]
        for other in others:
            other.setWidget(QtWidgets.QLabel('Unrelated tool'))
            main.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, other)
        main.tabifyDockWidget(*others)
        class Session:
            def capture(self, docks, done):
                done([dict(name=d.objectName(), kind='pdf_reference', card_id=d.card_id) for d in docks])
            def restore(self, entries, current, done):
                for entry in entries:
                    next(d for d in panes if d.card_id == entry['card_id']).setObjectName(entry['name'])
                done(panes, 0)
        manager = WorkspaceLayouts(main, session=Session(), profile=lambda: 'Synthetic')
        main.show(); app.processEvents()
        manager.enable_dragging(); manager.arrange('tabs'); app.processEvents()
        def bar():
            return next(b for b in main.findChildren(QtWidgets.QTabBar)
                        if b.count() and manager._tabs.dock_for(b, 0) is not None)
        def index(dock):
            return next(i for i in range(bar().count()) if manager._tabs.dock_for(bar(), i) is dock)
        def menu_action(dock, label):
            b = bar()
            def choose(menu, position):
                action = next(a for a in menu.actions() if a.text() == label)
                assert action.isEnabled()
                return action
            with patch.object(QtWidgets.QMenu, 'exec', choose):
                b.customContextMenuRequested.emit(b.tabRect(index(dock)).center())
            app.processEvents()
        def resize(dialog):
            fields = {s.accessibleName(): s for s in dialog.findChildren(QtWidgets.QSpinBox)}
            fields['Width (px):'].setValue(220)
            fields['Height (px):'].setValue(44)
            return QtWidgets.QDialog.DialogCode.Accepted
        with patch.object(QtWidgets.QDialog, 'exec', resize):
            menu_action(panes[1], 'Resize tabs…')
        assert all(220 <= bar().tabRect(i).width() <= 224 for i in range(2))
        assert all(44 <= bar().tabRect(i).height() <= 48 for i in range(2))
        for dock, color in zip(panes, ['#fff2a8', '#163552']):
            with patch.object(QtWidgets.QColorDialog, 'getColor', return_value=QtGui.QColor(color)):
                menu_action(dock, 'Tab color…')
        def background(dock):
            # Fixed widths may overflow the dock area; use native tab scrolling
            # before sampling the tab rather than its overflow arrow buttons.
            bar().setCurrentIndex(index(dock))
            app.processEvents()
            rect = bar().tabRect(index(dock))
            image = bar().grab().toImage()
            ratio = image.devicePixelRatio()
            return image.pixelColor(round((rect.left()+8)*ratio), round((rect.top()+8)*ratio)).name()
        assert background(panes[0]) == '#fff2a8'
        assert background(panes[1]) == '#163552'
        unrelated = next(b for b in main.findChildren(QtWidgets.QTabBar) if b is not bar())
        assert not unrelated.styleSheet() and not unrelated.tabsClosable()
        bar().moveTab(0, 1); app.processEvents()
        assert background(panes[0]) == '#fff2a8' and background(panes[1]) == '#163552'
        with patch.object(QtWidgets.QColorDialog, 'getColor', return_value=QtGui.QColor()):
            menu_action(panes[0], 'Tab color…')
        with patch.object(QtWidgets.QDialog, 'exec', return_value=QtWidgets.QDialog.DialogCode.Rejected):
            menu_action(panes[0], 'Resize tabs…')
        assert background(panes[0]) == '#fff2a8' and bar().tabRect(0).width() >= 220
        saved = []
        manager.save_named('Desk', saved.append)
        assert saved == [True]
        entries = config['workspace_layouts']['Synthetic']['Desk']['panes']
        assert all(e['tab_size'] == [220, 44] for e in entries)
        assert {e['tab_color'] for e in entries} == {'#fff2a8', '#163552'}
        menu_action(panes[0], 'Reset tab color')
        assert background(panes[0]) != '#fff2a8' and background(panes[1]) == '#163552'
        menu_action(panes[1], 'Reset tab size')
        assert bar().tabRect(0).width() < 220
        manager.load_named('Desk'); app.processEvents()
        assert background(panes[0]) == '#fff2a8' and background(panes[1]) == '#163552'
        assert all(bar().tabRect(i).width() >= 220 for i in range(2))
        # A new pane inherits group dimensions, but never another tab's color.
        new = QtWidgets.QDockWidget('New search', main)
        new.setObjectName('incremento_search_dock_new')
        new.setWidget(QtWidgets.QLabel('New search content'))
        main.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, new)
        new.show(); app.processEvents(); app.processEvents()
        assert 220 <= bar().tabRect(index(new)).width() <= 224
        assert background(new) not in ('#fff2a8', '#163552')
        with patch.object(QtWidgets.QColorDialog, 'getColor', return_value=QtGui.QColor('#b8d9f2')):
            menu_action(new, 'Tab color…')
        b = bar()
        close = b.tabButton(index(new), QtWidgets.QTabBar.ButtonPosition.RightSide)
        if close is None: close = b.tabButton(index(new), QtWidgets.QTabBar.ButtonPosition.LeftSide)
        QtTest.QTest.mouseClick(close, QtCore.Qt.MouseButton.LeftButton); app.processEvents()
        assert new.isHidden() and all(not d.isHidden() for d in panes)
        # A profile reset during a modal picker cannot apply its stale result.
        def stale_color(*args, **kwargs):
            manager.reset()
            return QtGui.QColor('#ff0000')
        with patch.object(QtWidgets.QColorDialog, 'getColor', side_effect=stale_color):
            menu_action(panes[0], 'Tab color…')
        assert all(background(d) not in ('#fff2a8', '#163552', '#ff0000') for d in panes)
        assert all(bar().tabRect(i).width() < 220 for i in range(bar().count()))
        manager.load_named('Desk'); app.processEvents()
        def stale_size(dialog):
            manager.reset()
            return resize(dialog)
        with patch.object(QtWidgets.QDialog, 'exec', stale_size):
            menu_action(panes[0], 'Resize tabs…')
        assert all(bar().tabRect(i).width() < 220 for i in range(bar().count()))
        assert [d.widget().toPlainText() for d in panes] == ['Unsaved document 0', 'Unsaved document 1']
        bar().grab().save(sys.argv[2])
        main.close()
    ''')
    result = subprocess.run([sys.executable, '-c', script, theme, str(tmp_path / 'tabs.png')],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr
