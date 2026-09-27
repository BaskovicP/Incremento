import test from "node:test";
import assert from "node:assert/strict";

import {
  buildContextMenuImportOptions,
  buildLinkSaveFallbackTitle,
  buildLinkSaveTitle,
  buildLinkSaveTitleFromCandidates,
  DEFAULT_LINK_SAVE_SETTINGS,
  eventMatchesLinkSaveModifier,
  isSupportedLinkSaveUrl,
  normalizeLinkSaveSettings,
  resolveContextMenuDeckName,
} from "../src/shared/linkSaveModel.js";

test("normalizeLinkSaveSettings applies defaults and preserves supported modifier keys", () => {
  assert.deepEqual(normalizeLinkSaveSettings(null), DEFAULT_LINK_SAVE_SETTINGS);
  assert.equal(DEFAULT_LINK_SAVE_SETTINGS.modifierClickEnabled, true);
  assert.deepEqual(
    normalizeLinkSaveSettings({
      modifierClickEnabled: true,
      modifierKey: "shift",
      navigateAfterSave: false,
      contextMenuEnabled: false,
      contextMenuDeckName: "Research",
    }),
    {
      modifierClickEnabled: true,
      modifierKey: "shift",
      navigateAfterSave: false,
      contextMenuEnabled: false,
      contextMenuDeckName: "Research",
    },
  );
});

test("context-menu import options always apply topic and the configured deck", () => {
  assert.deepEqual(
    buildContextMenuImportOptions({ contextMenuDeckName: "  Study   Videos  " }),
    {
      deckName: "Study Videos",
      tags: ["topic"],
    },
  );
  assert.deepEqual(
    buildContextMenuImportOptions({ contextMenuDeckName: "" }),
    {
      deckName: "Topics",
      tags: ["topic"],
    },
  );
});

test("resolveContextMenuDeckName keeps an available choice and falls back safely", () => {
  assert.equal(resolveContextMenuDeckName("Research", ["Topics", "Research"]), "Research");
  assert.equal(resolveContextMenuDeckName("Missing", ["Archive", "Topics"]), "Topics");
  assert.equal(resolveContextMenuDeckName("Missing", ["Archive", "Reading"]), "Archive");
  assert.equal(resolveContextMenuDeckName("Missing", []), "Topics");
});

test("eventMatchesLinkSaveModifier requires the configured modifier without extras", () => {
  const settings = normalizeLinkSaveSettings({
    modifierClickEnabled: true,
    modifierKey: "alt",
  });
  assert.equal(eventMatchesLinkSaveModifier({ altKey: true }, settings), true);
  assert.equal(eventMatchesLinkSaveModifier({ altKey: true, shiftKey: true }, settings), false);
  assert.equal(eventMatchesLinkSaveModifier({ shiftKey: true }, settings), false);
});

test("buildLinkSaveTitle prefers cleaned link text", () => {
  assert.equal(
    buildLinkSaveTitle("   Example   article  ", "https://example.com/path"),
    "Example article",
  );
});

test("YouTube thumbnail title selection skips duration overlays", () => {
  const url = "https://www.youtube.com/watch?v=abc123&t=633s";
  assert.equal(
    buildLinkSaveTitleFromCandidates(
      ["10:33", "10 minutes, 33 seconds", "A useful lecture about memory"],
      url,
    ),
    "A useful lecture about memory",
  );
});

test("buildLinkSaveTitle falls back to a readable URL-derived title", () => {
  assert.equal(
    buildLinkSaveTitle("", "https://www.example.com/articles/test-page"),
    "example.com / test-page",
  );
  assert.equal(buildLinkSaveFallbackTitle("https://www.example.com"), "example.com");
});

test("isSupportedLinkSaveUrl only accepts http(s) links", () => {
  assert.equal(isSupportedLinkSaveUrl("https://example.com"), true);
  assert.equal(isSupportedLinkSaveUrl("http://example.com"), true);
  assert.equal(isSupportedLinkSaveUrl("mailto:test@example.com"), false);
  assert.equal(isSupportedLinkSaveUrl("javascript:alert(1)"), false);
});
