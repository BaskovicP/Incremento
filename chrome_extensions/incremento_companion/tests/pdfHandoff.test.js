import test from "node:test";
import assert from "node:assert/strict";
import { createPdfHandoffController, handoffTicketFromUrl, sameHandoffSite, watchVerifiedPage, handoffSenderTab } from "../src/background/pdfHandoff.js";
import { readPdfHandoffInfo, allowPdfHandoff } from "../src/shared/pdfHandoffPermissions.js";

const ticket = "a".repeat(64);
const landing = `http://127.0.0.1:8766/incremento/webpage-pdf#${ticket}`;

test("handoff links accept only the exact local path and ticket shape", () => {
  assert.equal(handoffTicketFromUrl(landing), ticket);
  for (const url of [landing.replace("127.0.0.1", "evil.test"), landing.replace("8766", "8767"), landing.replace("http:", "https:"), `${landing}x`, `https://example.test/#${ticket}`]) {
    assert.equal(handoffTicketFromUrl(url), "");
  }
  assert.equal(sameHandoffSite("https://archive.is/abc", "https://archive.ph/abc"), true);
  assert.equal(sameHandoffSite("https://example.test/a", "https://evil.test/a"), false);
});

test("permission page identifies its own tab and requests access in the click before any asynchronous work", async () => {
  const calls = [];
  const api = {tabs: {getCurrent: async () => ({id: 7})},
    runtime: {sendMessage: async value => {calls.push(value); return {ok: true, origins: ["https://example.test/*"]};}},
    permissions: {request: value => {calls.push(value); return Promise.resolve(true);}}};
  const info = await readPdfHandoffInfo(ticket, api);
  calls.length = 0;
  const permitted = allowPdfHandoff(ticket, info, api);
  assert.deepEqual(calls, [{origins: ["https://example.test/*"]}]);
  await permitted;
  assert.deepEqual(calls[1], {type: "PDF_HANDOFF_BEGIN", ticket, tabId: 7});
});

test("only a real content tab or the exact extension permission page can identify a handoff tab", () => {
  const api = {runtime: {getURL: path => `chrome-extension://${"b".repeat(32)}/${path}`}};
  const msg = {type: "PDF_HANDOFF_INFO", ticket, tabId: 7};
  assert.equal(handoffSenderTab(msg, {url: api.runtime.getURL(`popup.html?pdfHandoff=${ticket}`)}, api), 7);
  assert.equal(handoffSenderTab(msg, {url: "https://example.test/article", tab: {id: 7}, frameId: 0}, api), null);
  assert.equal(handoffSenderTab({...msg, type: "PDF_HANDOFF_READY"}, {url: "https://example.test/article", tab: {id: 7}, frameId: 0}, api), 7);
  assert.equal(handoffSenderTab({...msg, type: "PDF_HANDOFF_READY"}, {frameId: 0}, api), null);
});

test("declining first-use access never opens or captures the target site", async () => {
  let began = false;
  const api = {permissions: {request: async () => false}, runtime: {sendMessage: async () => {began = true;}}};
  await assert.rejects(allowPdfHandoff(ticket, {origins: ["https://example.test/*"], tabId: 7}, api));
  assert.equal(began, false);
});

function fixture({permission = true} = {}) {
  const storage = {}, updates = [], probes = [], requests = [];
  let currentUrl = landing;
  const api = {
    runtime: {getURL: path => `chrome-extension://${"b".repeat(32)}/${path}`},
    storage: {session: {
      get: async key => ({[key]: storage[key]}), set: async values => Object.assign(storage, values),
      remove: async key => {delete storage[key];},
    }},
    permissions: {contains: async () => permission},
    tabs: {update: async (id, change) => {updates.push([id, change]); currentUrl = change.url;}, get: async id => ({id, url: currentUrl})},
    scripting: {executeScript: async options => {probes.push(options);}},
  };
  const rpc = async body => {
    requests.push(body);
    return body.action === "describe" ? {ok: true, url: "https://example.test/article", remainingSeconds: 600} : {ok: true};
  };
  const readPage = async () => ({ok: true, url: currentUrl, html: "<article>Verified content</article>"});
  const controller = createPdfHandoffController({api, rpc, readPage, now: () => 1000});
  return {api, controller, updates, probes, requests, setUrl: value => {currentUrl = value;}};
}

