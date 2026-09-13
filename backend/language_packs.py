"""Bounded offline translator spreadsheets and atomic, profile-scoped language packs.

Packs contain UI text only. No uploaded code, gettext expressions or HTML
attributes are executed. The English schema is the authority for every cell.
"""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import csv
import io
import json
import os
from pathlib import Path
import re
import secrets
import stat
from string import Formatter

try:
    from .paths import get_language_packs_dir
except ImportError:
    from paths import get_language_packs_dir

ROOT = Path(__file__).resolve().parents[1] / 'locales'
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 20_000
MAX_CELL_BYTES = 16 * 1024
MAX_PACKS = 20
FORMS = ('zero', 'one', 'two', 'few', 'many', 'other')
COMPONENTS = ('addon', 'reader', 'extension')
HEADERS = ('component', 'key', 'form', 'source', 'translation')
TOKEN_RE = re.compile(r'\{[A-Za-z_][A-Za-z_0-9]*(?:![rsa])?(?::[^{}]*)?\}|\$[A-Za-z_][A-Za-z_0-9]*\$')
MARKUP_RE = re.compile(r'<[A-Za-z/!][^>]*>')
_DANGER_URL = re.compile(r'(?:javascript|vbscript)\s*:|data\s*:\s*(?:text/html|image/svg)', re.I)
_FORMULA = re.compile(r"^'*\s*[=+@-]")
_DIRECTORY_FD_SUPPORTED = (os.name != 'nt' and hasattr(os, 'O_DIRECTORY') and os.open in os.supports_dir_fd)
_CONTROLS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


class LanguagePackError(ValueError):
    """Stable error category and spreadsheet row; text follows the active UI locale."""
    def __init__(self, code: str, *, row: int | None = None, details: str = ''):
        self.code, self.row, self.details = code, row, details
        super().__init__(code)

    def __str__(self):
        try:
            from .i18n import t
        except ImportError:
            from i18n import t
        detail = t('backend_language_pack_' + self.code)
        return t('backend_language_pack_row_error', row=self.row, detail=detail) if self.row else detail


