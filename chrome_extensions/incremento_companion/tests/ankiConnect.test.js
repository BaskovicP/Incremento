import test from "node:test";
import assert from "node:assert/strict";

import { createAnkiConnectClient } from "../src/shared/ankiConnect.js";

test("AnkiConnect calls from multiple tabs are serialized", async () => {
  const actions = [];
  let releaseFirst;
  const firstResponse = new Promise((resolve) => {
    releaseFirst = resolve;
  });
  const client = createAnkiConnectClient({
    fetchImpl: async (_url, options) => {
      const action = JSON.parse(options.body).action;
      actions.push(action);
      if (action === "findNotes") {
        await firstResponse;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ result: action, error: null }),
      };
    },
  });

  const first = client.call("findNotes", { query: "cid:1" });
  const second = client.call("notesInfo", { notes: [1] });
  await Promise.resolve();
  await Promise.resolve();

  assert.deepEqual(actions, ["findNotes"]);
  releaseFirst();
  assert.deepEqual(await Promise.all([first, second]), ["findNotes", "notesInfo"]);
  assert.deepEqual(actions, ["findNotes", "notesInfo"]);
});

test("a failed AnkiConnect call does not block the queue", async () => {
  const client = createAnkiConnectClient({
    fetchImpl: async (_url, options) => {
      const action = JSON.parse(options.body).action;
      return {
        ok: true,
        status: 200,
        json: async () => action === "findNotes"
          ? { result: null, error: "temporary failure" }
          : { result: [1], error: null },
      };
    },
  });

  const failed = client.call("findNotes");
  const next = client.call("notesInfo");

  await assert.rejects(failed, /temporary failure/);
  assert.deepEqual(await next, [1]);
});

test("a timed-out AnkiConnect call releases the next queued update", async () => {
  let requestCount = 0;
  const client = createAnkiConnectClient({
    timeoutMs: 5,
    fetchImpl: async (_url, options) => {
      requestCount += 1;
      if (requestCount === 1) {
        return new Promise((_resolve, reject) => {
          options.signal.addEventListener("abort", () => reject(new Error("aborted")));
        });
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ result: "saved", error: null }),
      };
    },
  });

  const timedOut = client.call("findNotes");
  const next = client.call("updateNoteFields");

  await assert.rejects(timedOut, /timed out/);
  assert.equal(await next, "saved");
  assert.equal(requestCount, 2);
});
