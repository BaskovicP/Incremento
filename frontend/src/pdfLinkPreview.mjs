import {retainPdfPage, releasePdfPage, estimatePdfPageBytes} from './pdfPageResources.mjs';
import {pdfPageTextContent} from './pdfTextCache.mjs';

export const DEFAULT_PDF_LINK_PREVIEW_ZOOM = 1.5;
const MAX_WIDTH = 4096;
const MAX_HEIGHT = 640;
const MAX_PIXELS = 4 * 1024 * 1024;
const CONTEXT = 24;
const CACHE_SIZE = 4;
const CACHE_BYTES = 32 * 1024 * 1024;

export function normalizePdfLinkPreviewZoom(raw) {
  const value = typeof raw === 'number' || (typeof raw === 'string' && raw.trim()) ? Number(raw) : NaN;
  return Number.isFinite(value)
    ? Math.round(Math.max(1, Math.min(4, value)) * 4) / 4 : DEFAULT_PDF_LINK_PREVIEW_ZOOM;
}

export function normalizePdfLinkPreviewSize(raw) {
  if (!raw || !['width', 'height'].every(key => typeof raw[key] === 'number'
      && Number.isFinite(raw[key]) && raw[key] > 0)) return null;
  return {width: Math.round(Math.min(4096, Math.max(280, raw.width))),
    height: Math.round(Math.min(4096, Math.max(160, raw.height)))};
}

export function pdfLinkPreviewLayout(size, anchor, viewportWidth, viewportHeight) {
  const preferred = normalizePdfLinkPreviewSize(size) || {width: 560, height: 360};
  const width = Math.max(1, Math.min(preferred.width, viewportWidth - 24));
  const height = Math.max(1, Math.min(preferred.height, viewportHeight - 24));
  const left = Math.max(12, Math.min(anchor.x - 24, viewportWidth - width - 12));
  const top = anchor.y + height + 20 < viewportHeight
    ? anchor.y + 20 : Math.max(12, anchor.y - height - 20);
  return {width, height, left, top,
    maxWidth: Math.max(1, viewportWidth - left - 12),
    maxHeight: Math.max(1, viewportHeight - top - 12)};
}

export function pdfLinkAtPoint(links, x, y) {
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return links.find(link => link.kind === 'internal'
    && x >= link.left && x <= link.left + link.width
    && y >= link.top && y <= link.top + link.height) || null;
}

export function pdfPreviewRegion(page, destination, pixelRatio = 1, zoom = DEFAULT_PDF_LINK_PREVIEW_ZOOM) {
  const scale = normalizePdfLinkPreviewZoom(zoom);
  const viewport = page.getViewport({scale});
  if (![viewport.width, viewport.height].every(value => Number.isFinite(value) && value > 0)) return null;
  const type = destination?.[1]?.name;
  const rawX = type === 'XYZ' || type === 'FitR' || type === 'FitV' || type === 'FitBV' ? destination[2] : null;
  const rawY = type === 'XYZ' ? destination[3]
    : type === 'FitH' || type === 'FitBH' ? destination[2]
      : type === 'FitR' ? destination[5] : null;
  let x = 0, y = 0;
  if (Number.isFinite(rawX) || Number.isFinite(rawY)) {
    // Null means unspecified, not PDF coordinate zero (which is the bottom).
    const view = page.view || [0, 0, viewport.width / scale, viewport.height / scale];
    [x, y] = viewport.convertToViewportPoint(
      Number.isFinite(rawX) ? rawX : view[0], Number.isFinite(rawY) ? rawY : view[3],
    );
  }
  const width = Math.min(MAX_WIDTH, Math.ceil(viewport.width));
  const left = Math.max(0, Math.min(Number.isFinite(x) ? x - CONTEXT : 0, viewport.width - width));
  const top = Math.max(0, Math.min(Number.isFinite(y) ? y - CONTEXT : 0, viewport.height - CONTEXT));
  const height = Math.min(MAX_HEIGHT, Math.ceil(viewport.height - top));
  return {viewport, left, top, width, height,
    scrollLeft: Math.max(0, x - left - CONTEXT),
    pixelRatio: Math.max(1, Math.min(2, Number(pixelRatio) || 1, Math.sqrt((MAX_PIXELS - 16384) / (width * height))))};
}

