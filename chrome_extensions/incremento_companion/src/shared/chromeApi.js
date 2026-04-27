export async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs && tabs[0] ? tabs[0] : null;
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
  try {
    const fromContentScript = await new Promise((resolve) => {
      try {
        chrome.tabs.sendMessage(tabId, { type: "GET_PAGE_CONTEXT" }, (response) => {
          const error = chrome.runtime.lastError;
          if (error || !response?.ok) {
            resolve(null);
            return;
          }
          resolve(response);
        });
      } catch (_err) {
        resolve(null);
      }
    });
    if (fromContentScript) {
      return fromContentScript;
    }
  } catch (_err) {
    // fall through to direct executeScript snapshot
  }
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const html = document.documentElement?.outerHTML || "";
        const selectionText = (
          (window.getSelection?.().toString() || "").trim()
          || String(globalThis.__incrementoLastSelectedText || "").trim()
        );
        return {
          html,
          selectionText,
          title: document.title || "",
          url: window.location.href || "",
        };
      },
    });
    return results && results[0] ? results[0].result : null;
  } catch (_err) {
    return null;
  }
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

  return new Promise((resolve, reject) => {
    try {
      chrome.tabs.sendMessage(Number(tabId), { type: "GET_CURRENT_MEDIA_CONTEXT" }, (response) => {
        const error = chrome.runtime.lastError;
        if (error) {
          reject(new Error(injectionError || error.message || "Failed to inspect the current page media."));
          return;
        }
        if (!response?.ok && injectionError && !response?.error) {
          reject(new Error(injectionError));
          return;
        }
        resolve(response || null);
      });
    } catch (error) {
      reject(new Error(String(error?.message || injectionError || "Failed to inspect the current page media.")));
    }
  });
}

export async function updateBrowserMediaRefBadgeForTab(tabId, reference) {
  if (!Number.isFinite(Number(tabId)) || Number(tabId) <= 0) {
    return false;
  }
  try {
    await chrome.tabs.sendMessage(Number(tabId), {
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
