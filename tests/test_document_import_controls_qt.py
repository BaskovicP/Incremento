"""Shared import controls preserve each reader's existing Qt behavior."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


def _run_dialog_script(tmp_path, kind, script):
    setup = '''
        import sys
        from types import SimpleNamespace
        import aqt
        from aqt.qt import QApplication, Qt
        app = QApplication([])
        aqt.mw = SimpleNamespace(
            col=SimpleNamespace(tags=SimpleNamespace(all=lambda: [])),
            addonManager=SimpleNamespace(getConfig=lambda *args: {}),
            taskman=SimpleNamespace(run_in_background=lambda *args, **kwargs: None))
        from backend import priority_manager
        sys.modules['priority_manager'] = priority_manager
        from frontend.pdf_dialog import AddPdfDialog
        from frontend.epub_dialog import AddEpubDialog
        kind = sys.argv[2]
        dialog = (AddPdfDialog if kind == 'pdf' else AddEpubDialog)(sys.argv[1])
    '''
    result = subprocess.run(
        [sys.executable, '-c', dedent(setup) + dedent(script), str(tmp_path), kind],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('kind', ['pdf', 'epub'])
def test_filtered_import_removal_and_undo_preserve_order_and_per_file_choices(tmp_path, kind):
    _run_dialog_script(tmp_path, kind, '''
        paths = [f'{title}.{kind}' for title in ('Visible first', 'Hidden second', 'Visible third')]
        dialog._add_paths(paths)
        for index, path in enumerate(paths):
            dialog._tag_edits[path].setTags(['topic', f'file-{index}'])
            dialog._priority_spins[path].setValue(23.4 + index)
            dialog._import_checks[path].setChecked(index != 0)
        dialog._table.selectAll()
        dialog._search_edit.setText('Visible')
        assert all(not dialog._table.isRowHidden(index.row())
                   for index in dialog._table.selectionModel().selectedRows())
        dialog._table.selectAll()
        assert dialog._selected_visible_rows() == [0, 2]
        dialog._remove_selected_rows()
        assert dialog._table.rowCount() == 1
        assert dialog._table.item(0, 1).data(Qt.ItemDataRole.UserRole) == paths[1]
        dialog._undo_remove_rows()
        assert [dialog._table.item(row, 1).data(Qt.ItemDataRole.UserRole)
                for row in range(3)] == paths
        for index, path in enumerate(paths):
            assert dialog._tag_edits[path].tags() == ['topic', f'file-{index}']
            assert dialog._priority_spins[path].value() == 23.4 + index
            assert dialog._import_checks[path].isChecked() == (index != 0)
        dialog._set_visible_import_checks(False)
        assert [dialog._import_checks[path].isChecked() for path in paths] == [False, True, False]
        dialog._search_edit.setText('no matches')
        assert dialog._selected_visible_rows() == []
        assert dialog._nearest_visible_row(0) == -1
        dialog.reject()
    ''')


@pytest.mark.parametrize('kind', ['pdf', 'epub'])
def test_import_progress_labels_and_priority_colors_keep_format_and_language(tmp_path, kind):
    _run_dialog_script(tmp_path, kind, '''
        from backend.i18n import initialize_language, Translator
        progress_key = 'imports_pdf_djvu_progress' if kind == 'pdf' else 'imports_epub_progress'
        detail_key = progress_key + '_detail'
        for locale in ('en', 'hr', 'zh-Hans'):
            initialize_language(locale)
            tr = Translator(locale)
            dialog._start_add_progress(3)
            assert dialog._add_progress.maximum() == 3
            assert dialog._add_progress.format() == tr.t(progress_key, completed=0, total=3)
            dialog._update_add_progress(5, 3, 'book.' + kind, phase='Import')
            assert dialog._add_progress.value() == 3
            assert dialog._add_status_lbl.text() == tr.t(
                detail_key, completed=3, total=3, phase='Import', filename='book.' + kind)
            dialog._finish_add_progress()
            assert dialog._add_progress.isHidden() and dialog._add_status_lbl.isHidden()
            assert dialog._add_total_entries == 0
            dialog._start_add_progress(0)
            adding_key = 'imports_pdf_adding' if kind == 'pdf' else 'imports_epub_adding'
            assert dialog._add_progress.format() == tr.t(adding_key)
            assert dialog._add_progress.isHidden()
        for reverse in (False, True):
            dialog._lower_priority_more_important = not reverse
            spin = dialog._build_priority_spin()
            assert spin.value() == 50 and spin.decimals() == 4 and spin.width() == 94
            for value, color in ((0, '#ff0000'), (8.5, '#ff4400'), (17, '#ff8800'),
                                 (50, '#00cc00'), (100, '#8800cc')):
                spin.setValue(100 - value if reverse else value)
                assert f'background-color: {color};' in spin.styleSheet()
        dialog.reject()
    ''')


@pytest.mark.parametrize('kind,batch', [('pdf', 8), ('epub', 12)])
def test_folder_import_keeps_its_format_specific_batch_size(tmp_path, kind, batch):
    _run_dialog_script(tmp_path, kind, f'''
        from unittest.mock import Mock
        paths = [f'book-{{index}}.{{kind}}' for index in range(20)]
        dialog._folder_pending_paths = list(paths)
        dialog._folder_total_paths = len(paths)
        dialog._folder_progress.setRange(0, len(paths))
        dialog._add_row = Mock()
        dialog._process_folder_queue()
        assert [call.args[0] for call in dialog._add_row.call_args_list] == paths[:{batch}]
        assert dialog._folder_pending_paths == paths[{batch}:]
        assert dialog._folder_progress.value() == {batch}
        label = dialog._folder_status_lbl if kind == 'pdf' else dialog._status_lbl
        assert label.text() == dialog._folder_status_text({batch})
        dialog.reject()
    ''')
