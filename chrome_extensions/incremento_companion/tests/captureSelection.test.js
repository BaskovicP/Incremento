import test from "node:test";
import assert from "node:assert/strict";
import { readCaptureSelection } from "../src/shared/captureSelection.js";
import { buildBrowserCapturePayload } from "../src/shared/browserCaptureModel.js";

const text = value => ({nodeType: 3, textContent: value});
const element = (name, ...children) => ({nodeType: 1, localName: name, childNodes: children});

test("selection capture keeps semantic formatting but excludes page controls and executable markup", () => {
  const fragment = element("div", element("p", text("A "), element("strong", text("point"))),
    element("nav", text("Navigation")), element("script", text("danger()")));
  const result = readCaptureSelection({toString: () => "A point", rangeCount: 1,
    getRangeAt: () => ({cloneContents: () => fragment})});
  assert.equal(result.selectedText, "A point");
  assert.equal(result.selectedHtml, "<div><p>A <strong>point</strong></p></div>");
});

test("selection capture has a plain-text fallback and rejects large selections", () => {
  assert.deepEqual(readCaptureSelection({toString: () => "A point", rangeCount: 0}),
    {selectedText: "A point", selectedHtml: ""});
  assert.throws(() => readCaptureSelection({toString: () => "x".repeat(200_001)}), /large/i);
});

test("edited excerpts discard stale formatting while passage links retain the original selection", () => {
  const context = {url: "https://example.com", title: "Page", selectedText: "Edited",
    originalSelectedText: "Original", selectedHtml: "<strong>Original</strong>"};
  const payload = buildBrowserCapturePayload(context, {linkToPassage: true});
  assert.equal(payload.selectedHtml, "");
  assert.equal(payload.sourceText, "Original");
  assert.equal(payload.linkToPassage, true);
  const unchanged = buildBrowserCapturePayload({...context, selectedText: "Original"}, {});
  assert.equal(unchanged.selectedHtml, "<strong>Original</strong>");
});
