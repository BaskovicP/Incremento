import test from "node:test";
import assert from "node:assert/strict";

import { captureSnapshot, triggerBrowserCaptureForTab } from "../src/shared/chromeApi.js";

async function withCaptureTab(context, respond, callback) {
  const originalChrome = globalThis.chrome;
  const requests = [];
  const injections = [];
  globalThis.chrome = {
    runtime: {lastError: null},
    scripting: {executeScript: async options => { injections.push(options); }},
    tabs: {sendMessage(tabId, message, options, callback) {
      // Accept the old broadcast shape too, so the regression reports the
      // missing recovery rather than a fake-API argument error.
      if (typeof options === "function") { callback = options; options = undefined; }
      requests.push({tabId, message, options});
      const response = respond(requests.length);
      globalThis.chrome.runtime.lastError = response.error ? {message: response.error} : null;
      callback(response.result);
      globalThis.chrome.runtime.lastError = null;
    }},
  };
  context.mock.method(globalThis, "setTimeout", callback => { queueMicrotask(callback); return 1; });
  try { await callback({requests, injections}); }
  finally { globalThis.chrome = originalChrome; }
}

test("capture waits through listener startup and opens exactly once in the main frame", async context => {
  await withCaptureTab(context, attempt => attempt < 3
    ? {error: "Could not establish connection. Receiving end does not exist."}
    : {result: {ok: true}}, async ({requests, injections}) => {
    assert.deepEqual(await triggerBrowserCaptureForTab(42, "selection"), {ok: true});
    assert.equal(requests.length, 3);
    assert.ok(requests.every(request => request.tabId === 42 && request.options?.frameId === 0));
    assert.deepEqual(injections, [{target: {tabId: 42, allFrames: true}, files: ["content-loader.js"]}]);
  });
});

test("capture never replays a delivered action when its reply reports a worker connection error", async context => {
  const error = "Could not establish connection. Receiving end does not exist.";
  await withCaptureTab(context, () => ({result: {ok: false, error}}), async ({requests}) => {
    assert.deepEqual(await triggerBrowserCaptureForTab(42, "selection"), {ok: false, error});
    assert.equal(requests.length, 1);
  });
});

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

test("PDF snapshot preserves styles through both the content-script and direct-read paths", async () => {
  const originalChrome = globalThis.chrome;
  const messages = [];
  const directReads = [];
  globalThis.chrome = {
    runtime: {lastError: null},
    scripting: {async executeScript(request) {
      if (request.func) {
        directReads.push(request.args[2]);
        return [{result: {ok: true, html: "<style>p{color:red}</style><p>Article</p>"}}];
      }
      return [];
    }},
    tabs: {sendMessage(_id, message, _options, callback) {messages.push(message); callback(null);}},
  };
  try {
    const result = await captureSnapshot(42, {includeHtml: true, preserveStyles: true});
    assert.match(result.html, /<style>/);
    assert.deepEqual(messages, [{type: "GET_PAGE_CONTEXT", includeHtml: true, htmlScope: "full", preserveStyles: true}]);
    assert.deepEqual(directReads, [{includeHtml: true, htmlScope: "full", preserveStyles: true}]);
  } finally {
    globalThis.chrome = originalChrome;
  }
});
