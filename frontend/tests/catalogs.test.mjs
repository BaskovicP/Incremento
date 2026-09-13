import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import test from 'node:test';

const sourceRoot = new URL('../src/', import.meta.url);
const catalogs = Object.fromEntries(
  ['en', 'hr', 'zh-Hans'].map((locale) => [
    locale,
    JSON.parse(readFileSync(new URL(`locales/${locale}.json`, sourceRoot), 'utf8')),
  ]),
);
const pluralSuffix = /_(one|few|other)$/;
const categories = { en: ['one', 'other'], hr: ['one', 'few', 'other'], 'zh-Hans': ['other'] };

function placeholders(message) {
  return [...new Set([...message.matchAll(/\{([a-z][a-z0-9_]*)\}/g)].map((match) => match[1]))].sort();
}

function sourceFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const url = new URL(entry.name + (entry.isDirectory() ? '/' : ''), directory);
    return entry.isDirectory()
      ? sourceFiles(url)
      : (/\.(?:jsx?|mjs)$/.test(entry.name) ? [url] : []);
  });
}

test('reader catalogs have complete language plural categories and matching placeholders', () => {
  const bases = Object.fromEntries(Object.entries(catalogs).map(([locale, catalog]) => [
    locale,
    [...new Set(Object.keys(catalog).map((key) => key.replace(pluralSuffix, '')))].sort(),
  ]));
  assert.deepEqual(bases.hr, bases.en);
  assert.deepEqual(bases['zh-Hans'], bases.en);

  for (const base of bases.en) {
    assert.match(base, /^[a-z][a-z0-9_]*$/);
    const isPlural = Object.hasOwn(catalogs.en, `${base}_other`);
    const expected = placeholders(catalogs.en[isPlural ? `${base}_other` : base]);
    for (const [locale, catalog] of Object.entries(catalogs)) {
      const expectedKeys = isPlural ? categories[locale].map((suffix) => `${base}_${suffix}`) : [base];
      const actualKeys = Object.keys(catalog).filter((key) => key === base || key.replace(pluralSuffix, '') === base).sort();
      assert.deepEqual(actualKeys, expectedKeys.sort(), `${locale}.${base} forms`);
      for (const key of expectedKeys) {
        assert.equal(typeof catalog[key], 'string', `${locale}.${key} missing`);
        assert.ok(catalog[key].trim(), `${locale}.${key} empty`);
        assert.deepEqual(placeholders(catalog[key]), expected, `${locale}.${key} placeholders`);
      }
    }
  }
});

test('literal reader message and plural references resolve to catalog entries', () => {
  let references = 0;
  for (const url of sourceFiles(sourceRoot)) {
    const source = readFileSync(url, 'utf8');
    const calls = [
      ...source.matchAll(/\b(tr|plural)\(\s*['"]([a-z][a-z0-9_]*)['"]/g),
      ...source.matchAll(/\b(readerMessage|readerPlural)\(\s*[^,]+,\s*['"]([a-z][a-z0-9_]*)['"]/g),
    ];
    for (const match of calls) {
      references += 1;
      const [, kind, id] = match;
      if (kind === 'plural' || kind === 'readerPlural') {
        for (const [locale, forms] of Object.entries(categories)) {
          for (const form of forms) {
            assert.ok(Object.hasOwn(catalogs[locale], `${id}_${form}`), `${url.pathname}: ${locale}.${id}_${form}`);
          }
        }
      } else {
        for (const [locale, catalog] of Object.entries(catalogs)) {
          assert.ok(Object.hasOwn(catalog, id), `${url.pathname}: ${locale}.${id}`);
        }
      }
    }
  }
  assert.ok(references > 100, `Only ${references} reader references scanned`);
});
