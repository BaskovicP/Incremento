import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { readdirSync } from "node:fs";

const base = new URL("../", import.meta.url);
const catalogs = Object.fromEntries(
  ["en", "hr", "zh_CN"].map((code) => [code, JSON.parse(readFileSync(new URL(`_locales/${code}/messages.json`, base), "utf8"))])
);

function parameters(entry) {
  const tokens = [...entry.message.matchAll(/\$([A-Za-z][A-Za-z0-9_]*)\$/g)].map((match) => match[1].toLowerCase());
  const placeholders = entry.placeholders || {};
  assert.deepEqual(Object.keys(placeholders).sort(), [...new Set(tokens)].sort());
  assert.deepEqual(Object.values(placeholders).map((item) => item.content).sort(),
    Object.values(placeholders).map((_item, index) => `$${index + 1}`).sort());
  return tokens.sort();
}

test("manifest references catalog messages in every Chrome locale", () => {
  const manifest = JSON.parse(readFileSync(new URL("manifest.json", base), "utf8"));
  assert.equal(manifest.default_locale, "en");
  const references = JSON.stringify(manifest).match(/__MSG_([A-Za-z0-9_]+)__/g) || [];
  assert.ok(references.length >= 10);
  for (const reference of references) {
    const key = reference.slice(6, -2);
    for (const catalog of Object.values(catalogs)) assert.ok(catalog[key], `${key} missing`);
  }
});

test("runtime catalogs have matching keys and placeholder contracts", () => {
  for (const [key, english] of Object.entries(catalogs.en)) {
    assert.match(key, /^[a-z][a-z0-9_]*$/);
    const expected = parameters(english);
    for (const [language, catalog] of Object.entries(catalogs)) {
      if (language === "zh_CN" && /_(one|few)$/.test(key)) continue;
      assert.ok(catalog[key], `${language}.${key} missing`);
      assert.deepEqual(parameters(catalog[key]), expected, `${language}.${key}`);
    }
  }
  for (const key of Object.keys(catalogs.zh_CN)) assert.ok(!/_(one|few)$/.test(key), `Chinese plural ${key}`);
});

test("static runtime translation references resolve to catalog entries", () => {
  const visit = (directory) => readdirSync(new URL(directory, base), { withFileTypes: true }).flatMap((entry) => {
    const path = `${directory}${entry.name}`;
    return entry.isDirectory() ? visit(`${path}/`) : (path.endsWith(".js") || path.endsWith(".jsx") ? [path] : []);
  });
  for (const path of visit("src/")) {
    const source = readFileSync(new URL(path, base), "utf8");
    for (const match of source.matchAll(/\b(t|tn|message)\("([a-z][a-z0-9_]*)"/g)) {
      const [, kind, key] = match;
      if (kind === "tn") {
        assert.ok(catalogs.en[`${key}_one`] && catalogs.en[`${key}_other`], `${path}: ${key}`);
        assert.ok(catalogs.hr[`${key}_one`] && catalogs.hr[`${key}_few`] && catalogs.hr[`${key}_other`], `${path}: ${key}`);
        assert.ok(catalogs.zh_CN[`${key}_other`], `${path}: ${key}`);
      } else {
        assert.ok(catalogs.en[key] || catalogs.en[`${key}_other`], `${path}: ${key}`);
      }
    }
  }
});
