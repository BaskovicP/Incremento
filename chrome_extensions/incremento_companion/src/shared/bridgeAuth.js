const HANDSHAKE_URL = "http://127.0.0.1:8766/incremento/handshake";
const PROTOCOL_VERSION = 2;

let authorizationPromise = null;

async function requestAuthorization() {
  const response = await fetch(HANDSHAKE_URL, { method: "GET", cache: "no-store" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data?.ok || Number(data.protocol) !== PROTOCOL_VERSION || !data.token) {
    throw new Error(String(data?.error || "Incremento bridge handshake failed."));
  }
  return String(data.token);
}

async function bridgeToken({ refresh = false } = {}) {
  if (refresh || !authorizationPromise) {
    authorizationPromise = requestAuthorization().catch((error) => {
      authorizationPromise = null;
      throw error;
    });
  }
  return authorizationPromise;
}

async function authorizedRequest(url, options, { refresh = false } = {}) {
  const token = await bridgeToken({ refresh });
  const headers = new Headers(options?.headers || {});
  headers.set("X-Incremento-Token", token);
  headers.set("X-Incremento-Protocol", String(PROTOCOL_VERSION));
  return fetch(url, { ...(options || {}), headers });
}

export async function bridgeFetch(url, options = {}) {
  let response = await authorizedRequest(url, options);
  if (response.status === 401) {
    response = await authorizedRequest(url, options, { refresh: true });
  }
  return response;
}

export function resetBridgeAuthorizationForTests() {
  authorizationPromise = null;
}
