import test from "node:test";
import assert from "node:assert/strict";
import { captureSnapshotForSender, snapshotPageShortcutFallback } from "../src/shared/snapshotCapture.js";

const sender = {tab: {id: 7, windowId: 3}};

test("snapshot capture stays in the sender window and verifies the active tab", async () => {
  const calls = [];
  const api = {tabs: {
    query: async options => {calls.push(options); return [{id: 7}];},
    captureVisibleTab: async (windowId, options) => {calls.push([windowId, options]); return "data:image/png;base64,YQ==";},
  }};
  assert.equal(await captureSnapshotForSender(api, sender), "data:image/png;base64,YQ==");
  assert.deepEqual(calls, [{active: true, windowId: 3}, [3, {format: "png"}], {active: true, windowId: 3}]);
});

test("missing activeTab grant becomes an actionable permission error without requesting broad access", async () => {
  let requests = 0;
  const api = {tabs: {query: async () => [{id: 7}], captureVisibleTab: async () => {
    throw new Error("Either the '<all_urls>' or 'activeTab' permission is required.");
  }}, permissions: {request() {requests += 1;}}};
  await assert.rejects(captureSnapshotForSender(api, sender), error => error.code === "snapshot_permission_required");
  assert.equal(requests, 0);
});

test("switching tabs before a region capture prevents capturing another page", async () => {
  let captures = 0;
  const api = {tabs: {query: async () => [{id: 8}], captureVisibleTab: async () => {captures += 1;}}};
  await assert.rejects(captureSnapshotForSender(api, sender), error => error.code === "snapshot_tab_changed");
  assert.equal(captures, 0);
});

test("a tab switch during capture discards the screenshot", async () => {
  let queries = 0;
  const api = {tabs: {query: async () => [{id: ++queries === 1 ? 7 : 8}],
    captureVisibleTab: async () => "data:image/png;base64,YQ=="}};
  await assert.rejects(captureSnapshotForSender(api, sender), error => error.code === "snapshot_tab_changed");
});

test("a sender without a window never falls back to the user's focused window", async () => {
  let captures = 0;
  const api = {tabs: {captureVisibleTab: async () => {captures += 1;}}};
  await assert.rejects(captureSnapshotForSender(api, {tab: {id: 7}}), error => error.code === "snapshot_tab_changed");
  assert.equal(captures, 0);
});

test("unrelated capture errors retain their original reason", async () => {
  const api = {tabs: {query: async () => [{id: 7}], captureVisibleTab: async () => {
    throw new Error("MAX_CAPTURE_VISIBLE_TAB_CALLS_PER_SECOND exceeded");
  }}};
  await assert.rejects(captureSnapshotForSender(api, sender), /MAX_CAPTURE_VISIBLE_TAB/);
});

test("page-only snapshot shortcut directs users to a real Chrome command instead of starting unauthorized capture", async () => {
  const messages = [], hints = [];
  await snapshotPageShortcutFallback(async message => {
    messages.push(message);
    return {ok: true, message: "Use the registered Snapshot capture shortcut: Option+Shift+X."};
  }, (text, options) => hints.push({text, options}));
  assert.deepEqual(messages, [{type: "SNAPSHOT_SHORTCUT_HELP"}]);
  assert.deepEqual(hints, [{text: "Use the registered Snapshot capture shortcut: Option+Shift+X.",
    options: {action: "open_shortcut_settings"}}]);
});
