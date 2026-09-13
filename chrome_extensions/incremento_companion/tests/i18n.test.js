import test from "node:test";
import assert from "node:assert/strict";
import {
  normalizeLanguagePreference,
  resolveLocale,
  createTranslator,
  initializeLanguage,
  currentLocale,
  applyStoredLanguageChange,
  saveLanguage,
  displayMessage,
  message,
  formatNumber,
} from "../src/shared/i18n.js";

test("manual language wins over Chrome; auto falls back without converting traditional Chinese", () => {
  assert.equal(normalizeLanguagePreference("hr-HR"), "hr");
  assert.equal(normalizeLanguagePreference("zh_CN"), "zh-Hans");
  assert.equal(normalizeLanguagePreference("zh"), "zh-Hans");
  assert.equal(normalizeLanguagePreference("zh-Hans-TW"), "auto");
  assert.equal(normalizeLanguagePreference("zh-Hant"), "auto");
  assert.equal(normalizeLanguagePreference("hr-"), "auto");
  assert.equal(normalizeLanguagePreference("en--"), "auto");
  assert.equal(resolveLocale("zh-Hans", "hr-HR"), "zh-Hans");
  assert.equal(resolveLocale("auto", "zh-TW"), "en");
  assert.equal(resolveLocale("auto", "hr-HR"), "hr");
});

test("catalog translator uses English fallback and locale-specific plural rules", () => {
  const catalogs = {
    en: { greeting: { message: "Hello, $NAME$", placeholders: { name: { content: "$1" } } }, item_one: { message: "$COUNT$ item", placeholders: { count: { content: "$1" } } }, item_other: { message: "$COUNT$ items", placeholders: { count: { content: "$1" } } } },
    hr: { greeting: { message: "Bok, $NAME$", placeholders: { name: { content: "$1" } } }, item_one: { message: "$COUNT$ stavka", placeholders: { count: { content: "$1" } } }, item_few: { message: "$COUNT$ stavke", placeholders: { count: { content: "$1" } } }, item_other: { message: "$COUNT$ stavki", placeholders: { count: { content: "$1" } } } },
    "zh-Hans": { greeting: { message: "你好，$NAME$", placeholders: { name: { content: "$1" } } }, item_other: { message: "$COUNT$ 项", placeholders: { count: { content: "$1" } } } },
  };
  const hr = createTranslator("hr", catalogs);
  for (const [count, expected] of [[0, "0 stavki"], [1, "1 stavka"], [2, "2 stavke"], [5, "5 stavki"], [11, "11 stavki"], [12, "12 stavki"], [21, "21 stavka"], [22, "22 stavke"], [25, "25 stavki"]]) {
    assert.equal(hr.plural("item", count), expected);
  }
  assert.equal(createTranslator("zh-Hans", catalogs).plural("item", 22), "22 项");
  assert.equal(createTranslator("hr", catalogs).text("missing", {}, "Fallback"), "Fallback");
  assert.equal(hr.text("greeting", { name: "$1 {x} <中文>" }), "Bok, $1 {x} <中文>");
});

test("malformed translated placeholders fall back to English without reprocessing values", () => {
  const catalogs = {
    en: { greeting: { message: "Hello, $NAME$", placeholders: { name: { content: "$1" } } } },
    hr: { greeting: { message: "Bok, $UNKNOWN$", placeholders: { name: { content: "$1" } } } },
  };
  const translator = createTranslator("hr", catalogs);
  assert.equal(translator.text("greeting", { name: "$1 {x} <中文>" }), "Hello, $1 {x} <中文>");
  assert.equal(translator.text("greeting", {}), "Translation unavailable");
  assert.equal(translator.text("future_key"), "Translation unavailable");
  assert.equal(translator.text("future_key", {}, "Readable fallback"), "Readable fallback");
});

