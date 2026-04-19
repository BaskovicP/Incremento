import { useCallback, useEffect, useRef, useState } from 'react';
import { usePdfRender } from './usePdfRender.js';
import HighlightLayer  from './HighlightLayer.jsx';
import PageCardPanel   from './PageCardPanel.jsx';

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
const CONTROLS_HEIGHT = 250;

const DEFAULT_LIMIT_STATUS = {
  enabled: false,
  daily_page_limit: 0,
  enforcement_mode: 'warning',
  enforcement_label: 'Warning',
  current_page: 1,
  baseline_page: 0,
  highest_page: 0,
  pages_used: 0,
  pages_remaining: 0,
  allowed_max_page: null,
  override_enabled: false,
  limit_reached: false,
  blocking_active: false,
  can_override: false,
};

function calculateTextWidth(text, font) {
  const canvas = calculateTextWidth._canvas || (calculateTextWidth._canvas = document.createElement('canvas'));
  const ctx = canvas.getContext('2d');
  if (!ctx) return text.length * 8;
  ctx.font = font;
  return ctx.measureText(text).width;
}

function nodesInSelection(range, textLayer) {
  if (!range || !textLayer) return null;
  const all = textLayer.children;
  const nodes = [];
  const start = range.startContainer?.nodeName === '#text'
    ? range.startContainer.parentNode
    : range.startContainer;
  const end = range.endContainer?.nodeName === '#text'
    ? range.endContainer.parentNode
    : range.endContainer;
  let inside = false;
  for (let i = 0; i < all.length; i += 1) {
    if (all[i] === start) inside = true;
    if (inside) nodes.push(all[i]);
    if (all[i] === end) break;
  }
  return nodes;
}

function isSelectionInside(sel, container) {
  if (!sel || !container || !sel.rangeCount) return false;
  for (let i = 0; i < sel.rangeCount; i += 1) {
    const node = sel.getRangeAt(i).commonAncestorContainer;
    if (!container.contains(node)) return false;
  }
  return true;
}

function selectionCleaned(sel, textLayer) {
  try {
    if (!sel || !sel.rangeCount) return '';
    const range = sel.getRangeAt(0);
    const nodes = nodesInSelection(range, textLayer);
    const original = (sel.toString() || '').trim();
    if (!nodes || nodes.length <= 1) return original;

    let text = '';
    let offsetLeftLast = 0;
    let offsetTopLast = 0;
    let textWidthLast = 0;
    let insertedCount = 0;
    let lastFontSize = null;
    const lastYDiffs = [];

    for (let i = 0; i < nodes.length; i += 1) {
      const node = nodes[i];
      const piece = (node.innerText || node.textContent || '');
      if (!piece) continue;

      if ((node.offsetLeft < offsetLeftLast || node.offsetTop > offsetTopLast + 5) && !piece.startsWith(' ')) {
        const fontSize = Number((node.style.fontSize || '').replace('px', '')) || null;
        if (lastFontSize && fontSize && Math.abs(fontSize - lastFontSize) > 4) {
          text += '\n\n' + piece;
          insertedCount += 2;
        } else if (lastYDiffs.length > 0 && (node.offsetTop - offsetTopLast) > lastYDiffs[lastYDiffs.length - 1] + 2) {
          text += '\n\n' + piece;
          insertedCount += 2;
        } else if (text.endsWith('-')) {
          text = text.slice(0, -1) + piece;
          insertedCount -= 1;
        } else {
          text += ' ' + piece;
          insertedCount += 1;
        }
        if (offsetTopLast !== 0) {
          lastYDiffs.push(node.offsetTop - offsetTopLast);
        }
        lastFontSize = fontSize;
      } else if (offsetLeftLast + textWidthLast < node.offsetLeft - 2 && !piece.startsWith(' ')) {
        text += ' ' + piece;
        insertedCount += 1;
      } else if (offsetLeftLast + textWidthLast > node.offsetLeft - 5) {
        text = text.trimEnd() + piece;
      } else {
        text += piece;
      }

      offsetLeftLast = node.offsetLeft;
      offsetTopLast = node.offsetTop;

      const fontDescriptor = `${node.style.fontWeight || 'normal'} ${node.style.fontSize || '12px'} ${node.style.fontFamily || 'sans-serif'}`;
      const scaleX = Number((node.style.transform || '').match(/[0-9]+(\.[0-9]+)?/)?.[0] || 1);
      textWidthLast = calculateTextWidth(piece.trim(), fontDescriptor) * scaleX;
    }

    if (!text.length) return original;

    text = text.replace(/( |\u00a0){2,}/g, ' ')
      .replace(/ ([,.;:]) /g, '$1 ')
      .replace(/ ([)\].!?:])/g, '$1')
      .replace(/([\[(]) /g, '$1')
      .trim();

    if (!original) return text;
    if (!original.startsWith(text.substring(0, Math.min(10, text.length)))) {
      for (let y = 10; y > 0; y -= 1) {
        const probe = original.substring(0, Math.min(y, original.length));
        const idx = text.indexOf(probe);
        if (idx > 0) {
          text = text.substring(idx);
          break;
        }
      }
    }
    if (text.length > original.length + insertedCount) {
      for (let y = 10; y > 0; y -= 1) {
        const probe = original.substring(Math.max(0, original.length - y));
        const idx = text.lastIndexOf(probe);
        if (idx >= 0) {
          text = text.substring(0, idx + probe.length);
          break;
        }
      }
    }
    return text.trim();
  } catch {
    return (sel?.toString() || '').trim();
  }
}

