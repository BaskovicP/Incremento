"""The writing margin and native editor keep source links through real edits."""
import pytest

from tests.test_writing_tabs_qt import run_tabs


def test_updating_arrow_positions_keeps_the_writing_preview_debounced():
    run_tabs('''
        from backend.writing_links import create_link, list_links
        dock = open_draft(11, 'Draft')
        source = dict(kind='pdf', card_id=7, page=3, quote='Original passage.')
        anchor = create_link(temporary.name, 'Synthetic', source, 11, source_title='Book')
        writing.insert_linked_excerpt(source, anchor)
        writing._flush_editor_state()
        dock._source_margin.set_rows(list_links(temporary.name, 'Synthetic', writing_card_id=11))
        before = dock._preview.toPlainText()
        dock._editor.document().find('Original passage.').insertText('Edited passage.')
        dock._preview_timer.stop()
        dock._source_margin._render_timer.timeout.emit()
        assert dock._preview.toPlainText() == before, 'Positioning an arrow must not re-render the preview on each keystroke'
        dock._preview_timer.timeout.emit()
        assert 'Edited passage.' in dock._preview.toPlainText()
        writing.reset_for_profile_switch()
    ''')


def test_preview_source_arrow_remains_legible_in_dark_theme():
    run_tabs('''
        from backend.writing_links import create_link, list_links
        from PyQt6.QtGui import QColor, QPalette
        palette = app.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor('#22272f'))
        palette.setColor(QPalette.ColorRole.WindowText, QColor('#eeeeee'))
        palette.setColor(QPalette.ColorRole.Text, QColor('#eeeeee'))
        palette.setColor(QPalette.ColorRole.Base, QColor('#252b34'))
        app.setPalette(palette)
        dock = open_draft(11, 'Draft')
        dock.setPalette(palette)
        writing._style_writing_workspace(dock.widget())
        assert dock._preview.palette().color(QPalette.ColorRole.Base).lightness() < 128
        source = dict(kind='pdf', card_id=7, page=3, quote='A linked passage.')
        anchor = create_link(temporary.name, 'Synthetic', source, 11, source_title='Book')
        writing.insert_linked_excerpt(source, anchor)
        writing._flush_editor_state()
        dock._source_margin.set_rows(list_links(temporary.name, 'Synthetic', writing_card_id=11))
        writing._refresh_markdown_preview()
        arrow = dock._preview.document().find('↗')
        assert not arrow.isNull()
        assert arrow.charFormat().anchorHref() == 'inc://source/' + anchor
        assert arrow.charFormat().foreground().color().lightness() >= 150
        writing.reset_for_profile_switch()
    ''')


