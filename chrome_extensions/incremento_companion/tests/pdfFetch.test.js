import test from "node:test";
import assert from "node:assert/strict";

import {
  fetchPdfPayloadForImport,
  getPdfPayloadForUrl,
  pdfUrlLooksLikePdf,
} from "../src/shared/pdfFetch.js";

class TestFileReader {
  constructor() {
    this.error = null;
    this.onload = null;
    this.onerror = null;
    this.result = "";
  }

  async readAsDataURL(blob) {
    try {
      const buffer = Buffer.from(await blob.arrayBuffer());
      this.result = `data:application/pdf;base64,${buffer.toString("base64")}`;
      this.onload?.();
    } catch (error) {
      this.error = error;
      this.onerror?.();
    }
  }
}

test("pdfUrlLooksLikePdf detects PDF-like URLs", () => {
  assert.equal(pdfUrlLooksLikePdf("https://example.com/file.pdf"), true);
  assert.equal(pdfUrlLooksLikePdf("https://example.com/file.PDF?dl=1"), true);
  assert.equal(pdfUrlLooksLikePdf("https://example.com/file"), false);
});

test("fetchPdfPayloadForImport returns base64 payload and inferred filename", async () => {
  const originalFetch = globalThis.fetch;
  const originalFileReader = globalThis.FileReader;
  const pdfBytes = Buffer.from("%PDF-1.7\nhello", "latin1");

  globalThis.FileReader = TestFileReader;
  globalThis.fetch = async () => new Response(pdfBytes, {
    status: 200,
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": 'attachment; filename="lesson.pdf"',
    },
  });

  try {
    const result = await fetchPdfPayloadForImport("https://example.com/download");

    assert.equal(result.pdfFilename, "lesson.pdf");
    assert.equal(result.pdfBase64, pdfBytes.toString("base64"));
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.FileReader = originalFileReader;
  }
});

test("fetchPdfPayloadForImport rejects captcha responses", async () => {
  const originalFetch = globalThis.fetch;
  const originalFileReader = globalThis.FileReader;

  globalThis.FileReader = TestFileReader;
  globalThis.fetch = async () => new Response("<html>sgcaptcha</html>", {
    status: 200,
    headers: {
      "Content-Type": "text/html",
    },
  });

  try {
    await assert.rejects(
      () => fetchPdfPayloadForImport("https://example.com/file.pdf"),
      /captcha challenge/
    );
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.FileReader = originalFileReader;
  }
});

test("getPdfPayloadForUrl skips non-PDF URLs without fetching", async () => {
  const originalFetch = globalThis.fetch;
  let called = false;

  globalThis.fetch = async () => {
    called = true;
    throw new Error("should not fetch");
  };

  try {
    const result = await getPdfPayloadForUrl("https://example.com/page");
    assert.equal(result, null);
    assert.equal(called, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("fetchPdfPayloadForImport rejects HTML even when headers and URL claim PDF", async () => {
  const originalFetch = globalThis.fetch;
  const originalFileReader = globalThis.FileReader;

  globalThis.FileReader = TestFileReader;
  globalThis.fetch = async () => new Response("<html><body>not a PDF</body></html>", {
    status: 200,
    headers: { "Content-Type": "application/pdf" },
  });

  try {
    await assert.rejects(
      () => fetchPdfPayloadForImport("https://example.com/file.pdf"),
      /did not return a PDF file/
    );
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.FileReader = originalFileReader;
  }
});

test("fetchPdfPayloadForImport rejects oversized Content-Length before reading", async () => {
  const originalFetch = globalThis.fetch;
  let bodyRead = false;

  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    url: "https://example.com/file.pdf",
    headers: new Headers({
      "Content-Type": "application/pdf",
      "Content-Length": "17",
    }),
    body: {
      getReader() {
        bodyRead = true;
        throw new Error("body must not be read");
      },
    },
  });

  try {
    await assert.rejects(
      () => fetchPdfPayloadForImport("https://example.com/file.pdf", { maxBytes: 16 }),
      /maximum size of 16 bytes/
    );
    assert.equal(bodyRead, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("fetchPdfPayloadForImport cancels a stream that exceeds the byte limit", async () => {
  const originalFetch = globalThis.fetch;
  const originalFileReader = globalThis.FileReader;
  let cancelled = false;
  const chunks = [
    new Uint8Array(Buffer.from("%PDF-1.7\n", "latin1")),
    new Uint8Array(Buffer.from("payload-too-large", "latin1")),
  ];
  let chunkIndex = 0;

  globalThis.FileReader = TestFileReader;
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    url: "https://example.com/file.pdf",
    headers: new Headers({ "Content-Type": "application/pdf" }),
    body: {
      getReader() {
        return {
          async read() {
            if (chunkIndex >= chunks.length) {
              return { done: true, value: undefined };
            }
            const value = chunks[chunkIndex];
            chunkIndex += 1;
            return { done: false, value };
          },
          async cancel() {
            cancelled = true;
          },
          releaseLock() {},
        };
      },
    },
  });

  try {
    await assert.rejects(
      () => fetchPdfPayloadForImport("https://example.com/file.pdf", { maxBytes: 12 }),
      /maximum size of 12 bytes/
    );
    assert.equal(cancelled, true);
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.FileReader = originalFileReader;
  }
});

test("fetchPdfPayloadForImport rejects unsafe source URLs before fetching", async () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    throw new Error("fetch must not run");
  };

  try {
    await assert.rejects(
      () => fetchPdfPayloadForImport("ftp://example.com/file.pdf"),
      /HTTP\(S\)/
    );
    await assert.rejects(
      () => fetchPdfPayloadForImport("https://user:secret@example.com/file.pdf"),
      /credentials/
    );
    assert.equal(calls, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("fetchPdfPayloadForImport sanitizes a server-provided filename", async () => {
  const originalFetch = globalThis.fetch;
  const originalFileReader = globalThis.FileReader;
  const pdfBytes = Buffer.from("%PDF-1.7\nhello", "latin1");

  globalThis.FileReader = TestFileReader;
  globalThis.fetch = async () => new Response(pdfBytes, {
    status: 200,
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": 'attachment; filename="../../unsafe\\name.pdf"',
    },
  });

  try {
    const result = await fetchPdfPayloadForImport("https://example.com/file.pdf");
    assert.equal(result.pdfFilename, "unsafe_name.pdf");
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.FileReader = originalFileReader;
  }
});
