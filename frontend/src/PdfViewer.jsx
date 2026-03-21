import { useCallback, useEffect, useRef, useState } from 'react';

const WORKER_SRC    = '/_addons/incremento/user_files/pdfjs/pdf.worker.min.js';
const ZOOM_STEP     = 0.1;
const ZOOM_MIN      = 0.25;
const ZOOM_MAX      = 4.0;
const POLL_MS       = 100;
const POLL_MAX      = 20;
const SIDEBAR_MIN_W = 220;
const SIDEBAR_MAX_W = 700;
const SIDEBAR_DEF_W = 340;

/* ─────────────────────────────────────────────────────────────────────────────
   Tiny sub-components
───────────────────────────────────────────────────────────────────────────── */

function FieldRow({ fname, index, value, collapsed, pinned, onToggleCollapse, onTogglePin, onChange }) {
  const shortcut = index < 4 ? `⌘${index + 1}` : null;
  return (
    <div style={{ borderBottom: '1px solid #3a3a3a' }}>
      {/* header row */}
      <div
        onClick={onToggleCollapse}
        style={{
          display: 'flex', alignItems: 'center', padding: '7px 12px',
          cursor: 'pointer', userSelect: 'none', gap: 6,
        }}
      >
        <span style={{ color: '#888', fontSize: 11, width: 10, flexShrink: 0 }}>
          {collapsed ? '›' : '∨'}
        </span>
        <span style={{ flex: 1, fontSize: 13, color: '#d0d0d0' }}>{fname}</span>
        {shortcut && (
          <span style={{ color: '#555', fontSize: 10 }}>{shortcut}</span>
        )}
        {/* pin icon — stops collapse toggle from firing */}
        <span
          title={pinned ? 'Unpin field (value clears on add)' : 'Pin field (value persists after add)'}
          onClick={e => { e.stopPropagation(); onTogglePin(); }}
          style={{ color: pinned ? '#f0c040' : '#555', fontSize: 14, cursor: 'pointer', lineHeight: 1 }}
        >
          {pinned ? '★' : '☆'}
        </span>
      </div>

      {/* textarea */}
      {!collapsed && (
        <div style={{ padding: '0 10px 10px 10px' }}>
          <textarea
            value={value}
            onChange={e => onChange(e.target.value)}
            rows={3}
            style={{
              width: '100%', boxSizing: 'border-box', resize: 'vertical',
              background: '#3b3b3b', border: '1px solid #505050',
              borderRadius: 3, color: '#e0e0e0', padding: '6px 8px',
              fontSize: 13, lineHeight: 1.45, outline: 'none',
              fontFamily: 'inherit',
            }}
            onFocus={e => { e.target.style.borderColor = '#6a8fce'; }}
            onBlur={e  => { e.target.style.borderColor = '#505050'; }}
          />
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   Main component
───────────────────────────────────────────────────────────────────────────── */

export default function PdfViewer() {
  /* PDF state */
  const [page,       setPage]       = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [zoom,       setZoom]       = useState(1.0);
  const [error,      setError]      = useState('');

  /* Sidebar state */
  const [sidebarOpen,       setSidebarOpen]       = useState(false);
  const [sidebarWidth,      setSidebarWidth]       = useState(SIDEBAR_DEF_W);
  const [notetypes,         setNotetypes]          = useState([]);
  const [decks,             setDecks]              = useState([]);
  const [selectedNotetype,  setSelectedNotetype]   = useState('');
  const [selectedDeck,      setSelectedDeck]       = useState('');
  const [fieldValues,       setFieldValues]        = useState([]);
  const [collapsedFields,   setCollapsedFields]    = useState(new Set());
  const [pinnedFields,      setPinnedFields]       = useState(new Set());
  const [addCardStatus,     setAddCardStatus]      = useState(null);

  /* Refs */
  const metaLoadedRef    = useRef(false);
  const pinnedFieldsRef  = useRef(new Set());  // mirror of pinnedFields for callbacks
  const sidebarWidthRef  = useRef(SIDEBAR_DEF_W);

  const pdfDocRef    = useRef(null);
  const busyRef      = useRef(false);
  const activeCvsRef = useRef('a');
  const cardIdRef    = useRef(null);
  const filenameRef  = useRef(null);
  const pageRef      = useRef(1);
  const zoomRef      = useRef(1.0);
  const canvasARef   = useRef(null);
  const canvasBRef   = useRef(null);
  const containerRef = useRef(null);
  const textLayerRef = useRef(null);

  useEffect(() => { pageRef.current = page; }, [page]);
  useEffect(() => { zoomRef.current = zoom; }, [zoom]);

  /* ── Text layer (PDF.js 3.x) ─────────────────────────────────────────────── */
  const renderTextLayer = useCallback((pg, viewport) => {
    const tl  = textLayerRef.current;
    const lib = window.pdfjsLib;
    if (!tl || !lib) return;
    tl.innerHTML = '';

    // Required by PDF.js 3.x: setLayerDimensions() uses this CSS var for
    // width/height, and every span transform resolves through it.
    tl.style.setProperty('--scale-factor', viewport.scale);

    // Align precisely with the centered canvas (margin:0 auto on a block wrapper).
    const wrapperW = containerRef.current?.offsetWidth ?? viewport.width;
    tl.style.left      = Math.round((wrapperW - viewport.width) / 2) + 'px';
    tl.style.top       = '0px';
    tl.style.transform = 'none';

    try {
      const stream = pg.streamTextContent({ includeMarkedContent: true });
      const task   = lib.renderTextLayer({ textContentSource: stream, container: tl, viewport });
      if (task?.promise) task.promise.catch(() => {});
      if (task?.cancel)  tl._cancelTextLayer = () => { try { task.cancel(); } catch (_) {} };
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

      const colW  = containerRef.current?.offsetWidth || 800;
      const maxH  = Math.max(window.innerHeight - 120, 300);
      const base  = pg.getViewport({ scale: 1 });
      let scale   = Math.min(colW / base.width, maxH / base.height) * zoomRef.current;
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

  /* ── Sidebar resize ──────────────────────────────────────────────────────── */
  const startResize = useCallback((e) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = sidebarWidthRef.current;
    const onMove = (ev) => {
      // sidebar is on left: dragging right makes it wider
      const newW = Math.max(SIDEBAR_MIN_W, Math.min(SIDEBAR_MAX_W, startW + ev.clientX - startX));
      sidebarWidthRef.current = newW;
      setSidebarWidth(newW);
    };
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup',   onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup',   onUp);
  }, []);

  /* ── Metadata loading ────────────────────────────────────────────────────── */
  const loadMeta = useCallback(() => {
    if (metaLoadedRef.current) return;
    metaLoadedRef.current = true;
    window.pycmd('incremento_get_notetypes');
    window.pycmd('incremento_get_decks');
  }, []);

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

  /* ── Register globals ────────────────────────────────────────────────────── */
  useEffect(() => {
    window.incrementoPdfStart = startViewer;
    window.incrementoPdfNav   = nav;
    window.incrementoPdfZoom  = adjustZoom;

    window.incrementoReceiveNotetypes = (data) => {
      setNotetypes(data);
      if (data.length) {
        setSelectedNotetype(data[0].name);
        setFieldValues(data[0].fields.map(() => ''));
        setCollapsedFields(new Set());
      }
    };
    window.incrementoReceiveDecks = (data) => {
      setDecks(data);
      if (data.length) setSelectedDeck(data[0]);
    };
    window.incrementoAddCardResult = (ok, msg) => {
      setAddCardStatus({ ok, msg });
      if (ok) {
        // Clear unpinned fields; keep pinned values for the next card
        setFieldValues(prev => prev.map((v, i) => pinnedFieldsRef.current.has(i) ? v : ''));
        setTimeout(() => setAddCardStatus(null), 2500);
      }
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

  /* ── Re-render PDF when sidebar opens/closes ─────────────────────────────── */
  useEffect(() => {
    if (!pdfDocRef.current) return;
    const t = setTimeout(() => { if (!busyRef.current) renderPage(pageRef.current); }, 60);
    return () => clearTimeout(t);
  }, [sidebarOpen, sidebarWidth, renderPage]);

  /* ── Cmd/Ctrl+1–4 → fill field from selection ───────────────────────────── */
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
      // Un-collapse the target field so the user sees the result
      setCollapsedFields(prev => { const next = new Set(prev); next.delete(n - 1); return next; });
      setFieldValues(prev => { const next = [...prev]; if (n - 1 < next.length) next[n - 1] = sel; return next; });
      setAddCardStatus(null);
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [loadMeta]);

  /* ── Sidebar field helpers ───────────────────────────────────────────────── */
  const handleNotetypeChange = useCallback((name) => {
    setSelectedNotetype(name);
    const nt = notetypes.find(n => n.name === name);
    setFieldValues(nt ? nt.fields.map(() => '') : []);
    setCollapsedFields(new Set());
    setAddCardStatus(null);
  }, [notetypes]);

  const toggleCollapsed = useCallback((i) => {
    setCollapsedFields(prev => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });
  }, []);

  const togglePinned = useCallback((i) => {
    setPinnedFields(prev => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      pinnedFieldsRef.current = next;
      return next;
    });
  }, []);

  const handleAddCard = useCallback(() => {
    const nt = notetypes.find(n => n.name === selectedNotetype);
    if (!nt) return;
    const fields = {};
    nt.fields.forEach((fname, i) => { fields[fname] = fieldValues[i] || ''; });
    window.pycmd('incremento_add_card:' + JSON.stringify({ notetype: selectedNotetype, deck: selectedDeck, fields }));
    setAddCardStatus(null);
  }, [notetypes, selectedNotetype, selectedDeck, fieldValues]);

  const currentFields = notetypes.find(n => n.name === selectedNotetype)?.fields ?? [];

  /* ── Render ──────────────────────────────────────────────────────────────── */
  return (
    <div style={{ display: 'flex', width: '100%', alignItems: 'flex-start' }}>

      {/* ════════════════════════════════════════════════════════════════════
          LEFT: Add-card sidebar
      ════════════════════════════════════════════════════════════════════ */}
      {sidebarOpen && (
        <>
          <div
            id="pdf-sidebar"
            style={{
              width: sidebarWidth, flexShrink: 0,
              display: 'flex', flexDirection: 'column',
              background: '#2b2b2b', borderRight: '1px solid #3a3a3a',
              fontFamily: 'system-ui, sans-serif', fontSize: 13,
              minHeight: 0,
              /* max-height keeps it from pushing the PDF off screen */
              maxHeight: 'calc(100vh - 80px)', overflowY: 'auto',
            }}
          >
            {/* ── Type + Deck header bar ── */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 0,
              borderBottom: '1px solid #3a3a3a', flexShrink: 0,
            }}>
              <span style={{ padding: '8px 10px', color: '#888', fontSize: 12, borderRight: '1px solid #3a3a3a', whiteSpace: 'nowrap' }}>
                Type
              </span>
              <select
                value={selectedNotetype}
                onChange={e => handleNotetypeChange(e.target.value)}
                style={{
                  flex: 1, border: 'none', borderRight: '1px solid #3a3a3a',
                  background: 'transparent', color: '#d0d0d0',
                  padding: '7px 8px', fontSize: 12, outline: 'none',
                  cursor: 'pointer', minWidth: 0,
                }}
              >
                {notetypes.map(nt => <option key={nt.name} value={nt.name}>{nt.name}</option>)}
              </select>

              <span style={{ padding: '8px 10px', color: '#888', fontSize: 12, borderRight: '1px solid #3a3a3a', whiteSpace: 'nowrap' }}>
                Deck
              </span>
              <select
                value={selectedDeck}
                onChange={e => { setSelectedDeck(e.target.value); setAddCardStatus(null); }}
                style={{
                  flex: 1, border: 'none',
                  background: 'transparent', color: '#d0d0d0',
                  padding: '7px 8px', fontSize: 12, outline: 'none',
                  cursor: 'pointer', minWidth: 0,
                }}
              >
                {decks.map(d => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>

            {/* ── Fields ── */}
            <div style={{ flex: 1 }}>
              {notetypes.length === 0
                ? <div style={{ padding: 16, color: '#666', fontSize: 12 }}>Loading…</div>
                : currentFields.map((fname, i) => (
                    <FieldRow
                      key={fname}
                      fname={fname}
                      index={i}
                      value={fieldValues[i] || ''}
                      collapsed={collapsedFields.has(i)}
                      pinned={pinnedFields.has(i)}
                      onToggleCollapse={() => toggleCollapsed(i)}
                      onTogglePin={() => togglePinned(i)}
                      onChange={v => {
                        setFieldValues(prev => { const n = [...prev]; n[i] = v; return n; });
                        setAddCardStatus(null);
                      }}
                    />
                  ))
              }
            </div>

            {/* ── Add Card footer ── */}
            <div style={{ padding: '10px 12px', borderTop: '1px solid #3a3a3a', flexShrink: 0 }}>
              {addCardStatus && (
                <div style={{
                  marginBottom: 8, padding: '5px 8px', borderRadius: 3, fontSize: 12,
                  background: addCardStatus.ok ? '#1a3a1a' : '#3a1a1a',
                  color: addCardStatus.ok ? '#6dbf6d' : '#f07070',
                  border: `1px solid ${addCardStatus.ok ? '#2a5a2a' : '#5a2a2a'}`,
                }}>
                  {addCardStatus.msg}
                </div>
              )}
              <button
                onClick={handleAddCard}
                style={{
                  width: '100%', padding: '8px 0', cursor: 'pointer',
                  background: '#4a4a52', color: '#e0e0e0',
                  border: '1px solid #606068', borderRadius: 4, fontSize: 13,
                  fontFamily: 'inherit',
                }}
                onMouseEnter={e => { e.target.style.background = '#5a5a64'; }}
                onMouseLeave={e => { e.target.style.background = '#4a4a52'; }}
              >
                Add Card
              </button>
            </div>
          </div>

          {/* ── Drag handle ── */}
          <div
            onMouseDown={startResize}
            style={{
              width: 4, flexShrink: 0, cursor: 'col-resize',
              background: '#3a3a3a', transition: 'background 0.15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = '#5a8ae0'; }}
            onMouseLeave={e => { e.currentTarget.style.background = '#3a3a3a'; }}
          />
        </>
      )}

      {/* ════════════════════════════════════════════════════════════════════
          RIGHT: PDF viewer
      ════════════════════════════════════════════════════════════════════ */}
      <div style={{ flex: 1, minWidth: 0 }}>

        {/* Controls bar — rendered before canvas so it's visible immediately */}
        <div id="pdf-controls" style={{ textAlign: 'center', padding: '4px 0' }}>
          <button onClick={() => nav(-1)}>&#8592; Prev</button>
          <span id="pdf-page-label" style={{ margin: '0 12px' }}>
            {totalPages > 0 ? `Page ${page} / ${totalPages}` : 'Page \u2014 / \u2014'}
          </span>
          <button onClick={() => nav(1)}>Next &#8594;</button>
          <span style={{ marginLeft: 20 }}>
            <button onClick={() => adjustZoom(-1)}>&#8722;</button>
            <span id="pdf-zoom-label" style={{ margin: '0 8px' }}>{Math.round(zoom * 100)}%</span>
            <button onClick={() => adjustZoom(1)}>&#43;</button>
          </span>
          <button
            style={{ marginLeft: 20 }}
            onClick={() => { setSidebarOpen(o => !o); loadMeta(); }}
          >
            {sidebarOpen ? '\u2715 Cards' : '\u2630 Cards'}
          </button>
        </div>

        {error && (
          <div id="pdf-error" style={{ color: 'red', padding: '4px 8px', textAlign: 'center' }}>
            {error}
          </div>
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
    </div>
  );
}
