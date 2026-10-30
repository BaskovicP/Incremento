"""PDF name edits through the real Qt bookshelf and a disposable Anki collection."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent, indent

import pytest


ROOT = Path(__file__).resolve().parents[1]
SETUP = """
import os, sys, tempfile, types
from concurrent.futures import Future
from pathlib import Path
from anki.collection import Collection
from aqt.qt import QApplication, QInputDialog
import aqt.operations

package = types.ModuleType('incremento')
package.__path__ = [os.getcwd()]
sys.modules['incremento'] = package
from incremento.frontend import pdf_bookshelf as shelf

app = QApplication([])
temporary = tempfile.TemporaryDirectory()
col = Collection(str(Path(temporary.name) / 'collection.anki2'))
model = col.models.new('Incremento PDF')
for name in ('Title', 'PDF_Filename', 'PDF_Cover', 'Incremento_Source_Title'):
    col.models.add_field(model, col.models.new_field(name))
template = col.models.new_template('PDF')
template.update(qfmt='{{Title}}', afmt='{{Title}}')
col.models.add_template(model, template)
col.models.add(model)

def add(title):
    note = col.new_note(model)
    note['Title'] = title
    note['PDF_Filename'] = 'original_managed_file.pdf'
    note['Incremento_Source_Title'] = 'Original provenance'
    col.add_note(note, col.decks.id('Default'))
    return note

first, second = add('First book'), add('Deep_Knowledge_Ways')
profile = ['Captured']
background, operations, notices, prompts = [], [], [], []
shelf._active_profile = lambda: profile[0]
shelf.get_all_priorities = lambda *_args: {}
shelf.configured_priority_lower_is_more_important = lambda: True
shelf._load_pdf_metadata_titles = lambda *_args, **_kwargs: {}
shelf.mw = types.SimpleNamespace(col=col, taskman=types.SimpleNamespace(
    run_in_background=lambda work, done, **_kwargs: background.append((work, done))))
shelf.tooltip = lambda message, **_kwargs: notices.append(message)
reply = ['Deep Knowledge Ways', True]
def prompt(*args, **kwargs):
    prompts.append((args, kwargs))
    return tuple(reply)
QInputDialog.getText = prompt

class Operation:
    def __init__(self, parent, op):
        self.op = op
    def success(self, callback):
        self.done = callback
        return self
    def failure(self, callback):
        self.failed = callback
        return self
    def run_in_background(self):
        operations.append(self)
    def finish(self):
        try:
            changes = self.op(col)
        except Exception as error:
            self.failed(error)
        else:
            self.done(changes)
aqt.operations.CollectionOp = Operation

entries = shelf._load_bookshelf_entries('/synthetic', collection=col, profile='Captured')
dialog = shelf._DocumentBookshelfDialog(addon_dir='/synthetic', entries=entries)
target = next(entry for entry in entries if entry.note_id == second.id)
def ids():
    return [dialog._list.item(i).data(shelf.Qt.ItemDataRole.UserRole).note_id
            for i in range(dialog._list.count())]
def search(text):
    dialog._search.setText(text)
    dialog._filter_timer.timeout.emit()
