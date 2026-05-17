import { useCallback, useEffect, useRef, useState } from 'react';
import { usePdfRender } from './usePdfRender.js';
import HighlightLayer  from './HighlightLayer.jsx';

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
  snapshot: '#2563EB',
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

const TOOLBAR_GROUP_STYLE = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 10,
  padding: '10px 12px',
  borderRadius: 14,
  background: 'linear-gradient(180deg, rgba(44,44,44,0.96), rgba(28,28,28,0.96))',
  border: '1px solid rgba(138,138,138,0.26)',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.05), 0 8px 18px rgba(0,0,0,0.16)',
};

const TOOLBAR_LABEL_STYLE = {
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  color: 'rgba(200,200,200,0.72)',
};

const TOOLBAR_STACK_STYLE = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'flex-start',
  gap: 5,
};

const TOOLBAR_SEPARATOR_STYLE = {
  width: 1,
  alignSelf: 'stretch',
  background: 'linear-gradient(180deg, rgba(255,255,255,0.02), rgba(140,140,140,0.35), rgba(255,255,255,0.02))',
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

function findTextSpan(node, container) {
  let current = node;
  while (current && current !== container) {
    if (current.nodeType === Node.ELEMENT_NODE && current.tagName === 'SPAN') {
      return current;
    }
    current = current.parentNode;
  }
  return null;
}

function rectToPdfCoords(rect, layerRect, scale) {
  if (!rect || !layerRect || !scale) return null;
  const width = rect.width / scale;
  const height = rect.height / scale;
  if (width <= 0 || height <= 0) return null;
  return {
    x: (rect.left - layerRect.left) / scale,
    y: (rect.top - layerRect.top) / scale,
    w: width,
    h: height,
  };
}

function makeClientHighlightId(prefix = 'hl') {
  return `${prefix}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
}

function findBestVisibleTextSpan(textLayer) {
  if (!textLayer) return null;
  const spans = Array.from(textLayer.querySelectorAll('span')).filter((span) => /\S/.test(span.textContent || ''));
  if (!spans.length) return null;

  const viewportMid = window.innerHeight / 2;
  let best = null;
  let bestDistance = Infinity;
  for (const span of spans) {
    const rect = span.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    if (rect.bottom < 0 || rect.top > window.innerHeight) continue;
    const spanMid = rect.top + (rect.height / 2);
    const distance = Math.abs(spanMid - viewportMid);
    if (distance < bestDistance) {
      best = span;
      bestDistance = distance;
    }
  }
  return best || spans[0];
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

function normalizeJumpText(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();
}

function clearJumpHitStyles(textLayer) {
  if (!textLayer) return;
  textLayer.querySelectorAll('span[data-inc-jump-hit="1"]').forEach((span) => {
    span.dataset.incJumpHit = '0';
    span.style.background = '';
    span.style.outline = '';
    span.style.borderRadius = '';
  });
}

function markJumpHit(spans) {
  spans.forEach((span) => {
    span.dataset.incJumpHit = '1';
    span.style.background = 'rgba(59, 130, 246, 0.24)';
    span.style.outline = '1px solid rgba(96, 165, 250, 0.95)';
    span.style.borderRadius = '3px';
  });
}

function findExcerptSpanMatch(textLayer, excerpt) {
  const target = normalizeJumpText(excerpt);
  if (!textLayer || !target) return null;

  const spans = Array.from(textLayer.querySelectorAll('span'))
    .map((span) => ({ span, text: normalizeJumpText(span.textContent) }))
    .filter(({ text }) => text.length > 0);
  if (!spans.length) return null;

  const maxWindow = 48;
  const maxCombinedLength = Math.max(target.length * 2, target.length + 120);
  for (let start = 0; start < spans.length; start += 1) {
    let combined = '';
    const matched = [];
    for (let end = start; end < spans.length && end < start + maxWindow; end += 1) {
      const piece = spans[end].text;
      combined = combined ? `${combined} ${piece}` : piece;
      matched.push(spans[end].span);
      if (combined.includes(target)) {
        return matched;
      }
      if (combined.length > maxCombinedLength) {
        break;
      }
    }
  }

  const tokens = target.split(/\s+/).filter((token) => token.length >= 4).slice(0, 6);
  if (!tokens.length) return null;
  return spans
    .filter(({ text }) => tokens.some((token) => text.includes(token)))
    .slice(0, Math.max(1, Math.min(tokens.length, 4)))
    .map(({ span }) => span);
}

export default function PdfViewer() {
  // ── Rendering pipeline (text layer, canvases, zoom, navigation) ────────────
  const {
    page, totalPages, zoom, error, renderInfo, readPage,
    canvasARef, canvasBRef, containerRef, textLayerRef,
    pdfDocRef, activeCvsRef, cardIdRef, pageRef, lastScaleRef,
    startViewer, nav: rawNav, adjustZoom, setReadProgress: rawSetReadProgress,
  } = usePdfRender();

  // ── Highlight state ────────────────────────────────────────────────────────
  const [highlights,    setHighlights]    = useState([]);
  const [hlColor,       setHlColor]       = useState('yellow');
  const [autoHighlight, setAutoHighlight] = useState(false);
  const hlColorRef       = useRef('yellow');
  const autoHighlightRef = useRef(false);
  const applyAutoHighlightSetting = useCallback((value) => {
    const enabled = !!value;
    autoHighlightRef.current = enabled;
    setAutoHighlight(enabled);
  }, []);

  // ── Snapshot state ─────────────────────────────────────────────────────────
  const [snapshotMode, setSnapshotMode] = useState(false);
  const [snapRect,     setSnapRect]     = useState(null);
  const snapStartRef = useRef(null);

  // ── Page card panel state ──────────────────────────────────────────────────
  const [pageCards,     setPageCards]     = useState([]);
  const [showHighlightsPanel, setShowHighlightsPanel] = useState(false);
  const [bookmarks, setBookmarks] = useState([]);
  const [showBookmarksPanel, setShowBookmarksPanel] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [readAnchor, setReadAnchor] = useState(null);
  const [limitStatus, setLimitStatus] = useState(DEFAULT_LIMIT_STATUS);
  const [limitNotice, setLimitNotice] = useState(null);
  const [hoveredHighlightNote, setHoveredHighlightNote] = useState(null);
  const [highlightsScope, setHighlightsScope] = useState('all');
  const [focusedHighlightId, setFocusedHighlightId] = useState(null);
  const [highlightJumpNonce, setHighlightJumpNonce] = useState(0);
  const [pageJumpEditing, setPageJumpEditing] = useState(false);
  const [pageJumpValue, setPageJumpValue] = useState('');
  const pendingHighlightScrollRef = useRef(null);
  const pendingExcerptJumpRef = useRef('');
  const pendingReadAnchorScrollRef = useRef(false);
  const lastReadAnchorSpanRef = useRef(null);
  const pageJumpInputRef = useRef(null);

  // ── Highlights for the current page ───────────────────────────────────────
  const pageHighlights = highlights.filter(h => h.page === page);
  const minViewerWidth = renderInfo?.pageWidth ? Math.ceil(renderInfo.pageWidth) : 0;
  const showReadMarker = (
    readAnchor
    && readPage > 0
    && page === readPage
    && Number(readAnchor.page || 0) === page
  );
  const readMarkerRect = (
    showReadMarker
    && Number.isFinite(Number(readAnchor.x))
    && Number.isFinite(Number(readAnchor.y))
    && Number.isFinite(Number(readAnchor.w))
    && Number.isFinite(Number(readAnchor.h))
  )
    ? {
        x: Number(readAnchor.x || 0),
        y: Number(readAnchor.y || 0),
        w: Number(readAnchor.w || 0),
        h: Number(readAnchor.h || 0),
      }
    : null;
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
  const hasPdfCard = Number(cardIdRef.current || 0) > 0;

  const clearLimitNotice = useCallback(() => setLimitNotice(null), []);

  const refreshBookmarks = useCallback(() => {
    if (!cardIdRef.current) return;
    window.pycmd(`incremento_pdf_bookmark_list:${cardIdRef.current}`);
  }, [cardIdRef]);

  const addBookmark = useCallback(() => {
    if (!cardIdRef.current) return;
    window.pycmd('incremento_pdf_bookmark_add:' + JSON.stringify({
      cardId: cardIdRef.current,
      page: pageRef.current,
    }));
    setShowBookmarksPanel(true);
  }, [cardIdRef, pageRef]);

  const deleteBookmark = useCallback((id) => {
    if (!cardIdRef.current || !id) return;
    window.pycmd('incremento_pdf_bookmark_delete:' + JSON.stringify({
      cardId: cardIdRef.current,
      id,
    }));
  }, [cardIdRef]);

  const showHighlightNote = useCallback((highlight, event) => {
    const note = String(highlight?.note || '').trim();
    if (!note) return;
    setHoveredHighlightNote({
      id: String(highlight.id || ''),
      note,
      x: Number(event?.clientX || 0),
      y: Number(event?.clientY || 0),
    });
  }, []);

  const moveHighlightNote = useCallback((event) => {
    setHoveredHighlightNote((prev) => (
      prev
        ? {
            ...prev,
            x: Number(event?.clientX || prev.x || 0),
            y: Number(event?.clientY || prev.y || 0),
          }
        : prev
    ));
  }, []);

  const hideHighlightNote = useCallback(() => {
    setHoveredHighlightNote(null);
  }, []);

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

  const buildReadAnchor = useCallback(() => {
    const tl = textLayerRef.current;
    const scale = Number(lastScaleRef.current || 0);
    if (!tl || !scale) return null;

    const tlRect = tl.getBoundingClientRect();
    const selection = window.getSelection();
    if (selection && !selection.isCollapsed && selection.rangeCount && isSelectionInside(selection, tl)) {
      const range = selection.getRangeAt(0);
      const rects = Array.from(range.getClientRects()).filter((rect) => rect.width > 0 && rect.height > 0);
      const targetRect = rects.length ? rects[rects.length - 1] : null;
      const coords = rectToPdfCoords(targetRect, tlRect, scale);
      if (coords) {
        return {
          page: pageRef.current,
          ...coords,
          text: selectionCleaned(selection, tl).slice(0, 240),
        };
      }
    }

    let span = lastReadAnchorSpanRef.current;
    if (!span || !tl.contains(span)) {
      span = findBestVisibleTextSpan(tl);
    }
    if (!span) return null;

    const coords = rectToPdfCoords(span.getBoundingClientRect(), tlRect, scale);
    if (!coords) return null;
    return {
      page: pageRef.current,
      ...coords,
      text: String(span.textContent || '').trim().slice(0, 240),
    };
  }, [lastScaleRef, pageRef, textLayerRef]);

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
    const wrapper = containerRef.current;
    if (!wrapper) return;

    const scrollToPdfRect = (rect, leftBias = 0.25, topPad = 24) => {
      if (!rect) return false;
      const wrapperRect = wrapper.getBoundingClientRect();
      const scale = renderInfo?.scale || 1;
      const tlLeft = renderInfo?.tlLeft || 0;
      const targetTop = window.scrollY + wrapperRect.top + (rect.y * scale) - topPad;
      const targetLeft = Math.max(
        0,
        window.scrollX + tlLeft + (rect.x * scale) - (window.innerWidth * leftBias),
      );
      window.scrollTo({
        top: Math.max(0, targetTop),
        left: targetLeft,
        behavior: 'smooth',
      });
      return true;
    };

    if (pendingId) {
      const target = highlights.find((h) => h.id === pendingId);
      if (!target || target.page !== page || !target.rects?.length) return;
      if (!scrollToPdfRect(target.rects[0])) return;
      setFocusedHighlightId(pendingId);
      window.setTimeout(() => setFocusedHighlightId(null), 1400);
      pendingHighlightScrollRef.current = null;
      return;
    }

    const jumpExcerpt = pendingExcerptJumpRef.current;
    if (jumpExcerpt) {
      const normalizedExcerpt = normalizeJumpText(jumpExcerpt);
      if (!normalizedExcerpt) {
        pendingExcerptJumpRef.current = '';
      } else {
        const highlightTarget = highlights.find((highlight) => {
          if (highlight.page !== page || !highlight.rects?.length) return false;
          const highlightText = normalizeJumpText(highlight.text);
          return (
            highlightText.includes(normalizedExcerpt)
            || normalizedExcerpt.includes(highlightText)
          );
        });
        if (highlightTarget?.rects?.length && scrollToPdfRect(highlightTarget.rects[0])) {
          setFocusedHighlightId(String(highlightTarget.id || ''));
          window.setTimeout(() => setFocusedHighlightId(null), 1600);
          pendingExcerptJumpRef.current = '';
          pendingReadAnchorScrollRef.current = false;
          return;
        }

        const tl = textLayerRef.current;
        const spanCount = tl ? tl.querySelectorAll('span').length : 0;
        if (tl && spanCount > 0) {
          clearJumpHitStyles(tl);
          const matchedSpans = findExcerptSpanMatch(tl, normalizedExcerpt);
          if (matchedSpans?.length) {
            markJumpHit(matchedSpans);
            try {
              matchedSpans[0].scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' });
            } catch (_) {}
            pendingExcerptJumpRef.current = '';
            pendingReadAnchorScrollRef.current = false;
            window.setTimeout(() => clearJumpHitStyles(tl), 2200);
            return;
          }
          pendingExcerptJumpRef.current = '';
        } else {
          return;
        }
      }
    }

    if (pendingReadAnchorScrollRef.current && showReadMarker) {
      if (readMarkerRect) {
        scrollToPdfRect(readMarkerRect, 0.15, 80);
      }
      pendingReadAnchorScrollRef.current = false;
    }
  }, [page, renderInfo, highlights, containerRef, highlightJumpNonce, showReadMarker, readMarkerRect, textLayerRef]);

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

  useEffect(() => {
    const tl = textLayerRef.current;
    if (!tl) return;
    const rememberSpan = (event) => {
      const span = findTextSpan(event.target, tl);
      if (span) {
        lastReadAnchorSpanRef.current = span;
      }
    };
    tl.addEventListener('mousedown', rememberSpan, true);
    tl.addEventListener('click', rememberSpan, true);
    return () => {
      tl.removeEventListener('mousedown', rememberSpan, true);
      tl.removeEventListener('click', rememberSpan, true);
    };
  }, [page, textLayerRef]);

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

  const makeSnapshotHighlight = useCallback((canvasRect) => {
    const cardId = Number(cardIdRef.current || 0);
    const scale = Number(lastScaleRef.current || 0);
    if (!cardId || !scale || !canvasRect) return false;

    const rect = {
      x: canvasRect.x / scale,
      y: canvasRect.y / scale,
      w: canvasRect.w / scale,
      h: canvasRect.h / scale,
    };
    if (rect.w <= 0 || rect.h <= 0) return false;

    const hl = {
      id: makeClientHighlightId('snapshot'),
      page: pageRef.current,
      color: 'snapshot',
      text: 'Snapshot region',
      note: '',
      rects: [rect],
    };
    setHighlights(prev => [...prev, hl]);
    window.pycmd('incremento_pdf_hl_add:' + JSON.stringify({ cardId, highlight: hl }));
    return true;
  }, [cardIdRef, lastScaleRef, pageRef]);

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

    makeSnapshotHighlight({ x: cx, y: cy, w: cw, h: ch });

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
  }, [activeCvsRef, canvasARef, canvasBRef, cardIdRef, makeSnapshotHighlight, pageRef]);

  // ── Highlight helpers ──────────────────────────────────────────────────────
  const deleteHighlight = useCallback((id) => {
    setHighlights(prev => prev.filter(h => h.id !== id));
    window.pycmd('incremento_pdf_hl_del:' + JSON.stringify({ cardId: cardIdRef.current, id }));
  }, [cardIdRef]);

  const updateHighlightNote = useCallback((id, note) => {
    setHighlights(prev => prev.map((h) => (
      h.id === id ? { ...h, note: String(note || '') } : h
    )));
  }, []);

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

  const openPageJump = useCallback(() => {
    if (totalPages <= 0) return;
    setPageJumpValue(String(pageRef.current || page || 1));
    setPageJumpEditing(true);
  }, [page, pageRef, totalPages]);

  const commitPageJump = useCallback(() => {
    const target = parseInt(pageJumpValue, 10);
    setPageJumpEditing(false);
    if (!Number.isFinite(target)) return;
    const clamped = Math.max(1, Math.min(target, totalPages || target));
    const delta = clamped - pageRef.current;
    if (delta !== 0) {
      limitAwareNav(delta);
    }
  }, [limitAwareNav, pageJumpValue, pageRef, totalPages]);

  const cancelPageJump = useCallback(() => {
    setPageJumpEditing(false);
    setPageJumpValue('');
  }, []);

  useEffect(() => {
    if (!pageJumpEditing) return;
    const input = pageJumpInputRef.current;
    if (!input) return;
    input.focus();
    input.select();
  }, [pageJumpEditing]);

  const jumpToBookmark = useCallback((bookmark) => {
    const targetPage = Number(bookmark?.location?.page || 0);
    if (!Number.isFinite(targetPage) || targetPage < 1) return;
    limitAwareNav(targetPage - pageRef.current);
  }, [limitAwareNav, pageRef]);

  const limitAwareMarkRead = useCallback(() => {
    if (!canMarkReadAtPage(pageRef.current)) {
      return;
    }
    const nextReadPage = pageRef.current <= readPage ? 0 : pageRef.current;
    setReadAnchor(null);
    rawSetReadProgress(nextReadPage, null);
  }, [canMarkReadAtPage, pageRef, rawSetReadProgress, readPage]);

  const limitAwareMarkReadAnchor = useCallback(() => {
    const currentPage = pageRef.current;
    if (!canMarkReadAtPage(currentPage)) {
      return;
    }
    if (showReadMarker) {
      setReadAnchor(null);
      rawSetReadProgress(currentPage, null);
      return;
    }
    const anchor = buildReadAnchor();
    setReadAnchor(anchor);
    rawSetReadProgress(currentPage, anchor);
  }, [buildReadAnchor, canMarkReadAtPage, pageRef, rawSetReadProgress, showReadMarker]);

  // ── Register globals + consume pending ────────────────────────────────────
  useEffect(() => {
    // Wrap startViewer to also consume pending highlights.
    const startWithHighlights = (
      cardId,
      filename,
      startPage,
      startZoom,
      startReadPage = 0,
      startReadAnchor = null,
      startSearchQuery = '',
      startJumpExcerpt = '',
      startScrollToReadAnchor = false,
      startLimitStatus = null,
      startAutoHighlightOnExtract = undefined,
      startBookmarks = null,
    ) => {
      setHighlights(window._incPdfHighlights || []);
      window._incPdfHighlights = null;
      setBookmarks(Array.isArray(startBookmarks) ? startBookmarks : (window._incPdfBookmarks || []));
      window._incPdfBookmarks = null;
      setSearchQuery(startSearchQuery || '');
      setReadAnchor(startReadAnchor && typeof startReadAnchor === 'object' ? startReadAnchor : null);
      pendingExcerptJumpRef.current = String(startJumpExcerpt || '').trim();
      pendingReadAnchorScrollRef.current = !!startScrollToReadAnchor;
      setLimitStatus(startLimitStatus || DEFAULT_LIMIT_STATUS);
      setLimitNotice(null);
      if (typeof startAutoHighlightOnExtract === 'boolean') {
        applyAutoHighlightSetting(startAutoHighlightOnExtract);
      }
      startViewer(cardId, filename, startPage, startZoom, startReadPage);
    };

    window.incrementoPdfStart = startWithHighlights;
    window.incrementoPdfNav   = limitAwareNav;
    window.incrementoPdfZoom  = adjustZoom;
    window.incrementoPdfMarkRead = limitAwareMarkRead;
    window.incrementoSetAutoHighlightOnExtract = (value) => {
      applyAutoHighlightSetting(value);
    };

    window.incrementoReceivePageCards = (data) => {
      if (data.page === pageRef.current) {
        setPageCards(data.cards || []);
      }
    };
    window.incrementoReceivePdfLimitStatus = (status) => {
      setLimitStatus(status || DEFAULT_LIMIT_STATUS);
    };
    window.incrementoReceivePdfBookmarks = (items) => {
      setBookmarks(Array.isArray(items) ? items : []);
    };
    window.incrementoUpdatePdfHighlightNote = (id, note) => {
      updateHighlightNote(String(id || ''), String(note || ''));
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
        pending.readAnchor || null,
        pending.searchQuery || '',
        pending.jumpExcerpt || '',
        pending.scrollToReadAnchor || false,
        pending.limitStatus || DEFAULT_LIMIT_STATUS,
        pending.autoHighlightOnExtract,
        pending.bookmarks || [],
      );
    }
    return () => {
      delete window.incrementoPdfStart;
      delete window.incrementoPdfNav;
      delete window.incrementoPdfZoom;
      delete window.incrementoPdfMarkRead;
      delete window.incrementoSetAutoHighlightOnExtract;
      delete window.incrementoReceivePageCards;
      delete window.incrementoReceivePdfLimitStatus;
      delete window.incrementoReceivePdfBookmarks;
      delete window.incrementoUpdatePdfHighlightNote;
    };
  }, [startViewer, limitAwareNav, adjustZoom, limitAwareMarkRead, pageRef, updateHighlightNote, applyAutoHighlightSetting]);

  // ── Request card sources for current page ─────────────────────────────────
  useEffect(() => {
    if (!pdfDocRef.current || !cardIdRef.current) return;
    setPageCards([]);
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
        paddingBottom: `${CONTROLS_HEIGHT}px`,
      }}
    >

      {/* Controls */}
      <div
        id="pdf-controls"
        style={{
          position: 'fixed',
          bottom: 0,
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
          borderTop: '1px solid rgba(130,130,130,0.35)',
          boxShadow: '0 -3px 10px rgba(0,0,0,0.28)',
        }}
      >

        {/* ── Row 1: Reader status and navigation ── */}
        <div style={{ display: 'flex', alignItems: 'stretch', justifyContent: 'center', gap: 12, marginBottom: 8, flexWrap: 'wrap' }}>
          <div style={TOOLBAR_GROUP_STYLE}>
            <div style={TOOLBAR_STACK_STYLE}>
              <span style={TOOLBAR_LABEL_STYLE}>Navigate</span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                <button onClick={() => limitAwareNav(-1)}>&#8592; Prev</button>
                {pageJumpEditing ? (
                  <span style={{ minWidth: 170, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6, fontSize: 15, fontWeight: 700 }}>
                    <span>Page</span>
                    <input
                      ref={pageJumpInputRef}
                      type="number"
                      min="1"
                      max={totalPages || undefined}
                      value={pageJumpValue}
                      onChange={(event) => setPageJumpValue(event.target.value)}
                      onBlur={commitPageJump}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') {
                          event.preventDefault();
                          commitPageJump();
                        } else if (event.key === 'Escape') {
                          event.preventDefault();
                          cancelPageJump();
                        }
                      }}
                      style={{
                        width: 64,
                        height: 30,
                        boxSizing: 'border-box',
                        textAlign: 'center',
                        fontSize: 15,
                        fontWeight: 700,
                        color: '#f4f4f5',
                        background: 'rgba(255,255,255,0.08)',
                        border: '1px solid rgba(180,180,180,0.46)',
                        borderRadius: 8,
                        outline: 'none',
                      }}
                    />
                    <span>/ {totalPages}</span>
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={openPageJump}
                    title={totalPages > 0 ? 'Go to page' : undefined}
                    style={{
                      minWidth: 170,
                      height: 32,
                      padding: '0 8px',
                      textAlign: 'center',
                      fontSize: 15,
                      fontWeight: 700,
                      color: 'inherit',
                      background: 'transparent',
                      border: '1px solid transparent',
                      borderRadius: 8,
                      cursor: totalPages > 0 ? 'pointer' : 'default',
                    }}
                  >
                    {totalPages > 0 ? `Page ${page} / ${totalPages}` : 'Page \u2014 / \u2014'}
                  </button>
                )}
                <button onClick={() => limitAwareNav(1)}>Next &#8594;</button>
              </span>
            </div>
            <span style={TOOLBAR_SEPARATOR_STYLE} />
            <div style={TOOLBAR_STACK_STYLE}>
              <span style={TOOLBAR_LABEL_STYLE}>Zoom</span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                <button onClick={() => adjustZoom(-1)}>&#8722;</button>
                <span style={{ minWidth: 54, textAlign: 'center', fontSize: 15, fontWeight: 700 }}>
                  {Math.round(zoom * 100)}%
                </span>
                <button onClick={() => adjustZoom(1)}>&#43;</button>
              </span>
            </div>
          </div>

          <div style={{ ...TOOLBAR_GROUP_STYLE, padding: '10px 14px', gap: 12 }}>
            <div style={TOOLBAR_STACK_STYLE}>
              <span style={TOOLBAR_LABEL_STYLE}>Reading</span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <button
                  title={readPage > 0 ? `Read up to page ${readPage} — click to toggle progress only` : 'Mark pages as read up to here without placing an exact marker'}
                  style={{
                    background:  readPage > 0 && page <= readPage ? 'rgba(34,197,94,0.3)' : 'transparent',
                    border:      '1px solid rgba(34,197,94,0.6)', borderRadius: 8,
                    color:       readPage > 0 && page <= readPage ? 'rgb(22,163,74)' : 'inherit',
                    cursor:      'pointer', padding: '4px 10px', fontSize: 12,
                    fontWeight:  readPage > 0 && page <= readPage ? 'bold' : 'normal',
                  }}
                  onClick={limitAwareMarkRead}
                >
                  ✓ Read to here
                </button>
                <button
                  title={showReadMarker ? 'Remove the exact READ UP UNTIL HERE marker from this page' : 'Place the exact READ UP UNTIL HERE marker at the current text row'}
                  aria-label="Toggle exact read marker"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 34,
                    height: 30,
                    padding: 0,
                    fontSize: 16,
                    fontWeight: 800,
                    borderRadius: 8,
                    cursor: 'pointer',
                    background: showReadMarker ? 'rgba(14,165,233,0.22)' : 'rgba(255,255,255,0.03)',
                    color: showReadMarker ? 'rgb(125,211,252)' : 'inherit',
                    border: showReadMarker ? '1px solid rgba(14,165,233,0.75)' : '1px solid rgba(180,180,180,0.32)',
                    boxShadow: showReadMarker ? '0 0 0 1px rgba(14,165,233,0.12) inset' : 'none',
                  }}
                  onClick={limitAwareMarkReadAnchor}
                >
                  ↦
                </button>
                {readPage > 0 && (
                  <span style={{
                    fontSize: 11,
                    color: 'rgb(22,163,74)',
                    fontWeight: 'bold',
                    padding: '4px 8px',
                    borderRadius: 999,
                    background: 'rgba(22,163,74,0.12)',
                    border: '1px solid rgba(22,163,74,0.24)',
                  }}>
                    p.1–{readPage}
                  </span>
                )}
              </span>
            </div>
            <span style={TOOLBAR_SEPARATOR_STYLE} />
            <span
              title={totalPages > 0 ? `Read progress: ${readPage}/${totalPages} pages` : 'Read progress'}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                padding: '6px 8px',
                borderRadius: 10,
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
        <div style={{ display: 'flex', alignItems: 'stretch', justifyContent: 'center', gap: 12, flexWrap: 'wrap' }}>
          {hasPdfCard && (
            <div style={{ ...TOOLBAR_GROUP_STYLE, padding: '10px 14px', gap: 12, flexWrap: 'wrap' }}>
              <div style={TOOLBAR_STACK_STYLE}>
                <span style={TOOLBAR_LABEL_STYLE}>Annotate</span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '2px 4px' }}>
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
                          width: 22, height: 22,
                          borderRadius: 6, padding: 0, cursor: 'pointer',
                          boxShadow: hlColor === c ? '0 0 0 2px rgba(255,255,255,0.12)' : 'none',
                        }}
                      />
                    ))}
                  </span>
                  <label style={{
                    fontSize: 12,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '6px 10px',
                    borderRadius: 999,
                    background: 'rgba(255,255,255,0.04)',
                    border: '1px solid rgba(255,255,255,0.08)',
                  }}>
                    <input
                      type="checkbox"
                      checked={autoHighlight}
                      onChange={e => applyAutoHighlightSetting(e.target.checked)}
                    />
                    Highlight when extracting
                  </label>
                </span>
              </div>
              <span style={TOOLBAR_SEPARATOR_STYLE} />
              <div style={TOOLBAR_STACK_STYLE}>
                <span style={TOOLBAR_LABEL_STYLE}>Capture</span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <button
                    title={snapshotMode ? 'Cancel snapshot' : 'Draw a rectangle to capture a region'}
                    style={{
                      background:  snapshotMode ? 'rgba(37,99,235,0.2)' : 'transparent',
                      border:      '1px solid rgba(37,99,235,0.5)',
                      borderRadius: 8, color: snapshotMode ? 'rgb(37,99,235)' : 'inherit',
                      cursor: 'pointer', padding: '4px 10px', fontSize: 12,
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
                      borderRadius: 8,
                      color: showHighlightsPanel ? 'rgb(56,189,248)' : 'inherit',
                      cursor: 'pointer',
                      padding: '4px 10px',
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
                  <button
                    title="Bookmark the current page as an interesting place"
                    onClick={addBookmark}
                  >
                    &#9733; Bookmark
                  </button>
                  <button
                    title="Show saved interesting-place bookmarks"
                    style={{
                      background: showBookmarksPanel ? 'rgba(250,204,21,0.18)' : 'transparent',
                      border: '1px solid rgba(250,204,21,0.55)',
                      borderRadius: 8,
                      color: showBookmarksPanel ? 'rgb(234,179,8)' : 'inherit',
                      cursor: 'pointer',
                      padding: '4px 10px',
                      fontSize: 12,
                      fontWeight: showBookmarksPanel ? 'bold' : 'normal',
                    }}
                    onClick={() => {
                      refreshBookmarks();
                      setShowBookmarksPanel(o => !o);
                    }}
                  >
                    Bookmarks ({bookmarks.length})
                  </button>
                </span>
              </div>
            </div>
          )}

          <div style={{ ...TOOLBAR_GROUP_STYLE, padding: '10px 14px', gap: 12, flexWrap: 'wrap' }}>
            {hasPdfCard && (
              <>
                <div style={TOOLBAR_STACK_STYLE}>
                  <span style={TOOLBAR_LABEL_STYLE}>Review</span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <button onClick={() => window.pycmd(`incremento_pdf_due_review:${cardIdRef.current}:${pageRef.current}`)}>
                      &#x1F9E0; Review Due
                    </button>
                    <button onClick={() => window.pycmd(`incremento_pdf_limit_settings:${cardIdRef.current}`)}>
                      &#x1F4D6; Reading Limit
                    </button>
                    <button onClick={() => window.pycmd(`incremento_pdf_regenerate_cover:${cardIdRef.current}`)}>
                      Regenerate Cover
                    </button>
                  </span>
                </div>
                <span style={TOOLBAR_SEPARATOR_STYLE} />
                <div style={TOOLBAR_STACK_STYLE}>
                  <span style={TOOLBAR_LABEL_STYLE}>Cards</span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <button
                      title="Open all cards created from this PDF in the Anki Browser"
                      onClick={() => window.pycmd('incremento_open_all_pdf_cards:' + cardIdRef.current)}
                    >
                      Open All in Browser
                    </button>
                    {pageCards.length > 0 && (
                      <button
                        title={`Open the ${pageCards.length} card${pageCards.length > 1 ? 's' : ''} created on this page in the Anki Browser`}
                        onClick={() => window.pycmd('incremento_open_page_cards:' + JSON.stringify(
                          pageCards
                            .map((card) => Number(card.note_id || 0))
                            .filter((noteId) => Number.isInteger(noteId) && noteId > 0),
                        ))}
                        style={{
                          background:  'rgba(74,144,217,0.12)',
                          border:      '1px solid rgba(74,144,217,0.6)', borderRadius: 8,
                          color:       'rgb(74,144,217)', cursor: 'pointer',
                          padding:     '4px 10px', fontSize: 12, fontWeight: 'bold',
                        }}
                      >
                        &#x1F4C4; Page cards ({pageCards.length})
                      </button>
                    )}
                    <button onClick={() => window.pycmd('incremento_open_add_card')}>
                      &#43; Add Card
                    </button>
                  </span>
                </div>
                <span style={TOOLBAR_SEPARATOR_STYLE} />
                <div style={TOOLBAR_STACK_STYLE}>
                  <span style={TOOLBAR_LABEL_STYLE}>Status</span>
                  <button
                    title="Mark this PDF as finished reading — suspends the card so it won't appear again"
                    style={{
                      background:  'transparent',
                      border:      '1px solid rgba(220,50,50,0.45)', borderRadius: 8,
                      color:       'rgba(220,70,70,0.9)', cursor: 'pointer',
                      padding:     '4px 10px', fontSize: 12,
                    }}
                    onClick={() => {
                      if (window.confirm('Mark this PDF as finished reading?\nThe card will be suspended and removed from future sessions.')) {
                        window.pycmd('incremento_pdf_finished:' + cardIdRef.current);
                      }
                    }}
                  >
                    ✓ Finished Reading
                  </button>
                </div>
              </>
            )}
            {!hasPdfCard && (
              <div style={TOOLBAR_STACK_STYLE}>
                <span style={TOOLBAR_LABEL_STYLE}>Cards</span>
                <button onClick={() => window.pycmd('incremento_open_add_card')}>
                  &#43; Add Card
                </button>
              </div>
            )}
          </div>
        </div>

      </div>

      {/* Bookmarks panel */}
      {hasPdfCard && showBookmarksPanel && (
        <div
          style={{
            position: 'fixed',
            top: CONTROLS_HEIGHT + 8,
            right: 12,
            width: 'min(420px, calc(100vw - 24px))',
            maxHeight: 'calc(100vh - 220px)',
            overflowY: 'auto',
            background: 'rgba(25,25,25,0.97)',
            border: '1px solid rgba(250,204,21,0.40)',
            borderRadius: 8,
            boxShadow: '0 8px 20px rgba(0,0,0,0.35)',
            padding: 10,
            zIndex: 65,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <strong style={{ fontSize: 13 }}>PDF Bookmarks</strong>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <button onClick={addBookmark} style={{ fontSize: 12, padding: '1px 8px' }}>
                Add current page
              </button>
              <button onClick={() => setShowBookmarksPanel(false)} style={{ fontSize: 12, padding: '1px 8px' }}>
                Close
              </button>
            </span>
          </div>
          {bookmarks.length === 0 ? (
            <div style={{ fontSize: 12, opacity: 0.75 }}>No bookmarks yet.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {bookmarks.map((bookmark) => (
                <div
                  key={bookmark.id}
                  style={{
                    border: '1px solid rgba(90,90,90,0.55)',
                    borderRadius: 6,
                    background: 'rgba(35,35,35,0.75)',
                    color: 'inherit',
                    padding: '8px 10px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                    <span style={{ fontSize: 12, fontWeight: 700 }}>
                      {bookmark.label || `Page ${bookmark?.location?.page || 1}`}
                    </span>
                    <span style={{ display: 'inline-flex', gap: 6, flexShrink: 0 }}>
                      <button
                        onClick={() => {
                          jumpToBookmark(bookmark);
                          setShowBookmarksPanel(false);
                        }}
                        style={{ fontSize: 11, padding: '1px 7px' }}
                      >
                        Jump
                      </button>
                      <button
                        onClick={() => deleteBookmark(bookmark.id)}
                        style={{
                          border: '1px solid rgba(220,70,70,0.55)',
                          borderRadius: 4,
                          background: 'rgba(220,70,70,0.12)',
                          color: 'rgba(248,113,113,0.95)',
                          cursor: 'pointer',
                          fontSize: 11,
                          padding: '1px 7px',
                        }}
                      >
                        Delete
                      </button>
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Highlights panel */}
      {hasPdfCard && showHighlightsPanel && (
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
                      title={(hl.note || '').trim() ? 'Edit note for this highlight' : 'Add note to this highlight'}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        window.pycmd('incremento_pdf_hl_note:' + JSON.stringify({ id: hl.id }));
                      }}
                      style={{
                        border: '1px solid rgba(74,144,217,0.55)',
                        borderRadius: 4,
                        background: 'rgba(74,144,217,0.12)',
                        color: 'rgba(147,197,253,0.95)',
                        cursor: 'pointer',
                        fontSize: 11,
                        padding: '1px 7px',
                        flexShrink: 0,
                      }}
                    >
                      {(hl.note || '').trim() ? 'Edit note' : 'Add note'}
                    </button>
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
                  {(hl.note || '').trim() && (
                    <div style={{ fontSize: 12, lineHeight: 1.35, color: 'rgb(147,197,253)', marginTop: 6 }}>
                      Note: {String(hl.note).trim()}
                    </div>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {error && (
        <div style={{ color: 'red', padding: '4px 8px', textAlign: 'center' }}>{error}</div>
      )}

      {hoveredHighlightNote && (
        <div
          style={{
            position: 'fixed',
            left: hoveredHighlightNote.x + 14,
            top: hoveredHighlightNote.y + 16,
            maxWidth: 280,
            padding: '8px 10px',
            background: 'rgba(20,20,20,0.96)',
            border: '1px solid rgba(147,197,253,0.45)',
            borderRadius: 6,
            color: 'rgb(219,234,254)',
            fontSize: 12,
            lineHeight: 1.4,
            boxShadow: '0 8px 18px rgba(0,0,0,0.35)',
            pointerEvents: 'none',
            zIndex: 120,
            whiteSpace: 'pre-wrap',
          }}
        >
          {hoveredHighlightNote.note}
        </div>
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

        {showReadMarker && readMarkerRect && (
          <div
            style={{
              position: 'absolute',
              top: Math.max(8, (readMarkerRect.y * renderInfo.scale) + ((readMarkerRect.h * renderInfo.scale) / 2) - 18),
              left: Math.max(8, renderInfo.tlLeft + (readMarkerRect.x * renderInfo.scale) - 178),
              zIndex: 4,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 10,
              padding: '10px 12px 10px 10px',
              borderRadius: 14,
              background: 'linear-gradient(135deg, rgba(8,145,178,0.96), rgba(14,116,144,0.96))',
              color: '#ecfeff',
              fontSize: 12,
              fontWeight: 800,
              letterSpacing: '0.05em',
              textTransform: 'uppercase',
              border: '1px solid rgba(103,232,249,0.6)',
              boxShadow: '0 10px 24px rgba(0,0,0,0.28)',
              pointerEvents: 'none',
            }}
            title={readAnchor?.text ? `You stopped at: ${readAnchor.text}` : `You marked page ${readPage} as your current stopping point`}
          >
            <span style={{ fontSize: 26, lineHeight: 1 }}>↦</span>
            <span>Read Up Until Here</span>
          </div>
        )}

        {showReadMarker && !readMarkerRect && (
          <div
            style={{
              position: 'absolute',
              top: 18,
              left: Math.max(10, renderInfo.tlLeft - 6),
              zIndex: 4,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 10,
              padding: '10px 12px 10px 10px',
              borderRadius: 14,
              background: 'linear-gradient(135deg, rgba(8,145,178,0.96), rgba(14,116,144,0.96))',
              color: '#ecfeff',
              fontSize: 12,
              fontWeight: 800,
              letterSpacing: '0.05em',
              textTransform: 'uppercase',
              border: '1px solid rgba(103,232,249,0.6)',
              boxShadow: '0 10px 24px rgba(0,0,0,0.28)',
              pointerEvents: 'none',
            }}
            title={`You marked page ${readPage} as your current stopping point`}
          >
            <span style={{ fontSize: 26, lineHeight: 1 }}>↦</span>
            <span>Read Up Until Here</span>
          </div>
        )}

        <HighlightLayer
          pageHighlights={pageHighlights}
          renderInfo={renderInfo}
          deleteHighlight={deleteHighlight}
          focusedHighlightId={focusedHighlightId}
          showHighlightNote={showHighlightNote}
          moveHighlightNote={moveHighlightNote}
          hideHighlightNote={hideHighlightNote}
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
