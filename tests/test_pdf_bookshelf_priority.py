"""Bookshelf priority edits capture the clicked selection and refresh only after an atomic save."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent, indent

import pytest


ROOT = Path(__file__).resolve().parents[1]
SETUP = """
import sys, types, threading
from pathlib import Path
from anki.collection import Collection
from aqt.qt import QApplication, QAction, QItemSelectionModel, Qt
import aqt.operations

package = types.ModuleType('incremento')
package.__path__ = [str(Path.cwd())]
sys.modules['incremento'] = package
from incremento.backend import paths, priority_manager as priorities
from incremento.frontend import pdf_bookshelf as shelf
from incremento.frontend.priority_dialog import PriorityDialog

app = QApplication([])
root = sys.argv[1]
col = Collection(str(Path(root) / 'collection.anki2'))
paths.set_active_profile('Captured')
cards = []
for title in ['Alpha PDF', 'Beta PDF', 'Gamma EPUB']:
    note = col.new_note(col.models.by_name('Basic'))
    note['Front'] = title
    col.add_note(note, col.decks.id('Default'))
    cards.append(note.cards()[0])
for card, value in zip(cards, [10, 20, 30]):
    priorities.set_priority(root, 'Captured', card.id, value)
pending, notices, prompts, menus = [], [], [], []
shelf.mw = types.SimpleNamespace(col=col, taskman=types.SimpleNamespace(
    run_in_background=lambda *a, **kw: None))
shelf.tooltip = lambda message, **kw: notices.append(message)
shelf.configured_priority_lower_is_more_important = lambda: True
shelf._DocumentBookshelfDialog._start_pdf_metadata_scan = lambda self: None
shelf._DocumentBookshelfDialog._start_book_summary_scan = lambda self, entries: None
reply = [7.25, True]
def prompt(self):
    prompts.append(self.priority)
    self._spin.setValue(reply[0])
    return int(reply[1])
PriorityDialog.exec = prompt

class Query:
    def __init__(self, parent, op, success):
        self.op, self.done = op, success
    def failure(self, callback):
        self.failed = callback
        return self
    def run_in_background(self):
        pending.append(self)
    def finish(self):
        try: result = self.op(shelf.mw.col)
        except Exception as error: self.failed(error)
        else: self.done(result)
aqt.operations.QueryOp = Query

entries = [shelf._BookshelfEntry(title, card.id, kind, priority=value, note_id=card.nid,
    source_filename=str(index) + '.' + kind.lower())
    for index, (title, card, kind, value) in enumerate(zip(
        ['Alpha PDF', 'Beta PDF', 'Gamma EPUB'], cards, ['PDF', 'PDF', 'EPUB'], [10, 20, 30]))]
dialog = shelf._DocumentBookshelfDialog(addon_dir=root, entries=entries)
dialog.show()
app.processEvents()

class Menu:
    def __init__(self, parent):
        self.actions = []
        menus.append(self)
    def addAction(self, label):
        action = QAction(label, dialog)
        self.actions.append(action)
        return action
    def addSeparator(self): pass
    def exec(self, position): pass
shelf.QMenu = Menu
def items():
    return {dialog._list.item(i).data(Qt.ItemDataRole.UserRole).card_id: dialog._list.item(i)
            for i in range(dialog._list.count())}
def selected():
    return {e.card_id for e in dialog._selected_library_entries()}
def select(indices):
    dialog._list.clearSelection()
    for index in indices: items()[cards[index].id].setSelected(True)
def priority_action(index):
    item = items()[cards[index].id]
    dialog._show_context_menu(dialog._list.visualItemRect(item).center())
    return next(a for a in menus[-1].actions if a.text() == 'Set Priority…')
def stored():
    return priorities.get_all_priorities(root, 'Captured')
