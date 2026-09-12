import { bridgeFetch } from "./bridgeAuth.js";

const BRIDGE_URL = "http://127.0.0.1:8766/incremento/add-content";
const BROWSER_CAPTURE_META_URL = "http://127.0.0.1:8766/incremento/browser-capture-meta";
const BROWSER_MEDIA_REF_URL = "http://127.0.0.1:8766/incremento/browser-media-ref";
const BRIDGE_UNAVAILABLE_MESSAGE = "Failed to reach Incremento in Anki. Keep Anki open and reload the addon.";
const ORIGIN_CONFLICT_MESSAGE = "This Companion copy is not authorized. Restart Anki, then reopen the popup. If this returns, disable duplicate Companion copies in other Chrome/Brave profiles.";

async function parseBridgeResponse(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data?.ok) {
    throw new Error(String(data?.error || `Request failed (${response.status})`));
  }
  return data;
}

export async function importIntoIncremento(payload) {
  const response = await bridgeFetch(BRIDGE_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseBridgeResponse(response);
}

export async function loadBrowserCaptureMeta() {
  const response = await bridgeFetch(BROWSER_CAPTURE_META_URL, {
    method: "GET",
  });
  return parseBridgeResponse(response);
}

export async function loadBrowserMediaRef(cardId) {
  const response = await bridgeFetch(`${BROWSER_MEDIA_REF_URL}?cardId=${encodeURIComponent(String(cardId || ""))}`, {
    method: "GET",
  });
  return parseBridgeResponse(response);
}

export async function saveBrowserMediaRef(payload) {
  const response = await bridgeFetch(BROWSER_MEDIA_REF_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseBridgeResponse(response);
}

export async function submitBrowserCapture(payload) {
  const response = await bridgeFetch(BRIDGE_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      type: "browser_capture",
      ...payload,
    }),
  });
  return parseBridgeResponse(response);
}

export function formatBridgeError(error, fallbackMessage) {
  if (error instanceof TypeError) {
    return BRIDGE_UNAVAILABLE_MESSAGE;
  }
  const message = String(error?.message || "").trim();
  if (message === "Origin not allowed.") {
    return ORIGIN_CONFLICT_MESSAGE;
  }
  return message || fallbackMessage;
}
