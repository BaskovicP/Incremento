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

  // Sidebar state
  const [sidebarOpen,      setSidebarOpen]      = useState(false);
  const [notetypes,        setNotetypes]        = useState([]);
  const [decks,            setDecks]            = useState([]);
  const [selectedNotetype, setSelectedNotetype] = useState('');
  const [selectedDeck,     setSelectedDeck]     = useState('');
  const [fieldValues,      setFieldValues]      = useState([]);
  const [addCardStatus,    setAddCardStatus]     = useState(null);
  const metaLoadedRef = useRef(false);

  // PDF refs
  const pdfDocRef    = useRef(null);
  const busyRef      = useRef(false);
  const activeCvsRef = useRef('a');
  const cardIdRef    = useRef(null);
  const filenameRef  = useRef(null);
  const pageRef      = useRef(1);
  const zoomRef      = useRef(1.0);
  const canvasARef   = useRef(null);
  const canvasBRef   = useRef(null);
  // containerRef: the block-level wrapper; offsetWidth gives the PDF column width reliably
  const containerRef = useRef(null);
  const textLayerRef = useRef(null);

  useEffect(() => { pageRef.current = page; }, [page]);
  useEffect(() => { zoomRef.current = zoom; }, [zoom]);

  // PDF.js 3.x: use streamTextContent() → textContentSource (ReadableStream)
  const renderTextLayer = useCallback((pg, viewport) => {
    const tl  = textLayerRef.current;
    const lib = window.pdfjsLib;
    if (!tl || !lib) return;
    tl.innerHTML    = '';
    tl.style.width  = viewport.width  + 'px';
    tl.style.height = viewport.height + 'px';
    try {
      const stream = pg.streamTextContent({ includeMarkedContent: true });
      const task   = lib.renderTextLayer({ textContentSource: stream, container: tl, viewport });
      if (task?.promise) task.promise.catch(() => {});
      if (task?.cancel) {
        // store cancel fn so we can abort if page changes
        tl._cancelTextLayer = () => { try { task.cancel(); } catch (_) {} };
      }
    } catch (_) {}
  }, []);

  const renderPage = useCallback((num) => {
    const doc = pdfDocRef.current;
    if (busyRef.current || !doc) return;
    busyRef.current = true;

    // Cancel any in-progress text-layer render
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

      // containerRef is display:block → offsetWidth = actual column width
      const colWidth = containerRef.current?.offsetWidth || 800;

      // Fit the full page into the visible viewport (subtract controls + Anki chrome)
      const maxH = Math.max(window.innerHeight - 120, 300);

      const base    = pg.getViewport({ scale: 1 });
      const scaleW  = colWidth / base.width;
      const scaleH  = maxH    / base.height;
      // Use the smaller scale so the whole page is visible; then apply zoom multiplier
      let scale = Math.min(scaleW, scaleH) * zoomRef.current;
      if (!scale || scale <= 0) scale = 1;

      const viewport = pg.getViewport({ scale });
      const dpr      = window.devicePixelRatio || 1;

      backCvs.width        = viewport.width  * dpr;
      backCvs.height       = viewport.height * dpr;
      backCvs.style.width  = viewport.width  + 'px';
      backCvs.style.height = viewport.height + 'px';

      const ctx = backCvs.getContext('2d');
      pg.render({ canvasContext: ctx, viewport, transform: [dpr, 0, 0, dpr, 0, 0] })
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
        if (typeof window.pdfjsLib !== 'undefined') {
          clearInterval(poll);
          doStart();
        } else if (++attempts > POLL_MAX) {
          clearInterval(poll);
          setError('PDF.js failed to load.');
        }
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

  const adjustZoom = useCallback((direction) => {
    if (!pdfDocRef.current) return;
    const next    = zoomRef.current + direction * ZOOM_STEP;
    const clamped = parseFloat(Math.max(ZOOM_MIN, Math.min(next, ZOOM_MAX)).toFixed(2));
    zoomRef.current = clamped;
    setZoom(clamped);
    renderPage(pageRef.current);
  }, [renderPage]);

  // Load note types + decks from Python (once)
  const loadMeta = useCallback(() => {
    if (metaLoadedRef.current) return;
    metaLoadedRef.current = true;
    window.pycmd('incremento_get_notetypes');
    window.pycmd('incremento_get_decks');
  }, []);

  // Register globals
  useEffect(() => {
    window.incrementoPdfStart = startViewer;
    window.incrementoPdfNav   = nav;
    window.incrementoPdfZoom  = adjustZoom;

    window.incrementoReceiveNotetypes = (data) => {
      setNotetypes(data);
      if (data.length) {
        setSelectedNotetype(data[0].name);
        setFieldValues(data[0].fields.map(() => ''));
      }
    };
    window.incrementoReceiveDecks = (data) => {
      setDecks(data);
      if (data.length) setSelectedDeck(data[0]);
    };
    window.incrementoAddCardResult = (ok, msg) => {
      setAddCardStatus({ ok, msg });
      if (ok) setFieldValues(prev => prev.map(() => ''));
    };

    const pending = window._incPdfPending;
    if (pending) {
      window._incPdfPending = null;
      startViewer(pending.cardId, pending.filename, pending.page);
    }

    return () => {
      delete window.incrementoPdfStart;
      delete window.incrementoPdfNav;
      delete window.incrementoPdfZoom;
      delete window.incrementoReceiveNotetypes;
      delete window.incrementoReceiveDecks;
      delete window.incrementoAddCardResult;
    };
  }, [startViewer, nav, adjustZoom]);

  // Re-render when sidebar toggles (column width changed)
  useEffect(() => {
    if (!pdfDocRef.current) return;
    const t = setTimeout(() => { if (!busyRef.current) renderPage(pageRef.current); }, 60);
    return () => clearTimeout(t);
  }, [sidebarOpen, renderPage]);

  // Cmd/Ctrl+1–4 → fill sidebar field from selection
  useEffect(() => {
    const handler = (e) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      const n = parseInt(e.key, 10);
      if (n < 1 || n > 4) return;
      const sel = window.getSelection()?.toString().trim() || '';
      if (!sel) return;
      e.preventDefault();
      setSidebarOpen(true);
      loadMeta();
      setFieldValues(prev => {
        const next = [...prev];
        if (n - 1 < next.length) next[n - 1] = sel;
        return next;
      });
      setAddCardStatus(null);
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [loadMeta]);

  const handleNotetypeChange = useCallback((name) => {
    setSelectedNotetype(name);
    const nt = notetypes.find(n => n.name === name);
    setFieldValues(nt ? nt.fields.map(() => '') : []);
    setAddCardStatus(null);
  }, [notetypes]);

  const handleAddCard = useCallback(() => {
    const nt = notetypes.find(n => n.name === selectedNotetype);
    if (!nt) return;
    const fields = {};
    nt.fields.forEach((fname, i) => { fields[fname] = fieldValues[i] || ''; });
    window.pycmd('incremento_add_card:' + JSON.stringify({
      notetype: selectedNotetype,
      deck:     selectedDeck,
      fields,
    }));
    setAddCardStatus(null);
  }, [notetypes, selectedNotetype, selectedDeck, fieldValues]);

  const currentFields = notetypes.find(n => n.name === selectedNotetype)?.fields ?? [];

  return (
    <div style={{ display: 'flex', width: '100%', alignItems: 'flex-start' }}>

      {/* ── Left: PDF viewer ── */}
      <div style={{ flex: 1, minWidth: 0 }}>

        {/* Controls — rendered FIRST so they appear at the top before PDF loads */}
        <div id="pdf-controls" style={{ textAlign: 'center', padding: '4px 0' }}>
          <button onClick={() => nav(-1)}>&#8592; Prev</button>
          <span id="pdf-page-label" style={{ margin: '0 12px' }}>
            {totalPages > 0 ? `Page ${page} / ${totalPages}` : 'Page \u2014 / \u2014'}
          </span>
          <button onClick={() => nav(1)}>Next &#8594;</button>
          <span style={{ marginLeft: 20 }}>
            <button onClick={() => adjustZoom(-1)}>&#8722;</button>
            <span id="pdf-zoom-label" style={{ margin: '0 8px' }}>
              {Math.round(zoom * 100)}%
            </span>
            <button onClick={() => adjustZoom(1)}>&#43;</button>
          </span>
          <button
            style={{ marginLeft: 20 }}
            onClick={() => { setSidebarOpen(o => !o); loadMeta(); }}
          >
            {sidebarOpen ? '\u2715 Cards' : '\u2630 Cards'}
          </button>
        </div>

        {error && <div id="pdf-error" style={{ color: 'red', padding: '4px 8px', textAlign: 'center' }}>{error}</div>}

        {/* Canvas wrapper: display:block so offsetWidth = column width before first render */}
        <div
          id="pdf-canvas-wrapper"
          ref={containerRef}
          style={{ position: 'relative', display: 'block', textAlign: 'center' }}
        >
          <canvas ref={canvasARef} id="pdf-canvas-a" style={{ display: 'block', margin: '0 auto' }} />
          <canvas
            ref={canvasBRef}
            id="pdf-canvas-b"
            style={{ display: 'none', position: 'absolute', top: 0, left: '50%', transform: 'translateX(-50%)' }}
          />
          <div
            ref={textLayerRef}
            id="pdf-text-layer"
            style={{
              position: 'absolute',
              // centre over the canvas (which is margin:auto inside a block wrapper)
              top: 0,
              left: '50%',
              transform: 'translateX(-50%)',
              overflow: 'hidden',
              lineHeight: 1,
              pointerEvents: 'auto',
              userSelect: 'text',
              WebkitUserSelect: 'text',
            }}
          />
        </div>
      </div>

      {/* ── Right: Add-card sidebar ── */}
      {sidebarOpen && (
        <div
          id="pdf-sidebar"
          style={{
            width: 260, flexShrink: 0, padding: '10px 12px',
            borderLeft: '1px solid #888', overflowY: 'auto',
            fontFamily: 'sans-serif', fontSize: 13,
          }}
        >
          <div style={{ fontWeight: 'bold', marginBottom: 8 }}>Add Card</div>

          <label style={{ display: 'block', marginBottom: 2 }}>Note type</label>
          <select
            value={selectedNotetype}
            onChange={e => handleNotetypeChange(e.target.value)}
            style={{ width: '100%', marginBottom: 8 }}
          >
            {notetypes.map(nt => <option key={nt.name}>{nt.name}</option>)}
          </select>

          <label style={{ display: 'block', marginBottom: 2 }}>Deck</label>
          <select
            value={selectedDeck}
            onChange={e => { setSelectedDeck(e.target.value); setAddCardStatus(null); }}
            style={{ width: '100%', marginBottom: 10 }}
          >
            {decks.map(d => <option key={d}>{d}</option>)}
          </select>

          {currentFields.map((fname, i) => (
            <div key={fname} style={{ marginBottom: 6 }}>
              <label style={{ display: 'block', marginBottom: 2 }}>
                {fname}{' '}
                {i < 4 && <span style={{ color: '#888', fontSize: 11 }}>&#8984;{i + 1}</span>}
              </label>
              <textarea
                value={fieldValues[i] || ''}
                onChange={e => {
                  const v = e.target.value;
                  setFieldValues(prev => { const n = [...prev]; n[i] = v; return n; });
                  setAddCardStatus(null);
                }}
                rows={3}
                style={{ width: '100%', boxSizing: 'border-box', resize: 'vertical' }}
              />
            </div>
          ))}

          {notetypes.length === 0 && (
            <div style={{ color: '#888', marginBottom: 8 }}>Loading\u2026</div>
          )}

          <button
            onClick={handleAddCard}
            style={{ width: '100%', padding: '6px 0', marginTop: 4, cursor: 'pointer' }}
          >
            Add Card
          </button>

          {addCardStatus && (
            <div style={{ marginTop: 6, color: addCardStatus.ok ? 'green' : 'red' }}>
              {addCardStatus.msg}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
