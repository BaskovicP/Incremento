import test from "node:test";
import assert from "node:assert/strict";
import { resetBridgeAuthorizationForTests } from "../src/shared/bridgeAuth.js";

test("text capture loads note types through an origin-preserving authenticated metadata POST", {timeout: 5000}, async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  const listeners = {};
  const calls = [];
  const event = name => ({addListener(callback) {listeners[name] = callback;}});
  const meta = {ok: true, deckNames: ["Topics"], tagNames: ["topic"],
    noteTypes: [{name: "Basic", fields: ["Front", "Back"]}]};
  globalThis.chrome = {
    i18n: {getUILanguage: () => "en"},
    runtime: {onMessage: event("message")},
    tabs: {onRemoved: event("removed"), onUpdated: event("updated")},
    action: {onClicked: event("action")},
    commands: {onCommand: event("command")},
    storage: {local: {get: async () => ({ui_language: "en"})},
      session: {get: async () => ({})}, onChanged: event("storage")},
  };
  globalThis.fetch = async (url, options) => {
    if (url.endsWith("/handshake")) {
      assert.equal(options.method, "POST");
      return Response.json({ok: true, protocol: 2, token: "capture-token"});
    }
    assert.equal(url, "http://127.0.0.1:8766/incremento/browser-capture-meta");
    calls.push(options);
    // Chromium can omit Origin on privileged GETs. The bridge correctly rejects
    // that request instead of relaxing its extension-origin authorization.
    if (options.method !== "POST") return Response.json({ok: false,
      error_code: "origin_not_allowed", error: "Origin not allowed."}, {status: 403});
    return Response.json(meta);
  };
  resetBridgeAuthorizationForTests();
  try {
    await import("../src/background/main.js?capture-meta");
    const response = await new Promise(resolve => {
      const asynchronous = listeners.message({type: "LOAD_BROWSER_CAPTURE_META"},
        {tab: {id: 7}}, resolve);
      assert.equal(asynchronous, true);
    });
    assert.deepEqual(response, meta);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].body, undefined);
    assert.equal(calls[0].headers.get("X-Incremento-Token"), "capture-token");
    assert.equal(calls[0].headers.get("X-Incremento-Protocol"), "2");
  } finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
    resetBridgeAuthorizationForTests();
  }
});
