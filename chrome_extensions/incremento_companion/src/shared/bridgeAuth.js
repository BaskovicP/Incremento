import { t } from "./i18n.js";

const HANDSHAKE_URL = "http://127.0.0.1:8766/incremento/handshake";
const PROTOCOL_VERSION = 2;
const MAX_TRANSIENT_RETRIES = 2;
const RETRY_DELAYS_MS = [60, 180];

let authorizationPromise = null;

async function requestAuthorization() {
  // Chrome may omit Origin on privileged cross-origin GET requests. A bodyless
  // POST preserves the browser-authenticated extension origin without putting
  // credentials in the URL or weakening the bridge's exact-origin binding.
  const response = await fetch(HANDSHAKE_URL, { method: "POST", cache: "no-store" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data?.ok || Number(data.protocol) !== PROTOCOL_VERSION || !data.token) {
    const error = new Error(String(data?.error || t("bridge_handshake_failed")));
    error.code = typeof data?.error_code === "string" ? data.error_code : "";
    throw error;
  }
  return String(data.token);
}

function startAuthorization() {
  const request = requestAuthorization().catch((error) => {
    if (authorizationPromise === request) {
      authorizationPromise = null;
    }
    throw error;
  });
  authorizationPromise = request;
  return request;
}

function bridgeAuthorization() {
  return authorizationPromise || startAuthorization();
}

function refreshBridgeAuthorization(staleAuthorization) {
  if (!authorizationPromise || authorizationPromise === staleAuthorization) {
    return startAuthorization();
  }
  return authorizationPromise;
}

function retryDelay(attempt) {
  const delayMs = RETRY_DELAYS_MS[Math.min(attempt, RETRY_DELAYS_MS.length - 1)] || 0;
  return new Promise((resolve) => setTimeout(resolve, delayMs));
}

function requestMethod(options) {
  return String(options?.method || "GET").trim().toUpperCase() || "GET";
}

function canRetryConnectionFailure(options, safeToRetry) {
  return Boolean(safeToRetry) || ["GET", "HEAD", "OPTIONS"].includes(requestMethod(options));
}

async function authorizedRequest(url, options, authorization) {
  const token = await authorization;
  const headers = new Headers(options?.headers || {});
  headers.set("X-Incremento-Token", token);
  headers.set("X-Incremento-Protocol", String(PROTOCOL_VERSION));
  return fetch(url, { ...(options || {}), headers });
}

export async function bridgeFetch(url, options = {}, { safeToRetry = false } = {}) {
  let authorization = bridgeAuthorization();
  let authorizationRefreshed = false;
  let transientRetries = 0;

  while (true) {
    let response;
    try {
      response = await authorizedRequest(url, options, authorization);
    } catch (error) {
      if (
        !canRetryConnectionFailure(options, safeToRetry)
        || transientRetries >= MAX_TRANSIENT_RETRIES
      ) {
        throw error;
      }
      await retryDelay(transientRetries);
      transientRetries += 1;
      authorization = bridgeAuthorization();
      continue;
    }

    if (response.status === 401 && !authorizationRefreshed) {
      authorization = refreshBridgeAuthorization(authorization);
      authorizationRefreshed = true;
      continue;
    }

    if (response.status === 503 && transientRetries < MAX_TRANSIENT_RETRIES) {
      await retryDelay(transientRetries);
      transientRetries += 1;
      continue;
    }

    return response;
  }
}

export function resetBridgeAuthorizationForTests() {
  authorizationPromise = null;
}
