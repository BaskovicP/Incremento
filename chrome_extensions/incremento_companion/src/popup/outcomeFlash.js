export const OUTCOME_FLASH_DURATION_MS = 900;

export function createOutcomeFlashController({
  onChange,
  setTimer = globalThis.setTimeout,
  clearTimer = globalThis.clearTimeout,
  durationMs = OUTCOME_FLASH_DURATION_MS,
}) {
  let timerId = null;
  let revision = 0;
  let disposed = false;

  return {
    trigger(rawKind) {
      const kind = rawKind === "success" || rawKind === "error" ? rawKind : "";
      if (!kind || disposed) return;
      if (timerId !== null) clearTimer(timerId);
      revision += 1;
      const flashRevision = revision;
      onChange({ kind, revision: flashRevision });
      timerId = setTimer(() => {
        timerId = null;
        if (!disposed && revision === flashRevision) {
          onChange({ kind: "", revision: flashRevision });
        }
      }, Math.max(0, Number(durationMs) || OUTCOME_FLASH_DURATION_MS));
    },
    dispose() {
      disposed = true;
      if (timerId !== null) {
        clearTimer(timerId);
        timerId = null;
      }
    },
  };
}
