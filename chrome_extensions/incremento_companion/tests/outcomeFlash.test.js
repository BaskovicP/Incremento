import test from "node:test";
import assert from "node:assert/strict";

import {
  OUTCOME_FLASH_DURATION_MS,
  createOutcomeFlashController,
} from "../src/popup/outcomeFlash.js";

test("outcome flash controller emits a unique success or error flash and then clears it", () => {
  const events = [];
  const timers = [];
  const cleared = [];
  const controller = createOutcomeFlashController({
    onChange: (value) => events.push(value),
    setTimer: (callback, delay) => {
      timers.push({ callback, delay });
      return timers.length;
    },
    clearTimer: (id) => cleared.push(id),
  });

  controller.trigger("success");
  controller.trigger("error");

  assert.deepEqual(events, [
    { kind: "success", revision: 1 },
    { kind: "error", revision: 2 },
  ]);
  assert.deepEqual(cleared, [1]);
  assert.equal(timers[0].delay, OUTCOME_FLASH_DURATION_MS);
  assert.equal(timers[1].delay, OUTCOME_FLASH_DURATION_MS);

  timers[1].callback();
  assert.deepEqual(events.at(-1), { kind: "", revision: 2 });
});

test("outcome flash controller ignores unsupported outcomes and cancels on dispose", () => {
  const events = [];
  const cleared = [];
  const controller = createOutcomeFlashController({
    onChange: (value) => events.push(value),
    setTimer: () => 17,
    clearTimer: (id) => cleared.push(id),
  });

  controller.trigger("pending");
  controller.trigger("success");
  controller.dispose();

  assert.deepEqual(events, [{ kind: "success", revision: 1 }]);
  assert.deepEqual(cleared, [17]);
});
