"""Language choice and real gettext fallback, independent of Anki/Qt."""
from __future__ import annotations

import struct
from pathlib import Path

import pytest

from backend import i18n


def _catalog(root: Path, locale: str, messages: dict[str, str], domain="incremento_core"):
    entries = {
        "": "Content-Type: text/plain; charset=UTF-8\nPlural-Forms: " + {
            "en": "nplurals=2; plural=(n != 1);",
            "hr": "nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<12 || n%100>14) ? 1 : 2);",
            "zh-Hans": "nplurals=1; plural=0;",
        }[locale] + "\n",
        **messages,
    }
    pairs = [(k.encode(), v.encode()) for k, v in sorted(entries.items())]
    count = len(pairs)
    start = 28 + 16 * count
    source = b"".join(k + b"\0" for k, _ in pairs)
    target = b"".join(v + b"\0" for _, v in pairs)
    offsets, cursor = [], start
    for key, _ in pairs:
        offsets.append(struct.pack("<2I", len(key), cursor))
        cursor += len(key) + 1
    cursor = start + len(source)
    for _, value in pairs:
        offsets.append(struct.pack("<2I", len(value), cursor))
        cursor += len(value) + 1
    file = root / locale / "LC_MESSAGES" / f"{domain}.mo"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(struct.pack("<7I", 0x950412DE, 0, count, 28, 28 + 8 * count, 0, 0)
                     + b"".join(offsets) + source + target)


@pytest.mark.parametrize("choice,host,expected", [
    ("auto", "en_US", "en"), ("auto", "hr_HR", "hr"),
    ("auto", "zh_CN", "zh-Hans"), ("auto", "zh-TW", "en"),
    ("auto", "de-DE", "en"), ("hr", "en", "hr"),
    ("en", "hr", "en"), ("zh-Hans", "hr", "zh-Hans"),
    (None, "hr", "hr"), ([], "hr", "hr"), ("../hr", "en", "en"),
])
def test_manual_language_overrides_host_and_auto_resolves_supported_aliases(choice, host, expected):
    assert i18n.resolve_locale(choice, host) == expected


def test_language_registry_has_stable_codes_and_native_labels():
    assert dict(i18n.LANGUAGES) == {"en": "English", "hr": "Hrvatski", "zh-Hans": "简体中文"}
    assert i18n.normalize_language_choice("hr_HR") == "hr"
    assert i18n.normalize_language_choice("zh_CN") == "zh-Hans"
    assert i18n.normalize_language_choice("zh-Hant") == "auto"


def test_missing_local_message_uses_english_across_domains(tmp_path):
    _catalog(tmp_path, "en", {"save": "Save", "title": "Open {title}"})
    _catalog(tmp_path, "hr", {"save": "Spremi"})
    _catalog(tmp_path, "en", {"reader": "Reader"}, "incremento_readers")
    translator = i18n.Translator("hr", tmp_path)
    assert translator.t("save") == "Spremi"
    assert translator.t("reader") == "Reader"
    assert translator.t("title", title="<你好> ${x}") == "Open <你好> ${x}"


@pytest.mark.parametrize("count,expected", [(0,"0 kartica"),(1,"1 kartica"),(2,"2 kartice"),
    (5,"5 kartica"),(11,"11 kartica"),(12,"12 kartica"),(21,"21 kartica"),(22,"22 kartice")])
def test_gettext_uses_croatian_plural_forms(tmp_path, count, expected):
    _catalog(tmp_path, "en", {"cards\0cards_plural": "{count} card\0{count} cards"})
    _catalog(tmp_path, "hr", {"cards\0cards_plural": "{count} kartica\0{count} kartice\0{count} kartica"})
    assert i18n.Translator("hr", tmp_path).tn("cards", count) == expected


def test_plural_fallback_uses_english_rules_not_croatian_rule_index(tmp_path):
    _catalog(tmp_path, "en", {"cards\0cards_plural": "{count} card\0{count} cards"})
    _catalog(tmp_path, "hr", {"save": "Spremi"})
    assert i18n.Translator("hr", tmp_path).tn("cards", 21) == "21 cards"


def test_chinese_is_invariant_and_invalid_translation_format_falls_back(tmp_path):
    _catalog(tmp_path, "en", {"cards\0cards_plural": "{count} card\0{count} cards", "title": "Open {title}"})
    _catalog(tmp_path, "zh-Hans", {"cards\0cards_plural": "{count} 张卡片", "title": "打开{wrong}"})
    translator = i18n.Translator("zh-Hans", tmp_path)
    assert translator.tn("cards", 5) == "5 张卡片"
    assert translator.t("title", title="中文") == "Open 中文"


def test_unavailable_catalog_and_unknown_id_do_not_expose_machine_id(tmp_path):
    assert i18n.Translator("hr", tmp_path).t("internal_missing_key") == "Translation unavailable"


def test_saving_language_does_not_change_active_translator(monkeypatch):
    import backend.config_service as config_service
    from unittest.mock import Mock
    previous = i18n.get_locale()
    try:
        i18n.initialize_language("en", "hr")
        config_service.save_addon_config(Mock(), "incremento", {"ui_language": "hr"})
        assert i18n.get_locale() == "en"
        i18n.initialize_language("hr", "en")
        assert i18n.get_locale() == "hr"
    finally:
        i18n.initialize_language(previous, "en")


@pytest.mark.parametrize('locale,number,expected', [
    ('en', 12345.5, '12,345.5'), ('hr', 12345.5, '12.345,5'),
    ('zh-Hans', 12345.5, '12,345.5'), ('hr', -1000, '-1.000'),
])
def test_numbers_follow_interface_locale_without_changing_values(locale, number, expected):
    import backend.i18n as i18n
    old = i18n.get_locale()
    try:
        i18n.initialize_language(locale)
        assert i18n.format_number(number) == expected
    finally:
        i18n.initialize_language(old)


@pytest.mark.parametrize('locale,expected', [
    ('en', '9/13/2026'), ('hr', '13. 9. 2026.'), ('zh-Hans', '2026/9/13'),
])
def test_dates_use_display_locale_and_leave_iso_storage_unchanged(locale, expected):
    import backend.i18n as i18n
    from datetime import date
    value = date(2026, 9, 13)
    old = i18n.get_locale()
    try:
        i18n.initialize_language(locale)
        assert i18n.format_date(value) == expected
        assert i18n.format_date(value.isoformat()) == expected
        assert value.isoformat() == '2026-09-13'
    finally:
        i18n.initialize_language(old)


def test_truncated_local_catalog_uses_english_fallback(tmp_path):
    _catalog(tmp_path, 'en', {'hello': 'Hello'})
    path = tmp_path / 'hr/LC_MESSAGES/incremento_broken.mo'
    path.parent.mkdir(parents=True)
    path.write_bytes(struct.pack('<I', 0x950412DE))
    assert i18n.Translator('hr', tmp_path).t('hello') == 'Hello'
