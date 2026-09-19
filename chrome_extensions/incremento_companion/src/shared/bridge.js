import { bridgeFetch } from "./bridgeAuth.js";
import { t } from "./i18n.js";

const BRIDGE_URL = "http://127.0.0.1:8766/incremento/add-content";
const BROWSER_CAPTURE_META_URL = "http://127.0.0.1:8766/incremento/browser-capture-meta";
const BROWSER_MEDIA_REF_URL = "http://127.0.0.1:8766/incremento/browser-media-ref";
const BRIDGE_ERROR_CODES = new Set([
  "authorization_required", "bridge_busy", "unknown_path", "invalid_request",
  "operation_failed", "unsupported_transfer_encoding", "invalid_content_length",
  "request_too_large", "request_timeout", "incomplete_body", "invalid_json",
]);

async function parseBridgeResponse(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data?.ok) {
    const error = new Error(String(data?.error || t("bridge_request_failed", { status: response.status })));
    error.code = typeof data?.error_code === "string" ? data.error_code : "";
    throw error;
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
    method: "POST",
  }, { safeToRetry: true });
  return parseBridgeResponse(response);
}

export async function loadBrowserMediaRef(cardId) {
  const response = await bridgeFetch(`${BROWSER_MEDIA_REF_URL}?cardId=${encodeURIComponent(String(cardId || ""))}`, {
    method: "POST",
  }, { safeToRetry: true });
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
    return t("bridge_unavailable");
  }
  const message = String(error?.message || "").trim();
  if (error?.code === "origin_not_allowed" || message === "Origin not allowed.") {
    return t("bridge_origin_conflict");
  }
  if (BRIDGE_ERROR_CODES.has(error?.code)) return t(`bridge_error_${error.code}`);
  return message || fallbackMessage;
}
