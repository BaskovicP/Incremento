"""Tabbed workspaces keep their layout when more live panes are opened."""
import ast
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent
from types import SimpleNamespace
from unittest.mock import Mock


def test_new_and_reopened_panes_join_the_group_until_a_split_or_profile_reset():
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
        main.resize(1000, 700)
        profile = ['First']
        manager = WorkspaceLayouts(main, profile=lambda: profile[0])
        def pane(name):
            dock = QtWidgets.QDockWidget(name, main)
            dock.setObjectName('incremento_' + name)
            dock.setWidget(QtWidgets.QTextEdit('Unsaved ' + name))
            main.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, dock)
            return dock
        def wait_until(predicate):
            deadline = QtCore.QDeadlineTimer(1500)
            while not predicate() and not deadline.hasExpired():
                app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 20)
            return predicate()
        first, second = pane('pdf_dock'), pane('pdf_reference_initial')
        main.show(); app.processEvents()
        assert manager.arrange('tabs')
        opened = [first, second]
        for name in ('search_dock', 'epub_dock', 'video_dock', 'web_dock', 'writing_dock', 'add_card_dock', 'local_file_dock'):
            dock = pane(name)
            content = dock.widget()
            dock.setFloating(True); dock.show()
            assert wait_until(lambda: set(main.tabifiedDockWidgets(dock)) == set(opened)), name
            assert not dock.isFloating() and not dock.visibleRegion().isEmpty()
            assert dock.widget() is content and content.toPlainText() == 'Unsaved ' + name
            opened.append(dock)
        # Existing live tabs are retained as each new pane becomes active.
        assert all(not dock.isHidden() for dock in opened)
        assert manager.arrange('columns')
        split = pane('pdf_reference_split')
        split.setFloating(True); split.show(); app.processEvents()
        assert split.isFloating() and not main.tabifiedDockWidgets(split)
        assert manager.restore()
        fresh = pane('pdf_reference_after_restore')
        fresh.setFloating(True); fresh.show()
        assert wait_until(lambda: first in main.tabifiedDockWidgets(fresh))
        assert split.isFloating(), 'Restoring tabs must preserve existing extra floating panes'
        # Closing and reopening a floating pane while grouped puts it in the group.
        split.close(); app.processEvents()
        split.show()
        assert wait_until(lambda: first in main.tabifiedDockWidgets(split))
        unrelated = QtWidgets.QDockWidget('Other addon', main)
        unrelated.setObjectName('other_addon_tools')
        unrelated.setWidget(QtWidgets.QLabel('Other tools'))
        main.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, unrelated)
        unrelated.show(); app.processEvents()
        assert not main.tabifiedDockWidgets(unrelated)
        pending = pane('pdf_reference_old_profile')
        pending.setFloating(True); pending.show()
        profile[0] = 'Second'
        manager.reset()
        # A restored opening preference in the new profile still cannot adopt
        # a pane whose Show event was queued under the previous profile.
        manager.tabbed = True
        app.processEvents()
        assert pending.isFloating(), 'A queued open from the old profile cannot join another profile'
        assert manager.arrange('tabs')
        replacement = WorkspaceLayouts(main, profile=lambda: profile[0])
        after_reload = pane('pdf_reference_after_reload')
        after_reload.setFloating(True); after_reload.show(); app.processEvents()
        assert after_reload.isFloating(), 'A superseded layout controller cannot adopt new panes'
        assert all(d.widget().toPlainText().startswith('Unsaved ') for d in opened)
        main.close()
        from PyQt6 import sip
        if not sip.isdeleted(main):
            sip.delete(main)
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr


