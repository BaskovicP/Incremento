import assert from 'node:assert/strict';
import test from 'node:test';
import { createReaderLanguage, messageFromCatalogs, normalizeReaderLocale, pluralFromCatalogs, readerMessage, readerPlural } from '../src/i18n.mjs';

test('reader locale normalization distinguishes simplified and traditional Chinese', () => {
  assert.equal(normalizeReaderLocale('hr-HR'), 'hr');
  assert.equal(normalizeReaderLocale('zh-CN'), 'zh-Hans');
  assert.equal(normalizeReaderLocale('zh-Hant'), 'en');
  assert.equal(normalizeReaderLocale(' zh_Hans_CN '), 'zh-Hans');
  assert.equal(normalizeReaderLocale('zh'), 'zh-Hans');
  assert.equal(normalizeReaderLocale('zh-TW'), 'en');
  assert.equal(normalizeReaderLocale('hr-'), 'en');
  assert.equal(normalizeReaderLocale('../hr'), 'en');
  assert.equal(normalizeReaderLocale([]), 'en');
});

test('missing messages and malformed placeholders use readable English fallback', () => {
  const catalogs = {
    en: { title: 'Open {title}' },
    hr: { title: 'Otvori {wrong}' },
  };
  assert.equal(messageFromCatalogs(catalogs, 'hr', 'title', { title: 'Card' }), 'Open Card');
  assert.equal(messageFromCatalogs(catalogs, 'hr', 'absent'), 'Translation unavailable');
  assert.equal(messageFromCatalogs(catalogs, 'hr', 'title'), 'Translation unavailable');
});

test('reader messages interpolate untrusted values as plain text', () => {
  assert.equal(readerMessage('hr', 'reader_go_to_page', { page: '<$>{中文}' }), 'Idi na stranicu <$>{中文}');
  assert.equal(readerMessage('zh-Hans', 'reader_previous_page'), '上一页');
});

test('reader plural uses Croatian CLDR categories and English fallback', () => {
  assert.equal(readerPlural('hr', 'reader_page_cards_tooltip', 2), 'Otvori 2 kartice stvorene na ovoj stranici u pregledniku Anki');
  assert.equal(readerPlural('hr', 'reader_page_cards_tooltip', 5), 'Otvori 5 kartica stvorenih na ovoj stranici u pregledniku Anki');
  assert.equal(readerPlural('zh-Hans', 'reader_page_cards_tooltip', 5), '在 Anki 浏览器中打开本页创建的 5 张卡片');
});

test('malformed or missing Croatian few form falls back through the English plural rule', () => {
  const catalogs = {
    en: { cards_other: 'Open {count} cards' },
    hr: { cards_one: 'Otvori {count} karticu', cards_few: 'Otvori {missing} kartice', cards_other: 'Otvori {count} kartica' },
  };
  assert.equal(pluralFromCatalogs(catalogs, 'hr', 'cards', 2), 'Open 2 cards');
  assert.equal(pluralFromCatalogs({ ...catalogs, hr: { cards_other: 'Otvori {count} kartica' } }, 'hr', 'cards', 2), 'Open 2 cards');
  assert.equal(pluralFromCatalogs(catalogs, 'hr', 'absent', 2), 'Translation unavailable');
  assert.equal(pluralFromCatalogs({ en: { cards_other: 'Open {missing} cards' }, hr: {} }, 'hr', 'cards', 2), 'Translation unavailable');
});

test('custom reader language uses its own messages, locale, and immutable snapshot', () => {
  const pack = { locale: 'de', messages: {
    reader_previous_page: 'Vorherige Seite',
    reader_go_to_page: 'Gehe zu Seite {page}',
  } };
  const language = createReaderLanguage('de', pack);
  pack.messages.reader_previous_page = 'Changed after document start';
  assert.equal(language.locale, 'de');
  assert.equal(language.tr('reader_previous_page'), 'Vorherige Seite');
  assert.equal(language.tr('reader_go_to_page', { page: '<script>$&中文</script>' }), 'Gehe zu Seite <script>$&中文</script>');
  assert.equal(language.tr('reader_next_page'), 'Next page');
});

