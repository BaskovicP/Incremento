import test from "node:test";
import assert from "node:assert/strict";
import { PDF_EXPORT_SETTINGS_KEY } from "../src/shared/pdfExportSettings.js";

test("PDF shortcut reads current saved preferences and passes them through the authenticated bridge", {timeout: 5000}, async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  const listeners = {};
  const contexts = [];
  const payloads = [];
  const toasts = [];
  const saved = {ui_language: "en"};
  let rejectSettingsRead = false;
  let omitHtml = false;
  let pageUrl = "https://example.test/article";
  let imported;
  const event = name => ({addListener(callback) {listeners[name] = callback;}});
  globalThis.chrome = {
    i18n: {getUILanguage: () => "en"},
    runtime: {onMessage: event("message")},
    tabs: {
      onRemoved: event("removed"), onUpdated: event("updated"),
      query: async () => [{id: 7, url: pageUrl, title: "Example"}],
      sendMessage: async (_id, message) => {
        if (message.type === "GET_PAGE_CONTEXT") {
          contexts.push(message);
          return {ok: true, url: pageUrl, title: "Example", html: message.includeHtml && !omitHtml ? "<style>p{color:red}</style><p>Article</p>" : ""};
        }
        if (message.type === "SHOW_TOAST") {toasts.push(message.text); imported();}
      },
    },
    scripting: {executeScript: async () => []},
    action: {onClicked: event("action"), setTitle: async () => {}, setBadgeBackgroundColor: async () => {}, setBadgeText: async () => {}},
    commands: {onCommand: event("command")},
    storage: {local: {get: async key => {
      if (rejectSettingsRead && key === PDF_EXPORT_SETTINGS_KEY) throw new Error("Synthetic storage failure");
      return saved;
    }}, session: {get: async () => ({})}, onChanged: event("storage")},
  };
  globalThis.fetch = async (url, options) => {
    if (url.endsWith("/handshake")) return Response.json({ok: true, protocol: 2, token: "synthetic-token"});
    assert.equal(url, "http://127.0.0.1:8766/incremento/add-content");
    assert.equal(options.headers.get("X-Incremento-Protocol"), "2");
    assert.equal(options.headers.get("X-Incremento-Token"), "synthetic-token");
    payloads.push(JSON.parse(options.body));
    return Response.json({ok: true, kind: "pdf", title: "Example", cardId: 42});
  };
  try {
    await import("../src/background/main.js?pdf-settings");
    for (const style of ["website", "article", "print"]) {
      const preferences = {style, dynamic: style === "article", includeLinks: style !== "print"};
      saved[PDF_EXPORT_SETTINGS_KEY] = preferences;
      const completed = new Promise(resolve => {imported = resolve;});
      listeners.command("add-current-page-as-pdf");
      await completed;
      assert.deepEqual(payloads.at(-1).pdfOptions, preferences);
      assert.equal(payloads.at(-1).captureOpenedPage, undefined);
      assert.equal(contexts.at(-1).includeHtml, !preferences.dynamic);
      assert.equal(contexts.at(-1).preserveStyles, true);
      assert.equal(Boolean(payloads.at(-1).html), !preferences.dynamic);
    }
    assert.equal(payloads.length, 3);
    saved[PDF_EXPORT_SETTINGS_KEY] = {style: "article", dynamic: true, includeLinks: true};
    pageUrl = "https://example.test/article.pdf";
    const captured = new Promise(resolve => {imported = resolve;});
    listeners.command("capture-opened-page-as-pdf");
    await captured;
    assert.deepEqual(payloads.at(-1).pdfOptions, {style: "article", dynamic: false, includeLinks: true});
    assert.equal(payloads.at(-1).captureOpenedPage, true);
    assert.equal(contexts.at(-1).includeHtml, true);
    assert.equal(contexts.at(-1).preserveStyles, true);
    assert.equal(payloads.at(-1).html, "<style>p{color:red}</style><p>Article</p>");
    assert.deepEqual(saved[PDF_EXPORT_SETTINGS_KEY], {style: "article", dynamic: true, includeLinks: true});
    omitHtml = true;
    const unavailable = new Promise(resolve => {imported = resolve;});
    listeners.command("capture-opened-page-as-pdf");
    await unavailable;
    assert.equal(payloads.length, 4, "missing opened-page HTML must not fall back to a fresh URL download");
    rejectSettingsRead = true;
    const failed = new Promise(resolve => {imported = resolve;});
    listeners.command("add-current-page-as-pdf");
    await failed;
    assert.equal(payloads.length, 4, "a failed settings read must not import with different defaults");
    assert.equal(contexts.length, 5);
    assert.equal(toasts.at(-1), "Could not load settings. Try again.");
  } finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});
