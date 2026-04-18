import { importIntoIncremento, loadBrowserMediaRef } from "../shared/bridge.js";
import { getPdfPayloadForUrl } from "../shared/pdfFetch.js";
import { isSupportedVideoUrl } from "../shared/url.js";
import {
  buildAutomaticWritingTitle,
  buildPreferredWritingFilename,
} from "../shared/writingTitle.js";

const TAB_STATE = new Map();
const WEB_TRACK_TAB_STATE = new Map();
const WEB_MEDIA_SYNC_STATE = new Map();
const LINKED_CARD_TAB_STATE = new Map();
const STORAGE_KEY = "incremento_last_video_time";
const WEB_TRACK_STORAGE_KEY = "incremento_tracked_web_tabs";
const LINKED_CARD_STORAGE_KEY = "incremento_linked_card_tabs";
const OFFSCREEN_PATH = "offscreen.html";
const ANKICONNECT_URL = "http://127.0.0.1:8765";
const ANKICONNECT_VERSION = 6;
const INCREMENTO_NOTE_TYPE = "Incremento Video";
const WEB_TRACK_BRIDGE_URL = "http://127.0.0.1:8766/incremento/update-web-card";
const WEB_TRACK_MEDIA_BRIDGE_URL = "http://127.0.0.1:8766/incremento/update-web-card-media";
const INC_CARD_ID_PARAM = "inc_card_id";
const INC_TRACK_WEB_PARAM = "inc_track_web";
const INC_RESUME_SEC_PARAM = "inc_resume_sec";
const INC_RESUME_MEDIA_PARAM = "inc_resume_media";
const INC_RESUME_HASH_MARKER = "__incremento_resume__=1";
const CONTENT_SCRIPT_FILE = "dist/content.js";
const COMMAND_BROWSER_CAPTURE_SELECTION = "browser-capture-selection";
const COMMAND_BROWSER_CAPTURE_SNAPSHOT = "browser-capture-snapshot";
const COMMAND_ADD_CURRENT_PAGE_AS_PDF = "add-current-page-as-pdf";
const COMMAND_ADD_CURRENT_PAGE_AS_VIDEO = "add-current-page-as-video";
const COMMAND_ADD_CURRENT_PAGE_AS_WEBPAGE = "add-current-page-as-webpage";
const COMMAND_ADD_SELECTION_TO_MARKDOWN = "add-selection-to-markdown";
const COMMAND_ADD_PAGE_TO_MARKDOWN = "add-page-to-markdown";
const BRIDGE_URL = "http://127.0.0.1:8766/incremento/add-content";
const BROWSER_CAPTURE_META_URL = "http://127.0.0.1:8766/incremento/browser-capture-meta";

function isHttpUrl(rawUrl) {
  return /^https?:\/\//i.test(String(rawUrl || ""));
}

async function parseBridgeResponse(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data?.ok) {
    throw new Error(String(data?.error || `Request failed (${response.status})`));
  }
  return data;
}

async function loadBrowserCaptureMeta() {
  const response = await fetch(BROWSER_CAPTURE_META_URL, {
    method: "GET",
  });
  return parseBridgeResponse(response);
}

async function submitBrowserCapture(payload) {
  const response = await fetch(BRIDGE_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      type: "browser_capture",
      ...payload,
    }),
  });
  return parseBridgeResponse(response);
}