test('custom plural messages use locale number formatting and CLDR categories', () => {
  const de = createReaderLanguage('de', { locale: 'de', messages: {
    'reader_page_cards_tooltip::one': '{count} Karte öffnen',
    'reader_page_cards_tooltip::other': '{count} Karten öffnen',
  } });
  assert.equal(de.plural('reader_page_cards_tooltip', 1), '1 Karte öffnen');
  assert.equal(de.plural('reader_page_cards_tooltip', 2000), '2.000 Karten öffnen');
  const fr = createReaderLanguage('fr', { locale: 'fr', messages: {
    'reader_page_cards_tooltip::one': 'Ouvrir {count} carte',
    'reader_page_cards_tooltip::other': 'Ouvrir {count} cartes',
  } });
  assert.equal(fr.plural('reader_page_cards_tooltip', 0), 'Ouvrir 0 carte');
  const ar = createReaderLanguage('ar-EG', { locale: 'ar-EG', messages: {
    'reader_page_cards_tooltip::two': 'بطاقتان {count}',
  } });
  assert.equal(ar.plural('reader_page_cards_tooltip', 2), 'بطاقتان ٢');
});

test('missing and malformed custom forms use English rule and complete English message', () => {
  const language = createReaderLanguage('hr', { locale: 'hr', messages: {
    reader_go_to_page: 'Idi na stranicu {wrong}',
    'reader_page_cards_tooltip::few': 'Otvori {wrong} kartice',
    'reader_page_cards_tooltip::other': 'Otvori {count} kartica',
  } });
  assert.equal(language.tr('reader_go_to_page', { page: 3 }), 'Go to page 3');
  assert.equal(language.tr('reader_previous_page'), 'Previous page');
  assert.equal(language.plural('reader_page_cards_tooltip', 2), 'Open the 2 cards created on this page in the Anki Browser');
  assert.equal(language.plural('reader_page_cards_tooltip', 1), 'Open the 1 card created on this page in the Anki Browser');
});

test('a new document without a custom snapshot never retains the prior language pack', () => {
  const pack = { locale: 'de', messages: { reader_previous_page: 'Vorherige Seite' } };
  const first = createReaderLanguage('de', pack);
  const reopened = createReaderLanguage('de', pack);
  const nextProfile = createReaderLanguage('de');
  assert.equal(first.tr('reader_previous_page'), reopened.tr('reader_previous_page'));
  assert.equal(nextProfile.locale, 'en');
  assert.equal(nextProfile.tr('reader_previous_page'), 'Previous page');
});

test('malformed custom snapshots fail closed to English without throwing', () => {
  for (const payload of [[], {}, { locale: '../de', messages: {} }, { locale: 'de', messages: [] }, { locale: 'fr', messages: { reader_previous_page: 'Précédente' } }]) {
    const language = createReaderLanguage('de', payload);
    assert.equal(language.locale, 'en');
    assert.equal(language.tr('reader_previous_page'), 'Previous page');
  }
});

test('an installed language absent from ICU retains its text with English numeric rules', () => {
  const language = createReaderLanguage('qaa', { locale: 'qaa', messages: {
    reader_previous_page: 'Custom previous',
    'reader_page_cards_tooltip::other': 'Custom {count} cards',
  } });
  assert.equal(language.locale, 'qaa');
  assert.equal(language.tr('reader_previous_page'), 'Custom previous');
  assert.equal(language.plural('reader_page_cards_tooltip', 2000), 'Custom 2,000 cards');
});

test('custom translation cannot discard required values or add unknown message identifiers', () => {
  const language = createReaderLanguage('de', { locale: 'de', messages: {
    reader_go_to_page: 'Seite',
    unknown_reader_action: 'Do something else',
    reader_previous_page: 42,
  } });
  assert.equal(language.tr('reader_go_to_page', { page: 3 }), 'Go to page 3');
  assert.equal(language.tr('unknown_reader_action'), 'Translation unavailable');
  assert.equal(language.tr('reader_previous_page'), 'Previous page');
});
