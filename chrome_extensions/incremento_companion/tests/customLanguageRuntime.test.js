import test from "node:test";
import assert from "node:assert/strict";
import { initializeLanguage, applyStoredLanguageChange, currentLocale, currentPreference, currentLanguagePacks, currentLanguageSnapshot, saveLanguageSettings, subscribeLanguage, watchLanguageStorage, t, tn, createTranslator } from "../src/shared/i18n.js";
import { stageLanguagePack } from "../src/shared/languagePacks.js";

const german = () => ({ version: 1, locale: "de", name: "Deutsch", translations: { addon: {}, reader: {}, extension: { settings: "Einstellungen", "item::one": "$COUNT$ Notiz", "item::other": "$COUNT$ Notizen" } } });
const chromeFake = (stored = {}) => {
  const state = structuredClone(stored), writes = [], listeners = [];
  return { state, writes, listeners, i18n: { getUILanguage: () => "en-US" }, storage: { onChanged: {addListener: callback => listeners.push(callback), removeListener: callback => listeners.splice(listeners.indexOf(callback), 1)}, local: { get: async () => structuredClone(state), set: async update => { writes.push(structuredClone(update)); Object.assign(state, structuredClone(update)); } } } };
};

test("custom language cold startup loads its validated pack before the first translated action", async () => {
  const api = chromeFake({ ui_language: "custom:de", ui_language_packs: {de: german()} });
  await initializeLanguage(api);
  assert.equal(currentLocale(), "de");
  assert.equal(currentPreference(), "custom:de");
  assert.equal(t("settings"), "Einstellungen");
  assert.equal(t("language_save"), "Save");
});

test("import remains a draft until Save and failed atomic persistence keeps the active language", async () => {
  const api = chromeFake({ui_language: "en"});
  await initializeLanguage(api);
  const staged = stageLanguagePack({}, german());
  assert.equal(t("settings"), "Settings");
  assert.deepEqual(api.writes, []); // Cancel simply discards this UI-owned draft.
  api.storage.local.set = async () => { throw Error("quota"); };
  await assert.rejects(saveLanguageSettings("custom:de", staged, api), /quota/);
  assert.equal(currentLocale(), "en");
  assert.deepEqual(currentLanguagePacks(), {});
});

test("Save writes packs and selected language together and retains unrelated stored imports", async () => {
  const french = {...german(), locale: "fr", name: "Français"};
  const api = chromeFake({ ui_language: "en", ui_language_packs: {fr: french} });
  await initializeLanguage(api);
  await saveLanguageSettings("custom:de", stageLanguagePack({}, german()), api);
  assert.equal(api.writes.length, 1);
  assert.deepEqual(Object.keys(api.writes[0]).sort(), ["ui_language", "ui_language_packs"]);
  assert.equal(api.state.ui_language_packs.fr.name, "Français");
  assert.equal(t("settings"), "Einstellungen");
});

test("replacing a pack in an existing context changes its snapshot even when locale is unchanged", async () => {
  const api = chromeFake({ ui_language: "custom:de", ui_language_packs: {de: german()} });
  await initializeLanguage(api);
  const before = currentLanguageSnapshot();
  const updated = german(); updated.translations.extension.settings = "Neue Einstellungen";
  const stop = watchLanguageStorage(api);
  const broadcasts = [];
  const unsubscribe = subscribeLanguage(code => broadcasts.push(code));
  api.listeners[0]({ui_language_packs: {newValue: {de: updated}}}, "local");
  assert.equal(t("settings"), "Neue Einstellungen");
  assert.notEqual(currentLanguageSnapshot(), before);
  assert.deepEqual(broadcasts, ["de"]);
  stop(); unsubscribe();
});

test("malformed saved imports fall back without letting new text execute or damage built-ins", async () => {
  const invalid = german(); invalid.translations.extension.settings = '<img src=x onerror="alert(1)">';
  const api = chromeFake({ ui_language: "custom:de", ui_language_packs: {de: invalid} });
  await initializeLanguage(api);
  assert.equal(currentLocale(), "de");
  assert.equal(t("settings"), "Settings");
  assert.equal(currentLanguagePacks().de.translations.extension.settings, undefined);
  assert.equal(currentLanguagePacks().de.translations.extension["item::one"], "$COUNT$ Notiz");
});

test("custom plural rules use matching forms and fall back with English's rule if incomplete", () => {
  const en = { things_one: { message: "$COUNT$ thing", placeholders: { count: {content: "$1"} } }, things_other: { message: "$COUNT$ things", placeholders: {count: {content: "$1"}} } };
  const pack = {locale: "hr", translations: {extension: {"things::one": "$COUNT$ stvar", "things::few": "$COUNT$ stvari", "things::other": "$COUNT$ stvari"}}};
  assert.equal(createTranslator("hr", {en}, pack).plural("things", 21), "21 stvar");
  delete pack.translations.extension["things::few"];
  assert.equal(createTranslator("hr", {en}, pack).plural("things", 21), "21 things");
});

test("a later storage event wins against a slow custom language startup read", async () => {
  const api = chromeFake();
  let release;
  api.storage.local.get = () => new Promise(resolve => { release = resolve; });
  const read = initializeLanguage(api);
  applyStoredLanguageChange("hr", api);
  release({ ui_language: "custom:de", ui_language_packs: {de: german()} });
  await read;
  assert.equal(currentLocale(), "hr");
});
