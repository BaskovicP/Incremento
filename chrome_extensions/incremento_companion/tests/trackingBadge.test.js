import test from "node:test";
import assert from "node:assert/strict";

import { refreshTrackingBadgeLanguage } from "../src/shared/trackingBadge.js";

test("locale refresh leaves absent and hidden tracking badges untouched", () => {
  const refreshed = [];
  assert.equal(refreshTrackingBadgeLanguage(null, () => refreshed.push("absent")), false);
  assert.equal(
    refreshTrackingBadgeLanguage({ style: { display: "none" } }, () => refreshed.push("hidden")),
    false
  );
  assert.deepEqual(refreshed, []);
});

test("locale refresh relabels an existing visible tracking badge", () => {
  const badge = { style: { display: "inline-flex" } };
  let calls = 0;
  assert.equal(refreshTrackingBadgeLanguage(badge, () => { calls += 1; }), true);
  assert.equal(calls, 1);
  assert.equal(badge.style.display, "inline-flex");
});
