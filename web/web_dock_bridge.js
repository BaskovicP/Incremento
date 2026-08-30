(function() {
  const INCREMENTO_CARD_ID = __CARD_ID__;
  const PYCMD_PREFIX = __PYCMD_PREFIX__;
  function emit(msg) {
    console.log(PYCMD_PREFIX + msg);
  }
  if (window._incrementoWebBridgeInstalled) {
    return;
  }
  window._incrementoWebBridgeInstalled = true;
  window._incrementoLastSelection = '';
  window._incrementoWebSnapshotActive = false;
  window._incrementoWebSnapshotBox = null;
  window._incrementoWebSnapshotStart = null;
  window._incrementoWebBookmarkTarget = null;
  window._incrementoWebProgressTimer = null;

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
      cardId: INCREMENTO_CARD_ID,
      url: window.location.href || '',
      scrollRatio: currentScrollRatio()
    };
  }

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
  });

  window.addEventListener('scroll', scheduleProgress, { passive: true });
  window.addEventListener('resize', scheduleProgress);
  window.addEventListener('beforeunload', emitProgress);
  window.addEventListener('pagehide', emitProgress);
})();
