/** Crop from backing pixels, which can be less dense than the current display. */
export function cropPdfSnapshot(canvas, rect, createCanvas) {
  const size = canvas.getBoundingClientRect();
  if (![canvas.width, canvas.height, size.width, size.height, rect.w, rect.h]
    .every(value => Number.isFinite(value) && value > 0)
    || ![rect.x, rect.y].every(Number.isFinite)) return null;
  const scaleX = canvas.width / size.width, scaleY = canvas.height / size.height;
  const left = Math.max(0, Math.min(canvas.width, Math.round(rect.x * scaleX)));
  const top = Math.max(0, Math.min(canvas.height, Math.round(rect.y * scaleY)));
  const right = Math.max(left, Math.min(canvas.width, Math.round((rect.x + rect.w) * scaleX)));
  const bottom = Math.max(top, Math.min(canvas.height, Math.round((rect.y + rect.h) * scaleY)));
  if (right === left || bottom === top) return null;
  const output = createCanvas();
  output.width = right - left;
  output.height = bottom - top;
  output.getContext('2d').drawImage(canvas, left, top, output.width, output.height,
    0, 0, output.width, output.height);
  return output;
}

/** Encode outside the synchronous pointer handler; never deliver a stale capture. */
export function encodePdfSnapshot(canvas, isCurrent, Reader = globalThis.FileReader) {
  return new Promise((resolve, reject) => {
    canvas.toBlob(blob => {
      if (!blob || !isCurrent()) { resolve(null); return; }
      const reader = new Reader();
      reader.onerror = () => reject(new Error('PDF snapshot encoding failed'));
      reader.onload = () => resolve(isCurrent() ? reader.result : null);
      reader.readAsDataURL(blob);
    }, 'image/png');
  });
}

/** The drag rectangle has no React state: moving it must not render the reader. */
export function paintPdfSnapshotPreview(element, rect) {
  if (!element) return;
  if (!rect || rect.w <= 2 || rect.h <= 2) {
    element.style.display = 'none';
    return;
  }
  Object.assign(element.style, {
    display: 'block', left: `${rect.x}px`, top: `${rect.y}px`,
    width: `${rect.w}px`, height: `${rect.h}px`,
  });
}

/** Only the capture button/overlay subscribe; activation must not render the reader. */
export function createPdfSnapshotMode() {
  let active = false;
  const listeners = new Set();
  return {
    getSnapshot: () => active,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    setActive(value) {
      const next = value === true;
      if (next === active) return;
      active = next;
      for (const listener of listeners) listener();
    },
  };
}

export const INACTIVE_PDF_SNAPSHOT_MODE = {
  getSnapshot: () => false,
  subscribe: () => () => {},
};
