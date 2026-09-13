"""Display language must leave timer values and note-type identities intact."""
from backend.i18n import Translator
import note_type_update_dialog
from note_type_updates import PendingNoteTypeUpdate
import timer_widget
import local_file_dock


def test_croatian_timer_plural_forms_preserve_reader_counts(monkeypatch):
    tr = Translator('hr')
    monkeypatch.setattr(timer_widget, '_t', tr.t, raising=False)
    monkeypatch.setattr(timer_widget, '_tn', tr.tn, raising=False)
    lines = timer_widget._timer_run_summary_lines(2, {(10, 1)}, set())
    assert lines[0] == 'Ponovljene su <b>2</b> kartice'
    assert 'PDF' in lines[1] and '<b>1</b>' in lines[1]
    assert 'Translation unavailable' not in '\n'.join(lines)


def test_note_update_chinese_retains_identifiers_and_consent_instructions(monkeypatch):
    monkeypatch.setattr(note_type_update_dialog, '_t', Translator('zh-Hans').t, raising=False)
    update = PendingNoteTypeUpdate('Incremento PDF', ('add fields: PDF_Cover_Image',))
    html = note_type_update_dialog.format_note_type_update_html([update])
    assert '尚未更改' in html
    assert 'Incremento PDF' in html and 'PDF_Cover_Image' in html
    assert '上传到 AnkiWeb' in html and '下载' in html
    assert update.changes == ('add fields: PDF_Cover_Image',)


def test_local_file_display_does_not_change_stored_mode(monkeypatch):
    monkeypatch.setattr(local_file_dock, '_t', Translator('hr').t, raising=False)
    assert local_file_dock._mode_label(local_file_dock.LOCAL_FILE_MODE_MANAGED_COPY) == 'Upravljana kopija'
