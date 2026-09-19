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
          errorCode: "page_html_too_large",
          errorParams: { count: 2_000_000, actual: 2_450_123, scope: "main" },
        });
      },
    },
  };

  try {
    const error = await captureSnapshot(42).then(
      () => null,
      (reason) => reason,
    );
    assert.match(error.message, /Page HTML is too large/);
    assert.equal(error.code, "page_html_too_large");
    assert.deepEqual(error.details, { count: 2_000_000, actual: 2_450_123, scope: "main" });
    assert.equal(executeCalls, 1);
  } finally {
    globalThis.chrome = originalChrome;
  }
});

test("captureSnapshot requests only the HTML scope needed by the current action", async () => {
  const originalChrome = globalThis.chrome;
  const messages = [];
  globalThis.chrome = {
    runtime: { lastError: null },
    scripting: {
      async executeScript() {
        return [];
      },
    },
    tabs: {
      sendMessage(_tabId, message, _options, callback) {
        messages.push(message);
        callback({
          ok: true,
          html: "<main>Useful</main>",
          selectionText: "",
          title: "Example",
          url: "https://example.test",
        });
      },
    },
  };

  try {
    const result = await captureSnapshot(42, { includeHtml: true, htmlScope: "main" });
    assert.equal(result.html, "<main>Useful</main>");
    assert.deepEqual(messages, [{
      type: "GET_PAGE_CONTEXT",
      includeHtml: true,
      htmlScope: "main",
    }]);
  } finally {
    globalThis.chrome = originalChrome;
  }
});
