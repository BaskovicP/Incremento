import test from "node:test";
import assert from "node:assert/strict";

let scenario = 0;
async function withBackground(callback) {
  const originalChrome = globalThis.chrome;
  const listeners = {};
  const event = name => ({addListener(listener) {listeners[name] = listener;}});
  let messageSent;
  const firstMessage = new Promise(resolve => {messageSent = resolve;});
  const state = {activeId: 7, messages: [], injections: [], titles: [], openedTabs: [],
    createTab: async () => {},
    sendMessage: async () => ({ok: true}),
    shortcuts: [{name: "browser-capture-snapshot", shortcut: "Alt+Shift+X"}],
    capture: async () => {throw new Error("Either the '<all_urls>' or 'activeTab' permission is required.");}};
  globalThis.chrome = {
    i18n: {getUILanguage: () => "en"},
    runtime: {onMessage: event("message")},
    tabs: {onRemoved: event("removed"), onUpdated: event("updated"),
      query: async options => options.active
        ? [{id: state.activeId, windowId: 3, url: "https://example.com/article"}] : [],
      captureVisibleTab: (...args) => state.capture(...args),
      sendMessage: (tabId, message, options, callback) => {
        state.messages.push({tabId, message, options});
        messageSent();
        const response = state.sendMessage(tabId, message, options);
        if (callback) {
          void response.then(result => callback(result), error => {
            globalThis.chrome.runtime.lastError = {message: error.message};
            callback();
            globalThis.chrome.runtime.lastError = null;
          });
        }
        return response;
      },
      create: async options => {state.openedTabs.push(options); return state.createTab(options);}},
    scripting: {executeScript: async options => {state.injections.push(options);}},
    action: {onClicked: event("action"), setTitle: async options => {state.titles.push(options);}},
    commands: {onCommand: event("command"), getAll: async () => state.shortcuts},
    storage: {local: {get: async () => ({ui_language: "en"})},
      session: {get: async () => ({})}, onChanged: event("storage")},
  };
  try {
    await import(`../src/background/main.js?snapshot-regression-${++scenario}`);
    const request = (message, sender = {tab: {id: 7, windowId: 3}}) => new Promise(resolve => {
      assert.equal(listeners.message(message, sender, resolve), true);
    });
    await callback({state, request, listeners, firstMessage});
  } finally {
    globalThis.chrome = originalChrome;
  }
}

test("snapshot permission failures explain the toolbar/registered-shortcut recovery path", async () => {
  await withBackground(async ({request}) => {
    const response = await request({type: "CAPTURE_VISIBLE_TAB"});
    assert.equal(response.ok, false);
    assert.equal(response.errorCode, "snapshot_permission_required");
    assert.match(response.error, /toolbar icon/);
    assert.match(response.error, /Snapshot capture/);
    assert.match(response.error, /In Chrome/);
    assert.match(response.error, /Global/);
    assert.ok(!response.error.includes("<all_urls>"));
  });
});

test("a global snapshot command explains In Chrome scope before opening an unauthorized overlay", {timeout: 2000}, async () => {
  await withBackground(async ({listeners, state, firstMessage}) => {
    listeners.command("browser-capture-snapshot");
    await firstMessage;
    assert.equal(state.messages.length, 1);
    assert.equal(state.messages[0].tabId, 7);
    assert.equal(state.messages[0].message.type, "SHOW_TOAST");
    assert.match(state.messages[0].message.text, /Global/);
    assert.match(state.messages[0].message.text, /In Chrome/);
    assert.equal(state.messages[0].message.action, "open_shortcut_settings");
    assert.deepEqual(state.openedTabs, [], "showing a warning must not open settings without a click");
    assert.equal(state.injections.length, 0);
    assert.ok(state.titles.some(item => item.tabId === 7 && /In Chrome/.test(item.title)));
  });
});

