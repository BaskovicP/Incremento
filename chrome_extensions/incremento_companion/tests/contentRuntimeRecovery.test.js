import test from "node:test";
import assert from "node:assert/strict";

let scenario = 0;
const missingReceiver = "Could not establish connection. Receiving end does not exist.";

// Exercise the real page listener and its visible error at the Chrome/DOM
// boundaries. No page, Anki profile, or wall-clock timer is involved.
async function withPage(context, respond, callback) {
  const names = ["chrome", "window", "document", "requestAnimationFrame",
    "__incrementoLastSelectedText", "__incrementoLastSelection", "__incrementoSelectionError"];
  const originals = names.map(name => [name, Object.getOwnPropertyDescriptor(globalThis, name)]);
  const elements = [];
  const requests = [];
  let listener;
  globalThis.document = {
    title: "Example",
    addEventListener() {},
    querySelector() { return null; },
    getElementById(id) { return elements.find(element => element.id === id && !element.removed); },
    createElement() {
      return {style: {}, setAttribute() {}, remove() { this.removed = true; }};
    },
    documentElement: {appendChild(element) { elements.push(element); }},
  };
  globalThis.window = {
    location: {href: "https://example.test/article", hostname: "example.test"},
    getSelection: () => ({toString: () => "Selected passage", rangeCount: 0}),
    addEventListener() {}, setTimeout() {}, setInterval() {},
  };
  globalThis.requestAnimationFrame = callback => callback();
  globalThis.chrome = {
    i18n: {getUILanguage: () => "en"},
    storage: {local: {get: async () => ({ui_language: "en"})}, onChanged: {addListener() {}}},
    runtime: {
      onMessage: {addListener(callback) { listener = callback; }},
      sendMessage(message, callback) {
        requests.push(message);
        const response = respond(requests.length, message);
        globalThis.chrome.runtime.lastError = response.error ? {message: response.error} : null;
        callback(response.result);
        globalThis.chrome.runtime.lastError = null;
      },
    },
  };
  context.mock.method(globalThis, "setTimeout", (callback, delay) => {
    if (delay < 1000) queueMicrotask(callback);
    return 1;
  });
  try {
    await import(`../src/content/main.js?runtime-recovery-${++scenario}`);
    const result = await new Promise(resolve => {
      assert.equal(listener({type: "TRIGGER_BROWSER_CAPTURE", mode: "selection"}, {}, resolve), true);
    });
    await callback({result, requests, toast: elements.at(-1)?.textContent});
  } finally {
    for (const [name, descriptor] of originals) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else delete globalThis[name];
    }
  }
}

test("text capture recovers a missing worker listener before displaying the backend's response", async context => {
  await withPage(context, attempt => attempt < 3 ? {error: missingReceiver}
    : {result: {ok: false, error: "Open Anki before capturing text."}}, ({result, requests, toast}) => {
    assert.equal(toast, "Open Anki before capturing text.");
    assert.deepEqual(result, {ok: false, error: toast});
    assert.deepEqual(requests, Array(3).fill({type: "LOAD_BROWSER_CAPTURE_META"}));
  });
});

test("a persistently disconnected capture explains extension and page reload after bounded retries", async context => {
  await withPage(context, () => ({error: missingReceiver}), ({requests, toast}) => {
    assert.match(toast, /reload.*extension.*reload.*page/i);
    assert.ok(!toast.includes("Receiving end"));
    assert.equal(requests.length, 3);
    assert.ok(requests.every(message => message.type === "LOAD_BROWSER_CAPTURE_META"));
  });
});