export default function PdfViewer() {
  // ── Rendering pipeline (text layer, canvases, zoom, navigation) ────────────
  const {
    page, totalPages, zoom, error, renderInfo, readPage,
    canvasARef, canvasBRef, containerRef, textLayerRef,
    pdfDocRef, activeCvsRef, cardIdRef, pageRef, lastScaleRef,
    startViewer, nav: rawNav, adjustZoom, markRead: rawMarkRead,
  } = usePdfRender();

  // ── Highlight state ────────────────────────────────────────────────────────
  const [highlights,    setHighlights]    = useState([]);
  const [hlColor,       setHlColor]       = useState('yellow');
  const [autoHighlight, setAutoHighlight] = useState(false);
  const hlColorRef       = useRef('yellow');
  const autoHighlightRef = useRef(false);

  // ── Snapshot state ─────────────────────────────────────────────────────────
  const [snapshotMode, setSnapshotMode] = useState(false);
  const [snapRect,     setSnapRect]     = useState(null);
  const snapStartRef = useRef(null);

  // ── Page card panel state ──────────────────────────────────────────────────
  const [pageCards,     setPageCards]     = useState([]);
  const [showCardPanel, setShowCardPanel] = useState(false);
  const [showHighlightsPanel, setShowHighlightsPanel] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [limitStatus, setLimitStatus] = useState(DEFAULT_LIMIT_STATUS);
  const [limitNotice, setLimitNotice] = useState(null);
  const [highlightsScope, setHighlightsScope] = useState('all');
  const [focusedHighlightId, setFocusedHighlightId] = useState(null);
  const [highlightJumpNonce, setHighlightJumpNonce] = useState(0);
  const pendingHighlightScrollRef = useRef(null);

  // ── Highlights for the current page ───────────────────────────────────────
  const pageHighlights = highlights.filter(h => h.page === page);
  const minViewerWidth = renderInfo?.pageWidth ? Math.ceil(renderInfo.pageWidth) : 0;
  const progressPct = (totalPages > 0 && readPage > 0)
    ? Math.max(0, Math.min(100, Math.round((readPage / totalPages) * 100)))
    : 0;
  const progressSegments = 10;
  const filledSegments = Math.round((progressPct / 100) * progressSegments);
  const sortedHighlights = [...highlights].sort((a, b) => {
    if ((a.page || 0) !== (b.page || 0)) return (a.page || 0) - (b.page || 0);
    return String(a.id || '').localeCompare(String(b.id || ''));
  });
  const highlightsForPanel = highlightsScope === 'page'
    ? sortedHighlights.filter((h) => h.page === page)
    : sortedHighlights;
  const limitEnabled = !!limitStatus?.enabled;
  const limitMode = String(limitStatus?.enforcement_mode || 'warning');
  const limitUsed = Number(limitStatus?.pages_used || 0);
  const limitTotal = Number(limitStatus?.daily_page_limit || 0);
  const limitRemaining = Number(limitStatus?.pages_remaining || 0);
  const allowedMaxPage = limitStatus?.allowed_max_page == null ? null : Number(limitStatus.allowed_max_page);
  const limitReached = !!limitStatus?.limit_reached;
  const overrideEnabled = !!limitStatus?.override_enabled;

  const clearLimitNotice = useCallback(() => setLimitNotice(null), []);

  const describeLimitReached = useCallback(() => {
    const prefix = limitTotal > 0
      ? `Daily limit reached: ${Math.max(limitUsed, limitTotal)}/${limitTotal} pages today.`
      : 'Daily limit reached for this PDF.';
    if (limitMode === 'hard_stop') {
      return `${prefix} Come back after your next Incremento day reset.`;
    }
    return `${prefix} Use override to keep reading today.`;
  }, [limitMode, limitTotal, limitUsed]);

  const canMoveToPage = useCallback((targetPage) => {
    if (!limitEnabled || targetPage <= pageRef.current) {
      return true;
    }
    if (overrideEnabled || allowedMaxPage == null) {
      return true;
    }
    if (targetPage <= allowedMaxPage) {
      return true;
    }
    if (limitMode === 'warning') {
      setLimitNotice({
        kind: 'warning',
        text: `You are moving past today's ${limitTotal}-page limit for this PDF.`,
      });
      return true;
    }
    setLimitNotice({
      kind: limitMode === 'soft_lock' ? 'soft_lock' : 'hard_stop',
      text: describeLimitReached(),
    });
    return false;
  }, [allowedMaxPage, describeLimitReached, limitEnabled, limitMode, limitTotal, overrideEnabled, pageRef]);

  const canMarkReadAtPage = useCallback((targetPage) => {
    if (!limitEnabled) {
      return true;
    }
    if (overrideEnabled || allowedMaxPage == null || targetPage <= allowedMaxPage) {
      return true;
    }
    if (limitMode === 'warning') {
      setLimitNotice({
        kind: 'warning',
        text: `Read-through can go past today's ${limitTotal}-page limit for this PDF.`,
      });
      return true;
    }
    setLimitNotice({
      kind: limitMode === 'soft_lock' ? 'soft_lock' : 'hard_stop',
      text: describeLimitReached(),
    });
    return false;
  }, [allowedMaxPage, describeLimitReached, limitEnabled, limitMode, limitTotal, overrideEnabled]);

  const requestLimitOverride = useCallback(() => {
    if (!cardIdRef.current) return;
    window.pycmd(`incremento_pdf_limit_override:${cardIdRef.current}`);
  }, [cardIdRef]);

  useEffect(() => {
    if (!limitEnabled) {
      setLimitNotice(null);
      return;
    }
    if (overrideEnabled && limitReached) {
      setLimitNotice({
        kind: 'info',
        text: 'Daily reading limit override is active for this PDF until the next day reset.',
      });
      return;
    }
    if (!limitReached && limitNotice?.kind !== 'warning') {
      setLimitNotice(null);
    }
  }, [limitEnabled, limitNotice?.kind, limitReached, overrideEnabled]);

  useEffect(() => {
    const pendingId = pendingHighlightScrollRef.current;
    if (!pendingId) return;
    const target = highlights.find((h) => h.id === pendingId);
    if (!target || target.page !== page || !target.rects?.length) return;

    const firstRect = target.rects[0];
    const wrapper = containerRef.current;
    if (!wrapper) return;

    const wrapperRect = wrapper.getBoundingClientRect();
    const scale = renderInfo?.scale || 1;
    const tlLeft = renderInfo?.tlLeft || 0;
    const targetTop = window.scrollY + wrapperRect.top + (firstRect.y * scale) - CONTROLS_HEIGHT - 24;
    const targetLeft = Math.max(
      0,
      window.scrollX + tlLeft + (firstRect.x * scale) - (window.innerWidth * 0.25),
    );

    window.scrollTo({
      top: Math.max(0, targetTop),
      left: targetLeft,
      behavior: 'smooth',
    });

    setFocusedHighlightId(pendingId);
    window.setTimeout(() => setFocusedHighlightId(null), 1400);
    pendingHighlightScrollRef.current = null;
  }, [page, renderInfo, highlights, containerRef, highlightJumpNonce]);

  useEffect(() => {
    const tl = textLayerRef.current;
    if (!tl) return;
    const spans = Array.from(tl.querySelectorAll('span'));
    spans.forEach((sp) => {
      if (sp.dataset.incSearchHit === '1') {
        sp.dataset.incSearchHit = '0';
        sp.style.background = '';
        sp.style.outline = '';
      }
    });

    const q = (searchQuery || '').trim().toLowerCase();
    if (!q) return;

    const toks = q.split(/\s+/).filter((t) => t.length >= 2);
    let firstHit = null;
    for (const sp of spans) {
      const txt = (sp.textContent || '').toLowerCase();
      if (!txt) continue;
      const hit = txt.includes(q) || (toks.length > 0 && toks.some((t) => txt.includes(t)));
      if (!hit) continue;
      sp.dataset.incSearchHit = '1';
      sp.style.background = 'rgba(255, 153, 0, 0.45)';
      sp.style.outline = '1px solid rgba(255, 153, 0, 0.95)';
      if (!firstHit) firstHit = sp;
    }

    if (firstHit) {
      try {
        firstHit.scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' });
      } catch (_) {}
    }
  }, [searchQuery, page, renderInfo, textLayerRef]);

  // ── Snapshot handlers ──────────────────────────────────────────────────────
  const handleSnapStart = useCallback((e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    snapStartRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    setSnapRect(null);
    e.preventDefault();
  }, []);

  const handleSnapMove = useCallback((e) => {
    if (!snapStartRef.current) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const cy = e.clientY - rect.top;
    const { x: sx, y: sy } = snapStartRef.current;
    setSnapRect({ x: Math.min(sx, cx), y: Math.min(sy, cy),
                  w: Math.abs(cx - sx), h: Math.abs(cy - sy) });
  }, []);

  const handleSnapEnd = useCallback((e) => {
    if (!snapStartRef.current) return;
    const overlayRect = e.currentTarget.getBoundingClientRect();
    const ex = e.clientX - overlayRect.left;
    const ey = e.clientY - overlayRect.top;
    const { x: sx, y: sy } = snapStartRef.current;
    snapStartRef.current = null;
    setSnapshotMode(false);
    setSnapRect(null);

    const rx = Math.min(sx, ex), ry = Math.min(sy, ey);
    const rw = Math.abs(ex - sx), rh = Math.abs(ey - sy);
    if (rw < 5 || rh < 5) return;

    const cvs = activeCvsRef.current === 'a' ? canvasARef.current : canvasBRef.current;
    if (!cvs) return;

    const cvsRect = cvs.getBoundingClientRect();
    const cvsLeft = cvsRect.left - overlayRect.left;
    const cvsTop  = cvsRect.top  - overlayRect.top;

    const cx  = Math.max(0, rx - cvsLeft);
    const cy  = Math.max(0, ry - cvsTop);
    const cx2 = Math.min(rx + rw - cvsLeft, cvsRect.width);
    const cy2 = Math.min(ry + rh - cvsTop,  cvsRect.height);
    const cw  = cx2 - cx;
    const ch  = cy2 - cy;
    if (cw < 5 || ch < 5) return;

    const dpr = window.devicePixelRatio || 1;
    const tmp = document.createElement('canvas');
    tmp.width  = Math.round(cw * dpr);
    tmp.height = Math.round(ch * dpr);
    tmp.getContext('2d').drawImage(
      cvs,
      Math.round(cx * dpr), Math.round(cy * dpr),
      Math.round(cw * dpr), Math.round(ch * dpr),
      0, 0,
      Math.round(cw * dpr), Math.round(ch * dpr)
    );
    window.pycmd('incremento_pdf_snapshot:' + JSON.stringify({
      cardId: cardIdRef.current,
      page:   pageRef.current,
      image:  tmp.toDataURL('image/png'),
    }));
  }, [activeCvsRef, canvasARef, canvasBRef, cardIdRef, pageRef]);

  // ── Highlight helpers ──────────────────────────────────────────────────────
  const deleteHighlight = useCallback((id) => {
    setHighlights(prev => prev.filter(h => h.id !== id));
    window.pycmd('incremento_pdf_hl_del:' + JSON.stringify({ cardId: cardIdRef.current, id }));
  }, [cardIdRef]);

  const makeHighlight = useCallback((sel, forcedColor = null) => {
    if (!sel || sel.isCollapsed || !sel.rangeCount) return false;
    const tl = textLayerRef.current;
    const range = sel.getRangeAt(0);
    if (!tl || !tl.contains(range.commonAncestorContainer)) return false;
    const tlRect = tl.getBoundingClientRect();
    const scale = lastScaleRef.current;
    const rects = Array.from(range.getClientRects())
      .map(r => ({
        x: (r.left - tlRect.left) / scale,
        y: (r.top  - tlRect.top)  / scale,
        w: r.width  / scale,
        h: r.height / scale,
      }))
      .filter(r => r.w > 2 && r.h > 2);
    if (!rects.length) return false;
    const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
    const hl = {
      id,
      page: pageRef.current,
      color: forcedColor || hlColorRef.current,
      text: sel.toString(),
      rects,
    };
    setHighlights(prev => [...prev, hl]);
    window.pycmd('incremento_pdf_hl_add:' + JSON.stringify({ cardId: cardIdRef.current, highlight: hl }));
    return true;
  }, [textLayerRef, lastScaleRef, pageRef, cardIdRef]);

  const pickHighlightColor = useCallback((color, applyNow = false) => {
    hlColorRef.current = color;
    setHlColor(color);
    if (!applyNow) return;
    const sel = window.getSelection();
    if (makeHighlight(sel, color) && sel?.removeAllRanges) {
      sel.removeAllRanges();
    }
  }, [makeHighlight]);

  const limitAwareNav = useCallback((delta) => {
    if (delta > 0) {
      const nextPage = pageRef.current + delta;
      if (!canMoveToPage(nextPage)) {
        return;
      }
    }
    rawNav(delta);
  }, [canMoveToPage, pageRef, rawNav]);

  const limitAwareMarkRead = useCallback(() => {
    if (!canMarkReadAtPage(pageRef.current)) {
      return;
    }
    rawMarkRead();
  }, [canMarkReadAtPage, pageRef, rawMarkRead]);

  // ── Register globals + consume pending ────────────────────────────────────
  useEffect(() => {
    // Wrap startViewer to also consume pending highlights.
    const startWithHighlights = (
      cardId,
      filename,
      startPage,
      startZoom,
      startReadPage = 0,
      startSearchQuery = '',
      startLimitStatus = null,
    ) => {
      setHighlights(window._incPdfHighlights || []);
      window._incPdfHighlights = null;
      setSearchQuery(startSearchQuery || '');
      setLimitStatus(startLimitStatus || DEFAULT_LIMIT_STATUS);
      setLimitNotice(null);
      startViewer(cardId, filename, startPage, startZoom, startReadPage);
    };

    window.incrementoPdfStart = startWithHighlights;
    window.incrementoPdfNav   = limitAwareNav;
    window.incrementoPdfZoom  = adjustZoom;
    window.incrementoPdfMarkRead = limitAwareMarkRead;

    window.incrementoReceivePageCards = (data) => {
      if (data.page === pageRef.current) {
        setPageCards(data.cards || []);
      }
    };
    window.incrementoReceivePdfLimitStatus = (status) => {
      setLimitStatus(status || DEFAULT_LIMIT_STATUS);
    };

    const pending = window._incPdfPending;
    if (pending) {
      window._incPdfPending = null;
      startWithHighlights(
        pending.cardId,
        pending.filename,
        pending.page,
        pending.zoom,
        pending.readPage || 0,
        pending.searchQuery || '',
        pending.limitStatus || DEFAULT_LIMIT_STATUS,
      );
    }
    return () => {
      delete window.incrementoPdfStart;
      delete window.incrementoPdfNav;
      delete window.incrementoPdfZoom;
      delete window.incrementoPdfMarkRead;
      delete window.incrementoReceivePageCards;
      delete window.incrementoReceivePdfLimitStatus;
    };
  }, [startViewer, limitAwareNav, adjustZoom, limitAwareMarkRead, pageRef]);

  // ── Request card sources for current page ─────────────────────────────────
  useEffect(() => {
    if (!pdfDocRef.current || !cardIdRef.current) return;
    setPageCards([]);
    setShowCardPanel(false);
    window.pycmd('incremento_get_page_cards:' + cardIdRef.current + ':' + page);
  }, [page, pdfDocRef, cardIdRef]);

  // ── Keyboard: Ctrl/Cmd+1–4 fill field / Option+H highlight ───────────────
  useEffect(() => {
    const idxFromShortcut = (e) => {
      const byCode = {
        Digit1: 0,
        Digit2: 1,
        Digit3: 2,
        Digit4: 3,
      };
      if (Object.prototype.hasOwnProperty.call(byCode, e.code)) {
        return byCode[e.code];
      }
      const n = parseInt(e.key, 10);
      if (Number.isNaN(n) || n < 1 || n > 4) return null;
      return n - 1;
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
      const idx = idxFromShortcut(e);
      if (idx === null) return;

      // Prevent browser/app tab-switch behavior (notably Cmd+1 on macOS).
      e.preventDefault();
      e.stopPropagation();

      performExtraction(idx);
    };

    const performExtraction = (idx) => {
      const selObj  = window.getSelection();
      const tl = textLayerRef.current;
      if (!tl || !selObj || !selObj.rangeCount || !isSelectionInside(selObj, tl)) return false;
      const selText = selectionCleaned(selObj, tl);
      if (!selText) return false;
      if (autoHighlightRef.current) makeHighlight(selObj);
      window.pycmd('incremento_fill_field:' + JSON.stringify({ idx, text: selText }));
      return true;
    };

    window.incrementoHandleExtractShortcut = (idx) => {
      const n = Number(idx);
      if (!Number.isInteger(n) || n < 0 || n > 3) return false;
      return performExtraction(n);
    };

    window.addEventListener('keydown', handler, true);
    return () => {
      window.removeEventListener('keydown', handler, true);
      delete window.incrementoHandleExtractShortcut;
    };
  }, [textLayerRef, makeHighlight]);

  // ── Copy cleaned selection from PDF text layer ─────────────────────────────
  useEffect(() => {
    const onCopy = (e) => {
      const tl = textLayerRef.current;
      const sel = window.getSelection();
      if (!tl || !sel || !sel.rangeCount || !isSelectionInside(sel, tl)) return;
      const cleaned = selectionCleaned(sel, tl);
      if (!cleaned) return;
      e.clipboardData?.setData('text/plain', cleaned);
      e.preventDefault();
    };
    document.addEventListener('copy', onCopy);
    return () => document.removeEventListener('copy', onCopy);
  }, [textLayerRef]);

  /* ── Render ────────────────────────────────────────────────────────────────── */
  return (
    <div
      style={{
        width: '100%',
        minWidth: minViewerWidth > 0 ? `${minViewerWidth}px` : undefined,
        paddingTop: `${CONTROLS_HEIGHT}px`,
      }}
    >

      {/* Controls */}
      <div
        id="pdf-controls"
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          zIndex: 50,
          width: '100vw',
          boxSizing: 'border-box',
          padding: '6px 8px 6px',
          userSelect: 'none',
          background: 'rgba(30, 30, 30, 0.96)',
          backdropFilter: 'blur(4px)',
          WebkitBackdropFilter: 'blur(4px)',
          borderBottom: '1px solid rgba(130,130,130,0.35)',
          boxShadow: '0 3px 10px rgba(0,0,0,0.28)',
        }}
      >

        {/* ── Row 1: Navigation + Zoom ── */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, marginBottom: 6 }}>
          <button onClick={() => limitAwareNav(-1)}>&#8592; Prev</button>
          <span style={{ margin: '0 4px' }}>
            {totalPages > 0 ? `Page ${page} / ${totalPages}` : 'Page \u2014 / \u2014'}
          </span>
          <button onClick={() => limitAwareNav(1)}>Next &#8594;</button>
          <span style={{ width: 1, height: 18, background: 'rgba(128,128,128,0.4)', margin: '0 4px', display: 'inline-block' }} />
          <button onClick={() => adjustZoom(-1)}>&#8722;</button>
          <span style={{ minWidth: 40, textAlign: 'center' }}>{Math.round(zoom * 100)}%</span>
          <button onClick={() => adjustZoom(1)}>&#43;</button>
        </div>

        {/* ── Row 2: Reading progress ── */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, marginBottom: 6 }}>
          <button
            title={readPage > 0 ? `Read up to page ${readPage} — click to toggle` : 'Mark pages as read up to here'}
            style={{
              background:  readPage > 0 && page <= readPage ? 'rgba(34,197,94,0.3)' : 'transparent',
              border:      '1px solid rgba(34,197,94,0.6)', borderRadius: 4,
              color:       readPage > 0 && page <= readPage ? 'rgb(22,163,74)' : 'inherit',
              cursor:      'pointer', padding: '2px 8px', fontSize: 12,
              fontWeight:  readPage > 0 && page <= readPage ? 'bold' : 'normal',
            }}
            onClick={limitAwareMarkRead}
          >
            ✓ Read to here
          </button>
          {readPage > 0 && (
            <span style={{ fontSize: 11, color: 'rgb(22,163,74)', fontWeight: 'bold' }}>
              p.1–{readPage}
            </span>
          )}
          <span
            title={totalPages > 0 ? `Read progress: ${readPage}/${totalPages} pages` : 'Read progress'}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '2px 6px',
              borderRadius: 6,
              background: 'rgba(20,20,20,0.45)',
              border: '1px solid rgba(120,120,120,0.35)',
            }}
          >
            <span style={{ minWidth: 36, textAlign: 'right', fontWeight: 'bold', fontSize: 12 }}>
              {progressPct}%
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}>
              {Array.from({ length: progressSegments }).map((_, idx) => (
                <span
                  key={idx}
                  style={{
                    width: 14,
                    height: 20,
                    borderRadius: 4,
                    background: idx < filledSegments ? 'rgba(14,165,233,0.85)' : 'rgba(80,80,80,0.28)',
                    border: idx < filledSegments ? '1px solid rgba(14,165,233,0.95)' : '1px solid rgba(130,130,130,0.55)',
                    boxSizing: 'border-box',
                  }}
                />
              ))}
            </span>
          </span>
        </div>

        {/* ── Row 3: Daily reading limit ── */}
        {limitEnabled && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, marginBottom: 6, flexWrap: 'wrap' }}>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                padding: '4px 10px',
                borderRadius: 999,
                background: limitReached ? 'rgba(245,158,11,0.18)' : 'rgba(34,197,94,0.12)',
                border: limitReached ? '1px solid rgba(245,158,11,0.45)' : '1px solid rgba(34,197,94,0.35)',
                fontSize: 12,
                fontWeight: 600,
              }}
              title="Daily PDF reading limit for this card"
            >
              <span>{`Today: ${limitUsed}/${limitTotal} pages`}</span>
              <span style={{ opacity: 0.72 }}>•</span>
              <span>{`${Math.max(0, limitRemaining)} remaining`}</span>
              <span style={{ opacity: 0.72 }}>•</span>
              <span>{limitStatus?.enforcement_label || 'Warning'}</span>
              {overrideEnabled && (
                <>
                  <span style={{ opacity: 0.72 }}>•</span>
                  <span style={{ color: 'rgb(96,165,250)' }}>Override active</span>
                </>
              )}
            </span>
            {allowedMaxPage != null && (
              <span style={{ fontSize: 11, color: '#c8c8c8' }}>
                Stop point today: page {allowedMaxPage}
              </span>
            )}
          </div>
        )}

        {limitNotice && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 8,
              marginBottom: 6,
              padding: '6px 10px',
              borderRadius: 8,
              background:
                limitNotice.kind === 'warning'
                  ? 'rgba(245,158,11,0.16)'
                  : limitNotice.kind === 'info'
                    ? 'rgba(59,130,246,0.15)'
                    : 'rgba(239,68,68,0.14)',
              border:
                limitNotice.kind === 'warning'
                  ? '1px solid rgba(245,158,11,0.40)'
                  : limitNotice.kind === 'info'
                    ? '1px solid rgba(59,130,246,0.40)'
                    : '1px solid rgba(239,68,68,0.40)',
              fontSize: 12,
            }}
          >
            <span>{limitNotice.text}</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              {limitNotice.kind === 'soft_lock' && !overrideEnabled && (
                <button onClick={requestLimitOverride}>
                  Override today
                </button>
              )}
              <button onClick={clearLimitNotice}>
                Dismiss
              </button>
            </span>
          </div>
        )}

        {/* ── Row 4: Tools + card management ── */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 14, flexWrap: 'wrap' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            {Object.keys(HL_COLORS).map(c => (
              <button
                key={c}
                title={`Highlight ${c}`}
                onMouseDown={(e) => {
                  e.preventDefault();
                  pickHighlightColor(c, true);
                }}
                onClick={() => pickHighlightColor(c, false)}
                style={{
                  background:  HL_SOLID[c],
                  border:      hlColor === c ? '2px solid white' : '2px solid transparent',
                  width: 18, height: 18,
                  borderRadius: 3, padding: 0, cursor: 'pointer',
                }}
              />
            ))}
            <span style={{ width: 1, height: 18, background: 'rgba(128,128,128,0.4)', display: 'inline-block' }} />
            <label style={{ fontSize: 12, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}>
              <input
                type="checkbox"
                checked={autoHighlight}
                onChange={e => { autoHighlightRef.current = e.target.checked; setAutoHighlight(e.target.checked); }}
              />
              Highlight when extracting
            </label>
            <button
              title={snapshotMode ? 'Cancel snapshot' : 'Draw a rectangle to capture a region'}
              style={{
                background:  snapshotMode ? 'rgba(37,99,235,0.2)' : 'transparent',
                border:      '1px solid rgba(37,99,235,0.5)',
                borderRadius: 4, color: snapshotMode ? 'rgb(37,99,235)' : 'inherit',
                cursor: 'pointer', padding: '2px 8px', fontSize: 12,
                fontWeight: snapshotMode ? 'bold' : 'normal',
              }}
              onClick={() => { setSnapshotMode(o => !o); setSnapRect(null); snapStartRef.current = null; }}
            >
              &#x1F4F7; Snapshot
            </button>
            <button
              title="Show highlights list"
              style={{
                background: showHighlightsPanel ? 'rgba(56,189,248,0.2)' : 'transparent',
                border: '1px solid rgba(56,189,248,0.55)',
                borderRadius: 4,
                color: showHighlightsPanel ? 'rgb(56,189,248)' : 'inherit',
                cursor: 'pointer',
                padding: '2px 8px',
                fontSize: 12,
                fontWeight: showHighlightsPanel ? 'bold' : 'normal',
              }}
              onClick={() => {
                setHighlightsScope('all');
                setShowHighlightsPanel(o => !o);
              }}
            >
              &#x1F4D1; Highlights ({highlights.length})
            </button>
          </span>
          <span style={{ width: 1, height: 20, background: 'rgba(128,128,128,0.4)', display: 'inline-block' }} />
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
          <button onClick={() => window.pycmd(`incremento_pdf_limit_settings:${cardIdRef.current}`)}>
            &#x1F4D6; Reading Limit
          </button>
          <button onClick={() => window.pycmd('incremento_open_add_card')}>
            &#43; Add Card
          </button>
          {pageCards.length > 0 && (
            <button
              title={`${pageCards.length} card${pageCards.length > 1 ? 's' : ''} created on this page — click to preview`}
              onClick={() => setShowCardPanel(o => !o)}
              style={{
                background:  showCardPanel ? 'rgba(74,144,217,0.25)' : 'rgba(74,144,217,0.12)',
                border:      '1px solid rgba(74,144,217,0.6)', borderRadius: 4,
                color:       'rgb(74,144,217)', cursor: 'pointer',
                padding:     '2px 8px', fontSize: 12, fontWeight: 'bold',
              }}
            >
              &#x1F4C4; {pageCards.length}
            </button>
          )}
          <button
            title="Mark this PDF as finished reading — suspends the card so it won't appear again"
            style={{
              background:  'transparent',
              border:      '1px solid rgba(220,50,50,0.45)', borderRadius: 4,
              color:       'rgba(220,70,70,0.9)', cursor: 'pointer',
              padding:     '2px 8px', fontSize: 12,
            }}
            onClick={() => {
              if (window.confirm('Mark this PDF as finished reading?\nThe card will be suspended and removed from future sessions.')) {
                window.pycmd('incremento_pdf_finished:' + cardIdRef.current);
              }
            }}
          >
            ✓ Finished Reading
          </button>
          </span>
        </div>

      </div>

      {/* Card preview panel */}
      {showCardPanel && pageCards.length > 0 && (
        <PageCardPanel page={page} pageCards={pageCards} />
      )}

      {/* Highlights panel */}
      {showHighlightsPanel && (
        <div
          style={{
            position: 'fixed',
            top: CONTROLS_HEIGHT + 8,
            right: 12,
            width: 'min(520px, calc(100vw - 24px))',
            maxHeight: 'calc(100vh - 220px)',
            overflowY: 'auto',
            background: 'rgba(25,25,25,0.97)',
            border: '1px solid rgba(120,120,120,0.45)',
            borderRadius: 8,
            boxShadow: '0 8px 20px rgba(0,0,0,0.35)',
            padding: 10,
            zIndex: 60,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <strong style={{ fontSize: 13 }}>PDF Highlights</strong>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <button
                onClick={() => setHighlightsScope('all')}
                style={{
                  border: '1px solid rgba(59,130,246,0.55)',
                  borderRadius: 4,
                  background: highlightsScope === 'all' ? 'rgba(59,130,246,0.2)' : 'transparent',
                  color: highlightsScope === 'all' ? 'rgb(96,165,250)' : 'inherit',
                  cursor: 'pointer',
                  fontSize: 12,
                  padding: '1px 8px',
                }}
              >
                Whole PDF
              </button>
              <button
                onClick={() => setHighlightsScope('page')}
                style={{
                  border: '1px solid rgba(59,130,246,0.55)',
                  borderRadius: 4,
                  background: highlightsScope === 'page' ? 'rgba(59,130,246,0.2)' : 'transparent',
                  color: highlightsScope === 'page' ? 'rgb(96,165,250)' : 'inherit',
                  cursor: 'pointer',
                  fontSize: 12,
                  padding: '1px 8px',
                }}
              >
                This page
              </button>
              <button
                onClick={() => setShowHighlightsPanel(false)}
                style={{
                  border: '1px solid rgba(140,140,140,0.5)',
                  borderRadius: 4,
                  background: 'transparent',
                  color: 'inherit',
                  cursor: 'pointer',
                  fontSize: 12,
                  padding: '1px 8px',
                }}
              >
                Close
              </button>
            </span>
          </div>

          {highlightsForPanel.length === 0 ? (
            <div style={{ fontSize: 12, opacity: 0.75 }}>No highlights yet.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {highlightsForPanel.map((hl) => (
                <button
                  key={hl.id}
                  onClick={() => {
                    const targetPage = Math.max(1, parseInt(hl.page || 1, 10));
                    pendingHighlightScrollRef.current = hl.id;
                    setHighlightJumpNonce((n) => n + 1);
                    nav(targetPage - pageRef.current);
                    setShowHighlightsPanel(false);
                  }}
                  style={{
                    textAlign: 'left',
                    border: '1px solid rgba(90,90,90,0.55)',
                    borderRadius: 6,
                    background: 'rgba(35,35,35,0.75)',
                    color: 'inherit',
                    cursor: 'pointer',
                    padding: '8px 10px',
                  }}
                  title={`Go to page ${hl.page || 1}`}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 3 }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, opacity: 0.9 }}>
                      <span
                        style={{
                          width: 10,
                          height: 10,
                          borderRadius: 999,
                          background: HL_SOLID[hl.color] || '#9CA3AF',
                          border: '1px solid rgba(255,255,255,0.35)',
                          display: 'inline-block',
                          flexShrink: 0,
                        }}
                      />
                      <span>Page {hl.page || 1}</span>
                    </span>
                    <button
                      title="Delete this highlight"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        deleteHighlight(hl.id);
                      }}
                      style={{
                        border: '1px solid rgba(220,70,70,0.55)',
                        borderRadius: 4,
                        background: 'rgba(220,70,70,0.12)',
                        color: 'rgba(248,113,113,0.95)',
                        cursor: 'pointer',
                        fontSize: 11,
                        padding: '1px 7px',
                        flexShrink: 0,
                      }}
                    >
                      Delete
                    </button>
                  </div>
                  <div style={{ fontSize: 12, lineHeight: 1.35 }}>
                    {(hl.text || '(no text)').trim()}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

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

        <HighlightLayer
          pageHighlights={pageHighlights}
          renderInfo={renderInfo}
          deleteHighlight={deleteHighlight}
          focusedHighlightId={focusedHighlightId}
          snapshotMode={snapshotMode}
          snapRect={snapRect}
          handleSnapStart={handleSnapStart}
          handleSnapMove={handleSnapMove}
          handleSnapEnd={handleSnapEnd}
        />

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
