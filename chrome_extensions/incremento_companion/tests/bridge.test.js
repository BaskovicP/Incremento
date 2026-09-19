import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";

import {
  formatBridgeError,
  importIntoIncremento,
  loadBrowserCaptureMeta,
  loadBrowserMediaRef,
  saveBrowserMediaRef,
  submitBrowserCapture,
} from "../src/shared/bridge.js";
import { resetBridgeAuthorizationForTests } from "../src/shared/bridgeAuth.js";
import { applyStoredLanguageChange } from "../src/shared/i18n.js";

beforeEach(() => resetBridgeAuthorizationForTests());

function withHandshake(handler) {
  return async (url, options) => {
    if (String(url).endsWith("/incremento/handshake")) {
      assert.equal(options?.method, "POST");
      return {
        ok: true,
        status: 200,
        json: async () => ({ ok: true, protocol: 2, token: "test-token" }),
      };
    }
    return handler(url, options);
  };
}

test("importIntoIncremento posts JSON payload and returns successful response", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;

  globalThis.fetch = withHandshake(async (url, options) => {
    calls.push({ url, options });
    return {
      ok: true,
      status: 200,
      json: async () => ({ ok: true, kind: "pdf", title: "Example" }),
    };
  });

  try {
    const payload = {
      kind: "pdf",
      title: "Example",
      url: "https://example.com/file.pdf",
      deckName: "Research::Bookmarks",
    };
    const result = await importIntoIncremento(payload);

    assert.deepEqual(result, { ok: true, kind: "pdf", title: "Example" });
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "http://127.0.0.1:8766/incremento/add-content");
    assert.equal(calls[0].options.method, "POST");
    assert.equal(calls[0].options.headers.get("Content-Type"), "application/json");
    assert.equal(calls[0].options.headers.get("X-Incremento-Token"), "test-token");
    assert.deepEqual(JSON.parse(calls[0].options.body), payload);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("importIntoIncremento throws bridge errors from the response body", async () => {
  const originalFetch = globalThis.fetch;

  globalThis.fetch = withHandshake(async () => ({
    ok: false,
    status: 500,
    json: async () => ({ ok: false, error: "Bridge failure" }),
  }));

  try {
    await assert.rejects(
      () => importIntoIncremento({ kind: "webpage" }),
      /Bridge failure/
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("bridge refreshes authorization once after the backend restarts", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  let handshakeCount = 0;
  let dataRequestCount = 0;

  globalThis.fetch = async (url, options) => {
    calls.push({ url: String(url), options });
    if (String(url).endsWith("/incremento/handshake")) {
      handshakeCount += 1;
      return {
        ok: true,
        status: 200,
        json: async () => ({ ok: true, protocol: 2, token: `token-${handshakeCount}` }),
      };
    }
    dataRequestCount += 1;
    if (dataRequestCount === 2) {
      return {
        ok: false,
        status: 401,
        json: async () => ({ ok: false, error: "Bridge authorization required." }),
      };
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ ok: true, kind: "webpage", title: "Example" }),
    };
  };

  try {
    await importIntoIncremento({ kind: "webpage" });
    await importIntoIncremento({ kind: "webpage" });

    assert.equal(handshakeCount, 2);
    assert.equal(dataRequestCount, 3);
    const dataCalls = calls.filter(({ url }) => !url.endsWith("/incremento/handshake"));
    assert.equal(dataCalls[0].options.headers.get("X-Incremento-Token"), "token-1");
    assert.equal(dataCalls[1].options.headers.get("X-Incremento-Token"), "token-1");
    assert.equal(dataCalls[2].options.headers.get("X-Incremento-Token"), "token-2");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("concurrent stale requests share one authorization refresh", async () => {
  const originalFetch = globalThis.fetch;
  let handshakeCount = 0;
  let staleRequestCount = 0;
  let releaseStaleRequests;
  const bothStaleRequestsArrived = new Promise((resolve) => {
    releaseStaleRequests = resolve;
  });

  globalThis.fetch = async (url, options) => {
    if (String(url).endsWith("/incremento/handshake")) {
      handshakeCount += 1;
      return {
        ok: true,
        status: 200,
        json: async () => ({ ok: true, protocol: 2, token: `token-${handshakeCount}` }),
      };
    }

    const token = options.headers.get("X-Incremento-Token");
    if (token === "token-1" && staleRequestCount > 0) {
      staleRequestCount += 1;
      if (staleRequestCount === 3) {
        releaseStaleRequests();
      }
      await bothStaleRequestsArrived;
      return {
        ok: false,
        status: 401,
        json: async () => ({ ok: false, error: "Bridge authorization required." }),
      };
    }

    if (token === "token-1") {
      staleRequestCount = 1;
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ ok: true, kind: "webpage", title: "Example" }),
    };
  };

  try {
    await importIntoIncremento({ kind: "webpage" });
    await Promise.all([
      importIntoIncremento({ kind: "webpage" }),
      importIntoIncremento({ kind: "webpage" }),
    ]);

    assert.equal(handshakeCount, 2);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("metadata loading retries a temporarily busy bridge", async () => {
  const originalFetch = globalThis.fetch;
  let dataRequestCount = 0;

  globalThis.fetch = withHandshake(async () => {
    dataRequestCount += 1;
    if (dataRequestCount === 1) {
      return {
        ok: false,
        status: 503,
        json: async () => ({ ok: false, error: "Bridge is busy.", error_code: "bridge_busy" }),
      };
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ ok: true, deckNames: ["Topics"], tagNames: ["stable"] }),
    };
  });

  try {
    const result = await loadBrowserCaptureMeta();
    assert.deepEqual(result.tagNames, ["stable"]);
    assert.equal(dataRequestCount, 2);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("metadata loading retries a transient connection failure", async () => {
  const originalFetch = globalThis.fetch;
  let dataRequestCount = 0;

  globalThis.fetch = withHandshake(async () => {
    dataRequestCount += 1;
    if (dataRequestCount === 1) {
      throw new TypeError("temporary connection failure");
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ ok: true, deckNames: ["Topics"], tagNames: ["stable"] }),
    };
  });

  try {
    const result = await loadBrowserCaptureMeta();
    assert.deepEqual(result.tagNames, ["stable"]);
    assert.equal(dataRequestCount, 2);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("metadata loading retries a transient handshake failure", async () => {
  const originalFetch = globalThis.fetch;
  let handshakeCount = 0;
  let dataRequestCount = 0;

  globalThis.fetch = async (url) => {
    if (String(url).endsWith("/incremento/handshake")) {
      handshakeCount += 1;
      if (handshakeCount === 1) {
        throw new TypeError("temporary handshake failure");
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ ok: true, protocol: 2, token: "fresh-token" }),
      };
    }
    dataRequestCount += 1;
    return {
      ok: true,
      status: 200,
      json: async () => ({ ok: true, deckNames: ["Topics"], tagNames: ["stable"] }),
    };
  };

  try {
    const result = await loadBrowserCaptureMeta();
    assert.deepEqual(result.tagNames, ["stable"]);
    assert.equal(handshakeCount, 2);
    assert.equal(dataRequestCount, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("an ambiguous POST connection failure is not retried", async () => {
  const originalFetch = globalThis.fetch;
  let dataRequestCount = 0;

  globalThis.fetch = withHandshake(async () => {
    dataRequestCount += 1;
    throw new TypeError("connection dropped after send");
  });

  try {
    await assert.rejects(
      () => submitBrowserCapture({
        url: "https://example.com",
        noteTypeName: "Basic",
        deckName: "Topics",
      }),
      /connection dropped after send/
    );
    assert.equal(dataRequestCount, 1);
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

test("formatBridgeError explains how to recover from an extension-origin conflict", () => {
  assert.equal(
    formatBridgeError(new Error("Origin not allowed."), "Fallback"),
    "This Companion copy is not authorized. Restart Anki, then reopen the popup. If this returns, disable duplicate Companion copies in other Chrome/Brave profiles."
  );
});

test("backend error code localizes independently of its English compatibility message", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = withHandshake(async () => ({
    ok: false,
    status: 403,
    json: async () => ({ ok: false, error_code: "origin_not_allowed", error: "Origin not allowed." }),
  }));
  applyStoredLanguageChange("hr", { i18n: { getUILanguage: () => "en" } });
  try {
    await assert.rejects(async () => {
      try { await importIntoIncremento({ kind: "webpage" }); }
      catch (error) {
        assert.match(formatBridgeError(error, "Fallback"), /ovlašten/);
        throw error;
      }
    }, /Origin not allowed/);
  } finally {
    applyStoredLanguageChange("en", { i18n: { getUILanguage: () => "en" } });
    globalThis.fetch = originalFetch;
  }
});

test("loadBrowserCaptureMeta loads browser capture metadata", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;

  globalThis.fetch = withHandshake(async (url, options) => {
    calls.push({ url, options });
    return {
      ok: true,
      status: 200,
      json: async () => ({ ok: true, noteTypes: [{ name: "Basic", fields: ["Front", "Back"] }], deckNames: ["Default"] }),
    };
  });

  try {
    const result = await loadBrowserCaptureMeta();
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "http://127.0.0.1:8766/incremento/browser-capture-meta");
    assert.equal(calls[0].options.method, "POST");
    assert.equal(calls[0].options.body, undefined);
    assert.equal(result.deckNames[0], "Default");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("submitBrowserCapture posts a browser_capture payload", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;

  globalThis.fetch = withHandshake(async (url, options) => {
    calls.push({ url, options });
    return {
      ok: true,
      status: 200,
      json: async () => ({ ok: true, noteTypeName: "Basic", deckName: "Default" }),
    };
  });

  try {
    await submitBrowserCapture({
      url: "https://example.com",
      noteTypeName: "Basic",
      deckName: "Default",
    });
    assert.equal(calls.length, 1);
    assert.equal(JSON.parse(calls[0].options.body).type, "browser_capture");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("loadBrowserMediaRef loads the saved browser media record for a card", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;

  globalThis.fetch = withHandshake(async (url, options) => {
    calls.push({ url, options });
    return {
      ok: true,
      status: 200,
      json: async () => ({ ok: true, cardId: 42, hasReference: true, timeText: "12:34" }),
    };
  });

  try {
    const result = await loadBrowserMediaRef(42);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "http://127.0.0.1:8766/incremento/browser-media-ref?cardId=42");
    assert.equal(calls[0].options.method, "POST");
    assert.equal(calls[0].options.body, undefined);
    assert.equal(result.timeText, "12:34");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("saveBrowserMediaRef posts a browser media payload", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;

  globalThis.fetch = withHandshake(async (url, options) => {
    calls.push({ url, options });
    return {
      ok: true,
      status: 200,
      json: async () => ({ ok: true, cardId: 42, timeText: "12:34" }),
    };
  });

  try {
    const payload = {
      cardId: 42,
      pageUrl: "https://example.com/article",
      mediaUrl: "https://player.example.com/video",
      mediaTitle: "Clip",
      seconds: 754,
    };
    const result = await saveBrowserMediaRef(payload);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "http://127.0.0.1:8766/incremento/browser-media-ref");
    assert.equal(calls[0].options.method, "POST");
    assert.deepEqual(JSON.parse(calls[0].options.body), payload);
    assert.equal(result.cardId, 42);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
