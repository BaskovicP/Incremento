"""Real-PDF interchange contracts; all files and databases belong to tmp_path."""
import importlib.util
import shutil
import sys
import sysconfig
from pathlib import Path

import pytest

# The test harness intentionally exposes backend/statistics.py as "statistics".
# PyMuPDF needs the standard library module during import; restore the harness
# module immediately so the rest of the suite retains its normal dependencies.
_previous_statistics = sys.modules.get('statistics')
_stdlib_spec = importlib.util.spec_from_file_location(
    '_pdf_stdlib_statistics', Path(sysconfig.get_path('stdlib')) / 'statistics.py')
_stdlib_statistics = importlib.util.module_from_spec(_stdlib_spec)
_stdlib_spec.loader.exec_module(_stdlib_statistics)
try:
    sys.modules['statistics'] = _stdlib_statistics
    import pymupdf as fitz
finally:
    if _previous_statistics is None:
        sys.modules.pop('statistics', None)
    else:
        sys.modules['statistics'] = _previous_statistics

import paths
import pdf_annotations as annotations
from pdf_highlights import add_highlight, load_highlights, remove_highlight, update_highlight_note


PROFILE = 'TestProfile'
CARD = 42
FILENAME = 'document.pdf'


def pdf_file(tmp_path, *, rotation=0, crop=False):
    folder = paths.get_pdf_dir(str(tmp_path), PROFILE)
    folder.mkdir(parents=True, exist_ok=True)
    filename = folder / FILENAME
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=500)
        page.insert_text((60, 80), 'A passage with italic text.', fontsize=12)
        page.insert_text((60, 110), 'Another highlighted passage.', fontsize=12)
        if crop:
            page.set_cropbox(fitz.Rect(30, 30, 370, 470))
        page.set_rotation(rotation)
        doc.save(filename)
    return filename


def local_highlight(note='My saved note', hl_id='local'):
    return {'id': hl_id, 'page': 1, 'color': 'yellow', 'text': 'A passage with italic text.',
            'note': note, 'rects': [{'x': 60, 'y': 65, 'w': 150, 'h': 18}]}


def native_rows(filename):
    with fitz.open(filename) as doc:
        return sorted([{'page': i + 1, 'name': a.info['id'], 'kind': a.type[1],
                 'note': a.info['content'], 'vertices': a.vertices}
                for i, page in enumerate(doc) for a in (page.annots() or [])], key=lambda row: (row['page'], row['name']))


def change_pdf(filename, operation):
    temporary = filename.with_suffix('.edited.pdf')
    with fitz.open(filename) as doc:
        operation(doc)
        doc.save(temporary)
    temporary.replace(filename)


def add_native(doc, note='Outside reader note'):
    page = doc[0]
    annot = page.add_highlight_annot(fitz.Rect(60, 95, 210, 113))
    annot.set_info(content=note, title='Outside reader')
    annot.update()


def sync(tmp_path, **kwargs):
    return annotations.sync_pdf_annotations(str(tmp_path), PROFILE, CARD, FILENAME, **kwargs)


def test_incremento_highlight_and_unicode_note_become_one_editable_pdf_annotation(tmp_path):
    filename = pdf_file(tmp_path)
    highlight = local_highlight('Arabic العربية\nChinese 中文\nMy note')
    add_highlight(str(tmp_path), PROFILE, CARD, highlight)

    result = sync(tmp_path)

    rows = native_rows(filename)
    assert len(rows) == 1
    assert rows[0]['kind'] == 'Highlight'
    assert rows[0]['note'] == highlight['note']
    assert rows[0]['vertices'] == pytest.approx([(60, 65), (210, 65), (60, 83), (210, 83)])
    assert load_highlights(str(tmp_path), PROFILE, CARD)[0]['text'] == highlight['text']
    assert result['reader_path'] != str(filename)
    assert native_rows(result['reader_path']) == [], 'reader copy must prevent double-painted highlights'
    before = filename.read_bytes()
    sync(tmp_path)
    assert filename.read_bytes() == before, 'unchanged sync must not rewrite or duplicate annotations'


