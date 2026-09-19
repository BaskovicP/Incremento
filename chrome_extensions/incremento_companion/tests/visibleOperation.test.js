import test from "node:test";
import assert from "node:assert/strict";

import { runVisibleOperation } from "../src/popup/visibleOperation.js";

test("visible operation reports its first stage before awaiting work", async () => {
  const events = [];
  let releaseWork;
  const workGate = new Promise((resolve) => {
    releaseWork = resolve;
  });

  const operation = runVisibleOperation({
    initialStatus: { text: "Reading page", detail: "Checking the active tab", kind: "" },
    onStatus: (status) => events.push(status),
    run: async (report) => {
      events.push("work-started");
      await workGate;
      report({ text: "Sending", detail: "Waiting for Anki", kind: "" });
      return 42;
    },
    failureStatus: () => ({ text: "Failed", kind: "error" }),
  });

  assert.deepEqual(events, [
    { text: "Reading page", detail: "Checking the active tab", kind: "" },
    "work-started",
  ]);

  releaseWork();
  assert.deepEqual(await operation, { ok: true, value: 42 });
  assert.deepEqual(events.at(-1), { text: "Sending", detail: "Waiting for Anki", kind: "" });
});

test("visible operation turns an early inspection exception into a reported failure", async () => {
  const events = [];
  const failure = new Error("tab capture failed");

  const result = await runVisibleOperation({
    initialStatus: { text: "Reading page", detail: "Checking the active tab", kind: "" },
    onStatus: (status) => events.push(status),
    run: async () => {
      throw failure;
    },
    failureStatus: (error, lastStatus) => ({
      text: error.message,
      detail: `Stopped during: ${lastStatus.text}`,
      kind: "error",
    }),
  });

  assert.deepEqual(result, { ok: false, error: failure });
  assert.deepEqual(events, [
    { text: "Reading page", detail: "Checking the active tab", kind: "" },
    {
      text: "tab capture failed",
      detail: "Stopped during: Reading page",
      kind: "error",
    },
  ]);
});
