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


def _note_image():
    import base64
    import struct
    import zlib

    def chunk(kind, value):
        return struct.pack('>I', len(value)) + kind + value + struct.pack('>I', zlib.crc32(kind + value))

    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 1, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00\x00\xff\x00')) + chunk(b'IEND', b'')
    return 'data:image/png;base64,' + base64.b64encode(png).decode()


def test_embedded_annotation_image_roundtrips_with_caption_and_without_text():
    from annotation_notes import normalize_note, note_display_html

    image = f'<img src="{_note_image()}" width="2" height="1" alt="">'
    markup = f'<p>{image}</p><p>A landmark</p>'
    assert normalize_note('A landmark', markup) == ('A landmark', markup)
    assert note_display_html({'note': '', 'note_html': image}) == image


@pytest.mark.parametrize('source', ['https://example.com/tracker.png', 'file:///tmp/private',
                                    'data:image/svg+xml;base64,PHN2Zz4=', 'data:image/png;base64,YmFk'])
def test_annotation_images_reject_non_raster_or_external_sources(source):
    from annotation_notes import normalize_note

    assert normalize_note('caption', f'<p><img src="{source}" onerror="bad()">caption</p>') == ('caption', '<p>caption</p>')


@pytest.mark.parametrize('module', ['pdf_highlights', 'epub_highlights'])
def test_image_note_survives_save_reopen_and_stale_geometry_update(tmp_path, module):
    store = importlib.import_module(module)
    root = str(tmp_path)
    store.add_highlight(root, 'One', 7, {'id': 'image', 'text': 'source'})
    stale = store.load_highlights(root, 'One', 7)[0]
    markup = f'<p><img src="{_note_image()}" width="2" height="1" alt=""></p>'
    store.update_highlight_note(root, 'One', 7, 'image', '', note_html=markup)
    store.update_highlight(root, 'One', 7, {**stale, 'text': 'resized'})
    assert store.load_highlights(root, 'One', 7)[0]['note_html'] == markup
    assert store.load_highlights(root, 'Two', 7) == []
    store.update_highlight_note(root, 'One', 7, 'image', '', note_html='')
    assert not store.load_highlights(root, 'One', 7)[0].get('note_html')


def test_annotation_image_limits_and_search_preview_preserve_caption_without_side_effects():
    import base64
    from html import escape
    from annotation_notes import image_info, normalize_note, MAX_IMAGE_BYTES
    from search_all_preview import annotation_note_html

    source = _note_image()
    image = f'<img src="{source}" width="2" height="1" alt="">'
    assert annotation_note_html('landmark', image + '<b>landmark</b>', escape) == image + '<b>landmark</b>'
    with pytest.raises(ValueError):
        normalize_note('', image * 5)
    with pytest.raises(ValueError):
        image_info('data:image/png;base64,' + base64.b64encode(b'x' * (MAX_IMAGE_BYTES + 1)).decode())
    raw = bytearray(base64.b64decode(source.split(',')[1]))
    raw[16:20] = (10_000).to_bytes(4, 'big')
    with pytest.raises(ValueError):
        image_info('data:image/png;base64,' + base64.b64encode(raw).decode())


def test_stretched_image_dimensions_remain_bounded_and_survive_normalization():
    from annotation_notes import normalize_note

    image = f'<img src="{_note_image()}" width="120" height="80" alt="">'
    assert normalize_note('caption', image + '<p>caption</p>')[1] == image + '<p>caption</p>'


@pytest.mark.parametrize('side', ['left', 'right'])
def test_image_wrapping_and_centered_own_line_are_preserved_without_arbitrary_css(side):
    from annotation_notes import normalize_note
    from search_all_preview import annotation_note_html
    from html import escape

    image = f'<img src="{_note_image()}" width="120" height="80" alt="" style="float:{side}">'
    markup = '<p>' + image + 'Caption</p>'
    assert normalize_note('Caption', markup) == ('Caption', markup)
    assert markup in annotation_note_html('Caption', markup, escape)
    own_line = '<p align="center">' + image.replace(f' style="float:{side}"', '') + '</p><p>Caption</p>'
    assert normalize_note('Caption', own_line) == ('Caption', own_line)
    hostile = markup.replace(f'float:{side}', 'position:fixed;background-image:url(https://example.com/track)')
    assert 'style=' not in normalize_note('Caption', hostile)[1]


@pytest.mark.parametrize('alignment', ['left', 'center', 'right'])
def test_own_line_image_alignment_roundtrips_without_changing_caption(alignment):
    from annotation_notes import normalize_note
    from search_all_preview import annotation_note_html
    from html import escape

    markup = f'<p align="{alignment}"><img src="{_note_image()}" width="120" height="80" alt=""></p><p>Caption</p>'
    assert normalize_note('Caption', markup) == ('Caption', markup)
    assert annotation_note_html('Caption', markup, escape) == markup


@pytest.mark.parametrize('module', ['pdf_highlights', 'epub_highlights'])
def test_modeless_note_save_rejects_conflicts_or_deleted_targets_without_overwriting(tmp_path, module):
    store = importlib.import_module(module)
    root = str(tmp_path)
    store.add_highlight(root, 'One', 7, {'id': 'h', 'text': 'source', 'note': 'Original', 'note_html': '<b>Original</b>'})
    expected = ('Original', '<b>Original</b>')
    saved = store.update_highlight_note(root, 'One', 7, 'h', 'First edit', note_html='<i>First edit</i>', expected_note=expected)
    assert saved['note'] == 'First edit'
    stale = store.update_highlight_note(root, 'One', 7, 'h', 'Stale edit', note_html='<b>Stale edit</b>', expected_note=expected)
    assert stale is None
    assert store.load_highlights(root, 'One', 7)[0]['note'] == 'First edit'
    store.remove_highlight(root, 'One', 7, 'h')
    assert store.update_highlight_note(root, 'One', 7, 'h', 'Deleted target', expected_note=('First edit', '<i>First edit</i>')) is None
    assert store.load_highlights(root, 'One', 7) == []
    assert store.load_highlights(root, 'Two', 7) == []


@pytest.mark.parametrize('module', ['pdf_highlights', 'epub_highlights'])
@pytest.mark.parametrize('text_changed', [False, True], ids=['formatting-only', 'text-and-formatting'])
def test_modeless_save_is_atomic_when_another_writer_changes_the_note_during_validation(tmp_path, monkeypatch, module, text_changed):
    store = importlib.import_module(module)
    root = str(tmp_path)
    store.add_highlight(root, 'One', 7, {'id': 'h', 'note': 'Original'})
    connection = store.get_connection(root, 'One')
    concurrent_note = 'Concurrent edit' if text_changed else 'Original'
    concurrent_html = f'<b>{concurrent_note}</b>'

    class RacingConnection:
        raced = False

        def __enter__(self):
            connection.__enter__()
            return self

        def __exit__(self, *args):
            return connection.__exit__(*args)

        def execute(self, sql, args=()):
            if sql.startswith('UPDATE') and not self.raced:
                self.raced = True
                connection.execute(f'UPDATE {module} SET note=?, note_html=? WHERE card_id=? AND id=?',
                                   (concurrent_note, concurrent_html, 7, 'h'))
                connection.commit()
            return connection.execute(sql, args)

    racing = RacingConnection()
    monkeypatch.setattr(store, 'get_connection', lambda *args: racing)
    assert store.update_highlight_note(root, 'One', 7, 'h', 'Stale draft', expected_note=('Original', '')) is None
    assert connection.execute(f'SELECT note, note_html FROM {module} WHERE id=?', ('h',)).fetchone() == (
        concurrent_note, concurrent_html)