test("Anki handoff opens the article and completion sends its HTML without a capture click", async () => {
  const f = fixture();
  await f.controller.navigate(7, landing);
  assert.deepEqual(f.updates, [[7, {url: "https://example.test/article"}]]);
  await f.controller.loaded(7, "https://example.test/article");
  assert.equal(f.probes.length, 1);
  assert.deepEqual(f.probes[0].target, {tabId: 7, frameIds: [0]});
  await f.controller.ready(7, ticket, 0);
  assert.deepEqual(f.requests.at(-1), {action: "submit", ticket, url: "https://example.test/article", html: "<article>Verified content</article>"});
  const count = f.requests.length;
  await f.controller.ready(7, ticket, 0);
  assert.equal(f.requests.length, count, "duplicate readiness must not submit twice");
});

test("first use requests site access through an extension page rather than injecting without permission", async () => {
  const f = fixture({permission: false});
  await f.controller.navigate(7, landing);
  assert.match(f.updates[0][1].url, /popup.html\?pdfHandoff=/);
  assert.equal(f.probes.length, 0);
});

test("another tab, subframe, wrong ticket and navigation away cannot finish the import", async () => {
  const f = fixture();
  await f.controller.navigate(7, landing);
  await f.controller.ready(8, ticket, 0);
  await f.controller.ready(7, "c".repeat(64), 0);
  await f.controller.ready(7, ticket, 1);
  assert.equal(f.requests.filter(value => value.action === "submit").length, 0);
  f.setUrl("https://evil.test/article");
  await f.controller.ready(7, ticket, 0);
  assert.equal(f.requests.filter(value => value.action === "submit").length, 0);
  f.setUrl("https://example.test/unrelated-article");
  await f.controller.ready(7, ticket, 0);
  assert.equal(f.requests.filter(value => value.action === "submit").length, 0);
});

test("verification watcher waits through the challenge and emits readiness without a click", async () => {
  const original = {document: globalThis.document, chrome: globalThis.chrome, setInterval: globalThis.setInterval, clearInterval: globalThis.clearInterval};
  let tick;
  const messages = [];
  globalThis.setInterval = callback => {tick = callback; return 1;};
  globalThis.clearInterval = () => {};
  globalThis.chrome = {runtime: {sendMessage: async value => messages.push(value)}};
  globalThis.document = {readyState: "complete", title: "Just a moment...", body: {innerText: "Verify you are human"}, querySelector: () => ({})};
  try {
    watchVerifiedPage(ticket, Date.now() + 600000);
    tick(); tick();
    assert.deepEqual(messages, []);
    globalThis.document.title = "Article";
    globalThis.document.body.innerText = "The article is now readable. ".repeat(20);
    globalThis.document.querySelector = () => null;
    tick();
    assert.deepEqual(messages, [], "wait for stable article content");
    tick();
    assert.deepEqual(messages, [{type: "PDF_HANDOFF_READY", ticket}]);
  } finally {
    Object.assign(globalThis, original);
    delete globalThis.__incrementoPdfHandoffWatch;
  }
});

test("worker restart restores the pending handoff, while closing its tab cancels it", async () => {
  const f = fixture();
  await f.controller.navigate(7, landing);
  const restored = createPdfHandoffController({api: f.api, rpc: async body => f.requests.push(body), readPage: async () => ({url: "https://example.test/article", html: "<p>Article</p>"}), now: () => 1000});
  await restored.ready(7, ticket, 0);
  assert.equal(f.requests.at(-1).action, "submit");
  await f.controller.navigate(8, landing);
  await f.controller.closed(8);
  assert.deepEqual(f.requests.at(-1), {action: "fail", ticket});
});
