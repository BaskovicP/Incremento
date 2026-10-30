"""Real Qt interactions, entirely offscreen and in disposable profiles."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


def test_bookshelf_edits_shared_document_notes_filters_lists_and_keeps_import_drafts(tmp_path):
    script = dedent('''
        import sys, types
        from pathlib import Path
        from aqt.qt import QApplication, QInputDialog, QMessageBox, Qt
        package = types.ModuleType('incremento')
        package.__path__ = [str(Path.cwd())]
        sys.modules['incremento'] = package
        from incremento.backend import document_lists as library, paths
        from incremento.frontend import pdf_bookshelf as shelf
        from incremento.frontend.document_details import ImportBookDetails
        app = QApplication([])
        root = sys.argv[1]
        paths.set_active_profile('Captured')
        shelf._active_profile = paths.get_active_profile
        shelf.configured_priority_lower_is_more_important = lambda: True
        shelf._start = None
        shelf.mw = types.SimpleNamespace(col=types.SimpleNamespace(media=types.SimpleNamespace(dir=lambda:root)),
            taskman=types.SimpleNamespace(run_in_background=lambda *a, **k:None))
        biology=library.create_document_list(root,'Captured','Biology')
        psychology=library.create_document_list(root,'Captured','Psychology')
        entries=[shelf._BookshelfEntry('Behave',1,'PDF',source_filename='shared.pdf'),
                 shelf._BookshelfEntry('A second card for Behave',2,'PDF',source_filename='shared.pdf'),
                 shelf._BookshelfEntry('An EPUB',3,'EPUB',source_filename='other.epub')]
        dialog=shelf._DocumentBookshelfDialog(addon_dir=root,entries=entries)
        editor=dialog._book_details
        assert dialog._splitter.count()==3
        editor._reason.setPlainText('ChatGPT suggested it for biology.')
        editor._source.setText('A blog I liked')
        for i in range(editor._lists.count()):
            editor._lists.item(i).setCheckState(Qt.CheckState.Checked)
        dialog._save_book_details()
        details=library.load_document_library(root,'Captured')['books'][('pdf','shared.pdf')]
        assert details['list_ids']==[biology,psychology]
        assert details['reason']=='ChatGPT suggested it for biology.'
        assert {e.saved_reason for e in dialog._entries if e.source_filename=='shared.pdf'}=={details['reason']}
        for i in range(dialog._list_sidebar.count()):
            if dialog._list_sidebar.item(i).data(Qt.ItemDataRole.UserRole)==biology:
                dialog._list_sidebar.setCurrentRow(i)
        assert dialog._list.count()==2
        dialog._search.setText('ChatGPT')
        dialog._filter_timer.timeout.emit()
        assert dialog._list.count()==2
        editor._reason.setPlainText('An unsaved edit')
        dialog._list.setCurrentRow(1)
        assert editor._reason.toPlainText()=='An unsaved edit'
        paths.set_active_profile('Other')
        dialog._save_book_details()
        assert library.load_document_library(root,'Captured')['books'][('pdf','shared.pdf')]==details
        paths.set_active_profile('Captured')
        dialog._save_book_details()
        assert dialog._list.count()==0  # The saved reason no longer matches ChatGPT.
        dialog._search.clear()
        dialog._filter_timer.timeout.emit()
        editor._reason.setPlainText('Keep this draft until I choose Save')
        QMessageBox.question=lambda *a,**kw:QMessageBox.StandardButton.Cancel
        dialog._accept_reference(beside=False)
        assert dialog.reference_mode=='main'
        assert not dialog._pdf_metadata_cancelled.is_set()
        assert library.load_document_library(root,'Captured')['books'][('pdf','shared.pdf')]['reason']=='An unsaved edit'
        QMessageBox.question=lambda *a,**kw:QMessageBox.StandardButton.Save
        dialog.reject()
        assert library.load_document_library(root,'Captured')['books'][('pdf','shared.pdf')]['reason']=='Keep this draft until I choose Save'

        imports=ImportBookDetails(root,'Captured')
        imports.set_path('one.pdf')
        imports._reason.setPlainText('First reason')
        imports._source.setText('First source')
        imports.set_path('two.epub')
        assert imports._reason.toPlainText()==''
        imports._reason.setPlainText('Second reason')
        imports.set_path('one.pdf')
        assert imports._reason.toPlainText()=='First reason'
        assert imports.for_path('two.epub')['reason']=='Second reason'
        assert imports.for_path('one.pdf')['source']=='First source'
        imports.close()
    ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ,"QT_QPA_PLATFORM":"offscreen"},
        capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("kind", ["pdf", "epub"])
def test_native_import_dialog_passes_each_files_details_to_its_manager(tmp_path, kind):
    script = dedent('''
        import importlib, sys, types
        from pathlib import Path
        import aqt
        from aqt.qt import QApplication, Qt
        app=QApplication([])
        package=types.ModuleType('incremento')
        package.__path__=[str(Path.cwd())]
        sys.modules['incremento']=package
        root,kind=sys.argv[1:]
        from incremento.backend import paths, document_lists as library, priority_manager
        paths.set_active_profile('Captured')
        col=types.SimpleNamespace(tags=types.SimpleNamespace(all=lambda:[]))
        aqt.mw=types.SimpleNamespace(col=col,taskman=types.SimpleNamespace(run_in_background=lambda *a,**k:None))
        module=importlib.import_module('incremento.frontend.'+kind+'_dialog')
        manager=importlib.import_module('incremento.backend.'+kind+'_manager')
        calls=[]
        setattr(manager,'add_'+kind+'_card',lambda *args,**kwargs:calls.append((args,kwargs)) or len(calls))
        priority_manager.set_priority=lambda *a,**k:None
        cls=getattr(module,'Add'+('Pdf' if kind=='pdf' else 'Epub')+'Dialog')
        dialog=cls(root,deck_names=['Topics'])
        names=[str(Path(root)/('first.'+kind)),str(Path(root)/('second.'+kind))]
        for path in names:
            Path(path).touch()
            dialog._add_paths([path])
        dialog._table.setCurrentCell(0,1)
        editor=dialog._book_details
        editor._reason.setPlainText('Recommended by ChatGPT')
        editor._source.setText('Conversation about biology')
        list_id=library.create_document_list(root,'Captured','Biology')
        editor.reload_lists()
        editor._lists.item(0).setCheckState(Qt.CheckState.Checked)
        dialog._table.setCurrentCell(1,1)
        assert editor._reason.toPlainText()==''
        editor._reason.setPlainText('Found on a favourite blog')
        editor._source.setText('A blog')
        dialog._start_add()
        for _ in range(10):app.processEvents()
        assert len(calls)==2
        assert [args[2] for args,kwargs in calls]==names
        assert [kwargs['profile'] for args,kwargs in calls]==['Captured','Captured']
        assert calls[0][1]['document_details']=={'reason':'Recommended by ChatGPT',
            'source':'Conversation about biology','list_ids':[list_id]}
        assert calls[1][1]['document_details']=={'reason':'Found on a favourite blog',
            'source':'A blog','list_ids':[]}
        dialog.close()
    ''')
    result=subprocess.run([sys.executable,"-c",script,str(tmp_path),kind],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ,"QT_QPA_PLATFORM":"offscreen"},capture_output=True,text=True,timeout=30)
    assert result.returncode == 0,result.stdout+result.stderr
