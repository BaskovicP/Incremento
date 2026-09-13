#!/usr/bin/env python3
"""Build the offline spreadsheet schema from shipped English source catalogs."""
from __future__ import annotations

import argparse
import gettext
import io
import json
from pathlib import Path
import re
import subprocess

FORMS = ('zero', 'one', 'two', 'few', 'many', 'other')
TOKEN_RE = re.compile(r'\{[A-Za-z_][A-Za-z_0-9]*(?:![rsa])?(?::[^{}]*)?\}|\$[A-Za-z_][A-Za-z_0-9]*\$')
MARKUP_RE = re.compile(r'<[A-Za-z/!][^>]*>')


def build_catalog(root: Path) -> dict:
    entries = []
    def add(component, key, form, source):
        entries.append({'component': component, 'key': key, 'form': form, 'source': source,
                        'tokens': sorted(TOKEN_RE.findall(source)), 'markup': MARKUP_RE.findall(source)})
    for path in sorted((root / 'locales/en/LC_MESSAGES').glob('incremento*.po')):
        compiled = subprocess.run(['msgfmt', '--endianness=little', '-o', '-', str(path)], check=True, capture_output=True).stdout
        messages = gettext.GNUTranslations(io.BytesIO(compiled))._catalog
        plural_ids = {key[0] for key in messages if isinstance(key, tuple)}
        for key, source in messages.items():
            if isinstance(key, str) and key:
                add('addon', key, '', source)
        for key in sorted(plural_ids):
            for form in FORMS:
                add('addon', key, form, messages[key, 0 if form == 'one' else 1])
    for component, path in (
        ('reader', root / 'frontend/src/locales/en.json'),
        ('extension', root / 'chrome_extensions/incremento_companion/_locales/en/messages.json'),
    ):
        raw = json.loads(path.read_text(encoding='utf-8'))
        messages = {key: value['message'] if isinstance(value, dict) else value for key, value in raw.items()}
        plural_ids = {key[:-4] for key in messages if key.endswith('_one') and key[:-4] + '_other' in messages}
        for key, source in messages.items():
            if any(key == base + '_' + form for base in plural_ids for form in FORMS):
                continue
            add(component, key, '', source)
        for key in sorted(plural_ids):
            for form in FORMS:
                add(component, key, form, messages[key + ('_one' if form == 'one' else '_other')])
    entries.sort(key=lambda entry: (entry['component'], entry['key'], entry['form']))
    identities = {(entry['component'], entry['key'], entry['form']) for entry in entries}
    if len(identities) != len(entries):
        raise ValueError('Duplicate translation catalog key.')
    return {'version': 1, 'entries': entries}


def build_builtin_packs(root: Path, schema: dict) -> dict:
    result = {}
    for locale, name, chrome_locale in [('en', 'English', 'en'), ('hr', 'Hrvatski', 'hr'), ('zh-Hans', '简体中文', 'zh_CN')]:
        catalogs = gettext.NullTranslations()
        for path in sorted((root / 'locales' / locale / 'LC_MESSAGES').glob('incremento*.po')):
            compiled = subprocess.run(['msgfmt', '--endianness=little', '-o', '-', str(path)], check=True, capture_output=True).stdout
            catalogs.add_fallback(gettext.GNUTranslations(io.BytesIO(compiled)))
        reader = json.loads((root / 'frontend/src/locales' / (locale + '.json')).read_text(encoding='utf-8'))
        extension = json.loads((root / 'chrome_extensions/incremento_companion/_locales' / chrome_locale / 'messages.json').read_text(encoding='utf-8'))
        translations = {component: {} for component in ('addon', 'reader', 'extension')}
        for entry in schema['entries']:
            component, key, form = entry['component'], entry['key'], entry['form']
            runtime_key = key + ('::' + form if form else '')
            if component == 'addon':
                value = catalogs.ngettext(key, key + '_plural', {'zero':0, 'one':1, 'two':2, 'few':2, 'many':5, 'other':5}[form]) if form else catalogs.gettext(key)
            else:
                messages = reader if component == 'reader' else extension
                lookup = key + ('_' + form if form else '')
                value = messages.get(lookup, messages.get(key + '_other', entry['source']))
                if isinstance(value, dict):
                    value = value['message']
            # Builtin catalogs sometimes change HTML whitespace/quotes. Keep the
            # English tag bytes in the editable sheet while retaining translated
            # text; attributes are a read-only part of the import contract.
            tags = MARKUP_RE.findall(value)
            if len(tags) == len(entry['markup']):
                replacements = iter(entry['markup'])
                value = MARKUP_RE.sub(lambda _match: next(replacements), value)
            translations[component][runtime_key] = value
        result[locale] = {'version': 1, 'locale': locale, 'name': name, 'translations': translations}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    path = args.repo_root / 'locales/translation_catalog.json'
    schema = build_catalog(args.repo_root)
    outputs = {path: schema, args.repo_root / 'locales/builtin_translation_packs.json': build_builtin_packs(args.repo_root, schema)}
    for path, content in outputs.items():
        _write_or_check(path, content, args.check)
    print('Translation spreadsheet catalogs are current.')


def _write_or_check(path, content, check):
    data = (json.dumps(content, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    if path.is_symlink():
        raise SystemExit('Translation catalog may not be a symlink.')
    if check:
        if not path.is_file() or path.read_bytes() != data:
            raise SystemExit('Stale translation catalog; run scripts/build_translation_catalog.py')
    else:
        path.write_bytes(data)


if __name__ == '__main__':
    main()
