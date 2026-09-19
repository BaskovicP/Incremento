const DEFAULT_ANKICONNECT_URL = "http://127.0.0.1:8765";
const DEFAULT_ANKICONNECT_VERSION = 6;
const DEFAULT_TIMEOUT_MS = 8_000;

export function createAnkiConnectClient({
  fetchImpl = globalThis.fetch,
  url = DEFAULT_ANKICONNECT_URL,
  version = DEFAULT_ANKICONNECT_VERSION,
  timeoutMs = DEFAULT_TIMEOUT_MS,
} = {}) {
  let queue = Promise.resolve();

  async function request(action, params) {
    const controller = new globalThis.AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetchImpl(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, version, params }),
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error(`AnkiConnect request failed (${response.status}).`);
      }
      const data = await response.json();
      if (data?.error) {
        throw new Error(String(data.error));
      }
      return data?.result;
    } catch (error) {
      if (controller.signal.aborted) {
        throw new Error("AnkiConnect request timed out.");
      }
      throw error;
    } finally {
      clearTimeout(timeoutId);
    }
  }

  return {
    call(action, params = {}) {
      const result = queue.then(() => request(action, params));
      queue = result.then(
        () => undefined,
        () => undefined,
      );
      return result;
    },
  };
}

export const ankiConnectClient = createAnkiConnectClient();
