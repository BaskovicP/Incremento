"""A deleted supplemental reader must not strand the current study visit."""
from textwrap import dedent

import pytest

from tests.test_study_navigation_qt import run_scene


READERS = '''
from PyQt6 import sip
class Reference(QtWidgets.QDockWidget):
    def __init__(self, snapshot, location=None, **kw):
        super().__init__('Textbook', kw['owner'])
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.closed = False
        self.location = dict(location or {})
        self.state = types.SimpleNamespace(card_id=12, page=kw.get('page', 1),
            scroll_ratio=kw.get('scroll_ratio', .4), zoom=kw.get('zoom', 1), closed=False)
        self.view = QtWidgets.QTextEdit('Passage', self)
        self.setWidget(self.view)
    def closeEvent(self, event):
        self.closed = self.state.closed = True
        super().closeEvent(event)
sys.modules['frontend.pdf_reference_workspace'].ReferenceWindow = Reference
sys.modules['frontend.epub_reference_workspace'] = types.SimpleNamespace(
    EpubReferenceWindow=Reference, _windows=[], _load=lambda *a: dict(title='Geometry'))
if kind == 'epub':
    source = dict(kind='epub', card_id=12, section=2, offset=-1, scroll=.4, quote='')
    document['location'] = row['source'] = recording['source'] = source
bridge('video'); drain(); w = ui._window
passage, player = w.reader, w.player
player.pos = 16.75
player.paused = False
if kind == 'pdf':
    passage.state.page = 8
    passage.state.scroll_ratio = .62
else:
    passage.location.update(section=4, offset=150, scroll=.62)
w.poll_location(); drain()
saved_source = dict(w.source)
'''


@pytest.mark.parametrize('kind', ['pdf', 'epub'])
@pytest.mark.parametrize('deleted', [False, True], ids=['close-pending', 'native-deleted'])
def test_back_to_passage_reopens_a_closed_reader_without_losing_the_review_or_player(kind, deleted):
    run_scene(f'kind = {kind!r}\n' + dedent(READERS) + dedent(f'''
        passage.close()
        if {deleted!r}:
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
            assert sip.isdeleted(passage.view)
        w.back_to_passage(); drain()
        assert w.reader is not passage and not sip.isdeleted(w.reader.view)
        assert w.source == saved_source and w.visit.stage == 'book'
        assert w.book_host.isVisible() and not w.play_host.isVisible()
        assert w.player is player and player.pos == 16.75 and player.paused
        assert player.loads == 1
        assert mw.reviewer.card.id == 41 and mw.reviewer.state == 'question'
        assert web.toPlainText() == 'Original question'
        w.close()
    '''))


def test_old_reader_deferred_deletion_cannot_retire_its_replacement():
    run_scene("kind = 'pdf'\n" + dedent(READERS) + dedent('''
        w.open_document(dict(saved_source, page=9)); drain()
        replacement = w.reader
        assert replacement is not passage
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        assert sip.isdeleted(passage)
        assert w.reader is replacement and not sip.isdeleted(replacement.view)
        w.navigate('video')
        w.back_to_passage(); drain()
        assert w.reader is replacement and w.source['page'] == 9
        w.close()
    '''))


def test_reader_closed_between_polls_recovers_the_latest_position_without_a_stale_excerpt():
    run_scene("kind = 'pdf'\n" + dedent(READERS) + dedent('''
        w.source.update(quote='Selection from the earlier page', page_y=.25)
        passage.state.page = 9
        passage.state.scroll_ratio = .73
        passage.close()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        w.back_to_passage(); drain()
        assert w.reader.state.page == 9 and w.reader.state.scroll_ratio == .73
        assert w.source['quote'] == '' and w.source.get('page_y') is None
        w.close()
    '''))


def test_destroying_the_focused_reader_restores_the_workspace_before_reopening():
    run_scene("kind = 'pdf'\n" + dedent(READERS) + dedent('''
        w.back_to_passage()
        w.enter_focus('book', remember=False)
        assert mw.isFullScreen()
        passage.close()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        assert not mw.isFullScreen() and w.focus_stage is None
        assert w.reader is None and not w.book_host.isVisible()
        w.back_to_passage(); drain()
        assert w.reader is not None and w.source == saved_source
        w.close()
    '''))


def test_reader_recovery_callback_is_discarded_after_a_profile_switch():
    run_scene("kind = 'pdf'\n" + dedent(READERS) + dedent('''
        passage.close()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        w.back_to_passage()
        assert pending, 'Recovering the reader must use the background document loader'
        profile[0] = 'Other'
        w.poll_location(); drain()
        assert w.visit.closed and ui._window is None and w.reader is None
        assert web.isVisible() and web.isEnabled() and bottom.isEnabled()
    '''))
