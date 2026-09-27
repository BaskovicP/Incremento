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

function caretVisualPoint(document, caret) {
  if (!document || !caret) return null;
  try {
    let rect = caret.getBoundingClientRect?.();
    let useRightEdge = false;
    if (!rect || !Number.isFinite(rect.top) || !(Number(rect.height) > 0)) {
      const node = caret.startContainer;
      const length = node?.nodeType === 3 ? String(node.nodeValue || '').length : 0;
      if (!length) return null;
      const offset = Math.max(0, Math.min(Number(caret.startOffset) || 0, length));
      const probe = document.createRange();
      if (offset < length) {
        probe.setStart(node, offset);
        probe.setEnd(node, offset + 1);
      } else {
        probe.setStart(node, offset - 1);
        probe.setEnd(node, offset);
        useRightEdge = true;
      }
      rect = probe.getBoundingClientRect?.();
    }
    if (!rect || !Number.isFinite(rect.top) || !(Number(rect.height) > 0)) return null;
    return {
      x: Number(useRightEdge ? rect.right : rect.left),
      y: Number(rect.top) + (Number(rect.height) / 2),
      height: Number(rect.height),
    };
  } catch (_error) {
    return null;
  }
}

function mergedTextRows(rects) {
  const rows = [];
  for (const rect of rects.sort((a, b) => a.top - b.top || a.left - b.left)) {
    const row = rows.find(candidate => {
      const overlap = Math.min(candidate.bottom, rect.bottom) - Math.max(candidate.top, rect.top);
      const minHeight = Math.min(candidate.height, rect.height);
      const horizontalGap = Math.max(0, rect.left - candidate.right, candidate.left - rect.right);
      return overlap >= minHeight * 0.45
        && horizontalGap <= Math.max(candidate.height, rect.height) * 4;
    });
    if (!row) {
      rows.push({ ...rect });
      continue;
    }
    row.top = Math.min(row.top, rect.top);
    row.bottom = Math.max(row.bottom, rect.bottom);
    row.left = Math.min(row.left, rect.left);
    row.right = Math.max(row.right, rect.right);
    row.height = Math.max(row.height, rect.height);
  }
  return rows;
}

function collectTextRowRects(document, root) {
  if (!document || !root || typeof document.createTreeWalker !== 'function') return [];
  const rows = [];
  try {
    const showText = document.defaultView?.NodeFilter?.SHOW_TEXT ?? 4;
    const walker = document.createTreeWalker(root, showText);
    while (walker.nextNode() && rows.length < 4000) {
      const node = walker.currentNode;
      if (!node?.nodeValue?.length) continue;
      const range = document.createRange();
      range.selectNodeContents(node);
      for (const rect of Array.from(range.getClientRects?.() || [])) {
        if (!rect || !(Number(rect.height) > 0) || !(Number(rect.width) >= 0)) continue;
        rows.push({
          top: Number(rect.top),
          bottom: Number(rect.bottom),
          left: Number(rect.left),
          right: Number(rect.right),
          height: Number(rect.height),
        });
      }
    }
  } catch (_error) {
    return [];
  }
  return mergedTextRows(rows);
}

function nearestTextRow(rows, x, y) {
  let nearest = null;
  let nearestDistance = Infinity;
  for (const row of rows) {
    const verticalDistance = y < row.top ? row.top - y : (y > row.bottom ? y - row.bottom : 0);
    const horizontalDistance = x < row.left ? row.left - x : (x > row.right ? x - row.right : 0);
    const distance = verticalDistance * 10000 + horizontalDistance;
    if (distance < nearestDistance) {
      nearest = row;
      nearestDistance = distance;
    }
  }
  return nearest;
}

function stickyTextRow(session, candidate, y) {
  const active = session.activeRow;
  if (!active || active === candidate) {
    session.activeRow = candidate;
    return candidate;
  }
  const goingDown = candidate.top > active.top;
  const gap = goingDown
    ? Math.max(0, candidate.top - active.bottom)
    : Math.max(0, active.top - candidate.bottom);
  const hysteresis = Math.min(gap * 0.2, Math.max(active.height, candidate.height) * 0.25);
  const midpoint = goingDown
    ? (active.bottom + candidate.top) / 2 + hysteresis
    : (candidate.bottom + active.top) / 2 - hysteresis;
  if ((goingDown && y < midpoint) || (!goingDown && y > midpoint)) return active;
  session.activeRow = candidate;
  return candidate;
}

