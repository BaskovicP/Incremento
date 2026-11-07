"""Native-tab workflows preserve pane identity, cancellations and profile boundaries."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_switch_search_pin_groups_bulk_close_recovery_navigation_and_session_restore():
    script = dedent('''
        import copy, sys, types
        from unittest.mock import patch
        from PyQt6 import QtCore, QtGui, QtWidgets, QtTest
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtGui, QtWidgets):
            for name in dir(module): setattr(qt, name, getattr(module, name))
        sys.modules['aqt'] = types.ModuleType('aqt'); sys.modules['aqt.qt'] = qt
        from frontend.workspace import WorkspaceLayouts, add_workspace_menu
        app = QtWidgets.QApplication([])
        main = QtWidgets.QMainWindow(); main.resize(1200, 700)
        main.setCentralWidget(QtWidgets.QLabel('Reviewer'))
        config = {}
        class Config:
            def getConfig(self, package): return copy.deepcopy(config)
            def writeConfig(self, package, value): config.update(copy.deepcopy(value))
        main.addonManager = Config()
        profile = ['A']
        panes = []
        class Dock(QtWidgets.QDockWidget):
            allow_close = True
            def closeEvent(self, event):
                if self.allow_close: super().closeEvent(event)
                else: event.ignore()
        def make(cid, name=None):
            dock = Dock('Book ' + str(cid), main)
            dock.setObjectName(name or 'incremento_pdf_reference_' + str(cid))
            dock.cid = cid
            dock.setWidget(QtWidgets.QTextEdit('Unsaved text ' + str(cid)))
            main.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, dock)
            dock.show(); panes.append(dock)
            return dock
        class Session:
            def capture_immediate(self, docks):
                return [dict(name=d.objectName(), kind='pdf_reference', card_id=d.cid, page=7, zoom=1.5) for d in docks]
            def capture(self, docks, done): done(self.capture_immediate(docks))
            def restore(self, entries, current, done):
                if not current(): return
                restored = []
                for e in entries:
                    dock = next((d for d in panes if d.cid == e['card_id'] and not d.isHidden()), None)
                    dock = dock or make(e['card_id'], e['name'])
                    dock.setObjectName(e['name'])
                    restored.append(dock)
                done(restored, 0)
        for cid in range(1, 5): make(cid)
        main.show(); app.processEvents()
        manager = WorkspaceLayouts(main, session=Session(), profile=lambda: profile[0])
        manager.enable_dragging(); manager.arrange('tabs'); app.processEvents()
        tabs = manager._tabs
        registered = {}
        menu = add_workspace_menu(main.menuBar(), manager, lambda: None,
            register_action=lambda key, action: registered.setdefault(key, action))
        assert len(registered) == 14
        def bar():
            return next(b for b in main.findChildren(QtWidgets.QTabBar) if b.count() and tabs.dock_for(b,0))
        def order(): return [tabs.dock_for(bar(),i) for i in range(bar().count())]
        tabs.pin(panes[2], True); app.processEvents()
        assert order()[0] is panes[2], 'Pinned tabs stay first'
        assert not tabs.close(panes[2]) and not panes[2].isHidden()
        bar().moveTab(0,3); tabs.refresh(); app.processEvents()
        assert order()[0] is panes[2], 'Dragging cannot move a pin behind ordinary tabs'
        tabs.set_group(panes[0], 'Reading'); tabs.set_group(panes[1], 'Reading')
        tabs.collapse_group(panes[0], True); app.processEvents()
        grouped = [i for i,d in enumerate(order()) if d in panes[:2]]
        assert sum(bar().isTabVisible(i) for i in grouped) == 1
        assert not any(d.isHidden() for d in panes), 'Collapsing a group cannot close its readers'
        representative = next(i for i in grouped if bar().isTabVisible(i))
        QtTest.QTest.mouseClick(bar(), QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.NoModifier, bar().tabRect(representative).center())
        app.processEvents()
        assert all(bar().isTabVisible(i) for i in grouped)
        tabs.collapse_group(panes[0], True); app.processEvents()
        def switch(dialog):
            field = dialog.findChild(QtWidgets.QLineEdit)
            listing = dialog.findChild(QtWidgets.QListWidget)
            field.setText('book 2'); app.processEvents()
            assert listing.count() == 1 and 'Book 2' in listing.item(0).text()
            field.setText('pdf'); app.processEvents()
            assert listing.count() == 4, 'Search includes type and collapsed members'
            field.setText('book 2'); app.processEvents()
            listing.setCurrentRow(0)
            return QtWidgets.QDialog.DialogCode.Accepted
        with patch.object(QtWidgets.QDialog, 'exec', switch): tabs.show_switcher()
        app.processEvents()
        assert tabs.current() is panes[1]
        assert all(bar().isTabVisible(i) for i in grouped), 'Selecting a hidden group member expands it'
        before = tabs.current(); tabs.navigate(1); app.processEvents()
        assert tabs.current() is not before
        tabs.jump(0); app.processEvents(); assert tabs.current() is panes[2]
        registered['workspace_next_tab'].trigger(); app.processEvents()
        assert tabs.current() is not panes[2]
        registered['workspace_tab_1'].trigger(); app.processEvents()
        assert tabs.current() is panes[2]
        assert not bar().tabIcon(0).isNull()
        assert 'PDF' in bar().tabToolTip(0) and '7' in bar().tabToolTip(0)
        panes[3]._workspace_dirty = True
        panes[3]._workspace_loading = True
        tabs.refresh()
        assert 'Loading' in bar().tabToolTip(order().index(panes[3]))
        panes[3]._workspace_loading = False
        tabs.refresh()
        assert 'Unsaved changes' in bar().tabToolTip(order().index(panes[3]))
        assert panes[3].windowTitle().startswith('* ')
        panes[3]._workspace_dirty = False
        panes[3]._workspace_failed = True
        tabs.refresh()
        assert 'Could not load' in bar().tabToolTip(order().index(panes[3]))
        panes[3]._workspace_failed = False
        tabs.refresh()
        # Close-to-right stops when a pane refuses to discard its draft.
        target = order()[1]; refusing = order()[2]; last = order()[3]
        refusing.allow_close = False
        assert tabs.close_many(target, 'right') == 0
        assert not last.isHidden()
        refusing.allow_close = True
        assert tabs.close_many(target, 'others') == 2
        app.processEvents()
        assert not panes[2].isHidden() and not target.isHidden()
        assert len(manager.visible_panes()) == 2
        assert tabs.reopen(); app.processEvents()
        assert len(manager.visible_panes()) == 3
        restored = [d for d in manager.visible_panes() if d is not panes[2] and d is not target][0]
        assert restored.cid == last.cid
        assert restored.widget().toPlainText() == 'Unsaved text ' + str(last.cid)
        assert tabs.close(restored); app.processEvents()
        assert manager.save_last_session()
        saved = config['workspace_last_sessions']['A']
        assert len(saved['panes']) == 2 and saved['open_as_tabs']
        assert any(e.get('tab_pinned') for e in saved['panes'])
        # A different profile cannot restore or reopen profile A's tabs.
        manager.reset(); profile[0] = 'B'
        assert not tabs.reopen() and not manager.restore_last_session()
        assert config['workspace_last_sessions']['A'] == saved
        profile[0] = 'A'
        assert manager.restore_last_session(); app.processEvents()
        assert any(getattr(d, '_workspace_tab_pinned', False) for d in manager.visible_panes())
        assert order()[0].cid == 3
        manager.reset(); manager.start_profile(); app.processEvents()
        assert any(getattr(d, '_workspace_tab_pinned', False) for d in manager.visible_panes())
        config['workspace_restore_last_session'] = False
        manager.reset(); manager.start_profile(); app.processEvents()
        assert not any(getattr(d, '_workspace_tab_pinned', False) for d in manager.visible_panes())
        assert manager.restore_last_session(); app.processEvents()
        assert any(getattr(d, '_workspace_tab_pinned', False) for d in manager.visible_panes())
        manager.close_profile()
        # Closing every tab must clear the saved session rather than revive it.
        for dock in manager.visible_panes(): dock.close()
        app.processEvents()
        assert manager.save_last_session()
        assert 'A' not in config['workspace_last_sessions']
        main.close()
        from PyQt6 import sip
        if not sip.isdeleted(main):
            sip.delete(main)
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
