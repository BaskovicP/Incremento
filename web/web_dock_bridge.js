(function() {
  const INCREMENTO_CARD_ID = __CARD_ID__;
  const PYCMD_PREFIX = __PYCMD_PREFIX__;
  function emit(msg) {
    console.log(PYCMD_PREFIX + msg);
  }
  if (
    window._incrementoWebBridgeInstalled &&
    typeof window.incrementoSetActiveCardId === 'function' &&
    typeof window.incrementoCaptureExtraction === 'function' &&
    typeof window.incrementoCaptureSnapshotAnchor === 'function' &&
    typeof window.incrementoResolveExtractionRects === 'function'
  ) {
    if (window.incrementoSetActiveCardId) {
      window.incrementoSetActiveCardId(INCREMENTO_CARD_ID);
    }
    return;
  }
  window._incrementoWebBridgeInstalled = true;
  window._incrementoActiveCardId = INCREMENTO_CARD_ID;
  window._incrementoLastSelection = '';
  window._incrementoWebSnapshotActive = false;
  window._incrementoWebSnapshotBox = null;
  window._incrementoWebSnapshotStart = null;
  window._incrementoWebBookmarkTarget = null;
  window._incrementoWebProgressTimer = null;
  window._incrementoLastExtraction = null;
  window._incrementoExtractionCaptureTimer = null;

  var EXTRACTION_EXACT_LIMIT = 4000;
  var EXTRACTION_CONTEXT_LIMIT = 96;
  var EXTRACTION_PATH_DEPTH_LIMIT = 64;
  var EXTRACTION_PATH_INDEX_LIMIT = 1000000;
  var EXTRACTION_OFFSET_LIMIT = 1000000;
  var EXTRACTION_ANCHOR_LIMIT = 48;
  var EXTRACTION_TEXT_SCAN_LIMIT = 1000000;
  var EXTRACTION_TEXT_NODE_LIMIT = 20000;
  var EXTRACTION_OCCURRENCE_LIMIT = 64;
  var EXTRACTION_CACHE_MS = 30000;
  var SNAPSHOT_MIN_DIMENSION = 6;
  var SNAPSHOT_MAX_DIMENSION = 100000;
  var SNAPSHOT_MAX_COORDINATE = 10000000;
  var SNAPSHOT_RATIO_SCALE = 1000000;
  var EXTRACTION_RECTS_PER_ANCHOR_LIMIT = 128;

  function clamp(value, minValue, maxValue) {
    var n = Number(value);
    if (!Number.isFinite(n)) {
      n = minValue;
    }
    return Math.max(minValue, Math.min(maxValue, n));
  }

  function maxScroll() {
    var doc = document.documentElement || document.body;
    return Math.max(0, ((doc && doc.scrollHeight) || 0) - window.innerHeight);
  }

  function currentScrollRatio() {
    var limit = maxScroll();
    return limit > 0 ? clamp(window.scrollY / limit, 0, 1) : 0;
  }

  function progressPayload() {
    return {
      cardId: Number(window._incrementoActiveCardId || INCREMENTO_CARD_ID),
      url: window.location.href || '',
      scrollRatio: currentScrollRatio()
    };
  }

  window.incrementoSetActiveCardId = function(cardId) {
    var nextCardId = Number(cardId);
    if (!Number.isInteger(nextCardId) || nextCardId <= 0) {
      return false;
    }
    if (Number(window._incrementoActiveCardId || 0) !== nextCardId) {
      window._incrementoLastSelection = '';
      window._incrementoLastExtraction = null;
    }
    window._incrementoActiveCardId = nextCardId;
    return true;
  };

  function emitProgress() {
    emit(__MSG_PROGRESS__ + JSON.stringify(progressPayload()));
  }

  function scheduleProgress() {
    if (window._incrementoWebProgressTimer) {
      clearTimeout(window._incrementoWebProgressTimer);
    }
    window._incrementoWebProgressTimer = setTimeout(function() {
      window._incrementoWebProgressTimer = null;
      emitProgress();
    }, 180);
  }

  function rootElement() {
    if (document.body) {
      return document.body;
    }
    if (document.documentElement) {
      return document.documentElement;
    }
    return null;
  }

  function bookmarkProbeY() {
    return Math.min(Math.max(72, window.innerHeight * 0.22), Math.max(0, window.innerHeight - 6));
  }

  function bookmarkProbeX() {
    return Math.min(Math.max(12, window.innerWidth * 0.5), Math.max(0, window.innerWidth - 12));
  }

  function buildNodePath(el) {
    var root = rootElement();
    if (!root || !el) {
      return [];
    }
    var path = [];
    var node = el;
    while (node && node !== root) {
      var parent = node.parentElement;
      if (!parent) {
        return [];
      }
      var index = Array.prototype.indexOf.call(parent.children, node);
      if (index < 0) {
        return [];
      }
      path.unshift(index);
      node = parent;
    }
    return path;
  }

  function buildDomPath(node) {
    var root = rootElement();
    if (!root || !node) {
      return [];
    }
    var path = [];
    var current = node;
    while (current && current !== root) {
      var parent = current.parentNode;
      if (!parent) {
        return [];
      }
      var index = Array.prototype.indexOf.call(parent.childNodes, current);
      if (index < 0) {
        return [];
      }
      path.unshift(index);
      current = parent;
    }
    return path;
  }

  function nodeFromPath(path) {
    var root = rootElement();
    if (!root || !Array.isArray(path)) {
      return null;
    }
    var node = root;
    for (var i = 0; i < path.length; i += 1) {
      var index = Number(path[i]);
      if (!Number.isInteger(index) || index < 0 || index >= node.children.length) {
        return null;
      }
      node = node.children[index];
    }
    return node;
  }

  function nodeFromDomPath(path) {
    var root = rootElement();
    if (!root || !Array.isArray(path)) {
      return null;
    }
    var node = root;
    for (var i = 0; i < path.length; i += 1) {
      var index = Number(path[i]);
      if (!Number.isInteger(index) || index < 0 || index >= node.childNodes.length) {
        return null;
      }
      node = node.childNodes[index];
    }
    return node;
  }

  function isIgnorableElement(el) {
    if (!el || !el.tagName) {
      return true;
    }
    return ['HTML', 'BODY', 'SCRIPT', 'STYLE', 'NOSCRIPT'].indexOf(el.tagName) >= 0;
  }

  function pickBookmarkElement() {
    var el = document.elementFromPoint(bookmarkProbeX(), bookmarkProbeY());
    if (!el) {
      return null;
    }
    if (el.nodeType === Node.TEXT_NODE) {
      el = el.parentElement;
    }
    while (el && isIgnorableElement(el)) {
      el = el.parentElement;
    }
    while (el && el.parentElement && el.getBoundingClientRect) {
      var rect = el.getBoundingClientRect();
      if (rect.height >= 18 && rect.width >= 18) {
        break;
      }
      el = el.parentElement;
      if (isIgnorableElement(el)) {
        break;
      }
    }
    return el && !isIgnorableElement(el) ? el : null;
  }

  function clearBookmarkMarker() {
    var target = window._incrementoWebBookmarkTarget;
    try {
      if (window._incrementoWebBookmarkSelectionApplied) {
        var sel = window.getSelection ? window.getSelection() : null;
        if (sel) {
          sel.removeAllRanges();
        }
      }
    } catch (_err) {}
    window._incrementoWebBookmarkSelectionApplied = false;
    if (!target) {
      return;
    }
    try {
      if (Object.prototype.hasOwnProperty.call(target, '__incrementoBookmarkPrevOutline')) {
        target.style.outline = target.__incrementoBookmarkPrevOutline;
      }
      if (Object.prototype.hasOwnProperty.call(target, '__incrementoBookmarkPrevOutlineOffset')) {
        target.style.outlineOffset = target.__incrementoBookmarkPrevOutlineOffset;
      }
      if (Object.prototype.hasOwnProperty.call(target, '__incrementoBookmarkPrevBoxShadow')) {
        target.style.boxShadow = target.__incrementoBookmarkPrevBoxShadow;
      }
      if (Object.prototype.hasOwnProperty.call(target, '__incrementoBookmarkPrevBackground')) {
        target.style.backgroundColor = target.__incrementoBookmarkPrevBackground;
      }
      if (Object.prototype.hasOwnProperty.call(target, '__incrementoBookmarkPrevTransition')) {
        target.style.transition = target.__incrementoBookmarkPrevTransition;
      }
    } catch (_err) {}
    window._incrementoWebBookmarkTarget = null;
  }

  function clampRangeOffset(node, offset) {
    var n = Number(offset);
    if (!Number.isFinite(n)) {
      n = 0;
    }
    n = Math.max(0, Math.floor(n));
    if (!node) {
      return 0;
    }
    if (node.nodeType === Node.TEXT_NODE) {
      return Math.min(n, (node.textContent || '').length);
    }
    return Math.min(n, node.childNodes ? node.childNodes.length : 0);
  }

  function bookmarkRange(bookmark) {
    if (
      !bookmark ||
      !Array.isArray(bookmark.selectionStartPath) ||
      !Array.isArray(bookmark.selectionEndPath)
    ) {
      return null;
    }
    var startNode = nodeFromDomPath(bookmark.selectionStartPath);
    var endNode = nodeFromDomPath(bookmark.selectionEndPath);
    if (!startNode || !endNode) {
      return null;
    }
    try {
      var range = document.createRange();
      range.setStart(startNode, clampRangeOffset(startNode, bookmark.selectionStartOffset));
      range.setEnd(endNode, clampRangeOffset(endNode, bookmark.selectionEndOffset));
      return range;
    } catch (_err) {
      return null;
    }
  }

  function extractionPathIsValid(path) {
    if (!Array.isArray(path) || path.length < 1 || path.length > EXTRACTION_PATH_DEPTH_LIMIT) {
      return false;
    }
    for (var i = 0; i < path.length; i += 1) {
      var value = Number(path[i]);
      if (!Number.isInteger(value) || value < 0 || value > EXTRACTION_PATH_INDEX_LIMIT) {
        return false;
      }
    }
    return true;
  }

  function extractionOffsetIsValid(value) {
    var offset = Number(value);
    return Number.isInteger(offset) && offset >= 0 && offset <= EXTRACTION_OFFSET_LIMIT;
  }

  function textExtractionAnchorIsValid(anchor) {
    return !!(
      anchor &&
      Number(anchor.version) === 1 &&
      (!anchor.kind || anchor.kind === 'text') &&
      typeof anchor.exact === 'string' &&
      anchor.exact.trim() &&
      anchor.exact.length <= EXTRACTION_EXACT_LIMIT &&
      typeof (anchor.prefix || '') === 'string' &&
      String(anchor.prefix || '').length <= EXTRACTION_CONTEXT_LIMIT &&
      typeof (anchor.suffix || '') === 'string' &&
      String(anchor.suffix || '').length <= EXTRACTION_CONTEXT_LIMIT &&
      extractionPathIsValid(anchor.startPath) &&
      extractionPathIsValid(anchor.endPath) &&
      extractionOffsetIsValid(anchor.startOffset) &&
      extractionOffsetIsValid(anchor.endOffset) &&
      (!anchor.startPath.every(function(value, index) {
        return value === anchor.endPath[index];
      }) || Number(anchor.endOffset) > Number(anchor.startOffset))
    );
  }

  function snapshotIntegerIsValid(value, minimum, maximum) {
    var normalized = Number(value);
    return Number.isInteger(normalized) && normalized >= minimum && normalized <= maximum;
  }

  function snapshotPathIsValid(path) {
    if (!Array.isArray(path) || path.length > EXTRACTION_PATH_DEPTH_LIMIT) {
      return false;
    }
    for (var i = 0; i < path.length; i += 1) {
      if (!snapshotIntegerIsValid(path[i], 0, EXTRACTION_PATH_INDEX_LIMIT)) {
        return false;
      }
    }
    return true;
  }

  function snapshotAnchorIsValid(anchor) {
    var tag = String((anchor && anchor.anchorTag) || '');
    return !!(
      anchor &&
      Number(anchor.version) === 1 &&
      anchor.kind === 'snapshot' &&
      snapshotIntegerIsValid(anchor.pageX, 0, SNAPSHOT_MAX_COORDINATE) &&
      snapshotIntegerIsValid(anchor.pageY, 0, SNAPSHOT_MAX_COORDINATE) &&
      snapshotIntegerIsValid(anchor.width, SNAPSHOT_MIN_DIMENSION, SNAPSHOT_MAX_DIMENSION) &&
      snapshotIntegerIsValid(anchor.height, SNAPSHOT_MIN_DIMENSION, SNAPSHOT_MAX_DIMENSION) &&
      snapshotIntegerIsValid(anchor.documentWidth, 1, SNAPSHOT_MAX_COORDINATE) &&
      snapshotIntegerIsValid(anchor.documentHeight, 1, SNAPSHOT_MAX_COORDINATE) &&
      snapshotPathIsValid(anchor.anchorPath) &&
      (!anchor.anchorPath.length || /^[a-z][a-z0-9-]{0,31}$/.test(tag)) &&
      snapshotIntegerIsValid(anchor.anchorXRatio, 0, SNAPSHOT_RATIO_SCALE) &&
      snapshotIntegerIsValid(anchor.anchorYRatio, 0, SNAPSHOT_RATIO_SCALE)
    );
  }

  function extractionAnchorIsValid(anchor) {
    return snapshotAnchorIsValid(anchor) || textExtractionAnchorIsValid(anchor);
  }

  function excludedExtractionTextNode(node) {
    var parent = node && node.parentElement;
    while (parent) {
      var tag = String(parent.tagName || '').toUpperCase();
      if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEXTAREA'].indexOf(tag) >= 0) {
        return true;
      }
      parent = parent.parentElement;
    }
    return false;
  }

  function extractionTextIndex() {
    var root = rootElement();
    if (!root || !document.createTreeWalker || typeof NodeFilter === 'undefined') {
      return null;
    }
    var walker;
    try {
      walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    } catch (_err) {
      return null;
    }
    var nodes = [];
    var starts = [];
    var text = '';
    var node = null;
    while (
      nodes.length < EXTRACTION_TEXT_NODE_LIMIT &&
      text.length < EXTRACTION_TEXT_SCAN_LIMIT &&
      (node = walker.nextNode())
    ) {
      if (excludedExtractionTextNode(node)) {
        continue;
      }
      var nodeText = String(node.textContent || '');
      if (!nodeText) {
        continue;
      }
      var remaining = EXTRACTION_TEXT_SCAN_LIMIT - text.length;
      if (nodeText.length > remaining) {
        nodeText = nodeText.slice(0, remaining);
      }
      starts.push(text.length);
      nodes.push(node);
      text += nodeText;
    }
    return { nodes: nodes, starts: starts, text: text };
  }

  function extractionAbsoluteOffset(index, node, offset) {
    if (!index || !node || node.nodeType !== Node.TEXT_NODE) {
      return null;
    }
    var nodeIndex = index.nodes.indexOf(node);
    if (nodeIndex < 0) {
      return null;
    }
    var normalizedOffset = clampRangeOffset(node, offset);
    return index.starts[nodeIndex] + normalizedOffset;
  }

  function extractionBoundaryAt(index, position, isEnd) {
    if (!index || !index.nodes.length) {
      return null;
    }
    var target = Number(position);
    if (!Number.isInteger(target) || target < 0 || target > index.text.length) {
      return null;
    }
    for (var i = 0; i < index.nodes.length; i += 1) {
      var node = index.nodes[i];
      var start = index.starts[i];
      var end = start + String(node.textContent || '').length;
      if ((isEnd && target <= end && target >= start) || (!isEnd && target < end && target >= start)) {
        return { node: node, offset: target - start };
      }
    }
    if (isEnd && target === index.text.length) {
      var lastNode = index.nodes[index.nodes.length - 1];
      return { node: lastNode, offset: String(lastNode.textContent || '').length };
    }
    return null;
  }

  function rangeFromExtractionPaths(anchor) {
    if (!textExtractionAnchorIsValid(anchor)) {
      return null;
    }
    var startNode = nodeFromDomPath(anchor.startPath);
    var endNode = nodeFromDomPath(anchor.endPath);
    if (!startNode || !endNode) {
      return null;
    }
    try {
      var range = document.createRange();
      range.setStart(startNode, clampRangeOffset(startNode, anchor.startOffset));
      range.setEnd(endNode, clampRangeOffset(endNode, anchor.endOffset));
      return range.toString() === anchor.exact ? range : null;
    } catch (_err) {
      return null;
    }
  }

  function matchingPrefixLength(text, occurrence, prefix) {
    var expected = String(prefix || '');
    var available = text.slice(Math.max(0, occurrence - expected.length), occurrence);
    var score = 0;
    while (
      score < expected.length &&
      score < available.length &&
      expected.charAt(expected.length - 1 - score) === available.charAt(available.length - 1 - score)
    ) {
      score += 1;
    }
    return score;
  }

  function matchingSuffixLength(text, occurrenceEnd, suffix) {
    var expected = String(suffix || '');
    var available = text.slice(occurrenceEnd, occurrenceEnd + expected.length);
    var score = 0;
    while (
      score < expected.length &&
      score < available.length &&
      expected.charAt(score) === available.charAt(score)
    ) {
      score += 1;
    }
    return score;
  }

  function rangeFromExtractionQuote(anchor, existingIndex) {
    if (!textExtractionAnchorIsValid(anchor)) {
      return null;
    }
    var index = arguments.length >= 2 ? existingIndex : extractionTextIndex();
    if (!index) {
      return null;
    }
    var exact = anchor.exact;
    var occurrences = [];
    var searchFrom = 0;
    while (occurrences.length <= EXTRACTION_OCCURRENCE_LIMIT) {
      var occurrence = index.text.indexOf(exact, searchFrom);
      if (occurrence < 0) {
        break;
      }
      occurrences.push(occurrence);
      searchFrom = occurrence + Math.max(1, exact.length);
    }
    if (!occurrences.length || occurrences.length > EXTRACTION_OCCURRENCE_LIMIT) {
      return null;
    }

    var selectedOccurrence = occurrences[0];
    if (occurrences.length > 1) {
      var bestScore = -1;
      var tied = false;
      for (var i = 0; i < occurrences.length; i += 1) {
        var candidate = occurrences[i];
        var score = matchingPrefixLength(index.text, candidate, anchor.prefix) +
          matchingSuffixLength(index.text, candidate + exact.length, anchor.suffix);
        if (score > bestScore) {
          bestScore = score;
          selectedOccurrence = candidate;
          tied = false;
        } else if (score === bestScore) {
          tied = true;
        }
      }
      var totalContext = String(anchor.prefix || '').length +
        String(anchor.suffix || '').length;
      var requiredScore = Math.min(8, totalContext);
      if (totalContext < 4 || bestScore < requiredScore || tied) {
        return null;
      }
    }

    var start = extractionBoundaryAt(index, selectedOccurrence, false);
    var end = extractionBoundaryAt(index, selectedOccurrence + exact.length, true);
    if (!start || !end) {
      return null;
    }
    try {
      var range = document.createRange();
      range.setStart(start.node, start.offset);
      range.setEnd(end.node, end.offset);
      return range.toString() === exact ? range : null;
    } catch (_err) {
      return null;
    }
  }

  function resolveExtractionAnchor(anchor) {
    return rangeFromExtractionPaths(anchor) || rangeFromExtractionQuote(anchor);
  }

  function documentRectFromClientRect(rect) {
    if (!rect) {
      return null;
    }
    var left = Number(rect.left);
    var top = Number(rect.top);
    var width = Number(rect.width);
    var height = Number(rect.height);
    if (
      !Number.isFinite(left) ||
      !Number.isFinite(top) ||
      !Number.isFinite(width) ||
      !Number.isFinite(height) ||
      width <= 0 ||
      height <= 0
    ) {
      return null;
    }
    return {
      x: Math.round(clamp(Number(window.scrollX || 0) + left, 0, SNAPSHOT_MAX_COORDINATE) * 100) / 100,
      y: Math.round(clamp(Number(window.scrollY || 0) + top, 0, SNAPSHOT_MAX_COORDINATE) * 100) / 100,
      width: Math.round(clamp(width, 0.5, SNAPSHOT_MAX_DIMENSION) * 100) / 100,
      height: Math.round(clamp(height, 0.5, SNAPSHOT_MAX_DIMENSION) * 100) / 100
    };
  }

  function rangeDocumentRects(range) {
    if (!range || typeof range.getClientRects !== 'function') {
      return [];
    }
    var clientRects;
    try {
      clientRects = Array.from(range.getClientRects());
    } catch (_err) {
      return [];
    }
    var result = [];
    for (
      var i = 0;
      i < clientRects.length && result.length < EXTRACTION_RECTS_PER_ANCHOR_LIMIT;
      i += 1
    ) {
      var normalized = documentRectFromClientRect(clientRects[i]);
      if (normalized) {
        result.push(normalized);
      }
    }
    return result;
  }

  function captureCurrentExtraction() {
    var sel = window.getSelection ? window.getSelection() : null;
    if (!sel || sel.rangeCount < 1) {
      return null;
    }
    var range;
    try {
      range = sel.getRangeAt(0).cloneRange();
    } catch (_err) {
      return null;
    }
    var exact = String(range.toString() || '');
    var rendered = '';
    try {
      rendered = String(typeof sel.toString === 'function' ? sel.toString() : '');
    } catch (_err) {
      rendered = '';
    }
    var text = rendered.trim() || exact.trim();
    if (!text) {
      return null;
    }
    var capture = {
      cardId: Number(window._incrementoActiveCardId || INCREMENTO_CARD_ID),
      url: window.location.href || '',
      text: text,
      anchor: null,
      rects: rangeDocumentRects(range),
      scrollX: Number(window.scrollX || 0),
      scrollY: Number(window.scrollY || 0),
      capturedAt: Date.now()
    };
    if (exact.length > EXTRACTION_EXACT_LIMIT) {
      return capture;
    }
    var startPath = buildDomPath(range.startContainer);
    var endPath = buildDomPath(range.endContainer);
    if (!extractionPathIsValid(startPath) || !extractionPathIsValid(endPath)) {
      return capture;
    }
    var prefix = '';
    var suffix = '';
    var index = extractionTextIndex();
    var absoluteStart = extractionAbsoluteOffset(index, range.startContainer, range.startOffset);
    var absoluteEnd = extractionAbsoluteOffset(index, range.endContainer, range.endOffset);
    if (absoluteStart !== null && absoluteEnd !== null && absoluteEnd >= absoluteStart) {
      prefix = index.text.slice(
        Math.max(0, absoluteStart - EXTRACTION_CONTEXT_LIMIT),
        absoluteStart
      );
      suffix = index.text.slice(
        absoluteEnd,
        absoluteEnd + EXTRACTION_CONTEXT_LIMIT
      );
    }
    capture.anchor = {
      version: 1,
      exact: exact,
      prefix: prefix,
      suffix: suffix,
      startPath: startPath,
      startOffset: clampRangeOffset(range.startContainer, range.startOffset),
      endPath: endPath,
      endOffset: clampRangeOffset(range.endContainer, range.endOffset)
    };
    if (!extractionAnchorIsValid(capture.anchor)) {
      capture.anchor = null;
    }
    return capture;
  }

  function cacheCurrentExtraction() {
    var capture = captureCurrentExtraction();
    if (capture) {
      window._incrementoLastExtraction = capture;
      window._incrementoLastSelection = capture.text;
    }
    return capture;
  }

  window.incrementoCaptureExtraction = function() {
    var current = cacheCurrentExtraction();
    if (current) {
      return current;
    }
    var cached = window._incrementoLastExtraction;
    if (
      cached &&
      cached.url === (window.location.href || '') &&
      Date.now() - Number(cached.capturedAt || 0) <= EXTRACTION_CACHE_MS
    ) {
      return cached;
    }
    return null;
  };

  function snapshotDocumentSize() {
    var doc = document.documentElement;
    var body = document.body;
    return {
      width: Math.max(
        1,
        Number(window.innerWidth || 0),
        Number((doc && doc.scrollWidth) || 0),
        Number((body && body.scrollWidth) || 0)
      ),
      height: Math.max(
        1,
        Number(window.innerHeight || 0),
        Number((doc && doc.scrollHeight) || 0),
        Number((body && body.scrollHeight) || 0)
      )
    };
  }

  function snapshotAnchorElement(clientX, clientY) {
    if (!document.elementFromPoint) {
      return null;
    }
    var el = null;
    try {
      el = document.elementFromPoint(clientX, clientY);
    } catch (_err) {
      return null;
    }
    if (el && el.nodeType === Node.TEXT_NODE) {
      el = el.parentElement;
    }
    while (el && isIgnorableElement(el)) {
      el = el.parentElement;
    }
    return el && el.getBoundingClientRect ? el : null;
  }

  window.incrementoCaptureSnapshotAnchor = function(rawRect) {
    var input = rawRect || {};
    var viewportWidth = Math.max(1, Number(window.innerWidth || 0));
    var viewportHeight = Math.max(1, Number(window.innerHeight || 0));
    var left = Math.round(clamp(input.x, 0, viewportWidth));
    var top = Math.round(clamp(input.y, 0, viewportHeight));
    var width = Math.round(clamp(input.width, 0, Math.min(SNAPSHOT_MAX_DIMENSION, viewportWidth - left)));
    var height = Math.round(clamp(input.height, 0, Math.min(SNAPSHOT_MAX_DIMENSION, viewportHeight - top)));
    if (width < SNAPSHOT_MIN_DIMENSION || height < SNAPSHOT_MIN_DIMENSION) {
      return null;
    }

    var centerX = left + (width / 2);
    var centerY = top + (height / 2);
    var anchorEl = snapshotAnchorElement(centerX, centerY);
    var anchorPath = [];
    var anchorTag = '';
    var anchorXRatio = 0;
    var anchorYRatio = 0;
    if (anchorEl) {
      var elementRect = anchorEl.getBoundingClientRect();
      if (elementRect && elementRect.width > 0 && elementRect.height > 0) {
        anchorPath = buildNodePath(anchorEl);
        anchorTag = String(anchorEl.tagName || '').toLowerCase();
        anchorXRatio = Math.round(
          clamp((centerX - elementRect.left) / elementRect.width, 0, 1) * SNAPSHOT_RATIO_SCALE
        );
        anchorYRatio = Math.round(
          clamp((centerY - elementRect.top) / elementRect.height, 0, 1) * SNAPSHOT_RATIO_SCALE
        );
      }
    }
    if (!anchorPath.length) {
      anchorPath = [];
      anchorTag = '';
      anchorXRatio = 0;
      anchorYRatio = 0;
    }

    var documentSize = snapshotDocumentSize();
    var anchor = {
      version: 1,
      kind: 'snapshot',
      pageX: Math.round(clamp(Number(window.scrollX || 0) + left, 0, SNAPSHOT_MAX_COORDINATE)),
      pageY: Math.round(clamp(Number(window.scrollY || 0) + top, 0, SNAPSHOT_MAX_COORDINATE)),
      width: width,
      height: height,
      documentWidth: Math.round(clamp(documentSize.width, 1, SNAPSHOT_MAX_COORDINATE)),
      documentHeight: Math.round(clamp(documentSize.height, 1, SNAPSHOT_MAX_COORDINATE)),
      anchorPath: anchorPath,
      anchorTag: anchorTag,
      anchorXRatio: anchorXRatio,
      anchorYRatio: anchorYRatio
    };
    if (!snapshotAnchorIsValid(anchor)) {
      return null;
    }
    return {
      cardId: Number(window._incrementoActiveCardId || INCREMENTO_CARD_ID),
      url: window.location.href || '',
      anchor: anchor,
      rects: [{
        x: Number(anchor.pageX),
        y: Number(anchor.pageY),
        width: Number(anchor.width),
        height: Number(anchor.height)
      }],
      scrollX: Number(window.scrollX || 0),
      scrollY: Number(window.scrollY || 0)
    };
  };

  window.incrementoResolveExtractionAnchor = function(anchor) {
    return resolveExtractionAnchor(anchor);
  };

  function snapshotDocumentRect(anchor) {
    if (!snapshotAnchorIsValid(anchor)) {
      return null;
    }
    if (anchor.anchorPath.length && anchor.anchorTag) {
      var el = nodeFromPath(anchor.anchorPath);
      if (
        el &&
        String(el.tagName || '').toLowerCase() === anchor.anchorTag &&
        el.getBoundingClientRect
      ) {
        try {
          var elementRect = el.getBoundingClientRect();
          if (elementRect && elementRect.width > 0 && elementRect.height > 0) {
            var centerX = elementRect.left + (
              elementRect.width * Number(anchor.anchorXRatio) / SNAPSHOT_RATIO_SCALE
            );
            var centerY = elementRect.top + (
              elementRect.height * Number(anchor.anchorYRatio) / SNAPSHOT_RATIO_SCALE
            );
            return {
              x: Math.round(clamp(
                Number(window.scrollX || 0) + centerX - (Number(anchor.width) / 2),
                0,
                SNAPSHOT_MAX_COORDINATE
              ) * 100) / 100,
              y: Math.round(clamp(
                Number(window.scrollY || 0) + centerY - (Number(anchor.height) / 2),
                0,
                SNAPSHOT_MAX_COORDINATE
              ) * 100) / 100,
              width: Number(anchor.width),
              height: Number(anchor.height)
            };
          }
        } catch (_err) {}
      }
    }
    return {
      x: Number(anchor.pageX),
      y: Number(anchor.pageY),
      width: Number(anchor.width),
      height: Number(anchor.height)
    };
  }

  function boundedExtractionAnchors(values, excludedIds) {
    if (!Array.isArray(values)) {
      return [];
    }
    var anchors = [];
    var seen = {};
    for (var i = 0; i < values.length && anchors.length < EXTRACTION_ANCHOR_LIMIT; i += 1) {
      var anchor = values[i];
      var id = String((anchor && anchor.id) || '');
      if (!id || id.length > 64 || seen[id] || (excludedIds && excludedIds[id])) {
        continue;
      }
      if (!extractionAnchorIsValid(anchor)) {
        continue;
      }
      seen[id] = true;
      anchors.push(anchor);
    }
    return anchors;
  }

  window.incrementoResolveExtractionRects = function(state) {
    var raw = state || {};
    var saved = boundedExtractionAnchors(raw.saved, null);
    var savedIds = {};
    for (var i = 0; i < saved.length; i += 1) {
      savedIds[String(saved[i].id)] = true;
    }
    var pending = boundedExtractionAnchors(raw.pending, savedIds);
    var markers = [];
    var sharedQuoteIndex;

    function resolveRange(anchor) {
      var directRange = rangeFromExtractionPaths(anchor);
      if (directRange) {
        return directRange;
      }
      if (sharedQuoteIndex === undefined) {
        sharedQuoteIndex = extractionTextIndex();
      }
      return rangeFromExtractionQuote(anchor, sharedQuoteIndex);
    }

    function appendMarker(anchor, stateName) {
      var kind = anchor.kind === 'snapshot' ? 'snapshot' : 'text';
      var rects = [];
      if (kind === 'snapshot') {
        var snapshotRect = snapshotDocumentRect(anchor);
        if (snapshotRect) {
          rects.push(snapshotRect);
        }
      } else {
        var range = resolveRange(anchor);
        rects = rangeDocumentRects(range);
      }
      if (!rects.length) {
        return;
      }
      markers.push({
        id: String(anchor.id),
        state: stateName,
        kind: kind,
        rects: rects
      });
    }

    for (var j = 0; j < saved.length; j += 1) {
      appendMarker(saved[j], 'saved');
    }
    for (var k = 0; k < pending.length; k += 1) {
      appendMarker(pending[k], 'pending');
    }
    return {
      cardId: Number(window._incrementoActiveCardId || INCREMENTO_CARD_ID),
      url: window.location.href || '',
      scrollX: Number(window.scrollX || 0),
      scrollY: Number(window.scrollY || 0),
      markers: markers
    };
  };

  function applyBookmarkMarker(bookmark) {
    clearBookmarkMarker();
    if (!bookmark || !Array.isArray(bookmark.path)) {
      return false;
    }
    var range = bookmarkRange(bookmark);
    if (range) {
      try {
        var sel = window.getSelection ? window.getSelection() : null;
        if (sel) {
          sel.removeAllRanges();
          sel.addRange(range.cloneRange());
          window._incrementoWebBookmarkSelectionApplied = true;
        }
      } catch (_err) {}
    }
    var el = nodeFromPath(bookmark.path);
    if (!el || !el.style) {
      return false;
    }
    try {
      el.__incrementoBookmarkPrevOutline = el.style.outline;
      el.__incrementoBookmarkPrevOutlineOffset = el.style.outlineOffset;
      el.__incrementoBookmarkPrevBoxShadow = el.style.boxShadow;
      el.__incrementoBookmarkPrevBackground = el.style.backgroundColor;
      el.__incrementoBookmarkPrevTransition = el.style.transition;
      el.style.transition = 'outline-color 140ms ease, box-shadow 140ms ease, background-color 140ms ease';
      el.style.outline = '3px solid rgba(245, 158, 11, 0.96)';
      el.style.outlineOffset = '2px';
      el.style.boxShadow = '0 0 0 6px rgba(245, 158, 11, 0.18)';
      el.style.backgroundColor = 'rgba(245, 158, 11, 0.08)';
      window._incrementoWebBookmarkTarget = el;
      return true;
    } catch (_err) {
      window._incrementoWebBookmarkTarget = null;
      return false;
    }
  }

  function scrollToBookmark(bookmark) {
    if (!bookmark || !Array.isArray(bookmark.path)) {
      return false;
    }
    var range = bookmarkRange(bookmark);
    if (range) {
      try {
        var rangeRect = range.getBoundingClientRect();
        if (rangeRect && (rangeRect.height > 0 || rangeRect.width > 0)) {
          var rangeTop = window.scrollY + rangeRect.top - Math.min(140, window.innerHeight * 0.22);
          window.scrollTo(0, Math.max(0, rangeTop));
          applyBookmarkMarker(bookmark);
          scheduleProgress();
          return true;
        }
      } catch (_err) {}
    }
    var el = nodeFromPath(bookmark.path);
    if (!el || !el.getBoundingClientRect) {
      return false;
    }
    var rect = el.getBoundingClientRect();
    var offsetRatio = clamp(bookmark.offsetRatio || 0, 0, 1);
    var desiredTop = window.scrollY + rect.top + (rect.height * offsetRatio) - Math.min(140, window.innerHeight * 0.22);
    window.scrollTo(0, Math.max(0, desiredTop));
    applyBookmarkMarker(bookmark);
    scheduleProgress();
    return true;
  }

  window.incrementoGetProgressPayload = function() {
    return progressPayload();
  };

  window.incrementoCaptureBookmark = function() {
    var sel = window.getSelection ? window.getSelection() : null;
    var selectedText = sel ? sel.toString().trim() : '';
    if (sel && sel.rangeCount > 0 && selectedText) {
      try {
        var range = sel.getRangeAt(0).cloneRange();
        var startNode = range.startContainer;
        var endNode = range.endContainer;
        var anchorEl =
          startNode && startNode.nodeType === Node.TEXT_NODE
            ? startNode.parentElement
            : startNode;
        while (anchorEl && isIgnorableElement(anchorEl)) {
          anchorEl = anchorEl.parentElement;
        }
        if (anchorEl) {
          var anchorRect = anchorEl.getBoundingClientRect();
          var selectionBookmark = {
            mode: 'selection',
            path: buildNodePath(anchorEl),
            offsetRatio: anchorRect.height > 1 ? clamp((range.getBoundingClientRect().top - anchorRect.top) / anchorRect.height, 0, 1) : 0,
            scrollRatio: currentScrollRatio(),
            tag: ((anchorEl.tagName || '').toLowerCase()),
            text: selectedText.slice(0, 240),
            selectionStartPath: buildDomPath(startNode),
            selectionStartOffset: range.startOffset,
            selectionEndPath: buildDomPath(endNode),
            selectionEndOffset: range.endOffset
          };
          if (selectionBookmark.path.length && selectionBookmark.selectionStartPath.length && selectionBookmark.selectionEndPath.length) {
            applyBookmarkMarker(selectionBookmark);
            return {
              url: window.location.href || '',
              bookmark: selectionBookmark
            };
          }
        }
      } catch (_err) {}
    }
    var el = pickBookmarkElement();
    if (!el) {
      return null;
    }
    var rect = el.getBoundingClientRect();
    var offsetRatio = rect.height > 1 ? clamp((bookmarkProbeY() - rect.top) / rect.height, 0, 1) : 0;
    var bookmark = {
      path: buildNodePath(el),
      offsetRatio: offsetRatio,
      scrollRatio: currentScrollRatio(),
      tag: ((el.tagName || '').toLowerCase()),
      text: ((el.innerText || el.textContent || '').trim().slice(0, 240))
    };
    if (!bookmark.path.length) {
      return null;
    }
    applyBookmarkMarker(bookmark);
    return {
      url: window.location.href || '',
      bookmark: bookmark
    };
  };

  window.incrementoApplyBookmarkMarker = function(bookmark) {
    return applyBookmarkMarker(bookmark);
  };

  window.incrementoApplyRestoreState = function(state) {
    var restore = state || {};
    var bookmark = restore.bookmark || null;
    var rememberScroll = !!restore.rememberScroll;
    var scrollRatio = clamp(restore.scrollRatio || 0, 0, 1);

    function attemptRestore() {
      if (bookmark && scrollToBookmark(bookmark)) {
        return true;
      }
      if (bookmark) {
        applyBookmarkMarker(bookmark);
      }
      if (rememberScroll) {
        window.scrollTo(0, maxScroll() * scrollRatio);
        scheduleProgress();
      }
      return false;
    }

    setTimeout(attemptRestore, 60);
    setTimeout(attemptRestore, 220);
    return true;
  };

  window.incrementoDisableSnapshotMode = function() {
    return setSnapshotActive(false);
  };

  function ensureBox() {
    if (window._incrementoWebSnapshotBox && document.documentElement && document.documentElement.contains(window._incrementoWebSnapshotBox)) {
      return window._incrementoWebSnapshotBox;
    }
    var box = document.createElement('div');
    box.style.position = 'fixed';
    box.style.zIndex = '2147483647';
    box.style.border = '2px solid rgba(37,99,235,0.95)';
    box.style.background = 'rgba(37,99,235,0.16)';
    box.style.pointerEvents = 'none';
    box.style.display = 'none';
    box.style.boxSizing = 'border-box';
    document.documentElement.appendChild(box);
    window._incrementoWebSnapshotBox = box;
    return box;
  }

  function hideBox() {
    var box = ensureBox();
    box.style.display = 'none';
  }

  function drawBox(a, b) {
    var box = ensureBox();
    var left = Math.min(a.x, b.x);
    var top = Math.min(a.y, b.y);
    var width = Math.abs(a.x - b.x);
    var height = Math.abs(a.y - b.y);
    box.style.left = left + 'px';
    box.style.top = top + 'px';
    box.style.width = width + 'px';
    box.style.height = height + 'px';
    box.style.display = 'block';
  }

  function setSnapshotActive(active) {
    window._incrementoWebSnapshotActive = !!active;
    if (!window._incrementoWebSnapshotActive) {
      window._incrementoWebSnapshotStart = null;
      hideBox();
    }
    try {
      document.documentElement.style.cursor = window._incrementoWebSnapshotActive ? 'crosshair' : '';
      if (document.body) {
        document.body.style.cursor = window._incrementoWebSnapshotActive ? 'crosshair' : '';
      }
    } catch (_err) {}
    return window._incrementoWebSnapshotActive;
  }

  window.incrementoToggleSnapshotMode = function() {
    return setSnapshotActive(!window._incrementoWebSnapshotActive);
  };

  document.addEventListener('selectionchange', function() {
    var sel = window.getSelection ? window.getSelection() : null;
    var text = sel ? sel.toString().trim() : '';
    if (!text) {
      return;
    }
    window._incrementoLastSelection = text;
    if (window._incrementoExtractionCaptureTimer) {
      clearTimeout(window._incrementoExtractionCaptureTimer);
    }
    window._incrementoExtractionCaptureTimer = setTimeout(function() {
      window._incrementoExtractionCaptureTimer = null;
      cacheCurrentExtraction();
    }, 60);
  });
  document.addEventListener('mouseup', cacheCurrentExtraction, true);
  document.addEventListener('keyup', cacheCurrentExtraction, true);

  window.addEventListener('scroll', function() {
    scheduleProgress();
  }, { passive: true });
  window.addEventListener('resize', function() {
    scheduleProgress();
  });
  window.addEventListener('beforeunload', emitProgress);
  window.addEventListener('pagehide', emitProgress);
})();
