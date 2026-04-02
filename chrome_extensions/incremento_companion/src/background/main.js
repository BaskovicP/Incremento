"use strict";

const TAB_STATE = new Map();
const WEB_TRACK_TAB_STATE = new Map();
const STORAGE_KEY = "incremento_last_video_time";
const WEB_TRACK_STORAGE_KEY = "incremento_tracked_web_tabs";
const OFFSCREEN_PATH = "offscreen.html";
const ANKICONNECT_URL = "http://127.0.0.1:8765";
const ANKICONNECT_VERSION = 6;
const INCREMENTO_NOTE_TYPE = "Incremento Video";
const WEB_TRACK_BRIDGE_URL = "http://127.0.0.1:8766/incremento/update-web-card";
const INC_CARD_ID_PARAM = "inc_card_id";
const INC_TRACK_WEB_PARAM = "inc_track_web";

function isHttpUrl(rawUrl) {
  return /^https?:\/\//i.test(String(rawUrl || ""));
}

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

function stripIncrementoTrackingParams(rawUrl) {
  const decoded = htmlDecodeUrl(rawUrl);
  try {
    const u = new URL(decoded);
    u.searchParams.delete(INC_CARD_ID_PARAM);
    u.searchParams.delete(INC_TRACK_WEB_PARAM);
    return u.toString();
  } catch (_err) {
    return decoded;
  }
}

function parseTrackedWebRegistration(rawUrl) {
  const decoded = htmlDecodeUrl(rawUrl);
  try {
    const u = new URL(decoded);
    const trackRaw = String(u.searchParams.get(INC_TRACK_WEB_PARAM) || "").trim().toLowerCase();
    const trackEnabled = trackRaw === "1" || trackRaw === "true" || trackRaw === "yes" || trackRaw === "on";
    const cid = Number(u.searchParams.get(INC_CARD_ID_PARAM) || 0);
    return {
      trackEnabled,
      cardId: Number.isFinite(cid) && cid > 0 ? Math.floor(cid) : 0,
      cleanUrl: stripIncrementoTrackingParams(decoded),
    };
  } catch (_err) {
    return {
      trackEnabled: false,
      cardId: 0,
      cleanUrl: stripIncrementoTrackingParams(decoded),
    };
  }
}

function extractTrackedVideoCardId(rawUrl) {
  try {
    const decoded = htmlDecodeUrl(rawUrl);
    const u = new URL(decoded);
    const host = String(u.hostname || "").toLowerCase();
    const isVideoHost =
      host === "youtu.be"
      || host.endsWith(".youtu.be")
      || host === "youtube.com"
      || host.endsWith(".youtube.com")
      || host === "vimeo.com"
      || host.endsWith(".vimeo.com");
    if (!isVideoHost) {
      return 0;
    }
    const cid = Number(u.searchParams.get(INC_CARD_ID_PARAM) || 0);
    return Number.isFinite(cid) && cid > 0 ? Math.floor(cid) : 0;
  } catch (_err) {
    return 0;
  }
}

async function loadTrackedWebState(tabId) {
  if (typeof tabId !== "number") {
    return null;
  }
  const inMemory = WEB_TRACK_TAB_STATE.get(tabId);
  if (inMemory) {
    return inMemory;
  }
  try {
    const data = await chrome.storage.session.get(WEB_TRACK_STORAGE_KEY);
    const all = data?.[WEB_TRACK_STORAGE_KEY];
    const saved = all ? all[String(tabId)] : null;
    if (saved && Number(saved.cardId) > 0) {
      const state = {
        cardId: Math.max(0, Math.floor(Number(saved.cardId) || 0)),
        lastUrl: String(saved.lastUrl || ""),
      };
      WEB_TRACK_TAB_STATE.set(tabId, state);
      return state;
    }
  } catch (_err) {
    // noop
  }
  return null;
}

async function saveTrackedWebState(tabId, state) {
  if (typeof tabId !== "number" || !state || Number(state.cardId) <= 0) {
    return;
  }
  WEB_TRACK_TAB_STATE.set(tabId, state);
  try {
    const data = await chrome.storage.session.get(WEB_TRACK_STORAGE_KEY);
    const all = data?.[WEB_TRACK_STORAGE_KEY] || {};
    all[String(tabId)] = {
      cardId: Math.max(0, Math.floor(Number(state.cardId) || 0)),
      lastUrl: String(state.lastUrl || ""),
    };
    await chrome.storage.session.set({ [WEB_TRACK_STORAGE_KEY]: all });
  } catch (_err) {
    // noop
  }
}

