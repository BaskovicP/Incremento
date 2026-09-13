"""Real gettext compilation must reject unshippable translation catalogs."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'compile_i18n.py'


def catalog(root, language, messages, domain='incremento_core'):
    path = root / 'locales' / language / 'LC_MESSAGES' / f'{domain}.po'
    path.parent.mkdir(parents=True, exist_ok=True)
    header = f'Language: {language}\nContent-Type: text/plain; charset=UTF-8\nPlural-Forms: nplurals=2; plural=(n != 1);\n'
    rows = ['msgid ""', 'msgstr ' + json.dumps(header), '']
    for key, value in messages.items():
        rows += ['msgid ' + json.dumps(key), 'msgstr ' + json.dumps(value), '']
    path.write_text('\n'.join(rows))
    return path


def run(root, *options):
    return subprocess.run([sys.executable, str(SCRIPT), '--repo-root', str(root), *options], capture_output=True, text=True)


def test_compilation_and_drift_detection(tmp_path):
    en = catalog(tmp_path, 'en', {'greeting': 'Hello {name}'})
    catalog(tmp_path, 'hr', {'greeting': 'Bok {name}'})
    assert run(tmp_path).returncode == 0
    assert en.with_suffix('.mo').is_file()
    assert run(tmp_path, '--check').returncode == 0
    catalog(tmp_path, 'hr', {'greeting': 'Pozdrav {name}'})
    result = run(tmp_path, '--check')
    assert result.returncode != 0
    assert 'stale' in result.stderr.lower()


@pytest.mark.parametrize('translated,problem', [
    ({'other': 'Drugo'}, 'keys'),
    ({'greeting': 'Bok {wrong}'}, 'placeholder'),
    ({'greeting': ''}, 'keys'),
    ({'greeting': 'Bok {name.__class__}'}, 'placeholder'),
])
def test_rejects_missing_keys_or_changed_interpolation(tmp_path, translated, problem):
    catalog(tmp_path, 'en', {'greeting': 'Hello {name}'})
    catalog(tmp_path, 'hr', translated)
    result = run(tmp_path)
    assert result.returncode != 0
    assert problem in result.stderr.lower()
    assert not list(tmp_path.rglob('*.mo'))


def test_rejects_duplicate_ids_across_domains(tmp_path):
    catalog(tmp_path, 'en', {'greeting': 'Hello'})
    catalog(tmp_path, 'en', {'greeting': 'Other'}, 'incremento_other')
    result = run(tmp_path)
    assert result.returncode != 0
    assert 'duplicate' in result.stderr.lower()


def test_rejects_symlink_catalog(tmp_path):
    external = tmp_path / 'external.po'
    external.write_text('private')
    po = catalog(tmp_path, 'en', {'greeting': 'Hello'})
    po.unlink()
    po.symlink_to(external)
    result = run(tmp_path)
    assert result.returncode != 0
    assert 'symlink' in result.stderr.lower()


def test_rejects_source_reference_to_missing_message(tmp_path):
    catalog(tmp_path, 'en', {'greeting': 'Hello'})
    code = tmp_path / 'frontend/dialog.py'
    code.parent.mkdir()
    code.write_text("label = t('missing_message')\n")
    result = run(tmp_path)
    assert result.returncode != 0
    assert 'missing_message' in result.stderr
    assert 'source' in result.stderr.lower()


def test_rejects_source_call_without_required_placeholder(tmp_path):
    catalog(tmp_path, 'en', {'greeting': 'Hello {name}'})
    (tmp_path / '__init__.py').write_text("label = t('greeting')\n")
    result = run(tmp_path)
    assert result.returncode != 0
    assert 'name' in result.stderr and 'placeholder' in result.stderr.lower()
    assert not list(tmp_path.rglob('*.mo'))


@pytest.mark.parametrize('options', [(), ('--check',)])
def test_output_symlink_is_rejected_before_any_write(tmp_path, options):
    en = catalog(tmp_path, 'en', {'greeting': 'Hello'})
    hr = catalog(tmp_path, 'hr', {'greeting': 'Bok'})
    external = tmp_path / 'private.mo'
    external.write_bytes(b'private bytes')
    hr.with_suffix('.mo').symlink_to(external)
    result = run(tmp_path, *options)
    assert result.returncode != 0
    assert 'symlink' in result.stderr.lower()
    assert external.read_bytes() == b'private bytes'
    assert not en.with_suffix('.mo').exists()
