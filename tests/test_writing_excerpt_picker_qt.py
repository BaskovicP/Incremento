"""Send to the open writing card, or explicitly choose another existing card."""
import pytest

from tests.test_writing_tabs_qt import run_tabs


_SETUP = '''
from frontend import writing_excerpt_ui as ui, writing_workspace as workspace
from backend.writing_manager import ensure_writing_file, read_writing_text
from backend.writing_links import list_links
from aqt.qt import QMenu
from types import SimpleNamespace
pending, opened = [], []
class Query:
    def __init__(self, **kw): self.kw = kw
    def failure(self, cb): self.failed = cb; return self
    def run_in_background(self): pending.append(self)
class Note(dict):
    def note_type(self): return {'name': 'Incremento Writing'}
notes = {11: Note(Title='Alpha', Markdown_File='writing/11.md'),
         22: Note(Title='Beta', Markdown_File='writing/22.md')}
writing.mw.col = SimpleNamespace(find_cards=lambda query: [11, 22],
    get_card=lambda cid: SimpleNamespace(nid=cid), get_note=lambda nid: notes[nid])
writing.mw.show()
ui.mw = writing.mw
ui.QueryOp = workspace.QueryOp = Query
ui.resolve_document = lambda *args: {'title': 'Source PDF'}
ui.refresh_readers = lambda: None
ui.tooltip = lambda *args, **kwargs: None
for cid, note in notes.items():
    ensure_writing_file(temporary.name, note['Markdown_File'], '# ' + note['Title'], profile='Synthetic')
def open_destination(cid):
    opened.append(cid)
    return writing.show_writing_in_dock(cid, notes[cid]['Title'], notes[cid]['Markdown_File'], keep_open=True)
writing.configure_writing_tab_actions(open_existing=lambda: None, new_writing=lambda: None, open_card=open_destination)
source = dict(kind='pdf', card_id=7, page=4, scroll=.3, quote='Captured PDF passage')
alive = [True]
def drain():
    while pending:
        operation = pending.pop(0)
        operation.kw['success'](operation.kw['op'](writing.mw.col))
def send_menu():
    menu = QMenu()
    ui.add_context_actions(menu, source, is_current=lambda: alive[0])
    return menu, next(action for action in menu.actions() if action.objectName() == 'incremento_send_to_writing')
'''


@pytest.mark.parametrize('already_open', [False, True], ids=['no-writing-pane', 'different-draft-open'])
def test_pdf_send_offers_searchable_existing_cards_and_only_writes_the_chosen_card(already_open):
    run_tabs(_SETUP + f'\nalready_open = {already_open!r}\n' + '''
if already_open:
    open_destination(11)
    drain()
opened.clear()
menu, action = send_menu()
assert action.isEnabled(), 'A writing pane must not be required before choosing a destination'
if already_open:
    action = next(a for a in menu.actions() if a.objectName() == 'incremento_choose_writing')
action.trigger()
drain()
assert not opened, 'No draft may open or change before an explicit choice'
picker = ui._dialogs[-1]
assert isinstance(picker, workspace.WritingPicker) and not picker.isModal()
assert picker.choices.count() == 2
picker.reject()
assert not opened and list_links(temporary.name, 'Synthetic', source=source) == []
action.trigger()
drain()
picker = ui._dialogs[-1]
picker.search.setText('beta')
assert picker.choices.count() == 1 and picker.choices.currentItem().text() == 'Beta'
picker.open_selected()
drain()
assert opened == [22]
assert writing.current_writing_card_id() == 22
assert 'Captured PDF passage' in writing._writing_dock._editor.toPlainText()
assert 'Captured PDF passage' not in read_writing_text(temporary.name, 'writing/11.md', profile='Synthetic')
rows = list_links(temporary.name, 'Synthetic', source=source)
assert len(rows) == 1 and rows[0]['writing_card_id'] == 22
assert rows[0]['source']['page'] == 4 and rows[0]['source']['quote'] == source['quote']
ui.reset()
writing.reset_for_profile_switch()
''')


def test_open_writing_receives_transfer_directly_without_reopening_picker_or_draft():
    run_tabs(_SETUP + '''
open_destination(11)
drain()
opened.clear()
editor = writing._writing_dock._editor
editor.setPlainText('First paragraph.\\n\\nLast paragraph.')
editor.moveCursor(editor.textCursor().MoveOperation.Start)
menu, action = send_menu()
action.trigger()
drain()
assert not opened and not ui._dialogs
assert editor.toPlainText().index('Last paragraph.') < editor.toPlainText().index(source['quote'])
assert len(list_links(temporary.name, 'Synthetic', source=source)) == 1
writing.reset_for_profile_switch()
''')


@pytest.mark.parametrize('retire', ['source', 'profile', 'collection', 'close'])
def test_pdf_destination_picker_drops_stale_or_cancelled_results_without_opening_or_writing(retire):
    run_tabs(_SETUP + f'\nretire = {retire!r}\n' + '''
menu, action = send_menu()
assert action.isEnabled()
action.trigger()
picker = ui._dialogs[-1]
assert isinstance(picker, workspace.WritingPicker)
operation = pending.pop(0)
collection = writing.mw.col
rows = operation.kw['op'](collection)
if retire == 'source': alive[0] = False
elif retire == 'profile': paths.set_active_profile('Other')
elif retire == 'collection': writing.mw.col = object()
else: picker.reject()
operation.kw['success'](rows)
assert picker.choices.count() == 0
picker.open_selected()
assert not opened and writing._writing_dock is None
assert not pending
assert list_links(temporary.name, 'Synthetic', source=source) == []
paths.set_active_profile('Synthetic')
ui.reset()
''')


@pytest.mark.parametrize('unavailable', ['empty-library', 'cannot-open'])
def test_pdf_destination_picker_does_not_create_or_edit_when_no_destination_can_open(unavailable):
    run_tabs(_SETUP + f'\nunavailable = {unavailable!r}\n' + '''
if unavailable == 'empty-library':
    writing.mw.col.find_cards = lambda query: []
else:
    writing._writing_tab_actions['open_card'] = lambda cid: False
menu, action = send_menu()
action.trigger()
drain()
picker = ui._dialogs[-1]
if unavailable == 'empty-library':
    assert picker.choices.count() == 0 and not picker.open_button.isEnabled()
picker.open_selected()
assert not pending and not opened
assert writing._writing_dock is None
assert list_links(temporary.name, 'Synthetic', source=source) == []
ui.reset()
''')