async function clearTrackedWebState(tabId) {
  if (typeof tabId !== "number") {
    return;
  }
  WEB_TRACK_TAB_STATE.delete(tabId);
  try {
    const data = await chrome.storage.session.get(WEB_TRACK_STORAGE_KEY);
    const all = data?.[WEB_TRACK_STORAGE_KEY];
    if (!all || typeof all !== "object") {
      return;
    }
    delete all[String(tabId)];
    await chrome.storage.session.set({ [WEB_TRACK_STORAGE_KEY]: all });
  } catch (_err) {
    // noop
  }
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

async function updateTrackedWebCard(cardId, url, title = "") {
  const cid = Math.max(0, Math.floor(Number(cardId) || 0));
  const cleanUrl = stripIncrementoTrackingParams(url);
  if (cid <= 0 || !isHttpUrl(cleanUrl)) {
    return { ok: false };
  }
  try {
    const response = await fetch(WEB_TRACK_BRIDGE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cardId: cid,
        url: cleanUrl,
        title: String(title || ""),
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data?.ok) {
      throw new Error(String(data?.error || `Request failed (${response.status})`));
    }
    return { ok: true, data };
  } catch (_err) {
    return { ok: false };
  }
}

async function maybeSyncTrackedWebTab(tabId, rawUrl, title = "") {
  if (typeof tabId !== "number") {
    return;
  }

  const registration = parseTrackedWebRegistration(rawUrl);
  let state = await loadTrackedWebState(tabId);
  if (registration.trackEnabled && registration.cardId > 0) {
    state = {
      cardId: registration.cardId,
      lastUrl: "",
    };
    await saveTrackedWebState(tabId, state);
  }
  if (!state) {
    return;
  }

  const cleanUrl = registration.cleanUrl || stripIncrementoTrackingParams(rawUrl);
  if (!isHttpUrl(cleanUrl) || state.lastUrl === cleanUrl) {
    return;
  }

  const synced = await updateTrackedWebCard(state.cardId, cleanUrl, title);
  if (!synced.ok) {
    return;
  }
  state.lastUrl = cleanUrl;
  await saveTrackedWebState(tabId, state);
}

async function getTrackingStatusForTab(tabId, rawUrl) {
  const videoCardId = extractTrackedVideoCardId(rawUrl);
  if (videoCardId > 0) {
    return { tracked: true, mode: "video", cardId: videoCardId };
  }

  const webState = await loadTrackedWebState(tabId);
  if (webState && Number(webState.cardId) > 0) {
    return {
      tracked: true,
      mode: "web",
      cardId: Math.max(0, Math.floor(Number(webState.cardId) || 0)),
    };
  }

  return { tracked: false, mode: "", cardId: 0 };
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

  if (msg.type === "GET_TRACKING_STATUS") {
    void (async () => {
      const tabId = sender?.tab?.id;
      if (typeof tabId !== "number") {
        sendResponse?.({ tracked: false, mode: "" });
        return;
      }
      const status = await getTrackingStatusForTab(tabId, String(msg.url || ""));
      sendResponse?.(status);
    })();
    return true;
  }

  return false;
});

chrome.tabs.onRemoved.addListener((tabId) => {
  const state = TAB_STATE.get(tabId);
  TAB_STATE.delete(tabId);
  void clearTrackedWebState(tabId);
  if (!state || !isFresh(state)) {
    return;
  }
  void persistAndCopy(state);
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  const nextUrl =
    (typeof changeInfo?.url === "string" && changeInfo.url)
    || (changeInfo?.status === "complete" ? String(tab?.url || "") : "");
  if (!nextUrl) {
    return;
  }
  void maybeSyncTrackedWebTab(tabId, nextUrl, String(tab?.title || ""));
});

if (chrome.webNavigation?.onCommitted) {
  chrome.webNavigation.onCommitted.addListener((details) => {
    if (details?.frameId !== 0) {
      return;
    }
    void maybeSyncTrackedWebTab(
      Number(details.tabId),
      String(details.url || ""),
      "",
    );
  });
}

if (chrome.webNavigation?.onHistoryStateUpdated) {
  chrome.webNavigation.onHistoryStateUpdated.addListener((details) => {
    if (details?.frameId !== 0) {
      return;
    }
    void maybeSyncTrackedWebTab(
      Number(details.tabId),
      String(details.url || ""),
      "",
    );
  });
}

if (chrome.webNavigation?.onReferenceFragmentUpdated) {
  chrome.webNavigation.onReferenceFragmentUpdated.addListener((details) => {
    if (details?.frameId !== 0) {
      return;
    }
    void maybeSyncTrackedWebTab(
      Number(details.tabId),
      String(details.url || ""),
      "",
    );
  });
}

chrome.action.onClicked.addListener(() => {
  void copyLatestStoredTime(true);
});

chrome.commands.onCommand.addListener((command) => {
  if (command !== "copy-last-video-time") {
    return;
  }
  void copyLatestStoredTime(true);
});
