"""One editable language sheet must work in both Anki and Chrome, offline."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from backend import language_packs as packs


ROOT = Path(__file__).resolve().parents[1]
JS_RUNNER = """
import fs from 'node:fs';
import {
  builtinLanguagePack, canonicalPackLocale, exportLanguagePackCsv,
  parseLanguagePackCsv, validateLanguagePack,
} from './chrome_extensions/incremento_companion/src/shared/languagePacks.js';
const request = JSON.parse(fs.readFileSync(0, 'utf8'));
try {
  let value;
  if (request.op === 'roundtrip') {
    const pack = parseLanguagePackCsv(request.csv);
    value = {pack, csv: exportLanguagePackCsv(pack, undefined, request.delimiter)};
  } else if (request.op === 'builtin') {
    const pack = await builtinLanguagePack(request.locale);
    value = {pack, csv: exportLanguagePackCsv(pack, undefined, request.delimiter)};
  } else if (request.op === 'export') {
    value = exportLanguagePackCsv(request.pack, undefined, request.delimiter);
  } else if (request.op === 'parse') {
    value = parseLanguagePackCsv(request.csv);
  } else if (request.op === 'validate') {
    value = validateLanguagePack(request.pack);
  } else if (request.op === 'locale') {
    value = canonicalPackLocale(request.locale);
  } else {
    throw new Error('Unknown interop test operation');
  }
  process.stdout.write(JSON.stringify({ok: true, value}));
} catch (error) {
  process.stdout.write(JSON.stringify({ok: false, code: error.code || error.name, row: error.row}));
}
"""


def js(request):
    node = shutil.which('node')
    assert node, 'Node is required for the cross-runtime language sheet contract.'
    result = subprocess.run(
        [node, '--input-type=module', '-e', JS_RUNNER],
        input=json.dumps(request), text=True, capture_output=True,
        cwd=ROOT, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr[:2000]
    return json.loads(result.stdout)


def entry(component='addon', *, tokens=False, markup=False, form=''):
    return next(item for item in packs.translation_catalog()['entries']
                if item['component'] == component and bool(item['tokens']) == tokens
                and bool(item['markup']) == markup and item['form'] == form)


def empty_pack(locale='de'):
    return {'version': 1, 'locale': locale, 'name': 'Deutsch',
            'translations': {component: {} for component in packs.COMPONENTS}}


def sheet(translation, *, item=None, locale='de', delimiter=','):
    item = item or entry()
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, delimiter=delimiter)
    writer.writerow(packs.HEADERS)
    for key, value in [('version', '1'), ('locale', locale), ('name', 'Deutsch')]:
        writer.writerow(['meta', key, '', '', value])
    writer.writerow([item['component'], item['key'], item['form'], item['source'], translation])
    return stream.getvalue().encode('utf-8-sig')


@pytest.mark.parametrize('locale', ['en', 'hr', 'zh-Hans'])
def test_bundled_translation_sheet_roundtrips_in_both_applications(locale):
    expected = packs.builtin_pack(locale)
    addon_csv = packs.export_csv(expected).decode('utf-8-sig')
    from_addon = js({'op': 'roundtrip', 'csv': addon_csv, 'delimiter': ','})
    assert from_addon['ok'], from_addon
    assert from_addon['value']['pack'] == expected
    assert packs.parse_csv(from_addon['value']['csv'].encode('utf-8')) == expected

    from_extension = js({'op': 'builtin', 'locale': locale, 'delimiter': ';'})
    assert from_extension['ok'], from_extension
    assert from_extension['value']['pack'] == expected
    assert packs.parse_csv(from_extension['value']['csv'].encode('utf-8')) == expected


@pytest.mark.parametrize('delimiter', [',', ';', '\t'])
def test_custom_sheet_roundtrips_quotes_newlines_unicode_placeholders_and_all_plural_forms(delimiter):
    expected = empty_pack()
    for component in packs.COMPONENTS:
        simple = entry(component)
        token_message = entry(component, tokens=True)
        expected['translations'][component][simple['key']] = 'Deutsch, "你好";\nNächste Zeile'
        expected['translations'][component][token_message['key']] = 'Übersetzt: ' + token_message['source']
        plural = entry(component, tokens=True, form='one')
        for form in packs.FORMS:
            expected['translations'][component][plural['key'] + '::' + form] = plural['source'] + ' · ' + form
    rich_text = entry(tokens=True, markup=True)
    expected['translations']['addon'][rich_text['key']] = rich_text['source'] + ' — Übersetzt'
    expected = packs.validate_pack(expected)

    result = js({'op': 'roundtrip', 'csv': packs.export_csv(expected).decode('utf-8-sig'), 'delimiter': delimiter})
    assert result['ok'], result
    assert result['value']['pack'] == expected
    assert packs.parse_csv(result['value']['csv'].encode('utf-8')) == expected


@pytest.mark.parametrize('translation', ['=SUM(A1:A2)', ' +42', '@name', "'=literal", "''@literal"])
def test_formula_like_translation_and_literal_apostrophes_roundtrip_without_execution(translation):
    expected = empty_pack()
    expected['translations']['addon'][entry()['key']] = translation
    expected = packs.validate_pack(expected)
    exported = packs.export_csv(expected)
    assert packs.parse_csv(exported) == expected
    result = js({'op': 'roundtrip', 'csv': exported.decode('utf-8-sig'), 'delimiter': ','})
    assert result['ok'], result
    assert result['value']['pack'] == expected
    assert packs.parse_csv(result['value']['csv'].encode('utf-8')) == expected
    rows = list(csv.reader(io.StringIO(result['value']['csv'].lstrip('\ufeff'))))
    exported_translation = next(row[4] for row in rows if row[0:2] == ['addon', entry()['key']])
    assert exported_translation.startswith("'"), 'Formula-like cells must be literal spreadsheet text.'


@pytest.mark.parametrize('locale', ['de-1901', 'sl-rozaj-biske', 'zh_hant_tw', 'de-' + '-'.join(['abcde' + str(i) for i in range(7)])])
def test_locale_codes_have_identical_cross_application_normalization(locale):
    result = js({'op': 'locale', 'locale': locale})
    assert result['ok'], result
    assert result['value'] == packs.canonical_locale(locale)


def test_whitespace_only_translation_is_omitted_in_both_applications():
    data = sheet(' \t\n ')
    expected = packs.parse_csv(data)
    assert expected['translations']['addon'] == {}
    result = js({'op': 'parse', 'csv': data.decode('utf-8-sig')})
    assert result['ok'], result
    assert result['value'] == expected


@pytest.mark.parametrize('translation', [
    '<img src=x onerror=alert(1)>', '<img src=x', '<script',
    'javascript:alert(1)', 'javascript :alert(1)', 'data:image/svg+xml,bad',
    '${alert(1)}', '`;alert(1)', '字' * 5462,
])
def test_unsafe_markup_and_oversized_utf8_cells_are_rejected_by_both_importers(translation):
    data = sheet(translation)
    with pytest.raises(packs.LanguagePackError):
        packs.parse_csv(data)
    result = js({'op': 'parse', 'csv': data.decode('utf-8-sig')})
    assert result['ok'] is False, 'The extension must reject the entire unsafe sheet before it can be staged.'


def test_changed_named_placeholders_are_rejected_in_both_applications():
    data = sheet('Wrong {replacement}', item=entry(tokens=True))
    with pytest.raises(packs.LanguagePackError) as error:
        packs.parse_csv(data)
    assert error.value.code == 'tokens'
    result = js({'op': 'parse', 'csv': data.decode('utf-8-sig')})
    assert result['ok'] is False
    assert result['code'] == 'tokens'


def test_error_row_identifies_the_same_spreadsheet_row_after_multiline_translations():
    data = sheet('First line\nSecond line')
    item = entry(tokens=True)
    stream = io.StringIO(newline='')
    csv.writer(stream).writerow([item['component'], item['key'], item['form'], item['source'], 'Missing placeholder'])
    data += stream.getvalue().encode('utf-8')
    with pytest.raises(packs.LanguagePackError) as error:
        packs.parse_csv(data)
    assert error.value.code == 'tokens'
    assert error.value.row == 6
    result = js({'op': 'parse', 'csv': data.decode('utf-8-sig')})
    assert result['ok'] is False
    assert result['code'] == 'tokens'
    assert result['row'] == 6


def test_required_addon_placeholder_cannot_be_hidden_inside_escaped_braces():
    item = entry(tokens=True)
    translation = item['source']
    for token in item['tokens']:
        translation = translation.replace(token, '{' + token + '}')
    data = sheet(translation, item=item)
    with pytest.raises(packs.LanguagePackError) as error:
        packs.parse_csv(data)
    assert error.value.code == 'tokens'
    result = js({'op': 'parse', 'csv': data.decode('utf-8-sig')})
    assert result['ok'] is False
    assert result['code'] == 'tokens'


@pytest.mark.parametrize('component_value', [None, False, 0, ''])
def test_malformed_component_does_not_become_an_empty_valid_pack(component_value):
    malformed = empty_pack()
    malformed['translations']['reader'] = component_value
    with pytest.raises(packs.LanguagePackError):
        packs.validate_pack(malformed)
    result = js({'op': 'validate', 'pack': malformed})
    assert result['ok'] is False
