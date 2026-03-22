import { useCallback, useEffect, useRef, useState } from 'react';

const DEFAULT_WORKER_SRC = '/_addons/incremento/user_files/pdfjs/pdf.worker.min.js';
const ZOOM_STEP  = 0.1;
const ZOOM_MIN   = 0.25;
const ZOOM_MAX   = 4.0;
const POLL_MS    = 100;
const POLL_MAX   = 20;

const HL_COLORS = {
  yellow: 'rgba(255,220,0,0.45)',
  green:  'rgba(0,200,80,0.4)',
  blue:   'rgba(30,144,255,0.4)',
  pink:   'rgba(255,80,140,0.4)',
};
const HL_SOLID = {
  yellow: '#FFE000',
  green:  '#00C850',
  blue:   '#1E90FF',
  pink:   '#FF508C',
};

export default function PdfViewer() {
  const [page,        setPage]        = useState(1);
  const [totalPages,  setTotalPages]  = useState(0);
  const [zoom,        setZoom]        = useState(1.0);
  const [error,       setError]       = useState('');
  const [highlights,     setHighlights]     = useState([]);
  const [hlColor,        setHlColor]        = useState('yellow');
  const [renderInfo,     setRenderInfo]     = useState({ scale: 1, tlLeft: 0 });
  const [autoHighlight,  setAutoHighlight]  = useState(false);

  const pdfDocRef          = useRef(null);
  const busyRef            = useRef(false);
  const activeCvsRef       = useRef('a');
  const cardIdRef          = useRef(null);
  const filenameRef        = useRef(null);
  const pageRef            = useRef(1);
  const zoomRef            = useRef(1.0);
  const lastRenderWidthRef = useRef(0);
  const lastScaleRef       = useRef(1);
  const hlColorRef         = useRef('yellow');
  const autoHighlightRef   = useRef(false);
  const canvasARef         = useRef(null);
  const canvasBRef         = useRef(null);
  const containerRef       = useRef(null);
  const textLayerRef       = useRef(null);

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
    const tlLeft   = Math.round((wrapperW - viewport.width) / 2);
    tl.style.left      = tlLeft + 'px';
    tl.style.top       = '0px';
    tl.style.transform = 'none';

    // Expose current scale + offset so highlight overlay re-renders correctly
    lastScaleRef.current = viewport.scale;
    setRenderInfo({ scale: viewport.scale, tlLeft });

    try {
      const stream = pg.streamTextContent();
      const task = new lib.TextLayer({ textContentSource: stream, container: tl, viewport });
      tl._cancelTextLayer = () => { try { task.cancel(); } catch (_) {} };
      task.render().then(() => {
        tl.querySelectorAll('span').forEach(span => {
          // Remove whitespace-only spans
          if (!/\S/.test(span.textContent)) { span.remove(); return; }
          // Remove spans that are visually almost invisible (< 3px wide)
          const rect = span.getBoundingClientRect();
          if (rect.width > 0 && rect.width < 3 && rect.height > 0) { span.remove(); return; }
          // Remove column-separator spans: text compressed to < 5% of normal width
          const sx = parseFloat((span.style.transform || '').match(/scaleX\(([\d.e+-]+)\)/)?.[1]);
          if (!isNaN(sx) && sx < 0.05) { span.remove(); return; }
          // Also handle matrix() form: matrix(a, b, c, d, tx, ty) — a is scaleX
          const mx = parseFloat((span.style.transform || '').match(/matrix\(([\d.e+-]+)/)?.[1]);
          if (!isNaN(mx) && mx < 0.05) { span.remove(); }
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
    lib.GlobalWorkerOptions.workerSrc = window._pdfWorkerSrc || DEFAULT_WORKER_SRC;
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

  const startViewer = useCallback((cardId, filename, startPage, startZoom) => {
    cardIdRef.current   = cardId;
    filenameRef.current = filename;
    pageRef.current     = startPage || 1;
    const z = parseFloat(startZoom) || 1.0;
    zoomRef.current = z;
    setZoom(z);
    setHighlights(window._incPdfHighlights || []);
    window._incPdfHighlights = null;
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

  const deleteHighlight = useCallback((id) => {
    setHighlights(prev => prev.filter(h => h.id !== id));
    window.pycmd('incremento_pdf_hl_del:' + JSON.stringify({ cardId: cardIdRef.current, id }));
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

  /* ── Register globals ────────────────────────────────────────────────────── */
  useEffect(() => {
    window.incrementoPdfStart = startViewer;
    window.incrementoPdfNav   = nav;
    window.incrementoPdfZoom  = adjustZoom;

    const pending = window._incPdfPending;
    if (pending) {
      window._incPdfPending = null;
      startViewer(pending.cardId, pending.filename, pending.page, pending.zoom);
    }
    return () => {
      delete window.incrementoPdfStart;
      delete window.incrementoPdfNav;
      delete window.incrementoPdfZoom;
    };
  }, [startViewer, nav, adjustZoom]);

  /* ── Ctrl+1–4 fill field  /  Option+H highlight ─────────────────────────── */
  useEffect(() => {
    const makeHighlight = (sel) => {
      if (!sel || sel.isCollapsed || !sel.rangeCount) return;
      const tl = textLayerRef.current;
      const range = sel.getRangeAt(0);
      if (!tl || !tl.contains(range.commonAncestorContainer)) return;
      const tlRect = tl.getBoundingClientRect();
      const scale  = lastScaleRef.current;
      const rects  = Array.from(range.getClientRects())
        .map(r => ({
          x: (r.left - tlRect.left) / scale,
          y: (r.top  - tlRect.top)  / scale,
          w: r.width  / scale,
          h: r.height / scale,
        }))
        .filter(r => r.w > 2 && r.h > 2);
      if (!rects.length) return;
      const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
      const hl = { id, page: pageRef.current, color: hlColorRef.current,
                   text: sel.toString(), rects };
      setHighlights(prev => [...prev, hl]);
      window.pycmd('incremento_pdf_hl_add:' + JSON.stringify({ cardId: cardIdRef.current, highlight: hl }));
    };

    const handler = (e) => {
      // Option/Alt+H — highlight current selection
      if (e.altKey && e.code === 'KeyH') {
        const sel = window.getSelection();
        if (!sel || sel.isCollapsed || !sel.rangeCount) return;
        const tl = textLayerRef.current;
        if (!tl || !tl.contains(sel.getRangeAt(0).commonAncestorContainer)) return;
        e.preventDefault();
        makeHighlight(sel);
        sel.removeAllRanges();
        return;
      }

      // Cmd/Ctrl+1–4 — fill Add Card field (+ auto-highlight if enabled)
      if (!(e.metaKey || e.ctrlKey)) return;
      const n = parseInt(e.key, 10);
      if (n < 1 || n > 4) return;
      const selObj  = window.getSelection();
      const selText = selObj?.toString().trim() || '';
      if (!selText) return;
      e.preventDefault();
      if (autoHighlightRef.current) makeHighlight(selObj);
      window.pycmd('incremento_fill_field:' + JSON.stringify({ idx: n - 1, text: selText }));
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, []);

  /* ── Highlights for current page ─────────────────────────────────────────── */
  const pageHighlights = highlights.filter(h => h.page === page);

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

        {/* Highlight color picker */}
        <span style={{ marginLeft: 20, verticalAlign: 'middle' }}>
          {Object.keys(HL_COLORS).map(c => (
            <button
              key={c}
              title={`Highlight ${c}`}
              onClick={() => { hlColorRef.current = c; setHlColor(c); }}
              style={{
                marginLeft: 3,
                background: HL_SOLID[c],
                border: hlColor === c ? '2px solid white' : '2px solid transparent',
                width: 18, height: 18,
                borderRadius: 3, padding: 0, cursor: 'pointer',
                verticalAlign: 'middle',
              }}
            />
          ))}
        </span>

        <button
          style={{ marginLeft: 20 }}
          onClick={() => window.pycmd('incremento_open_add_card')}
        >
          &#43; Add Card
        </button>

        <label style={{ marginLeft: 16, fontSize: 12, cursor: 'pointer',
                        userSelect: 'none', verticalAlign: 'middle' }}>
          <input
            type="checkbox"
            checked={autoHighlight}
            onChange={e => { autoHighlightRef.current = e.target.checked; setAutoHighlight(e.target.checked); }}
            style={{ marginRight: 4, verticalAlign: 'middle' }}
          />
          Highlight when extracting
        </label>
      </div>

      {error && (
        <div style={{ color: 'red', padding: '4px 8px', textAlign: 'center' }}>{error}</div>
      )}

      {/* Canvas wrapper */}
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

        {/* Highlight rects — below text layer (z:1), non-blocking */}
        {pageHighlights.map(h =>
          h.rects.map((r, ri) => (
            <div
              key={`${h.id}-${ri}`}
              style={{
                position:    'absolute',
                left:        renderInfo.tlLeft + r.x * renderInfo.scale,
                top:         r.y * renderInfo.scale,
                width:       r.w * renderInfo.scale,
                height:      r.h * renderInfo.scale,
                background:  HL_COLORS[h.color] || HL_COLORS.yellow,
                mixBlendMode:'multiply',
                pointerEvents: 'none',
                zIndex: 1,
              }}
            />
          ))
        )}

        {/* Delete buttons — above text layer (z:10), one per highlight group */}
        {pageHighlights.map(h => {
          if (!h.rects.length) return null;
          const r = h.rects[0];
          return (
            <button
              key={`del-${h.id}`}
              title="Remove highlight"
              onClick={() => deleteHighlight(h.id)}
              style={{
                position:  'absolute',
                left:      renderInfo.tlLeft + (r.x + r.w) * renderInfo.scale - 8,
                top:       r.y * renderInfo.scale - 8,
                width: 16, height: 16,
                fontSize: 10, lineHeight: '16px', textAlign: 'center',
                padding: 0, border: 'none',
                background: 'rgba(80,80,80,0.85)', color: '#fff',
                borderRadius: '50%', cursor: 'pointer',
                zIndex: 10,
              }}
            >
              ×
            </button>
          );
        })}

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