def test_custom_hex_color_is_kept_in_database_and_exported_pdf(tmp_path):
    filename = pdf_file(tmp_path)
    highlight = local_highlight('A searchable custom-color note')
    highlight['color'] = '#123abc'
    add_highlight(str(tmp_path), PROFILE, CARD, highlight)
    sync(tmp_path)
    with fitz.open(filename) as doc:
        native = next(doc[0].annots())
        assert native.colors['stroke'] == pytest.approx([18 / 255, 58 / 255, 188 / 255])
        assert native.opacity == pytest.approx(.42)
    saved = load_highlights(str(tmp_path), PROFILE, CARD)[0]
    assert saved['color'] == '#123abc'
    assert saved['note'] == highlight['note'] and saved['text'] == highlight['text']
    before = filename.read_bytes()
    sync(tmp_path)
    assert filename.read_bytes() == before


def test_custom_native_pdf_color_is_imported_as_exact_hex(tmp_path):
    filename = pdf_file(tmp_path)
    def populate(doc):
        page = doc[0]
        native = page.add_highlight_annot(fitz.Rect(60, 65, 210, 83))
        native.set_colors(stroke=(18 / 255, 58 / 255, 188 / 255))
        native.update(opacity=.42)
    change_pdf(filename, populate)
    sync(tmp_path)
    assert load_highlights(str(tmp_path), PROFILE, CARD)[0]['color'] == '#123abc'


def test_existing_native_highlights_and_comments_import_without_losing_other_annotation_types(tmp_path):
    filename = pdf_file(tmp_path)
    def populate(doc):
        add_native(doc)
        page = doc[0]
        page.add_text_annot((250, 80), 'A sticky note 中文')
        page.add_file_annot((250, 120), b'attachment', 'data.txt')
    change_pdf(filename, populate)

    result = sync(tmp_path)

    highlights = load_highlights(str(tmp_path), PROFILE, CARD)
    assert len(highlights) == 2
    assert {h['note'] for h in highlights} == {'Outside reader note', 'A sticky note 中文'}
    assert next(h for h in highlights if h['pdf_annotation']['kind'] == 'Highlight')['text']
    assert {r['kind'] for r in native_rows(filename)} == {'Highlight', 'Text', 'FileAttachment'}
    assert {r['kind'] for r in native_rows(result['reader_path'])} == {'Text', 'FileAttachment'}


def test_linked_original_and_managed_pdf_merge_new_edits_and_deletions_in_both_directions(tmp_path):
    filename = pdf_file(tmp_path)
    original = tmp_path / 'original.pdf'
    shutil.copy2(filename, original)
    add_highlight(str(tmp_path), PROFILE, CARD, local_highlight())
    sync(tmp_path, source_path=str(original))
    name = native_rows(original)[0]['name']
    def outside_edit(doc):
        page = doc[0]
        annot = next(page.annots())
        annot.set_info(content='Edited outside Incremento')
        annot.update()
        add_native(doc, 'A new outside annotation')
    change_pdf(original, outside_edit)

    sync(tmp_path)

    assert {h['note'] for h in load_highlights(str(tmp_path), PROFILE, CARD)} == {
        'Edited outside Incremento', 'A new outside annotation'}
    assert native_rows(filename) == native_rows(original)
    update_highlight_note(str(tmp_path), PROFILE, CARD, 'local', 'Edited in Incremento')
    sync(tmp_path)
    assert next(r for r in native_rows(original) if r['name'] == name)['note'] == 'Edited in Incremento'
    remove_highlight(str(tmp_path), PROFILE, CARD, 'local')
    sync(tmp_path)
    assert len(native_rows(original)) == 1
    def delete(doc):
        page = doc[0]
        page.delete_annot(next(page.annots()))
    change_pdf(original, delete)
    sync(tmp_path)
    assert load_highlights(str(tmp_path), PROFILE, CARD) == []
    assert native_rows(filename) == []


