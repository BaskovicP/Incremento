import test from "node:test";
import assert from "node:assert/strict";

import {
  applyTagSuggestion,
  getTagSuggestions,
  normalizeAvailableTags,
} from "../src/shared/tagAutocomplete.js";

test("normalizeAvailableTags sorts and deduplicates existing tags case-insensitively", () => {
  assert.deepEqual(
    normalizeAvailableTags([" spiritual ", "Topic::Books", "SPIRITUAL", "", null]),
    ["spiritual", "Topic::Books"]
  );
});

test("getTagSuggestions matches the active token and keeps already chosen tags out", () => {
  const tags = ["art", "book", "spiritual", "spiritual::prayer", "world::history"];

  assert.deepEqual(
    getTagSuggestions(tags, "book spir", 9),
    ["spiritual", "spiritual::prayer"]
  );
  assert.deepEqual(
    getTagSuggestions(tags, "spiritual ", 10),
    ["art", "book", "spiritual::prayer", "world::history"]
  );
  assert.deepEqual(
    getTagSuggestions(tags, "spiritual spiritual", 4),
    ["spiritual::prayer"]
  );
});

test("getTagSuggestions ranks prefix matches before contains matches and bounds the menu", () => {
  assert.deepEqual(
    getTagSuggestions(["beta", "alphabet", "alpha", "alpine", "calm"], "al", 2, 3),
    ["alpha", "alpine", "alphabet"]
  );
});

test("applyTagSuggestion replaces only the token at the cursor and appends a separator at the end", () => {
  assert.deepEqual(
    applyTagSuggestion("book spir draft", "spiritual", 7, 7),
    { value: "book spiritual draft", cursor: 14 }
  );
  assert.deepEqual(
    applyTagSuggestion("book, spir", "spiritual::prayer", 10, 10),
    { value: "book, spiritual::prayer ", cursor: 24 }
  );
});