async function injectContentScriptIntoOpenTabs() {
  if (!chrome.scripting?.executeScript || !chrome.tabs?.query) {
    return;
  }
  let tabs = [];
  try {
    tabs = await chrome.tabs.query({});
  } catch (_err) {
    return;
  }
  await Promise.all(
    tabs.map(async (tab) => {
      const tabId = Number(tab?.id);
      if (!Number.isFinite(tabId) || tabId <= 0 || !isHttpUrl(tab?.url || "")) {
        return;
      }
      try {
        await chrome.scripting.executeScript({
          target: { tabId, allFrames: true },
          files: [CONTENT_SCRIPT_FILE],
        });
      } catch (_err) {
        // ignore tabs where injection is not allowed
      }
    })
  );
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

function stripIncrementoResumeFragment(rawFragment) {
  const fragment = String(rawFragment || "").replace(/^#/, "").trim();
  if (!fragment) {
    return "";
  }
  const markerIndex = fragment.indexOf(INC_RESUME_HASH_MARKER);
  if (markerIndex < 0) {
    return fragment;
  }
  return fragment.slice(0, markerIndex).replace(/[&?]+$/, "");
}

function parseIncrementoResumeFragment(rawFragment) {
  const fragment = String(rawFragment || "").replace(/^#/, "").trim();
  if (!fragment) {
    return { resumeSec: 0, resumeMediaUrl: "" };
  }
  const markerIndex = fragment.indexOf(INC_RESUME_HASH_MARKER);
  if (markerIndex < 0) {
    return { resumeSec: 0, resumeMediaUrl: "" };
  }
  const params = new URLSearchParams(fragment.slice(markerIndex));
  return {
    resumeSec: Math.max(0, Math.floor(Number(params.get(INC_RESUME_SEC_PARAM) || 0))),
    resumeMediaUrl: stripIncrementoTrackingParams(params.get(INC_RESUME_MEDIA_PARAM) || ""),
  };
}

function stripIncrementoTrackingParams(rawUrl) {
  const decoded = htmlDecodeUrl(rawUrl);
  try {
    const u = new URL(decoded);
    u.searchParams.delete(INC_CARD_ID_PARAM);
    u.searchParams.delete(INC_TRACK_WEB_PARAM);
    u.searchParams.delete(INC_RESUME_SEC_PARAM);
    u.searchParams.delete(INC_RESUME_MEDIA_PARAM);
    const cleanFragment = stripIncrementoResumeFragment(u.hash);
    u.hash = cleanFragment ? `#${cleanFragment}` : "";
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
    const hashResume = parseIncrementoResumeFragment(u.hash);
    const resumeSec = Math.max(
      0,
      Math.floor(Number(u.searchParams.get(INC_RESUME_SEC_PARAM) || hashResume.resumeSec || 0))
    );
    const resumeMediaUrl = stripIncrementoTrackingParams(
      u.searchParams.get(INC_RESUME_MEDIA_PARAM) || hashResume.resumeMediaUrl || ""
    );
    return {
      trackEnabled,
      cardId: Number.isFinite(cid) && cid > 0 ? Math.floor(cid) : 0,
      cleanUrl: stripIncrementoTrackingParams(decoded),
      resumeSec,
      resumeMediaUrl,
    };
  } catch (_err) {
    return {
      trackEnabled: false,
      cardId: 0,
      cleanUrl: stripIncrementoTrackingParams(decoded),
      resumeSec: 0,
      resumeMediaUrl: "",
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

function extractIncrementoCardIdFromUrl(rawUrl) {
  try {
    const decoded = htmlDecodeUrl(rawUrl);
    const u = new URL(decoded);
    const cid = Number(u.searchParams.get(INC_CARD_ID_PARAM) || 0);
    return Number.isFinite(cid) && cid > 0 ? Math.floor(cid) : 0;
  } catch (_err) {
    return 0;
  }
}

async function loadLinkedCardContext(tabId) {
  if (typeof tabId !== "number") {
    return null;
  }
  const inMemory = LINKED_CARD_TAB_STATE.get(tabId);
  if (inMemory && Number(inMemory.cardId) > 0) {
    return inMemory;
  }
  try {
    const data = await chrome.storage.session.get(LINKED_CARD_STORAGE_KEY);
    const all = data?.[LINKED_CARD_STORAGE_KEY];
    const saved = all ? all[String(tabId)] : null;
    if (saved && Number(saved.cardId) > 0) {
      const state = {
        cardId: Math.max(0, Math.floor(Number(saved.cardId) || 0)),
        sourceUrl: String(saved.sourceUrl || ""),
        updatedAt: Math.max(0, Math.floor(Number(saved.updatedAt) || 0)),
      };
      LINKED_CARD_TAB_STATE.set(tabId, state);
      return state;
    }
  } catch (_err) {
    // noop
  }
  return null;
}

async function saveLinkedCardContext(tabId, state) {
  if (typeof tabId !== "number" || !state || Number(state.cardId) <= 0) {
    return;
  }
  const normalized = {
    cardId: Math.max(0, Math.floor(Number(state.cardId) || 0)),
    sourceUrl: stripIncrementoTrackingParams(String(state.sourceUrl || "")),
    updatedAt: Math.max(0, Math.floor(Number(state.updatedAt) || Date.now())),
  };
  LINKED_CARD_TAB_STATE.set(tabId, normalized);
  try {
    const data = await chrome.storage.session.get(LINKED_CARD_STORAGE_KEY);
    const all = data?.[LINKED_CARD_STORAGE_KEY] || {};
    all[String(tabId)] = normalized;
    await chrome.storage.session.set({ [LINKED_CARD_STORAGE_KEY]: all });
  } catch (_err) {
    // noop
  }
}

async function clearLinkedCardContext(tabId) {
  if (typeof tabId !== "number") {
    return;
  }
  LINKED_CARD_TAB_STATE.delete(tabId);
  try {
    const data = await chrome.storage.session.get(LINKED_CARD_STORAGE_KEY);
    const all = data?.[LINKED_CARD_STORAGE_KEY];
    if (!all || typeof all !== "object") {
      return;
    }
    delete all[String(tabId)];
    await chrome.storage.session.set({ [LINKED_CARD_STORAGE_KEY]: all });
  } catch (_err) {
    // noop
  }
}

async function registerLinkedCardContextFromUrl(tabId, rawUrl) {
  if (typeof tabId !== "number") {
    return null;
  }
  const cardId = extractIncrementoCardIdFromUrl(rawUrl);
  if (cardId <= 0) {
    return loadLinkedCardContext(tabId);
  }
  const state = {
    cardId,
    sourceUrl: stripIncrementoTrackingParams(rawUrl),
    updatedAt: Date.now(),
  };
  await saveLinkedCardContext(tabId, state);
  return state;
}

async function getLinkedCardContextForTab(tabId, rawUrl = "") {
  let state = await loadLinkedCardContext(tabId);
  if ((!state || Number(state.cardId) <= 0) && rawUrl) {
    state = await registerLinkedCardContextFromUrl(tabId, rawUrl);
  }
  if (!state || Number(state.cardId) <= 0) {
    return { linked: false, cardId: 0 };
  }
  return {
    linked: true,
    cardId: Math.max(0, Math.floor(Number(state.cardId) || 0)),
    sourceUrl: String(state.sourceUrl || ""),
    updatedAt: Math.max(0, Math.floor(Number(state.updatedAt) || 0)),
  };
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
        desiredResumeSec: Math.max(0, Math.floor(Number(saved.desiredResumeSec) || 0)),
        desiredResumeMediaUrl: normalizeTrackedWebMediaUrl(saved.desiredResumeMediaUrl || ""),
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
      desiredResumeSec: Math.max(0, Math.floor(Number(state.desiredResumeSec) || 0)),
      desiredResumeMediaUrl: normalizeTrackedWebMediaUrl(state.desiredResumeMediaUrl || ""),
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

function normalizeTrackedWebMediaUrl(rawUrl) {
  const cleanUrl = stripIncrementoTrackingParams(rawUrl);
  return isHttpUrl(cleanUrl) ? cleanUrl : "";
}

async function updateTrackedWebMedia(cardId, url, mediaUrl = "", mediaTitle = "", seconds = 0) {
  const cid = Math.max(0, Math.floor(Number(cardId) || 0));
  const cleanUrl = stripIncrementoTrackingParams(url);
  const cleanMediaUrl = normalizeTrackedWebMediaUrl(mediaUrl);
  const mediaSeconds = Math.max(0, Math.floor(Number(seconds) || 0));
  if (cid <= 0 || !isHttpUrl(cleanUrl) || mediaSeconds <= 0) {
    return { ok: false };
  }
  try {
    const response = await fetch(WEB_TRACK_MEDIA_BRIDGE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cardId: cid,
        url: cleanUrl,
        mediaUrl: cleanMediaUrl,
        mediaTitle: String(mediaTitle || ""),
        seconds: mediaSeconds,
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

async function maybeSyncTrackedWebMedia(tabId, frameId, msg) {
  if (typeof tabId !== "number") {
    return { ok: false };
  }

  const rawUrl = String(msg?.url || "");
  const registration = parseTrackedWebRegistration(rawUrl);
  let state = await loadTrackedWebState(tabId);
  if (registration.trackEnabled && registration.cardId > 0) {
    state = {
      cardId: registration.cardId,
      lastUrl: registration.cleanUrl || "",
      desiredResumeSec: registration.resumeSec,
      desiredResumeMediaUrl: registration.resumeMediaUrl,
    };
    await saveTrackedWebState(tabId, state);
  }

  const cardId = Math.max(
    0,
    Math.floor(
      Number(registration.cardId || 0) || Number(state?.cardId || 0) || Number(msg?.cardId || 0) || 0
    )
  );
  const seconds = Math.max(0, Math.floor(Number(msg?.seconds) || 0));
  const cleanUrl = stripIncrementoTrackingParams(rawUrl);
  const cleanMediaUrl = normalizeTrackedWebMediaUrl(msg?.mediaUrl || "");
  const mediaTitle = String(msg?.mediaTitle || msg?.title || "").trim();
  const flush = Boolean(msg?.flush);
  if (cardId <= 0 || !isHttpUrl(cleanUrl)) {
    return { ok: false };
  }

  const desiredResumeSec = Math.max(0, Math.floor(Number(state?.desiredResumeSec || 0)));
  const desiredResumeMediaUrl = normalizeTrackedWebMediaUrl(state?.desiredResumeMediaUrl || "");
  const mediaMatchesResume = !desiredResumeMediaUrl || !cleanMediaUrl || desiredResumeMediaUrl === cleanMediaUrl;
  if (desiredResumeSec > 0 && mediaMatchesResume) {
    try {
      await chrome.tabs.sendMessage(
        tabId,
        {
          type: "APPLY_MEDIA_RESUME",
          seconds: desiredResumeSec,
        },
        typeof frameId === "number" ? { frameId } : undefined,
      );
      state = {
        ...(state || {}),
        cardId,
        lastUrl: cleanUrl,
        desiredResumeSec: 0,
        desiredResumeMediaUrl: "",
      };
      await saveTrackedWebState(tabId, state);
    } catch (_err) {
      // ignore failed resume delivery
    }
  }

  if (seconds <= 0) {
    return { ok: true, skipped: true };
  }

  const previous = WEB_MEDIA_SYNC_STATE.get(tabId);
  const now = Date.now();
  const sameMedia = previous
    && previous.cardId === cardId
    && previous.url === cleanUrl
    && previous.mediaUrl === cleanMediaUrl;
  if (
    !flush
    && sameMedia
    && Math.abs(seconds - Number(previous.seconds || 0)) < 5
    && now - Number(previous.updatedAt || 0) < 15_000
  ) {
    return { ok: true, skipped: true };
  }

  const synced = await updateTrackedWebMedia(cardId, cleanUrl, cleanMediaUrl, mediaTitle, seconds);
  if (!synced.ok) {
    return synced;
  }
  WEB_MEDIA_SYNC_STATE.set(tabId, {
    cardId,
    url: cleanUrl,
    mediaUrl: cleanMediaUrl,
    seconds,
    updatedAt: now,
  });
  return synced;
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
      desiredResumeSec: registration.resumeSec,
      desiredResumeMediaUrl: registration.resumeMediaUrl,
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

async function ensureContentScriptInjected(tabId) {
  if (!chrome.scripting?.executeScript || typeof tabId !== "number") {
    return false;
  }
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: [CONTENT_SCRIPT_FILE],
    });
    return true;
  } catch (_err) {
    return false;
  }
}

async function invokeBrowserCaptureInTab(tabId, mode) {
  if (!chrome.scripting?.executeScript || typeof tabId !== "number") {
    return { ok: false };
  }
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
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
    return results?.[0]?.result || { ok: false };
  } catch (error) {
    return { ok: false, error: String(error?.message || "Failed to trigger browser capture.") };
  }
}

async function triggerBrowserCapture(mode) {
  const tab = await getActiveTab();
  if (!tab?.id || !isHttpUrl(tab.url || "")) {
    return false;
  }

  await ensureContentScriptInjected(tab.id);
  const response = await invokeBrowserCaptureInTab(tab.id, mode);
  return !!response?.ok;
}

async function triggerBrowserCaptureOnTab(tab, mode) {
  if (!tab?.id || !isHttpUrl(tab.url || "")) {
    return false;
  }
  await ensureContentScriptInjected(tab.id);
  const response = await invokeBrowserCaptureInTab(tab.id, mode);
  return !!response?.ok;
}

async function capturePageContext(tabId) {
  if (!chrome.scripting?.executeScript || typeof tabId !== "number") {
    return null;
  }
  await ensureContentScriptInjected(tabId);
  try {
    const response = await chrome.tabs.sendMessage(tabId, { type: "GET_PAGE_CONTEXT" });
    if (response?.ok) {
      return response;
    }
  } catch (_err) {
    // fall through to direct snapshot
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
    return results?.[0]?.result || null;
  } catch (_err) {
    return null;
  }
}

function buildImportPayload(kind, context, options = {}) {
  const pageUrl = String(context?.url || "").trim();
  const pageTitle = String(context?.title || pageUrl).trim();
  const selectionText = String(context?.selectionText || "");
  const payload = {
    kind,
    url: pageUrl,
    title: pageTitle || pageUrl,
    selectedText: selectionText,
  };

  if (kind === "pdf" && context?.html) {
    payload.html = String(context.html);
  }

  if (kind === "writing") {
    const writingMode = String(options.writingMode || "selection");
    payload.title = buildAutomaticWritingTitle(
      pageTitle,
      pageUrl,
      writingMode,
      selectionText,
    );
    payload.writingMode = writingMode;
    payload.preferredFilename = buildPreferredWritingFilename(pageTitle || payload.title, pageUrl);
    if (writingMode === "webpage_markdown") {
      payload.pageContentScope = String(options.pageContentScope || "main");
      if (context?.html) {
        payload.html = String(context.html);
      }
    }
  }

  return payload;
}

async function addCurrentPageToIncremento(command) {
  const tab = await getActiveTab();
  if (!tab?.id) {
    return {ok: false, error: "No active tab found."};
  }
  if (!isHttpUrl(tab.url || "")) {
    return {ok: false, error: "Only http(s) pages can be sent to Incremento."};
  }

  const context = await capturePageContext(tab.id);
  const pageUrl = String(context?.url || tab.url || "").trim();
  const pageTitle = String(context?.title || tab.title || pageUrl).trim();
  const selectionText = String(context?.selectionText || "");
  const html = String(context?.html || "");

  if (!isHttpUrl(pageUrl)) {
    return {ok: false, error: "Only http(s) pages can be sent to Incremento."};
  }

  let payload = null;
  let progressMessage = "";

  if (command === COMMAND_ADD_CURRENT_PAGE_AS_PDF) {
    payload = buildImportPayload("pdf", {url: pageUrl, title: pageTitle, selectionText, html});
    progressMessage = "Adding PDF card...";
    const pdfPayload = await getPdfPayloadForUrl(pageUrl);
    if (pdfPayload) {
      payload.pdfBase64 = pdfPayload.pdfBase64;
      payload.pdfFilename = pdfPayload.pdfFilename;
    }
  }
  if (command === COMMAND_ADD_CURRENT_PAGE_AS_VIDEO) {
    if (!isSupportedVideoUrl(pageUrl)) {
      return {ok: false, error: "Open a YouTube or Vimeo page to add a video card."};
    }
    payload = buildImportPayload("video", {url: pageUrl, title: pageTitle, selectionText, html});
    progressMessage = "Adding video card...";
    const state = TAB_STATE.get(tab.id);
    const startSeconds = Math.max(0, Math.floor(Number(state?.seconds || 0)));
    if (startSeconds > 0) {
      payload.startSeconds = startSeconds;
    }
  }
  if (command === COMMAND_ADD_CURRENT_PAGE_AS_WEBPAGE) {
    payload = buildImportPayload("webpage", {url: pageUrl, title: pageTitle, selectionText, html});
    progressMessage = "Adding webpage card...";
  }
  if (command === COMMAND_ADD_SELECTION_TO_MARKDOWN) {
    if (!selectionText) {
      return {ok: false, error: "Select text on the page first."};
    }
    payload = buildImportPayload("writing", {
      url: pageUrl,
      title: pageTitle,
      selectionText,
      html
    }, {writingMode: "selection"});
    progressMessage = "Adding writing card from selection...";
  }
  if (command === COMMAND_ADD_PAGE_TO_MARKDOWN) {
    if (!html) {
      return {ok: false, error: "Could not read webpage content from this tab."};
    }
    payload = buildImportPayload("writing", {url: pageUrl, title: pageTitle, selectionText, html}, {
      writingMode: "webpage_markdown",
      pageContentScope: "main",
    });
    progressMessage = "Adding writing card from webpage markdown...";
  } else {
    return {ok: false, error: "Unsupported command."};
  }

  try {
    const result = await importIntoIncremento(payload);
    await showToastInTab(tab.id, `Added ${result.kind} card: ${result.title}`);
    return {ok: true, result};
  } catch (error) {
    const message = String(error?.message || progressMessage || "Failed to add content.");
    await showToastInTab(tab.id, message);
    return {ok: false, error: message};
  }
}

async function reportBrowserCaptureTrigger(tabId, ok, fallbackMessage = "") {
  if (typeof tabId !== "number") {
    return;
  }
  const text = ok
    ? ""
    : (fallbackMessage || "Browser capture could not start on this tab.");
  if (!text) {
    return;
  }
  await showToastInTab(tabId, text);
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

async function captureVisibleTabForSender(sender) {
  const windowId = Number(sender?.tab?.windowId);
  const captureWindowId = Number.isFinite(windowId) && windowId >= 0 ? windowId : undefined;
  return chrome.tabs.captureVisibleTab(captureWindowId, { format: "png" });
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

  if (msg.type === "web_media_heartbeat") {
    void (async () => {
      const tabId = sender?.tab?.id;
      if (typeof tabId !== "number") {
        sendResponse?.({ ok: false });
        return;
      }
      const result = await maybeSyncTrackedWebMedia(tabId, sender?.frameId, msg);
      sendResponse?.({ ok: Boolean(result?.ok) });
    })();
    return true;
  }

  if (msg.type === "COPY_LATEST_VIDEO_TIME") {
    void (async () => {
      const copied = await copyLatestStoredTime(Boolean(msg.showFeedback));
      sendResponse?.({ ok: copied });
    })();
    return true;
  }

  if (msg.type === "GET_LINKED_CARD_CONTEXT") {
    void (async () => {
      const senderTabId = typeof sender?.tab?.id === "number" ? sender.tab.id : null;
      const requestedTabId = Number(msg.tabId);
      const tabId = Number.isFinite(requestedTabId) && requestedTabId > 0
        ? requestedTabId
        : senderTabId;
      if (typeof tabId !== "number") {
        sendResponse?.({ linked: false, cardId: 0 });
        return;
      }
      const status = await getLinkedCardContextForTab(tabId, String(msg.url || sender?.tab?.url || ""));
      sendResponse?.(status);
    })();
    return true;
  }

  if (msg.type === "LOAD_BROWSER_MEDIA_REF") {
    void (async () => {
      const senderTabId = typeof sender?.tab?.id === "number" ? sender.tab.id : null;
      const requestedCardId = Math.max(0, Math.floor(Number(msg.cardId) || 0));
      let cardId = requestedCardId;
      if (cardId <= 0 && typeof senderTabId === "number") {
        const linked = await getLinkedCardContextForTab(senderTabId, String(sender?.tab?.url || ""));
        cardId = Math.max(0, Math.floor(Number(linked?.cardId) || 0));
      }
      if (cardId <= 0) {
        sendResponse?.({ ok: true, hasReference: false, cardId: 0 });
        return;
      }
      try {
        const result = await loadBrowserMediaRef(cardId);
        sendResponse?.(result);
      } catch (error) {
        sendResponse?.({
          ok: false,
          error: String(error?.message || "Failed to load browser media reference."),
        });
      }
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

  if (msg.type === "LOAD_BROWSER_CAPTURE_META") {
    void (async () => {
      try {
        const result = await loadBrowserCaptureMeta();
        sendResponse?.(result);
      } catch (error) {
        sendResponse?.({ ok: false, error: String(error?.message || "Failed to load browser capture metadata.") });
      }
    })();
    return true;
  }

  if (msg.type === "SUBMIT_BROWSER_CAPTURE") {
    void (async () => {
      try {
        const result = await submitBrowserCapture(msg.payload || {});
        sendResponse?.(result);
      } catch (error) {
        sendResponse?.({ ok: false, error: String(error?.message || "Failed to submit browser capture.") });
      }
    })();
    return true;
  }

  if (msg.type === "CAPTURE_VISIBLE_TAB") {
    void (async () => {
      try {
        const dataUrl = await captureVisibleTabForSender(sender);
        sendResponse?.({ ok: true, dataUrl });
      } catch (error) {
        sendResponse?.({ ok: false, error: String(error?.message || "Failed to capture the current tab.") });
      }
    })();
    return true;
  }

  if (msg.type === "TRIGGER_BROWSER_CAPTURE") {
    void (async () => {
      const tabId = typeof sender?.tab?.id === "number" ? sender.tab.id : null;
      const mode = String(msg.mode || "").trim().toLowerCase();
      const ok = await triggerBrowserCapture(mode === "snapshot" ? "snapshot" : "selection");
      if (typeof tabId === "number") {
        await reportBrowserCaptureTrigger(tabId, ok, "Browser capture could not start on this tab.");
      }
      sendResponse?.({ ok });
    })();
    return true;
  }

  return false;
});

chrome.tabs.onRemoved.addListener((tabId) => {
  const state = TAB_STATE.get(tabId);
  TAB_STATE.delete(tabId);
  void clearTrackedWebState(tabId);
  void clearLinkedCardContext(tabId);
  WEB_MEDIA_SYNC_STATE.delete(tabId);
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
  void registerLinkedCardContextFromUrl(tabId, nextUrl);
  void maybeSyncTrackedWebTab(tabId, nextUrl, String(tab?.title || ""));
});

if (chrome.webNavigation?.onCommitted) {
  chrome.webNavigation.onCommitted.addListener((details) => {
    if (details?.frameId !== 0) {
      return;
    }
    void registerLinkedCardContextFromUrl(
      Number(details.tabId),
      String(details.url || ""),
    );
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
    void registerLinkedCardContextFromUrl(
      Number(details.tabId),
      String(details.url || ""),
    );
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
    void registerLinkedCardContextFromUrl(
      Number(details.tabId),
      String(details.url || ""),
    );
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

chrome.commands.onCommand.addListener((command, tab) => {
  if (command === COMMAND_BROWSER_CAPTURE_SELECTION) {
    void (tab ? triggerBrowserCaptureOnTab(tab, "selection") : triggerBrowserCapture("selection"));
    return;
  }
  if (command === COMMAND_BROWSER_CAPTURE_SNAPSHOT) {
    void (tab ? triggerBrowserCaptureOnTab(tab, "snapshot") : triggerBrowserCapture("snapshot"));
    return;
  }
  if (command !== "copy-last-video-time") {
    if (
      command === COMMAND_ADD_CURRENT_PAGE_AS_PDF
      || command === COMMAND_ADD_CURRENT_PAGE_AS_VIDEO
      || command === COMMAND_ADD_CURRENT_PAGE_AS_WEBPAGE
      || command === COMMAND_ADD_SELECTION_TO_MARKDOWN
      || command === COMMAND_ADD_PAGE_TO_MARKDOWN
    ) {
      void addCurrentPageToIncremento(command);
    }
    return;
  }
  void copyLatestStoredTime(true);
});

void injectContentScriptIntoOpenTabs();

if (chrome.runtime?.onInstalled) {
  chrome.runtime.onInstalled.addListener(() => {
    void injectContentScriptIntoOpenTabs();
  });
}