original = stored()
"""


def run_scenario(tmp_path, body):
    script = dedent(SETUP) + "\ntry:\n" + indent(dedent(body).strip(), "    ")
    script += "\nfinally:\n    dialog.reject()\n    col.close()\n"
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)], cwd=ROOT,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("view", ["covers", "reasons"])
def test_bookshelf_right_click_sets_pdf_epub_and_multiple_priorities_and_keeps_selection_and_drafts(tmp_path, view):
    run_scenario(tmp_path, """
        dialog._view_combo.setCurrentIndex(dialog._view_combo.findData(VIEW))
        dialog._sort_combo.setCurrentIndex(dialog._sort_combo.findData('priority'))
        schedule = col.db.all('SELECT id, ivl, due FROM cards ORDER BY id')
        select([0])
        priority_action(2).trigger()  # Right-clicking another tile replaces the old selection.
        assert selected() == {cards[2].id} and prompts == [30]
        assert stored() == original
        pending.pop().finish()
        assert stored() == {**original, cards[2].id: 7.25}
        assert dialog._entries[2].priority == 7.25
        assert list(items())[0] == cards[2].id
        reply[:] = [100, True]
        priority_action(0).trigger()
        assert prompts[-1] == 10, prompts
        pending.pop().finish()
        assert list(items())[-1] == cards[0].id
        select([0, 1])
        key = ('pdf', entries[0].source_filename)
        dialog._book_drafts[key] = {'reason': 'Unsaved reason', 'source': '', 'list_ids': []}
        reply[:] = [0, True]
        priority_action(0).trigger()
        assert selected() == {cards[0].id, cards[1].id} and prompts[-1] == 50
        select([2])  # A pending save keeps the selection from when the menu opened.
        pending.pop().finish()
        assert stored() == {cards[0].id: 0, cards[1].id: 0, cards[2].id: 7.25}
        assert selected() == {cards[2].id}
        assert [e.priority for e in dialog._entries] == [0, 0, 7.25]
        assert dialog._book_drafts[key]['reason'] == 'Unsaved reason'
        assert col.db.all('SELECT id, ivl, due FROM cards ORDER BY id') == schedule
        dialog._book_drafts.clear()
    """.replace("VIEW", repr(view)))


def test_bookshelf_cancel_missing_card_and_failed_batch_preserve_stored_and_displayed_priorities(tmp_path):
    run_scenario(tmp_path, """
        select([0, 1])
        reply[:] = [80, False]
        priority_action(0).trigger()
        assert not pending and stored() == original
        reply[1] = True
        conn = priorities.get_connection(root, 'Captured')
        conn.execute('CREATE TRIGGER reject_priority BEFORE INSERT ON priorities WHEN NEW.card_id='
                     + str(cards[1].id) + " BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
        conn.commit()
        priority_action(0).trigger()
        pending.pop().finish()
        assert stored() == original
        assert [e.priority for e in dialog._entries] == [10, 20, 30]
        assert len(notices) == 1
        conn.execute('DROP TRIGGER reject_priority')
        conn.commit()
        priority_action(0).trigger()
        col.remove_notes([cards[1].nid])
        pending.pop().finish()
        assert stored() == original
        assert [e.priority for e in dialog._entries] == [10, 20, 30]
        assert len(notices) == 2
    """)


@pytest.mark.parametrize("change", ["profile", "collection", "closed"])
@pytest.mark.parametrize("phase", ["queued", "saved"])
def test_bookshelf_priority_drops_stale_workers_and_callbacks(tmp_path, change, phase):
    run_scenario(tmp_path, """
        select([0])
        priority_action(0).trigger()
        operation = pending.pop()
        if PHASE == 'saved': result = operation.op(col)
        if CHANGE == 'profile': paths.set_active_profile('Other')
        elif CHANGE == 'collection': shelf.mw.col = object()
        else: dialog.reject()
        if PHASE == 'saved': operation.done(result)
        else: operation.finish()
        assert stored() == ({**original, cards[0].id: 7.25} if PHASE == 'saved' else original)
        assert [e.priority for e in dialog._entries] == [10, 20, 30]
        assert notices == []
    """.replace("PHASE", repr(phase)).replace("CHANGE", repr(change)))
