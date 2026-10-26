import {pdfReaderGroups} from './sharedPdfReader.mjs';
import {observeSearchText} from './pdfSearchObserver.mjs';
import {pageWindow} from './pagedRows.mjs';
import { createPdfSnapshotMode, cropPdfSnapshot, encodePdfSnapshot, paintPdfSnapshotPreview } from './pdfSnapshot.mjs';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {buildPdfHighlightIndex} from './pdfHighlightIndex.mjs';
import {createPdfHighlightTooltip} from './pdfHighlightTooltip.mjs';
import PdfHighlightTooltip from './PdfHighlightTooltip.jsx';
import { usePdfRender } from './usePdfRender.js';
import HighlightLayer, { isResizableTextHighlight } from './HighlightLayer.jsx';
import PdfSelectionLayer from './PdfSelectionLayer.jsx';
import PdfSnapshotLayer, { PdfSnapshotButton } from './PdfSnapshotLayer.jsx';
import PdfLinkPreview from './PdfLinkPreview.jsx';
import PdfPageLinks, {usePdfPageLinks} from './PdfPageLinks.jsx';
import {observePdfToolbarHeight, pdfPageLinksViewport} from './pdfPageLinks.mjs';
import {pdfDestinationScrollRatio} from './pdfDestination.mjs';
import {DEFAULT_PDF_LINK_PREVIEW_ZOOM, normalizePdfLinkPreviewZoom} from './pdfLinkPreview.mjs';
import { normalizePdfHighlightRects, pdfHighlightAtClientPoint } from './pdfHighlightRects.mjs';
import { HL_COLORS, HL_SOLID, highlightSolidColor, normalizeHighlightColor } from './highlightColors.mjs';
import { pushPdfLinkHistory, takePdfLinkHistory } from './pdfLinkHistory.mjs';
import { capturePdfFindStartPage, pdfFindReturnDelta } from './pdfFindHistory.mjs';
import { pdfAnchorScrollRatio } from './pdfAnchorLocation.mjs';
import { pdfImagePoint } from './pdfImagePoint.mjs';
import { pdfPageLocation } from './pdfPageLabels.mjs';
import { resolvePdfContentsLocation } from './pdfContents.mjs';
import { createReaderLanguage } from './i18n.mjs';
import { pdfFocusState, pdfFocusCommand } from './pdfFocus.mjs';
import { joinPdfTextParts, truncatePdfText } from './pdfCjkText.mjs';
import { selectionCleaned, selectionFormatted } from './pdfTextSelection.mjs';
import { stablePdfEndpointCaret } from './pdfSelection.mjs';
import {
  PDF_APPEARANCE_MODES,
  normalizePdfAppearanceMode,
  pdfPageAppearance,
} from './pdfAppearance.mjs';

const CONTROLS_HEIGHT = 250;
const COLLAPSED_CONTROLS_HEIGHT = 138;
const NO_HIGHLIGHTS = [];

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
  display: 'grid',
  alignItems: 'center',
  gridTemplateColumns: '110px minmax(0, 1fr)',
  gap: 12,
  padding: '9px 12px',
  flexWrap: 'wrap',
  width: '100%',
  boxSizing: 'border-box',
  minWidth: 0,
  border: '1px solid #3b3b3e',
  borderRadius: 8,
  background: '#252527',
};

const TOOLBAR_LABEL_STYLE = {
  fontSize: 11,
  fontWeight: 600,
  color: '#a7a7af',
};

const TOOLBAR_STACK_STYLE = {
  display: 'flex',
  alignItems: 'center',
  flexWrap: 'wrap',
  gap: 8,
};

const TOOLBAR_SEPARATOR_STYLE = {
  width: 1,
  height: 24,
  alignSelf: 'center',
  background: '#454548',
};

const PDF_APPEARANCE_SELECT_STYLE = {
  colorScheme: 'dark',
  color: '#f4f4f5',
  backgroundColor: '#27272a',
  border: '1px solid rgba(180,180,180,0.46)',
  borderRadius: 8,
  padding: '0 8px',
};

const PDF_APPEARANCE_OPTION_STYLE = {
  color: '#f4f4f5',
  backgroundColor: '#27272a',
};

const CONTROL_GROUPS = [
  ['navigation', 'reader_navigation'],
  ['reading', 'reader_reading'],
  ['annotation', 'reader_annotation_capture'],
  ['review', 'reader_review_cards'],
];

const DEFAULT_CONTROL_VISIBILITY = {
  navigation: true,
  reading: true,
  annotation: true,
  review: true,
};

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

function caretRangeAtClientPoint(doc, x, y) {
  if (!doc || !Number.isFinite(x) || !Number.isFinite(y)) return null;
  if (typeof doc.caretRangeFromPoint === 'function') {
    return doc.caretRangeFromPoint(x, y);
  }
  if (typeof doc.caretPositionFromPoint === 'function') {
    const position = doc.caretPositionFromPoint(x, y);
    if (position?.offsetNode) {
      const range = doc.createRange();
      range.setStart(position.offsetNode, position.offset);
      range.collapse(true);
      return range;
    }
  }
  return null;
}

function textRangeForPdfHighlight(highlight, textLayer, scale) {
  const rects = normalizePdfHighlightRects(highlight?.rects);
  const doc = textLayer?.ownerDocument;
  if (!doc || !rects.length || !Number.isFinite(scale) || scale <= 0) return null;
  const layerRect = textLayer.getBoundingClientRect();
  const first = rects[0];
  const last = rects[rects.length - 1];
  const start = caretRangeAtClientPoint(
    doc,
    layerRect.left + (first.x * scale) + 1,
    layerRect.top + ((first.y + first.h / 2) * scale),
  );
  const end = caretRangeAtClientPoint(
    doc,
    layerRect.left + ((last.x + last.w) * scale) - 1,
    layerRect.top + ((last.y + last.h / 2) * scale),
  );
  if (!start?.startContainer || !end?.startContainer) return null;
  if (!textLayer.contains(start.startContainer) || !textLayer.contains(end.startContainer)) return null;
  try {
    const range = doc.createRange();
    range.setStart(start.startContainer, start.startOffset);
    range.setEnd(end.startContainer, end.startOffset);
    return range.collapsed ? null : range;
  } catch (_error) {
    return null;
  }
}

function resizedPdfHighlight(highlight, range, textLayer, scale) {
  if (!highlight || !range || !textLayer || !Number.isFinite(scale) || scale <= 0) return null;
  const layerRect = textLayer.getBoundingClientRect();
  const rects = normalizePdfHighlightRects(Array.from(range.getClientRects())
    .map((rect) => rectToPdfCoords(rect, layerRect, scale))
    .filter(Boolean));
  const text = selectionCleaned({ rangeCount: 1, getRangeAt: () => range }, textLayer);
  if (!rects.length || !text) return null;
  const next = { ...highlight, text, rects };
  if (highlight.pdf_annotation && typeof highlight.pdf_annotation === 'object') {
    next.pdf_annotation = { ...highlight.pdf_annotation };
    // Resizing changes the PDF geometry. Preserve the stable annotation name and
    // appearance, but let the sync layer rebuild its quads and native xref.
    delete next.pdf_annotation.quads;
    delete next.pdf_annotation.xref;
  }
  return next;
}

