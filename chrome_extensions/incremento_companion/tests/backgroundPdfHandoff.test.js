import test from "node:test";
import assert from "node:assert/strict";

test("real background routing completes the Anki handoff through authenticated RPC without a command", {timeout: 5000}, async () => {
  const original = {chrome: globalThis.chrome, fetch: globalThis.fetch};
  const listeners = {}, storage = {}, requests = [];
  const ticket = "d".repeat(64);
  const landing = `http://127.0.0.1:8766/incremento/webpage-pdf#${ticket}`;
  const source = "https://example.test/article";
  let url = landing, opened, watching;
  const wasOpened = new Promise(resolve => {opened = resolve;});
  const wasWatching = new Promise(resolve => {watching = resolve;});
  const event = name => ({addListener(callback) {listeners[name] = callback;}});
  globalThis.chrome = {
    i18n: {getUILanguage: () => "en"},
    runtime: {onMessage: event("message"), getURL: path => `chrome-extension://${"b".repeat(32)}/${path}`},
    commands: {onCommand: event("command")},
    action: {onClicked: event("action"), setTitle: async () => {}, setBadgeText: async () => {}, setBadgeBackgroundColor: async () => {}},
    webNavigation: {onCommitted: event("committed")},
    permissions: {contains: async () => true},
    tabs: {onUpdated: event("updated"), onRemoved: event("removed"),
      get: async id => ({id, url}),
      update: async (_id, change) => {url = change.url; opened();},
      sendMessage: async (_id, message) => message.type === "GET_PAGE_CONTEXT"
        ? {ok: true, url, title: "Verified article", html: "<article>Verified browser content</article>"} : {ok: true},
    },
    scripting: {executeScript: async options => {
      if (options.func?.name === "watchVerifiedPage") {
        // Chrome serializes the function into a separate isolated world.
        const serialized = new Function(`return (${options.func.toString()})`)();
        assert.equal(typeof serialized, "function");
        watching();
      }
      return [];
    }},
    storage: {onChanged: event("storage"), local: {get: async () => ({ui_language: "en"})}, session: {
      get: async key => ({[key]: storage[key]}), set: async values => Object.assign(storage, values), remove: async key => {delete storage[key];},
    }},
  };
  globalThis.fetch = async (endpoint, options) => {
    if (endpoint.endsWith("/handshake")) return Response.json({ok: true, protocol: 2, token: "synthetic-token"});
    assert.equal(endpoint, "http://127.0.0.1:8766/incremento/webpage-pdf-handoff");
    assert.equal(options.headers.get("X-Incremento-Protocol"), "2");
    assert.equal(options.headers.get("X-Incremento-Token"), "synthetic-token");
    const body = JSON.parse(options.body);
    requests.push(body);
    return Response.json(body.action === "describe" ? {ok: true, url: source, remainingSeconds: 600} : {ok: true});
  };
  try {
    await import("../src/background/main.js?automatic-pdf-handoff");
    listeners.updated(7, {url: landing}, {url: landing});
    await wasOpened;
    assert.equal(url, source);
    listeners.updated(7, {status: "complete"}, {url: source});
    await wasWatching;
    const response = await new Promise(resolve => {
      assert.equal(listeners.message({type: "PDF_HANDOFF_READY", ticket}, {tab: {id: 7}, frameId: 0, url: source}, resolve), true);
    });
    assert.deepEqual(response, {ok: true});
    assert.deepEqual(requests.at(-1), {action: "submit", ticket, url: source, html: "<article>Verified browser content</article>"});
  } finally {
    Object.assign(globalThis, original);
  }
});
