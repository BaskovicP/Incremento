"""Rich annotation notes retain searchable text and only inert formatting."""
import importlib
import sqlite3

import pytest


def test_note_markup_keeps_common_formatting_and_safe_links():
    from annotation_notes import normalize_note

    markup = '<p><b>Rice</b> <i>theorem</i> <u>note</u> <s>old</s></p><ul><li><a href="https://example.com/?a=1&amp;b=2">Read more</a></li></ul>'
    text, html = normalize_note('Rice theorem note old\nRead more', markup)
    assert text == 'Rice theorem note old\nRead more'
    assert html == markup


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'file:///tmp/private', 'https://user:pass@example.com', 'data:text/html,bad'])
def test_note_markup_drops_active_content_and_unsafe_links(url):
    from annotation_notes import normalize_note

    text, html = normalize_note('visible link', f'<p onclick="bad()">visible <a href="{url}">link</a><img src="https://example.com/x"><script>bad()</script></p>')
    assert text == 'visible link'
    assert html == '<p>visible link</p>'


def test_note_markup_cannot_replace_the_searchable_text_or_interpret_legacy_html():
    from annotation_notes import normalize_note, note_display_html

    assert normalize_note('new note', '<b>stale note</b>') == ('new note', '')
    assert note_display_html({'note': '<b>literal</b>\nnext'}) == '&lt;b&gt;literal&lt;/b&gt;<br>next'


def test_oversized_note_is_rejected_without_truncating_user_text():
    from annotation_notes import MAX_NOTE_CHARS, normalize_note

    with pytest.raises(ValueError):
        normalize_note('x' * (MAX_NOTE_CHARS + 1), '')


@pytest.mark.parametrize('module', ['pdf_highlights', 'epub_highlights'])
def test_rich_note_save_resize_and_clear_are_card_and_profile_scoped(tmp_path, module):
    highlights = importlib.import_module(module)
    root = str(tmp_path)
    highlights.add_highlight(root, 'One', 7, {'id': 'h', 'text': 'source'})
    highlights.add_highlight(root, 'One', 8, {'id': 'other', 'note': 'keep'})
    saved = highlights.update_highlight_note(root, 'One', 7, 'h', 'Bold note', note_html='<p><b>Bold</b> note</p>')
    assert saved['note_html'] == '<p><b>Bold</b> note</p>'
    resized = {**saved, 'text': 'resized source'}
    highlights.update_highlight(root, 'One', 7, resized)
    assert highlights.load_highlights(root, 'One', 7)[0]['note_html'] == saved['note_html']
    assert highlights.load_highlights(root, 'Two', 7) == []
    assert highlights.load_highlights(root, 'One', 8)[0]['note'] == 'keep'
    assert highlights.update_highlight_note(root, 'One', 8, 'h', 'wrong', note_html='<b>wrong</b>') is None
    cleared = highlights.update_highlight_note(root, 'One', 7, 'h', '', note_html='')
    assert cleared['note'] == '' and not cleared.get('note_html')


def test_rich_note_schema_upgrade_preserves_legacy_notes_and_rolls_back_both_columns():
    import db
    from db_schema import initialize_schema

    conn = sqlite3.connect(':memory:')
    previous = tuple(m for m in db._SCHEMA_MIGRATIONS if m[0] <= 20)
    initialize_schema(conn, bootstrap=db._create_tables, migrations=previous)
    conn.execute("INSERT INTO pdf_highlights(id,card_id,note) VALUES ('legacy',7,'<b>literal</b>')")
    conn.commit()

    def fail(connection):
        db._migration_21_annotation_note_formatting(connection)
        raise RuntimeError('rollback')

    with pytest.raises(RuntimeError, match='rollback'):
        initialize_schema(conn, bootstrap=db._create_tables, migrations=previous + ((21, 'rich_notes', fail),))
    for table in ('pdf_highlights', 'epub_highlights'):
        assert 'note_html' not in {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
    assert conn.execute('PRAGMA user_version').fetchone() == (20,)
    initialize_schema(conn, bootstrap=db._create_tables, migrations=db._SCHEMA_MIGRATIONS)
    assert conn.execute('SELECT note,note_html FROM pdf_highlights').fetchone() == ('<b>literal</b>', '')
    conn.close()


@pytest.mark.parametrize('module,kind', [('pdf_highlights', 'pdf_annotations'), ('epub_highlights', 'epub_annotations')])
def test_formatted_note_search_matches_visible_words_and_returns_its_presentation(tmp_path, module, kind):
    from search_repository import search_excerpt_rows

    store = importlib.import_module(module)
    store.add_highlight(str(tmp_path), 'One', 7, {'id': 'h', 'text': 'source', 'note': 'Rice theorem',
                                                'note_html': '<p><b>Rice</b> theorem</p>'})
    rows = search_excerpt_rows(str(tmp_path), 'One', kind, 'Rice theorem')
    assert len(rows) == 1
    assert rows[0][2:] == ('Rice theorem', 'source', 'yellow', '<p><b>Rice</b> theorem</p>')
    assert search_excerpt_rows(str(tmp_path), 'One', kind, 'href') == []


@pytest.mark.parametrize('module', ['pdf_highlights', 'epub_highlights'])
def test_resizing_from_an_older_reader_cannot_erase_a_new_rich_note(tmp_path, module):
    store = importlib.import_module(module)
    root = str(tmp_path)
    store.add_highlight(root, 'One', 7, {'id': 'h', 'text': 'source', 'note': 'old'})
    old_view = store.load_highlights(root, 'One', 7)[0]
    store.update_highlight_note(root, 'One', 7, 'h', 'New note', note_html='<b>New</b> note')
    store.update_highlight(root, 'One', 7, {**old_view, 'text': 'resized source'})
    saved = store.load_highlights(root, 'One', 7)[0]
    assert (saved['text'], saved['note'], saved['note_html']) == ('resized source', 'New note', '<b>New</b> note')


def test_search_note_preview_keeps_formatting_and_query_marks_with_inert_links():
    from html import escape
    from search_all_preview import annotation_note_html

    result = annotation_note_html('Rich result', '<p><b>Rich</b> <a href="https://example.com/">result</a></p>',
                                  lambda text: escape(text).replace('Rich', '<mark>Rich</mark>'))
    assert result == '<p><b><mark>Rich</mark></b> <u>result</u></p>'
