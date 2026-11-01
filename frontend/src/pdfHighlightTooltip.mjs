import {hasAnnotationNote} from './annotationNote.mjs';

const TOOLTIP_MARGIN = 12;
const TOOLTIP_GAP = 16;
const TOOLTIP_WIDTH = 440;
const TOOLTIP_MAX_HEIGHT = 520;
const TOOLTIP_CLOSE_DELAY = 180;

export function pdfHighlightTooltipLayout(anchor, viewportWidth, viewportHeight) {
  const viewWidth = Math.max(1, Number(viewportWidth) || 1);
  const viewHeight = Math.max(1, Number(viewportHeight) || 1);
  const x = Number.isFinite(Number(anchor?.x)) ? Number(anchor.x) : 0;
  const y = Number.isFinite(Number(anchor?.y)) ? Number(anchor.y) : 0;
  const width = Math.max(1, Math.min(TOOLTIP_WIDTH, viewWidth - TOOLTIP_MARGIN * 2));
  const left = Math.max(TOOLTIP_MARGIN,
    Math.min(x + 14, viewWidth - width - TOOLTIP_MARGIN));
  if (y <= viewHeight / 2) {
    const top = Math.max(TOOLTIP_MARGIN, Math.min(y + TOOLTIP_GAP, viewHeight - TOOLTIP_MARGIN));
    return {left, top, width,
      maxHeight: Math.max(1, Math.min(TOOLTIP_MAX_HEIGHT, viewHeight - top - TOOLTIP_MARGIN))};
  }
  const bottom = Math.max(TOOLTIP_MARGIN,
    Math.min(viewHeight - y + TOOLTIP_GAP, viewHeight - TOOLTIP_MARGIN));
  return {left, bottom, width,
    maxHeight: Math.max(1, Math.min(TOOLTIP_MAX_HEIGHT, viewHeight - bottom - TOOLTIP_MARGIN))};
}

export function pdfHighlightTooltipSurfaceStyle(anchor, viewportWidth, viewportHeight) {
  return {
    ...pdfHighlightTooltipLayout(anchor, viewportWidth, viewportHeight),
    overflowY: 'auto',
    overflowX: 'hidden',
    overscrollBehavior: 'contain',
    pointerEvents: 'auto',
  };
}

/** Only the tooltip subscribes; pointer movement never rerenders the reader. */
export function createPdfHighlightTooltip({schedule = run => window.requestAnimationFrame(run),
  cancel = id => window.cancelAnimationFrame(id),
  delay = (run, ms) => globalThis.setTimeout(run, ms),
  cancelDelay = id => globalThis.clearTimeout(id)} = {}) {
  const listeners = new Set();
  let value = null, position = null, frame = null, closeTimer = null;
  const publish = next => {value = next; for (const listener of listeners) listener();};
  const stopMove = () => {if (frame !== null) cancel(frame); frame = null; position = null;};
  const cancelHide = () => {
    if (closeTimer !== null) cancelDelay(closeTimer);
    closeTimer = null;
  };
  const hide = () => {
    cancelHide();
    stopMove();
    if (value) publish(null);
  };
  const scheduleHide = () => {
    cancelHide();
    closeTimer = delay(() => {closeTimer = null; hide();}, TOOLTIP_CLOSE_DELAY);
  };
  return {
    subscribe(listener) {listeners.add(listener); return () => listeners.delete(listener);},
    getSnapshot: () => value,
    show(highlight, event) {
      const note = String(highlight?.note || '').trim();
      if (!hasAnnotationNote(highlight)) return;
      cancelHide();
      stopMove(); publish({id: String(highlight.id || ''), note,
        ...(highlight.note_html ? {html: String(highlight.note_html)} : {}),
        x: Number(event?.clientX || 0), y: Number(event?.clientY || 0)});
    },
    move(event) {
      if (!value) return;
      position = {x: Number(event?.clientX ?? value.x), y: Number(event?.clientY ?? value.y)};
      if (frame === null) frame = schedule(() => {
        frame = null;
        if (value && position) publish({...value, ...position});
        position = null;
      });
    },
    cancelHide,
    scheduleHide,
    hide,
  };
}
