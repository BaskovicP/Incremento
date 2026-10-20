"""Run the actual popup offscreen; never attach to a live Anki window."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def _run_popup_script(script):
    result = subprocess.run(
        [sys.executable, "-c", dedent(script)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_fold_button_toggles_every_level_and_saved_places_without_navigating():
    _run_popup_script('''
        from aqt.qt import QApplication, QWidget, QToolButton, Qt
        from PyQt6.QtTest import QTest
        from backend.i18n import initialize_language, t
        from frontend.reader_contents_popup import ReaderContentsPopup

        app = QApplication([])
        parent = QWidget()
        parent.resize(600, 600)
        for language in ('en', 'hr', 'zh-Hans'):
            initialize_language(language)
            for kind, key in (('pdf', 'page'), ('epub', 'section_index')):
                opened = []
                saved = []
                popup = ReaderContentsPopup(parent, entries=[
                    {'title': 'Chapter one', 'depth': 0, key: 1},
                    {'title': 'Overview', 'depth': 1, key: 2},
                    {'title': 'Deep detail', 'depth': 2, key: 3},
                    {'title': 'Chapter two', 'depth': 0, key: 10},
                    {'title': 'Appendix detail', 'depth': 1, key: 11},
                ], bookmarks=[{'label': 'Saved place', 'location': {key: 3}}],
                    current_position=2, kind=kind, is_current=lambda: True,
                    open_entry=opened.append, save_place=saved.append)
                popup.show_at(parent)
                app.processEvents()
                button = popup.findChild(QToolButton, 'ReaderContentsFoldButton')
                assert button is not None, 'Contents needs an expand/collapse-all control'
                branches = [popup._tree.topLevelItem(0),
                    popup._tree.topLevelItem(0).child(0),
                    popup._tree.topLevelItem(1), popup._tree.topLevelItem(2)]
                assert button.accessibleName() == t('reader_contents_expand_all')
                QTest.mouseClick(button, Qt.MouseButton.LeftButton)
                assert all(item.isExpanded() for item in branches)
                assert button.accessibleName() == t('reader_contents_collapse_all')
                assert button.toolTip() == t('reader_contents_collapse_all')
                QTest.mouseClick(button, Qt.MouseButton.LeftButton)
                assert not any(item.isExpanded() for item in branches)
                # Enter must never target a now-hidden child after folding.
                assert popup._tree.currentItem() == branches[0]
                assert button.accessibleName() == t('reader_contents_expand_all')
                # Manual folds keep the global button honest, including mixed states.
                for item in branches:
                    item.setExpanded(True)
                assert button.accessibleName() == t('reader_contents_collapse_all')
                branches[1].setExpanded(False)
                assert button.accessibleName() == t('reader_contents_expand_all')
                button.setFocus()
                QTest.keyClick(button, Qt.Key.Key_Space)
                assert all(item.isExpanded() for item in branches)
                assert popup.isVisible()
                assert opened == [] and saved == []
                popup.close()
        parent.close()
    ''')


def test_search_keeps_matches_visible_and_restores_folds_when_cleared():
    _run_popup_script('''
        from aqt.qt import QApplication, QWidget, QToolButton, Qt
        from PyQt6.QtTest import QTest
        from frontend.reader_contents_popup import ReaderContentsPopup

        app = QApplication([])
        parent = QWidget()
        parent.resize(600, 600)
        opened = []
        popup = ReaderContentsPopup(parent, entries=[
            {'title': 'Chapter one', 'depth': 0, 'page': 1},
            {'title': 'Deep detail', 'depth': 1, 'page': 2},
            {'title': 'Chapter two', 'depth': 0, 'page': 10},
            {'title': 'Other detail', 'depth': 1, 'page': 11},
        ], bookmarks=[{'label': 'Saved detail', 'location': {'page': 3}}],
            current_position=2, kind='pdf', is_current=lambda: True,
            open_entry=opened.append, save_place=lambda label: None)
        popup.show_at(parent)
        app.processEvents()
        button = popup.findChild(QToolButton, 'ReaderContentsFoldButton')
        assert button is not None, 'Contents needs an expand/collapse-all control'
        for state in ((True, False, True), (False, False, False), (True, True, True)):
            for index, expanded in enumerate(state):
                popup._tree.topLevelItem(index).setExpanded(expanded)
            popup._search.setText('detail')
            assert not button.isEnabled(), 'Search results must stay unfolded'
            assert popup._tree.topLevelItemCount() == 3
            assert popup._tree.topLevelItem(2).isExpanded()
            popup._search.setText('no match')
            assert popup._tree.topLevelItemCount() == 0
            popup._search.clear()
            assert button.isEnabled()
            assert tuple(popup._tree.topLevelItem(i).isExpanded() for i in range(3)) == state
        popup._search.setText('Deep detail')
        popup._search.setFocus()
        QTest.keyClick(popup._search, Qt.Key.Key_Down)
        assert popup._tree.hasFocus(), 'Arrow down should move from search into results'
        QTest.keyClick(popup._tree, Qt.Key.Key_Return)
        assert opened == [{'title': 'Deep detail', 'depth': 1, 'page': 2}]
        assert not popup.isVisible()
        parent.close()
    ''')


def test_fold_control_is_hidden_when_there_is_nothing_to_fold():
    _run_popup_script('''
        from aqt.qt import QApplication, QWidget, QToolButton
        from frontend.reader_contents_popup import ReaderContentsPopup

        app = QApplication([])
        parent = QWidget()
        for entries in ([], [{'title': 'Only chapter', 'depth': 0, 'page': 1}]):
            popup = ReaderContentsPopup(parent, entries=entries, bookmarks=[],
                current_position=1, kind='pdf', is_current=lambda: True,
                open_entry=lambda entry: None, save_place=lambda label: None)
            button = popup.findChild(QToolButton, 'ReaderContentsFoldButton')
            assert button is not None, 'Contents needs an expand/collapse-all control'
            assert button.isHidden()
            popup.close()
        parent.close()
    ''')


def test_clearing_search_restores_selection_and_scroll_in_a_long_outline():
    _run_popup_script('''
        from aqt.qt import QApplication, QWidget, QAbstractItemView, Qt
        from frontend.reader_contents_popup import ReaderContentsPopup

        app = QApplication([])
        parent = QWidget()
        parent.resize(600, 600)
        popup = ReaderContentsPopup(parent, entries=[
            {'title': 'Repeated chapter title', 'depth': i % 2, 'page': i + 1}
            for i in range(120)
        ], bookmarks=[], current_position=1, kind='pdf', is_current=lambda: True,
            open_entry=lambda entry: None, save_place=lambda label: None)
        popup.show_at(parent)
        popup._fold_button.click()
        app.processEvents()
        selected = popup._tree.topLevelItem(20).child(0)
        popup._tree.setCurrentItem(selected)
        popup._tree.scrollToItem(selected, QAbstractItemView.ScrollHint.PositionAtCenter)
        app.processEvents()
        before = popup._tree.verticalScrollBar().value()
        assert before > 0
        popup._search.setText('no matching chapter')
        app.processEvents()
        popup._search.clear()
        app.processEvents()
        assert popup._tree.currentItem().data(0, Qt.ItemDataRole.UserRole)['page'] == 42
        assert popup._tree.verticalScrollBar().value() == before
        popup.close()
        parent.close()
    ''')


def test_contents_popup_search_navigation_escape_and_stale_document_guard():
    script = dedent('''
        from aqt.qt import QApplication, QWidget, QPoint, Qt
        from PyQt6.QtTest import QTest
        from backend.i18n import initialize_language
        from frontend.reader_contents_popup import ReaderContentsPopup

        app = QApplication([])
        parent = QWidget()
        parent.resize(600, 600)
        parent.show()
        for language in ('en', 'hr', 'zh-Hans'):
            initialize_language(language)
            opened = []
            current = [True]
            entries = [
                {'title': 'Chapter <one>', 'depth': 0, 'page': 1, 'id': 0},
                {'title': 'A detail', 'depth': 1, 'page': 2, 'id': 1},
                {'title': 'Chapter two', 'depth': 0, 'page': 10, 'id': 2},
            ]
            popup = ReaderContentsPopup(parent, entries=entries,
                bookmarks=[{'label': 'Contents page', 'location': {'page': 3, 'scroll_ratio': .5}}],
                current_position=2, kind='pdf', is_current=lambda: current[0],
                open_entry=opened.append, save_place=lambda label: None)
            assert not popup.isVisible()
            popup.show_at(parent)
            app.processEvents()
            assert popup.isVisible()
            assert popup._tree.currentItem().text(0) == '• A detail'
            assert popup._tree.currentItem().parent().isExpanded()
            chapter = popup._tree.topLevelItem(0)
            chapter.setExpanded(False)
            app.processEvents()
            rect = popup._tree.visualItemRect(chapter)
            QTest.mouseClick(popup._tree.viewport(), Qt.MouseButton.LeftButton,
                pos=QPoint(max(1, rect.left() - 7), rect.center().y()))
            assert chapter.isExpanded()
            assert opened == []
            assert popup.isVisible()
            popup._search.setText('two')
            assert popup._tree.topLevelItemCount() == 1
            popup._search.returnPressed.emit()
            assert opened == [entries[2]]
            assert not popup.isVisible()
            popup.show_at(parent)
            popup._search.setText('Contents page')
            popup._search.returnPressed.emit()
            assert opened[-1] == {'page': 3, 'scroll_ratio': .5, 'saved_place': True}
            popup.show_at(parent)
            app.processEvents()
            QTest.keyClick(popup._search, Qt.Key.Key_Escape)
            app.processEvents()
            assert not popup.isVisible()
            current[0] = False
            popup._search.setText('two')
            popup._activate(popup._tree.topLevelItem(0))
            assert len(opened) == 2
            popup.close()
        parent.close()
    ''')
    result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
