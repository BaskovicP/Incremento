import { normalizePdfHighlightRects } from './pdfHighlightRects.mjs';

function caretRangeAtPoint(document, x, y) {
  if (!document || !Number.isFinite(x) || !Number.isFinite(y)) return null;
  if (typeof document.caretRangeFromPoint === 'function') {
    return document.caretRangeFromPoint(x, y);
  }
  if (typeof document.caretPositionFromPoint === 'function') {
    const position = document.caretPositionFromPoint(x, y);
    if (position?.offsetNode) {
      const range = document.createRange();
      range.setStart(position.offsetNode, position.offset);
      range.collapse(true);
      return range;
    }
  }
  return null;
}

function preciseRangeFromAnchor(document, anchor, caret) {
  if (!document || !anchor || !caret || typeof caret.compareBoundaryPoints !== 'function') return null;
  try {
    const next = document.createRange();
    const caretIsBeforeAnchor = caret.compareBoundaryPoints(0, anchor) < 0;
    if (caretIsBeforeAnchor) {
      next.setStart(caret.startContainer, caret.startOffset);
      next.setEnd(anchor.startContainer, anchor.startOffset);
    } else {
      next.setStart(anchor.startContainer, anchor.startOffset);
      next.setEnd(caret.startContainer, caret.startOffset);
    }
    return next;
  } catch (_error) {
    return null;
  }
}

function replaceSelection(window, range) {
  const selection = window?.getSelection?.();
  if (!selection || !range) return false;
  selection.removeAllRanges();
  selection.addRange(range);
  return true;
}

/**
 * Replace Chromium's initial text-drag tracking with exact caret hit-testing.
 * Qt WebEngine can jump several PDF.js rows during a trackpad drag, while
 * caretRangeFromPoint remains character-accurate (the resize handles use it too).
 */
export function installPrecisePdfSelectionDrag(textLayer, {
  document = globalThis.document,
  window = globalThis.window,
} = {}) {
  if (!textLayer || !document || !window) return () => {};
  let session = null;
  const usePointerEvents = typeof window.PointerEvent === 'function';
  const startEvent = usePointerEvents ? 'pointerdown' : 'mousedown';
  const moveEvent = usePointerEvents ? 'pointermove' : 'mousemove';
  const endEvent = usePointerEvents ? 'pointerup' : 'mouseup';

  const releasePointer = () => {
    const pointerId = session?.pointerId;
    if (pointerId === null || pointerId === undefined
        || typeof textLayer.releasePointerCapture !== 'function') return;
    try {
      textLayer.releasePointerCapture(pointerId);
    } catch (_error) {
      // The browser may already have released capture as the pointer ended.
    }
  };

  const blockNativeSelection = (event) => {
    if (session) event.preventDefault?.();
  };

  const update = (event) => {
    if (!session) return false;
    event.preventDefault?.();
    const caret = caretRangeAtPoint(document, Number(event.clientX), Number(event.clientY));
    if (!caret?.startContainer || !textLayer.contains(caret.startContainer)) return false;
    const next = preciseRangeFromAnchor(document, session.anchor, caret);
    if (!next || !textLayer.contains(next.commonAncestorContainer)) return false;
    return replaceSelection(window, next);
  };

  const finish = (event) => {
    if (!session) return;
    update(event);
    releasePointer();
    session = null;
  };

  const cancel = () => {
    if (!session) return;
    releasePointer();
    session = null;
  };

  const start = (event) => {
    if (event.button !== 0 || Number(event.detail || 1) > 1
        || (usePointerEvents && event.isPrimary === false)
        || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
    const caret = caretRangeAtPoint(document, Number(event.clientX), Number(event.clientY));
    if (!caret?.startContainer || !textLayer.contains(caret.startContainer)) return;
    event.preventDefault?.();
    const anchor = typeof caret.cloneRange === 'function' ? caret.cloneRange() : caret;
    anchor.collapse?.(true);
    if (!replaceSelection(window, anchor)) return;
    const pointerId = usePointerEvents && Number.isFinite(event.pointerId) ? event.pointerId : null;
    session = { anchor, pointerId };
    if (pointerId !== null && typeof textLayer.setPointerCapture === 'function') {
      try {
        textLayer.setPointerCapture(pointerId);
      } catch (_error) {
        // Document-level listeners still keep the drag active without capture.
      }
    }
  };

  textLayer.addEventListener(startEvent, start, true);
  document.addEventListener(moveEvent, update, true);
  document.addEventListener(endEvent, finish, true);
  if (usePointerEvents) document.addEventListener('pointercancel', cancel, true);
  document.addEventListener('mousedown', blockNativeSelection, true);
  document.addEventListener('selectstart', blockNativeSelection, true);
  document.addEventListener('dragstart', blockNativeSelection, true);
  return () => {
    releasePointer();
    session = null;
    textLayer.removeEventListener(startEvent, start, true);
    document.removeEventListener(moveEvent, update, true);
    document.removeEventListener(endEvent, finish, true);
    if (usePointerEvents) document.removeEventListener('pointercancel', cancel, true);
    document.removeEventListener('mousedown', blockNativeSelection, true);
    document.removeEventListener('selectstart', blockNativeSelection, true);
    document.removeEventListener('dragstart', blockNativeSelection, true);
  };
}

/** Move one endpoint of the real browser selection and retain the other. */
export function movePdfSelectionEndpoint(textLayer, currentRange, endpoint, clientX, clientY, {
  document = globalThis.document,
  window = globalThis.window,
} = {}) {
  if (!textLayer || !currentRange || !['start', 'end'].includes(endpoint)) return null;
  const caret = caretRangeAtPoint(document, Number(clientX), Number(clientY));
  if (!caret?.startContainer || !textLayer.contains(caret.startContainer)) return null;
  try {
    const next = document.createRange();
    if (endpoint === 'start') {
      next.setStart(caret.startContainer, caret.startOffset);
      next.setEnd(currentRange.endContainer, currentRange.endOffset);
    } else {
      next.setStart(currentRange.startContainer, currentRange.startOffset);
      next.setEnd(caret.startContainer, caret.startOffset);
    }
    if (next.collapsed || !textLayer.contains(next.commonAncestorContainer)) return null;
    const selection = window.getSelection();
    if (!selection) return null;
    selection.removeAllRanges();
    selection.addRange(next);
    return next;
  } catch (_error) {
    return null;
  }
}

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
