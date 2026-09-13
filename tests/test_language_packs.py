"""A translator can round-trip one safe spreadsheet without touching application data."""
from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path

import pytest

from backend import language_packs as packs
from backend import i18n


def make_csv(rows=(), *, locale='de', name='Deutsch', delimiter=','):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, delimiter=delimiter)
    writer.writerow(['component', 'key', 'form', 'source', 'translation'])
    for key, value in [('version', '1'), ('locale', locale), ('name', name)]:
        writer.writerow(['meta', key, '', '', value])
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8-sig')


def entry(component='addon', *, tokens=False, markup=False, form=''):
    return next(item for item in packs.translation_catalog()['entries'] if item['component'] == component
                and bool(item['tokens']) == tokens and bool(item['markup']) == markup and item['form'] == form)


def row(item, translation):
    return [item['component'], item['key'], item['form'], item['source'], translation]


def sample_pack():
    item = entry()
    return packs.parse_csv(make_csv([row(item, 'Übersetzung,\nmit Zeilen')]))


@pytest.mark.parametrize('delimiter', [',', ';', '\t'])
def test_spreadsheet_round_trip_all_components_preserves_unicode_multiline_and_tokens(delimiter):
    items = [entry(component) for component in ('addon', 'reader', 'extension')]
    pack = packs.parse_csv(make_csv([row(item, 'Übersetzung,\n文字') for item in items], delimiter=delimiter))
    assert pack['locale'] == 'de'
    assert pack['name'] == 'Deutsch'
    assert set(pack['translations']) == {'addon', 'reader', 'extension'}
    assert packs.parse_csv(packs.export_csv(pack)) == pack


def test_blank_template_exports_every_known_message_and_requires_language_metadata():
    data = packs.export_csv()
    assert data.startswith(b'\xef\xbb\xbf')
    assert len(list(csv.reader(io.StringIO(data.decode('utf-8-sig'))))) == len(packs.translation_catalog()['entries']) + 4
    with pytest.raises(packs.LanguagePackError, match='language'):
        packs.parse_csv(data)


@pytest.mark.parametrize('choice,canonical', [('custom:de_de','custom:de-DE'), ('custom:zh_hant_tw','custom:zh-Hant-TW'), ('custom:../../en','auto')])
def test_custom_choice_canonicalizes_without_registering_code(choice, canonical):
    assert i18n.normalize_language_choice(choice) == canonical


def test_invalid_row_reports_row_and_rejects_whole_pack():
    item = entry(tokens=True)
    with pytest.raises(packs.LanguagePackError) as caught:
        packs.parse_csv(make_csv([row(item, 'Missing replacement')]))
    assert caught.value.row == 5
    assert caught.value.code == 'tokens'


@pytest.mark.parametrize('bad', ['<img src=x onerror=alert(1)>', '<script>alert(1)</script>', 'javascript:alert(1)', '${alert(1)}', '`;alert(1)'])
def test_new_executable_markup_or_interpolation_is_rejected(bad):
    with pytest.raises(packs.LanguagePackError):
        packs.parse_csv(make_csv([row(entry(), bad)]))


def test_rich_text_requires_original_tag_attribute_order():
    item = entry(markup=True)
    assert packs.parse_csv(make_csv([row(item, item['source'])]))
    with pytest.raises(packs.LanguagePackError):
        packs.parse_csv(make_csv([row(item, item['source'].replace(item['markup'][0], '<a href="javascript:bad">', 1))]))


def test_duplicate_unknown_and_edited_source_rows_are_rejected_even_if_translation_blank():
    item = entry()
    for rows in ([row(item, ''), row(item, '')], [['addon','not_a_known_key','','','']], [row(item, '')[:3] + ['edited','']]):
        with pytest.raises(packs.LanguagePackError):
            packs.parse_csv(make_csv(rows))


def test_formula_cells_are_escaped_on_export_and_import_roundtrips_literal_text():
    item = entry()
    pack = packs.parse_csv(make_csv([row(item, "'=SUM(A1:A2)")]))
    assert pack['translations']['addon'][item['key']] == '=SUM(A1:A2)'
    data = packs.export_csv(pack)
    assert "'=SUM(A1:A2)" in data.decode('utf-8-sig')
    assert packs.parse_csv(data) == pack


def test_oversized_and_invalid_utf8_are_rejected():
    for data in (b'x' * (packs.MAX_FILE_BYTES + 1), b'\xff\xfe'):
        with pytest.raises(packs.LanguagePackError):
            packs.parse_csv(data)


def test_profile_storage_is_atomic_isolated_and_corrupt_pack_is_ignored(tmp_path, monkeypatch):
    original = sample_pack()
    packs.save_pack(str(tmp_path), 'One', original)
    assert packs.load_pack(str(tmp_path), 'One', 'de') == original
    assert packs.list_packs(str(tmp_path), 'Two') == []
    assert not (tmp_path / 'user_files' / 'Two').exists()
    updated = {**original, 'name':'German'}
    def fail_replace(*args, **kwargs):
        raise OSError('disk unavailable')
    monkeypatch.setattr(os, 'replace', fail_replace)
    with pytest.raises(packs.LanguagePackError):
        packs.save_pack(str(tmp_path), 'One', updated)
    assert packs.load_pack(str(tmp_path), 'One', 'de') == original
    folder = tmp_path / 'user_files' / 'One' / 'language_packs'
    assert [p.name for p in folder.iterdir()] == ['de.json']
    (folder / 'de.json').write_text('{malformed')
    assert packs.load_pack(str(tmp_path), 'One', 'de') is None


