import test from "node:test";
import assert from "node:assert/strict";

import {
  buildLinkSaveFallbackTitle,
  buildLinkSaveTitle,
  DEFAULT_LINK_SAVE_SETTINGS,
  eventMatchesLinkSaveModifier,
  isSupportedLinkSaveUrl,
  normalizeLinkSaveSettings,
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
    }),
    {
      modifierClickEnabled: true,
      modifierKey: "shift",
      navigateAfterSave: false,
      contextMenuEnabled: false,
    },
  );
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