@pytest.mark.parametrize('floating', [False, True], ids=['docked', 'floating'])
def test_compact_source_arrows_follow_the_excerpt_and_open_its_source_without_changing_prose(floating):
    run_tabs(f'        floating = {floating!r}\n' + '''
        from backend.writing_links import create_link, list_links
        from frontend import writing_excerpt_ui as ui
        from PyQt6.QtTest import QTest
        from aqt.qt import Qt, QUrl, QTextCursor, QPoint
        writing.mw.resize(1100, 800)
        writing.mw.show()
        dock = open_draft(11, 'Draft')
        if floating:
            dock.setFloating(True)
            dock.resize(850, 650)
        source = dict(kind='pdf', card_id=7, page=3, quote='An excerpt that remains in the writing.')
        anchor = create_link(temporary.name, 'Synthetic', source, 11, source_title='<Book>')
        writing.insert_linked_excerpt(source, anchor)
        writing._flush_editor_state()
        margin = dock._source_margin
        margin.set_rows(list_links(temporary.name, 'Synthetic', writing_card_id=11))
        app.processEvents()
        arrow = margin.buttons[anchor]
        assert arrow.text() == '↗' and margin.width() <= 36
        end = dock._editor.document().find(ui.marker(anchor))
        end.setPosition(end.selectionStart() - 1)
        rect = dock._editor.cursorRect(end)
        text_y = dock._editor.viewport().mapToGlobal(QPoint(0, rect.center().y())).y()
        arrow_y = arrow.mapToGlobal(QPoint(0, arrow.height() // 2)).y()
        assert abs(text_y - arrow_y) <= 3, 'Arrow must align with its excerpt in screen coordinates'
        assert source['quote'] in dock._editor.toPlainText()
        opened = []
        ui.preview_source = lambda row, **kwargs: opened.append(row['anchor'])
        QTest.mouseClick(arrow, Qt.MouseButton.LeftButton)
        assert opened == [anchor]
        before = dock._editor.toPlainText()
        old_y = arrow.y()
        cursor = QTextCursor(dock._editor.document())
        cursor.insertText('A new paragraph above the excerpt.\\n\\n')
        app.processEvents()
        margin.render()
        assert arrow.y() > old_y, 'The arrow follows its excerpt after edits'
        writing._refresh_markdown_preview()
        assert dock._preview.toPlainText().count(source['quote']) == 1
        assert dock._preview.toPlainText().count('↗') == 1
        dock._preview.anchorClicked.emit(QUrl('inc://source/' + anchor))
        assert opened == [anchor, anchor]
        from types import SimpleNamespace
        external = []
        ui.QDesktopServices = SimpleNamespace(openUrl=external.append)
        margin.follow_preview(QUrl('#research'))
        assert external == [], 'Existing document anchors must keep navigating within the preview'
        margin.follow_preview(QUrl('https://example.com/'))
        assert external == [QUrl('https://example.com/')]
        assert '↗' not in dock._editor.toPlainText(), 'Display arrows must not enter saved Markdown'
        margin.unlink(anchor)
        assert source['quote'] in dock._editor.toPlainText()
        assert anchor not in margin.buttons
        dock._editor.undo()
        margin.render()
        assert anchor in margin.buttons and before in dock._editor.toPlainText()
        writing.reset_for_profile_switch()
    ''')


def test_linked_excerpt_reveal_tracks_paraphrased_paragraphs_and_clears_on_click_or_timeout():
    run_tabs('''
        from backend.writing_links import create_link, strip_markers
        from PyQt6.QtTest import QTest
        from aqt.qt import Qt
        dock = open_draft(11, 'Draft')
        editor = dock._editor
        source = dict(kind='pdf', card_id=7, page=3, quote='First part.\\n\\nSecond part.')
        anchor = create_link(temporary.name, 'Synthetic', source, 11, source_title='Book')
        writing.insert_linked_excerpt(source, anchor)
        editor.document().find('First part.').insertText('Paraphrased first part.')
        writing.jump_to_excerpt(anchor)
        assert editor.textCursor().selectedText() == '', 'Reveal must not leave editable prose selected'
        pulse = [s.cursor.selectedText() for s in editor.extraSelections() if s.cursor.hasSelection()]
        assert pulse == ['Paraphrased first part.\\u2029\\u2029Second part.']
        assert 'incremento-excerpt' not in strip_markers(editor.toPlainText())
        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton)
        assert not any(s.cursor.hasSelection() for s in editor.extraSelections())
        writing.jump_to_excerpt(anchor)
        editor._excerpt_timer.timeout.emit()
        assert not any(s.cursor.hasSelection() for s in editor.extraSelections())
        writing.jump_to_excerpt(anchor)
        open_draft(22, 'Other')
        assert not any(s.cursor.hasSelection() for s in editor.extraSelections())
        writing.reset_for_profile_switch()
    ''')


