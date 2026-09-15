import { normalizePdfHighlightRects } from './pdfHighlightRects.mjs';

/**
 * Observe the native selection and publish merged geometry for its blue overlay.
 * CSS ::selection paints each PDF.js span separately, leaving word spaces clear;
 * the overlay fills those spaces using the same merge rule as saved highlights.
 * The browser's Range stays intact so copying, extraction, and highlight creation
 * continue to receive the original selected text and exact selection endpoints.
 */
export function observePdfTextSelection(textLayer, onChange, {
  document = globalThis.document,
  window = globalThis.window,
} = {}) {
  let frame = null;
  const update = () => {
    frame = null;
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || !selection.rangeCount) {
      onChange([]);
      return;
    }
    const rects = [];
    const layerRect = textLayer.getBoundingClientRect();
    for (let index = 0; index < selection.rangeCount; index += 1) {
      const range = selection.getRangeAt(index);
      // A selection in the toolbar or another document must clear this preview.
      if (!textLayer.contains(range.commonAncestorContainer)) {
        onChange([]);
        return;
      }
      // DOM rectangles already include zoom. Subtract the text-layer origin to
      // get local CSS pixels; the live overlay must not scale them a second time.
      rects.push(...Array.from(range.getClientRects(), rect => ({
        x: rect.left - layerRect.left,
        y: rect.top - layerRect.top,
        w: rect.width,
        h: rect.height,
      })));
    }
    onChange(normalizePdfHighlightRects(rects));
  };
  const schedule = () => {
    // Dragging can emit many selection changes. Read layout once per frame and
    // use the latest Range rather than queueing an update for every mouse move.
    if (frame === null) frame = window.requestAnimationFrame(update);
  };
  // PDF.js replaces spans on page/document changes. Re-read the Range then too,
  // so a preview cannot keep painting boxes from text that has been removed.
  const observer = new window.MutationObserver(schedule);
  observer.observe(textLayer, { childList: true, subtree: true, characterData: true });
  document.addEventListener('selectionchange', schedule);
  schedule();

  return () => {
    // Closing the reader or restarting observation after a render change must
    // detach listeners and cancel pending work before it can update stale state.
    document.removeEventListener('selectionchange', schedule);
    observer.disconnect();
    if (frame !== null) window.cancelAnimationFrame(frame);
  };
}
