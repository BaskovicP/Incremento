import test from "node:test";
import assert from "node:assert/strict";

import { captureSnapshot } from "../src/shared/chromeApi.js";

test("captureSnapshot surfaces local page-size errors", async () => {
  const originalChrome = globalThis.chrome;
  let executeCalls = 0;
  globalThis.chrome = {
    runtime: { lastError: null },
    scripting: {
      async executeScript() {
        executeCalls += 1;
        return [{
          result: {
            ok: false,
            error: "Page HTML is too large. Maximum is 2000000 characters.",
          },
        }];
      },
    },
    tabs: {
      sendMessage(_tabId, _message, _options, callback) {
        callback({
          ok: false,
          error: "Page HTML is too large. Maximum is 2000000 characters.",
        });
      },
    },
  };

  try {
    await assert.rejects(
      () => captureSnapshot(42),
      /Page HTML is too large/
    );
    assert.equal(executeCalls, 1);
  } finally {
    globalThis.chrome = originalChrome;
  }
});
