"use strict";

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || msg.type !== "offscreen-copy") {
    return;
  }
  const text = String(msg.text ?? "");
  (async () => {
    try {
      await navigator.clipboard.writeText(text);
      sendResponse({ ok: true });
    } catch (_err) {
      sendResponse({ ok: false });
    }
  })();
  return true;
});
