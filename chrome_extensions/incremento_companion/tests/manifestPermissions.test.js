import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const manifestUrl = new URL("../manifest.json", import.meta.url);

async function loadManifest() {
  return JSON.parse(await readFile(manifestUrl, "utf8"));
}

test("manifest keeps arbitrary browsing access optional and gesture-scoped", async () => {
  const manifest = await loadManifest();
  const permissions = new Set(manifest.permissions || []);
  const requiredHosts = new Set(manifest.host_permissions || []);
  const optionalHosts = new Set(manifest.optional_host_permissions || []);

  assert.equal(permissions.has("activeTab"), true);
  assert.equal(permissions.has("scripting"), true);
  assert.equal(permissions.has("tabs"), false);
  assert.equal(requiredHosts.has("<all_urls>"), false);
  assert.equal(requiredHosts.has("http://*/*"), false);
  assert.equal(requiredHosts.has("https://*/*"), false);
  assert.equal(optionalHosts.has("http://*/*"), true);
  assert.equal(optionalHosts.has("https://*/*"), true);
  assert.deepEqual(requiredHosts, new Set([
    "*://*.youtube.com/*",
    "*://*.youtu.be/*",
    "*://*.vimeo.com/*",
    "http://127.0.0.1:8765/*",
    "http://127.0.0.1:8766/*",
  ]));
});

test("manifest auto-injects only on supported media providers", async () => {
  const manifest = await loadManifest();
  const matches = new Set(
    (manifest.content_scripts || []).flatMap((entry) => entry.matches || [])
  );

  assert.equal(matches.has("http://*/*"), false);
  assert.equal(matches.has("https://*/*"), false);
  assert.deepEqual(matches, new Set([
    "*://*.youtube.com/*",
    "*://*.youtu.be/*",
    "*://*.vimeo.com/*",
  ]));

  const exposedMatches = new Set(
    (manifest.web_accessible_resources || []).flatMap((entry) => entry.matches || [])
  );
  assert.deepEqual(exposedMatches, new Set(["http://*/*", "https://*/*"]));
});