def test_saved_single_pane_tabbed_workspace_restores_the_opening_policy():
    script = dedent('''
        import copy, sys, types
        from PyQt6 import QtCore, QtGui, QtWidgets
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtGui, QtWidgets):
            for name in dir(module): setattr(qt, name, getattr(module, name))
        sys.modules['aqt'] = types.ModuleType('aqt'); sys.modules['aqt.qt'] = qt
        from frontend.workspace import WorkspaceLayouts
        app = QtWidgets.QApplication([])
        main = QtWidgets.QMainWindow(); main.setCentralWidget(QtWidgets.QLabel('Reviewer'))
        stored = {}
        class Config:
            def getConfig(self, package): return copy.deepcopy(stored)
            def writeConfig(self, package, value): stored.update(copy.deepcopy(value))
        main.addonManager = Config()
        first = QtWidgets.QDockWidget('Document', main)
        first.setObjectName('incremento_pdf_dock'); first.setWidget(QtWidgets.QTextEdit('Unsaved'))
        main.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, first)
        main.show(); app.processEvents()
        class Session:
            def capture(self, panes, done):
                done([dict(name=first.objectName(), kind='pdf', card_id=42)])
            def restore(self, entries, current, done): done([first], 0)
        manager = WorkspaceLayouts(main, session=Session(), profile=lambda: 'Synthetic')
        assert manager.arrange('tabs')
        saved = []; manager.save_named('Desk', saved.append)
        assert saved == [True] and stored['workspace_layouts']['Synthetic']['Desk']['open_as_tabs'] is True
        assert manager.arrange('columns') and not manager.tabbed
        manager.load_named('Desk'); app.processEvents()
        assert manager.tabbed
        second = QtWidgets.QDockWidget('Web Search', main)
        second.setObjectName('incremento_search_dock'); second.setWidget(QtWidgets.QLabel('Search'))
        main.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, second)
        second.setFloating(True); second.show()
        deadline = QtCore.QDeadlineTimer(1500)
        while first not in main.tabifiedDockWidgets(second) and not deadline.hasExpired():
            app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 20)
        assert main.tabifiedDockWidgets(second) == [first]
        assert first.widget().toPlainText() == 'Unsaved'
        main.close()
        from PyQt6 import sip
        if not sip.isdeleted(main):
            sip.delete(main)
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr


def test_explicit_document_opens_create_tabs_without_replacing_the_main_reader():
    tree = ast.parse((Path(__file__).resolve().parents[1] / '__init__.py').read_text())
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in ('_open_pdf_card', '_open_epub_card')]
    pdf, epub, pdf_reference, epub_reference = Mock(), Mock(), Mock(), Mock()
    namespace = dict(mw=SimpleNamespace(col=SimpleNamespace(
        get_card=lambda cid: SimpleNamespace(nid=cid),
        get_note=lambda nid: {'PDF_Filename': 'source.pdf', 'EPUB_File': 'source.epub'})),
        _workspace_layouts=SimpleNamespace(tabbed=True), _pdf_dock_mod=pdf, _epub_dock_mod=epub,
        _pdf_reference_workspace_mod=pdf_reference, _epub_reference_workspace_mod=epub_reference,
        _active_profile=lambda: 'Synthetic', _ADDON_DIR='/unused', EPUB_FILE_FIELD='EPUB_File',
        get_page=lambda *a: 5, get_zoom=lambda *a: 1.25, get_read_page=lambda *a: 10,
        get_scroll_ratio=lambda *a: .3, get_epub_progress=lambda *a: (2, .4, False))
    exec(compile(ast.Module(body=functions, type_ignores=[]), '<document-open>', 'exec'), namespace)
    namespace['_open_pdf_card'](42)
    namespace['_open_epub_card'](71)
    pdf.show_pdf_in_dock.assert_not_called()
    epub.show_epub_in_dock.assert_not_called()
    assert pdf_reference.open_reference.call_args.args == (42, 5)
    assert pdf_reference.open_reference.call_args.kwargs['new_window'] is True
    assert epub_reference.open_reference.call_args.args[0] == dict(card_id=71, section=2, offset=-1, scroll=.4)
    namespace['_workspace_layouts'].tabbed = False
    namespace['_open_pdf_card'](42)
    namespace['_open_epub_card'](71)
    pdf.show_pdf_in_dock.assert_called_once()
    epub.show_epub_in_dock.assert_called_once()