def test_linking_a_bare_original_after_managed_sync_preserves_incremento_annotations(tmp_path):
    filename = pdf_file(tmp_path)
    original = tmp_path / 'original.pdf'
    shutil.copy2(filename, original)
    add_highlight(str(tmp_path), PROFILE, CARD, local_highlight())
    sync(tmp_path)  # Automatic first open happens before original-file linking.
    result = sync(tmp_path, source_path=str(original))
    assert len(load_highlights(str(tmp_path), PROFILE, CARD)) == 1
    assert len(native_rows(filename)) == 1
    assert native_rows(filename) == native_rows(original)
    assert Path(result['source_path']) == original


def test_an_outside_reader_saving_an_old_copy_does_not_erase_new_incremento_highlights(tmp_path):
    filename = pdf_file(tmp_path)
    original, stale = tmp_path / 'original.pdf', tmp_path / 'stale.pdf'
    shutil.copy2(filename, original)
    add_highlight(str(tmp_path), PROFILE, CARD, local_highlight())
    sync(tmp_path, source_path=str(original))
    shutil.copy2(original, stale)  # Another reader still has this older snapshot.
    newer = local_highlight('Added while the other reader stayed open', 'newer')
    newer['rects'] = [{'x': 60, 'y': 95, 'w': 150, 'h': 18}]
    add_highlight(str(tmp_path), PROFILE, CARD, newer)
    sync(tmp_path)
    shutil.copy2(stale, original)
    change_pdf(original, lambda doc: add_native(doc, 'Outside addition'))
    sync(tmp_path)
    assert {row['note'] for row in load_highlights(str(tmp_path), PROFILE, CARD)} == {
        'My saved note', 'Added while the other reader stayed open', 'Outside addition'}
    assert len(native_rows(filename)) == 3
    assert native_rows(filename) == native_rows(original)


def test_snapshot_export_is_a_standard_rectangle_with_note_and_exact_bounds(tmp_path):
    filename = pdf_file(tmp_path)
    highlight = local_highlight()
    highlight['color'] = 'snapshot'
    add_highlight(str(tmp_path), PROFILE, CARD, highlight)
    result = sync(tmp_path)
    assert native_rows(filename)[0]['kind'] == 'Square'
    assert native_rows(filename)[0]['note'] == highlight['note']
    assert native_rows(result['reader_path']) == []
    sync(tmp_path)
    assert load_highlights(str(tmp_path), PROFILE, CARD)[0]['rects'] == highlight['rects']


def test_legacy_overlapping_text_selection_boxes_export_as_one_even_highlight_per_line(tmp_path):
    filename = pdf_file(tmp_path)
    highlight = local_highlight()
    highlight['rects'] = [
        {'x': 60, 'y': 65, 'w': 150, 'h': 18},
        {'x': 60, 'y': 67, 'w': 150, 'h': 14},
        {'x': 60, 'y': 95, 'w': 100, 'h': 18},
        {'x': 164, 'y': 97, 'w': 20, 'h': 14},
        {'x': 188, 'y': 95, 'w': 22, 'h': 18},
    ]
    add_highlight(str(tmp_path), PROFILE, CARD, highlight)
    sync(tmp_path)
    vertices = native_rows(filename)[0]['vertices']
    assert len(vertices) == 8
    assert vertices[0:4] == [(60, 65), (210, 65), (60, 83), (210, 83)]
    assert vertices[4:8] == [(60, 95), (210, 95), (60, 113), (210, 113)]


def test_concurrent_note_edits_preserve_both_texts_in_one_annotation(tmp_path):
    filename = pdf_file(tmp_path)
    add_highlight(str(tmp_path), PROFILE, CARD, local_highlight('Initial'))
    sync(tmp_path)
    update_highlight_note(str(tmp_path), PROFILE, CARD, 'local', 'Incremento version')
    def edit(doc):
        page = doc[0]
        annot = next(page.annots())
        annot.set_info(content='PDF reader version')
        annot.update()
    change_pdf(filename, edit)

    result = sync(tmp_path)

    assert result['conflicts'] == 1
    rows = native_rows(filename)
    assert len(rows) == 1
    assert 'Incremento version' in rows[0]['note']
    assert 'PDF reader version' in rows[0]['note']
    assert load_highlights(str(tmp_path), PROFILE, CARD)[0]['note'] == rows[0]['note']


