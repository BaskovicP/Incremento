import {
  MAX_BROWSER_CAPTURE_HTML_CHARS,
  MAX_BROWSER_CAPTURE_SELECTED_TEXT_CHARS,
} from "./browserCaptureModel.js";

export async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs && tabs[0] ? tabs[0] : null;
}

const MAIN_FRAME_MESSAGE_OPTIONS = { frameId: 0 };

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isReceivingEndError(error) {
  return /Receiving end does not exist/i.test(String(error?.message || error || ""));
}

function sendMessageToMainFrame(tabId, message) {
  return new Promise((resolve, reject) => {
    try {
      chrome.tabs.sendMessage(
        Number(tabId),
        message,
        MAIN_FRAME_MESSAGE_OPTIONS,
        (response) => {
          const error = chrome.runtime.lastError;
          if (error) {
            reject(new Error(error.message || "Failed to inspect the current tab."));
            return;
          }
          resolve(response || null);
        }
      );
    } catch (error) {
      reject(error);
    }
  });
}

async function sendMessageToMainFrameWithRetry(tabId, message, attempts = 3) {
  let lastError = null;
  const totalAttempts = Math.max(1, Number(attempts) || 1);
  for (let index = 0; index < totalAttempts; index += 1) {
    try {
      return await sendMessageToMainFrame(tabId, message);
    } catch (error) {
      lastError = error;
      if (!isReceivingEndError(error) || index === totalAttempts - 1) {
        throw error;
      }
      await sleep(80);
    }
  }
  throw lastError || new Error("Failed to inspect the current tab.");
}

export async function captureSnapshot(tabId) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content-loader.js"],
    });
  } catch (_err) {
    // Ignore injection failures here; the direct page read below may still succeed.
  }
  let fromContentScript = null;
  try {
    fromContentScript = await sendMessageToMainFrameWithRetry(
      tabId,
      { type: "GET_PAGE_CONTEXT" },
      4
    );
  } catch (error) {
    if (!isReceivingEndError(error)) {
      throw error;
    }
  }
  if (fromContentScript?.error) {
    throw new Error(String(fromContentScript.error));
  }
  if (fromContentScript) {
    return fromContentScript;
  }
  let results;
  try {
    results = await chrome.scripting.executeScript({
      target: { tabId },
      func: (maxHtmlChars, maxSelectedTextChars) => {
        const html = document.documentElement?.outerHTML || "";
        const selectionText = (
          (window.getSelection?.().toString() || "").trim()
          || String(globalThis.__incrementoLastSelectedText || "").trim()
        );
        if (html.length > maxHtmlChars) {
          return {
            ok: false,
            error: `Page HTML is too large. Maximum is ${maxHtmlChars} characters.`,
          };
        }
        if (selectionText.length > maxSelectedTextChars) {
          return {
            ok: false,
            error: `Selected text is too large. Maximum is ${maxSelectedTextChars} characters.`,
          };
        }
        return {
          ok: true,
          html,
          selectionText,
          title: document.title || "",
          url: window.location.href || "",
        };
      },
      args: [MAX_BROWSER_CAPTURE_HTML_CHARS, MAX_BROWSER_CAPTURE_SELECTED_TEXT_CHARS],
    });
  } catch (_err) {
    return null;
  }
  const result = results && results[0] ? results[0].result : null;
  if (result?.error) {
    throw new Error(String(result.error));
  }
  return result;
}

export function copyLatestVideoTime() {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type: "COPY_LATEST_VIDEO_TIME", showFeedback: true }, (response) => {
      const error = chrome.runtime.lastError;
      if (error) {
        reject(new Error(error.message || "Failed to copy video time."));
        return;
      }
      resolve(response || null);
    });
  });
}

export function getLinkedCardContextForTab(tabId, url = "") {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(
      {
        type: "GET_LINKED_CARD_CONTEXT",
        tabId: Number(tabId),
        url: String(url || ""),
      },
      (response) => {
        const error = chrome.runtime.lastError;
        if (error) {
          reject(new Error(error.message || "Failed to load linked card context."));
          return;
        }
        resolve(response || null);
      }
    );
  });
}

