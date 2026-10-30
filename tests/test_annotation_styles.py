"""Text-mark styles persist independently of color, notes, and selection geometry."""
import sqlite3

import pytest

import db
import epub_highlights
import pdf_highlights
from db_schema import initialize_schema


STYLES = ('highlight', 'underline', 'squiggly', 'dashed', 'dotted', 'strikeout')


@pytest.mark.parametrize('style', STYLES)
def test_epub_style_survives_resize_recolor_and_reopen(tmp_path, style):
    root, profile = str(tmp_path), 'Synthetic'
    mark = dict(id='mark', sectionIndex=2, startOffset=10, endOffset=25,
                text='Selected passage', color='blue', style=style, note='Keep my note')
    epub_highlights.add_highlight(root, profile, 7, mark)
    # A legacy/stale resize payload lacks style and note; it must preserve both.
    resized = {k: v for k, v in mark.items() if k not in ('style', 'note')}
    resized.update(endOffset=30, color='red')
    assert epub_highlights.update_highlight(root, profile, 7, resized)
    db.close_connection()
    row = epub_highlights.load_highlights(root, profile, 7)[0]
    assert row.get('style', 'highlight') == style
    assert (row['note'], row['endOffset'], row['color']) == ('Keep my note', 30, 'red')


def test_epub_style_edit_is_scoped_and_preserves_note_range_and_color(tmp_path):
    root, profile = str(tmp_path), 'Synthetic'
    mark = dict(id='mark', sectionIndex=2, startOffset=10, endOffset=25,
                text='Passage', color='blue', note='A note', note_html='<p>A note</p>')
    epub_highlights.add_highlight(root, profile, 7, mark)
    assert not epub_highlights.update_highlight_style(root, profile, 8, 'mark', 'dashed')
    assert epub_highlights.update_highlight_style(root, profile, 7, 'mark', 'dashed')
    assert epub_highlights.load_highlights(root, profile, 7) == [{**mark, 'style': 'dashed'}]
    assert epub_highlights.update_highlight(root, profile, 7, {**mark, 'style': 'highlight', 'endOffset': 30})
    assert epub_highlights.load_highlights(root, profile, 7) == [{**mark, 'style': 'dashed', 'endOffset': 30}]


@pytest.mark.parametrize('value', ['url(evil)', '<script>', {}, [], 'future-style'])
def test_invalid_epub_styles_fail_before_writing(tmp_path, value):
    with pytest.raises(ValueError):
        epub_highlights.add_highlight(str(tmp_path), 'Synthetic', 7, {'id': 'bad', 'style': value})
    assert epub_highlights.load_highlights(str(tmp_path), 'Synthetic', 7) == []


@pytest.mark.parametrize('style,kind', zip(STYLES, ('Highlight', 'Underline', 'Squiggly', 'Underline', 'Underline', 'StrikeOut')))
def test_pdf_style_becomes_native_markup_and_survives_stale_resize(tmp_path, style, kind):
    root, profile = str(tmp_path), 'Synthetic'
    mark = dict(id='mark', page=1, color='blue', style=style, text='Passage',
                note='Keep this note', rects=[dict(x=10, y=20, w=80, h=15)])
    pdf_highlights.add_highlight(root, profile, 7, mark)
    loaded = pdf_highlights.load_highlights(root, profile, 7)[0]
    assert loaded['pdf_annotation']['kind'] == kind
    assert loaded['pdf_annotation'].get('incremento_style', 'highlight') == style
    legacy = {k: v for k, v in mark.items() if k not in ('style', 'note')}
    assert pdf_highlights.update_highlight(root, profile, 7, legacy)
    updated = pdf_highlights.load_highlights(root, profile, 7)[0]
    assert updated['pdf_annotation']['kind'] == kind
    assert updated['pdf_annotation']['incremento_style'] == style
    assert updated['note'] == 'Keep this note'


def test_epub_style_migration_preserves_legacy_marks_and_rolls_back_ddl():
    with sqlite3.connect(':memory:') as conn:
        previous = tuple(m for m in db._SCHEMA_MIGRATIONS if m[0] <= 21)
        initialize_schema(conn, bootstrap=db._create_tables, migrations=previous)
        conn.execute("INSERT INTO epub_highlights(id,card_id) VALUES ('legacy',7)")
        conn.commit()

        def fail(connection):
            db._migration_22_annotation_styles(connection)
            raise RuntimeError('Interrupted')

        with pytest.raises(RuntimeError, match='Interrupted'):
            initialize_schema(conn, bootstrap=db._create_tables,
                              migrations=previous + ((22, 'annotation_styles', fail),))
        assert 'style' not in {r[1] for r in conn.execute('PRAGMA table_info(epub_highlights)')}
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 21
        for _ in range(2):
            assert initialize_schema(conn, bootstrap=db._create_tables, migrations=db._SCHEMA_MIGRATIONS) == 23
        assert conn.execute('SELECT id,card_id,style FROM epub_highlights').fetchall() == [('legacy', 7, 'highlight')]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE epub_highlights SET style='unsafe'")


def test_pdf_stale_range_edit_keeps_a_newer_style_from_another_reader(tmp_path):
    root, profile = str(tmp_path), 'Synthetic'
    mark = dict(id='mark', page=1, color='blue', style='highlight', text='Passage',
                note='Keep note', rects=[dict(x=10, y=20, w=80, h=15)])
    pdf_highlights.add_highlight(root, profile, 7, mark)
    stale = pdf_highlights.load_highlights(root, profile, 7)[0]
    assert pdf_highlights.update_highlight(root, profile, 7, {**stale, 'style': 'dashed'})
    assert pdf_highlights.update_highlight(root, profile, 7, {**stale, 'text': 'Resized passage'})
    updated = pdf_highlights.load_highlights(root, profile, 7)[0]
    assert updated['text'] == 'Resized passage'
    assert updated['note'] == 'Keep note'
    assert updated['pdf_annotation']['kind'] == 'Underline'
    assert updated['pdf_annotation']['incremento_style'] == 'dashed'
    assert updated['pdf_annotation']['opacity'] == 1