@pytest.mark.parametrize('count', [1, 2])
def test_conflicting_positions_keep_each_original_highlight_and_its_other_version(tmp_path, count):
    filename = pdf_file(tmp_path)
    original = tmp_path / 'original.pdf'
    shutil.copy2(filename, original)
    for index in range(count):
        row = local_highlight('Initial', f'h{index}')
        row['rects'] = [{'x': 60, 'y': 65 + index * 30, 'w': 80, 'h': 18}]
        add_highlight(str(tmp_path), PROFILE, CARD, row)
    sync(tmp_path, source_path=str(original))
    for row in load_highlights(str(tmp_path), PROFILE, CARD):
        row['rects'] = [{'x': 90, 'y': 65, 'w': 80, 'h': 18}]
        row['pdf_annotation'].pop('quads')
        row['note'] = 'Local position'
        add_highlight(str(tmp_path), PROFILE, CARD, row)
    def move(doc):
        page = doc[0]
        xrefs = [a.xref for a in page.annots()]
        for xref in xrefs:
            old = page.load_annot(xref)
            name, color, opacity = old.info['id'], old.colors['stroke'], old.opacity
            page.delete_annot(old)
            new = page.add_highlight_annot(fitz.Rect(190, 65, 270, 83))
            new.set_info(content='Outside position')
            new.set_colors(stroke=color)
            doc.xref_set_key(new.xref, 'NM', fitz.get_pdf_str(name))
            new.update(opacity=opacity)
    change_pdf(original, move)
    sync(tmp_path)
    assert len(native_rows(filename)) == count * 2
    assert len({r['name'] for r in native_rows(filename)}) == count * 2
    assert native_rows(filename) == native_rows(original)
    before = filename.read_bytes()
    sync(tmp_path)
    assert filename.read_bytes() == before


@pytest.mark.parametrize('rotation,crop', [(0, True), (90, False), (180, True), (270, True)])
def test_rotated_and_cropped_pdf_coordinates_round_trip(tmp_path, rotation, crop):
    filename = pdf_file(tmp_path, rotation=rotation, crop=crop)
    highlight = local_highlight()
    add_highlight(str(tmp_path), PROFILE, CARD, highlight)
    sync(tmp_path)

    with fitz.open(filename) as doc:
        page = doc[0]
        quad = fitz.Quad(next(page.annots()).vertices) * page.rotation_matrix
        assert tuple(quad.rect) == pytest.approx((60, 65, 210, 83), abs=0.001)
    sync(tmp_path)
    assert load_highlights(str(tmp_path), PROFILE, CARD)[0]['rects'] == highlight['rects']


def test_source_document_mismatch_does_not_modify_files_or_annotations(tmp_path):
    filename = pdf_file(tmp_path)
    original = tmp_path / 'other.pdf'
    with fitz.open() as doc:
        doc.new_page().insert_text((60, 80), 'An unrelated document')
        doc.save(original)
    add_highlight(str(tmp_path), PROFILE, CARD, local_highlight())
    before = filename.read_bytes(), original.read_bytes()

    with pytest.raises(annotations.PdfAnnotationSyncError):
        sync(tmp_path, source_path=str(original))

    assert (filename.read_bytes(), original.read_bytes()) == before
    assert len(load_highlights(str(tmp_path), PROFILE, CARD)) == 1


def test_failed_atomic_save_preserves_pdf_and_incremento_notes(tmp_path, monkeypatch):
    filename = pdf_file(tmp_path)
    add_highlight(str(tmp_path), PROFILE, CARD, local_highlight())
    before = filename.read_bytes()
    def fail(*_args, **_kwargs):
        raise OSError('simulated replace failure')
    monkeypatch.setattr(annotations, '_atomic_replace_pdf', fail)

    with pytest.raises(OSError):
        sync(tmp_path)

    assert filename.read_bytes() == before
    assert load_highlights(str(tmp_path), PROFILE, CARD)[0]['note'] == 'My saved note'


