"use strict";

const TAB_STATE = new Map();
const STORAGE_KEY = "incremento_last_video_time";
const OFFSCREEN_PATH = "offscreen.html";
const ANKICONNECT_URL = "http://127.0.0.1:8765";
const ANKICONNECT_VERSION = 6;
const INCREMENTO_NOTE_TYPE = "Incremento Video";

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

function htmlDecodeUrl(raw) {
  return String(raw || "").replaceAll("&amp;", "&").trim();
}

function setTimestampInVideoUrl(rawUrl, provider, videoId, seconds) {
  const sec = Math.max(0, Math.floor(Number(seconds) || 0));
  const decoded = htmlDecodeUrl(rawUrl);

  if (provider === "youtube") {
    let u = null;
    try {
      u = new URL(decoded);
    } catch (_err) {
      u = new URL(`https://www.youtube.com/watch?v=${videoId}`);
    }
    if (!u.searchParams.get("v")) {
      u.searchParams.set("v", videoId);
    }
    u.searchParams.delete("inc_card_id");
    u.searchParams.delete("start");
    u.searchParams.delete("time");
    if (sec > 0) {
      u.searchParams.set("t", `${sec}s`);
    } else {
      u.searchParams.delete("t");
    }
    u.hash = "";
    return u.toString();
  }

  if (provider === "vimeo") {
    let source = null;
    try {
      source = new URL(decoded);
    } catch (_err) {
      source = new URL(`https://player.vimeo.com/video/${videoId}`);
    }
    const out = new URL(`https://player.vimeo.com/video/${videoId}`);
    for (const [k, v] of source.searchParams.entries()) {
      const low = String(k || "").toLowerCase();
      if (low === "t" || low === "start" || low === "time" || low === "inc_card_id") {
        continue;
      }
      out.searchParams.append(k, v);
    }
    if (sec > 0) {
      out.hash = `t=${sec}s`;
    }
    return out.toString();
  }

  return decoded;
}

async function callAnki(action, params = {}) {
  const payload = {
    action,
    version: ANKICONNECT_VERSION,
    params,
  };
  const resp = await fetch(ANKICONNECT_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await resp.json();
  if (data?.error) {
    throw new Error(String(data.error));
  }
  return data?.result;
}

async function syncTimeToAnki(state) {
  const provider = String(state?.provider || "");
  const videoId = String(state?.videoId || "");
  const cardId = Math.max(0, Math.floor(Number(state?.cardId) || 0));
  const seconds = Math.max(0, Math.floor(Number(state?.seconds) || 0));
  if (!provider || !videoId || seconds <= 0) {
    return { ok: false, updatedNotes: 0 };
  }

  try {
    let noteIds = [];
    if (cardId > 0) {
      try {
        const byCard = await callAnki("findNotes", { query: `cid:${cardId}` });
        if (Array.isArray(byCard) && byCard.length > 0) {
          noteIds = byCard;
        }
      } catch (_err) {
        noteIds = [];
      }
    }
    if (noteIds.length === 0) {
      const query = `note:"${INCREMENTO_NOTE_TYPE}" YouTube_URL:*${videoId}*`;
      const byVideo = await callAnki("findNotes", { query });
      if (Array.isArray(byVideo)) {
        noteIds = byVideo;
      }
    }
    if (!Array.isArray(noteIds) || noteIds.length === 0) {
      return { ok: true, updatedNotes: 0 };
    }

    const notes = await callAnki("notesInfo", { notes: noteIds });
    if (!Array.isArray(notes) || notes.length === 0) {
      return { ok: true, updatedNotes: 0 };
    }

    const updates = [];
    for (const note of notes) {
      const noteId = Number(note?.noteId);
      const oldUrl = String(note?.fields?.YouTube_URL?.value || "");
      if (!noteId || !oldUrl) {
        continue;
      }
      const newUrl = setTimestampInVideoUrl(oldUrl, provider, videoId, seconds);
      if (!newUrl || newUrl === oldUrl) {
        continue;
      }
      updates.push(
        callAnki("updateNoteFields", {
          note: {
            id: noteId,
            fields: { YouTube_URL: newUrl },
          },
        })
      );
    }

    if (updates.length > 0) {
      await Promise.all(updates);
    }
    return { ok: true, updatedNotes: updates.length };
  } catch (_err) {
    return { ok: false, updatedNotes: 0 };
  }
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

async function _copyViaServiceWorkerClipboard(text) {
  const nav = globalThis?.navigator;
  if (!nav?.clipboard?.writeText) {
    return false;
  }
  try {
    await nav.clipboard.writeText(String(text ?? ""));
    return true;
  } catch (_err) {
    return false;
  }
}

async function _copyViaOffscreen(text) {
  const ok = await ensureOffscreen();
  if (!ok) {
    return false;
  }
  for (let i = 0; i < 3; i += 1) {
    try {
      const resp = await chrome.runtime.sendMessage({
        type: "offscreen-copy",
        text: String(text ?? ""),
      });
      if (resp && resp.ok) {
        return true;
      }
    } catch (_err) {
      // retry
    }
    await new Promise((resolve) => setTimeout(resolve, 80));
  }
  return false;
}

async function _copyViaActiveTabScript(text) {
  if (!chrome.scripting?.executeScript) {
    return false;
  }
  const tab = await getActiveTab();
  if (!tab?.id) {
    return false;
  }
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: async (value) => {
        const txt = String(value ?? "");
        try {
          if (navigator?.clipboard?.writeText) {
            await navigator.clipboard.writeText(txt);
            return true;
          }
        } catch (_err) {
          // fallback below
        }
        try {
          const ta = document.createElement("textarea");
          ta.value = txt;
          ta.setAttribute("readonly", "true");
          ta.style.position = "fixed";
          ta.style.opacity = "0";
          ta.style.left = "-9999px";
          document.body.appendChild(ta);
          ta.focus();
          ta.select();
          const ok = document.execCommand("copy");
          ta.remove();
          return !!ok;
        } catch (_err) {
          return false;
        }
      },
      args: [String(text ?? "")],
    });
    return !!(Array.isArray(results) && results[0] && results[0].result);
  } catch (_err) {
    return false;
  }
}