export function registerWebCardTrackingForTab(tabId, cardId, url = "") {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(
      {
        type: "REGISTER_WEB_CARD_TRACKING",
        tabId: Number(tabId),
        cardId: Number(cardId),
        url: String(url || ""),
      },
      (response) => {
        const error = chrome.runtime.lastError;
        if (error) {
          reject(new Error(error.message || "Failed to link the web card tab."));
          return;
        }
        resolve(response || null);
      }
    );
  });
}

export async function getCurrentMediaContextForTab(tabId) {
  if (!Number.isFinite(Number(tabId)) || Number(tabId) <= 0) {
    throw new Error("No active tab found for media detection.");
  }

  let injectionError = "";
  try {
    await chrome.scripting.executeScript({
      target: { tabId: Number(tabId) },
      files: ["content-loader.js"],
    });
  } catch (error) {
    injectionError = String(
      error?.message || "Chrome did not allow script injection on this tab."
    );
  }

  try {
    const response = await sendMessageToMainFrameWithRetry(
      Number(tabId),
      { type: "GET_CURRENT_MEDIA_CONTEXT" },
      4
    );
    if (!response?.ok && injectionError && !response?.error) {
      throw new Error(injectionError);
    }
    return response || null;
  } catch (error) {
    throw new Error(String(error?.message || injectionError || "Failed to inspect the current page media."));
  }
}

export async function updateBrowserMediaRefBadgeForTab(tabId, reference) {
  if (!Number.isFinite(Number(tabId)) || Number(tabId) <= 0) {
    return false;
  }
  try {
    await sendMessageToMainFrame(Number(tabId), {
      type: "UPDATE_BROWSER_MEDIA_REF_BADGE",
      reference: reference || null,
    });
    return true;
  } catch (_err) {
    return false;
  }
}

export async function openBookmarksPage() {
  await chrome.tabs.create({
    url: chrome.runtime.getURL("bookmarks.html"),
  });
}

export async function openExtensionShortcutsPage() {
  await chrome.tabs.create({
    url: "chrome://extensions/shortcuts",
  });
}

export async function getCommandShortcuts() {
  if (!chrome.commands?.getAll) {
    return [];
  }
  return chrome.commands.getAll();
}

export async function getLocalExtensionSetting(key, fallbackValue = null) {
  const data = await chrome.storage.local.get(key);
  return data && Object.prototype.hasOwnProperty.call(data, key) ? data[key] : fallbackValue;
}

export async function setLocalExtensionSetting(key, value) {
  await chrome.storage.local.set({ [key]: value });
}

export async function triggerBrowserCaptureForTab(tabId, mode) {
  if (!Number.isFinite(Number(tabId)) || Number(tabId) <= 0) {
    throw new Error("No active tab found for browser capture.");
  }

  const normalizedTabId = Number(tabId);

  let injectionError = "";
  const injectContentScript = async () => {
    try {
      await chrome.scripting.executeScript({
        target: { tabId: normalizedTabId, allFrames: true },
        files: ["content-loader.js"],
      });
      return "";
    } catch (error) {
      return String(
        error?.message || "Chrome did not allow script injection on this tab."
      );
    }
  };
  const sendTriggerMessage = () => new Promise((resolve) => {
    try {
      chrome.tabs.sendMessage(
        normalizedTabId,
        { type: "TRIGGER_BROWSER_CAPTURE", mode },
        (response) => {
          const error = chrome.runtime.lastError;
          if (error) {
            resolve({ ok: false, error: error.message || "Failed to trigger browser capture." });
            return;
          }
          resolve(response || { ok: false });
        }
      );
    } catch (error) {
      resolve({
        ok: false,
        error: String(error?.message || "Failed to trigger browser capture."),
      });
    }
  });

  injectionError = await injectContentScript();
  let result = await sendTriggerMessage();
  if (!result?.ok && /Receiving end does not exist/i.test(String(result?.error || ""))) {
    injectionError = await injectContentScript() || injectionError;
    result = await sendTriggerMessage();
  }

  if (!result?.ok && injectionError && !result?.error) {
    return { ok: false, error: injectionError };
  }
  if (!result?.ok && /Receiving end does not exist/i.test(String(result?.error || "")) && injectionError) {
    return { ok: false, error: injectionError };
  }
  return result;
}

export async function loadBookmarksTree() {
  const tree = await chrome.bookmarks.getTree();
  return Array.isArray(tree) ? tree : [];
}
