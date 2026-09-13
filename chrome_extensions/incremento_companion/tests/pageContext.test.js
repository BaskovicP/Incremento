import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";

import { readPageContextFromTab } from "../src/shared/pageContext.js";

function runAsChromeInjection(html, selection, maxHtmlChars, maxSelectedTextChars) {
  const page = {
    document: { documentElement: { outerHTML: html }, title: "Example" },
    window: { getSelection: () => ({ toString: () => selection }), location: { href: "https://example.test" } },
    globalThis: {},
  };
  const injected = vm.runInNewContext(`(${readPageContextFromTab.toString()})`, page);
  return injected(maxHtmlChars, maxSelectedTextChars);
}

test("serialized page context reader reports oversized HTML without module scope", () => {
  const result = runAsChromeInjection("123456", "selected", 5, 20);
  assert.equal(result.ok, false);
  assert.equal(result.errorCode, "page_html_too_large");
  assert.equal(result.errorParams.count, 5);
});

test("serialized page context reader reports oversized selection without module scope", () => {
  const result = runAsChromeInjection("<html>", "selected", 20, 5);
  assert.equal(result.ok, false);
  assert.equal(result.errorCode, "selected_text_too_large");
  assert.equal(result.errorParams.count, 5);
});
