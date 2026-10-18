import test from "node:test";
import assert from "node:assert/strict";
import { createWebsiteTagPreferences, websiteOrigin } from "../src/shared/websiteTags.js";

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => {resolve = yes; reject = no;});
  return {promise, resolve, reject};
}

function setup(overrides = {}) {
  const states = [];
  const tags = [];
  const writes = [];
  const model = createWebsiteTagPreferences({
    load: async () => ({site: "example.org", enabled: true, tags: ["saved", "topic"], profileToken: "profile-a"}),
    save: async value => {writes.push(value); return {ok: true};},
    onState: state => states.push(state),
    onTags: text => tags.push(text),
    ...overrides,
  });
  return {model, states, tags, writes};
}

test("website identity sends only an HTTP origin and rejects credentials or protected schemes", () => {
  assert.equal(websiteOrigin("https://Example.org/private?secret=yes#part"), "https://example.org");
  for (const url of ["file:///private", "chrome://settings", "https://u:p@example.org", "https://example.org/\nx"]) {
    assert.equal(websiteOrigin(url), "");
  }
});

test("reopening a remembered website restores tags; edits persist with the captured profile", async () => {
  const {model, states, tags, writes} = setup();
  await model.load("https://example.org/article");
  assert.equal(tags.at(-1), "saved topic");
  assert.equal(states.at(-1).enabled, true);
  model.changeTags("new, topic new");
  await model.flush();
  assert.deepEqual(writes, [{url: "https://example.org", enabled: true, tags: ["new", "topic"], profileToken: "profile-a"}]);
  assert.equal(states.at(-1).saving, false);
});

test("opt-in saves current tags and disabling forgets without clearing the current form", async () => {
  const {model, tags, writes} = setup({load: async () => ({site: "example.org", enabled: false, tags: [], profileToken: "a"})});
  await model.load("https://example.org");
  model.changeTags("manual");
  await model.flush();
  assert.equal(writes.length, 0);
  model.setEnabled(true);
  await model.flush();
  model.setEnabled(false);
  await model.flush();
  assert.deepEqual(writes.map(value => [value.enabled, value.tags]), [[true, ["manual"]], [false, []]]);
  assert.equal(tags.at(-1), "manual");
});

test("rapid edits serialize and coalesce so an old response cannot restore older tags", async () => {
  const first = deferred();
  const writes = [];
  const {model, tags} = setup({save: async value => {writes.push(value); if (writes.length === 1) await first.promise;}});
  await model.load("https://example.org");
  model.changeTags("one");
  model.changeTags("two");
  model.changeTags("latest");
  first.resolve();
  await model.flush();
  assert.deepEqual(writes.map(value => value.tags), [["one"], ["latest"]]);
  assert.equal(tags.at(-1), "latest");
});

test("late loads from a previous website never overwrite the new website", async () => {
  const first = deferred();
  const {model, states, tags} = setup({load: url => url.includes("old.org") ? first.promise : Promise.resolve({site: "new.org", enabled: false, tags: [], profileToken: "b"})});
  const pending = model.load("https://old.org");
  await model.load("https://new.org");
  model.changeTags("manual");
  first.resolve({site: "old.org", enabled: true, tags: ["stale"], profileToken: "a"});
  await pending;
  assert.equal(states.at(-1).site, "new.org");
  assert.equal(tags.at(-1), "manual");
});

test("save errors remain visible and retry preserves edits without clearing the form", async () => {
  let fail = true;
  const {model, states, tags, writes} = setup({save: async value => {if (fail) throw new Error("offline"); writes.push(value);}});
  await model.load("https://example.org");
  model.changeTags("unsaved");
  await assert.rejects(model.flush(), /offline/);
  assert.equal(states.at(-1).error.message, "offline");
  assert.equal(tags.at(-1), "unsaved");
  fail = false;
  model.retry();
  await model.flush();
  assert.deepEqual(writes[0].tags, ["unsaved"]);
  assert.equal(states.at(-1).error, null);
});

test("failed loads cannot write defaults over saved tags and disposal ignores callbacks", async () => {
  const {model, states, writes} = setup({load: async () => {throw new Error("offline");}});
  await model.load("https://example.org");
  model.setEnabled(true);
  model.changeTags("manual");
  assert.equal(writes.length, 0);
  assert.equal(states.at(-1).ready, false);
  const count = states.length;
  model.dispose();
  await model.load("https://example.org");
  assert.equal(states.length, count);
});

test("closing the popup lets already requested edits finish without touching the closed UI", async () => {
  const first = deferred();
  const writes = [];
  const {model, states} = setup({save: async value => {writes.push(value); if (writes.length === 1) await first.promise;}});
  await model.load("https://example.org");
  model.changeTags("one");
  model.changeTags("latest");
  model.dispose();
  const count = states.length;
  first.resolve();
  await model.flush();
  assert.deepEqual(writes.map(value => value.tags), [["one"], ["latest"]]);
  assert.equal(states.length, count);
});
