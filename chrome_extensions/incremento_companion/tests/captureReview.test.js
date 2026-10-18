import test from "node:test";
import assert from "node:assert/strict";
import { capturePreviewDocument, captureResultKind } from "../src/shared/captureReview.js";

test("field previews cannot run code or fetch page resources", () => {
  const result = capturePreviewDocument({Front: "<p>A <strong>passage</strong></p>", Back: '<a href="https://example.com">Source</a>'});
  assert.ok(result.includes("default-src 'none'"));
  assert.ok(result.includes("img-src data:"));
  assert.ok(result.includes("<p>A <strong>passage</strong></p>"));
  assert.ok(result.includes("<h3>Front</h3>"));
  assert.ok(capturePreviewDocument({'<script>bad()</script>': "Text"}).includes("&lt;script&gt;bad()&lt;/script&gt;"));
});

test("duplicate and preview replies never look like successful note creation", () => {
  assert.equal(captureResultKind({ok: true, duplicate: true, noteId: 5}), "duplicate");
  assert.equal(captureResultKind({ok: true, preview: true}), "preview");
  assert.equal(captureResultKind({ok: true, duplicate: true, opened: true}), "opened");
  assert.equal(captureResultKind({ok: true, type: "browser_capture", noteId: 5}), "created");
  assert.equal(captureResultKind({ok: true}), "error");
});