def test_changed_font_resources_cannot_reuse_positions_from_a_different_pdf(tmp_path):
    filename = pdf_file(tmp_path)
    original = tmp_path / 'original.pdf'
    shutil.copy2(filename, original)
    def change_font(doc):
        font_xref = doc[0].get_fonts()[0][0]
        doc.xref_set_key(font_xref, 'BaseFont', '/Courier')
    change_pdf(original, change_font)
    add_highlight(str(tmp_path), PROFILE, CARD, local_highlight())
    before = filename.read_bytes(), original.read_bytes()
    with pytest.raises(annotations.PdfAnnotationSyncError, match='document_changed'):
        sync(tmp_path, source_path=str(original))
    assert (filename.read_bytes(), original.read_bytes()) == before


def test_legacy_empty_citation_highlights_survive_repeated_sync_without_pdf_annotations(tmp_path):
    filename = pdf_file(tmp_path)
    highlight = local_highlight()
    highlight['rects'] = []
    add_highlight(str(tmp_path), PROFILE, CARD, highlight)
    sync(tmp_path)
    sync(tmp_path)
    assert len(load_highlights(str(tmp_path), PROFILE, CARD)) == 1
    assert native_rows(filename) == []


def test_imported_freetext_edits_remain_visible_and_unicode_is_preserved(tmp_path):
    filename = pdf_file(tmp_path)
    def populate(doc):
        page = doc[0]
        page.add_freetext_annot(fitz.Rect(60, 160, 320, 240), 'Visible PDF text')
        page.add_underline_annot(fitz.Rect(60, 95, 210, 113)).set_info(content='Underlined note')
    change_pdf(filename, populate)
    sync(tmp_path)
    rows = load_highlights(str(tmp_path), PROFILE, CARD)
    free = next(row for row in rows if row['pdf_annotation']['kind'] == 'FreeText')
    text = 'العربية 中文\nVisible editable text <img src=https://example.com>'
    update_highlight_note(str(tmp_path), PROFILE, CARD, free['id'], text)
    result = sync(tmp_path)
    assert next(row for row in native_rows(filename) if row['kind'] == 'FreeText')['note'] == text
    with fitz.open(result['reader_path']) as doc:
        page = doc[0]
        assert 'Visible editable text' in page.get_text()
        assert '中文' in page.get_text()
    sync(tmp_path)
    assert len(load_highlights(str(tmp_path), PROFILE, CARD)) == 2


def test_cancelled_sync_does_not_change_pdf_or_lose_saved_incremento_note(tmp_path):
    filename = pdf_file(tmp_path)
    add_highlight(str(tmp_path), PROFILE, CARD, local_highlight())
    before = filename.read_bytes()
    with pytest.raises(annotations.PdfAnnotationSyncCancelled):
        sync(tmp_path, cancel=lambda: True)
    assert filename.read_bytes() == before
    assert load_highlights(str(tmp_path), PROFILE, CARD)[0]['note'] == 'My saved note'
    assert not paths.get_pdf_annotation_reader_path(str(tmp_path), PROFILE, CARD).exists()


@pytest.mark.parametrize('protection', ['password', 'signed', 'restricted'])
def test_protected_pdf_is_not_rewritten_and_saved_incremento_notes_survive(tmp_path, protection):
    filename = pdf_file(tmp_path)
    if protection == 'signed':
        change_pdf(filename, lambda doc: doc.xref_set_key(doc.pdf_catalog(), 'AcroForm', '<</SigFlags 3>>'))
    else:
        temporary = filename.with_suffix('.encrypted.pdf')
        with fitz.open(filename) as doc:
            doc.save(temporary, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw='owner',
                     user_pw='password' if protection == 'password' else '',
                     permissions=fitz.PDF_PERM_PRINT)
        temporary.replace(filename)
    add_highlight(str(tmp_path), PROFILE, CARD, local_highlight())
    before = filename.read_bytes()
    with pytest.raises(annotations.PdfAnnotationSyncError, match='protected_pdf'):
        sync(tmp_path)
    assert filename.read_bytes() == before
    assert load_highlights(str(tmp_path), PROFILE, CARD)[0]['note'] == 'My saved note'


