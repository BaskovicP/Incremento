import { t } from "./i18n.js";

export function isMissingReceiver(error) {
  return /Receiving end does not exist/i.test(String(error?.message || error || ""));
}

const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

export async function requestExtensionRuntime(message, runtime) {
  if (!runtime?.sendMessage) throw new Error(t("extension_runtime_unavailable"));
  // Only the metadata read can be replayed. A disconnected reply from note
  // creation does not establish whether Anki already committed the note.
  const attempts = message?.type === "LOAD_BROWSER_CAPTURE_META" ? 3 : 1;
  for (let index = 0; index < attempts; index += 1) {
    try {
      return await new Promise((resolve, reject) => {
        runtime.sendMessage(message, response => {
          const error = runtime.lastError;
          if (error) reject(new Error(error.message || t("extension_request_failed")));
          else resolve(response || null);
        });
      });
    } catch (error) {
      if (isMissingReceiver(error) && index < attempts - 1) {
        await wait(100 * (index + 1));
        continue;
      }
      if (isMissingReceiver(error) || /context invalidated/i.test(String(error?.message || error))) {
        throw new Error(t("extension_runtime_unavailable"));
      }
      throw error;
    }
  }
}
