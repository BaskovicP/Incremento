import {retainPdfPage, releasePdfPage, estimatePdfPageBytes} from './pdfPageResources.mjs';

/** One idle page at a time, within both a moving ±5 window and a memory budget. */
export function createPdfPageWindow(doc, {schedule, cancel, createCanvas = () => document.createElement('canvas'),
  maxBytes = 64 * 1024 * 1024, estimateBytes = estimatePdfPageBytes}) {
  const held = new Map();
  const owner = {};
  let generation = 0, timer = null, busy = false, active = false, closed = false, center = 1;
  let visible = true;
  let pending = [];
  let warming = null;
  const remove = (number, page) => {held.delete(number); releasePdfPage(page, owner);};
  const bytes = () => [...held.values()].reduce((total, page) => total + estimateBytes(page), 0);
  const trim = () => {
    let memoryPressure = false;
    for (const [number, page] of [...held].sort(([a], [b]) => Math.abs(b - center) - Math.abs(a - center))) {
      if (number === center) continue;
      const overBudget = bytes() > maxBytes;
      if (!visible || Math.abs(number - center) > 5 || overBudget) {
        memoryPressure ||= overBudget;
        remove(number, page);
      }
    }
    return memoryPressure;
  };
  const pause = () => {
    ++generation; active = false;
    if (timer !== null) cancel(timer);
    timer = null; pending = [];
    try {warming?.cancel();} catch (_) {}
  };
  const enqueue = () => {
    if (closed || !visible || !active || busy || timer !== null || !pending.length) return;
    // Leave headroom before decoding another potentially large scan. The active
    // page is always retained, even when a single page exceeds the budget.
    if (bytes() + 8 * 1024 * 1024 > maxBytes) {pending = []; return;}
    timer = schedule(async () => {
      timer = null;
      if (!active || closed) return;
      const token = generation, number = pending.shift();
      busy = true;
      let page, canvas;
      const preparation = {};
      try {
        page = await doc.getPage(number);
        if (token !== generation || !active || closed) return;
        retainPdfPage(page, preparation);
        // getOperatorList uses a separate PDF.js intent/cache. A tiny display
        // render warms the exact image/operator resources used on page turns.
        if (typeof page.render === 'function') {
          const base = page.getViewport({scale: 1});
          const viewport = page.getViewport({scale: Math.min(32 / base.width, 32 / base.height)});
          canvas = createCanvas();
          canvas.width = Math.max(1, Math.ceil(viewport.width));
          canvas.height = Math.max(1, Math.ceil(viewport.height));
          warming = page.render({canvasContext: canvas.getContext('2d'), viewport});
          await warming.promise;
        } else await page.getOperatorList?.();
        if (token === generation && active && !closed) {
          retainPdfPage(page, owner); held.set(number, page);
          if (trim()) pending = [];
        }
      } catch (_) { /* A damaged neighbor must never block the current page. */ }
      finally {
        warming = null;
        if (canvas) canvas.width = canvas.height = 0;
        if (page) releasePdfPage(page, preparation);
        busy = false; enqueue();
      }
    });
  };
  return {
    pause,
    has: page => held.get(page.pageNumber) === page,
    display(page) {
      if (closed) return;
      pause(); active = true; center = page.pageNumber;
      retainPdfPage(page, owner);
      held.set(center, page);
      trim();
      for (let distance = 1; distance <= 5; distance++) {
        for (const number of [center + distance, center - distance]) {
          if (number >= 1 && number <= doc.numPages && !held.has(number)) pending.push(number);
        }
      }
      enqueue();
    },
    setVisible(value) {
      visible = Boolean(value);
      if (!visible) {pause(); trim();}
      else if (held.has(center)) this.display(held.get(center));
    },
    dispose() {
      pause(); closed = true;
      for (const page of held.values()) releasePdfPage(page, owner);
      held.clear();
    },
  };
}