def test_missing_native_names_and_names_reused_across_pages_keep_distinct_identities(tmp_path):
    filename = pdf_file(tmp_path)
    def populate(doc):
        page = doc[0]
        for y in [65, 95]:
            annotation = page.add_highlight_annot(fitz.Rect(60, y, 210, y + 18))
            annotation.set_info(content=str(y))
            doc.xref_set_key(annotation.xref, 'NM', 'null')
        page = doc.new_page(width=400, height=500)
        annotation = page.add_text_annot((60, 80), 'Page two')
        doc.xref_set_key(annotation.xref, 'NM', fitz.get_pdf_str('same-name'))
        page = doc[0]
        annotation = page.add_text_annot((250, 80), 'Page one')
        doc.xref_set_key(annotation.xref, 'NM', fitz.get_pdf_str('same-name'))
    change_pdf(filename, populate)
    sync(tmp_path)
    before = filename.read_bytes()
    sync(tmp_path)
    assert len(load_highlights(str(tmp_path), PROFILE, CARD)) == 4
    assert len({(row['page'], row['name']) for row in native_rows(filename)}) == 4
    assert filename.read_bytes() == before


def test_partial_linked_file_write_retries_without_duplicate_highlights(tmp_path, monkeypatch):
    filename = pdf_file(tmp_path)
    original = tmp_path / 'original.pdf'
    shutil.copy2(filename, original)
    add_highlight(str(tmp_path), PROFILE, CARD, local_highlight())
    replace = annotations._atomic_replace_pdf
    def fail_original(temporary, destination, signature):
        if destination == original:
            raise OSError('original locked by another reader')
        replace(temporary, destination, signature)
    monkeypatch.setattr(annotations, '_atomic_replace_pdf', fail_original)
    with pytest.raises(OSError):
        sync(tmp_path, source_path=str(original))
    assert len(native_rows(filename)) == 1
    assert native_rows(original) == []
    monkeypatch.setattr(annotations, '_atomic_replace_pdf', replace)
    sync(tmp_path, source_path=str(original))
    assert len(native_rows(filename)) == 1
    assert native_rows(filename) == native_rows(original)
    assert len(load_highlights(str(tmp_path), PROFILE, CARD)) == 1


def test_invalidated_document_owner_cannot_receive_imported_annotations_from_an_old_worker(tmp_path, monkeypatch):
    filename = pdf_file(tmp_path)
    change_pdf(filename, lambda doc: add_native(doc))
    replace = annotations._atomic_replace_pdf
    def invalidate(temporary, destination, signature):
        replace(temporary, destination, signature)
        conn = annotations.get_connection(str(tmp_path), PROFILE)
        with conn:
            conn.execute('DELETE FROM pdf_annotation_sync WHERE card_id=?', (CARD,))
    monkeypatch.setattr(annotations, '_atomic_replace_pdf', invalidate)
    with pytest.raises(annotations.PdfAnnotationSyncError, match='document_changed'):
        sync(tmp_path)
    assert load_highlights(str(tmp_path), PROFILE, CARD) == []


def test_linked_rectangle_annotations_keep_their_fill_border_color_and_author(tmp_path):
    filename = pdf_file(tmp_path)
    original = tmp_path / 'original.pdf'
    shutil.copy2(filename, original)
    def populate(doc):
        page = doc[0]
        annot = page.add_rect_annot(fitz.Rect(60, 160, 220, 220))
        annot.set_info(content='A colored box', title='PDF author', subject='Subject')
        annot.set_colors(stroke=(0.2, 0.4, 0.6), fill=(0.8, 0.7, 0.6))
        annot.set_border(width=3)
        annot.update(opacity=0.7)
    change_pdf(filename, populate)
    sync(tmp_path, source_path=str(original))
    with fitz.open(original) as doc:
        page = doc[0]
        annot = next(page.annots())
        assert annot.colors['fill'] == pytest.approx((0.8, 0.7, 0.6))
        assert annot.colors['stroke'] == pytest.approx((0.2, 0.4, 0.6))
        assert annot.border['width'] == 3
        assert annot.info['title'] == 'PDF author'
        assert annot.info['subject'] == 'Subject'