function previewText(content, region) {
  const text = [];
  let length = 0;
  for (const item of (content?.items || []).slice(0, 20000)) {
    if (!item.str || !item.transform?.slice(4, 6).every(Number.isFinite)) continue;
    const [x, y] = region.viewport.convertToViewportPoint(item.transform[4], item.transform[5]);
    if (x < region.left || x > region.left + region.width || y < region.top || y > region.top + region.height) continue;
    text.push(String(item.str).slice(0, 6000 - length));
    length += String(item.str).length + 1;
    if (length >= 6000) break;
  }
  return text.join(' ');
}

// One render at a time, bounded pixel surfaces/cache, no navigation or bridge
// access. A sequence invalidates both page-loading and canvas-render callbacks.
export function createPdfPreviewRenderer({createCanvas, onChange, pixelRatio = 1, zoom: initialZoom}) {
  let sequence = 0, task = null, document = null;
  let zoom = normalizePdfLinkPreviewZoom(initialZoom), activeRequest = null;
  const cache = new Map();
  const release = entry => {
    entry.canvas.width = entry.canvas.height = 0;
    releasePdfPage(entry.page, entry.owner);
  };
  const clearCache = () => {for (const entry of cache.values()) release(entry); cache.clear();};
  const clear = () => {
    ++sequence;
    try { task?.cancel(); } catch (_) {}
    task = null;
    activeRequest = null;
    onChange(null);
  };
  const dispose = () => {clear(); clearCache(); document = null;};
  const renderer = {
    clear, dispose,
    setZoom(value) {
      const next = normalizePdfLinkPreviewZoom(value);
      if (next === zoom) return;
      zoom = next;
      if (activeRequest) return renderer.show(...activeRequest);
    },
    async show(doc, link, anchor, maxPage = null) {
      clear();
      if (doc !== document) {clearCache(); document = doc;}
      if (!doc || link?.kind !== 'internal' || !Number.isInteger(link.targetPage)
          || link.targetPage < 1 || link.targetPage > doc.numPages) return;
      const current = sequence;
      const state = {link, anchor};
      activeRequest = [doc, link, anchor, maxPage];
      if (maxPage != null && link.targetPage > maxPage) {
        onChange({...state, status: 'limited'});
        return;
      }
      const key = JSON.stringify([link.targetPage, link.destination, zoom]);
      if (cache.has(key)) {
        const entry = cache.get(key);
        cache.delete(key); cache.set(key, entry);
        onChange({...state, ...entry.result, status: 'ready'});
        return;
      }
      onChange({...state, status: 'loading'});
      let page, canvas, cached = false;
      const owner = {};
      try {
        page = await doc.getPage(link.targetPage);
        retainPdfPage(page, owner);
        if (current !== sequence) return;
        const region = pdfPreviewRegion(page, link.destination, pixelRatio, zoom);
        if (!region) throw new Error('Invalid preview region');
        canvas = createCanvas();
        const dpr = region.pixelRatio;
        canvas.width = Math.ceil(region.width * dpr);
        canvas.height = Math.ceil(region.height * dpr);
        const rendering = page.render({canvasContext: canvas.getContext('2d'), viewport: region.viewport,
          transform: [dpr, 0, 0, dpr, (0 - region.left) * dpr, (0 - region.top) * dpr]});
        task = rendering;
        const content = pdfPageTextContent(page).catch(() => null);
        await rendering.promise;
        if (current !== sequence) return;
        task = null;
        const result = {canvas, region, text: ''};
        cache.set(key, {result, canvas, page, owner,
          bytes: canvas.width * canvas.height * 4 + estimatePdfPageBytes(page)});
        cached = true;
        let bytes = [...cache.values()].reduce((sum, entry) => sum + entry.bytes, 0);
        while (cache.size > 1 && (cache.size > CACHE_SIZE || bytes > CACHE_BYTES)) {
          const oldest = cache.keys().next().value, entry = cache.get(oldest);
          cache.delete(oldest); bytes -= entry.bytes; release(entry);
        }
        onChange({...state, ...result, status: 'ready'});
        // Text is an accessible equivalent; it must never hold up the image.
        const textContent = await content;
        if (current !== sequence) return;
        result.text = previewText(textContent, region);
        onChange({...state, ...result, status: 'ready'});
      } catch (_) {
        if (current === sequence) {task = null; onChange({...state, status: 'unavailable'});}
      } finally {
        if (!cached) {
          if (canvas) canvas.width = canvas.height = 0;
          if (page) releasePdfPage(page, owner);
        }
      }
    },
  };
  return renderer;
}

