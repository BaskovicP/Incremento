import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";

import {
  pageContextOptionsForImport,
  readPageContextFromTab,
} from "../src/shared/pageContext.js";

test("import context options request HTML only for actions that consume it", () => {
  assert.deepEqual(pageContextOptionsForImport("video"), { includeHtml: false, htmlScope: "full" });
  assert.deepEqual(pageContextOptionsForImport("webpage"), { includeHtml: false, htmlScope: "full" });
  assert.deepEqual(
    pageContextOptionsForImport("writing", { writingMode: "selection" }),
    { includeHtml: false, htmlScope: "full" },
  );
  assert.deepEqual(pageContextOptionsForImport("pdf"), { includeHtml: true, htmlScope: "full" });
  assert.deepEqual(
    pageContextOptionsForImport("writing", { writingMode: "webpage_markdown", pageContentScope: "main" }),
    { includeHtml: true, htmlScope: "main" },
  );
  assert.deepEqual(
    pageContextOptionsForImport("writing", { writingMode: "webpage_markdown", pageContentScope: "full" }),
    { includeHtml: true, htmlScope: "full" },
  );
});

function runAsChromeInjection(html, selection, maxHtmlChars, maxSelectedTextChars, options = {}) {
  const page = {
    document: { documentElement: { outerHTML: html }, title: "Example" },
    window: { getSelection: () => ({ toString: () => selection }), location: { href: "https://example.test" } },
    globalThis: {},
  };
  const injected = vm.runInNewContext(`(${readPageContextFromTab.toString()})`, page);
  return injected(maxHtmlChars, maxSelectedTextChars, options);
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

test("metadata-only page context does not serialize an oversized DOM", () => {
  const documentElement = {};
  Object.defineProperty(documentElement, "outerHTML", {
    get() {
      throw new Error("outerHTML must not be read");
    },
  });
  const page = {
    document: { documentElement, title: "Large page" },
    window: { getSelection: () => ({ toString: () => "" }), location: { href: "https://example.test/large" } },
    globalThis: {},
  };
  const injected = vm.runInNewContext(`(${readPageContextFromTab.toString()})`, page);

  const result = injected(20, 20, { includeHtml: false });

  assert.equal(result.ok, true);
  assert.equal(result.html, "");
  assert.equal(result.title, "Large page");
});

test("main-content page context serializes the largest semantic content root", () => {
  const small = {
    textContent: "Short",
    cloneNode: () => ({ outerHTML: "<article>Short</article>", querySelectorAll: () => [] }),
  };
  const large = {
    textContent: "This is the useful article body",
    cloneNode: () => ({ outerHTML: "<main><p>Useful article</p></main>", querySelectorAll: () => [] }),
  };
  const page = {
    document: {
      documentElement: { outerHTML: "x".repeat(100) },
      body: { textContent: "Fallback body" },
      querySelectorAll: () => [small, large],
      title: "Large page",
    },
    window: { getSelection: () => ({ toString: () => "" }), location: { href: "https://example.test/large" } },
    globalThis: {},
  };
  const injected = vm.runInNewContext(`(${readPageContextFromTab.toString()})`, page);

  const result = injected(50, 20, { includeHtml: true, htmlScope: "main" });

  assert.equal(result.ok, true);
  assert.equal(result.html, "<main><p>Useful article</p></main>");
});

test("full-content page context removes backend-ignored nodes before enforcing the cap", () => {
  let removed = false;
  const clone = {
    querySelectorAll: () => [{ remove: () => { removed = true; } }],
  };
  Object.defineProperty(clone, "outerHTML", {
    get() {
      return removed ? "<html><body>Useful</body></html>" : "x".repeat(100);
    },
  });
  const page = {
    document: {
      documentElement: {
        outerHTML: "x".repeat(100),
        cloneNode: () => clone,
      },
      title: "Large page",
    },
    window: { getSelection: () => ({ toString: () => "" }), location: { href: "https://example.test/large" } },
    globalThis: {},
  };
  const injected = vm.runInNewContext(`(${readPageContextFromTab.toString()})`, page);

  const result = injected(50, 20, { includeHtml: true, htmlScope: "full" });

  assert.equal(result.ok, true);
  assert.equal(result.html, "<html><body>Useful</body></html>");
});
