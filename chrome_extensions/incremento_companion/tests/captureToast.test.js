import test from "node:test";
import assert from "node:assert/strict";
import { showPageToast } from "../src/content/toast.js";

// A minimal DOM boundary: real event callbacks and UI transitions are exercised
// without a browser, user profile, or wall-clock waits.
function fixture() {
  class Element {
    constructor(tagName) {
      Object.assign(this, {tagName, children: [], style: {}, attributes: {}, listeners: {}, text: ""});
    }
    set textContent(value) {this.text = String(value); this.children = [];}
    get textContent() {return this.text + this.children.map(child => child.textContent).join("");}
    set innerHTML(_value) {assert.fail("Page text must never become executable markup");}
    setAttribute(name, value) {this.attributes[name] = value;}
    addEventListener(name, listener) {this.listeners[name] = listener;}
    appendChild(child) {this.children.push(child); return child;}
    remove() {this.removed = true;}
    click(event = {isTrusted: true, stopPropagation() {}}) {return this.listeners.click?.(event);}
  }
  const root = new Element("html");
  const all = element => [element, ...element.children.flatMap(all)];
  const doc = {documentElement: root, createElement: name => new Element(name),
    getElementById: id => all(root).find(element => element.id === id && !element.removed)};
  const timers = [], requests = [];
  const state = {response: async () => ({ok: true})};
  const options = {document: doc, requestFrame: callback => callback(),
    schedule: (callback, delay) => timers.push({callback, delay}),
    request: async message => {requests.push(message); return state.response();}};
  const button = (toast, label) => all(toast).find(element => element.tagName === "button" && element.textContent === label);
  return {doc, timers, requests, state, options, button};
}

test("a shortcut warning offers an accessible settings button and stays visible until acted on", () => {
  const {options, timers, requests, button} = fixture();
  const toast = showPageToast("Choose In Chrome. <script>untrusted</script>", {...options, action: "open_shortcut_settings"});
  assert.equal(toast.attributes.role, "alert");
  assert.ok(button(toast, "Open shortcut settings"));
  assert.ok(button(toast, "Dismiss warning"));
  assert.match(toast.textContent, /<script>untrusted<\/script>/);
  assert.equal(toast.removed, undefined);
  assert.deepEqual(timers, []);
  assert.deepEqual(requests, []);
});

test("clicking Open shortcut settings sends one fixed action and dismisses the warning after success", async () => {
  const {options, state, requests, button} = fixture();
  let finish;
  state.response = () => new Promise(resolve => {finish = resolve;});
  const toast = showPageToast("Use In Chrome", {...options, action: "open_shortcut_settings"});
  const open = button(toast, "Open shortcut settings");
  const pending = open.click();
  assert.equal(open.disabled, true);
  await open.click();
  assert.deepEqual(requests, [{type: "OPEN_SHORTCUT_SETTINGS"}]);
  assert.equal(toast.removed, undefined);
  finish({ok: true});
  await pending;
  assert.equal(toast.removed, true);
});

for (const reason of ["rejected request", "unsuccessful response"]) {
  test(`settings failure via ${reason} keeps the warning available for retry`, async () => {
    const {options, state, requests, button} = fixture();
    state.response = reason === "rejected request"
      ? async () => {throw new Error("browser internal detail");} : async () => ({ok: false});
    const toast = showPageToast("Use In Chrome", {...options, action: "open_shortcut_settings"});
    const open = button(toast, "Open shortcut settings");
    await open.click();
    assert.equal(toast.removed, undefined);
    assert.equal(open.disabled, false);
    assert.match(toast.textContent, /Failed to open Chrome shortcut settings\./);
    assert.ok(!toast.textContent.includes("browser internal detail"));
    state.response = async () => ({ok: true});
    await open.click();
    assert.equal(requests.length, 2);
    assert.equal(toast.removed, true);
  });
}

test("dismissing a warning and synthetic page clicks do not open settings", async () => {
  const {options, requests, button} = fixture();
  const toast = showPageToast("Use In Chrome", {...options, action: "open_shortcut_settings"});
  await button(toast, "Open shortcut settings").click({isTrusted: false, stopPropagation() {}});
  button(toast, "Dismiss warning").click();
  assert.equal(toast.removed, true);
  assert.deepEqual(requests, []);
});

test("ordinary toasts still expire, and their timers cannot dismiss a newer shortcut warning", () => {
  const {options, timers, doc} = fixture();
  const normal = showPageToast("Copied", options);
  assert.equal(timers[0].delay, 2400);
  const warning = showPageToast("Use In Chrome", {...options, action: "open_shortcut_settings"});
  assert.equal(normal.removed, true);
  timers[0].callback();
  assert.equal(timers[1].delay, 220);
  timers[1].callback();
  assert.equal(warning.removed, undefined);
  assert.equal(doc.getElementById("incremento-video-time-toast"), warning);
});

test("unknown warning actions cannot create buttons or open a supplied URL", () => {
  const {options, timers, requests, button} = fixture();
  const toast = showPageToast("Untrusted action", {...options, action: "https://untrusted.example"});
  assert.equal(button(toast, "Open shortcut settings"), undefined);
  assert.deepEqual(requests, []);
  assert.equal(timers[0].delay, 2400);
});
