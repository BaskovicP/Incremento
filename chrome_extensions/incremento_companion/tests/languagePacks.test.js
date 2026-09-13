import test from "node:test";
import assert from "node:assert/strict";
import { parseLanguagePackCsv, exportLanguagePackCsv, validateLanguagePack, canonicalPackLocale, packCoverage, MAX_CSV_BYTES } from "../src/shared/languagePacks.js";

const schema = { version: 1, entries: [
  { component: "addon", key: "welcome", form: "", source: "Hello {name}", tokens: ["{name}"], markup: [] },
  { component: "reader", key: "tooltip", form: "", source: '<b title="safe">Open</b>', tokens: [], markup: ['<b title="safe">', '</b>'] },
  { component: "extension", key: "hello", form: "", source: "Hello $NAME$", tokens: ["$NAME$"], markup: [] },
  ...["zero", "one", "two", "few", "many", "other"].map(form => ({ component: "extension", key: "items", form, source: "$COUNT$ items", tokens: ["$COUNT$"], markup: [] })),
  { component: "extension", key: "formula", form: "", source: "+ example", tokens: [], markup: [] },
] };
const pack = () => ({version: 1, locale: "de", name: "Deutsch", translations: { addon: {welcome: "Hallo {name}"}, reader: {tooltip: '<b title="safe">Öffnen</b>'}, extension: {hello: 'Hallo $NAME$, "Freund"\n新しい', "items::one": "$COUNT$ Ding", "items::other": "$COUNT$ Dinge", formula: '=SUM(A1:A2)'} }});

test("one editable CSV round-trips every component, plurals, Unicode, quotes, newlines and formulas", () => {
  const csv = exportLanguagePackCsv(pack(), schema);
  assert.ok(csv.startsWith("\uFEFFcomponent,key,form,source,translation\r\n"));
  assert.ok(csv.includes("'=SUM(A1:A2)"));
  assert.deepEqual(parseLanguagePackCsv(csv, schema), pack());
  assert.equal(packCoverage(pack(), schema).translated, 6);
  assert.equal(packCoverage(pack(), schema).total, 10);
});

test("blank template includes metadata and all current entries while missing translations fall back", () => {
  const csv = exportLanguagePackCsv(null, schema).replace('fr or pt-BR.",', 'fr or pt-BR.",de').replace('for example Deutsch.",', 'for example Deutsch.",Deutsch');
  const parsed = parseLanguagePackCsv(csv, schema);
  assert.equal(parsed.locale, "de");
  assert.deepEqual(parsed.translations, {addon: {}, reader: {}, extension: {}});
});

test("spreadsheet comma, semicolon and tab separators accept BOM and quoted lines", () => {
  for (const delimiter of [",", ";", "\t"]) {
    const csv = exportLanguagePackCsv(pack(), schema, delimiter);
    assert.deepEqual(parseLanguagePackCsv(csv, schema), pack());
  }
});

test("invalid identity, future version, duplicate keys and unknown keys fail with row numbers", () => {
  const good = exportLanguagePackCsv(pack(), schema);
  for (const [csv, code] of [
    [good.replace("File format version; keep 1.,1", "File format version; keep 1.,2"), "version"],
    [good.replace('fr or pt-BR.",de', 'fr or pt-BR.",../../de' ), "locale"],
    [good + "extension,hello,,Hello $NAME$,Hallo $NAME$\r\n", "duplicate"],
    [good + "extension,__proto__,,,value\r\n", "unknown"],
  ]) assert.throws(() => parseLanguagePackCsv(csv, schema), error => error.code === code && error.row > 0);
});

test("untrusted text cannot change protected placeholders or markup and never mutates input", () => {
  for (const invalid of ["Hallo", "Hallo {other}", "Hallo {name} {name}", 'Hallo {name}<img src=x onerror=alert(1)>', "Hallo {name}\u0000"]) {
    const value = pack(); value.translations.addon.welcome = invalid;
    const before = structuredClone(value);
    assert.throws(() => validateLanguagePack(value, schema));
    assert.deepEqual(value, before);
  }
  for (const invalid of ['<b title="javascript:bad">Öffnen</b>', '<b title="safe" onclick="bad()">Öffnen</b>', '<script>bad()</script>']) {
    const value = pack(); value.translations.reader.tooltip = invalid;
    assert.throws(() => validateLanguagePack(value, schema));
  }
});

test("oversized file, oversized cell and malformed quotes fail before returning a pack", () => {
  assert.throws(() => parseLanguagePackCsv("x".repeat(MAX_CSV_BYTES + 1), schema), error => error.code === "size");
  assert.throws(() => parseLanguagePackCsv(exportLanguagePackCsv(pack(), schema) + 'extension,formula,,,"unterminated', schema), error => error.code === "csv");
  const value = pack(); value.translations.extension.formula = "x".repeat(16385);
  assert.throws(() => validateLanguagePack(value, schema), error => error.code === "cell");
});

test("canonical language identities separate imported packs from built-in choices", () => {
  assert.equal(canonicalPackLocale("pt_br"), "pt-BR");
  assert.equal(canonicalPackLocale("zh-hant-tw"), "zh-Hant-TW");
  assert.equal(canonicalPackLocale("hr"), "hr");
  for (const value of ["auto", "custom:de", "__proto__", "en-US-u-ca-gregory", "en--GB", "../de"]) assert.equal(canonicalPackLocale(value), null);
});

test("real file import rejects oversize without reading and refuses damaged UTF-8", async () => {
  const {readLanguagePackFile} = await import("../src/shared/languagePacks.js");
  let reads = 0;
  await assert.rejects(readLanguagePackFile({size: MAX_CSV_BYTES + 1, arrayBuffer: async () => { reads++; }}), error => error.code === "size");
  assert.equal(reads, 0);
  await assert.rejects(readLanguagePackFile({size: 2, arrayBuffer: async () => Uint8Array.from([0xc3, 0x28]).buffer}), error => error.code === "encoding");
});

test("exporting each installed language preserves the entire editable catalog", async () => {
  const {builtinLanguagePack} = await import("../src/shared/languagePacks.js");
  for (const code of ["en", "hr", "zh-Hans"]) {
    const value = await builtinLanguagePack(code);
    const restored = parseLanguagePackCsv(exportLanguagePackCsv(value));
    assert.deepEqual(restored, value);
    for (const component of ["addon", "reader", "extension"]) assert.ok(Object.keys(restored.translations[component]).length > 10);
  }
});