def canonical_locale(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 48:
        return None
    parts = value.strip().replace('_', '-').split('-')
    if not re.fullmatch(r'[A-Za-z]{2,3}', parts[0]):
        return None
    result = [parts.pop(0).lower()]
    if parts and re.fullmatch(r'[A-Za-z]{4}', parts[0]):
        result.append(parts.pop(0).title())
    if parts and re.fullmatch(r'[A-Za-z]{2}|[0-9]{3}', parts[0]):
        result.append(parts.pop(0).upper())
    variants = set()
    for part in parts:
        if not re.fullmatch(r'[A-Za-z0-9]{5,8}|[0-9][A-Za-z0-9]{3}', part) or part.lower() in variants:
            return None
        variants.add(part.lower())
        result.append(part.lower())
    return '-'.join(result)


@lru_cache(maxsize=1)
def translation_catalog() -> dict:
    return json.loads((ROOT / 'translation_catalog.json').read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def _entries() -> dict:
    return {(e['component'], e['key'] + ('::' + e['form'] if e['form'] else '')): e
            for e in translation_catalog()['entries']}


def _cell(value: object, row: int | None = None) -> str:
    if not isinstance(value, str) or len(value.encode('utf-8')) > MAX_CELL_BYTES or _CONTROLS.search(value):
        raise LanguagePackError('cell', row=row)
    return value.replace('\r\n', '\n').replace('\r', '\n')


def _validate_text(entry: dict, value: str, row: int | None = None) -> str:
    value = _cell(value, row)
    if not value.strip():
        return ''
    if sorted(TOKEN_RE.findall(value)) != entry['tokens']:
        raise LanguagePackError('tokens', row=row)
    if entry['component'] != 'extension':
        try:
            parsed = list(Formatter().parse(value))
            if entry['component'] == 'addon':
                def fields(parts):
                    return sorted((field, spec, conversion or '') for _literal, field, spec, conversion in parts if field is not None)
                if fields(parsed) != fields(Formatter().parse(entry['source'])):
                    raise ValueError()
            for _text, field, spec, _conversion in parsed:
                if field is not None and (not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', field) or '{' in spec):
                    raise ValueError()
        except ValueError as exc:
            raise LanguagePackError('tokens', row=row) from exc
    if (MARKUP_RE.findall(value) != entry['markup']
            or len(re.findall(r'<(?:/?[A-Za-z]|!)', value)) != len(re.findall(r'<(?:/?[A-Za-z]|!)', entry['source']))):
        raise LanguagePackError('markup', row=row)
    for sequence in ('${', '`'):
        if value.count(sequence) > entry['source'].count(sequence):
            raise LanguagePackError('markup', row=row)
    if sorted(match.lower() for match in _DANGER_URL.findall(value)) != sorted(match.lower() for match in _DANGER_URL.findall(entry['source'])):
        raise LanguagePackError('markup', row=row)
    return value


def validate_pack(pack: object, *, stored: bool = False) -> dict:
    """Normalize a copy. Stored packs tolerate obsolete individual message rows."""
    if not isinstance(pack, dict) or set(pack) != {'version', 'locale', 'name', 'translations'}:
        raise LanguagePackError('format')
    if type(pack['version']) is not int or pack['version'] != 1:
        raise LanguagePackError('version')
    locale = canonical_locale(pack['locale'])
    if not locale:
        raise LanguagePackError('locale')
    name = pack['name']
    if not isinstance(name, str) or not name.strip() or len(name) > 80 or re.search(r'[<>\r\n\t]', name) or _CONTROLS.search(name):
        raise LanguagePackError('name')
    translations = pack['translations']
    if not isinstance(translations, dict) or set(translations) != set(COMPONENTS):
        raise LanguagePackError('format')
    result = {component: {} for component in COMPONENTS}
    count = 0
    for component, messages in translations.items():
        if not isinstance(messages, dict):
            raise LanguagePackError('format')
        count += len(messages)
        if count > MAX_ROWS:
            raise LanguagePackError('rows')
        for key, value in messages.items():
            _cell(key)
            _cell(value)
            entry = _entries().get((component, key))
            if entry is None:
                if stored:
                    continue
                raise LanguagePackError('unknown')
            try:
                value = _validate_text(entry, value)
            except LanguagePackError:
                if stored:
                    continue
                raise
            if value:
                result[component][key] = value
    normalized = {'version': 1, 'locale': locale, 'name': name.strip(), 'translations': result}
    if len(json.dumps(normalized, ensure_ascii=False).encode('utf-8')) > MAX_FILE_BYTES:
        raise LanguagePackError('size')
    return normalized


def _unescape_cell(value: str) -> str:
    value = _cell(value)
    return value[1:] if value.startswith("'") and _FORMULA.match(value[1:]) else value


def parse_csv(data: bytes) -> dict:
    if not isinstance(data, bytes) or len(data) > MAX_FILE_BYTES:
        raise LanguagePackError('size')
    try:
        text = data.decode('utf-8-sig')
    except UnicodeError as exc:
        raise LanguagePackError('encoding') from exc
    # Delimiter is chosen only from the exact header, never inferred from text.
    delimiter = None
    for candidate in (',', ';', '\t'):
        try:
            if next(csv.reader(io.StringIO(text), delimiter=candidate, strict=True), []) == list(HEADERS):
                delimiter = candidate
                break
        except csv.Error:
            continue
    if delimiter is None:
        raise LanguagePackError('headers')
    reader = csv.reader(io.StringIO(text, newline=''), delimiter=delimiter, strict=True)
    next(reader)
    meta, translated, seen = {}, {key: {} for key in COMPONENTS}, set()
    row = 1
    try:
        for row, cells in enumerate(reader, 2):
            if row > MAX_ROWS + 1:
                raise LanguagePackError('rows', row=row)
            if not cells:
                continue
            if len(cells) != len(HEADERS):
                raise LanguagePackError('columns', row=row)
            try:
                component, key, form, source, translation = [_unescape_cell(cell) for cell in cells]
            except LanguagePackError as exc:
                raise LanguagePackError(exc.code, row=row) from exc
            identity = (component, key, form)
            if identity in seen:
                raise LanguagePackError('duplicate', row=row)
            seen.add(identity)
            if component == 'meta':
                if key not in ('version', 'locale', 'name') or form or key in meta:
                    raise LanguagePackError('metadata', row=row)
                meta[key] = translation
                continue
            runtime_key = key + ('::' + form if form else '')
            entry = _entries().get((component, runtime_key))
            if entry is None or form not in ('', *FORMS):
                raise LanguagePackError('unknown', row=row)
            if source != entry['source']:
                raise LanguagePackError('source', row=row)
            value = _validate_text(entry, translation, row)
            if value:
                translated[component][runtime_key] = value
    except csv.Error as exc:
        raise LanguagePackError('format', row=row) from exc
    if set(meta) != {'version', 'locale', 'name'}:
        raise LanguagePackError('metadata')
    if meta['version'] != '1':
        raise LanguagePackError('version')
    return validate_pack({'version': 1, 'locale': meta['locale'], 'name': meta['name'], 'translations': translated})


def export_csv(pack: dict | None = None) -> bytes:
    pack = validate_pack(pack, stored=True) if pack is not None else None
    output = io.StringIO(newline='')
    writer = csv.writer(output, lineterminator='\r\n')
    def write(cells):
        writer.writerow(["'" + value if _FORMULA.match(value) else value for value in cells])
    write(HEADERS)
    write(['meta', 'version', '', 'File format version; keep 1.', '1'])
    write(['meta', 'locale', '', 'Language code, for example de, fr or pt-BR.', pack['locale'] if pack else ''])
    write(['meta', 'name', '', 'Language name in its own language, for example Deutsch.', pack['name'] if pack else ''])
    for entry in translation_catalog()['entries']:
        runtime_key = entry['key'] + ('::' + entry['form'] if entry['form'] else '')
        translation = pack['translations'][entry['component']].get(runtime_key, '') if pack else ''
        write([entry['component'], entry['key'], entry['form'], entry['source'], translation])
    data = output.getvalue().encode('utf-8-sig')
    if len(data) > MAX_FILE_BYTES:
        raise LanguagePackError('size')
    return data


def builtin_pack(locale: str) -> dict:
    """A selected bundled language, ready to edit in the same cross-app sheet."""
    choices = json.loads((ROOT / 'builtin_translation_packs.json').read_text(encoding='utf-8'))
    if locale not in choices:
        raise LanguagePackError('locale')
    return validate_pack(choices[locale], stored=True)


@contextmanager
def _directory(addon_dir: str, profile: str, *, create=False):
    path = get_language_packs_dir(addon_dir, profile)
    base = Path(addon_dir).absolute()
    # Every component is opened relative to a pinned descriptor with NOFOLLOW.
    # This protects both symlink inputs and ancestor swaps during a save.
    parts = path.absolute().relative_to(base).parts
    if not _DIRECTORY_FD_SUPPORTED:
        cursor = Path(base.anchor)
        for part, owned in [(part, False) for part in base.parts[1:]] + [(part, True) for part in parts]:
            cursor /= part
            try:
                info = cursor.lstat()
            except FileNotFoundError:
                if not (create and owned):
                    raise
                cursor.mkdir(mode=0o700)
                info = cursor.lstat()
            _reject_link(info)
            if not stat.S_ISDIR(info.st_mode):
                raise LanguagePackError('storage')
        yield cursor
        return
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, 'O_NOFOLLOW', 0)
    fd = None
    try:
        fd = os.open('/', flags)
        for part, owned in [(part, False) for part in base.parts[1:]] + [(part, True) for part in parts]:
            if create and owned:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        if fd is not None:
            os.close(fd)


def _reject_link(info):
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        # FILE_ATTRIBUTE_REPARSE_POINT includes Windows junctions, not only
        # symlinks exposed by pathlib.is_symlink().
        raise LanguagePackError('storage')


def _checked_file(directory: Path, name: str) -> Path:
    for parent in reversed((directory, *directory.parents)):
        info = parent.lstat()
        _reject_link(info)
        if not stat.S_ISDIR(info.st_mode):
            raise LanguagePackError('storage')
    target = directory / name
    try:
        info = target.lstat()
    except FileNotFoundError:
        return target
    _reject_link(info)
    if not stat.S_ISREG(info.st_mode):
        raise LanguagePackError('storage')
    return target


def _open_relative(directory, name, flags, mode=0o600):
    if isinstance(directory, Path):
        return os.open(_checked_file(directory, name), flags, mode)
    return os.open(name, flags, mode, dir_fd=directory)


def _stat_relative(directory, name):
    if isinstance(directory, Path):
        return _checked_file(directory, name).lstat()
    return os.stat(name, dir_fd=directory, follow_symlinks=False)


def _unlink_relative(directory, name):
    if isinstance(directory, Path):
        _checked_file(directory, name).unlink()
    else:
        os.unlink(name, dir_fd=directory)


def _replace_relative(directory, source, target):
    if isinstance(directory, Path):
        os.replace(_checked_file(directory, source), _checked_file(directory, target))
    else:
        os.replace(source, target, src_dir_fd=directory, dst_dir_fd=directory)


def _unique_json_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate JSON member.')
        value[key] = item
    return value


def _pack_filenames(fd: int) -> list[str]:
    names = []
    with os.scandir(fd) as entries:
        for index, entry in enumerate(entries):
            if index >= MAX_PACKS * 2 + 1:
                raise LanguagePackError('limit')
            if entry.name.endswith('.json'):
                names.append(entry.name)
    return sorted(names)


def _read_file(fd: int, filename: str) -> dict | None:
    opened = None
    try:
        opened = _open_relative(fd, filename, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
        info = os.fstat(opened)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
            return None
        with os.fdopen(opened, 'rb') as file:
            opened = None
            data = file.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            return None
        return validate_pack(json.loads(data, object_pairs_hook=_unique_json_object), stored=True)
    except (OSError, ValueError, UnicodeError, RecursionError):
        return None
    finally:
        if opened is not None:
            os.close(opened)


def load_pack(addon_dir: str, profile: str, locale: str) -> dict | None:
    locale = canonical_locale(locale)
    if locale is None:
        return None
    try:
        with _directory(addon_dir, profile) as fd:
            pack = _read_file(fd, locale + '.json')
            return pack if pack and pack['locale'] == locale else None
    except (OSError, ValueError):
        return None


def list_packs(addon_dir: str, profile: str) -> list[dict]:
    result = []
    try:
        with _directory(addon_dir, profile) as fd:
            files = _pack_filenames(fd)
            for filename in files[:MAX_PACKS]:
                pack = _read_file(fd, filename)
                if pack and filename == pack['locale'] + '.json':
                    result.append({'locale': pack['locale'], 'name': pack['name'], 'choice': 'custom:' + pack['locale'],
                                   'translated': sum(len(items) for items in pack['translations'].values()),
                                   'total': len(_entries())})
    except (OSError, ValueError):
        return []
    return result


def save_pack(addon_dir: str, profile: str, pack: dict) -> None:
    pack = validate_pack(pack)
    data = (json.dumps(pack, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
    filename = pack['locale'] + '.json'
    temporary = '.language-' + secrets.token_hex(12) + '.tmp'
    try:
        with _directory(addon_dir, profile, create=True) as fd:
            names = _pack_filenames(fd)
            if filename not in names and sum(name.endswith('.json') for name in names) >= MAX_PACKS:
                raise LanguagePackError('limit')
            if filename in names:
                info = _stat_relative(fd, filename)
                if not stat.S_ISREG(info.st_mode):
                    raise LanguagePackError('storage')
            opened = _open_relative(fd, temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            try:
                with os.fdopen(opened, 'wb') as file:
                    file.write(data)
                    file.flush()
                    os.fsync(file.fileno())
                _replace_relative(fd, temporary, filename)
                if isinstance(fd, int):
                    os.fsync(fd)
            finally:
                try:
                    _unlink_relative(fd, temporary)
                except FileNotFoundError:
                    pass
    except OSError as exc:
        raise LanguagePackError('storage') from exc


def delete_pack(addon_dir: str, profile: str, locale: str) -> None:
    """Explicit caller-owned rollback only; never called during normal loading."""
    locale = canonical_locale(locale)
    if locale is None:
        raise LanguagePackError('locale')
    try:
        with _directory(addon_dir, profile) as fd:
            filename = locale + '.json'
            if not stat.S_ISREG(_stat_relative(fd, filename).st_mode):
                raise LanguagePackError('storage')
            _unlink_relative(fd, filename)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise LanguagePackError('storage') from exc


@lru_cache(maxsize=1)
def _cardinal_rules():
    return json.loads((ROOT / 'cardinal_rules.json').read_text(encoding='utf-8'))['rules']


def plural_category(locale: str, count: int | float) -> str:
    """Interpret pinned CLDR cardinal relations; never eval uploaded expressions."""
    try:
        raw = str(count)
        if len(raw) > 128:
            return 'other'
        number = abs(Decimal(raw))
        if not number.is_finite() or abs(number.adjusted()) > 100:
            return 'other'
        digits = format(number, 'f').partition('.')[2]
        trimmed = digits.rstrip('0')
        values = {'n': number, 'i': int(number), 'v': len(digits), 'w': len(trimmed),
                  'f': int(digits or '0'), 't': int(trimmed or '0'), 'c': 0, 'e': 0}
    except (ValueError, InvalidOperation):
        return 'other'
    locale = canonical_locale(locale) or 'en'
    rules = _cardinal_rules().get(locale, _cardinal_rules().get(locale.split('-')[0], {}))
    def relation(condition):
        match = re.fullmatch(r'([nivwftce])(?: % (\d+))? (!?=) ([0-9.,]+)', condition)
        if match is None:
            return False
        operand, modulo, operator, ranges = match.groups()
        value = values[operand]
        if modulo:
            value %= int(modulo)
        matched = False
        for item in ranges.split(','):
            bounds = item.split('..')
            low, high = int(bounds[0]), int(bounds[-1])
            # CLDR equality ranges contain integers, unlike the old 'within'.
            if value == int(value) and low <= value <= high:
                matched = True
        return not matched if operator == '!=' else matched
    for form in FORMS[:-1]:
        condition = rules.get(form)
        if condition and any(all(relation(part) for part in term.split(' and ')) for term in condition.split(' or ')):
            return form
    return 'other'