def test_send_appends_at_end_without_replacing_text_and_margin_returns_to_the_source():
    run_tabs('''
        from backend.writing_links import create_link, list_links, marker
        dock = open_draft(11, 'Draft')
        dock._editor.setPlainText('Before. After.')
        cursor = dock._editor.textCursor()
        cursor.setPosition(8)
        dock._editor.setTextCursor(cursor)
        source = dict(kind='pdf', card_id=7, page=3, scroll=.4, quote='Original passage')
        anchor = create_link(temporary.name, 'Synthetic', source, 11, source_title='<Book>')
        assert writing.insert_linked_excerpt(source, anchor)
        text = dock._editor.toPlainText()
        assert text.index('Before.') < text.index('After.') < text.index('Original passage')
        assert marker(anchor) in text
        assert writing._flush_editor_state()
        rows = list_links(temporary.name, 'Synthetic', writing_card_id=11)
        assert len(rows) == 1
        dock._source_margin.set_rows(rows)
        assert not dock._source_margin.isHidden()
        assert dock._source_margin.width() <= 36
        buttons = list(dock._source_margin.buttons.values())
        assert len(buttons) == 1 and buttons[0].text() == '↗'
        assert '&lt;Book&gt;' in buttons[0].toolTip() and 'Original passage' in buttons[0].toolTip()
        writing._refresh_markdown_preview()
        assert 'incremento-excerpt' not in dock._preview.toPlainText()
        assert '↗' in dock._preview.toPlainText()
        dock._editor.undo()
        assert dock._editor.toPlainText() == 'Before. After.'
        assert writing._flush_editor_state()
        assert list_links(temporary.name, 'Synthetic', source=source) == []
        dock._editor.redo()
        assert writing._flush_editor_state()
        assert list_links(temporary.name, 'Synthetic', source=source)[0]['anchor'] == anchor
        open_draft(22, 'Other draft')
        assert dock._source_margin.isHidden(), 'Another tab must not inherit source links'
        writing.reset_for_profile_switch()
    ''')


def test_paraphrasing_retains_marker_and_source_but_explicit_unlink_keeps_the_text():
    run_tabs('''
        from backend.writing_links import create_link, marker, list_links
        dock = open_draft(11, 'Draft')
        source = dict(kind='epub', card_id=7, section=2, offset=30, quote='Original passage')
        anchor = create_link(temporary.name, 'Synthetic', source, 11, source_title='Book')
        writing.insert_linked_excerpt(source, anchor)
        writing._flush_editor_state()
        doc = dock._editor.document()
        cursor = doc.find('Original passage')
        cursor.insertText('My own wording')
        assert marker(anchor) in dock._editor.toPlainText()
        writing._flush_editor_state()
        rows = list_links(temporary.name, 'Synthetic', writing_card_id=11)
        dock._source_margin.set_rows(rows)
        dock._source_margin.unlink(anchor)
        assert 'My own wording' in dock._editor.toPlainText()
        assert marker(anchor) not in dock._editor.toPlainText()
        writing._flush_editor_state()
        assert list_links(temporary.name, 'Synthetic', source=source) == []
        writing.reset_for_profile_switch()
    ''')


