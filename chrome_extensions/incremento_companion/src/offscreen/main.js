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
import { initializeLanguage, localizeDocument, subscribeLanguage, watchLanguageStorage } from "../shared/i18n.js";

watchLanguageStorage();
void initializeLanguage().then(() => localizeDocument("offscreen_title"));
subscribeLanguage(() => localizeDocument("offscreen_title"));
