const BRIDGE_URL = "http://127.0.0.1:8766/incremento/add-content";
const BROWSER_CAPTURE_META_URL = "http://127.0.0.1:8766/incremento/browser-capture-meta";
const BRIDGE_UNAVAILABLE_MESSAGE = "Failed to reach Incremento in Anki. Keep Anki open and reload the addon.";

async function parseBridgeResponse(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data?.ok) {
    throw new Error(String(data?.error || `Request failed (${response.status})`));
  }
  return data;
}

export async function importIntoIncremento(payload) {
  const response = await fetch(BRIDGE_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseBridgeResponse(response);
}

export async function loadBrowserCaptureMeta() {
  const response = await fetch(BROWSER_CAPTURE_META_URL, {
    method: "GET",
  });
  return parseBridgeResponse(response);
}

export async function submitBrowserCapture(payload) {
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

export function formatBridgeError(error, fallbackMessage) {
  if (error instanceof TypeError) {
    return BRIDGE_UNAVAILABLE_MESSAGE;
  }
  return error?.message || fallbackMessage;
}
