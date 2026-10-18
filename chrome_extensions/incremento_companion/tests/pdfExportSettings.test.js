import test from "node:test";
import assert from "node:assert/strict";
import { DEFAULT_PDF_EXPORT_SETTINGS, PDF_EXPORT_SETTINGS_KEY, loadPdfExportSettings, normalizePdfExportSettings, pdfExportPayload, pdfExportSettingsForCapture } from "../src/shared/pdfExportSettings.js";
import { currentLocale, applyStoredLanguageChange, saveLanguageSettings } from "../src/shared/i18n.js";

test("missing and malformed preferences retain the legacy PDF layout and strict booleans", () => {
  for (const value of [undefined, null, [], "website", {style: "bad", dynamic: "false", includeLinks: 1}]) {
    assert.deepEqual(normalizePdfExportSettings(value), {style: "print", dynamic: false, includeLinks: false});
  }
  assert.deepEqual(DEFAULT_PDF_EXPORT_SETTINGS, {style: "print", dynamic: false, includeLinks: false});
});

test("popup and shortcut payloads use the same saved layout and export flags", async () => {
  for (const style of ["print", "website", "article"]) {
    const saved = {style, dynamic: true, includeLinks: true, token: "never-forward-this"};
    const settings = await loadPdfExportSettings({storage: {local: {get: async key => {
      assert.equal(key, PDF_EXPORT_SETTINGS_KEY);
      return {[key]: saved};
    }}}});
    assert.deepEqual(pdfExportPayload(settings), {pdfOptions: {style, dynamic: true, includeLinks: true}});
    assert.equal(saved.token, "never-forward-this");
  }
});

test("opened-page capture retains layout and links without reloading or changing saved preferences", () => {
  for (const style of ["print", "website", "article"]) {
    const saved = {style, dynamic: true, includeLinks: true};
    assert.deepEqual(pdfExportSettingsForCapture(saved, {openedPage: true}), {style, dynamic: false, includeLinks: true});
    assert.deepEqual(pdfExportPayload(saved, {openedPage: true}), {
      pdfOptions: {style, dynamic: false, includeLinks: true}, captureOpenedPage: true,
    });
    assert.deepEqual(pdfExportSettingsForCapture(saved), saved);
    assert.deepEqual(saved, {style, dynamic: true, includeLinks: true});
  }
});

test("one Settings save commits language and PDF preferences together, while failure keeps the language", async () => {
  const writes = [];
  const api = {storage: {local: {get: async () => ({}), set: async value => writes.push(value)}}, i18n: {getUILanguage: () => "en"}};
  applyStoredLanguageChange("en", api);
  const extra = {[PDF_EXPORT_SETTINGS_KEY]: {style: "article", dynamic: false, includeLinks: true}};
  await saveLanguageSettings("hr", {}, api, extra);
  assert.equal(writes.length, 1);
  assert.deepEqual(writes[0], {...extra, ui_language: "hr", ui_language_packs: {}});
  api.storage.local.set = async () => { throw new Error("quota"); };
  await assert.rejects(saveLanguageSettings("zh-Hans", {}, api, extra), /quota/);
  assert.equal(currentLocale(), "hr");
  applyStoredLanguageChange("en", api);
});
