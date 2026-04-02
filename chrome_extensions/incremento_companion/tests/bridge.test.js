import test from "node:test";
import assert from "node:assert/strict";

import { formatBridgeError, importIntoIncremento } from "../src/shared/bridge.js";

test("importIntoIncremento posts JSON payload and returns successful response", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;

  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return {
      ok: true,
      status: 200,
      json: async () => ({ ok: true, kind: "pdf", title: "Example" }),
    };
  };

  try {
    const payload = { kind: "pdf", title: "Example", url: "https://example.com/file.pdf" };
    const result = await importIntoIncremento(payload);

    assert.deepEqual(result, { ok: true, kind: "pdf", title: "Example" });
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "http://127.0.0.1:8766/incremento/add-content");
    assert.equal(calls[0].options.method, "POST");
    assert.equal(calls[0].options.headers["Content-Type"], "application/json");
    assert.deepEqual(JSON.parse(calls[0].options.body), payload);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("importIntoIncremento throws bridge errors from the response body", async () => {
  const originalFetch = globalThis.fetch;

  globalThis.fetch = async () => ({
    ok: false,
    status: 500,
    json: async () => ({ ok: false, error: "Bridge failure" }),
  });

  try {
    await assert.rejects(
      () => importIntoIncremento({ kind: "webpage" }),
      /Bridge failure/
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("formatBridgeError maps TypeError to the user-facing bridge message", () => {
  const message = formatBridgeError(new TypeError("network"), "Fallback");
  assert.equal(message, "Failed to reach Incremento in Anki. Keep Anki open and reload the addon.");
});

test("formatBridgeError falls back to error message or fallback text", () => {
  assert.equal(formatBridgeError(new Error("Boom"), "Fallback"), "Boom");
  assert.equal(formatBridgeError(null, "Fallback"), "Fallback");
});
