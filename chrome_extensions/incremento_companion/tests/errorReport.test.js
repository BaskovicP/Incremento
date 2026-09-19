import test from "node:test";
import assert from "node:assert/strict";

import {
  buildErrorReport,
  copyErrorReport,
  normalizeErrorCode,
  safePositiveInteger,
} from "../src/popup/errorReport.js";

test("copyable error report is verbose, line-oriented, and omits unavailable fields", () => {
  const report = buildErrorReport({
    title: "Incremento Companion error",
    fields: [
      ["Action", "Add Page to Markdown"],
      ["Stage", "Step 1 of 3 — Reading the current page"],
      ["Reason", "Page HTML is too large.\nMaximum is 2,000,000 characters."],
      ["Error code", "page_html_too_large"],
      ["Content scope", "main"],
      ["Captured characters", 2_450_123],
      ["Maximum characters", 2_000_000],
      ["Unused", ""],
    ],
  });

  assert.equal(report, [
    "Incremento Companion error",
    "Action: Add Page to Markdown",
    "Stage: Step 1 of 3 — Reading the current page",
    "Reason: Page HTML is too large. Maximum is 2,000,000 characters.",
    "Error code: page_html_too_large",
    "Content scope: main",
    "Captured characters: 2450123",
    "Maximum characters: 2000000",
  ].join("\n"));
});

test("error report helpers whitelist stable codes and bounded numeric diagnostics", () => {
  assert.equal(normalizeErrorCode("page_html_too_large"), "page_html_too_large");
  assert.equal(normalizeErrorCode("Bad code: secret"), "unexpected_error");
  assert.equal(safePositiveInteger(2_450_123), 2_450_123);
  assert.equal(safePositiveInteger(-1), null);
  assert.equal(safePositiveInteger("not a number"), null);
});

test("copyErrorReport writes the complete report and fails clearly without clipboard access", async () => {
  const copied = [];
  await copyErrorReport("full error report", {
    writeText: async (value) => copied.push(value),
  });
  assert.deepEqual(copied, ["full error report"]);
  await assert.rejects(() => copyErrorReport("report", null), /Clipboard is unavailable/);
});