"""


def run_scenario(body):
    script = dedent(SETUP) + "\ntry:\n" + indent(dedent(body).strip(), "    ")
    script += "\nfinally:\n    dialog.reject()\n    col.close()\n    temporary.cleanup()\n"
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("selection_only", [False, True], ids=["bookshelf", "open-pdf-window"])
def test_right_click_edits_clicked_pdf_name_and_refreshes_search_with_native_undo(selection_only):
    run_scenario("""
        dialog._selection_only = SELECTION_ONLY
        menus = []
        class Menu:
            def __init__(self, parent):
                self.actions = []
                menus.append(self)
            def addAction(self, label):
                from aqt.qt import QAction
                action = QAction(label, dialog)
                self.actions.append(action)
                return action
            def addSeparator(self): pass
            def exec(self, position): pass
        shelf.QMenu = Menu
        clicked = next(dialog._list.item(i) for i in range(dialog._list.count())
                       if dialog._list.item(i).data(shelf.Qt.ItemDataRole.UserRole) == target)
        dialog._list.setCurrentRow(1)  # The right-clicked tile owns the action.
        dialog._show_context_menu(dialog._list.visualItemRect(clicked).center())
        actions = [action for action in menus[-1].actions if action.text() == 'Edit PDF name…']
        assert len(actions) == 1, 'PDF context menu needs Edit PDF name'
        actions[0].trigger()
        assert prompts[-1][1]['text'] == 'Deep_Knowledge_Ways'
        assert col.get_note(second.id)['Title'] == 'Deep_Knowledge_Ways'
        assert len(operations) == 1
        operations.pop().finish()
        assert col.get_note(second.id)['Title'] == 'Deep Knowledge Ways'
        assert col.get_note(first.id)['Title'] == 'First book'
        search('Deep Knowledge')
        assert ids() == [second.id]
        assert col.find_notes('"Title:Deep Knowledge Ways"') == [second.id]
        reloaded = shelf._load_bookshelf_entries('/synthetic', collection=col, profile='Captured')
        assert next(e.title for e in reloaded if e.note_id == second.id) == 'Deep Knowledge Ways'
        note = col.get_note(second.id)
        assert note['PDF_Filename'] == 'original_managed_file.pdf'
        assert note['Incremento_Source_Title'] == 'Original provenance'
        col.undo()
        assert col.get_note(second.id)['Title'] == 'Deep_Knowledge_Ways'
        col.redo()
        assert col.get_note(second.id)['Title'] == 'Deep Knowledge Ways'
        assert notices == []
    """.replace("SELECTION_ONLY", repr(selection_only)))


def test_pdf_name_edit_cancels_or_rejects_invalid_input_without_writing():
    run_scenario("""
        for text, accepted in [('Cancelled', False), ('  ', True), ('x' * 2001, True), ('Bad\\x00name', True),
                               ('Deep_Knowledge_Ways', True)]:
            reply[:] = [text, accepted]
            dialog._edit_pdf_name(target)
            assert operations == []
            assert col.get_note(second.id)['Title'] == 'Deep_Knowledge_Ways'
        reply[:] = ['Hall & Guyton <notes>', True]
        dialog._edit_pdf_name(target)
        operations.pop().finish()
        assert col.get_note(second.id)['Title'] == 'Hall &amp; Guyton &lt;notes&gt;'
        reloaded = shelf._load_bookshelf_entries('/synthetic', collection=col, profile='Captured')
        assert next(e.title for e in reloaded if e.note_id == second.id) == 'Hall & Guyton <notes>'
        search('Hall & Guyton <notes>')
        assert ids() == [second.id]
    """)


def test_pdf_name_edit_rejects_stale_operations_and_preserves_title_during_metadata_scan():
    run_scenario("""
        dialog._start_pdf_metadata_scan()
        old_scan = background[-1]
        dialog._edit_pdf_name(target)
        operations.pop().finish()
        future = Future()
        future.set_result(old_scan[0]())
        old_scan[1](future)
        search('Deep Knowledge')
        assert ids() == [second.id], 'Old metadata results must not undo the edited name'

        current = next(e for e in dialog._entries if e.note_id == second.id)
        reply[:] = ['A later name', True]
        dialog._edit_pdf_name(current)
        pending = operations.pop()
        profile[0] = 'Other'
        pending.finish()
        assert col.get_note(second.id)['Title'] == 'Deep Knowledge Ways'
        profile[0] = 'Captured'
        dialog._edit_pdf_name(current)
        pending = operations.pop()
        original_col = shelf.mw.col
        shelf.mw.col = object()
        pending.finish()
        assert col.get_note(second.id)['Title'] == 'Deep Knowledge Ways'
        shelf.mw.col = original_col
        dialog._edit_pdf_name(current)
        pending = operations.pop()
        dialog.reject()
        pending.finish()
        assert col.get_note(second.id)['Title'] == 'Deep Knowledge Ways'
    """)


def test_failed_pdf_name_save_keeps_the_stored_name_and_bookshelf_unchanged():
    run_scenario("""
        def cannot_save(note):
            raise RuntimeError('synthetic write failure')
        col.update_note = cannot_save
        dialog._edit_pdf_name(target)
        operations.pop().finish()
        assert col.get_note(second.id)['Title'] == 'Deep_Knowledge_Ways'
        search('Deep_Knowledge')
        assert ids() == [second.id]
        search('Deep Knowledge')
        assert ids() == []
        assert notices == [shelf.t('reader_bookshelf_pdf_name_failed')]
    """)
