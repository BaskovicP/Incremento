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
