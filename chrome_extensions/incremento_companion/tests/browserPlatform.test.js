import test from "node:test";
import assert from "node:assert/strict";
import {createExtensionApi, isFirefox} from "../src/shared/extensionApi.js";
import {openExtensionShortcutsPage} from "../src/shared/chromeApi.js";

test("Firefox uses promise APIs while retaining Chrome callback error semantics", async () => {
  const chromeRuntime = {lastError: null, sendMessage(_message, callback) {
    this.lastError = {message: "Disconnected"}; callback(); this.lastError = null;
  }};
  const chrome = {runtime: chromeRuntime, storage: {session: {get: () => undefined}}};
  const browser = {runtime: {getBrowserInfo: async () => ({name: "Firefox"}),
    sendMessage: async message => ({ok: message.type})},
    storage: {session: {get: async () => ({tracked: 42})}}};
  const api = createExtensionApi(() => chrome, () => browser);
  assert.equal(isFirefox(api), true);
  assert.deepEqual(await api.runtime.sendMessage({type: "test"}), {ok: "test"});
  assert.deepEqual(await api.storage.session.get("tracked"), {tracked: 42});
  let failure;
  api.runtime.sendMessage({}, () => {failure = api.runtime.lastError.message;});
  assert.equal(failure, "Disconnected");
  assert.equal(api.runtime.lastError, null);
});

test("Chrome keeps its existing API path even when it exposes the browser namespace", async () => {
  const calls = [];
  const chrome = {runtime: {sendMessage: async message => {calls.push(message); return "chrome";}}};
  const browser = {runtime: {sendMessage: () => {throw new Error("must keep Chrome path");}}};
  const api = createExtensionApi(() => chrome, () => browser);
  assert.equal(isFirefox(api), false);
  assert.equal(await api.runtime.sendMessage({type: "test"}), "chrome");
  assert.deepEqual(calls, [{type: "test"}]);
});

test("event listeners remain ordinary callbacks and can be removed", () => {
  const listeners = new Set();
  const event = {addListener(fn) {listeners.add(fn);}, removeListener(fn) {listeners.delete(fn);}};
  const chrome = {runtime: {onMessage: event}};
  const browser = {runtime: {getBrowserInfo: () => {}, onMessage: {addListener() {throw new Error("wrong event");}}}};
  const api = createExtensionApi(() => chrome, () => browser);
  const listener = () => true;
  api.runtime.onMessage.addListener(listener);
  assert.ok(listeners.has(listener));
  api.runtime.onMessage.removeListener(listener);
  assert.equal(listeners.size, 0);
});

test("Firefox shortcut help opens a bundled instruction page without navigating the current tab", async () => {
  const original = globalThis.chrome;
  const opened = [];
  globalThis.chrome = {runtime: {getBrowserInfo() {}, getURL: path => `moz-extension://example/${path}`},
    tabs: {create: async options => opened.push(options)}};
  try {
    await openExtensionShortcutsPage();
    assert.deepEqual(opened, [{url: "moz-extension://example/firefox-help.html"}]);
  } finally {globalThis.chrome = original;}
});

test("Firefox content scripts use promises even without getBrowserInfo", async () => {
  const legacy = {runtime: {getURL: path => `moz-extension://uuid/${path}`,
    sendMessage: () => undefined}};
  const browser = {runtime: {getURL: legacy.runtime.getURL, sendMessage: async () => ({ok: true})}};
  const api = createExtensionApi(() => legacy, () => browser);
  assert.equal(isFirefox(api), true);
  assert.deepEqual(await api.runtime.sendMessage({type: "capture"}), {ok: true});
});

test("Firefox snapshot instructions use Firefox settings and preserve shortcut substitution", async () => {
  const {t} = await import("../src/shared/i18n.js");
  const previous = globalThis.chrome;
  globalThis.chrome = {runtime: {getURL: path => `moz-extension://uuid/${path}`}};
  try {
    const hint = t("snapshot_registered_shortcut", {shortcut: "Alt+Shift+X"});
    assert.match(hint, /Firefox/);
    assert.match(hint, /Alt\+Shift\+X/);
    assert.doesNotMatch(hint, /In Chrome/);
  } finally { globalThis.chrome = previous; }
});