def test_freetext_note_edits_keep_the_original_font_size_without_css_errors(tmp_path, capsys):
    filename = pdf_file(tmp_path)
    def populate(doc):
        page = doc[0]
        page.add_freetext_annot(fitz.Rect(60, 160, 340, 240), 'Large PDF note', fontsize=20,
                               text_color=(0.2, 0.4, 0.6), fill_color=(0.95, 0.95, 0.8))
    change_pdf(filename, populate)
    sync(tmp_path)
    row = load_highlights(str(tmp_path), PROFILE, CARD)[0]
    update_highlight_note(str(tmp_path), PROFILE, CARD, row['id'], 'Edited large note')
    sync(tmp_path)
    with fitz.open(filename) as doc:
        page = doc[0]
        annotation = next(page.annots())
        spans = [span for block in annotation.get_text('dict')['blocks'] for line in block.get('lines', []) for span in line['spans']]
        assert spans[0]['size'] == pytest.approx(20)
        assert spans[0]['color'] == 0x336699
    captured = capsys.readouterr()
    assert 'css syntax error' not in captured.out + captured.err


def test_sync_never_overwrites_a_newer_incremento_edit_while_pdf_is_being_saved(tmp_path, monkeypatch):
    pdf_file(tmp_path)
    add_highlight(str(tmp_path), PROFILE, CARD, local_highlight('First edit'))
    replace = annotations._atomic_replace_pdf
    def edit_during_save(*args, **kwargs):
        replace(*args, **kwargs)
        update_highlight_note(str(tmp_path), PROFILE, CARD, 'local', 'Newer edit')
    monkeypatch.setattr(annotations, '_atomic_replace_pdf', edit_during_save)

    result = sync(tmp_path)

    assert load_highlights(str(tmp_path), PROFILE, CARD)[0]['note'] == 'Newer edit'
    assert result['retry_needed']
    monkeypatch.setattr(annotations, '_atomic_replace_pdf', replace)
    sync(tmp_path)
    filename = paths.get_pdf_dir(str(tmp_path), PROFILE) / FILENAME
    assert native_rows(filename)[0]['note'] == 'Newer edit'


def test_symlink_source_and_traversing_managed_filename_fail_closed(tmp_path):
    filename = pdf_file(tmp_path)
    link = tmp_path / 'link.pdf'
    link.symlink_to(filename)
    with pytest.raises(annotations.PdfAnnotationSyncError):
        sync(tmp_path, source_path=str(link))
    with pytest.raises(annotations.PdfAnnotationSyncError):
        annotations.sync_pdf_annotations(str(tmp_path), PROFILE, CARD, '../document.pdf')


def test_annotation_sync_state_is_profile_scoped(tmp_path):
    pdf_file(tmp_path)
    add_highlight(str(tmp_path), 'OtherProfile', CARD, local_highlight('Other profile'))
    sync(tmp_path)
    assert annotations.pdf_annotation_sync_state(str(tmp_path), 'OtherProfile', CARD) is None
    assert load_highlights(str(tmp_path), 'OtherProfile', CARD)[0]['note'] == 'Other profile'


def test_picked_hex_matching_a_legacy_swatch_keeps_its_hex_identity(tmp_path):
    pdf_file(tmp_path)
    add_highlight(str(tmp_path), PROFILE, CARD, {'id': 'custom-green', 'page': 1,
        'color': '#00c850', 'text': 'A passage', 'note': '',
        'rects': [{'x': 60, 'y': 65, 'w': 150, 'h': 18}]})
    sync(tmp_path)
    sync(tmp_path)
    assert load_highlights(str(tmp_path), PROFILE, CARD)[0]['color'] == '#00c850'