test("malformed or incomplete translated plural families use the whole English plural rule", () => {
  const en = {
    item_one: { message: "$COUNT$ item", placeholders: { count: { content: "$1" } } },
    item_other: { message: "$COUNT$ items", placeholders: { count: { content: "$1" } } },
  };
  const hr = {
    item_one: { message: "$COUNT$ stavka", placeholders: { count: { content: "$1" } } },
    item_few: { message: "$UNKNOWN$ stavke", placeholders: { count: { content: "$1" } } },
    item_other: { message: "$COUNT$ stavki", placeholders: { count: { content: "$1" } } },
  };
  assert.equal(createTranslator("hr", { en, hr }).plural("item", 2), "2 items");
  assert.equal(createTranslator("hr", { en, hr }).plural("item", 21), "21 items");
  assert.equal(createTranslator("hr", { en, hr: { item_one: hr.item_one } }).plural("item", 21), "21 items");
  assert.equal(createTranslator("hr", { en: {}, hr }).plural("unknown", 2), "Translation unavailable");
});

test("storage change wins over a stale startup read", async () => {
  let finishRead;
  const chromeApi = {
    storage: { local: { get: () => new Promise((resolve) => { finishRead = resolve; }) } },
    i18n: { getUILanguage: () => "en-US" },
  };
  const loading = initializeLanguage(chromeApi);
  applyStoredLanguageChange("zh-Hans", chromeApi);
  finishRead({ ui_language: "hr" });
  await loading;
  assert.equal(currentLocale(), "zh-Hans");
});

test("Save persists only the language key and failed writes keep the effective language", async () => {
  const writes = [];
  const chromeApi = {
    storage: { local: { set: async (value) => { writes.push(value); } } },
    i18n: { getUILanguage: () => "en-US" },
  };
  applyStoredLanguageChange("en", chromeApi);
  await saveLanguage("hr-HR", chromeApi);
  assert.deepEqual(writes, [{ ui_language: "hr" }]);
  assert.equal(currentLocale(), "hr");
  chromeApi.storage.local.set = async () => { throw new Error("write failed"); };
  await assert.rejects(saveLanguage("zh-Hans", chromeApi), /write failed/);
  assert.equal(currentLocale(), "hr");
});

test("message descriptors retranslate running progress without changing parameters", () => {
  const progress = message("importing_item", { index: 2, count: 3, title: "<中文>" });
  applyStoredLanguageChange("hr", { i18n: { getUILanguage: () => "en" } });
  assert.equal(displayMessage(progress), "Uvoz 2 od 3: <中文>");
  applyStoredLanguageChange("zh-Hans", { i18n: { getUILanguage: () => "en" } });
  assert.equal(displayMessage(progress), "正在导入第 2 项，共 3 项：<中文>");
  applyStoredLanguageChange("en", { i18n: { getUILanguage: () => "en" } });
});

test("nested kind labels retranslate with a saved status and leave user text untouched", () => {
  const status = message("added_card", { kind: message("webpage_kind"), title: "My webpage $KIND$" });
  const original = structuredClone(status);
  applyStoredLanguageChange("hr", { i18n: { getUILanguage: () => "en" } });
  assert.equal(displayMessage(status), "Dodana kartica vrste Mrežna stranica: My webpage $KIND$");
  applyStoredLanguageChange("zh-Hans", { i18n: { getUILanguage: () => "en" } });
  assert.equal(displayMessage(status), "已添加 网页 卡片：My webpage $KIND$");
  assert.deepEqual(status, original);
  applyStoredLanguageChange("en", { i18n: { getUILanguage: () => "en" } });
});

test("count formatting follows the effective catalog locale", () => {
  applyStoredLanguageChange("hr", { i18n: { getUILanguage: () => "en" } });
  assert.equal(formatNumber(2000000), "2.000.000");
  applyStoredLanguageChange("zh-Hans", { i18n: { getUILanguage: () => "en" } });
  assert.equal(formatNumber(2000000), "2,000,000");
  applyStoredLanguageChange("en", { i18n: { getUILanguage: () => "en" } });
});