function makeClientHighlightId(prefix = 'hl') {
  return `${prefix}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
}

function escapeHtml(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
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

function normalizeJumpText(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();
}

function firstHighlightRect(highlight) {
  const rects = Array.isArray(highlight?.rects) ? highlight.rects : [];
  const first = rects[0] || {};
  return {
    x: Number(first.x ?? Number.MAX_SAFE_INTEGER),
    y: Number(first.y ?? Number.MAX_SAFE_INTEGER),
  };
}

function compareHighlights(a, b) {
  const pageDiff = Number(a?.page || 0) - Number(b?.page || 0);
  if (pageDiff !== 0) return pageDiff;
  const aRect = firstHighlightRect(a);
  const bRect = firstHighlightRect(b);
  if (aRect.y !== bRect.y) return aRect.y - bRect.y;
  if (aRect.x !== bRect.x) return aRect.x - bRect.x;
  return String(a?.id || '').localeCompare(String(b?.id || ''));
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

function clearSearchHitStyles(textLayer) {
  if (!textLayer) return;
  textLayer.querySelectorAll('span').forEach((span) => {
    if (span.dataset.incSearchHit === '1') {
      if (typeof span.dataset.incSearchOriginalText === 'string') {
        // PDF.js may replace this text between render passes.
        if (span.textContent === span.dataset.incSearchOriginalText) {
          span.textContent = span.dataset.incSearchOriginalText;
        }
        delete span.dataset.incSearchOriginalText;
      }
      span.dataset.incSearchHit = '0';
      delete span.dataset.incSearchQuery;
    }
  });
}

function buildSearchHighlightRegex(query) {
  const phrase = String(query || '').trim();
  if (!phrase) return null;
  const parts = [phrase, ...phrase.split(/\s+/).filter((token) => token.length >= 2)]
    .map((part) => part.trim())
    .filter(Boolean)
    .sort((a, b) => b.length - a.length);
  const unique = Array.from(new Set(parts.map((part) => part.toLowerCase())))
    .map((lowered) => parts.find((part) => part.toLowerCase() === lowered))
    .filter(Boolean);
  if (!unique.length) return null;
  const pattern = unique
    .map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    .join('|');
  return new RegExp(`(${pattern})`, 'gi');
}

function highlightSpanText(span, regex) {
  if (!span || !regex) return false;
  const originalText = String(span.textContent || '');
  if (!originalText) return false;

  regex.lastIndex = 0;
  if (!regex.test(originalText)) {
    if (span.textContent !== originalText) span.textContent = originalText;
    delete span.dataset.incSearchOriginalText;
    return false;
  }
  regex.lastIndex = 0;

  span.dataset.incSearchOriginalText = originalText;
  span.innerHTML = escapeHtml(originalText).replace(
    regex,
    '<span data-inc-search-fragment="1" style="background: rgba(59, 130, 246, 0.28); outline: 1px solid rgba(37, 99, 235, 0.9); border-radius: 2px;">$1</span>',
  );
  return true;
}

function applySearchHitStyles(textLayer, query) {
  if (!textLayer) return null;

  const q = String(query || '').trim().toLowerCase();
  if (!q) { clearSearchHitStyles(textLayer); return null; }

  const spans = Array.from(textLayer.querySelectorAll('span')).filter(
    (span) => span.dataset.incSearchFragment !== '1',
  );
  const regex = buildSearchHighlightRegex(query);
  let firstHit = null;
  for (const span of spans) {
    if (span.dataset.incSearchQuery === q
      && span.textContent === span.dataset.incSearchOriginalText) {
      if (!firstHit) firstHit = span;
      continue;
    }
    const hit = highlightSpanText(span, regex);
    if (!hit) { span.dataset.incSearchHit = '0'; delete span.dataset.incSearchQuery; continue; }
    span.dataset.incSearchHit = '1';
    span.dataset.incSearchQuery = q;
    if (!firstHit) firstHit = span;
  }
  return firstHit;
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
      combined = joinPdfTextParts(combined, piece);
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

function clampScrollRatio(value) {
  const ratio = Number(value);
  if (!Number.isFinite(ratio)) return 0;
  return Math.max(0, Math.min(ratio, 1));
}

function getPdfViewportMetrics(wrapper) {
  if (!wrapper) return null;
  const rect = wrapper.getBoundingClientRect();
  const pageHeight = Math.max(0, wrapper.offsetHeight || rect.height || 0);
  const configuredControlsHeight = Number.parseInt(
    window.getComputedStyle(document.documentElement).getPropertyValue('--pdf-controls-height'),
    10,
  );
  const controlsHeight = Number.isFinite(configuredControlsHeight)
    ? configuredControlsHeight
    : CONTROLS_HEIGHT;
  return pdfPageLinksViewport({scrollY: window.scrollY, wrapperTop: rect.top, pageHeight,
    windowHeight: window.innerHeight, controlsHeight});
}

export default function PdfViewer({readingOnly = false, referenceControls = null} = {}) {
  const [language, setLanguage] = useState(() => createReaderLanguage('en'));
  const [pageLinksDocument, setPageLinksDocument] = useState({cardId: 0, generation: 0});
  const { tr, plural } = language;
  // ── Rendering pipeline (text layer, canvases, zoom, navigation) ────────────
  const {
    page, totalPages, pageLabels, zoom, error, renderInfo, readPage, linkAnnotations, contents, contentsReady,
    canvasARef, canvasBRef, containerRef, textLayerRef,
    pdfDocRef, busyRef, activeCvsRef, cardIdRef, pageRef, lastScaleRef,
    startViewer, nav: rawNav, adjustZoom, setReadProgress: rawSetReadProgress,
  } = usePdfRender();
  const pageLinksState = usePdfPageLinks({cardId: pageLinksDocument.cardId, page,
    generation: pageLinksDocument.generation,
    enabled: !!pdfDocRef.current && !error && renderInfo.cardId === pageLinksDocument.cardId && renderInfo.page === page,
    onCommand: message => {
      const metrics = getPdfViewportMetrics(containerRef.current);
      const point = metrics?.pageHeight > 0 ? clampScrollRatio((window.scrollY - metrics.pageTop) / metrics.pageHeight) : null;
      window.pycmd?.('incremento_pdf_page_links:' + JSON.stringify({...message, page_y: point}));
    }});
  const pageLocationText = pdfPageLocation(page, totalPages, pageLabels, tr);
  const pageLocationTitle = tr('reader_page_jump') + '\n' + tr(
    pageLabels?.[page - 1] ? 'reader_page_numbering_hint' : 'reader_printed_page_unavailable',
  );

  // ── Highlight state ────────────────────────────────────────────────────────
  const [highlights,    setHighlights]    = useState([]);
  const [nativeHighlightsVisible, setNativeHighlightsVisible] = useState(false);
  const [showHighlightControls, setShowHighlightControls] = useState(true);
  const [showHighlightDeleteButtons, setShowHighlightDeleteButtons] = useState(true);
  const [hlColor,       setHlColor]       = useState('yellow');
  const [autoHighlight, setAutoHighlight] = useState(false);
  const [resizingHighlightId, setResizingHighlightId] = useState(null);
  const [highlightColorPopover, setHighlightColorPopover] = useState(null);
  const highlightColorPopoverRef = useRef(null);
  const resizeHighlightRef = useRef(null);
  const highlightRangeCacheRef = useRef(new Map());
  const scrollToTopOnPageChangeRef = useRef(true);
  const hlColorRef       = useRef('yellow');
  const pendingHighlightSelectionRef = useRef(null);
  const autoHighlightRef = useRef(false);
  const applyAutoHighlightSetting = useCallback((value) => {
    const enabled = !!value;
    autoHighlightRef.current = enabled;
    setAutoHighlight(enabled);
  }, []);
  const applyScrollToTopOnPageChangeSetting = useCallback((value) => {
    scrollToTopOnPageChangeRef.current = !!value;
  }, []);

  // ── Snapshot state ─────────────────────────────────────────────────────────
  const [snapshotMode] = useState(createPdfSnapshotMode);
  const snapPreviewRef = useRef(null);
  const snapStartRef = useRef(null);

  // ── Page card panel state ──────────────────────────────────────────────────
  const [pageCards,     setPageCards]     = useState([]);
  const [showHighlightsPanel, setShowHighlightsPanel] = useState(false);
  const [highlightPanelOffset, setHighlightPanelOffset] = useState(0);
  const [bookmarks, setBookmarks] = useState([]);
  const [showBookmarksPanel, setShowBookmarksPanel] = useState(false);
  const [findOpen, setFindOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchHits, setSearchHits] = useState([]);
  const [activeSearchHitIndex, setActiveSearchHitIndex] = useState(-1);
  const [findStartPage, setFindStartPage] = useState(null);
  const [readAnchor, setReadAnchor] = useState(null);
  const [limitStatus, setLimitStatus] = useState(DEFAULT_LIMIT_STATUS);
  const [limitNotice, setLimitNotice] = useState(null);
  const [highlightTooltip] = useState(() => createPdfHighlightTooltip({
    schedule: run => window.requestAnimationFrame(run), cancel: id => window.cancelAnimationFrame(id),
  }));
  useEffect(() => () => highlightTooltip.hide(), [highlightTooltip]);
  const [highlightsScope, setHighlightsScope] = useState('all');
  const [highlightsNotesOnly, setHighlightsNotesOnly] = useState(false);
  const [focusedHighlightId, setFocusedHighlightId] = useState(null);
  const [activeHighlightId, setActiveHighlightId] = useState(null);
  const [highlightJumpNonce, setHighlightJumpNonce] = useState(0);
  const [pageJumpEditing, setPageJumpEditing] = useState(false);
  const [pageJumpValue, setPageJumpValue] = useState('');
  const pendingHighlightScrollRef = useRef(null);
  const pendingExcerptJumpRef = useRef('');
  const pendingReadAnchorScrollRef = useRef(false);
  const pendingPageTopScrollRef = useRef(false);
  const pendingResumeScrollRef = useRef(null);
  const pendingContentsFractionRef = useRef(null);
  const pendingDestinationPointRef = useRef(null);
  const contentsGenerationRef = useRef(0);
  const pendingResumePageRef = useRef(null);
  const suppressScrollPersistUntilRef = useRef(0);
  const lastReadAnchorSpanRef = useRef(null);
  const pageJumpInputRef = useRef(null);
  const findInputRef = useRef(null);
  const suppressSearchSyncRef = useRef(false);
  const [searchJumpNonce, setSearchJumpNonce] = useState(0);
  const [controlsCollapsed, setControlsCollapsed] = useState(() => (
    typeof window._incPdfPending?.controlsCollapsed === 'boolean'
      ? window._incPdfPending.controlsCollapsed
      : true
  ));
  const [compactPanel, setCompactPanel] = useState(null);
  const applyControlsCollapsed = useCallback(collapsed => {
    setControlsCollapsed(collapsed);
    setCompactPanel(null);
    const cardId = Number(cardIdRef.current || 0);
    if (cardId > 0) window.pycmd('incremento_pdf_controls:' + JSON.stringify({cardId, collapsed}));
  }, [cardIdRef]);
  const [savedPdfFocusState, setPdfFocusState] = useState(null);
  const focusState = pdfFocusState(savedPdfFocusState, pageLinksDocument.cardId);
  const focusButton = readingOnly ? null : (
    <button
      type="button"
      aria-pressed={focusState.enabled}
      disabled={!focusState.available}
      title={tr('reader_pdf_focus_mode_hint')}
      onClick={() => {
        const command = pdfFocusCommand(savedPdfFocusState, cardIdRef.current);
        if (command) window.pycmd(command);
      }}
      style={{
        border: focusState.enabled ? '1px solid rgba(96,165,250,0.78)' : '1px solid rgba(180,180,180,0.35)',
        background: focusState.enabled ? 'rgba(59,130,246,0.20)' : 'rgba(255,255,255,0.04)',
        color: focusState.enabled ? 'rgb(147,197,253)' : 'inherit',
        fontWeight: focusState.enabled ? 700 : 400,
        ...(controlsCollapsed ? {} : {padding: '2px 9px', fontSize: 11}),
      }}
    >
      {tr('reader_pdf_focus_mode')}
    </button>
  );
  const controlsRef = useRef(null);
  const [measuredControlsHeight, setMeasuredControlsHeight] = useState(0);
  const [showControlChooser, setShowControlChooser] = useState(false);
  const [controlVisibility, setControlVisibility] = useState(DEFAULT_CONTROL_VISIBILITY);
  const [clickableLinks, setClickableLinks] = useState(false);
  const [linkPreviewZoom, setLinkPreviewZoom] = useState(DEFAULT_PDF_LINK_PREVIEW_ZOOM);
  const applyLinkPreviewZoom = useCallback((value) => {
    const zoom = normalizePdfLinkPreviewZoom(value);
    setLinkPreviewZoom(zoom);
    const cardId = Number(cardIdRef.current || 0);
    if (cardId > 0) window.pycmd('incremento_pdf_link_preview_zoom:' + JSON.stringify({cardId, zoom}));
  }, [cardIdRef]);
  const [linkBackHistory, setLinkBackHistory] = useState([]);
  const [linkBackScrollNonce, setLinkBackScrollNonce] = useState(0);
  const [appearanceMode, setAppearanceMode] = useState('original');
  const pageAppearance = pdfPageAppearance(appearanceMode);
  const applyAppearanceMode = useCallback((value) => {
    const mode = normalizePdfAppearanceMode(value);
    setAppearanceMode(mode);
    const cardId = Number(cardIdRef.current || 0);
    if (cardId > 0) {
      window.pycmd('incremento_pdf_appearance:' + JSON.stringify({ cardId, mode }));
    }
  }, [cardIdRef]);

  const visibleControlsHeight = measuredControlsHeight || (controlsCollapsed ? COLLAPSED_CONTROLS_HEIGHT : CONTROLS_HEIGHT);
  useEffect(() => observePdfToolbarHeight(controlsRef.current, setMeasuredControlsHeight, window.ResizeObserver), []);
  useEffect(() => {
    document.documentElement.style.setProperty('--pdf-controls-height', `${visibleControlsHeight}px`);
    return () => document.documentElement.style.removeProperty('--pdf-controls-height');
  }, [visibleControlsHeight]);

  const clearPendingResumeScroll = useCallback(() => {
    pendingResumeScrollRef.current = null;
    pendingResumePageRef.current = null;
    pendingContentsFractionRef.current = null;
    pendingDestinationPointRef.current = null;
  }, []);

  const openFind = useCallback(() => {
    setControlVisibility(current => ({...current, reading: true}));
    setShowControlChooser(false);
    setFindOpen(true);
    window.setTimeout(() => {
      if (findInputRef.current) {
        findInputRef.current.focus();
        findInputRef.current.select();
      }
    }, 0);
  }, []);

  const suppressScrollPersistence = useCallback((ms = 500) => {
    suppressScrollPersistUntilRef.current = Date.now() + Math.max(0, Number(ms) || 0);
  }, []);

  // ── Highlights for the current page ───────────────────────────────────────
  const highlightIndex = useMemo(() => buildPdfHighlightIndex(highlights, compareHighlights), [highlights]);
  const pageHighlights = highlightIndex.byPage.get(page) || NO_HIGHLIGHTS;
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
  const sortedHighlights = highlightIndex.sorted;
  const scopedHighlightsForPanel = highlightsScope === 'page'
    ? (highlightIndex.sortedByPage.get(page) || NO_HIGHLIGHTS)
    : sortedHighlights;
  const highlightsForPanel = useMemo(() => highlightsNotesOnly
    ? scopedHighlightsForPanel.filter((h) => String(h.note || '').trim())
    : scopedHighlightsForPanel, [scopedHighlightsForPanel, highlightsNotesOnly]);
  const missingCardHighlightCount = highlightIndex.missingCards;
  const highlightPanelPage = pageWindow(highlightsForPanel.length, highlightPanelOffset);
  useEffect(() => { setHighlightPanelOffset(0); }, [page, highlightsScope, highlightsNotesOnly]);
  useEffect(() => {
    const index = highlightsForPanel.findIndex(highlight => String(highlight.id) === String(activeHighlightId));
    if (index >= 0) setHighlightPanelOffset(Math.floor(index / 50) * 50);
  }, [activeHighlightId]);
  const currentHighlightIndex = highlightIndex.byId.get(String(activeHighlightId || '')) ?? -1;
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

  const showHighlightNote = highlightTooltip.show;
  const moveHighlightNote = highlightTooltip.move;
  const hideHighlightNote = highlightTooltip.hide;

  const describeLimitReached = useCallback(() => {
    const prefix = limitTotal > 0
      ? tr('reader_limit_reached_pages', { used: Math.max(limitUsed, limitTotal), total: limitTotal })
      : tr('reader_limit_reached_pdf');
    if (limitMode === 'hard_stop') {
      return tr('reader_limit_reached_hard', { prefix });
    }
    return tr('reader_limit_reached_soft', { prefix });
  }, [limitMode, limitTotal, limitUsed, tr]);

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
        text: tr('reader_moving_past_limit', { count: limitTotal }),
      });
      return true;
    }
    setLimitNotice({
      kind: limitMode === 'soft_lock' ? 'soft_lock' : 'hard_stop',
      text: describeLimitReached(),
    });
    return false;
  }, [allowedMaxPage, describeLimitReached, limitEnabled, limitMode, limitTotal, overrideEnabled, pageRef, tr]);

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
        text: tr('reader_read_past_limit', { count: limitTotal }),
      });
      return true;
    }
    setLimitNotice({
      kind: limitMode === 'soft_lock' ? 'soft_lock' : 'hard_stop',
      text: describeLimitReached(),
    });
    return false;
  }, [allowedMaxPage, describeLimitReached, limitEnabled, limitMode, limitTotal, overrideEnabled, tr]);

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
          text: truncatePdfText(selectionCleaned(selection, tl), 240),
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
      text: truncatePdfText(String(span.textContent || '').trim(), 240),
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
        text: tr('reader_override_notice'),
      });
      return;
    }
    if (!limitReached && limitNotice?.kind !== 'warning') {
      setLimitNotice(null);
    }
  }, [limitEnabled, limitNotice?.kind, limitReached, overrideEnabled, tr]);

  useEffect(() => {
    const pendingId = pendingHighlightScrollRef.current;
    const wrapper = containerRef.current;
    if (!wrapper) return;

    const scrollToPdfRect = (rect, leftBias = 0.25, topPad = 24) => {
      if (!rect) return false;
      const wrapperRect = wrapper.getBoundingClientRect();
      const scale = renderInfo?.scale || 1;
      const tlLeft = renderInfo?.tlLeft || 0;
      const pageTop = getPdfViewportMetrics(wrapper)?.pageTop ?? window.scrollY + wrapperRect.top;
      const targetTop = pageTop + (rect.y * scale) - topPad;
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
      clearPendingResumeScroll();
      suppressScrollPersistence(900);
      setActiveHighlightId(String(pendingId));
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
          clearPendingResumeScroll();
          suppressScrollPersistence(900);
          setActiveHighlightId(String(highlightTarget.id || ''));
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
            clearPendingResumeScroll();
            suppressScrollPersistence(900);
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
        clearPendingResumeScroll();
        suppressScrollPersistence(900);
        scrollToPdfRect(readMarkerRect, 0.15, 80);
      }
      pendingReadAnchorScrollRef.current = false;
      return;
    }

    if (pendingPageTopScrollRef.current) {
      pendingPageTopScrollRef.current = false;
      clearPendingResumeScroll();
      suppressScrollPersistence(700);
      window.scrollTo({
        top: Math.max(0, getPdfViewportMetrics(wrapper)?.pageTop || 0),
        left: window.scrollX,
        behavior: 'auto',
      });
      return;
    }

    const pendingResumePage = pendingResumePageRef.current;
    const pendingResumeScroll = pendingResumeScrollRef.current;
    if (
      pendingResumePage != null
      && pendingResumeScroll != null
      && Number(pendingResumePage) === page
    ) {
      const metrics = getPdfViewportMetrics(wrapper);
      if (!metrics) return;
      const pageFraction = pendingContentsFractionRef.current;
      const destinationPoint = pendingDestinationPointRef.current;
      const ratio = destinationPoint != null ? pdfDestinationScrollRatio(destinationPoint, metrics.pageHeight, metrics.visibleHeight)
        : pageFraction == null ? clampScrollRatio(pendingResumeScroll)
        : metrics.maxOffset > 0 ? clampScrollRatio(pageFraction * metrics.pageHeight / metrics.maxOffset) : 0;
      clearPendingResumeScroll();
      suppressScrollPersistence(700);
      window.scrollTo({
        top: Math.max(0, metrics.pageTop + (ratio * metrics.maxOffset)),
        left: window.scrollX,
        behavior: 'auto',
      });
    }
  }, [
    page,
    renderInfo,
    highlights,
    containerRef,
    highlightJumpNonce,
    showReadMarker,
    readMarkerRect,
    textLayerRef,
    clearPendingResumeScroll,
    suppressScrollPersistence,
    linkBackScrollNonce,
  ]);

  useEffect(() => {
    const tl = textLayerRef.current;
    if (!tl) return;
    let didScroll = false;

    const renderSearchHits = () => {
      const firstHit = applySearchHitStyles(tl, searchQuery);
      if (!firstHit || didScroll) return;
      didScroll = true;
      clearPendingResumeScroll();
      suppressScrollPersistence(900);
      try {
        firstHit.scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' });
      } catch (_) {}
    };

    return observeSearchText(tl, {
      render: renderSearchHits,
      clear: () => clearSearchHitStyles(tl),
    });
  }, [searchQuery, page, renderInfo, textLayerRef, clearPendingResumeScroll, suppressScrollPersistence, searchJumpNonce]);

  useEffect(() => {
    if (String(searchQuery || '').trim()) {
      const currentPage = pageRef.current;
      setFindStartPage((startPage) => capturePdfFindStartPage(startPage, currentPage));
    } else {
      setFindStartPage(null);
    }
    if (suppressSearchSyncRef.current) {
      suppressSearchSyncRef.current = false;
      return;
    }
    if (typeof window.pycmd === 'function') {
      window.pycmd('incremento_pdf_find:' + JSON.stringify({ query: searchQuery || '' }));
    }
  }, [pageRef, searchQuery]);

  useEffect(() => {
    const onKeyDown = (event) => {
      if ((event.metaKey || event.ctrlKey) && String(event.key || '').toLowerCase() === 'f') {
        event.preventDefault();
        event.stopPropagation();
        openFind();
        return;
      }
      if (event.key === 'Escape' && findOpen) {
        event.preventDefault();
        setFindOpen(false);
      }
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [findOpen, openFind]);

  useEffect(() => {
    let timer = 0;
    const reportScrollRatio = () => {
      timer = 0;
      if (!cardIdRef.current || Date.now() < suppressScrollPersistUntilRef.current) {
        return;
      }
      const wrapper = containerRef.current;
      const metrics = getPdfViewportMetrics(wrapper);
      if (!metrics) return;
      const ratio = metrics.maxOffset <= 0
        ? 0
        : clampScrollRatio((window.scrollY - metrics.pageTop) / metrics.maxOffset);
      window.pycmd('incremento_pdf_scroll:' + JSON.stringify({
        cardId: cardIdRef.current,
        scrollRatio: ratio,
      }));
    };
    const scheduleReport = () => {
      if (timer) window.clearTimeout(timer);
      timer = window.setTimeout(reportScrollRatio, 180);
    };
    window.addEventListener('scroll', scheduleReport, { passive: true });
    window.addEventListener('resize', scheduleReport);
    return () => {
      if (timer) window.clearTimeout(timer);
      window.removeEventListener('scroll', scheduleReport);
      window.removeEventListener('resize', scheduleReport);
    };
  }, [cardIdRef, containerRef]);

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
    paintPdfSnapshotPreview(snapPreviewRef.current, null);
    e.preventDefault();
  }, []);

  const handleSnapMove = useCallback((e) => {
    if (!snapStartRef.current) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const cy = e.clientY - rect.top;
    const { x: sx, y: sy } = snapStartRef.current;
    paintPdfSnapshotPreview(snapPreviewRef.current, { x: Math.min(sx, cx), y: Math.min(sy, cy),
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
    snapshotMode.setActive(false);
    paintPdfSnapshotPreview(snapPreviewRef.current, null);

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

    const tmp = cropPdfSnapshot(cvs, {x: cx, y: cy, w: cw, h: ch},
      () => document.createElement('canvas'));
    if (!tmp) return;
    const cardId = cardIdRef.current;
    const page = pageRef.current;
    const generation = contentsGenerationRef.current;
    const isCurrent = () => !!containerRef.current?.isConnected
      && cardId === cardIdRef.current && page === pageRef.current
      && generation === contentsGenerationRef.current;
    encodePdfSnapshot(tmp, isCurrent).then(image => {
      if (image) window.pycmd('incremento_pdf_snapshot:' + JSON.stringify({ cardId, page, image }));
    }).catch(() => { console.warn('PDF snapshot encoding failed'); });
  }, [activeCvsRef, canvasARef, canvasBRef, cardIdRef, makeSnapshotHighlight, pageRef, snapshotMode]);

  // ── Highlight helpers ──────────────────────────────────────────────────────
  const deleteHighlight = useCallback((id) => {
    setHighlights(prev => prev.filter(h => h.id !== id));
    highlightRangeCacheRef.current.delete(String(id || ''));
    if (resizeHighlightRef.current?.id === String(id || '')) {
      resizeHighlightRef.current = null;
      setResizingHighlightId(null);
    }
    window.pycmd('incremento_pdf_hl_del:' + JSON.stringify({ cardId: cardIdRef.current, id }));
  }, [cardIdRef]);

  const editHighlightNote = useCallback((id) => {
    window.pycmd('incremento_pdf_hl_note:' + JSON.stringify({ id }));
  }, []);

  const updateHighlightNote = useCallback((id, note) => {
    setHighlights(prev => prev.map((h) => (
      h.id === id ? { ...h, note: String(note || '') } : h
    )));
  }, []);

  const activateHighlightResize = useCallback((highlight) => {
    const tl = textLayerRef.current;
    const scale = Number(lastScaleRef.current || 0);
    if (!highlight || !tl || !scale) return false;
    const id = String(highlight.id || '');
    let range = highlightRangeCacheRef.current.get(id) || null;
    if (!range?.commonAncestorContainer || !tl.contains(range.commonAncestorContainer)) {
      highlightRangeCacheRef.current.delete(id);
      range = textRangeForPdfHighlight(highlight, tl, scale);
      if (range) highlightRangeCacheRef.current.set(id, range.cloneRange());
    }
    if (!range) return false;
    resizeHighlightRef.current = {
      id,
      range: range.cloneRange(),
      original: highlight,
      preview: highlight,
      dragging: false,
      pointerId: null,
      dragState: {},
    };
    setResizingHighlightId(id);
    return true;
  }, [lastScaleRef, textLayerRef]);

  const deactivateHighlightResize = useCallback(() => {
    resizeHighlightRef.current = null;
    setResizingHighlightId(null);
  }, []);

  const showHighlightColorPopover = useCallback((highlight, point) => {
    if (!showHighlightControls || !highlight || highlight.color === 'snapshot') {
      setHighlightColorPopover(null);
      return;
    }
    hideHighlightNote();
    setHighlightColorPopover({ id: highlight.id, page: pageRef.current, cardId: cardIdRef.current,
      x: Number(point.clientX), y: Number(point.clientY) });
  }, [cardIdRef, hideHighlightNote, pageRef, showHighlightControls]);

  const activateHighlightAtClientPoint = useCallback((point) => {
    if (!showHighlightControls) return false;
    const wrapper = containerRef.current;
    if (!wrapper) return false;
    const highlight = pdfHighlightAtClientPoint(
      pageHighlights,
      renderInfo,
      wrapper.getBoundingClientRect(),
      Number(point?.clientX),
      Number(point?.clientY),
    );
    showHighlightColorPopover(highlight, point);
    if (isResizableTextHighlight(highlight)) return activateHighlightResize(highlight);
    deactivateHighlightResize();
    return false;
  }, [activateHighlightResize, containerRef, deactivateHighlightResize, pageHighlights, renderInfo, showHighlightControls, showHighlightColorPopover]);

  const activateHighlightFromPageClick = useCallback((event) => {
    if (snapshotMode.getSnapshot() || event?.defaultPrevented) return;
    const interactive = event?.target?.closest?.('button,a,input,textarea,select,[contenteditable="true"]');
    if (interactive) return;
    const selection = window.getSelection?.();
    if (selection && !selection.isCollapsed) {
      setHighlightColorPopover(null);
      deactivateHighlightResize();
      return;
    }
    activateHighlightAtClientPoint(event);
  }, [activateHighlightAtClientPoint, deactivateHighlightResize, snapshotMode]);

  const colorPopoverHighlight = showHighlightControls
    && highlightColorPopover?.page === page
    && highlightColorPopover?.cardId === cardIdRef.current
    ? pageHighlights.find(h => h.id === highlightColorPopover.id && h.color !== 'snapshot') : null;

  useEffect(() => {
    if (!colorPopoverHighlight) return undefined;
    const dismiss = () => setHighlightColorPopover(null);
    const outside = event => {
      if (!highlightColorPopoverRef.current?.contains(event.target)) dismiss();
    };
    const onKey = event => {
      if (event.key === 'Escape') {
        event.preventDefault();
        dismiss();
      }
    };
    // Keyboard focus can queue a scroll event before the palette opens. Ignore
    // that delayed notification unless the viewport has actually moved since.
    const scrollX = window.scrollX;
    const scrollY = window.scrollY;
    const onScroll = event => {
      if (event.target !== document || window.scrollX !== scrollX || window.scrollY !== scrollY) dismiss();
    };
    const popup = highlightColorPopoverRef.current;
    (popup?.querySelector('button[aria-pressed="true"]') || popup?.querySelector('button'))?.focus({ preventScroll: true });
    document.addEventListener('pointerdown', outside, true);
    document.addEventListener('keydown', onKey);
    window.addEventListener('scroll', onScroll, true);
    window.addEventListener('resize', dismiss);
    return () => {
      document.removeEventListener('pointerdown', outside, true);
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('scroll', onScroll, true);
      window.removeEventListener('resize', dismiss);
    };
  }, [colorPopoverHighlight, highlightColorPopover]);

  useEffect(() => {
    if (!resizingHighlightId) return undefined;
    const dismissHighlightResizeOutside = (event) => {
      const target = event?.target;
      if (target?.closest?.('.incremento-pdf-highlight-resize-handle, .incremento-pdf-highlight-actions')) return;
      if (target && containerRef.current?.contains(target)) return;
      deactivateHighlightResize();
    };
    document.addEventListener('pointerdown', dismissHighlightResizeOutside, true);
    return () => document.removeEventListener('pointerdown', dismissHighlightResizeOutside, true);
  }, [containerRef, deactivateHighlightResize, resizingHighlightId]);

  const updateHighlightResizePreview = useCallback((event) => {
    const session = resizeHighlightRef.current;
    const tl = textLayerRef.current;
    const scale = Number(lastScaleRef.current || 0);
    if (!session?.dragging || !tl || !scale) return false;
    if (session.pointerId !== null && Number(event?.pointerId) !== session.pointerId) return false;
    const caret = stablePdfEndpointCaret(
      tl,
      session.range,
      session.endpoint,
      Number(event?.clientX),
      Number(event?.clientY),
      { document: tl.ownerDocument, dragState: session.dragState },
    );
    if (!caret?.startContainer || !tl.contains(caret.startContainer)) return false;
    try {
      const nextRange = tl.ownerDocument.createRange();
      if (session.endpoint === 'start') {
        nextRange.setStart(caret.startContainer, caret.startOffset);
        nextRange.setEnd(session.range.endContainer, session.range.endOffset);
      } else {
        nextRange.setStart(session.range.startContainer, session.range.startOffset);
        nextRange.setEnd(caret.startContainer, caret.startOffset);
      }
      if (nextRange.collapsed) return false;
      const nextHighlight = resizedPdfHighlight(session.preview, nextRange, tl, scale);
      if (!nextHighlight) return false;
      session.range = nextRange;
      session.preview = nextHighlight;
      setHighlights((previous) => previous.map((item) => (
        String(item.id || '') === session.id ? nextHighlight : item
      )));
      return true;
    } catch (_error) {
      return false;
    }
  }, [lastScaleRef, textLayerRef]);

  const beginHighlightResize = useCallback((highlight, endpoint, event) => {
    // Prefer the exact saved range, but reconstruct it when PDF.js has replaced
    // the text spans after a zoom or render change.
    if (!activateHighlightResize(highlight)) return;
    setHighlightColorPopover(null);
    const session = resizeHighlightRef.current;
    if (!session || (endpoint !== 'start' && endpoint !== 'end')) return;
    event?.preventDefault?.();
    event?.stopPropagation?.();
    event?.currentTarget?.setPointerCapture?.(event.pointerId);
    session.original = highlight;
    session.preview = highlight;
    session.endpoint = endpoint;
    session.dragging = true;
    session.pointerId = Number.isFinite(Number(event?.pointerId)) ? Number(event.pointerId) : null;
    hideHighlightNote();
  }, [activateHighlightResize, hideHighlightNote]);

  const moveHighlightResize = useCallback((event) => {
    updateHighlightResizePreview(event);
  }, [updateHighlightResizePreview]);

  const endHighlightResize = useCallback((event) => {
    const session = resizeHighlightRef.current;
    if (!session?.dragging) return;
    updateHighlightResizePreview(event);
    session.dragging = false;
    event?.currentTarget?.releasePointerCapture?.(event.pointerId);
    if (session.preview && String(session.preview.id || '') === session.id) {
      window.pycmd('incremento_pdf_hl_update:' + JSON.stringify({
        cardId: cardIdRef.current,
        highlight: session.preview,
      }));
      session.original = session.preview;
      highlightRangeCacheRef.current.set(session.id, session.range.cloneRange());
    }
    session.pointerId = null;
    session.endpoint = null;
    session.dragState = {};
  }, [cardIdRef, updateHighlightResizePreview]);

  const cancelHighlightResize = useCallback((event) => {
    const session = resizeHighlightRef.current;
    if (!session?.dragging) return;
    session.dragging = false;
    event?.currentTarget?.releasePointerCapture?.(event.pointerId);
    const original = session.original;
    setHighlights((previous) => previous.map((item) => (
      String(item.id || '') === session.id ? original : item
    )));
    session.preview = original;
    session.pointerId = null;
    resizeHighlightRef.current = null;
    setResizingHighlightId(null);
  }, []);

  useEffect(() => {
    const session = resizeHighlightRef.current;
    if (session?.dragging && session.original) {
      setHighlights((previous) => previous.map((item) => (
        String(item.id || '') === session.id ? session.original : item
      )));
    }
    resizeHighlightRef.current = null;
    setResizingHighlightId(null);
    setHighlightColorPopover(null);
    highlightRangeCacheRef.current.clear();
  }, [page]);

  const recolorHighlight = useCallback((id, value) => {
    const color = normalizeHighlightColor(value);
    const original = highlights.find(h => h.id === id);
    if (!color || !original || original.color === 'snapshot') return;
    const highlight = { ...original, color };
    if (original.pdf_annotation) {
      const hex = highlightSolidColor(color);
      highlight.pdf_annotation = { ...original.pdf_annotation,
        color: [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255) };
    }
    setHighlights(previous => previous.map(h => h.id === id ? highlight : h));
    window.pycmd('incremento_pdf_hl_update:' + JSON.stringify({ cardId: cardIdRef.current, highlight }));
  }, [highlights, cardIdRef]);

  const makeHighlight = useCallback((sel, forcedColor = null) => {
    if (!sel || sel.isCollapsed || !sel.rangeCount) return false;
    const tl = textLayerRef.current;
    const range = sel.getRangeAt(0);
    if (!tl || !tl.contains(range.commonAncestorContainer)) return false;
    const tlRect = tl.getBoundingClientRect();
    const scale = lastScaleRef.current;
    // Saved highlights use unscaled PDF coordinates so they survive zoom changes.
    // Merge their word boxes with the same rule as the live blue selection; the
    // saved annotation therefore keeps the continuous appearance after reopening.
    const rects = normalizePdfHighlightRects(Array.from(range.getClientRects())
      .map(r => ({
        x: (r.left - tlRect.left) / scale,
        y: (r.top  - tlRect.top)  / scale,
        w: r.width  / scale,
        h: r.height / scale,
      })))
      .filter(r => r.w > 0 && r.h > 0);
    if (!rects.length) return false;
    const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
    const hl = {
      id,
      page: pageRef.current,
      color: forcedColor || hlColorRef.current,
      text: selectionCleaned(sel, tl),
      rects,
    };
    setHighlights(prev => [...prev, hl]);
    highlightRangeCacheRef.current.set(
      id,
      typeof range.cloneRange === 'function' ? range.cloneRange() : range,
    );
    resizeHighlightRef.current = null;
    setResizingHighlightId(null);
    window.pycmd('incremento_pdf_hl_add:' + JSON.stringify({ cardId: cardIdRef.current, highlight: hl }));
    sel.removeAllRanges?.();
    return true;
  }, [textLayerRef, lastScaleRef, pageRef, cardIdRef]);

  const pickHighlightColor = useCallback((color, applyNow = false) => {
    color = normalizeHighlightColor(color);
    if (!color) return;
    hlColorRef.current = color;
    setHlColor(color);
    if (!applyNow) return;
    const sel = window.getSelection();
    if (makeHighlight(sel, color) && sel?.removeAllRanges) {
      sel.removeAllRanges();
    }
  }, [makeHighlight]);

  const openHighlightColorPicker = useCallback((highlight = null) => {
    const sel = window.getSelection();
    const range = sel && !sel.isCollapsed && sel.rangeCount ? sel.getRangeAt(0) : null;
    pendingHighlightSelectionRef.current = highlight ? { id: highlight.id, page: pageRef.current, cardId: cardIdRef.current } : range && textLayerRef.current?.contains(range.commonAncestorContainer)
      ? { range: range.cloneRange(), page: pageRef.current, cardId: cardIdRef.current } : null;
    window.pycmd('incremento_pdf_hl_color:' + JSON.stringify({
      cardId: cardIdRef.current, currentColor: highlight?.color || hlColorRef.current,
    }));
  }, [cardIdRef, textLayerRef, pageRef]);

  const finishHighlightColorPicker = useCallback((value) => {
    const pending = pendingHighlightSelectionRef.current;
    pendingHighlightSelectionRef.current = null;
    const color = normalizeHighlightColor(value);
    if (!color) return;
    pickHighlightColor(color);
    if (!pending || pending.page !== pageRef.current || pending.cardId !== cardIdRef.current) return;
    if (pending.id) {
      recolorHighlight(pending.id, color);
      return;
    }
    const range = pending.range;
    if (range && makeHighlight({
      rangeCount: 1, isCollapsed: range.collapsed,
      getRangeAt: () => range, toString: () => range.toString(),
    }, color)) window.getSelection()?.removeAllRanges();
  }, [pickHighlightColor, makeHighlight, recolorHighlight, pageRef, cardIdRef]);

  const limitAwareNav = useCallback((delta, options = {}) => {
    const scrollToTop = options.scrollToTop !== undefined
      ? !!options.scrollToTop
      : delta > 0;
    if (delta > 0) {
      const nextPage = pageRef.current + delta;
      if (!canMoveToPage(nextPage)) {
        return false;
      }
    }
    clearPendingResumeScroll();
    pendingPageTopScrollRef.current = !!(scrollToTop && scrollToTopOnPageChangeRef.current);
    suppressScrollPersistence(600);
    rawNav(delta);
    return true;
  }, [canMoveToPage, clearPendingResumeScroll, pageRef, rawNav, suppressScrollPersistence]);

  const returnToFindStartPage = useCallback(() => {
    const delta = pdfFindReturnDelta(findStartPage, pageRef.current);
    if (delta === null) return false;
    if (delta === 0) return true;
    return limitAwareNav(delta, { scrollToTop: false });
  }, [findStartPage, limitAwareNav, pageRef]);

  const capturePdfLinkLocation = useCallback(() => {
    const currentPage = Number(pageRef.current || 0);
    if (!Number.isInteger(currentPage) || currentPage < 1) return null;
    const metrics = getPdfViewportMetrics(containerRef.current);
    const scrollRatio = !metrics || metrics.maxOffset <= 0
      ? 0
      : clampScrollRatio((window.scrollY - metrics.pageTop) / metrics.maxOffset);
    return { page: currentPage, scrollRatio };
  }, [containerRef, pageRef]);

  useEffect(() => {
    window.incrementoPdfImagePointAtPoint = (x, y) => {
      if (!pdfDocRef.current || busyRef.current) return null;
      const canvas = activeCvsRef.current === 'a' ? canvasARef.current : canvasBRef.current;
      if (!canvas || Number(canvas.dataset.pdfCard) !== cardIdRef.current
        || Number(canvas.dataset.pdfPage) !== pageRef.current) return null;
      return pdfImagePoint(x, y, canvas.getBoundingClientRect());
    };
    return () => { delete window.incrementoPdfImagePointAtPoint; };
  }, [activeCvsRef, busyRef, canvasARef, canvasBRef, cardIdRef, pageRef, pdfDocRef]);

  useEffect(() => {
    window.incrementoPdfAnchorAtPoint = (clientX, clientY) => {
      const wrapper = containerRef.current;
      const cardId = Number(cardIdRef.current || 0);
      const currentPage = Number(pageRef.current || 0);
      if (!wrapper || !Number.isInteger(cardId) || cardId <= 0) return null;
      if (!Number.isInteger(currentPage) || currentPage <= 0) return null;

      const x = Number(clientX);
      const y = Number(clientY);
      if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
      const target = document.elementFromPoint(x, y);
      if (!target || !wrapper.contains(target)) return null;

      const rect = wrapper.getBoundingClientRect();
      const metrics = getPdfViewportMetrics(wrapper);
      const scrollRatio = pdfAnchorScrollRatio({
        clientY: y,
        wrapperTop: rect.top,
        pageHeight: metrics?.pageHeight,
        visibleHeight: metrics?.visibleHeight,
      });
      if (scrollRatio === null) return null;
      return { cardId, page: currentPage, pageLabel: pageLabels?.[currentPage - 1] || '', scrollRatio };
    };
    return () => {
      delete window.incrementoPdfAnchorAtPoint;
    };
  }, [cardIdRef, containerRef, pageLabels, pageRef]);

  const jumpBackFromPdfLink = useCallback(() => {
    const taken = takePdfLinkHistory(linkBackHistory);
    const target = taken.location;
    if (!target) return;

    const delta = target.page - pageRef.current;
    if (delta !== 0 && !limitAwareNav(delta, { scrollToTop: false })) return;

    pendingHighlightScrollRef.current = null;
    pendingExcerptJumpRef.current = '';
    pendingReadAnchorScrollRef.current = false;
    pendingPageTopScrollRef.current = false;
    pendingResumePageRef.current = target.page;
    pendingResumeScrollRef.current = target.scrollRatio;
    pendingContentsFractionRef.current = null;
    suppressScrollPersistence(700);
    setLinkBackHistory(taken.history);
    if (delta === 0) setLinkBackScrollNonce(value => value + 1);
  }, [limitAwareNav, linkBackHistory, pageRef, suppressScrollPersistence]);

  const openContents = useCallback(() => {
    if (!contentsReady || !cardIdRef.current) return;
    window.pycmd('incremento_pdf_contents:' + JSON.stringify({
      cardId: cardIdRef.current, totalPages, token: contentsGenerationRef.current,
      location: capturePdfLinkLocation(),
      entries: contents.map(({id, title, depth, page: targetPage}) => ({id, title, depth, page: targetPage})),
    }));
  }, [cardIdRef, capturePdfLinkLocation, contents, contentsReady, totalPages]);

  useEffect(() => {
    window.incrementoPdfOpenContents = openContents;
    window.incrementoPdfContentsJump = async (entry, token) => {
      if (token !== contentsGenerationRef.current) return;
      const doc = pdfDocRef.current;
      const source = capturePdfLinkLocation();
      if (!doc || !source) return;
      const target = entry.saved_place
        ? {page: Number(entry.page), scrollRatio: clampScrollRatio(entry.scroll_ratio)}
        : await resolvePdfContentsLocation(doc, contents.find(item => item.id === entry.id));
      if (!target || doc !== pdfDocRef.current || token !== contentsGenerationRef.current || pageRef.current !== source.page) return;
      if (!Number.isInteger(target.page) || target.page < 1 || target.page > doc.numPages) return;
      const delta = target.page - source.page;
      if (delta !== 0 && !limitAwareNav(delta, {scrollToTop: false})) return;
      pendingHighlightScrollRef.current = null;
      pendingExcerptJumpRef.current = '';
      pendingReadAnchorScrollRef.current = false;
      pendingPageTopScrollRef.current = false;
      pendingResumePageRef.current = target.page;
      pendingResumeScrollRef.current = target.scrollRatio ?? 0;
      pendingContentsFractionRef.current = target.pageFraction ?? null;
      suppressScrollPersistence(700);
      setLinkBackHistory(history => pushPdfLinkHistory(history, source));
      if (delta === 0) setLinkBackScrollNonce(value => value + 1);
    };
    return () => {
      delete window.incrementoPdfOpenContents;
      delete window.incrementoPdfContentsJump;
    };
  }, [capturePdfLinkLocation, contents, limitAwareNav, openContents, pageRef, pdfDocRef, suppressScrollPersistence]);

  const activatePdfLink = useCallback((event, link) => {
    if (!clickableLinks || !event?.nativeEvent?.isTrusted || !link) return;
    event.preventDefault();
    event.stopPropagation();
    if (link.kind === 'internal') {
      const targetPage = Number(link.targetPage || 0);
      const delta = targetPage - pageRef.current;
      if (Number.isInteger(targetPage) && targetPage > 0 && delta !== 0) {
        const sourceLocation = capturePdfLinkLocation();
        if (limitAwareNav(delta, { scrollToTop: false }) && sourceLocation) {
          setLinkBackHistory(history => pushPdfLinkHistory(history, sourceLocation));
        }
      }
      return;
    }
    if (link.kind === 'external' && link.url && cardIdRef.current) {
      window.pycmd('incremento_pdf_open_link:' + JSON.stringify({
        cardId: cardIdRef.current,
        url: String(link.url),
      }));
    }
  }, [cardIdRef, capturePdfLinkLocation, clickableLinks, limitAwareNav, pageRef]);

  const jumpToHighlight = useCallback((highlight, { closePanel = false } = {}) => {
    if (!highlight?.id) return;
    const targetPage = Math.max(1, parseInt(highlight.page || 1, 10));
    const delta = targetPage - pageRef.current;
    pendingHighlightScrollRef.current = String(highlight.id);
    setActiveHighlightId(String(highlight.id));
    setHighlightJumpNonce((n) => n + 1);
    if (delta !== 0) {
      limitAwareNav(delta, { scrollToTop: false });
    }
    if (closePanel) {
      setShowHighlightsPanel(false);
    }
  }, [limitAwareNav, pageRef]);

  const moveHighlightCursor = useCallback((direction) => {
    if (!sortedHighlights.length) return;
    let baseIndex = currentHighlightIndex;
    if (baseIndex < 0) {
      baseIndex = sortedHighlights.findIndex((highlight) => Number(highlight.page || 0) >= Number(pageRef.current || 0));
      if (baseIndex < 0) {
        baseIndex = direction > 0 ? -1 : 0;
      }
    }
    const offset = direction >= 0 ? 1 : -1;
    const nextIndex = (baseIndex + offset + sortedHighlights.length) % sortedHighlights.length;
    jumpToHighlight(sortedHighlights[nextIndex], { closePanel: false });
  }, [currentHighlightIndex, jumpToHighlight, pageRef, sortedHighlights]);

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
      limitAwareNav(delta, { scrollToTop: false });
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
    limitAwareNav(targetPage - pageRef.current, { scrollToTop: false });
  }, [limitAwareNav, pageRef]);

  const limitAwareMarkRead = useCallback(() => {
    if (!canMarkReadAtPage(pageRef.current)) {
      return;
    }
    const nextReadPage = pageRef.current <= readPage ? 0 : pageRef.current;
    setReadAnchor(null);
    rawSetReadProgress(nextReadPage, null);
  }, [canMarkReadAtPage, pageRef, rawSetReadProgress, readPage]);

  const clearReadAnchor = useCallback(() => {
    const currentPage = pageRef.current;
    if (!canMarkReadAtPage(currentPage)) {
      return;
    }
    setReadAnchor(null);
    rawSetReadProgress(currentPage, null);
  }, [canMarkReadAtPage, pageRef, rawSetReadProgress]);

  const limitAwareMarkReadAnchor = useCallback((event = null) => {
    const currentPage = pageRef.current;
    if (!canMarkReadAtPage(currentPage)) {
      return;
    }
    if (event?.shiftKey) {
      clearReadAnchor();
      return;
    }
    const anchor = buildReadAnchor();
    if (!anchor) {
      return;
    }
    setReadAnchor(anchor);
    rawSetReadProgress(currentPage, anchor);
  }, [buildReadAnchor, canMarkReadAtPage, clearReadAnchor, pageRef, rawSetReadProgress]);

  // ── Register globals + consume pending ────────────────────────────────────
  useEffect(() => {
    // Wrap startViewer to also consume pending highlights.
    const startWithHighlights = (
      cardId,
      filename,
      startPage,
      startZoom,
      startScrollRatio = 0.0,
      startReadPage = 0,
      startReadAnchor = null,
      startSearchQuery = '',
      startSearchHits = [],
      startActiveSearchHitIndex = -1,
      startJumpExcerpt = '',
      startJumpHighlightId = '',
      startScrollToReadAnchor = false,
      startLimitStatus = null,
      startAutoHighlightOnExtract = undefined,
      startScrollToTopOnPageChange = true,
      startBookmarks = null,
      startLocale = 'en',
      startCustomLanguage = null,
      startAppearanceMode = 'original',
      startShowHighlightDeleteButtons = true,
      startLinkPreviewZoom = DEFAULT_PDF_LINK_PREVIEW_ZOOM,
      startPageY = null,
      startControlsCollapsed = null,
    ) => {
      setPageLinksDocument(current => ({cardId: Number(cardId), generation: current.generation + 1}));
      contentsGenerationRef.current += 1;
      snapshotMode.setActive(false);
      snapStartRef.current = null;
      pendingContentsFractionRef.current = null;
      pendingDestinationPointRef.current = typeof startPageY === 'number' && Number.isFinite(startPageY)
        && startPageY >= 0 && startPageY <= 1 ? startPageY : null;
      if (Number(cardIdRef.current || 0) !== Number(cardId || 0)) {
        setFindStartPage(null);
      }
      const nextLanguage = createReaderLanguage(startLocale, startCustomLanguage);
      setLanguage(nextLanguage);
      document.documentElement.lang = nextLanguage.locale;
      setAppearanceMode(normalizePdfAppearanceMode(startAppearanceMode));
      setPdfFocusState(window._incPdfFocusState);
      setControlsCollapsed(typeof startControlsCollapsed === 'boolean' ? startControlsCollapsed : true);
      setCompactPanel(null);
      setShowHighlightDeleteButtons(startShowHighlightDeleteButtons !== false);
      setLinkPreviewZoom(normalizePdfLinkPreviewZoom(startLinkPreviewZoom));
      setLinkBackHistory([]);
      setHighlights(Array.isArray(window._incPdfHighlights) ? window._incPdfHighlights.slice().sort(compareHighlights) : []);
      resizeHighlightRef.current = null;
      highlightRangeCacheRef.current.clear();
      setResizingHighlightId(null);
      setHighlightColorPopover(null);
      setNativeHighlightsVisible(window._pdfNativeHighlightsVisible === true);
      window._pdfNativeHighlightsVisible = null;
      window._incPdfHighlights = null;
      setBookmarks(Array.isArray(startBookmarks) ? startBookmarks : (window._incPdfBookmarks || []));
      window._incPdfBookmarks = null;
      setFindOpen(!!startSearchQuery);
      setSearchQuery(startSearchQuery || '');
      setSearchHits(Array.isArray(startSearchHits) ? startSearchHits : []);
      setActiveSearchHitIndex(Number.isInteger(startActiveSearchHitIndex) ? startActiveSearchHitIndex : -1);
      setReadAnchor(startReadAnchor && typeof startReadAnchor === 'object' ? startReadAnchor : null);
      pendingExcerptJumpRef.current = String(startJumpExcerpt || '').trim();
      pendingHighlightScrollRef.current = String(startJumpHighlightId || '').trim();
      setActiveHighlightId(String(startJumpHighlightId || '').trim() || null);
      pendingReadAnchorScrollRef.current = !!startScrollToReadAnchor;
      pendingPageTopScrollRef.current = false;
      pendingResumeScrollRef.current = clampScrollRatio(startScrollRatio);
      pendingResumePageRef.current = Math.max(1, parseInt(startPage, 10) || 1);
      suppressScrollPersistence(700);
      setLimitStatus(startLimitStatus || DEFAULT_LIMIT_STATUS);
      pendingHighlightSelectionRef.current = null;
      setLimitNotice(null);
      if (typeof startAutoHighlightOnExtract === 'boolean') {
        applyAutoHighlightSetting(startAutoHighlightOnExtract);
      }
      applyScrollToTopOnPageChangeSetting(startScrollToTopOnPageChange);
      startViewer(cardId, filename, startPage, startZoom, startReadPage);
      const workspace = window._incWorkspaceActive;
      if (workspace?.card_id === Number(cardId)) {
        window._incWorkspacePending = workspace;
        window.incrementoPdfRestoreWorkspace?.(workspace);
      } else {
        window._incWorkspaceActive = null;
        if (window._incWorkspacePending?.card_id !== Number(cardId)) window._incWorkspacePending = null;
      }
    };

    window.incrementoPickPdfHighlightColor = finishHighlightColorPicker;
    window.incrementoPdfStart = startWithHighlights;
    window.incrementoSetPdfFocusState = setPdfFocusState;
    window.incrementoSetPdfLinkPreviewZoom = value => setLinkPreviewZoom(normalizePdfLinkPreviewZoom(value));
    window.incrementoPdfNav   = limitAwareNav;
    window.incrementoPdfZoom  = adjustZoom;
    window.incrementoPdfMarkRead = limitAwareMarkRead;
    window.incrementoPdfOpenFind = openFind;
    window.incrementoSetAutoHighlightOnExtract = (value) => {
      applyAutoHighlightSetting(value);
    };
    window.incrementoSetScrollToTopOnPageChange = (value) => {
      applyScrollToTopOnPageChangeSetting(value);
    };
    window.incrementoSetPdfAppearanceMode = (mode) => {
      setAppearanceMode(normalizePdfAppearanceMode(mode));
    };
    window.incrementoSetPdfHighlightDeleteButtons = (value) => {
      setShowHighlightDeleteButtons(value !== false);
    };

    window.incrementoReceivePageCards = (data) => {
      if (data.page === pageRef.current) {
        setPageCards(data.cards || []);
      }
    };
    window.incrementoReceivePdfReadProgress = (data) => {
      setReadAnchor(data.anchor || null);
      rawSetReadProgress(data.page || 0, data.anchor || null, false);
    };
    window.incrementoReceivePdfHighlights = (items) => {
      setHighlights(Array.isArray(items) ? items.slice().sort(compareHighlights) : []);
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
    window.incrementoReceivePdfSearchState = (state) => {
      const payload = state && typeof state === 'object' ? state : {};
      const query = String(payload.query || '');
      setSearchQuery(current => {
        if (current !== query) suppressSearchSyncRef.current = true;
        return query;
      });
      setSearchHits(Array.isArray(payload.hits) ? payload.hits : []);
      setActiveSearchHitIndex(Number.isInteger(payload.activeIndex) ? payload.activeIndex : -1);
      if (query) setFindOpen(true);
      const hit = Array.isArray(payload.hits) ? payload.hits[payload.activeIndex] : null;
      if (hit && Number(hit.page || 0) === Number(pageRef.current || 0)) {
        pendingExcerptJumpRef.current = String(hit.excerpt || hit.snippet || '');
        setSearchJumpNonce((value) => value + 1);
      }
    };

    const pending = window._incPdfPending;
    if (pending) {
      window._incPdfPending = null;
      startWithHighlights(
        pending.cardId,
        pending.filename,
        pending.page,
        pending.zoom,
        pending.scrollRatio || 0.0,
        pending.readPage || 0,
        pending.readAnchor || null,
        pending.searchQuery || '',
        pending.searchHits || [],
        pending.activeSearchHitIndex ?? -1,
        pending.jumpExcerpt || '',
        pending.jumpHighlightId || '',
        pending.scrollToReadAnchor || false,
        pending.limitStatus || DEFAULT_LIMIT_STATUS,
        pending.autoHighlightOnExtract,
        pending.scrollToTopOnPageChange,
        pending.bookmarks || [],
        pending.locale || 'en',
        pending.customLanguage || null,
        pending.appearanceMode || 'original',
        pending.showHighlightDeleteButtons,
        pending.linkPreviewZoom,
        pending.pageY,
        pending.controlsCollapsed,
      );
    }
    return () => {
      delete window.incrementoPickPdfHighlightColor;
      delete window.incrementoPdfStart;
      delete window.incrementoSetPdfFocusState;
      delete window.incrementoSetPdfLinkPreviewZoom;
      delete window.incrementoPdfNav;
      delete window.incrementoPdfZoom;
      delete window.incrementoPdfMarkRead;
      delete window.incrementoPdfOpenFind;
      delete window.incrementoSetAutoHighlightOnExtract;
      delete window.incrementoSetScrollToTopOnPageChange;
      delete window.incrementoSetPdfAppearanceMode;
      delete window.incrementoSetPdfHighlightDeleteButtons;
      delete window.incrementoReceivePageCards;
      delete window.incrementoReceivePdfHighlights;
      delete window.incrementoReceivePdfReadProgress;
      delete window.incrementoReceivePdfLimitStatus;
      delete window.incrementoReceivePdfBookmarks;
      delete window.incrementoUpdatePdfHighlightNote;
      delete window.incrementoReceivePdfSearchState;
    };
  }, [
    startViewer,
    finishHighlightColorPicker,
    limitAwareNav,
    adjustZoom,
    limitAwareMarkRead,
    pageRef,
    updateHighlightNote,
    applyAutoHighlightSetting,
    applyScrollToTopOnPageChangeSetting,
    openFind,
    suppressScrollPersistence,
    snapshotMode,
  ]);

  // Workspace snapshots contain view settings only; annotations and content
  // remain with the document. A startup pending value survives host-page loads.
  useEffect(() => {
    window.incrementoPdfWorkspaceState = () => {
      const metrics = getPdfViewportMetrics(containerRef.current);
      return {
        card_id: Number(cardIdRef.current || 0), page: pageRef.current, zoom,
        scroll: metrics && metrics.maxOffset > 0
          ? clampScrollRatio((window.scrollY - metrics.pageTop) / metrics.maxOffset) : 0,
        controls: {collapsed: controlsCollapsed, groups: {...controlVisibility},
          links: clickableLinks, appearance: appearanceMode},
      };
    };
    window.incrementoPdfRestoreWorkspace = state => {
      if (!state || state.card_id !== Number(cardIdRef.current || 0)) return;
      const controls = state.controls || {};
      if (typeof controls.collapsed === 'boolean') setControlsCollapsed(controls.collapsed);
      if (typeof controls.links === 'boolean') setClickableLinks(controls.links);
      if (['original', 'dark', 'night'].includes(controls.appearance)) setAppearanceMode(controls.appearance);
      const groups = controls.groups || {};
      setControlVisibility(current => Object.fromEntries(Object.keys(current).map(key => (
        [key, typeof groups[key] === 'boolean' ? groups[key] : current[key]]
      ))));
      setCompactPanel(null);
      window._incWorkspaceActive = state;
      window._incWorkspacePending = null;
    };
    if (window._incWorkspacePending) window.incrementoPdfRestoreWorkspace(window._incWorkspacePending);
    else if (window._incWorkspaceActive?.card_id === Number(cardIdRef.current || 0)) {
      window._incWorkspaceActive = window.incrementoPdfWorkspaceState();
    }
    return () => {
      delete window.incrementoPdfWorkspaceState;
      delete window.incrementoPdfRestoreWorkspace;
    };
  }, [appearanceMode, cardIdRef, clickableLinks, containerRef, controlsCollapsed, controlVisibility,
    pageLinksDocument.generation, pageRef, zoom]);

  // ── Request card sources for current page ─────────────────────────────────
  useEffect(() => {
    if (!pdfDocRef.current || !cardIdRef.current) return;
    setPageCards([]);
    window.pycmd('incremento_get_page_cards:' + cardIdRef.current + ':' + page);
  }, [page, pdfDocRef, cardIdRef]);

  // ── Keyboard: Ctrl/Cmd+1–4 fill field / Ctrl/Cmd/Alt+H highlight ───────────────
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
      // Ctrl/Cmd+H or Option/Alt+H — highlight current selection
      if (!e.shiftKey && (e.altKey || e.ctrlKey || e.metaKey) && e.code === 'KeyH') {
        const sel = window.getSelection();
        if (!sel || sel.isCollapsed || !sel.rangeCount) return;
        const tl = textLayerRef.current;
        if (!tl || !tl.contains(sel.getRangeAt(0).commonAncestorContainer)) return;
        e.preventDefault();
        e.stopPropagation();
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
      const formatted = selectionFormatted(selObj, tl);
      if (!formatted.text) return false;
      if (autoHighlightRef.current) makeHighlight(selObj);
      window.pycmd('incremento_fill_field:' + JSON.stringify({ idx, ...formatted }));
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
      className={readingOnly ? 'incremento-pdf-reading-only' : undefined}
      style={{
        width: '100%',
        minHeight: '100vh',
        minWidth: minViewerWidth > 0 ? `${minViewerWidth}px` : undefined,
        paddingBottom: `${visibleControlsHeight}px`,
        background: pageAppearance.background,
      }}
    >
      <style>{`
        #pdf-controls { container-type: inline-size; max-height: min(50vh, 360px); overflow-y: auto; }
        #pdf-controls div, #pdf-controls span { min-width: 0; flex-wrap: wrap; }
        #pdf-controls button, #pdf-controls select { max-width: 100%; min-height: 28px; }
        #pdf-controls .reader-control-row { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; padding: 4px 0; }
        #pdf-controls .reader-control-cluster { display: inline-flex; align-items: center; gap: 5px; flex-wrap: wrap; }
        #pdf-controls .reader-zoom { margin-left: auto; }
        #pdf-controls .reader-primary-actions { border-bottom: 1px solid #454545; padding-bottom: 8px; }
        #pdf-controls .reader-mark-read { background: #17452e; border: 1px solid #328059; color: #9ce7b7; }
        #pdf-controls .reader-status-row { justify-content: space-between; font-size: 12px; }
        #pdf-controls .reader-status-row button { background: transparent; border-color: transparent; }
        #pdf-controls .reader-progress { display: flex; flex-direction: column; gap: 4px; min-width: 140px; color: #c8c8cf; }
        #pdf-controls .reader-progress-track { display: block; height: 4px; width: 100%; background: #444; border-radius: 3px; }
        #pdf-controls .reader-progress-track > span { display: block; height: 100%; background: #6bc694; border-radius: 3px; }
        #pdf-controls .reader-options { padding: 10px 0; }
        #pdf-controls .reader-expanded-rows { display: flex; flex-direction: column; gap: 6px; }
        #pdf-controls .reader-expanded-heading { color: #c7c7cd; font-size: 11px; font-weight: 600; line-height: 14px; }
        #pdf-controls .reader-expanded-group button, #pdf-controls .reader-expanded-group select { box-sizing: border-box; min-height: 28px; }
        #pdf-controls .reader-expanded-group button { height: 30px; font-size: 12px; }
        #pdf-controls .reader-expanded-body { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 14px; }
        @container (max-width: 1050px) {
          #pdf-controls .reader-expanded-group { grid-template-columns: minmax(0, 1fr) !important; gap: 8px !important; }
        }
        #pdf-controls .reader-expanded-group button[aria-pressed='true'] { border-color: #70a9dc; }


        .incremento-pdf-reading-only #pdf-controls div,
        .incremento-pdf-reading-only #pdf-controls span { min-width: 0; flex-wrap: wrap; }
        #pdf-controls button:focus-visible,
        #pdf-controls input:focus-visible,
        #pdf-controls select:focus-visible,
        #pdf-controls [tabindex]:focus-visible,
        .incremento-pdf-highlight-controls-toggle:focus-visible {
          outline: 3px solid #60a5fa !important;
          outline-offset: 2px;
        }
        #pdf-controls select {
          color-scheme: dark;
        }
        #pdf-controls select option {
          color: #f4f4f5;
          background-color: #27272a;
        }
        @media (prefers-reduced-motion: reduce) {
          #pdf-controls *,
          #pdf-controls *::before,
          #pdf-controls *::after {
            animation-duration: 0.01ms !important;
            animation-iteration-count: 1 !important;
            scroll-behavior: auto !important;
            transition-duration: 0.01ms !important;
          }
        }
      `}</style>

      {/* Controls */}
      <div
        id="pdf-controls"
        ref={controlsRef}
        role="toolbar"
        aria-label={tr("reader_pdf_controls")}
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

        {controlsCollapsed && (
          <div className="reader-essential-controls">
            <div className="reader-control-row reader-navigation">
              <button type="button" disabled={!contentsReady} onClick={openContents}
                title={tr('reader_contents_hint')} aria-haspopup="dialog">{tr('reader_contents')}</button>
              <button type="button" onClick={openFind}>{tr('reader_search')}</button>
              <span className="reader-control-cluster">
                <button aria-label={tr('reader_previous_pdf_page')} onClick={() => limitAwareNav(-1)}>← {tr('reader_prev_short')}</button>
                {pageJumpEditing ? (
                  <label className="reader-control-cluster">{tr('reader_pdf_page')}
                    <input ref={pageJumpInputRef} aria-label={tr('reader_pdf_page_number')} type="number"
                      min="1" max={totalPages || undefined} value={pageJumpValue}
                      onChange={event => setPageJumpValue(event.target.value)} onBlur={commitPageJump}
                      onKeyDown={event => {
                        if (event.key === 'Enter') { event.preventDefault(); commitPageJump(); }
                        else if (event.key === 'Escape') { event.preventDefault(); cancelPageJump(); }
                      }} style={{width: 64, minWidth: 0}} />
                    <span>/ {totalPages}</span>
                  </label>
                ) : <button type="button" onClick={openPageJump} title={pageLocationTitle}>{pageLocationText}</button>}
                <button aria-label={tr('reader_next_pdf_page')} onClick={() => limitAwareNav(1)}>{tr('reader_next_short')} →</button>
              </span>
              <span className="reader-control-cluster reader-zoom">
                <button aria-label={tr('reader_zoom_out')} onClick={() => adjustZoom(-1)}>−</button>
                <span>{Math.round(zoom * 100)}%</span>
                <button aria-label={tr('reader_zoom_in')} onClick={() => adjustZoom(1)}>+</button>
              </span>
            </div>
            <div className="reader-control-row reader-primary-actions">
              <button type="button" className="reader-mark-read" aria-label={tr('reader_read_to_here')}
                aria-pressed={readPage > 0 && page <= readPage} onClick={limitAwareMarkRead}>✓ {tr('reader_read_to_here')}</button>
              <button type="button" aria-label={tr('reader_extract')} onMouseDown={event => event.preventDefault()}
                onClick={() => window.incrementoHandleExtractShortcut?.(0)}>{tr('reader_extract')}</button>
              <button type="button" aria-label={tr('reader_bookmark')} title={tr('reader_bookmark_current')} onClick={addBookmark}>☆ {tr('reader_bookmark')}</button>
              <button type="button" aria-expanded={compactPanel === 'annotation'} aria-controls="pdf-secondary-controls"
                onClick={() => setCompactPanel(value => value === 'annotation' ? null : 'annotation')}>{tr('reader_annotate')}</button>
              {!readingOnly && <>
                <button type="button" aria-label={tr('reader_review_all')} title={tr('reader_review_all_tooltip')}
                  onClick={() => window.pycmd(`incremento_pdf_review_all:${cardIdRef.current}:${pageRef.current}`)}>{tr('reader_review_all')}</button>
                <button type="button" aria-label={tr('reader_review_cards')} aria-expanded={compactPanel === 'review'}
                  aria-controls="pdf-secondary-controls" onClick={() => setCompactPanel(value => value === 'review' ? null : 'review')}>▾</button>
              </>}
              <button type="button" aria-expanded={compactPanel === 'more'} aria-controls="pdf-secondary-controls"
                onClick={() => setCompactPanel(value => value === 'more' ? null : 'more')}>{tr('reader_more')}</button>
              <button type="button" onClick={() => applyControlsCollapsed(false)} aria-expanded="false">{tr('reader_show_controls')}</button>
            </div>
            <div className="reader-control-row reader-status-row">
              <span className="reader-control-cluster">
                <button type="button" aria-pressed={clickableLinks} onClick={() => setClickableLinks(value => !value)}
                  title={clickableLinks ? tr('reader_links_disable') : tr('reader_links_enable')}>
                  {tr('reader_links_state', {state: clickableLinks ? tr('reader_on') : tr('reader_off')})}
                </button>
                <button type="button" disabled={!linkBackHistory.length} onClick={jumpBackFromPdfLink}
                  title={linkBackHistory.length ? tr('reader_jump_back_page', {page: linkBackHistory.at(-1).page}) : tr('reader_jump_back_hint')}>
                  ↩ {tr('reader_jump_back')}
                </button>
                <PdfPageLinks linksState={pageLinksState} tr={tr} />
              </span>
              <span className="reader-progress" title={tr('reader_read_progress_pages', {read: readPage, total: totalPages})}>
                <span>{tr('reader_marked_read', {percent: progressPct})}</span>
                <span className="reader-progress-track" role="progressbar" aria-label={tr('reader_read_progress')}
                  aria-valuemin="0" aria-valuemax="100" aria-valuenow={progressPct}><span style={{width: `${progressPct}%`}} /></span>
              </span>
            </div>
          </div>
        )}
        {findOpen && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
            <span style={{ color: '#d4d4d8', fontWeight: 600 }}>{tr('reader_find')}</span>
            <input
              ref={findInputRef}
              type="text"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder={tr("reader_search_pdf")}
              style={{
                width: 260,
                height: 32,
                padding: '0 10px',
                borderRadius: 8,
                border: '1px solid rgba(180,180,180,0.35)',
                background: 'rgba(255,255,255,0.08)',
                color: '#f5f5f5',
              }}
            />
            <span
              role="status"
              aria-live="polite"
              style={{ minWidth: 64, textAlign: 'center', color: '#a1a1aa', fontSize: 12 }}
            >
              {searchQuery ? (searchHits.length ? tr('reader_search_position', { current: Math.max(0, activeSearchHitIndex + 1), total: searchHits.length }) : tr('reader_zero_results')) : ''}
            </span>
            <button
              type="button"
              disabled={!searchHits.length}
              onClick={() => window.pycmd('incremento_pdf_find_nav:' + JSON.stringify({ direction: -1 }))}
            >
              {tr('reader_prev_short')}
            </button>
            <button
              type="button"
              disabled={!searchHits.length}
              onClick={() => window.pycmd('incremento_pdf_find_nav:' + JSON.stringify({ direction: 1 }))}
            >
              {tr('reader_next_short')}
            </button>
            {findStartPage !== null && (
              <button
                type="button"
                disabled={Number(page) === Number(findStartPage)}
                onClick={returnToFindStartPage}
              >
                {tr('reader_return_to_search_page', { page: findStartPage })}
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                setFindOpen(false);
                setSearchQuery('');
                setFindStartPage(null);
              }}
            >
              {tr('reader_close')}
            </button>
            <button
              type="button"
              onClick={() => window.pycmd('incremento_pdf_open_find_dialog')}
            >
              {tr('reader_all')}
            </button>
          </div>
        )}

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
              title={tr("reader_daily_limit")}
            >
              <span>{tr('reader_today_pages', { used: limitUsed, total: limitTotal })}</span>
              <span style={{ opacity: 0.72 }}>•</span>
              <span>{tr('reader_remaining', { count: Math.max(0, limitRemaining) })}</span>
              <span style={{ opacity: 0.72 }}>•</span>
              <span>{tr(`reader_limit_${limitStatus?.enforcement_mode || 'warning'}`)}</span>
              {overrideEnabled && (
                <>
                  <span style={{ opacity: 0.72 }}>•</span>
                  <span style={{ color: 'rgb(96,165,250)' }}>{tr('reader_override_active')}</span>
                </>
              )}
            </span>
            {allowedMaxPage != null && (
              <span style={{ fontSize: 11, color: '#c8c8c8' }}>
                {tr('reader_stop_point', { page: allowedMaxPage })}
              </span>
            )}
          </div>
        )}

        {limitNotice && (
          <div
            role="status"
            aria-live="polite"
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
                  {tr('reader_override_today')}
                </button>
              )}
              <button onClick={clearLimitNotice}>
                {tr('reader_dismiss')}
              </button>
            </span>
          </div>
        )}

        {(!controlsCollapsed || compactPanel) && (
          <div id="pdf-secondary-controls">
            {controlsCollapsed && compactPanel === 'more' && <div className="reader-control-row reader-options">
              <select aria-label={tr("reader_pdf_appearance")} value={appearanceMode}
                onChange={(event) => applyAppearanceMode(event.target.value)} style={PDF_APPEARANCE_SELECT_STYLE}>
                {PDF_APPEARANCE_MODES.map(mode => <option key={mode} value={mode} style={PDF_APPEARANCE_OPTION_STYLE}>{tr(`reader_pdf_appearance_${mode}`)}</option>)}
              </select>
              {focusButton}
              {referenceControls?.({ready: !error && renderInfo.cardId === cardIdRef.current && renderInfo.page === page && renderInfo.textReady === true && !busyRef.current})}
              <button type="button" onClick={() => setShowControlChooser(true)}>{tr('reader_customize_controls')}</button>
              <button type="button" onClick={limitAwareMarkReadAnchor} title={tr('reader_place_exact_marker')}>{tr('reader_exact_read_marker')}</button>
              {!readingOnly && <>
                <button type="button" onClick={() => window.pycmd(`incremento_pdf_limit_settings:${cardIdRef.current}`)}>{tr('reader_reading_limit')}</button>
                <button type="button" onClick={() => window.pycmd(`incremento_pdf_regenerate_cover:${cardIdRef.current}`)}>{tr('reader_regenerate_cover')}</button>
              </>}
            </div>}
            {!controlsCollapsed && <>
            <div style={{ display: 'flex', justifyContent: 'flex-end', flexWrap: 'wrap', gap: 6, marginBottom: 4 }}>
              {focusButton}
              {referenceControls?.({ready: !error && renderInfo.cardId === cardIdRef.current && renderInfo.page === page && renderInfo.textReady === true && !busyRef.current})}
              <button
                type="button"
                onClick={() => setShowControlChooser(true)}
                title={tr("reader_choose_controls")}
                style={{ padding: '2px 9px', fontSize: 11 }}
              >
                {tr('reader_customize_controls')}
              </button>
              <button
                type="button"
                onClick={() => applyControlsCollapsed(true)}
                aria-expanded="true"
                title={tr("reader_minimize_controls")}
                style={{
                  border: '1px solid rgba(180,180,180,0.35)',
                  background: 'rgba(255,255,255,0.04)',
                  color: 'rgba(235,235,235,0.82)',
                  padding: '2px 9px',
                  fontSize: 11,
                }}
              >
                {tr('reader_minimize_controls_label')}
              </button>
            </div>

        {/* ── Row 1: Reader status and navigation ── */}
        <div className="reader-expanded-rows" style={{marginBottom: 6}}>
          {controlVisibility.navigation && <div className="reader-expanded-group" role="group" aria-label={tr('reader_navigation')} style={TOOLBAR_GROUP_STYLE}>
            <span className="reader-expanded-heading">{tr('reader_navigation')}</span>
            <div className="reader-expanded-body">
            <div style={TOOLBAR_STACK_STYLE}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                <button type="button" disabled={!contentsReady} onClick={openContents}
                  title={tr('reader_contents_hint')} aria-haspopup="dialog">
                  {tr('reader_contents')}
                </button>
                <button type="button" onClick={openFind}>{tr('reader_search')}</button>
                <button
                  aria-label={tr("reader_previous_pdf_page")}
                  onClick={() => limitAwareNav(-1)}
                >
                  &#8592; {tr('reader_prev_short')}
                </button>
                {pageJumpEditing ? (
                  <span style={{ minWidth: 170, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6, fontSize: 15, fontWeight: 700 }}>
                    <span>{tr('reader_pdf_page')}</span>
                    <input
                      ref={pageJumpInputRef}
                      aria-label={tr("reader_pdf_page_number")}
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
                    title={totalPages > 0 ? pageLocationTitle : undefined}
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
                    {pageLocationText}
                  </button>
                )}
                <button
                  aria-label={tr("reader_next_pdf_page")}
                  onClick={() => limitAwareNav(1)}
                >
                  {tr('reader_next_short')} &#8594;
                </button>
              </span>
            </div>
            <span style={TOOLBAR_SEPARATOR_STYLE} />
            <div style={TOOLBAR_STACK_STYLE}>
              <span style={TOOLBAR_LABEL_STYLE}>{tr('reader_zoom')}</span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                <button aria-label={tr("reader_zoom_out")} onClick={() => adjustZoom(-1)}>
                  &#8722;
                </button>
                <span style={{ minWidth: 54, textAlign: 'center', fontSize: 15, fontWeight: 700 }}>
                  {Math.round(zoom * 100)}%
                </span>
                <button aria-label={tr("reader_zoom_in")} onClick={() => adjustZoom(1)}>
                  &#43;
                </button>
              </span>
            </div>
            <span style={TOOLBAR_SEPARATOR_STYLE} />
            <div style={TOOLBAR_STACK_STYLE}>
              <label htmlFor="pdf-appearance-mode" style={TOOLBAR_LABEL_STYLE}>
                {tr('reader_pdf_appearance')}
              </label>
              <select
                id="pdf-appearance-mode"
                aria-label={tr("reader_pdf_appearance")}
                title={tr("reader_pdf_appearance_hint")}
                value={appearanceMode}
                onChange={(event) => applyAppearanceMode(event.target.value)}
                style={{
                  ...PDF_APPEARANCE_SELECT_STYLE,
                  height: 32,
                  minWidth: 104,
                }}
              >
                {PDF_APPEARANCE_MODES.map((mode) => (
                  <option key={mode} value={mode} style={PDF_APPEARANCE_OPTION_STYLE}>
                    {tr(`reader_pdf_appearance_${mode}`)}
                  </option>
                ))}
              </select>
            </div>
            </div>
          </div>}

          {controlVisibility.reading && <div className="reader-expanded-group" role="group" aria-label={tr('reader_reading')} style={TOOLBAR_GROUP_STYLE}>
            <span className="reader-expanded-heading">{tr('reader_reading')}</span>
            <div className="reader-expanded-body">
            <div style={TOOLBAR_STACK_STYLE}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <button
                  title={readPage > 0 ? tr("reader_read_to_page", { page: readPage }) : tr("reader_mark_read_to_here")}
                  style={{
                    background:  readPage > 0 && page <= readPage ? 'rgba(34,197,94,0.3)' : 'transparent',
                    border:      '1px solid rgba(34,197,94,0.6)', borderRadius: 8,
                    color:       readPage > 0 && page <= readPage ? '#9ce7b7' : 'inherit',
                    cursor:      'pointer', padding: '4px 10px', fontSize: 12,
                    fontWeight:  readPage > 0 && page <= readPage ? 'bold' : 'normal',
                  }}
                  onClick={limitAwareMarkRead}
                >
                  ✓ {tr('reader_read_to_here')}
                </button>
                <button
                  title={showReadMarker ? tr("reader_move_exact_marker") : tr("reader_place_exact_marker")}
                  aria-label={tr("reader_set_exact_marker")}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    minWidth: 34,
                    minHeight: 30,
                    padding: '4px 10px',
                    fontSize: 12,
                    fontWeight: 400,
                    borderRadius: 8,
                    cursor: 'pointer',
                    background: showReadMarker ? 'rgba(14,165,233,0.22)' : 'rgba(255,255,255,0.03)',
                    color: showReadMarker ? 'rgb(125,211,252)' : 'inherit',
                    border: showReadMarker ? '1px solid rgba(14,165,233,0.75)' : '1px solid rgba(180,180,180,0.32)',
                    boxShadow: showReadMarker ? '0 0 0 1px rgba(14,165,233,0.12) inset' : 'none',
                  }}
                  onClick={limitAwareMarkReadAnchor}
                >
                  {tr('reader_exact_read_marker')}
                </button>
                <button
                  type="button"
                  aria-pressed={clickableLinks}
                  title={clickableLinks ? tr("reader_links_disable") : tr("reader_links_enable")}
                  onClick={() => setClickableLinks(value => !value)}
                  style={{
                    background: clickableLinks ? 'rgba(59,130,246,0.22)' : 'rgba(255,255,255,0.03)',
                    border: clickableLinks ? '1px solid rgba(96,165,250,0.78)' : '1px solid rgba(180,180,180,0.32)',
                    borderRadius: 8,
                    color: clickableLinks ? 'rgb(147,197,253)' : 'inherit',
                    cursor: 'pointer',
                    padding: '4px 10px',
                    fontSize: 12,
                    fontWeight: clickableLinks ? 700 : 400,
                  }}
                >
                  {tr('reader_links_state', { state: clickableLinks ? tr('reader_on') : tr('reader_off') })}
                </button>
                <button
                  type="button"
                  disabled={linkBackHistory.length === 0}
                  onClick={jumpBackFromPdfLink}
                  title={linkBackHistory.length > 0 ? tr("reader_jump_back_page", { page: linkBackHistory.at(-1).page }) : tr("reader_jump_back_hint")}
                  style={{
                    background: 'rgba(255,255,255,0.03)',
                    border: '1px solid rgba(180,180,180,0.32)',
                    borderRadius: 8,
                    color: 'inherit',
                    cursor: linkBackHistory.length > 0 ? 'pointer' : 'default',
                    opacity: linkBackHistory.length > 0 ? 1 : 0.48,
                    padding: '4px 10px',
                    fontSize: 12,
                  }}
                >
                  ↩ {tr('reader_jump_back')}
                </button>
                <PdfPageLinks linksState={pageLinksState} tr={tr} />
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
                    {tr('reader_read_range', { page: readPage })}
                  </span>
                )}
              </span>
            </div>
            <span style={TOOLBAR_SEPARATOR_STYLE} />
            <span
              title={totalPages > 0 ? tr("reader_read_progress_pages", { read: readPage, total: totalPages }) : tr("reader_read_progress")}
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
          </div>}
        </div>

            </>}
        {/* ── Row 4: Tools + card management ── */}
        <div className="reader-expanded-rows">
          {hasPdfCard && (controlsCollapsed ? compactPanel === 'annotation' : controlVisibility.annotation) && (
            <div className="reader-expanded-group" role="group" aria-label={tr('reader_annotation_capture')} style={TOOLBAR_GROUP_STYLE}>
              <span className="reader-expanded-heading">{tr('reader_annotation_capture')}</span>
            <div className="reader-expanded-body">
              <div style={TOOLBAR_STACK_STYLE}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '2px 4px' }}>
                    {Object.keys(HL_COLORS).map(c => (
                      <button
                        key={c}
                        aria-label={tr('reader_use_highlight_color', { color: tr(`reader_color_${c}`) })}
                        aria-pressed={hlColor === c}
                        title={tr('reader_highlight_color', { color: tr(`reader_color_${c}`) })}
                        onMouseDown={(e) => {
                          e.preventDefault();
                          pickHighlightColor(c, true);
                        }}
                        onClick={() => pickHighlightColor(c, false)}
                        style={{
                          background:  HL_SOLID[c],
                          border:      hlColor === c ? '2px solid white' : '2px solid transparent',
                          width: 22, height: 22, minHeight: 22,
                          borderRadius: 6, padding: 0, cursor: 'pointer',
                          boxShadow: hlColor === c ? '0 0 0 2px rgba(255,255,255,0.12)' : 'none',
                        }}
                      />
                    ))}
                  </span>
                  <button
                    title={`${tr('reader_choose_annotation_color')} (${highlightSolidColor(hlColor)})`}
                    onMouseDown={e => e.preventDefault()}
                    onClick={() => openHighlightColorPicker()}
                    style={{ background: 'transparent', border: '1px solid rgba(138,138,138,0.4)',
                      color: '#ddd', borderRadius: 6, padding: '5px 8px', cursor: 'pointer' }}
                  >
                    <span aria-hidden="true" style={{ display: 'inline-block', width: 12, height: 12,
                      background: highlightSolidColor(hlColor), borderRadius: 3, marginRight: 6 }} />
                    {tr('reader_more_colors')}
                  </button>
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
                    {tr('reader_highlight_when_extracting')}
                  </label>
                </span>
              </div>
              <span style={TOOLBAR_SEPARATOR_STYLE} />
              <div style={TOOLBAR_STACK_STYLE}>
                <span style={TOOLBAR_LABEL_STYLE}>{tr('reader_capture')}</span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <button type="button" onMouseDown={event => event.preventDefault()} onClick={() => window.incrementoHandleExtractShortcut?.(0)}>{tr('reader_extract')}</button>
                  <PdfSnapshotButton mode={snapshotMode} tr={tr} onToggle={() => {
                    paintPdfSnapshotPreview(snapPreviewRef.current, null);
                    snapStartRef.current = null;
                  }} />
                  <button
                    title={tr("reader_show_highlights")}
                    style={{
                      background: showHighlightsPanel ? 'rgba(56,189,248,0.2)' : 'transparent',
                      border: showHighlightsPanel ? '1px solid rgba(56,189,248,0.55)' : '1px solid #555',
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
                    &#x1F4D1; {tr('reader_highlights_count', { count: highlights.length })}
                  </button>
                  <button
                    title={tr("reader_bookmark_current")}
                    onClick={addBookmark}
                  >
                    &#9733; {tr('reader_bookmark')}
                  </button>
                  <button
                    title={tr("reader_show_bookmarks")}
                    style={{
                      background: showBookmarksPanel ? 'rgba(250,204,21,0.18)' : 'transparent',
                      border: showBookmarksPanel ? '1px solid rgba(250,204,21,0.55)' : '1px solid #555',
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
                    {tr('reader_bookmarks_count', { count: bookmarks.length })}
                  </button>
                </span>
              </div>
            </div>
            </div>
          )}

          {!readingOnly && (controlsCollapsed ? compactPanel === 'review' : controlVisibility.review) && <div className="reader-expanded-group" role="group" aria-label={tr('reader_review_cards')} style={TOOLBAR_GROUP_STYLE}>
            <span className="reader-expanded-heading">{tr('reader_review_cards')}</span>
            <div className="reader-expanded-body">
            {hasPdfCard && (
              <>
                <div style={TOOLBAR_STACK_STYLE}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <button onClick={() => window.pycmd(`incremento_pdf_due_review:${cardIdRef.current}:${pageRef.current}`)}>
                      &#x1F9E0; {tr('reader_review_due')}
                    </button>
                    <button
                      title={tr("reader_review_all_tooltip")}
                      onClick={() => window.pycmd(`incremento_pdf_review_all:${cardIdRef.current}:${pageRef.current}`)}
                    >
                      &#x25B6; {tr('reader_review_all')}
                    </button>
                    <button onClick={() => window.pycmd(`incremento_pdf_limit_settings:${cardIdRef.current}`)}>
                      &#x1F4D6; {tr('reader_reading_limit')}
                    </button>
                    <button onClick={() => window.pycmd(`incremento_pdf_regenerate_cover:${cardIdRef.current}`)}>
                      {tr('reader_regenerate_cover')}
                    </button>
                  </span>
                </div>
                <span style={TOOLBAR_SEPARATOR_STYLE} />
                <div style={TOOLBAR_STACK_STYLE}>
                  <span style={TOOLBAR_LABEL_STYLE}>{tr('reader_cards')}</span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <button
                      title={tr("reader_open_all_cards")}
                      onClick={() => window.pycmd('incremento_open_all_pdf_cards:' + cardIdRef.current)}
                    >
                      {tr('reader_open_all_in_browser')}
                    </button>
                    {pageCards.length > 0 && (
                      <button
                        title={plural('reader_page_cards_tooltip', pageCards.length)}
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
                        &#x1F4C4; {tr('reader_page_cards_count', { count: pageCards.length })}
                      </button>
                    )}
                    <button onClick={() => window.pycmd('incremento_open_add_card')}>
                      &#43; {tr('reader_add_card')}
                    </button>
                  </span>
                </div>
                <span style={TOOLBAR_SEPARATOR_STYLE} />
                <div style={TOOLBAR_STACK_STYLE}>
                  <span style={TOOLBAR_LABEL_STYLE}>{tr('reader_status')}</span>
                  <button
                    title={tr("reader_finished_tooltip")}
                    style={{
                      background:  'transparent',
                      border:      '1px solid rgba(220,50,50,0.45)', borderRadius: 8,
                      color:       'rgba(220,70,70,0.9)', cursor: 'pointer',
                      padding:     '4px 10px', fontSize: 12,
                    }}
                    onClick={() => {
                      if (window.confirm(tr("reader_finished_confirm"))) {
                        window.pycmd('incremento_pdf_finished:' + cardIdRef.current);
                      }
                    }}
                  >
                    ✓ {tr('reader_finished_reading')}
                  </button>
                </div>
              </>
            )}
            {!hasPdfCard && (
              <div style={TOOLBAR_STACK_STYLE}>
                <span style={TOOLBAR_LABEL_STYLE}>{tr('reader_cards')}</span>
                <button onClick={() => window.pycmd('incremento_open_add_card')}>
                  &#43; {tr('reader_add_card')}
                </button>
              </div>
            )}
            </div>
          </div>}
        </div>

          </div>
        )}

      </div>

      {showControlChooser && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={tr("reader_customize_pdf_controls")}
          onClick={() => setShowControlChooser(false)}
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 100,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 20,
            background: 'rgba(0,0,0,0.48)',
          }}
        >
          <div
            onClick={(event) => event.stopPropagation()}
            style={{
              width: 'min(380px, calc(100vw - 40px))',
              padding: 18,
              borderRadius: 14,
              background: 'linear-gradient(180deg, rgba(48,48,48,0.99), rgba(27,27,27,0.99))',
              border: '1px solid rgba(170,170,170,0.32)',
              boxShadow: '0 18px 50px rgba(0,0,0,0.5)',
              color: '#f4f4f5',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 14 }}>
              <div>
                <div style={{ fontSize: 16, fontWeight: 700 }}> {tr("reader_customize_controls")}</div>
                <div style={{ marginTop: 4, fontSize: 12, color: 'rgba(220,220,220,0.68)' }}>
                  {tr('reader_customize_intro')}
                </div>
              </div>
              <button type="button" onClick={() => setShowControlChooser(false)} aria-label={tr("reader_close")}>×</button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {CONTROL_GROUPS.filter(([key]) => pdfReaderGroups(readingOnly).includes(key)).map(([key, labelId]) => (
                <label
                  key={key}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '10px 12px',
                    borderRadius: 9,
                    background: 'rgba(255,255,255,0.05)',
                    border: '1px solid rgba(255,255,255,0.09)',
                    cursor: 'pointer',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={!!controlVisibility[key]}
                    onChange={(event) => setControlVisibility((current) => ({
                      ...current,
                      [key]: event.target.checked,
                    }))}
                  />
                  <span>{tr(labelId)}</span>
                </label>
              ))}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
              <button type="button" onClick={() => setControlVisibility(DEFAULT_CONTROL_VISIBILITY)}>
                {tr('reader_show_all')}
              </button>
              <button type="button" onClick={() => setShowControlChooser(false)} style={{ fontWeight: 700 }}>
                {tr('reader_done')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Bookmarks panel */}
      {hasPdfCard && (controlsCollapsed || controlVisibility.annotation) && showBookmarksPanel && (
        <div
          style={{
            position: 'fixed',
            top: 8,
            right: 12,
            width: 'min(420px, calc(100vw - 24px))',
            maxHeight: 'calc(100vh - var(--pdf-controls-height, 58px) - 24px)',
            boxSizing: 'border-box',
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
            <strong style={{ fontSize: 13 }}> {tr("reader_pdf_bookmarks")}</strong>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <button onClick={addBookmark} style={{ fontSize: 12, padding: '1px 8px' }}>
                {tr('reader_add_current_page')}
              </button>
              <button onClick={() => setShowBookmarksPanel(false)} style={{ fontSize: 12, padding: '1px 8px' }}>
                {tr('reader_close')}
              </button>
            </span>
          </div>
          {bookmarks.length === 0 ? (
            <div style={{ fontSize: 12, opacity: 0.75 }}> {tr("reader_no_bookmarks")}</div>
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
                      {bookmark.label || tr('reader_page_number', { page: bookmark?.location?.page || 1 })}
                    </span>
                    <span style={{ display: 'inline-flex', gap: 6, flexShrink: 0 }}>
                      <button
                        onClick={() => {
                          jumpToBookmark(bookmark);
                          setShowBookmarksPanel(false);
                        }}
                        style={{ fontSize: 11, padding: '1px 7px' }}
                      >
                        {tr('reader_jump')}
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
                        {tr('reader_delete')}
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
      {hasPdfCard && (controlsCollapsed || controlVisibility.annotation) && showHighlightsPanel && (
        <div
          style={{
            position: 'fixed',
            top: 8,
            right: 12,
            width: 'min(520px, calc(100vw - 24px))',
            maxHeight: 'calc(100vh - var(--pdf-controls-height, 58px) - 24px)',
            boxSizing: 'border-box',
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
            <strong style={{ fontSize: 13 }}>{tr('reader_pdf_highlights')}</strong>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              <button
                onClick={() => window.pycmd?.('incremento_pdf_annotations')}
                style={{ fontSize: 12, padding: '1px 8px' }}
              >
                {tr('reader_pdf_sync_title')}
              </button>
              <button
                onClick={() => moveHighlightCursor(-1)}
                disabled={sortedHighlights.length === 0}
                style={{ fontSize: 12, padding: '1px 8px' }}
              >
                {tr('reader_previous_highlight')}
              </button>
              <button
                onClick={() => moveHighlightCursor(1)}
                disabled={sortedHighlights.length === 0}
                style={{ fontSize: 12, padding: '1px 8px' }}
              >
                {tr('reader_next_highlight')}
              </button>
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
                {tr('reader_whole_pdf')}
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
                {tr('reader_this_page')}
              </button>
              {!readingOnly && <button
                onClick={() => window.pycmd('incremento_pdf_hl_bulk_cards')}
                disabled={missingCardHighlightCount === 0}
                style={{
                  border: '1px solid rgba(59,130,246,0.55)',
                  borderRadius: 4,
                  background: missingCardHighlightCount > 0 ? 'rgba(59,130,246,0.2)' : 'transparent',
                  color: missingCardHighlightCount > 0 ? 'rgb(96,165,250)' : 'rgba(229,231,235,0.45)',
                  cursor: missingCardHighlightCount > 0 ? 'pointer' : 'default',
                  fontSize: 12,
                  padding: '1px 8px',
                }}
                title={missingCardHighlightCount > 0
                  ? plural('reader_create_missing_tooltip', missingCardHighlightCount)
                  : tr('reader_no_unlinked_highlights')}
              >
                {tr('reader_create_missing_cards', { count: missingCardHighlightCount })}
              </button>}
              <button
                onClick={() => setHighlightsNotesOnly((value) => !value)}
                style={{
                  border: '1px solid rgba(59,130,246,0.55)',
                  borderRadius: 4,
                  background: highlightsNotesOnly ? 'rgba(59,130,246,0.2)' : 'transparent',
                  color: highlightsNotesOnly ? 'rgb(96,165,250)' : 'inherit',
                  cursor: 'pointer',
                  fontSize: 12,
                  padding: '1px 8px',
                }}
              >
                {tr('reader_notes_only')}
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
                {tr('reader_close')}
              </button>
            </span>
          </div>

          <button
            type="button"
            className="incremento-pdf-highlight-controls-toggle"
            title={tr('reader_highlight_controls_hint')}
            onClick={() => {
              setShowHighlightControls(value => !value);
              deactivateHighlightResize();
              setHighlightColorPopover(null);
              hideHighlightNote();
              setFocusedHighlightId(null);
              setShowHighlightsPanel(false);
            }}
            style={{ fontSize: 12, padding: '4px 8px', marginBottom: 8 }}
          >
            {tr(showHighlightControls ? 'reader_hide_highlight_controls' : 'reader_show_highlight_controls')}
          </button>

          {highlightsForPanel.length > 50 && <nav style={{display: 'flex', gap: 12, marginBottom: 8}}>
            <button type="button" disabled={highlightPanelPage.start === 0}
              onClick={() => setHighlightPanelOffset(highlightPanelPage.previous)}>{tr('reader_previous_page')}</button>
            <span role="status" aria-live="polite">{highlightPanelPage.start + 1}–{highlightPanelPage.end} / {highlightsForPanel.length}</span>
            <button type="button" disabled={highlightPanelPage.end === highlightsForPanel.length}
              onClick={() => setHighlightPanelOffset(highlightPanelPage.next)}>{tr('reader_next_page')}</button>
          </nav>}
          {highlightsForPanel.length === 0 ? (
            <div style={{ fontSize: 12, opacity: 0.75 }}>
              {highlightsNotesOnly
                ? (highlightsScope === 'page' ? tr('reader_no_highlight_notes_page') : tr('reader_no_highlight_notes'))
                : tr('reader_no_highlights')}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {highlightsForPanel.slice(highlightPanelPage.start, highlightPanelPage.end).map((hl) => {
                const note = String(hl.note || '').trim();
                const excerpt = String(hl.text || tr('reader_no_text')).trim();
                const linkedNoteId = Number(hl.linked_note_id || 0);
                const hasLinkedCard = Number.isInteger(linkedNoteId) && linkedNoteId > 0;
                const isActive = String(hl.id || '') === String(activeHighlightId || '');
                return (
                  <button
                    key={hl.id}
                    onClick={() => jumpToHighlight(hl, { closePanel: true })}
                    style={{
                      textAlign: 'left',
                      border: isActive ? '1px solid rgba(96,165,250,0.75)' : '1px solid rgba(90,90,90,0.55)',
                      borderRadius: 6,
                      background: isActive ? 'rgba(30,58,138,0.32)' : 'rgba(35,35,35,0.75)',
                      color: 'inherit',
                      cursor: 'pointer',
                      padding: '8px 10px',
                    }}
                    title={tr('reader_go_to_page', { page: hl.page || 1 })}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 3 }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, opacity: 0.9 }}>
                        <span
                          style={{
                            width: 10,
                            height: 10,
                            borderRadius: 999,
                            background: highlightSolidColor(hl.color),
                            border: '1px solid rgba(255,255,255,0.35)',
                            display: 'inline-block',
                            flexShrink: 0,
                          }}
                        />
                        <span>{tr('reader_page_number', { page: hl.page || 1 })}</span>
                      </span>
                      {!readingOnly && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginLeft: 'auto', fontSize: 11 }}>
                        <span
                          style={{
                            color: hasLinkedCard ? 'rgb(147,197,253)' : 'rgba(229,231,235,0.72)',
                            fontWeight: 700,
                          }}
                        >
                          {hasLinkedCard ? tr('reader_preview_card') : tr('reader_create_card')}
                        </span>
                      </span>}
                    </div>
                    {hl.color !== 'snapshot' && (
                      <button
                        type="button"
                        title={tr('reader_choose_annotation_color')}
                        aria-label={tr('reader_choose_annotation_color')}
                        onClick={e => { e.stopPropagation(); openHighlightColorPicker(hl); }}
                      >
                        {tr('reader_choose_annotation_color')}
                      </button>
                    )}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 6 }}>
                      {!readingOnly && <button
                        title={hasLinkedCard ? tr('reader_preview_linked_card') : tr('reader_prefill_card')}
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          if (hasLinkedCard) {
                            window.pycmd(`incremento_open_card:${linkedNoteId}`);
                            return;
                          }
                          window.pycmd('incremento_pdf_hl_card:' + JSON.stringify({ id: hl.id }));
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
                        {hasLinkedCard ? tr('reader_preview_card') : tr('reader_create_card')}
                      </button>}
                      <button
                        title={note ? tr('reader_edit_note_tooltip') : tr('reader_add_note_tooltip')}
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          editHighlightNote(hl.id);
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
                        {note ? tr('reader_edit_note') : tr('reader_add_note')}
                      </button>
                      <button
                        title={tr('reader_delete_highlight')}
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
                        {tr('reader_delete')}
                      </button>
                    </div>
                    {note && highlightsNotesOnly ? (
                      <>
                        <div style={{ fontSize: 12, lineHeight: 1.35, color: 'rgb(191,219,254)' }}>
                          {note}
                        </div>
                        <div style={{ fontSize: 11, lineHeight: 1.35, color: 'rgba(229,231,235,0.72)', marginTop: 6 }}>
                          {tr('reader_highlight_excerpt', { excerpt })}
                        </div>
                      </>
                    ) : (
                      <>
                        <div style={{ fontSize: 12, lineHeight: 1.35 }}>
                          {excerpt}
                        </div>
                        {note && (
                          <div style={{ fontSize: 12, lineHeight: 1.35, color: 'rgb(147,197,253)', marginTop: 6 }}>
                            Note: {note}
                          </div>
                        )}
                      </>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      {error && (
        <div
          role="alert"
          aria-live="assertive"
          style={{ color: 'red', padding: '4px 8px', textAlign: 'center' }}
        >
          {tr(error)}
        </div>
      )}

      {colorPopoverHighlight && (
        <div
          ref={highlightColorPopoverRef}
          className="incremento-pdf-highlight-color-popover"
          role="dialog"
          aria-label={tr('reader_choose_annotation_color')}
          style={{ position: 'fixed', zIndex: 130,
            left: Math.max(8, Math.min(highlightColorPopover.x - 124, window.innerWidth - 256)),
            top: Math.max(8, Math.min(highlightColorPopover.y + 16, window.innerHeight - 116)),
            width: 248, maxWidth: 'calc(100vw - 16px)', boxSizing: 'border-box',
            padding: 10, borderRadius: 10, background: '#1f2937', color: '#f9fafb',
            border: '1px solid #64748b', boxShadow: '0 4px 16px rgba(0,0,0,0.35)' }}
        >
          <style>{`.incremento-pdf-highlight-color-popover button:focus-visible {
            outline: 2px solid #fff; outline-offset: 2px;
          }`}</style>
          <div style={{ fontSize: 12, marginBottom: 8 }}>{tr('reader_choose_annotation_color')}</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {Object.keys(HL_COLORS).map(color => (
              <button key={color} type="button"
                title={tr('reader_highlight_color', { color: tr(`reader_color_${color}`) })}
                aria-label={tr('reader_highlight_color', { color: tr(`reader_color_${color}`) })}
                aria-pressed={highlightSolidColor(colorPopoverHighlight.color) === highlightSolidColor(color)}
                onClick={() => {
                  recolorHighlight(colorPopoverHighlight.id, color);
                  deactivateHighlightResize();
                  setHighlightColorPopover(null);
                }}
                style={{ width: 24, height: 24, minWidth: 24, padding: 0,
                  background: highlightSolidColor(color), border: '1px solid rgba(255,255,255,0.6)',
                  borderRadius: '50%', color: '#111827', cursor: 'pointer' }}
              >{highlightSolidColor(colorPopoverHighlight.color) === highlightSolidColor(color) ? '✓' : ''}</button>
            ))}
          </div>
          <button type="button" onClick={() => {
            openHighlightColorPicker(colorPopoverHighlight);
            deactivateHighlightResize();
            setHighlightColorPopover(null);
          }} style={{ marginTop: 8, padding: '2px 6px', background: 'transparent',
            border: '1px solid #94a3b8', borderRadius: 4, color: 'inherit', cursor: 'pointer', fontSize: 12 }}>
            {tr('reader_more_colors')}
          </button>
        </div>
      )}

      {showHighlightControls && !colorPopoverHighlight && (
        <PdfHighlightTooltip tooltip={highlightTooltip} />
      )}

      <PdfLinkPreview containerRef={containerRef} pdfDocRef={pdfDocRef}
        links={linkAnnotations} tlLeft={renderInfo.tlLeft} sourcePage={page}
        documentToken={contentsGenerationRef.current} snapshotMode={snapshotMode} disabled={!!resizingHighlightId}
        maxPage={limitEnabled && limitMode !== 'warning' && !overrideEnabled && allowedMaxPage != null
          ? Math.max(page, allowedMaxPage) : null}
        pageLabels={pageLabels} appearance={pageAppearance} tr={tr}
        zoom={linkPreviewZoom} onZoom={applyLinkPreviewZoom} />

      {/* Canvas wrapper */}
      <div
        id="pdf-canvas-wrapper"
        ref={containerRef}
        onClick={activateHighlightFromPageClick}
        style={{
          position: 'relative',
          display: 'block',
          textAlign: 'center',
          background: pageAppearance.background,
        }}
      >
        <canvas ref={canvasARef} id="pdf-canvas-a"
          style={{
            display: 'block',
            margin: '0 auto',
            pointerEvents: 'none',
            filter: pageAppearance.filter,
          }} />
        <canvas ref={canvasBRef} id="pdf-canvas-b"
          style={{ display: 'none', position: 'absolute', top: 0, left: '50%',
                   transform: 'translateX(-50%)', pointerEvents: 'none',
                   filter: pageAppearance.filter }} />

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
            title={readAnchor?.text ? tr('reader_stopped_at', { text: readAnchor.text }) : tr('reader_stopping_page', { page: readPage })}
          >
            <span style={{ fontSize: 26, lineHeight: 1 }}>↦</span>
            <span>{tr('reader_read_marker')}</span>
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
            title={tr('reader_stopping_page', { page: readPage })}
          >
            <span style={{ fontSize: 26, lineHeight: 1 }}>↦</span>
            <span>{tr('reader_read_marker')}</span>
          </div>
        )}

        <div
          id="pdf-link-layer"
          aria-hidden={!clickableLinks}
          style={{
            position: 'absolute',
            inset: 0,
            zIndex: 3,
            pointerEvents: 'none',
          }}
        >
          {linkAnnotations.map((link, index) => (
            <button
              key={`${link.kind}-${link.url || link.targetPage || ''}-${index}`}
              type="button"
              data-pdf-link-index={index}
              tabIndex={clickableLinks ? 0 : -1}
              aria-label={link.label || (link.kind === 'external' ? tr('reader_open_external_link') : tr('reader_go_to_page', { page: link.targetPage }))}
              title={link.label || (link.kind === 'external' ? link.url : tr('reader_go_to_page', { page: link.targetPage }))}
              onClick={(event) => activatePdfLink(event, link)}
              style={{
                position: 'absolute',
                left: renderInfo.tlLeft + link.left,
                top: link.top,
                width: link.width,
                height: link.height,
                minWidth: 0,
                minHeight: 0,
                margin: 0,
                padding: 0,
                borderRadius: 2,
                border: clickableLinks ? '1px solid rgba(59,130,246,0.42)' : 'none',
                background: clickableLinks ? 'rgba(59,130,246,0.07)' : 'transparent',
                color: 'transparent',
                cursor: clickableLinks ? 'pointer' : 'text',
                pointerEvents: clickableLinks ? 'auto' : 'none',
              }}
            />
          ))}
        </div>

        <PdfSelectionLayer
          language={language}
          textLayerRef={textLayerRef}
          renderInfo={renderInfo}
          onTextClick={activateHighlightAtClientPoint}
        />

        <HighlightLayer
          nativeHighlightsVisible={nativeHighlightsVisible}
          showHighlightControls={showHighlightControls}
          showHighlightDeleteButtons={showHighlightDeleteButtons}
          language={language}
          pageHighlights={pageHighlights}
          renderInfo={renderInfo}
          deleteHighlight={deleteHighlight}
          editHighlightNote={editHighlightNote}
          showHighlightColorPopover={showHighlightColorPopover}
          activateHighlightResize={activateHighlightResize}
          resizingHighlightId={resizingHighlightId}
          beginHighlightResize={beginHighlightResize}
          moveHighlightResize={moveHighlightResize}
          endHighlightResize={endHighlightResize}
          cancelHighlightResize={cancelHighlightResize}
          focusedHighlightId={focusedHighlightId}
          showHighlightNote={showHighlightNote}
          moveHighlightNote={moveHighlightNote}
          hideHighlightNote={hideHighlightNote}
        />
        <PdfSnapshotLayer mode={snapshotMode} previewRef={snapPreviewRef}
          onStart={handleSnapStart} onMove={handleSnapMove} onEnd={handleSnapEnd} />

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
