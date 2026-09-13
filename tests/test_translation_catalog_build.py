"""The exported spreadsheet stays aligned with all three editable source catalogs."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/build_translation_catalog.py'


def fixture_repo(tmp_path):
    for locale in ('en', 'hr', 'zh-Hans'):
        folder = tmp_path / 'locales' / locale / 'LC_MESSAGES'
        folder.mkdir(parents=True)
        (folder / 'incremento_core.po').write_text(
            'msgid ""\nmsgstr "Content-Type: text/plain; charset=UTF-8\\nPlural-Forms: nplurals=2; plural=(n != 1);\\n"\n'
            '\nmsgid "hello"\nmsgstr "<b>Hello {name}</b>"\n'
            '\nmsgid "cards"\nmsgid_plural "cards_plural"\nmsgstr[0] "{count} card"\nmsgstr[1] "{count} cards"\n'
        )
        reader = tmp_path / 'frontend/src/locales' / (locale + '.json')
        reader.parent.mkdir(parents=True, exist_ok=True)
        reader.write_text(json.dumps({'page':'Page {number}'}))
        extension = tmp_path / 'chrome_extensions/incremento_companion/_locales' / ('zh_CN' if locale == 'zh-Hans' else locale) / 'messages.json'
        extension.parent.mkdir(parents=True)
        extension.write_text(json.dumps({'title':{'message':'Hello $NAME$'}}))
    return tmp_path


def run(root, *extra):
    return subprocess.run([sys.executable, str(SCRIPT), '--repo-root', str(root), *extra], capture_output=True, text=True)


def test_generator_exports_all_plural_categories_placeholders_and_exact_markup(tmp_path):
    root = fixture_repo(tmp_path)
    result = run(root)
    assert result.returncode == 0, result.stderr
    schema = json.loads((root / 'locales/translation_catalog.json').read_text())
    entries = schema['entries']
    plural = [entry for entry in entries if entry['key'] == 'cards']
    assert {entry['form'] for entry in plural} == {'zero','one','two','few','many','other'}
    assert next(entry for entry in plural if entry['form'] == 'few')['source'] == '{count} cards'
    rich = next(entry for entry in entries if entry['key'] == 'hello')
    assert rich['markup'] == ['<b>', '</b>']
    assert rich['tokens'] == ['{name}']
    assert {entry['component'] for entry in entries} == {'addon','reader','extension'}
    builtins = json.loads((root / 'locales/builtin_translation_packs.json').read_text())
    assert set(builtins) == {'en', 'hr', 'zh-Hans'}
    assert builtins['hr']['translations']['addon']['cards::other'] == '{count} cards'


def test_check_detects_source_drift_without_overwriting_exported_catalog(tmp_path):
    root = fixture_repo(tmp_path)
    assert run(root).returncode == 0
    exported = (root / 'locales/translation_catalog.json').read_bytes()
    assert run(root, '--check').returncode == 0
    (root / 'frontend/src/locales/en.json').write_text(json.dumps({'page':'Changed {number}'}))
    result = run(root, '--check')
    assert result.returncode != 0
    assert 'Stale translation catalog' in result.stderr
    assert (root / 'locales/translation_catalog.json').read_bytes() == exported
