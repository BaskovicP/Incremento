export async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs && tabs[0] ? tabs[0] : null;
}

export async function captureSnapshot(tabId) {
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const html = document.documentElement?.outerHTML || "";
        const selectionText = (window.getSelection?.().toString() || "").trim();
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

export async function loadBookmarksTree() {
  const tree = await chrome.bookmarks.getTree();
  return Array.isArray(tree) ? tree : [];
}
