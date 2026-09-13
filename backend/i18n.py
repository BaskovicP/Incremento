"""Local, dependency-free UI translations; never changes Anki or process locale.

The composition root initializes one translator at startup. Saving a preference
does not replace it: existing reviewers, docks and drafts keep their UI language
until Anki restarts. Catalog domains are separated by their source-code owner.
"""
from __future__ import annotations

import gettext
import struct
from pathlib import Path


LANGUAGES = (("en", "English"), ("hr", "Hrvatski"), ("zh-Hans", "简体中文"))
CATALOG_ROOT = Path(__file__).resolve().parent.parent / "locales"
_UNAVAILABLE = "Translation unavailable"


def _canonical_locale(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip().replace("_", "-").lower()
    parts = value.split("-")
    if parts[0] in {"en", "hr"} and all(part.isalnum() for part in parts):
        return parts[0]
    if parts[0] == "zh" and all(part.isalnum() for part in parts):
        if "hant" in parts or any(region in parts for region in ("tw", "hk", "mo")):
            return None
        if value == "zh" or "hans" in parts or any(region in parts for region in ("cn", "sg")):
            return "zh-Hans"
    return None


def normalize_language_choice(value: object) -> str:
    """Normalize a stored preference; unknown values retain the auto behavior."""
    if isinstance(value, str) and value.strip().startswith("custom:"):
        try:
            from .language_packs import canonical_locale
        except ImportError:
            from language_packs import canonical_locale
        locale = canonical_locale(value.strip()[7:])
        return "custom:" + locale if locale else "auto"
    return _canonical_locale(value) or "auto"


def resolve_locale(choice: object = "auto", host_language: object = "en") -> str:
    normalized = normalize_language_choice(choice)
    return normalized if normalized != "auto" else (_canonical_locale(host_language) or "en")


def _load_catalogs(root: Path, locale: str) -> gettext.NullTranslations:
    chain = gettext.NullTranslations()
    for path in sorted((root / locale / "LC_MESSAGES").glob("incremento*.mo")):
        try:
            with path.open("rb") as stream:
                catalog = gettext.GNUTranslations(stream)
        except (OSError, EOFError, ValueError, UnicodeError, struct.error):
            continue
        chain.add_fallback(catalog)
    return chain


class Translator:
    """A locale-specific catalog snapshot usable in pure tests and background UI models."""

    def __init__(self, locale: str, catalog_dir: Path | str | None = None, *, custom_pack: dict | None = None):
        self.custom_pack = None
        if isinstance(locale, str) and locale.startswith('custom:'):
            try:
                from .language_packs import validate_pack
            except ImportError:
                from language_packs import validate_pack
            try:
                candidate = validate_pack(custom_pack)
                if normalize_language_choice(locale) == 'custom:' + candidate['locale']:
                    self.custom_pack = candidate
            except (ValueError, OSError):
                pass
        self.locale = self.custom_pack['locale'] if self.custom_pack else (_canonical_locale(locale) or "en")
        root = Path(catalog_dir) if catalog_dir is not None else CATALOG_ROOT
        self._english = _load_catalogs(root, "en")
        self._messages = _load_catalogs(root, "en" if self.custom_pack else self.locale)
        if self.locale != "en":
            self._messages.add_fallback(self._english)

    @staticmethod
    def _format(message: str, values: dict) -> str | None:
        try:
            return message.format_map(values)
        except (KeyError, ValueError, IndexError, AttributeError, TypeError):
            return None

    def t(self, message_id: str, **values) -> str:
        if self.custom_pack:
            override = self.custom_pack['translations']['addon'].get(message_id)
            if override:
                formatted = self._format(override, values)
                if formatted is not None:
                    return formatted
        text = self._messages.gettext(message_id)
        if text != message_id:
            formatted = self._format(text, values)
            if formatted is not None:
                return formatted
        english = self._english.gettext(message_id)
        return (self._format(english, values) if english != message_id else None) or _UNAVAILABLE

    def tn(self, message_id: str, count: int, **values) -> str:
        plural_id = message_id + "_plural"
        values = {**values, "count": count}
        if self.custom_pack:
            try:
                from .language_packs import plural_category
            except ImportError:
                from language_packs import plural_category
            key = message_id + '::' + plural_category(self.locale, count)
            override = self.custom_pack['translations']['addon'].get(key)
            if override:
                formatted = self._format(override, values)
                if formatted is not None:
                    return formatted
        text = self._messages.ngettext(message_id, plural_id, count)
        if text not in (message_id, plural_id):
            formatted = self._format(text, values)
            if formatted is not None:
                return formatted
        english = self._english.ngettext(message_id, plural_id, count)
        return (self._format(english, values) if english not in (message_id, plural_id) else None) or _UNAVAILABLE


_translator = Translator("en")


def initialize_language(choice: object = "auto", host_language: object = "en", *, custom_pack: dict | None = None) -> str:
    """Called only by addon startup; config writes deliberately do not call this."""
    global _translator
    _translator = Translator(resolve_locale(choice, host_language), custom_pack=custom_pack)
    return _translator.locale


def get_custom_reader_payload() -> dict | None:
    """Return an independent, validated snapshot for this profile's PDF viewer."""
    pack = _translator.custom_pack
    return {'locale': pack['locale'], 'messages': dict(pack['translations']['reader'])} if pack else None


def get_locale() -> str:
    return _translator.locale


def t(message_id: str, **values) -> str:
    return _translator.t(message_id, **values)


def tn(message_id: str, count: int, **values) -> str:
    return _translator.tn(message_id, count, **values)


def format_number(value: int | float, *, digits: int | None = None) -> str:
    """Format UI numbers without changing the process locale or stored value."""
    rendered = format(value, ',' if digits is None else f',.{digits}f')
    if get_locale() == 'hr':
        return rendered.translate(str.maketrans({',': '.', '.': ','}))
    return rendered


def format_date(value, format: str = 'short') -> str:
    """Format a date/ISO date for display; persisted dates remain ISO 8601."""
    from datetime import date

    if format != 'short':
        raise ValueError('Only the short display date format is supported.')
    if isinstance(value, str):
        value = date.fromisoformat(value)
    if not isinstance(value, date):
        raise TypeError('Expected a date or ISO date string.')
    if get_locale() == 'hr':
        return f'{value.day}. {value.month}. {value.year}.'
    if get_locale() == 'zh-Hans':
        return f'{value.year}/{value.month}/{value.day}'
    return f'{value.month}/{value.day}/{value.year}'
