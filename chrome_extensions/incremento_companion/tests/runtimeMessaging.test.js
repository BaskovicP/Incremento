import test from "node:test";
import assert from "node:assert/strict";
import { requestExtensionRuntime } from "../src/shared/runtimeMessaging.js";

const missingReceiver = "Could not establish connection. Receiving end does not exist.";

for (const message of [
  {type: "SUBMIT_BROWSER_CAPTURE", payload: {operation: "create"}},
  {type: "SUBMIT_BROWSER_CAPTURE", payload: {operation: "preview"}},
  {type: "CAPTURE_VISIBLE_TAB"},
  {type: "OPEN_SHORTCUT_SETTINGS"},
]) {
  test(`${message.type} ${message.payload?.operation || ""} is never replayed after a connection failure`, async () => {
    let attempts = 0;
    const runtime = {lastError: {message: missingReceiver},
      sendMessage(request, callback) {attempts += 1; assert.equal(request, message); callback();}};
    await assert.rejects(requestExtensionRuntime(message, runtime), /Reload the extension/);
    assert.equal(attempts, 1);
  });
}

test("an invalidated page context is not retried and explains how to reconnect", async () => {
  let attempts = 0;
  const runtime = {sendMessage() {attempts += 1; throw new Error("Extension context invalidated.");}};
  await assert.rejects(requestExtensionRuntime({type: "LOAD_BROWSER_CAPTURE_META"}, runtime), /Reload the extension.*reload this page/);
  assert.equal(attempts, 1);
});

test("a missing runtime explains how to reconnect without sending anything", async () => {
  await assert.rejects(requestExtensionRuntime({type: "LOAD_BROWSER_CAPTURE_META"}, null), /Reload the extension/);
});

test("ambiguous channel closure is preserved without replaying even a metadata read", async () => {
  let attempts = 0;
  const runtime = {lastError: {message: "The message port closed before a response was received."},
    sendMessage(_request, callback) {attempts += 1; callback();}};
  await assert.rejects(requestExtensionRuntime({type: "LOAD_BROWSER_CAPTURE_META"}, runtime), /message port closed/);
  assert.equal(attempts, 1);
});

test("application responses are passed through unchanged without connection retries", async () => {
  let attempts = 0;
  const response = {ok: false, error: missingReceiver};
  const runtime = {sendMessage(_request, callback) {attempts += 1; callback(response);}};
  assert.equal(await requestExtensionRuntime({type: "LOAD_BROWSER_CAPTURE_META"}, runtime), response);
  assert.equal(attempts, 1);
});
