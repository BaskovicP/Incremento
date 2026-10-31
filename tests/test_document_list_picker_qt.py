"""List membership choices remain reviewable and local until accepted."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


def test_search_button_and_enter_filter_categories_without_accepting_or_losing_selected_lists(tmp_path):
    script = dedent('''
        import sys, types
        from pathlib import Path
        from aqt.qt import QApplication, QDialog, Qt
        from PyQt6.QtTest import QTest
        package = types.ModuleType('incremento')
        package.__path__ = [str(Path.cwd())]
        sys.modules['incremento'] = package
        from incremento.backend import paths
        from incremento.frontend.document_details import DocumentListPickerDialog
        app = QApplication([])
        paths.set_active_profile('Captured')
        picker = DocumentListPickerDialog(sys.argv[1], 'Captured',
            [(1, 'Argentina'), (2, 'Physics'), (3, 'Philosophy')], [1])
        picker.show()
        picker._search.setText('pHyS')
        picker._selected.setFocus()
        app.processEvents()
        picker._search_button.click()
        app.processEvents()
        assert picker._search.hasFocus()
        visible = lambda: [picker._lists.item(i).text() for i in range(picker._lists.count())
                           if not picker._lists.item(i).isHidden()]
        assert visible() == ['Physics']
        assert picker.selected_list_ids == [1]
        QTest.keyClick(picker._search, Qt.Key.Key_Return)
        assert picker.isVisible() and picker.result() == QDialog.DialogCode.Rejected
        assert visible() == ['Physics']
        picker._search.clear()
        picker._search_button.click()
        assert visible() == ['Argentina', 'Physics', 'Philosophy']
        assert picker.selected_list_ids == [1]
        picker.reject()
        assert not (Path(sys.argv[1]) / 'user_files').exists()
    ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("outcome", ["accept", "cancel", "profile-switch"])
def test_list_picker_search_keeps_selected_categories_visible_and_only_applies_on_accept(tmp_path, outcome):
    script = dedent('''
        import sys, types
        from pathlib import Path
        from aqt.qt import QApplication, QTimer, Qt
        package = types.ModuleType('incremento')
        package.__path__ = [str(Path.cwd())]
        sys.modules['incremento'] = package
        from incremento.backend import paths, document_lists as library
        from incremento.frontend.document_details import BookDetailsEditor
        app = QApplication([])
        root, outcome = sys.argv[1:]
        paths.set_active_profile('Captured')
        choices = [(i + 1, f'Category {i:03}') for i in range(500)]
        editor = BookDetailsEditor(root, 'Captured', available_lists=choices)
        editor.set_details({'reason': 'Keep this reason', 'source': 'Keep this source', 'list_ids': [1, 500]})
        before = editor.raw_details()
        changes = []
        opened = []
        editor.changed.connect(lambda: changes.append(editor.raw_details()))
        def choose():
            opened.append(True)
            picker = app.activeModalWidget()
            picker._search.setText('category 025')
            visible = [picker._lists.item(i) for i in range(picker._lists.count())
                       if not picker._lists.item(i).isHidden()]
            assert [item.data(Qt.ItemDataRole.UserRole) for item in visible] == [26]
            assert {picker._selected.item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(picker._selected.count())} == {1, 500}
            visible[0].setCheckState(Qt.CheckState.Checked)
            picker._search.setText('no matching categories')
            assert picker.selected_list_ids == [1, 26, 500]
            assert picker._selected.count() == 3
            picker._selected.setCurrentRow(0)
            picker._remove_button.click()
            assert picker.selected_list_ids == [26, 500]
            assert editor.raw_details() == before  # Changes are staged inside the picker.
            if outcome == 'profile-switch':
                paths.set_active_profile('Other')
                picker.accept()
            elif outcome == 'cancel':
                picker.reject()
            else:
                picker.accept()
        QTimer.singleShot(0, choose)
        editor._edit_lists.click()
        assert opened == [True]
        expected = {**before, 'list_ids': [26, 500]} if outcome == 'accept' else before
        assert editor.raw_details() == expected
        assert changes == ([expected] if outcome == 'accept' else [])
        assert not (Path(root) / 'user_files').exists()
        editor.close()
    ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path), outcome],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_list_picker_creates_and_selects_a_new_category_without_losing_hidden_choices(tmp_path):
    script = dedent('''
        import sys, types
        from pathlib import Path
        from aqt.qt import QApplication, QInputDialog, QTimer, Qt
        package = types.ModuleType('incremento')
        package.__path__ = [str(Path.cwd())]
        sys.modules['incremento'] = package
        from incremento.backend import paths, document_lists as library
        from incremento.frontend.document_details import BookDetailsEditor
        app = QApplication([])
        root = sys.argv[1]
        paths.set_active_profile('Captured')
        first = library.create_document_list(root, 'Captured', 'Argentina')
        second = library.create_document_list(root, 'Captured', 'Wikipedia')
        editor = BookDetailsEditor(root, 'Captured')
        editor.set_details({'list_ids': [first, second]})
        QInputDialog.getText = lambda *a, **kw: ('Politics', True)
        def choose():
            picker = app.activeModalWidget()
            picker._search.setText('Music')
            picker._new_button.click()
            assert picker._selected.count() == 3
            assert picker._search.text() == ''
            picker.accept()
        QTimer.singleShot(0, choose)
        editor._edit_lists.click()
        ids = dict((name, key) for key, name in library.get_document_lists(root, 'Captured'))
        assert editor.details()['list_ids'] == sorted(ids.values())
        assert 'Politics' in editor._list_summary.text()
        assert library.load_document_library(root, 'Captured')['books'] == {}
        editor.close()
    ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_list_picker_blocks_accepting_more_than_the_membership_limit(tmp_path):
    script = dedent('''
        import sys, types
        from pathlib import Path
        from aqt.qt import QApplication, QDialog, Qt
        package = types.ModuleType('incremento')
        package.__path__ = [str(Path.cwd())]
        sys.modules['incremento'] = package
        from incremento.backend import paths
        from incremento.frontend.document_details import DocumentListPickerDialog
        app = QApplication([])
        paths.set_active_profile('Captured')
        choices = [(i, f'Category {i}') for i in range(1, 66)]
        picker = DocumentListPickerDialog(sys.argv[1], 'Captured', choices, list(range(1, 66)))
        picker.show()
        assert not picker._ok_button.isEnabled()
        picker.accept()
        assert picker.isVisible() and picker.result() == QDialog.DialogCode.Rejected
        picker._lists.item(64).setCheckState(Qt.CheckState.Unchecked)
        assert picker._ok_button.isEnabled()
        picker.accept()
        assert picker.result() == QDialog.DialogCode.Accepted
        assert picker.selected_list_ids == list(range(1, 65))
        assert not (Path(sys.argv[1]) / 'user_files').exists()
    ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_many_selected_lists_keep_the_book_details_summary_compact_without_losing_memberships(tmp_path):
    script = dedent('''
        import sys, types
        from pathlib import Path
        from aqt.qt import QApplication
        package = types.ModuleType('incremento')
        package.__path__ = [str(Path.cwd())]
        sys.modules['incremento'] = package
        from incremento.frontend.document_details import BookDetailsEditor
        app = QApplication([])
        names = [(i, f'Category {i}: ' + 'A long category name ' * 3) for i in range(1, 65)]
        editor = BookDetailsEditor(sys.argv[1], 'Captured', available_lists=names)
        editor.set_details({'list_ids': list(range(1, 65))})
        assert editor.details()['list_ids'] == list(range(1, 65))
        summary = editor._list_summary.text()
        assert '+61 more' in summary
        assert len(summary) < 300
        editor.close()
    ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
