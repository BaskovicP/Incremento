import test from "node:test";
import assert from "node:assert/strict";

test("one media scan supplies both heartbeats and hidden polling waits for playback events", async () => {
  const names = ["chrome", "window", "document", "requestAnimationFrame"];
  const originals = names.map(name => [name, Object.getOwnPropertyDescriptor(globalThis, name)]);
  const intervals = new Map(), events = new Map(), messages = [];
  let scans = 0;
  const video = {videoWidth: 640, videoHeight: 360, currentTime: 19, paused: false,
    getAttribute: () => "Synthetic video"};
  const videos = [video];
  globalThis.document = {
    title: "Synthetic page", visibilityState: "visible",
    querySelector: () => null,
    getElementsByTagName: () => { scans += 1; return videos; },
    querySelectorAll: selector => { if (selector === "video") { scans += 1; return [video]; } return []; },
    addEventListener: (name, callback) => events.set(name, callback),
    getElementById: () => null, createElement: () => ({style: {}, setAttribute() {}, remove() {}}),
    documentElement: {appendChild() {}},
  };
  globalThis.window = {location: new URL("https://www.youtube.com/watch?v=abc123DEF45"),
    getSelection: () => ({toString: () => "", rangeCount: 0}),
    addEventListener() {}, setTimeout() {},
    setInterval: (callback, delay) => { intervals.set(delay, callback); return delay; }};
  globalThis.requestAnimationFrame = callback => callback();
  globalThis.chrome = {
    i18n: {getUILanguage: () => "en"},
    storage: {local: {get: async () => ({ui_language: "en"})}, onChanged: {addListener() {}}},
    runtime: {id: "synthetic-extension", onMessage: {addListener() {}}, sendMessage(message, callback) {
      messages.push(message); callback?.({ok: true});
    }},
  };
  try {
    await import("../src/content/main.js?media-sampling");
    scans = 0;
    intervals.get(1000)();
    assert.equal(scans, 1);
    assert.deepEqual(messages.filter(message => /heartbeat$/.test(message.type)).map(message =>
      [message.type, message.seconds, message.videoId]), [
      ["heartbeat", 19, "abc123DEF45"], ["web_media_heartbeat", 19, "abc123DEF45"],
    ]);
    document.visibilityState = "hidden";
    events.get("visibilitychange")();
    scans = 0;
    intervals.get(1000)();
    assert.equal(scans, 0);
    // Actual playback events continue reporting while another app is active.
    video.currentTime = 25;
    events.get("timeupdate")();
    assert.equal(scans, 0);
    assert.deepEqual(messages.slice(-2).map(message => message.seconds), [25,25]);
    const replacement = {...video, videoWidth: 1280, currentTime: 42};
    videos.push(replacement);
    events.get("timeupdate")();
    assert.deepEqual(messages.slice(-2).map(message => message.seconds), [42,42]);
    videos.pop();
    events.get("timeupdate")();
    assert.deepEqual(messages.slice(-2).map(message => message.seconds), [25,25]);
    assert.equal(scans, 0);
  } finally {
    for (const [name, descriptor] of originals) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else delete globalThis[name];
    }
  }
});