// Passive listeners leave native selection and opt-in link activation alone.
export function attachPdfLinkPreview({container, popup, host, links, tlLeft, doc, preview, maxPage = null, onResize}) {
  let active = null, dismissed = null, timer = null, interacting = false, initialSize = null;
  const cancelClose = () => {if (timer != null) host.clearTimeout(timer); timer = null;};
  const close = () => {cancelClose(); active = null; interacting = false; initialSize = null; preview.clear();};
  const scheduleClose = () => {if (!interacting && timer == null) timer = host.setTimeout(close, 180);};
  const leave = () => {dismissed = null; scheduleClose();};
  const open = (link, x, y) => {
    cancelClose();
    if (dismissed && dismissed !== link) dismissed = null;
    if (link === active || link === dismissed) return;
    active = link;
    void preview.show(doc, link, {x, y}, maxPage);
  };
  const move = event => {
    if (interacting) return;
    if (event.buttons || event.pointerType === 'touch') {if (active) close(); return;}
    const rect = container.getBoundingClientRect();
    const link = pdfLinkAtPoint(links, event.clientX - rect.left - tlLeft, event.clientY - rect.top);
    if (link) open(link, event.clientX, event.clientY);
    else {dismissed = null; scheduleClose();}
  };
  const focus = event => {
    const target = event.target.closest?.('[data-pdf-link-index]');
    const link = links[Number(target?.dataset.pdfLinkIndex)];
    if (!target || link?.kind !== 'internal') return;
    const rect = target.getBoundingClientRect();
    open(link, rect.left, rect.bottom);
  };
  const key = event => {if (event.key === 'Escape' && active) {dismissed = active; close();}};
  const scroll = event => {if (!popup.contains(event.target)) close();};
  const pointerDown = event => {
    if (!popup.contains(event.target)) {close(); return;}
    interacting = true;
    initialSize = popup.getBoundingClientRect();
    cancelClose();
  };
  const pointerUp = event => {
    if (!interacting) return;
    interacting = false;
    const rect = popup.getBoundingClientRect();
    const size = normalizePdfLinkPreviewSize(rect);
    if (size && initialSize && (rect.width !== initialSize.width || rect.height !== initialSize.height)) {
      onResize?.(size);
    }
    initialSize = null;
    if (!popup.contains(event.target)) scheduleClose();
  };
  const pointerCancel = event => {initialSize = null; pointerUp(event);};
  const listeners = [
    [container, 'pointermove', move], [container, 'pointerleave', leave],
    [container, 'focusin', focus], [container, 'focusout', scheduleClose],
    [popup, 'pointerenter', cancelClose], [popup, 'pointerleave', scheduleClose],
    [popup, 'focusin', cancelClose], [popup, 'focusout', scheduleClose],
    [host, 'keydown', key], [host, 'scroll', scroll], [host, 'resize', close],
    [host, 'blur', close], [host, 'pointerdown', pointerDown],
    [host, 'pointerup', pointerUp], [host, 'pointercancel', pointerCancel],
  ];
  // Enter/leave and window blur must target the surface itself. Capturing them
  // would treat transitions between text spans or popup controls as leaving it.
  const capture = name => !['pointerenter', 'pointerleave', 'blur'].includes(name);
  for (const [target, name, callback] of listeners) target.addEventListener(name, callback, capture(name));
  return () => {
    cancelClose();
    for (const [target, name, callback] of listeners) target.removeEventListener(name, callback, capture(name));
    close();
  };
}