test("the warning action opens only Chrome shortcut settings in a new tab", {timeout: 2000}, async () => {
  await withBackground(async ({request, state}) => {
    const response = await request({type: "OPEN_SHORTCUT_SETTINGS", url: "https://untrusted.example"});
    assert.deepEqual(response, {ok: true});
    assert.deepEqual(state.openedTabs, [{url: "chrome://extensions/shortcuts"}]);
  });
});

test("opening shortcut settings reports failure so the warning can remain available for retry", {timeout: 2000}, async () => {
  await withBackground(async ({request, state}) => {
    state.createTab = async () => {throw new Error("browser-internal detail");};
    const response = await request({type: "OPEN_SHORTCUT_SETTINGS"});
    assert.deepEqual(response, {ok: false, error: "Failed to open Chrome shortcut settings."});
    assert.equal(state.openedTabs.length, 1);
  });
});

test("a local snapshot command starts capture on the tab Chrome authorized", {timeout: 2000}, async () => {
  await withBackground(async ({listeners, state, firstMessage}) => {
    listeners.command("browser-capture-snapshot", {id: 9, windowId: 4, url: "https://example.com/article"});
    await firstMessage;
    assert.deepEqual(state.messages, [{tabId: 9,
      message: {type: "TRIGGER_BROWSER_CAPTURE", mode: "snapshot"}, options: {frameId: 0}}]);
    assert.deepEqual(state.injections, [{target: {tabId: 9, allFrames: true}, files: ["content-loader.js"]}]);
  });
});

test("the text shortcut recovers listener startup on Chrome's authorized tab without querying another tab", {timeout: 2000}, async context => {
  context.mock.method(globalThis, "setTimeout", callback => {queueMicrotask(callback); return 1;});
  await withBackground(async ({listeners, state}) => {
    let finish;
    const completed = new Promise(resolve => {finish = resolve;});
    let attempts = 0;
    state.sendMessage = async (_tabId, message) => {
      assert.equal(message.type, "TRIGGER_BROWSER_CAPTURE");
      if (++attempts < 3) throw new Error("Could not establish connection. Receiving end does not exist.");
      finish();
      return {ok: true};
    };
    listeners.command("browser-capture-selection", {id: 9, url: "https://example.test/article"});
    await completed;
    assert.equal(attempts, 3);
    assert.ok(state.messages.every(item => item.tabId === 9 && item.options?.frameId === 0));
    assert.deepEqual(state.injections, [{target: {tabId: 9, allFrames: true}, files: ["content-loader.js"]}]);
  });
});

test("a text shortcut failure displays the capture error instead of silently doing nothing", {timeout: 2000}, async () => {
  await withBackground(async ({listeners, state}) => {
    let finish;
    const completed = new Promise(resolve => {finish = resolve;});
    state.sendMessage = async (_tabId, message) => {
      if (message.type === "SHOW_TOAST") {finish(message.text); return {ok: true};}
      return {ok: false, error: "Open Anki before capturing text."};
    };
    listeners.command("browser-capture-selection", {id: 9, url: "https://example.test/article"});
    assert.equal(await completed, "Open Anki before capturing text.");
  });
});

test("the old page shortcut displays the user's actual registered snapshot shortcut", async () => {
  await withBackground(async ({request, state}) => {
    state.shortcuts = [{name: "browser-capture-snapshot", shortcut: "Command+Shift+K"}];
    const response = await request({type: "SNAPSHOT_SHORTCUT_HELP"});
    assert.equal(response.ok, true);
    assert.ok(response.message.includes("Command+Shift+K"));
    state.shortcuts = [];
    const unassigned = await request({type: "SNAPSHOT_SHORTCUT_HELP"});
    assert.match(unassigned.message, /Keyboard shortcuts/);
  });
});

test("an authorized region capture still returns the image through the background handler", async () => {
  await withBackground(async ({request, state}) => {
    state.capture = async windowId => {assert.equal(windowId, 3); return "data:image/png;base64,YQ==";};
    assert.deepEqual(await request({type: "CAPTURE_VISIBLE_TAB"}), {ok: true, dataUrl: "data:image/png;base64,YQ=="});
  });
});
