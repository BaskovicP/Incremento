export async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs && tabs[0] ? tabs[0] : null;
}

export async function captureSnapshot(tabId) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["dist/content.js"],
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

export async function triggerBrowserCaptureForTab(tabId, mode) {
  if (!Number.isFinite(Number(tabId)) || Number(tabId) <= 0) {
    throw new Error("No active tab found for browser capture.");
  }

  let injectionError = "";
  try {
    await chrome.scripting.executeScript({
      target: { tabId: Number(tabId) },
      files: ["dist/content.js"],
    });
  } catch (error) {
    injectionError = String(
      error?.message || "Chrome did not allow script injection on this tab."
    );
  }

  const results = await chrome.scripting.executeScript({
    target: { tabId: Number(tabId) },
    func: (captureMode) => {
      const trigger = globalThis.__incrementoTriggerBrowserCapture;
      if (typeof trigger !== "function") {
        return { ok: false, error: "Browser capture script is not available on this page." };
      }
      try {
        return trigger(captureMode);
      } catch (error) {
        return { ok: false, error: String(error?.message || "Failed to trigger browser capture.") };
      }
    },
    args: [mode],
  });
  const result = results?.[0]?.result || { ok: false };
  if (!result.ok && injectionError && !result.error) {
    return { ok: false, error: injectionError };
  }
  if (!result.ok && injectionError && result.error === "Browser capture script is not available on this page.") {
    return { ok: false, error: injectionError };
  }
  return result;
}

export async function loadBookmarksTree() {
  const tree = await chrome.bookmarks.getTree();
  return Array.isArray(tree) ? tree : [];
}
