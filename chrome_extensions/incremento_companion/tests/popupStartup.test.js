import test from "node:test";
import assert from "node:assert/strict";

import { runPopupStartupTasks } from "../src/popup/startup.js";

test("page inspection failure does not prevent bridge metadata loading", async () => {
  const events = [];

  const result = await runPopupStartupTasks({
    loadConnection: async () => {
      events.push("connection");
      return { deckNames: ["Topics"], tagNames: ["stable"] };
    },
    inspectPage: async () => {
      events.push("page");
      throw new Error("current tab cannot be inspected");
    },
  });

  assert.deepEqual(events.sort(), ["connection", "page"]);
  assert.equal(result.connection.status, "fulfilled");
  assert.deepEqual(result.connection.value.tagNames, ["stable"]);
  assert.equal(result.page.status, "rejected");
  assert.match(result.page.reason.message, /cannot be inspected/);
});