def test_symlink_storage_cannot_read_or_overwrite_outside_profile(tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    user = tmp_path / 'user_files'
    user.mkdir()
    (user / 'One').symlink_to(outside, target_is_directory=True)
    assert packs.load_pack(str(tmp_path), 'One', 'de') is None
    with pytest.raises(packs.LanguagePackError):
        packs.save_pack(str(tmp_path), 'One', sample_pack())
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize('locale,values', [
    ('de',{1:'one',2:'other'}), ('hr',{1:'one',2:'few',11:'other',21:'one'}),
    ('zh',{1:'other',2:'other'}), ('ar',{0:'zero',1:'one',2:'two',3:'few',11:'many',100:'other'}),
    ('ru',{1:'one',2:'few',5:'many',21:'one'}), ('pl',{1:'one',2:'few',5:'many',12:'many',22:'few'}),
])
def test_offline_plural_categories_match_cldr(locale, values):
    for count, expected in values.items():
        assert packs.plural_category(locale, count) == expected


def test_runtime_custom_snapshot_uses_safe_translations_and_english_for_missing_categories():
    singular = entry()
    plural = entry(tokens=True, form='one')
    pack = packs.parse_csv(make_csv([row(singular,'Übersetzt'), row(plural, plural['source'].replace(' ', ' · ', 1))], locale='ru', name='Русский'))
    translator = i18n.Translator('custom:ru', custom_pack=pack)
    assert translator.locale == 'ru'
    assert translator.t(singular['key']) == 'Übersetzt'
    assert translator.tn(plural['key'], 21) == plural['source'].replace(' ', ' · ', 1).format(count=21)
    assert translator.tn(plural['key'], 5) == i18n.Translator('en').tn(plural['key'], 5)
    pack['translations']['addon'][singular['key']] = '<script>bad</script>'
    assert translator.t(singular['key']) == 'Übersetzt'
    assert i18n.Translator('custom:ru', custom_pack=pack).locale == 'en'


@pytest.mark.parametrize('text', ["'=SUM(A1:A2)", "''@hello", '  +literal', '-hello', '\t=with_tab', 'normal apostrophe: \''])
def test_existing_literal_apostrophes_survive_formula_protection(text):
    pack = sample_pack()
    key = next(iter(pack['translations']['addon']))
    pack['translations']['addon'][key] = text
    assert packs.parse_csv(packs.export_csv(pack)) == pack


def test_stored_pack_retains_other_translations_after_catalog_changes(tmp_path):
    pack = sample_pack()
    key = next(iter(pack['translations']['addon']))
    pack['translations']['addon']['removed_key'] = 'Alter Text'
    pack['translations']['reader'][entry('reader', tokens=True)['key']] = 'Now incompatible'
    folder = tmp_path / 'user_files' / 'One' / 'language_packs'
    folder.mkdir(parents=True)
    (folder / 'de.json').write_text(json.dumps(pack))
    loaded = packs.load_pack(str(tmp_path), 'One', 'de')
    assert loaded['translations']['addon'] == {key: pack['translations']['addon'][key]}
    assert loaded['translations']['reader'] == {}
    with pytest.raises(packs.LanguagePackError):
        packs.validate_pack(pack)


def test_copied_name_mismatch_and_duplicate_json_are_not_loaded(tmp_path):
    pack = sample_pack()
    folder = tmp_path / 'user_files' / 'One' / 'language_packs'
    folder.mkdir(parents=True)
    (folder / 'fr.json').write_text(json.dumps(pack))
    assert packs.load_pack(str(tmp_path), 'One', 'fr') is None
    (folder / 'de.json').write_text(json.dumps(pack)[:-1] + ',"locale":"de"}')
    assert packs.load_pack(str(tmp_path), 'One', 'de') is None


def test_symlink_target_file_is_never_read_replaced_or_deleted(tmp_path):
    pack = sample_pack()
    secret = tmp_path / 'secret.json'
    secret.write_text(json.dumps(pack))
    folder = tmp_path / 'user_files' / 'One' / 'language_packs'
    folder.mkdir(parents=True)
    (folder / 'de.json').symlink_to(secret)
    assert packs.load_pack(str(tmp_path), 'One', 'de') is None
    with pytest.raises(packs.LanguagePackError):
        packs.save_pack(str(tmp_path), 'One', pack)
    with pytest.raises(packs.LanguagePackError):
        packs.delete_pack(str(tmp_path), 'One', 'de')
    assert json.loads(secret.read_text()) == pack


def test_pack_limit_allows_existing_language_updates_without_extra_files(tmp_path, monkeypatch):
    monkeypatch.setattr(packs, 'MAX_PACKS', 2)
    de = sample_pack()
    fr = {**de, 'locale': 'fr', 'name':'Français'}
    packs.save_pack(str(tmp_path), 'One', de)
    packs.save_pack(str(tmp_path), 'One', fr)
    packs.save_pack(str(tmp_path), 'One', {**de, 'name':'German'})
    with pytest.raises(packs.LanguagePackError) as error:
        packs.save_pack(str(tmp_path), 'One', {**de, 'locale':'es', 'name':'Español'})
    assert error.value.code == 'limit'
    assert {pack['locale'] for pack in packs.list_packs(str(tmp_path), 'One')} == {'de', 'fr'}
    packs.delete_pack(str(tmp_path), 'One', 'de')
    assert packs.load_pack(str(tmp_path), 'One', 'de') is None
    assert packs.load_pack(str(tmp_path), 'One', 'fr') == fr


@pytest.mark.parametrize('locale', ['en', 'hr', 'zh-Hans'])
def test_every_builtin_can_export_all_three_components_and_reimport(locale):
    pack = packs.builtin_pack(locale)
    assert packs.parse_csv(packs.export_csv(pack)) == pack
    assert all(pack['translations'].values())


@pytest.mark.parametrize('locale,count,category', [('hr',1.2,'few'),('hr',1.1,'one'),('ru',1.2,'other'),('fr',0,'one'),('pt-PT',0,'other'),('ar',-3,'few')])
def test_plural_operands_include_fractional_digits_and_region(locale, count, category):
    assert packs.plural_category(locale,count) == category


def test_portable_storage_without_posix_directory_descriptors_preserves_atomic_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(packs, '_DIRECTORY_FD_SUPPORTED', False, raising=False)
    monkeypatch.delattr(os, 'O_DIRECTORY', raising=False)
    pack = sample_pack()
    packs.save_pack(str(tmp_path), 'One', pack)
    assert packs.load_pack(str(tmp_path), 'One', 'de') == pack
    assert packs.list_packs(str(tmp_path), 'One')[0]['name'] == 'Deutsch'
    assert packs.list_packs(str(tmp_path), 'Two') == []
    previous = (tmp_path / 'user_files/One/language_packs/de.json').read_bytes()
    def fail_replace(*args, **kwargs):
        raise OSError('disk unavailable')
    with monkeypatch.context() as patch:
        patch.setattr(os, 'replace', fail_replace)
        with pytest.raises(packs.LanguagePackError):
            packs.save_pack(str(tmp_path), 'One', {**pack, 'name':'German'})
    assert (tmp_path / 'user_files/One/language_packs/de.json').read_bytes() == previous
    packs.delete_pack(str(tmp_path), 'One', 'de')
    assert packs.load_pack(str(tmp_path), 'One', 'de') is None


def test_portable_storage_rejects_linked_parent_and_target(tmp_path, monkeypatch):
    monkeypatch.setattr(packs, '_DIRECTORY_FD_SUPPORTED', False, raising=False)
    outside = tmp_path / 'outside'
    outside.mkdir()
    folder = tmp_path / 'user_files' / 'One'
    folder.mkdir(parents=True)
    (folder / 'language_packs').symlink_to(outside, target_is_directory=True)
    with pytest.raises(packs.LanguagePackError):
        packs.save_pack(str(tmp_path), 'One', sample_pack())
    assert packs.load_pack(str(tmp_path), 'One', 'de') is None
    assert list(outside.iterdir()) == []


def test_escaping_a_required_python_placeholder_does_not_count_as_preserving_it():
    item = next(item for item in packs.translation_catalog()['entries'] if item['component'] == 'addon' and item['tokens'] == ['{source}'])
    with pytest.raises(packs.LanguagePackError) as error:
        packs.parse_csv(make_csv([row(item, '{{source}}')]))
    assert error.value.code == 'tokens'


def test_portable_path_checks_reject_windows_junction_reparse_attributes(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(packs, '_DIRECTORY_FD_SUPPORTED', False)
    parent = tmp_path / 'user_files'
    parent.mkdir()
    original = Path.lstat
    def junction_info(path):
        actual = original(path)
        if path == parent:
            return SimpleNamespace(st_mode=actual.st_mode, st_file_attributes=0x400)
        return actual
    monkeypatch.setattr(Path, 'lstat', junction_info)
    with pytest.raises(packs.LanguagePackError):
        packs.save_pack(str(tmp_path), 'One', sample_pack())
    assert list(parent.iterdir()) == []


@pytest.mark.skipif(not hasattr(os, 'mkfifo'), reason='FIFO is a POSIX filesystem object')
def test_a_fifo_disguised_as_a_pack_is_rejected_without_waiting_for_a_writer(tmp_path):
    import subprocess
    import sys
    folder = tmp_path / 'user_files' / 'One' / 'language_packs'
    folder.mkdir(parents=True)
    os.mkfifo(folder / 'de.json')
    code = "import sys; from backend.language_packs import load_pack; assert load_pack(sys.argv[1], 'One', 'de') is None"
    subprocess.run([sys.executable, '-c', code, str(tmp_path)], check=True, timeout=2, capture_output=True)