function isWordCharacter(character) {
  return !!character && !/[\s.,;:!?()[\]{}"“”‘’/\\|…—–-]/u.test(character);
}

function magneticWordCaret(document, caret, clientX) {
  const node = caret?.startContainer;
  if (!node || node.nodeType !== 3) return caret;
  const text = String(node.nodeValue || '');
  const offset = Math.max(0, Math.min(Number(caret.startOffset) || 0, text.length));
  const candidates = [];
  for (let boundary = Math.max(0, offset - 1); boundary <= Math.min(text.length, offset + 1); boundary += 1) {
    if (isWordCharacter(text[boundary - 1]) === isWordCharacter(text[boundary])) continue;
    const range = document.createRange();
    range.setStart(node, boundary);
    range.collapse(true);
    const point = caretVisualPoint(document, range);
    if (!point) continue;
    const threshold = Math.max(2, Math.min(6, point.height * 0.22));
    const distance = Math.abs(point.x - Number(clientX));
    if (distance <= threshold) candidates.push({ range, distance });
  }
  candidates.sort((a, b) => a.distance - b.distance);
  return candidates[0]?.range || caret;
}

function caretAtStablePoint(document, root, session, clientX, clientY) {
  const x = Number(clientX);
  const y = Number(clientY);
  const nativeCaret = caretRangeAtPoint(document, x, y);
  const nativePoint = caretVisualPoint(document, nativeCaret);
  const nativeIsNearby = nativePoint
    && Math.abs(nativePoint.y - y) <= Math.max(6, nativePoint.height * 1.5);
  if (!session.textRows.length) return nativeCaret;

  const nearest = nearestTextRow(session.textRows, x, y);
  if (!nearest) return nativeCaret;
  const targetRow = stickyTextRow(session, nearest, y);
  const pointerInsideTarget = x >= targetRow.left && x <= targetRow.right
    && y >= targetRow.top && y <= targetRow.bottom;
  if (nativeIsNearby && pointerInsideTarget && targetRow === nearest) {
    return magneticWordCaret(document, nativeCaret, x);
  }
  const inset = Math.min(1, Math.max(0, targetRow.height / 4));
  const probeX = Math.max(targetRow.left + inset, Math.min(x, targetRow.right - inset));
  const probeY = Math.max(targetRow.top + inset, Math.min(y, targetRow.bottom - inset));
  const snapped = caretRangeAtPoint(document, probeX, probeY);
  const resolved = snapped?.startContainer && root.contains(snapped.startContainer) ? snapped : nativeCaret;
  if (x < targetRow.left || x > targetRow.right) return resolved;
  return magneticWordCaret(document, resolved, probeX);
}

function caretMovementMatchesPointer(document, session, caret, clientY) {
  const nextPointerY = Number(clientY);
  const nextPoint = caretVisualPoint(document, caret);
  const previousPointerY = session.lastPointerY;
  const previousPoint = session.lastCaretPoint;
  session.lastPointerY = nextPointerY;
  if (!nextPoint) return true;
  if (!previousPoint || !Number.isFinite(previousPointerY) || !Number.isFinite(nextPointerY)) {
    session.lastCaretPoint = nextPoint;
    return true;
  }
  const pointerDelta = nextPointerY - previousPointerY;
  const caretDelta = nextPoint.y - previousPoint.y;
  const lineHeight = Math.max(1, previousPoint.height, nextPoint.height);
  const movesOpposite = Math.abs(pointerDelta) >= 1
    && pointerDelta * caretDelta < 0
    && Math.abs(caretDelta) > lineHeight * 0.75;
  const leapsPastPointer = Math.abs(caretDelta) > Math.abs(pointerDelta) + lineHeight * 2.25;
  if (movesOpposite || leapsPastPointer) return false;
  session.lastCaretPoint = nextPoint;
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
  onSelectionHandlesChange = () => {},
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

  const hideHandlesOutsideSelection = (event) => {
    const target = event?.target;
    if (target?.closest?.('.incremento-pdf-selection-resize-handle')) return;
    if (!target || !textLayer.contains(target)) onSelectionHandlesChange(false);
  };

  const update = (event) => {
    if (!session) return false;
    event.preventDefault?.();
    const caret = caretAtStablePoint(document, textLayer, session, event.clientX, event.clientY);
    if (!caret?.startContainer || !textLayer.contains(caret.startContainer)) return false;
    if (!caretMovementMatchesPointer(document, session, caret, event.clientY)) return false;
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
    onSelectionHandlesChange(false);
  };

  const start = (event) => {
    if (event.button !== 0 || Number(event.detail || 1) > 1
        || (usePointerEvents && event.isPrimary === false)
        || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
    const textRows = collectTextRowRects(document, textLayer);
    const initialSession = { textRows };
    const caret = caretAtStablePoint(
      document,
      textLayer,
      initialSession,
      event.clientX,
      event.clientY,
    );
    if (!caret?.startContainer || !textLayer.contains(caret.startContainer)) return;
    event.preventDefault?.();
    const anchor = typeof caret.cloneRange === 'function' ? caret.cloneRange() : caret;
    anchor.collapse?.(true);
    if (!replaceSelection(window, anchor)) return;
    const pointerId = usePointerEvents && Number.isFinite(event.pointerId) ? event.pointerId : null;
    session = {
      anchor,
      pointerId,
      lastPointerY: Number(event.clientY),
      lastCaretPoint: caretVisualPoint(document, caret),
      textRows,
      activeRow: initialSession.activeRow,
    };
    onSelectionHandlesChange(true);
    if (pointerId !== null && typeof textLayer.setPointerCapture === 'function') {
      try {
        textLayer.setPointerCapture(pointerId);
      } catch (_error) {
        // Document-level listeners still keep the drag active without capture.
      }
    }
  };

  textLayer.addEventListener(startEvent, start, true);
  document.addEventListener(startEvent, hideHandlesOutsideSelection, true);
  document.addEventListener(moveEvent, update, true);
  document.addEventListener(endEvent, finish, true);
  if (usePointerEvents) document.addEventListener('pointercancel', cancel, true);
  document.addEventListener('mousedown', blockNativeSelection, true);
  document.addEventListener('selectstart', blockNativeSelection, true);
  document.addEventListener('dragstart', blockNativeSelection, true);
  return () => {
    releasePointer();
    session = null;
    onSelectionHandlesChange(false);
    textLayer.removeEventListener(startEvent, start, true);
    document.removeEventListener(startEvent, hideHandlesOutsideSelection, true);
    document.removeEventListener(moveEvent, update, true);
    document.removeEventListener(endEvent, finish, true);
    if (usePointerEvents) document.removeEventListener('pointercancel', cancel, true);
    document.removeEventListener('mousedown', blockNativeSelection, true);
    document.removeEventListener('selectstart', blockNativeSelection, true);
    document.removeEventListener('dragstart', blockNativeSelection, true);
  };
}

/** Resolve an endpoint drag while keeping blank horizontal space on the active row. */
export function stablePdfEndpointCaret(textLayer, currentRange, endpoint, clientX, clientY, {
  document = globalThis.document,
  dragState = {},
} = {}) {
  if (!textLayer || !currentRange || !['start', 'end'].includes(endpoint)) return null;
  if (dragState && typeof dragState === 'object') {
    if (!Array.isArray(dragState.textRows)) {
      dragState.textRows = collectTextRowRects(document, textLayer);
    }
    if (!dragState.activeRow && dragState.textRows.length) {
      try {
        const boundary = document.createRange();
        const container = endpoint === 'start' ? currentRange.startContainer : currentRange.endContainer;
        const offset = endpoint === 'start' ? currentRange.startOffset : currentRange.endOffset;
        boundary.setStart(container, offset);
        boundary.collapse(true);
        const point = caretVisualPoint(document, boundary);
        if (point) dragState.activeRow = nearestTextRow(dragState.textRows, point.x, point.y);
      } catch (_error) {
        // Fall through to pointer-based row resolution below.
      }
    }
    return caretAtStablePoint(document, textLayer, dragState, Number(clientX), Number(clientY));
  }
  return caretRangeAtPoint(document, Number(clientX), Number(clientY));
}

/** Move one endpoint of the real browser selection and retain the other. */
export function movePdfSelectionEndpoint(textLayer, currentRange, endpoint, clientX, clientY, {
  document = globalThis.document,
  window = globalThis.window,
  dragState = null,
} = {}) {
  if (!textLayer || !currentRange || !['start', 'end'].includes(endpoint)) return null;
  const caret = stablePdfEndpointCaret(
    textLayer,
    currentRange,
    endpoint,
    clientX,
    clientY,
    { document, dragState },
  );
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
