import test from "node:test";
import assert from "node:assert/strict";
import { setImmediate } from "node:timers";

import { applyStoredLanguageChange } from "../src/shared/i18n.js";

let importIndex = 0;

async function coldWorkerCase(savedLanguage, { rejectRead = false, savedPacks = {} } = {}) {
  let resolveLanguage;
  let rejectLanguage;
  const languageRead = new Promise((resolve, reject) => {
    resolveLanguage = resolve;
    rejectLanguage = reject;
  });
  const messages = [];
  const listeners = {};
  const event = (name) => ({ addListener(callback) { listeners[name] = callback; } });
  const chromeApi = {
    i18n: { getUILanguage: () => "en-US" },
    runtime: { onMessage: event("message") },
    tabs: {
      onRemoved: event("removed"),
      onUpdated: event("updated"),
      query: async () => [{ id: 7, url: "https://example.test" }],
      sendMessage: async (_id, message) => { messages.push(message); },
    },
    action: {
      onClicked: event("action"),
      setTitle: async () => {},
      setBadgeBackgroundColor: async () => {},
      setBadgeText: async () => {},
    },
    commands: { onCommand: event("command") },
    storage: {
      local: { get: (key) => (key === "ui_language" || (Array.isArray(key) && key.includes("ui_language"))) ? languageRead : Promise.resolve({}) },
      onChanged: event("storage"),
    },
  };
  globalThis.chrome = chromeApi;
  applyStoredLanguageChange("en", chromeApi);
  await import(`../src/background/main.js?cold-language-${++importIndex}`);
  assert.equal(typeof listeners.command, "function", "listeners register before storage resolves");
  assert.equal(typeof listeners.action, "function");
  assert.equal(typeof listeners.message, "function");
  listeners.command("copy-last-video-time");
  let captureResponse;
  listeners.message({ type: "SUBMIT_BROWSER_CAPTURE", payload: {} }, {}, (response) => {
    captureResponse = response;
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(messages, [], "feedback waits for the saved language");
  assert.equal(captureResponse, undefined);
  if (rejectRead) rejectLanguage(new Error("storage unavailable"));
  else resolveLanguage({ ui_language: savedLanguage, ui_language_packs: savedPacks });
  await new Promise((resolve) => setImmediate(resolve));
  return { messages, captureResponse };
}

test("cold worker command feedback waits for saved Croatian and Chinese", async () => {
  const originalChrome = globalThis.chrome;
  try {
    const hr = await coldWorkerCase("hr");
    assert.equal(hr.messages[0].text, "Još nema spremljenog vremena videozapisa.");
    assert.equal(hr.captureResponse.error, "Odaberite vrstu bilješke i špil.");
    const zh = await coldWorkerCase("zh-Hans");
    assert.equal(zh.messages[0].text, "尚无已保存的视频时间。");
    assert.equal(zh.captureResponse.error, "请选择笔记类型和牌组。");
  } finally {
    globalThis.chrome = originalChrome;
  }
});

test("cold worker command uses English fallback after a storage read error", async () => {
  const originalChrome = globalThis.chrome;
  try {
    const fallback = await coldWorkerCase(null, { rejectRead: true });
    assert.equal(fallback.messages[0].text, "No stored video time yet.");
    assert.equal(fallback.captureResponse.error, "Choose a note type and deck.");
  } finally {
    globalThis.chrome = originalChrome;
  }
});

test("cold worker waits for an imported language before its first command and capture reply", async () => {
  const originalChrome = globalThis.chrome;
  try {
    const pack = {version: 1, locale: "de", name: "Deutsch", translations: {addon: {}, reader: {}, extension: {no_stored_video_time: "Noch keine Videozeit gespeichert.", choose_note_type_deck: "Notiztyp und Stapel auswählen."}}};
    const result = await coldWorkerCase("custom:de", {savedPacks: {de: pack}});
    assert.equal(result.messages[0].text, "Noch keine Videozeit gespeichert.");
    assert.equal(result.captureResponse.error, "Notiztyp und Stapel auswählen.");
  } finally {
    globalThis.chrome = originalChrome;
  }
});
