/**
 * usePdfRender — custom hook encapsulating the PDF.js rendering pipeline.
 *
 * Manages: canvas double-buffering, text layer, zoom, navigation, and
 * read-progress tracking. Does NOT touch highlights (caller's concern).
 *
 * Note: startViewer does NOT consume window._incPdfHighlights — the caller
 * (PdfViewer.jsx) must do that before or after calling startViewer.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

const DEFAULT_WORKER_SRC = '/_addons/incremento/web/pdfjs/pdf.worker.min.js';
const ZOOM_STEP = 0.1;
const ZOOM_MIN  = 0.25;
const ZOOM_MAX  = 4.0;
const POLL_MS   = 100;
const POLL_MAX  = 20;

function resolveWorkerSrc(rawWorkerSrc) {
  const fallback = DEFAULT_WORKER_SRC;
  const candidate = String(rawWorkerSrc || fallback).trim();
  if (!candidate) {
    return fallback;
  }
  try {
    return new URL(candidate, window.location.href).toString();
  } catch (_err) {
    return fallback;
  }
}

export function usePdfRender() {
  const [page,       setPage]       = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [zoom,       setZoom]       = useState(1.0);
  const [error,      setError]      = useState('');
  const [renderInfo, setRenderInfo] = useState({ scale: 1, tlLeft: 0 });
  const [readPage,   setReadPage]   = useState(0);

  const pdfDocRef          = useRef(null);
  const busyRef            = useRef(false);
  const activeCvsRef       = useRef('a');
  const cardIdRef          = useRef(null);
  const filenameRef        = useRef(null);
  const pageRef            = useRef(1);
  const zoomRef            = useRef(1.0);
  const lastRenderWidthRef = useRef(0);
  const lastScaleRef       = useRef(1);
  const readPageRef        = useRef(0);
  const canvasARef         = useRef(null);
  const canvasBRef         = useRef(null);
  const containerRef       = useRef(null);
  const textLayerRef       = useRef(null);

  useEffect(() => { pageRef.current = page; }, [page]);
  useEffect(() => { zoomRef.current = zoom; }, [zoom]);

  /* ── Text layer (PDF.js 4.x) ──────────────────────────────────────────────── */
  const renderTextLayer = useCallback((pg, viewport) => {
    const tl  = textLayerRef.current;
    const lib = window.pdfjsLib;
    if (!tl || !lib) return;
    tl.innerHTML = '';

    tl.style.setProperty('--scale-factor', viewport.scale);
    tl.style.width    = viewport.width  + 'px';
    tl.style.height   = viewport.height + 'px';
    tl.style.clipPath = 'inset(0)';

    const wrapperW = containerRef.current?.offsetWidth ?? viewport.width;
    const tlLeft   = Math.round((wrapperW - viewport.width) / 2);
    tl.style.left      = tlLeft + 'px';
    tl.style.top       = '0px';
    tl.style.transform = 'none';

    lastScaleRef.current = viewport.scale;
    setRenderInfo({ scale: viewport.scale, tlLeft, pageWidth: viewport.width });

    try {
      const stream = pg.streamTextContent();
      const task = new lib.TextLayer({ textContentSource: stream, container: tl, viewport });
      tl._cancelTextLayer = () => { try { task.cancel(); } catch (_) {} };
      task.render().then(() => {
        tl.querySelectorAll('span').forEach(span => {
          if (!/\S/.test(span.textContent)) { span.remove(); return; }
          const rect = span.getBoundingClientRect();
          if (rect.width > 0 && rect.width < 3 && rect.height > 0) { span.remove(); return; }
          const sx = parseFloat((span.style.transform || '').match(/scaleX\(([\d.e+-]+)\)/)?.[1]);
          if (!isNaN(sx) && sx < 0.05) { span.remove(); return; }
          const mx = parseFloat((span.style.transform || '').match(/matrix\(([\d.e+-]+)/)?.[1]);
          if (!isNaN(mx) && mx < 0.05) { span.remove(); }
        });
      }).catch(() => {});
    } catch (_) {}
  }, []);

  /* ── Render page ──────────────────────────────────────────────────────────── */
  const renderPage = useCallback((num) => {
    const doc = pdfDocRef.current;
    if (busyRef.current || !doc) return;
    busyRef.current = true;

    if (textLayerRef.current?._cancelTextLayer) {
      textLayerRef.current._cancelTextLayer();
      textLayerRef.current._cancelTextLayer = null;
    }

    doc.getPage(num).then(pg => {
      const backId  = activeCvsRef.current === 'a' ? 'b' : 'a';
      const frontId = activeCvsRef.current;
      const backCvs  = backId  === 'a' ? canvasARef.current : canvasBRef.current;
      const frontCvs = frontId === 'a' ? canvasARef.current : canvasBRef.current;
      if (!backCvs) { busyRef.current = false; return; }

      const colW = containerRef.current?.offsetWidth || 800;
      lastRenderWidthRef.current = colW;
      const maxH = Math.max(window.innerHeight - 120, 300);
      const base = pg.getViewport({ scale: 1 });
      let scale  = Math.min(colW / base.width, maxH / base.height) * zoomRef.current;
      if (!scale || scale <= 0) scale = 1;

      const viewport = pg.getViewport({ scale });
      const dpr      = window.devicePixelRatio || 1;

      backCvs.width        = viewport.width  * dpr;
      backCvs.height       = viewport.height * dpr;
      backCvs.style.width  = viewport.width  + 'px';
      backCvs.style.height = viewport.height + 'px';

      pg.render({ canvasContext: backCvs.getContext('2d'), viewport, transform: [dpr, 0, 0, dpr, 0, 0] })
        .promise
        .then(() => {
          backCvs.style.display  = 'block';
          if (frontCvs) frontCvs.style.display = 'none';
          activeCvsRef.current = backId;
          setPage(num);
          pageRef.current = num;
          busyRef.current = false;
          if (containerRef.current) containerRef.current.style.height = viewport.height + 'px';
          renderTextLayer(pg, viewport);
        })
        .catch(e => { setError('Render error: ' + e); busyRef.current = false; });
    }).catch(e => { setError('Page error: ' + e); busyRef.current = false; });
  }, [renderTextLayer]);

  /* ── PDF loading ──────────────────────────────────────────────────────────── */
  const doStart = useCallback(() => {
    const lib = window.pdfjsLib;
    lib.GlobalWorkerOptions.workerSrc = resolveWorkerSrc(window._pdfWorkerSrc);
    window._pdfWorkerSrc = null;
    const pdfUrl = window._pdfFileUrl || ('/' + encodeURIComponent(filenameRef.current));
    window._pdfFileUrl = null;
    lib.getDocument(pdfUrl).promise
      .then(doc => {
        pdfDocRef.current = doc;
        const total     = doc.numPages;
        const startPage = Math.min(Math.max(pageRef.current, 1), total);
        setTotalPages(total);
        pageRef.current = startPage;
        renderPage(startPage);
      })
      .catch(e => setError('Load error: ' + e));
  }, [renderPage]);

  /**
   * startViewer — initialise state for a new card.
   * NOTE: does NOT touch window._incPdfHighlights — caller must handle that.
   */
  const startViewer = useCallback((cardId, filename, startPage, startZoom, startReadPage = 0) => {
    const normalizedCardId = Number(cardId);
    cardIdRef.current   = Number.isFinite(normalizedCardId) && normalizedCardId > 0 ? normalizedCardId : 0;
    filenameRef.current = filename;
    pageRef.current     = startPage || 1;
    const z = parseFloat(startZoom) || 1.0;
    zoomRef.current = z;
    setZoom(z);
    const rp = parseInt(startReadPage) || 0;
    readPageRef.current = rp;
    setReadPage(rp);
    window._incPdfPending = null;
    if (typeof window.pdfjsLib === 'undefined') {
      let attempts = 0;
      const poll = setInterval(() => {
        if (typeof window.pdfjsLib !== 'undefined') { clearInterval(poll); doStart(); }
        else if (++attempts > POLL_MAX) { clearInterval(poll); setError('PDF.js failed to load.'); }
      }, POLL_MS);
      return;
    }
    doStart();
  }, [doStart]);

  const nav = useCallback((delta) => {
    const doc = pdfDocRef.current;
    if (!doc) return;
    const next = pageRef.current + delta;
    if (next < 1 || next > doc.numPages) return;
    pageRef.current = next;
    window.pycmd('incremento_pdf_nav:' + cardIdRef.current + ':' + next);
    renderPage(next);
  }, [renderPage]);

  const adjustZoom = useCallback((dir) => {
    if (!pdfDocRef.current) return;
    const clamped = parseFloat(Math.max(ZOOM_MIN, Math.min(zoomRef.current + dir * ZOOM_STEP, ZOOM_MAX)).toFixed(2));
    zoomRef.current = clamped;
    setZoom(clamped);
    renderPage(pageRef.current);
    window.pycmd('incremento_pdf_zoom:' + cardIdRef.current + ':' + clamped);
  }, [renderPage]);

  const markRead = useCallback(() => {
    const p   = pageRef.current;
    const cur = readPageRef.current;
    const newRp = (p <= cur) ? 0 : p;
    readPageRef.current = newRp;
    setReadPage(newRp);
    window.pycmd('incremento_pdf_mark_read:' + cardIdRef.current + ':' + newRp);
  }, []);

  /* ── Text-layer event isolation ───────────────────────────────────────────── */
  useEffect(() => {
    const tl = textLayerRef.current;
    if (!tl) return;
    const stop = (e) => e.stopPropagation();
    tl.addEventListener('selectstart', stop);
    tl.addEventListener('mousedown',   stop);
    tl.addEventListener('mouseup',     stop);
    tl.addEventListener('click',       stop);
    return () => {
      tl.removeEventListener('selectstart', stop);
      tl.removeEventListener('mousedown',   stop);
      tl.removeEventListener('mouseup',     stop);
      tl.removeEventListener('click',       stop);
    };
  }, []);

  /* ── Re-render when container is resized ─────────────────────────────────── */
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let timer;
    const observer = new ResizeObserver((entries) => {
      const newW = Math.round(entries[0]?.contentRect.width ?? 0);
      if (Math.abs(newW - lastRenderWidthRef.current) < 5) return;
      clearTimeout(timer);
      timer = setTimeout(() => {
        if (!busyRef.current && pdfDocRef.current) renderPage(pageRef.current);
      }, 150);
    });
    observer.observe(container);
    return () => { clearTimeout(timer); observer.disconnect(); };
  }, [renderPage]);

  return {
    // State (read-only)
    page, totalPages, zoom, error, renderInfo, readPage,
    // Refs attached to DOM elements in JSX
    canvasARef, canvasBRef, containerRef, textLayerRef,
    // Refs read by PdfViewer for keyboard/snapshot/highlight logic
    pdfDocRef, busyRef, activeCvsRef, cardIdRef, pageRef, lastScaleRef,
    // Callbacks
    startViewer, nav, adjustZoom, markRead,
  };
}
