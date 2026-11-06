import test from "node:test";
import assert from "node:assert/strict";

test("offline capture command sends the loaded article through authenticated import", {timeout: 5000}, async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  const listeners = {};
  const contexts = [];
  const payloads = [];
  let html = "<article><h1>Saved page</h1><p>Already loaded content</p></article>";
  let finished;
  const event = name => ({addListener(callback) {listeners[name] = callback;}});
  globalThis.chrome = {
    i18n: {getUILanguage: () => "en"},
    runtime: {onMessage: event("message")},
    tabs: {
      onRemoved: event("removed"), onUpdated: event("updated"),
      query: async () => [{id: 7, url: "https://example.test/article", title: "Saved page"}],
      sendMessage: async (_id, message) => {
        if (message.type === "GET_PAGE_CONTEXT") {
          contexts.push(message);
          return {ok: true, url: "https://example.test/article", title: "Saved page", html};
        }
        if (message.type === "SHOW_TOAST") finished();
      },
    },
    scripting: {executeScript: async () => []},
    action: {onClicked: event("action"), setTitle: async () => {}, setBadgeBackgroundColor: async () => {}, setBadgeText: async () => {}},
    commands: {onCommand: event("command")},
    storage: {local: {get: async () => ({ui_language: "en"})}, session: {get: async () => ({})}, onChanged: event("storage")},
  };
  globalThis.fetch = async (url, options) => {
    if (url.endsWith("/handshake")) return Response.json({ok: true, protocol: 2, token: "synthetic-token"});
    assert.equal(url, "http://127.0.0.1:8766/incremento/add-content");
    assert.equal(options.headers.get("X-Incremento-Protocol"), "2");
    assert.equal(options.headers.get("X-Incremento-Token"), "synthetic-token");
    payloads.push(JSON.parse(options.body));
    return Response.json({ok: true, kind: "document", title: "Saved page", cardId: 42});
  };
  try {
    await import("../src/background/main.js?offline-document");
    const captured = new Promise(resolve => {finished = resolve;});
    listeners.command("save-offline-document");
    await captured;
    // The command now explicitly saves the complete HTML snapshot.
    assert.deepEqual(contexts.map(context => [context.includeHtml, context.htmlScope, context.preserveStyles]), [[true, "full", true]]);
    assert.equal(payloads[0].kind, "document");
    assert.equal(payloads[0].html, html);
    assert.equal(payloads[0].pageContentScope, "full");
    assert.equal(payloads[0].documentFormat, "html");
    assert.equal(payloads[0].pdfOptions, undefined);
    html = "";
    const rejected = new Promise(resolve => {finished = resolve;});
    listeners.command("save-offline-document");
    await rejected;
    assert.equal(payloads.length, 1, "empty capture must never become a live-page import");
  } finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});
