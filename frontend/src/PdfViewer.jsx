import { useCallback, useEffect, useRef, useState } from 'react';

const WORKER_SRC = '/_addons/incremento/user_files/pdfjs/pdf.worker.min.js';
const ZOOM_STEP  = 0.1;
const ZOOM_MIN   = 0.25;
const ZOOM_MAX   = 4.0;
const POLL_MS    = 100;
const POLL_MAX   = 20;

export default function PdfViewer() {
  const [page,       setPage]       = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [zoom,       setZoom]       = useState(1.0);
  const [error,      setError]      = useState('');

  const pdfDocRef        = useRef(null);
  const busyRef          = useRef(false);
  const activeCvsRef     = useRef('a');
  const cardIdRef        = useRef(null);
  const filenameRef      = useRef(null);
  const pageRef          = useRef(1);
  const zoomRef          = useRef(1.0);
  const lastRenderWidthRef = useRef(0);   // width used in last renderPage call
  const canvasARef       = useRef(null);
  const canvasBRef       = useRef(null);
  const containerRef     = useRef(null);
  const textLayerRef     = useRef(null);

  useEffect(() => { pageRef.current = page; }, [page]);
  useEffect(() => { zoomRef.current = zoom; }, [zoom]);

  /* ── Text layer (PDF.js 4.x) ─────────────────────────────────────────────── */
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
    tl.style.left      = Math.round((wrapperW - viewport.width) / 2) + 'px';
    tl.style.top       = '0px';
    tl.style.transform = 'none';

    try {
      const stream = pg.streamTextContent();
      // PDF.js 4.x: TextLayer class replaces renderTextLayer()
      const task = new lib.TextLayer({ textContentSource: stream, container: tl, viewport });
      tl._cancelTextLayer = () => { try { task.cancel(); } catch (_) {} };
      task.render().then(() => {
        tl.querySelectorAll('span').forEach(span => {
          if (!/\S/.test(span.textContent)) { span.remove(); return; }
          const rect = span.getBoundingClientRect();
          if (rect.width < 2 && rect.height > 0) span.remove();
        });
      }).catch(() => {});
    } catch (_) {}
  }, []);

  /* ── Render page ─────────────────────────────────────────────────────────── */
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
          renderTextLayer(pg, viewport);
        })
        .catch(e => { setError('Render error: ' + e); busyRef.current = false; });
    }).catch(e => { setError('Page error: ' + e); busyRef.current = false; });
  }, [renderTextLayer]);

  /* ── PDF loading ─────────────────────────────────────────────────────────── */
  const doStart = useCallback(() => {
    const lib = window.pdfjsLib;
    lib.GlobalWorkerOptions.workerSrc = WORKER_SRC;
    lib.getDocument('/' + encodeURIComponent(filenameRef.current)).promise
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

  const startViewer = useCallback((cardId, filename, startPage) => {
    cardIdRef.current   = cardId;
    filenameRef.current = filename;
    pageRef.current     = startPage || 1;
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
  }, [renderPage]);

  /* ── Text-layer event isolation (stop Anki intercepting selection events) ── */
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

  /* ── Re-render when container is resized (keeps text layer aligned) ─────── */
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let timer;
    const observer = new ResizeObserver((entries) => {
      const newW = Math.round(entries[0]?.contentRect.width ?? 0);
      // Ignore sub-5px jitter (scrollbars, click events, etc.) — only act on
      // real window resizes so that text selection is never interrupted.
      if (Math.abs(newW - lastRenderWidthRef.current) < 5) return;
      clearTimeout(timer);
      timer = setTimeout(() => {
        if (!busyRef.current && pdfDocRef.current) renderPage(pageRef.current);
      }, 150);
    });
    observer.observe(container);
    return () => { clearTimeout(timer); observer.disconnect(); };
  }, [renderPage]);

  /* ── Register globals ────────────────────────────────────────────────────── */
  useEffect(() => {
    window.incrementoPdfStart = startViewer;
    window.incrementoPdfNav   = nav;
    window.incrementoPdfZoom  = adjustZoom;

    const pending = window._incPdfPending;
    if (pending) {
      window._incPdfPending = null;
      startViewer(pending.cardId, pending.filename, pending.page);
    }
    return () => {
      delete window.incrementoPdfStart;
      delete window.incrementoPdfNav;
      delete window.incrementoPdfZoom;
    };
  }, [startViewer, nav, adjustZoom]);

  /* ── Ctrl+1–4 in JS (real Ctrl key; Cmd handled by Python QShortcut) ────── */
  useEffect(() => {
    const handler = (e) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      const n = parseInt(e.key, 10);
      if (n < 1 || n > 4) return;
      const sel = window.getSelection()?.toString().trim() || '';
      if (!sel) return;
      e.preventDefault();
      window.pycmd('incremento_fill_field:' + JSON.stringify({ idx: n - 1, text: sel }));
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, []);

  /* ── Render ──────────────────────────────────────────────────────────────── */
  return (
    <div style={{ width: '100%' }}>

      {/* Controls */}
      <div id="pdf-controls" style={{ textAlign: 'center', padding: '4px 0' }}>
        <button onClick={() => nav(-1)}>&#8592; Prev</button>
        <span style={{ margin: '0 12px' }}>
          {totalPages > 0 ? `Page ${page} / ${totalPages}` : 'Page \u2014 / \u2014'}
        </span>
        <button onClick={() => nav(1)}>Next &#8594;</button>
        <span style={{ marginLeft: 20 }}>
          <button onClick={() => adjustZoom(-1)}>&#8722;</button>
          <span style={{ margin: '0 8px' }}>{Math.round(zoom * 100)}%</span>
          <button onClick={() => adjustZoom(1)}>&#43;</button>
        </span>
        <button
          style={{ marginLeft: 20 }}
          onClick={() => window.pycmd('incremento_open_add_card')}
        >
          &#43; Add Card
        </button>
      </div>

      {error && (
        <div style={{ color: 'red', padding: '4px 8px', textAlign: 'center' }}>{error}</div>
      )}

      {/* Canvas wrapper — display:block ensures offsetWidth = column width */}
      <div
        id="pdf-canvas-wrapper"
        ref={containerRef}
        style={{ position: 'relative', display: 'block', textAlign: 'center' }}
      >
        <canvas ref={canvasARef} id="pdf-canvas-a"
          style={{ display: 'block', margin: '0 auto', pointerEvents: 'none' }} />
        <canvas ref={canvasBRef} id="pdf-canvas-b"
          style={{ display: 'none', position: 'absolute', top: 0, left: '50%',
                   transform: 'translateX(-50%)', pointerEvents: 'none' }} />
        <div
          ref={textLayerRef}
          id="pdf-text-layer"
          style={{
            position: 'absolute', top: 0, left: 0,
            overflow: 'hidden', lineHeight: 1, zIndex: 2,
            pointerEvents: 'auto',
            userSelect: 'text', WebkitUserSelect: 'text',
            cursor: 'text',
          }}
        />
      </div>
    </div>
  );
}
