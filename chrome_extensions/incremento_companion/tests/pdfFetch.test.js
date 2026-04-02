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
