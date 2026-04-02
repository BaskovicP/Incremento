"use strict";

const BRIDGE_URL = "http://127.0.0.1:8766/incremento/add-content";
const state = {
  activeTab: null,
  snapshot: null,
  busy: false,
};

const titleInput = document.getElementById("title-input");
const pageUrl = document.getElementById("page-url");
const selectionNote = document.getElementById("selection-note");
const statusEl = document.getElementById("status");
const kindButtons = Array.from(document.querySelectorAll(".kind-btn"));
const openBookmarksBtn = document.getElementById("open-bookmarks");
const copyVideoTimeBtn = document.getElementById("copy-video-time");

function setStatus(text, kind = "") {
  statusEl.textContent = String(text || "");
  statusEl.className = "status";
  if (kind) {
    statusEl.classList.add(`is-${kind}`);
  }
}

function setBusy(nextBusy) {
  state.busy = !!nextBusy;
  for (const btn of kindButtons) {
    btn.disabled = state.busy || !state.activeTab;
  }
  copyVideoTimeBtn.disabled = state.busy;
  if (openBookmarksBtn) {
    openBookmarksBtn.disabled = state.busy;
  }
}

function isHttpUrl(url) {
  return /^https?:\/\//i.test(String(url || ""));
}

function isSupportedVideoUrl(url) {
  try {
    const u = new URL(String(url || ""));
    const host = String(u.hostname || "").toLowerCase();
    if (host === "youtu.be" || host.endsWith(".youtu.be")) {
      return Boolean(u.pathname.split("/").filter(Boolean)[0]);
    }
    if (host === "youtube.com" || host.endsWith(".youtube.com")) {
      if (u.searchParams.get("v")) {
        return true;
      }
      const parts = u.pathname.split("/").filter(Boolean);
      return ["embed", "shorts", "live"].includes(parts[0]) && Boolean(parts[1]);
    }
    if (host === "vimeo.com" || host.endsWith(".vimeo.com")) {
      return /(?:\/video\/|\/)(\d{5,})(?:[/?#]|$)/.test(u.pathname);
    }
  } catch (_err) {
    return false;
  }
  return false;
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs && tabs[0] ? tabs[0] : null;
}

async function captureSnapshot(tabId) {
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

function updatePageUi() {
  const tab = state.activeTab;
  const snapshot = state.snapshot || {};
  const title = String(snapshot.title || tab?.title || "").trim();
  const url = String(snapshot.url || tab?.url || "").trim();

  pageUrl.textContent = url || "No supported page selected.";
  if (!titleInput.value.trim()) {
    titleInput.value = title || url;
  }

  const selectionText = String(snapshot.selectionText || "");
  if (isSupportedVideoUrl(url)) {
    selectionNote.textContent = "Video cards use the current YouTube or Vimeo URL.";
  } else if (selectionText) {
    selectionNote.textContent = `Writing cards will include the current selection (${selectionText.length} chars).`;
  } else {
    selectionNote.textContent = "Writing cards will start with the page title and source link.";
  }

  const enabled = Boolean(tab && isHttpUrl(url));
  for (const btn of kindButtons) {
    const kind = String(btn.dataset.kind || "");
    const needsVideoPage = kind === "video";
    btn.disabled = !enabled || state.busy || (needsVideoPage && !isSupportedVideoUrl(url));
  }
  if (!enabled) {
    setStatus("Open a normal http(s) page first.", "error");
  }
}

async function initialize() {
  setBusy(true);
  try {
    state.activeTab = await getActiveTab();
    if (state.activeTab?.id && isHttpUrl(state.activeTab.url)) {
      state.snapshot = await captureSnapshot(state.activeTab.id);
    }
    updatePageUi();
  } catch (err) {
    setStatus(err?.message || "Failed to inspect the current page.", "error");
  } finally {
    setBusy(false);
    updatePageUi();
  }
}

async function addCurrentPage(kind) {
  if (!state.activeTab) {
    setStatus("No active tab found.", "error");
    return;
  }

  const snapshot = state.snapshot || {};
  const url = String(snapshot.url || state.activeTab.url || "").trim();
  if (!isHttpUrl(url)) {
    setStatus("Only http(s) pages can be sent to Incremento.", "error");
    return;
  }
  if (kind === "video" && !isSupportedVideoUrl(url)) {
    setStatus("Open a YouTube or Vimeo page to add a video card.", "error");
    return;
  }

  const payload = {
    kind,
    url,
    title: titleInput.value.trim() || snapshot.title || state.activeTab.title || url,
    selectedText: String(snapshot.selectionText || ""),
  };
  if (kind === "pdf" && snapshot.html) {
    payload.html = String(snapshot.html);
  }

  if (kind === "pdf" && typeof fetchPdfPayloadForImport === "function" && pdfUrlLooksLikePdf(url)) {
    try {
      const pdfPayload = await fetchPdfPayloadForImport(url);
      payload.pdfBase64 = pdfPayload.pdfBase64;
      payload.pdfFilename = pdfPayload.pdfFilename;
    } catch (_err) {
      // Fall back to addon-side retrieval if browser-side fetch is blocked or unnecessary.
    }
  }

  setBusy(true);
  const label = kind === "video" ? "video" : kind;
  setStatus(`Adding ${label} card...`);

  try {
    const response = await fetch(BRIDGE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data?.ok) {
      throw new Error(String(data?.error || `Request failed (${response.status})`));
    }
    setStatus(`Added ${data.kind} card: ${data.title}`, "success");
  } catch (err) {
    const message = err instanceof TypeError
      ? "Failed to reach Incremento in Anki. Keep Anki open and reload the addon."
      : (err?.message || "Failed to add content.");
    setStatus(message, "error");
  } finally {
    setBusy(false);
    updatePageUi();
  }
}

for (const btn of kindButtons) {
  btn.addEventListener("click", () => {
    void addCurrentPage(btn.dataset.kind || "");
  });
}

copyVideoTimeBtn.addEventListener("click", () => {
  setBusy(true);
  setStatus("Copying last video time...");
  chrome.runtime.sendMessage({ type: "COPY_LATEST_VIDEO_TIME", showFeedback: true }, (resp) => {
    const err = chrome.runtime.lastError;
    if (err) {
      setStatus(err.message || "Failed to copy video time.", "error");
    } else if (resp?.ok) {
      setStatus("Copied last video time.", "success");
    } else {
      setStatus("No stored video time yet.", "error");
    }
    setBusy(false);
    updatePageUi();
  });
});

if (openBookmarksBtn) {
  openBookmarksBtn.addEventListener("click", async () => {
    try {
      await chrome.tabs.create({
        url: chrome.runtime.getURL("bookmarks.html"),
      });
      window.close();
    } catch (err) {
      setStatus(err?.message || "Failed to open bookmark importer.", "error");
    }
  });
}

void initialize();