def test_async_send_captures_target_and_rejects_tab_profile_and_source_changes():
    run_tabs('''
        from frontend import writing_excerpt_ui as ui
        from backend.writing_links import list_links
        from types import SimpleNamespace
        pending = []
        class Query:
            def __init__(self, **kw): self.kw = kw
            def failure(self, cb): self.failed = cb; return self
            def run_in_background(self): pending.append(self)
        class Note(dict):
            def note_type(self): return {'name': 'Incremento Writing'}
        ui.QueryOp = Query
        ui.mw = writing.mw
        ui.refresh_readers = lambda: None
        ui.resolve_document = lambda *args: {'title': 'Source book'}
        writing.mw.col = SimpleNamespace(get_card=lambda cid: SimpleNamespace(nid=cid),
            get_note=lambda nid: Note(Title='Draft', Markdown_File=f'writing/{nid}.md'))
        writing.mw.show()
        dock = open_draft(11, 'Draft')
        pending.clear()
        source = dict(kind='pdf', card_id=7, page=3, scroll=.4, quote='Captured passage')
        alive = [True]
        for retire in ('tab', 'profile', 'source'):
            open_draft(11, 'Draft'); pending.clear()
            ui.send_to_writing(source, is_current=lambda: alive[0])
            operation = pending.pop()
            result = operation.kw['op'](writing.mw.col)
            if retire == 'tab':
                open_draft(22, 'Other')
            elif retire == 'profile':
                paths.set_active_profile('Other')
            else:
                alive[0] = False
            operation.kw['success'](result)
            assert 'Captured passage' not in dock._editor.toPlainText()
            assert list_links(temporary.name, 'Synthetic', source=source) == []
            paths.set_active_profile('Synthetic'); alive[0] = True
        open_draft(11, 'Draft'); pending.clear()
        dock._editor.selectAll()
        before = dock._editor.toPlainText()
        ui.send_to_writing(source)
        operation = pending.pop()
        operation.kw['success'](operation.kw['op'](writing.mw.col))
        assert before in dock._editor.toPlainText(), 'An existing selection must not be replaced'
        assert 'Captured passage' in dock._editor.toPlainText()
        assert len(list_links(temporary.name, 'Synthetic', source=source)) == 1
        writing.reset_for_profile_switch()
    ''')


def test_source_margin_load_cannot_populate_a_different_tab_after_background_read():
    run_tabs('''
        from frontend import writing_excerpt_ui as ui
        from types import SimpleNamespace
        pending = []
        class Query:
            def __init__(self, **kw): self.kw = kw
            def failure(self, cb): return self
            def run_in_background(self): pending.append(self)
        ui.QueryOp = Query
        writing.mw.col = SimpleNamespace()
        dock = open_draft(11, 'Draft')
        operation = pending.pop()
        open_draft(22, 'Other')
        operation.kw['success']([dict(anchor='a'*32, source_title='Wrong book',
            source=dict(kind='pdf', card_id=7, page=3, quote='Wrong passage'), writing_card_id=11)])
        assert dock._source_margin.isHidden() and not dock._source_margin.rows
        writing.reset_for_profile_switch()
    ''')


def test_source_preview_at_the_writing_cursor_uses_its_excerpt_and_menu_never_truncates():
    run_tabs('''
        from frontend import writing_excerpt_ui as ui
        from backend.writing_links import create_link, list_links
        from aqt.qt import QMenu
        dock = open_draft(11, 'Draft')
        sources = [dict(kind='pdf', card_id=7, page=page, quote=f'Passage {page}') for page in (3, 9)]
        for source in sources:
            anchor = create_link(temporary.name, 'Synthetic', source, 11, source_title='Book')
            writing.insert_linked_excerpt(source, anchor)
        writing._flush_editor_state()
        dock._source_margin.set_rows(list_links(temporary.name, 'Synthetic', writing_card_id=11))
        opened = []
        ui.preview_source = lambda row, **kw: opened.append(row['source']['page'])
        dock._editor.setTextCursor(dock._editor.document().find('Passage 3'))
        dock._source_margin.preview_at_cursor()
        dock._editor.setTextCursor(dock._editor.document().find('Passage 9'))
        dock._source_margin.preview_at_cursor()
        assert opened == [3, 9]
        menu = QMenu()
        ui.add_context_actions(menu, dict(sources[0], quote='x' * 2001))
        send = next(action for action in menu.actions() if action.objectName() == 'incremento_send_to_writing')
        assert not send.isEnabled() and '2,000' in send.toolTip()
        writing.reset_for_profile_switch()
    ''')


