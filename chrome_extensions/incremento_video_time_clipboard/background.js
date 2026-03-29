"use strict";

const TAB_STATE = new Map();
const STORAGE_KEY = "incremento_last_video_time";
const OFFSCREEN_PATH = "offscreen.html";

function formatTime(totalSeconds) {
  const t = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const s = t % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${m}:${String(s).padStart(2, "0")}`;
}

function isFresh(state, maxAgeMs = 60_000) {
  if (!state || typeof state.updatedAt !== "number") {
    return false;
  }
  return Date.now() - state.updatedAt <= maxAgeMs;
}

async function getActiveTab() {
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    return tabs && tabs[0] ? tabs[0] : null;
  } catch (_err) {
    return null;
  }
}

async function ensureOffscreen() {
  if (!chrome.offscreen?.createDocument) {
    return false;
  }
  try {
    if (chrome.runtime.getContexts) {
      const contexts = await chrome.runtime.getContexts({
        contextTypes: ["OFFSCREEN_DOCUMENT"],
        documentUrls: [chrome.runtime.getURL(OFFSCREEN_PATH)],
      });
      if (Array.isArray(contexts) && contexts.length > 0) {
        return true;
      }
    }
    await chrome.offscreen.createDocument({
      url: OFFSCREEN_PATH,
      reasons: [chrome.offscreen.Reason.CLIPBOARD],
      justification: "Copy latest video stop time for pasting into Anki.",
    });
    return true;
  } catch (_err) {
    return false;
  }
}

async function copyText(text) {
  const ok = await ensureOffscreen();
  if (!ok) {
    return false;
  }
  try {
    const resp = await chrome.runtime.sendMessage({
      type: "offscreen-copy",
      text: String(text ?? ""),
    });
    return !!(resp && resp.ok);
  } catch (_err) {
    return false;
  }
}

async function showToastInTab(tabId, text) {
  if (typeof tabId !== "number") {
    return;
  }
  try {
    await chrome.tabs.sendMessage(tabId, { type: "SHOW_TOAST", text: String(text || "") });
  } catch (_err) {
    // The tab may be gone or script unavailable.
  }
}

async function persistPayload(payload) {
  try {
    await chrome.storage.local.set({ [STORAGE_KEY]: payload });
  } catch (_err) {
    // noop
  }
}

async function persistAndCopy(state) {
  if (!state || Number(state.seconds) < 0) {
    return { ok: false };
  }
  const seconds = Math.max(0, Math.floor(Number(state.seconds) || 0));
  const payload = {
    provider: state.provider || "",
    videoId: state.videoId || "",
    seconds,
    timeText: formatTime(seconds),
    url: state.url || "",
    title: state.title || "",
    updatedAt: Date.now(),
  };
  await persistPayload(payload);
  if (seconds <= 0) {
    return { ok: false, payload };
  }
  const copied = await copyText(payload.timeText);
  return { ok: copied, payload };
}

function updateActionState(state) {
  if (!state) {
    return;
  }
  const seconds = Math.max(0, Math.floor(Number(state.seconds) || 0));
  const provider = state.provider || "video";
  const timeText = formatTime(seconds);
  void chrome.action.setBadgeBackgroundColor({ color: "#0d6efd" });
  void chrome.action.setBadgeText({ text: seconds > 0 ? "▶" : "" });
  void chrome.action.setTitle({ title: `Incremento (${provider}) ${timeText}` });
}

async function copyLatestStoredTime(showFeedback) {
  let payload = null;
  try {
    const data = await chrome.storage.local.get(STORAGE_KEY);
    payload = data?.[STORAGE_KEY] || null;
  } catch (_err) {
    payload = null;
  }
  if (!payload || Number(payload.seconds) < 0) {
    if (showFeedback) {
      const tab = await getActiveTab();
      if (tab?.id) {
        await showToastInTab(tab.id, "No stored video time yet.");
      }
    }
    return false;
  }
  const text = payload.timeText || formatTime(payload.seconds);
  const copied = await copyText(text);
  if (showFeedback) {
    const tab = await getActiveTab();
    if (tab?.id) {
      const msg = copied
        ? `Copied video time: ${text}`
        : `Failed to copy video time (${text})`;
      await showToastInTab(tab.id, msg);
    }
  }
  return copied;
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || msg.type !== "heartbeat") {
    return;
  }
  const tabId = sender?.tab?.id;
  if (typeof tabId !== "number") {
    sendResponse?.({ ok: false });
    return;
  }

  const state = {
    provider: typeof msg.provider === "string" ? msg.provider : "",
    videoId: typeof msg.videoId === "string" ? msg.videoId : "",
    seconds: Number(msg.seconds) || 0,
    title: typeof msg.title === "string" ? msg.title : "",
    url: typeof msg.url === "string" ? msg.url : "",
    updatedAt: Date.now(),
  };
  TAB_STATE.set(tabId, state);
  updateActionState(state);
  sendResponse?.({ ok: true });
});

chrome.tabs.onRemoved.addListener((tabId) => {
  const state = TAB_STATE.get(tabId);
  TAB_STATE.delete(tabId);
  if (!state || !isFresh(state)) {
    return;
  }
  void persistAndCopy(state);
});

chrome.action.onClicked.addListener(() => {
  void copyLatestStoredTime(true);
});

chrome.commands.onCommand.addListener((command) => {
  if (command !== "copy-last-video-time") {
    return;
  }
  void copyLatestStoredTime(true);
});