async function copyText(text) {
  if (await _copyViaServiceWorkerClipboard(text)) {
    return true;
  }
  if (await _copyViaOffscreen(text)) {
    return true;
  }
  if (await _copyViaActiveTabScript(text)) {
    return true;
  }
  return false;
}

async function showToastInTab(tabId, text) {
  if (typeof tabId !== "number") {
    return;
  }
  try {
    await chrome.tabs.sendMessage(tabId, { type: "SHOW_TOAST", text: String(text || "") });
  } catch (_err) {
    // tab may be gone
  }
}

async function persistPayload(payload) {
  try {
    await chrome.storage.local.set({ [STORAGE_KEY]: payload });
  } catch (_err) {
    // noop
  }
}

async function persistAndCopy(state, options = {}) {
  const copyToClipboard = options?.copyToClipboard !== false;
  if (!state || Number(state.seconds) < 0) {
    return { ok: false };
  }
  const seconds = Math.max(0, Math.floor(Number(state.seconds) || 0));
  const payload = {
    provider: state.provider || "",
    videoId: state.videoId || "",
    cardId: Math.max(0, Math.floor(Number(state.cardId) || 0)),
    seconds,
    timeText: formatTime(seconds),
    url: state.url || "",
    title: state.title || "",
    updatedAt: Date.now(),
    ankiUpdatedNotes: 0,
    ankiSyncedAt: 0,
  };
  if (seconds > 0) {
    const sync = await syncTimeToAnki(state);
    if (sync.ok) {
      payload.ankiUpdatedNotes = Number(sync.updatedNotes) || 0;
      payload.ankiSyncedAt = Date.now();
    }
  }
  await persistPayload(payload);
  if (seconds <= 0) {
    return { ok: false, payload };
  }
  if (!copyToClipboard) {
    return { ok: true, payload };
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
      const msg = copied ? `Copied video time: ${text}` : `Failed to copy video time (${text})`;
      await showToastInTab(tab.id, msg);
    }
  }
  return copied;
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || !msg.type) {
    return false;
  }

  if (msg.type === "heartbeat") {
    const tabId = sender?.tab?.id;
    if (typeof tabId !== "number") {
      sendResponse?.({ ok: false });
      return false;
    }
    const state = {
      provider: typeof msg.provider === "string" ? msg.provider : "",
      videoId: typeof msg.videoId === "string" ? msg.videoId : "",
      cardId: Math.max(0, Math.floor(Number(msg.cardId) || 0)),
      seconds: Number(msg.seconds) || 0,
      flush: !!msg.flush,
      title: typeof msg.title === "string" ? msg.title : "",
      url: typeof msg.url === "string" ? msg.url : "",
      updatedAt: Date.now(),
    };
    TAB_STATE.set(tabId, state);
    updateActionState(state);
    if (state.flush) {
      void persistAndCopy(state, { copyToClipboard: false });
    }
    sendResponse?.({ ok: true });
    return false;
  }

  if (msg.type === "COPY_LATEST_VIDEO_TIME") {
    void (async () => {
      const copied = await copyLatestStoredTime(Boolean(msg.showFeedback));
      sendResponse?.({ ok: copied });
    })();
    return true;
  }

  return false;
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