def test_excerpt_metadata_is_hidden_in_the_editor_and_does_not_add_words():
    run_tabs('''
        from backend.writing_links import create_link, marker
        dock = open_draft(11, 'Draft')
        source = dict(kind='pdf', card_id=7, page=3, quote='Two words')
        anchor = create_link(temporary.name, 'Synthetic', source, 11, source_title='Book')
        writing.insert_linked_excerpt(source, anchor)
        dock.show(); app.processEvents()
        block = dock._editor.document().find(marker(anchor)).block()
        formats = block.layout().formats()
        assert any(fmt.format.foreground().color().alpha() == 0 for fmt in formats), 'Source metadata must not appear as prose'
        assert writing._count_words('Two words' + marker(anchor)) == 2
        dock._editor.selectAll()
        assert 'incremento-excerpt' not in dock._editor.createMimeDataFromSelection().text()
        assert 'incremento-excerpt' not in writing.get_selected_text()
        writing.reset_for_profile_switch()
    ''')


def test_backlink_cannot_create_a_missing_file_or_open_a_profile_escape():
    run_tabs('''
        from frontend import writing_excerpt_ui as ui
        from backend.writing_links import create_link, marker, sync_links
        from pathlib import Path
        from types import SimpleNamespace
        dock = open_draft(11, 'Draft')
        ui.mw = writing.mw
        pending = []
        class Query:
            def __init__(self, **kw): self.kw = kw
            def failure(self, cb): return self
            def run_in_background(self): pending.append(self)
        class Note(dict):
            def note_type(self): return {'name': 'Incremento Writing'}
        ui.QueryOp = Query
        writing.mw.col = SimpleNamespace(get_card=lambda cid: SimpleNamespace(nid=cid),
            get_note=lambda nid: Note(Title='Draft', Markdown_File='writing/11.md'))
        source = dict(kind='pdf', card_id=7, page=3, quote='Original passage')
        anchor = create_link(temporary.name, 'Synthetic', source, 11, source_title='Book')
        sync_links(temporary.name, 'Synthetic', 11, marker(anchor))
        path = Path(temporary.name)/'user_files/Synthetic/writing/11.md'
        path.unlink()
        outside = Path(temporary.name)/'outside.md'
        outside.write_text('Preserve this file')
        for mode in ('missing', 'escape'):
            if mode == 'escape': path.symlink_to(outside)
            ui.open_backlink(source, anchor)
            operation = pending.pop()
            try:
                operation.kw['op'](writing.mw.col)
            except ValueError:
                pass
            else:
                raise AssertionError('A missing or escaping writing target must be unavailable')
            assert outside.read_text() == 'Preserve this file'
        path.unlink()
        path.write_text('Recovered draft')
        writing.reset_for_profile_switch()
    ''')


def test_backlink_jump_places_an_editable_cursor_in_the_excerpt_without_selecting_its_anchor():
    run_tabs('''
        from frontend import writing_excerpt_ui as ui
        from backend.writing_links import create_link, marker, list_links
        dock = open_draft(11, 'Draft')
        anchors = []
        for page in (3, 9):
            source = dict(kind='pdf', card_id=7, page=page, quote=f'Passage {page}')
            anchor = create_link(temporary.name, 'Synthetic', source, 11, source_title='Book')
            anchors.append(anchor)
            writing.insert_linked_excerpt(source, anchor)
        writing._flush_editor_state()
        dock._source_margin.set_rows(list_links(temporary.name, 'Synthetic', writing_card_id=11))
        assert writing.jump_to_excerpt(anchors[0])
        cursor = dock._editor.textCursor()
        assert not cursor.hasSelection()
        assert cursor.block().text() == 'Passage 3'
        opened = []
        ui.preview_source = lambda row, **kw: opened.append(row['source']['page'])
        dock._source_margin.preview_at_cursor()
        assert opened == [3]
        dock._editor.insertPlainText('Rephrased: ')
        writing._flush_editor_state()
        assert marker(anchors[0]) in dock._editor.toPlainText()
        assert len(list_links(temporary.name, 'Synthetic', writing_card_id=11)) == 2
        writing.reset_for_profile_switch()
    ''')
