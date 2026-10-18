import test from "node:test";
import assert from "node:assert/strict";
import { resetBridgeAuthorizationForTests } from "../src/shared/bridgeAuth.js";

test("capture metadata restores the sender website's tags without sending its private page URL", {timeout: 5000}, async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  const listeners = {};
  const websiteReads = [];
  const event = name => ({addListener(callback) {listeners[name] = callback;}});
  const meta = {ok: true, deckNames: ["Topics"], tagNames: ["data", "blockchain"],
    noteTypes: [{name: "Basic", fields: ["Front", "Back"]}]};
  globalThis.chrome = {
    i18n: {getUILanguage: () => "en"},
    runtime: {onMessage: event("message")},
    tabs: {onRemoved: event("removed"), onUpdated: event("updated")},
    action: {onClicked: event("action")}, commands: {onCommand: event("command")},
    storage: {local: {get: async () => ({ui_language: "en"})},
      session: {get: async () => ({})}, onChanged: event("storage")},
  };
  globalThis.fetch = async (url, options) => {
    if (url.endsWith("/handshake")) return Response.json({ok: true, protocol: 2, token: "capture-token"});
    assert.equal(options.method, "POST");
    assert.equal(options.headers.get("X-Incremento-Token"), "capture-token");
    if (url.endsWith("/browser-capture-meta")) return Response.json(meta);
    assert.equal(url, "http://127.0.0.1:8766/incremento/website-tags");
    websiteReads.push(JSON.parse(options.body));
    return Response.json({ok: true, site: "updraft.cyfrin.io", enabled: true, tags: ["blockchain"], profileToken: "a"});
  };
  resetBridgeAuthorizationForTests();
  try {
    await import("../src/background/main.js?capture-website-tags");
    const response = await new Promise(resolve => {
      listeners.message({type: "LOAD_BROWSER_CAPTURE_META", url: "https://untrusted.example"},
        {url: "https://updraft.cyfrin.io/courses/lesson?private=value#selection", tab: {id: 7, url: "https://other.example"}}, resolve);
    });
    assert.deepEqual(response.websiteTags, {site: "updraft.cyfrin.io", enabled: true, tags: ["blockchain"]});
    assert.deepEqual(websiteReads, [{action: "load", url: "https://updraft.cyfrin.io"}]);
  } finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
    resetBridgeAuthorizationForTests();
  }
});
