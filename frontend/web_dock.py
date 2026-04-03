"""
web_dock.py — Web browsing dock (QWebEngineView with persistent profile).

Displays web pages in a right-side dock that persists across card reviews.
The last-visited URL is saved when the page finishes loading.

Public API:
    show_web_in_dock(card_id, home_url, last_url)
    open_web_location(card_id, target_url)
    on_web_question_shown(card)
    on_web_reviewer_will_end()
    on_add_cards_did_add_note(note)
    sync_web_note_type()
    add_web_function()
"""

import json
import os
import re
import tempfile
from urllib.parse import quote, urlparse

from aqt import mw
from aqt.utils import showInfo, tooltip
from aqt.qt import (
    QApplication,
    QCheckBox,
    QDialog,
    QDockWidget,
    QEvent,
    QHBoxLayout,
    QLabel,
    QObject,
    QPoint,
    QPushButton,
    QRect,
    QShortcut,
    QKeySequence,
    QTextBrowser,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
    qconnect,
)
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView

try:
    from ..backend.db import add_web_card_source, get_web_card_sources
    from ..backend.web_manager import (
        WEB_NOTE_TYPE,
        add_web_card,
        build_external_web_url,
        configured_remember_browser_card_scroll,
        ensure_web_note_type,
        get_web_progress,
        get_web_url,
        set_web_bookmark,
        set_web_scroll_position,
        set_web_url,
    )
except ImportError:
    from db import add_web_card_source, get_web_card_sources
    from web_manager import (
        WEB_NOTE_TYPE,
        add_web_card,
        build_external_web_url,
        configured_remember_browser_card_scroll,
        ensure_web_note_type,
        get_web_progress,
        get_web_url,
        set_web_bookmark,
        set_web_scroll_position,
        set_web_url,
    )

_ADDON_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)

_web_dock = None
_current_web_card_id = None
_current_web_home_url = None
_web_profile = None
_PYCMD_BRIDGE = "__incremento_webdock_pycmd__:"
_MSG_SELECTION_STATE = "incremento_selection_state:"
_MSG_FILL_FIELD = "incremento_web_fill_field:"
_MSG_SNAPSHOT = "incremento_web_snapshot:"
_MSG_PROGRESS = "incremento_web_progress:"
_track_web_window_with_extension = False
_web_shortcuts_registered = False
_web_shortcuts = []
_web_interaction_filter = None
_web_snapshot_mode = False
_web_snapshot_origin = None
_web_snapshot_shield = None
_web_snapshot_overlay = None
_web_snapshot_override_cursor = False
_pending_web_restore = None


def _remember_browser_card_scroll() -> bool:
    try:
        return bool(configured_remember_browser_card_scroll())
    except Exception:
        return True


def _web_progress_state(card_id: int | None = None) -> dict:
    try:
        target_card_id = int(card_id if card_id is not None else _current_web_card_id)
    except Exception:
        target_card_id = 0
    if target_card_id <= 0:
        return {
            "url": "",
            "scroll_ratio": 0.0,
            "bookmark_url": "",
            "bookmark_payload": {},
        }
    try:
        return get_web_progress(_ADDON_DIR, target_card_id)
    except Exception:
        return {
            "url": "",
            "scroll_ratio": 0.0,
            "bookmark_url": "",
            "bookmark_payload": {},
        }


def _refresh_web_bookmark_button() -> None:
    if _web_dock is None:
        return
    progress = _web_progress_state()
    has_bookmark = bool(progress.get("bookmark_url")) and bool(
        progress.get("bookmark_payload")
    )
    try:
        _web_dock._bookmark_btn.setText("Bookmark")
        _web_dock._bookmark_btn.setToolTip(
            "Replace the saved browser-card bookmark with the current reading position."
            if has_bookmark
            else "Save the current reading position as the browser-card bookmark."
        )
    except Exception:
        pass


def _persist_web_url(card_id: int | None, url: str | None) -> None:
    try:
        target_card_id = int(card_id) if card_id is not None else 0
    except Exception:
        target_card_id = 0
    target_url = str(url or "").strip()
    if target_card_id <= 0 or not target_url or target_url == "about:blank":
        return
    try:
        set_web_url(_ADDON_DIR, target_card_id, target_url)
    except Exception:
        pass


def _persist_web_scroll(card_id: int | None, data) -> None:
    if not _remember_browser_card_scroll():
        return
    try:
        target_card_id = int(card_id if card_id is not None else _current_web_card_id)
    except Exception:
        target_card_id = 0
    if target_card_id <= 0 or not isinstance(data, dict):
        return
    target_url = str(data.get("url") or "").strip()
    if not target_url or target_url == "about:blank":
        return
    try:
        scroll_ratio = float(data.get("scrollRatio", 0.0) or 0.0)
    except Exception:
        scroll_ratio = 0.0
    try:
        set_web_scroll_position(
            _ADDON_DIR,
            target_card_id,
            target_url,
            max(0.0, min(scroll_ratio, 1.0)),
        )
    except Exception:
        pass


def _persist_current_web_state() -> None:
    try:
        target_card_id = int(_current_web_card_id) if _current_web_card_id is not None else 0
    except Exception:
        target_card_id = 0
    if _web_dock is None:
        _persist_web_url(target_card_id, _current_web_display_url())
        return
    current_url = _current_web_display_url()
    _persist_web_url(target_card_id, current_url)
    if not _remember_browser_card_scroll():
        return
    try:
        _web_dock._view.page().runJavaScript(
            "(function(){"
            "  if (window.incrementoGetProgressPayload) {"
            "    return window.incrementoGetProgressPayload();"
            "  }"
            "  return {url: window.location.href || '', scrollRatio: 0};"
            "})();",
            lambda data, card_id=target_card_id: _persist_web_scroll(card_id, data),
        )
    except Exception:
        pass


def _source_url_label(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return "Source"
    try:
        parsed = urlparse(raw)
        label = f"{parsed.netloc}{parsed.path or ''}"
        if parsed.fragment:
            label += f"#{parsed.fragment}"
        if not label:
            label = raw
    except Exception:
        label = raw
    label = label.strip() or raw
    return label if len(label) <= 72 else label[:69] + "..."


def web_citation(url: str | None = None) -> str:
    current_url = str(url or _current_web_display_url()).strip()
    if not current_url or not _current_web_card_id:
        return ""
    encoded_url = quote(current_url, safe="")
    label = (
        _source_url_label(current_url)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    cmd = f"incremento_open_web:{int(_current_web_card_id)}:{encoded_url}"
    return (
        f"<a onclick=\"pycmd('{cmd}'); return false;\" "
        f"style=\"cursor:pointer; color:#4a90d9; text-decoration:none;\">"
        f"{label}</a>"
    )


class _WebDockPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source):
        if not message.startswith(_PYCMD_BRIDGE):
            return
        msg = message[len(_PYCMD_BRIDGE) :]
        if msg.startswith(_MSG_SELECTION_STATE):
            try:
                data = json.loads(msg[len(_MSG_SELECTION_STATE) :])
                from . import add_card_dock as _add_card_dock_mod

                _add_card_dock_mod.update_selection_state(
                    "web",
                    has_text=bool(data.get("hasText")),
                )
            except Exception:
                pass
            return
        if msg.startswith(_MSG_FILL_FIELD):
            try:
                data = json.loads(msg[len(_MSG_FILL_FIELD) :])
                from . import add_card_dock as _add_card_dock_mod

                _add_card_dock_mod.fill_dock_field(
                    int(data["idx"]),
                    str(data.get("text") or ""),
                    include_pdf_citation=False,
                    citation_html=web_citation(data.get("url")),
                    source_link_kind="web",
                )
            except Exception:
                pass
            return
        if msg.startswith(_MSG_SNAPSHOT):
            try:
                data = json.loads(msg[len(_MSG_SNAPSHOT) :])
                _handle_web_snapshot(data)
            except Exception as exc:
                showInfo(f"Web snapshot failed:\n{exc}")
            return
        if msg.startswith(_MSG_PROGRESS):
            try:
                data = json.loads(msg[len(_MSG_PROGRESS) :])
                _persist_web_scroll(_current_web_card_id, data)
            except Exception:
                pass


class _WebInteractionFilter(QObject):
    def eventFilter(self, watched, event):
        global _web_snapshot_origin
        if _web_dock is None or not _web_snapshot_mode:
            return False
        try:
            if not _web_dock.isVisible():
                return False
            view = _web_dock._view
        except Exception:
            return False

        etype = event.type()
        if etype == QEvent.Type.KeyPress:
            try:
                if event.key() == Qt.Key.Key_Escape:
                    _set_web_snapshot_mode(False)
                    return True
            except Exception:
                return False
            return False

        if etype not in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseMove,
            QEvent.Type.MouseButtonRelease,
        ):
            return False

        try:
            global_pos = event.globalPosition().toPoint()
        except Exception:
            return False
        local_pos = view.mapFromGlobal(global_pos)
        if not view.rect().contains(local_pos):
            if etype == QEvent.Type.MouseMove and _web_snapshot_origin is not None:
                local_pos = QPoint(
                    max(0, min(local_pos.x(), view.rect().right())),
                    max(0, min(local_pos.y(), view.rect().bottom())),
                )
            else:
                return False

        if etype == QEvent.Type.MouseButtonPress:
            try:
                if event.button() != Qt.MouseButton.LeftButton:
                    return False
            except Exception:
                return False
            _web_snapshot_origin = local_pos
            _ensure_snapshot_band(view)
            _web_snapshot_shield.setGeometry(view.rect())
            _web_snapshot_shield.raise_()
            _web_snapshot_shield.show()
            _web_snapshot_overlay.setGeometry(
                QRect(_web_snapshot_origin, _web_snapshot_origin)
            )
            _web_snapshot_overlay.raise_()
            _web_snapshot_overlay.show()
            return True

        if etype == QEvent.Type.MouseMove:
            if _web_snapshot_origin is None:
                return False
            _ensure_snapshot_band(view)
            _web_snapshot_shield.setGeometry(view.rect())
            _web_snapshot_shield.raise_()
            _web_snapshot_shield.show()
            _web_snapshot_overlay.setGeometry(
                QRect(_web_snapshot_origin, local_pos).normalized()
            )
            _web_snapshot_overlay.raise_()
            _web_snapshot_overlay.show()
            return True

        if etype == QEvent.Type.MouseButtonRelease:
            try:
                if event.button() != Qt.MouseButton.LeftButton:
                    return False
            except Exception:
                return False
            if _web_snapshot_origin is None:
                return False
            rect = QRect(_web_snapshot_origin, local_pos).normalized().intersected(
                view.rect()
            )
            _web_snapshot_origin = None
            if _web_snapshot_overlay is not None:
                _web_snapshot_overlay.hide()
            current_url = _current_web_display_url()
            _set_web_snapshot_mode(False)
            if rect.width() < 6 or rect.height() < 6:
                return True
            try:
                pixmap = view.grab(rect)
            except Exception as exc:
                showInfo(f"Web snapshot failed:\n{exc}")
                return True
            if pixmap.isNull():
                showInfo("Web snapshot failed:\nCould not capture selected region.")
                return True
            try:
                _insert_snapshot_into_field(pixmap, current_url)
            except Exception as exc:
                showInfo(f"Web snapshot failed:\n{exc}")
            return True

        return False


def _build_web_bridge_js() -> str:
    script = """
window.pycmd = function(msg) {
  console.log(__PYCMD_PREFIX__ + msg);
};
(function() {
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
      url: window.location.href || '',
      scrollRatio: currentScrollRatio()
    };
  }

  function emitProgress() {
    window.pycmd(__MSG_PROGRESS__ + JSON.stringify(progressPayload()));
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
    window.pycmd(__MSG_SELECTION__ + JSON.stringify({source: 'web', hasText: true}));
  });

  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && window._incrementoWebSnapshotActive) {
      e.preventDefault();
      e.stopPropagation();
      setSnapshotActive(false);
      return;
    }
    if (!(e.metaKey || e.ctrlKey)) {
      return;
    }
    var map = { Digit1: 0, Digit2: 1, Digit3: 2, Digit4: 3 };
    var idx = Object.prototype.hasOwnProperty.call(map, e.code) ? map[e.code] : null;
    if (idx === null) {
      var n = parseInt(e.key, 10);
      if (!Number.isNaN(n) && n >= 1 && n <= 4) {
        idx = n - 1;
      }
    }
    if (idx === null) {
      return;
    }
    var sel = window.getSelection ? window.getSelection() : null;
    var text = sel ? sel.toString().trim() : '';
    if (!text) {
      return;
    }
    e.preventDefault();
    e.stopPropagation();
    window._incrementoLastSelection = text;
    window.pycmd(__MSG_FILL__ + JSON.stringify({
      idx: idx,
      text: text,
      url: window.location.href || ''
    }));
  }, true);

  document.addEventListener('mousedown', function(e) {
    if (!window._incrementoWebSnapshotActive || e.button !== 0) {
      return;
    }
    window._incrementoWebSnapshotStart = { x: e.clientX, y: e.clientY };
    drawBox(window._incrementoWebSnapshotStart, window._incrementoWebSnapshotStart);
    e.preventDefault();
    e.stopPropagation();
  }, true);

  document.addEventListener('mousemove', function(e) {
    if (!window._incrementoWebSnapshotActive || !window._incrementoWebSnapshotStart) {
      return;
    }
    drawBox(window._incrementoWebSnapshotStart, { x: e.clientX, y: e.clientY });
    e.preventDefault();
    e.stopPropagation();
  }, true);

  document.addEventListener('mouseup', function(e) {
    if (!window._incrementoWebSnapshotActive || !window._incrementoWebSnapshotStart || e.button !== 0) {
      return;
    }
    var start = window._incrementoWebSnapshotStart;
    var end = { x: e.clientX, y: e.clientY };
    var left = Math.min(start.x, end.x);
    var top = Math.min(start.y, end.y);
    var width = Math.abs(start.x - end.x);
    var height = Math.abs(start.y - end.y);
    window._incrementoWebSnapshotStart = null;
    setSnapshotActive(false);
    if (width < 6 || height < 6) {
      return;
    }
    window.pycmd(__MSG_SNAPSHOT__ + JSON.stringify({
      x: left,
      y: top,
      width: width,
      height: height,
      url: window.location.href || ''
    }));
    e.preventDefault();
    e.stopPropagation();
  }, true);

  window.addEventListener('scroll', scheduleProgress, { passive: true });
  window.addEventListener('resize', scheduleProgress);
  window.addEventListener('beforeunload', emitProgress);
  window.addEventListener('pagehide', emitProgress);
})();
"""
    return (
        script.replace("__PYCMD_PREFIX__", json.dumps(_PYCMD_BRIDGE))
        .replace("__MSG_SELECTION__", json.dumps(_MSG_SELECTION_STATE))
        .replace("__MSG_FILL__", json.dumps(_MSG_FILL_FIELD))
        .replace("__MSG_SNAPSHOT__", json.dumps(_MSG_SNAPSHOT))
        .replace("__MSG_PROGRESS__", json.dumps(_MSG_PROGRESS))
    )


def _current_web_display_url() -> str:
    if _web_dock is not None:
        try:
            current = (_web_dock._view.url().toString() or "").strip()
            if current and current != "about:blank":
                return current
        except Exception:
            pass
    return str(_current_web_home_url or "").strip()


def _current_selected_text() -> str:
    if _web_dock is None:
        return ""
    try:
        text = _web_dock._view.page().selectedText() or ""
        text = str(text).replace("\u2029", "\n").strip()
        if text:
            return text
    except Exception:
        pass
    return ""


def _bookmark_restore_state(current_url: str) -> dict:
    return _bookmark_restore_state_for_url(
        current_url,
        allow_bookmark=True,
        allow_scroll=True,
    )


def _bookmark_restore_state_for_url(
    current_url: str,
    *,
    allow_bookmark: bool,
    allow_scroll: bool,
) -> dict:
    progress = _web_progress_state()
    bookmark_url = str(progress.get("bookmark_url") or "").strip()
    bookmark_payload = progress.get("bookmark_payload") or {}
    bookmark = None
    if allow_bookmark and bookmark_url and bookmark_payload and current_url == bookmark_url:
        bookmark = bookmark_payload
    return {
        "rememberScroll": bool(allow_scroll and _remember_browser_card_scroll()),
        "scrollRatio": float(progress.get("scroll_ratio") or 0.0),
        "bookmark": bookmark,
    }


def _set_pending_web_restore(
    card_id: int,
    *,
    allow_bookmark: bool,
    allow_scroll: bool,
) -> None:
    global _pending_web_restore
    _pending_web_restore = {
        "card_id": int(card_id),
        "allow_bookmark": bool(allow_bookmark),
        "allow_scroll": bool(allow_scroll),
    }


def _apply_web_restore_state(
    current_url: str,
    *,
    allow_bookmark: bool,
    allow_scroll: bool,
) -> None:
    if _web_dock is None or not current_url or current_url == "about:blank":
        return
    payload = _bookmark_restore_state_for_url(
        current_url,
        allow_bookmark=allow_bookmark,
        allow_scroll=allow_scroll,
    )
    try:
        _web_dock._view.page().runJavaScript(
            "window.incrementoApplyRestoreState && "
            f"window.incrementoApplyRestoreState({json.dumps(payload)});"
        )
    except Exception:
        pass


def _save_web_bookmark() -> None:
    if _web_dock is None or _current_web_card_id is None:
        tooltip("Incremento: no browser card is currently open.")
        return
    try:
        target_card_id = int(_current_web_card_id)
    except Exception:
        tooltip("Incremento: no browser card is currently open.")
        return

    def _handle(payload) -> None:
        if not isinstance(payload, dict):
            tooltip("Incremento: couldn't place a bookmark here.")
            return
        current_url = str(payload.get("url") or "").strip()
        bookmark = payload.get("bookmark")
        if not current_url or not isinstance(bookmark, dict):
            tooltip("Incremento: couldn't place a bookmark here.")
            return
        try:
            set_web_bookmark(
                _ADDON_DIR,
                target_card_id,
                url=current_url,
                bookmark_payload=bookmark,
            )
        except Exception as exc:
            showInfo(f"Failed to save bookmark:\n{exc}")
            return
        _refresh_web_bookmark_button()
        tooltip("Incremento: bookmark saved.")

    try:
        _web_dock._view.page().runJavaScript(
            "window.incrementoCaptureBookmark && window.incrementoCaptureBookmark();",
            _handle,
        )
    except Exception as exc:
        showInfo(f"Failed to save bookmark:\n{exc}")


def _resolve_web_selection(callback) -> None:
    text = _current_selected_text()
    if text:
        callback(text)
        return
    if _web_dock is None:
        callback("")
        return
    try:
        _web_dock._view.page().runJavaScript(
            "(function(){ return (window._incrementoLastSelection || "
            "(window.getSelection && window.getSelection().toString()) || '').trim(); })();",
            lambda text: callback(str(text or "").strip()),
        )
    except Exception:
        callback("")


def _update_native_selection_state() -> None:
    try:
        from . import add_card_dock as _add_card_dock_mod

        _add_card_dock_mod.update_selection_state(
            "web",
            text=_current_selected_text(),
        )
    except Exception:
        pass


def _extract_web_selection_to_field(idx: int) -> None:
    def _apply(text: str) -> None:
        if not text:
            tooltip("Select some text first.")
            return
        try:
            from . import add_card_dock as _add_card_dock_mod

            _add_card_dock_mod.fill_dock_field(
                idx,
                text,
                include_pdf_citation=False,
                citation_html=web_citation(),
                source_link_kind="web",
            )
        except Exception as exc:
            showInfo(f"Web extraction failed:\n{exc}")

    _resolve_web_selection(_apply)


def _get_add_card_field_names() -> list[str]:
    from . import add_card_dock as _add_card_dock_mod

    _add_card_dock_mod.open_add_card_dock()
    try:
        dock = _add_card_dock_mod.get_add_card_dock()
        if dock:
            note = dock.widget().editor.note
            if note:
                field_names = [f["name"] for f in note.note_type()["flds"]]
                if field_names:
                    return field_names
    except Exception:
        pass
    return [f"Field {i + 1}" for i in range(4)]


def _prompt_extract_target_field() -> int:
    field_names = _get_add_card_field_names()
    picker = QDialog(mw)
    picker.setWindowTitle("Extract selection into field")
    picker.setFixedWidth(340)
    layout = QVBoxLayout(picker)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(0)

    layout.addWidget(QLabel("Insert selected text into:"))
    layout.addSpacing(12)

    chosen_idx = [-1]

    def _make_handler(idx):
        def _handler():
            chosen_idx[0] = idx
            picker.accept()

        return _handler

    for i, name in enumerate(field_names):
        btn = QPushButton(name)
        btn.setStyleSheet("text-align: left; padding: 7px 12px;")
        btn.clicked.connect(_make_handler(i))
        layout.addWidget(btn)
        layout.addSpacing(4)

    layout.addSpacing(8)
    cancel_btn = QPushButton("Cancel")
    cancel_btn.clicked.connect(picker.reject)
    layout.addWidget(cancel_btn)

    if not picker.exec():
        return -1
    return chosen_idx[0]


def _extract_web_selection_with_picker() -> None:
    target_idx = _prompt_extract_target_field()
    if target_idx < 0:
        return
    _extract_web_selection_to_field(target_idx)


def _ensure_snapshot_band(view) -> None:
    global _web_snapshot_shield, _web_snapshot_overlay
    if _web_snapshot_shield is None or _web_snapshot_shield.parent() is not view:
        _web_snapshot_shield = QWidget(view)
        _web_snapshot_shield.setCursor(Qt.CursorShape.CrossCursor)
        _web_snapshot_shield.setStyleSheet("background: rgba(37,99,235,0.02);")
        _web_snapshot_shield.hide()
    if _web_snapshot_overlay is None or _web_snapshot_overlay.parent() is not _web_snapshot_shield:
        _web_snapshot_overlay = QWidget(_web_snapshot_shield)
        _web_snapshot_overlay.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        _web_snapshot_overlay.setStyleSheet(
            "border: 2px solid rgba(37,99,235,0.95);"
            "background: rgba(37,99,235,0.22);"
        )
        _web_snapshot_overlay.hide()


def _set_web_snapshot_mode(active: bool) -> None:
    global _web_snapshot_mode, _web_snapshot_origin, _web_snapshot_override_cursor
    _web_snapshot_mode = bool(active)
    _web_snapshot_origin = None
    if _web_dock is not None:
        try:
            _ensure_snapshot_band(_web_dock._view)
        except Exception:
            pass
    if _web_snapshot_shield is not None:
        try:
            _web_snapshot_shield.hide()
        except Exception:
            pass
    if _web_snapshot_overlay is not None:
        try:
            _web_snapshot_overlay.hide()
        except Exception:
            pass
    if _web_dock is not None:
        try:
            _web_dock._view.setCursor(
                Qt.CursorShape.CrossCursor
                if _web_snapshot_mode
                else Qt.CursorShape.ArrowCursor
            )
        except Exception:
            pass
        try:
            _web_dock._view.unsetCursor() if not _web_snapshot_mode else None
        except Exception:
            pass
        if _web_snapshot_mode and _web_snapshot_shield is not None:
            try:
                _web_snapshot_shield.setGeometry(_web_dock._view.rect())
                _web_snapshot_shield.raise_()
                _web_snapshot_shield.show()
            except Exception:
                pass
        try:
            _web_dock._snapshot_btn.setText(
                "Drag to Capture" if _web_snapshot_mode else "Snapshot"
            )
            _web_dock._snapshot_btn.setStyleSheet(
                (
                    "font-weight: bold;"
                    "color: white;"
                    "background: rgba(37,99,235,0.92);"
                    "border: 1px solid rgba(29,78,216,1.0);"
                    "border-radius: 4px;"
                    "padding: 0 8px;"
                    if _web_snapshot_mode
                    else ""
                )
            )
        except Exception:
            pass
    app = QApplication.instance()
    if app is not None:
        try:
            if _web_snapshot_mode and not _web_snapshot_override_cursor:
                app.setOverrideCursor(Qt.CursorShape.CrossCursor)
                _web_snapshot_override_cursor = True
            elif not _web_snapshot_mode and _web_snapshot_override_cursor:
                app.restoreOverrideCursor()
                _web_snapshot_override_cursor = False
        except Exception:
            _web_snapshot_override_cursor = False


def _current_web_source_rows() -> list[dict]:
    if _current_web_card_id is None:
        return []
    current_url = _current_web_display_url()
    if not current_url:
        return []
    try:
        return get_web_card_sources(_ADDON_DIR, int(_current_web_card_id), current_url)
    except Exception:
        return []


def _refresh_web_cards_panel() -> None:
    if _web_dock is None:
        return
    current_url = _current_web_display_url()
    rows = _current_web_source_rows()
    count = len(rows)
    try:
        _web_dock._cards_btn.setText(f"Cards {count}")
        _web_dock._cards_btn.setVisible(count > 0)
    except Exception:
        pass
    if count <= 0:
        try:
            _web_dock._cards_panel.hide()
            _web_dock._cards_panel.setHtml("")
        except Exception:
            pass
        return
    html = [
        "<div style='font-family:sans-serif;font-size:12px;line-height:1.45'>",
        "<div style='font-weight:bold;color:rgb(74,144,217);margin-bottom:6px'>",
        "Cards created at this URL",
        "</div>",
        (
            "<div style='color:#888;margin-bottom:8px;word-break:break-all'>"
            + current_url.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            + "</div>"
        ),
    ]
    for row in rows:
        excerpt = str(row.get("excerpt") or "").strip()
        safe_excerpt = (
            excerpt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            or "<i style='color:#888'>No text</i>"
        )
        html.append(
            "<div style='margin-bottom:6px;padding:6px 8px;"
            "background:rgba(74,144,217,0.08);border-left:3px solid rgba(74,144,217,0.55)'>"
            f"<a href='inc://card/{int(row['note_id'])}' "
            "style='text-decoration:none;color:inherit'>"
            f"{safe_excerpt}</a></div>"
        )
    html.append("</div>")
    try:
        _web_dock._cards_panel.setHtml("".join(html))
    except Exception:
        pass


def _toggle_web_cards_panel() -> None:
    if _web_dock is None:
        return
    rows = _current_web_source_rows()
    if not rows:
        tooltip("Incremento: no cards recorded for this URL yet.")
        return
    _refresh_web_cards_panel()
    try:
        visible = _web_dock._cards_panel.isVisible()
        _web_dock._cards_panel.setVisible(not visible)
    except Exception:
        pass


def _insert_snapshot_into_field(pixmap: QPixmap, current_url: str) -> None:
    from . import add_card_dock as _add_card_dock_mod

    fd, tmp_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        if not pixmap.save(tmp_path, "PNG"):
            raise RuntimeError("Could not encode snapshot image.")
        media_filename = mw.col.media.add_file(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    _add_card_dock_mod.open_add_card_dock()
    field_names = []
    try:
        dock = _add_card_dock_mod.get_add_card_dock()
        if dock:
            note = dock.widget().editor.note
            if note:
                field_names = [f["name"] for f in note.note_type()["flds"]]
    except Exception:
        pass
    if not field_names:
        field_names = [f"Field {i + 1}" for i in range(4)]

    scaled = pixmap
    if scaled.width() > 300:
        scaled = scaled.scaledToWidth(300, Qt.TransformationMode.SmoothTransformation)
    if scaled.height() > 180:
        scaled = scaled.scaledToHeight(180, Qt.TransformationMode.SmoothTransformation)

    picker = QDialog(mw)
    picker.setWindowTitle("Insert snapshot into field")
    picker.setFixedWidth(340)
    layout = QVBoxLayout(picker)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(0)

    preview_lbl = QLabel()
    preview_lbl.setPixmap(scaled)
    preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(preview_lbl)

    layout.addSpacing(14)
    layout.addWidget(QLabel("Insert image into:"))
    layout.addSpacing(8)

    chosen_idx = [-1]

    def _make_handler(idx):
        def _handler():
            chosen_idx[0] = idx
            picker.accept()

        return _handler

    for i, name in enumerate(field_names):
        btn = QPushButton(name)
        btn.setStyleSheet("text-align: left; padding: 7px 12px;")
        btn.clicked.connect(_make_handler(i))
        layout.addWidget(btn)
        layout.addSpacing(4)

    layout.addSpacing(8)
    cancel_btn = QPushButton("Cancel")
    cancel_btn.clicked.connect(picker.reject)
    layout.addWidget(cancel_btn)

    if not picker.exec() or chosen_idx[0] < 0:
        return

    citation = web_citation(current_url)
    html = f'<img src="{media_filename}">'
    _add_card_dock_mod.fill_dock_field(
        chosen_idx[0],
        html,
        include_pdf_citation=False,
        citation_html=citation,
        source_link_kind="web",
    )


def _handle_web_snapshot(data: dict) -> None:
    if _web_dock is None:
        return
    try:
        x = max(0, int(round(float(data.get("x") or 0))))
        y = max(0, int(round(float(data.get("y") or 0))))
        width = max(0, int(round(float(data.get("width") or 0))))
        height = max(0, int(round(float(data.get("height") or 0))))
    except Exception as exc:
        raise RuntimeError(f"Invalid snapshot bounds: {exc}") from exc
    if width < 6 or height < 6:
        return
    current_url = str(data.get("url") or _current_web_display_url()).strip()
    try:
        pixmap = _web_dock._view.grab()
    except Exception as exc:
        raise RuntimeError(f"Could not capture web view: {exc}") from exc
    if pixmap.isNull():
        raise RuntimeError("Could not capture web view.")
    try:
        dpr = float(pixmap.devicePixelRatio())
    except Exception:
        dpr = 1.0
    crop = pixmap.copy(
        int(round(x * dpr)),
        int(round(y * dpr)),
        int(round(width * dpr)),
        int(round(height * dpr)),
    )
    if crop.isNull():
        raise RuntimeError("The selected region was outside the current viewport.")
    try:
        crop.setDevicePixelRatio(dpr)
    except Exception:
        pass
    _insert_snapshot_into_field(crop, current_url)


def _toggle_snapshot_mode() -> None:
    _set_web_snapshot_mode(not _web_snapshot_mode)


def _open_result_link(qurl) -> None:
    s = qurl.toString() if hasattr(qurl, "toString") else str(qurl)
    if not s.startswith("inc://card/"):
        return
    try:
        note_id = int(s.rsplit("/", 1)[1])
    except Exception:
        return
    try:
        from aqt import dialogs

        b = dialogs.open("Browser", mw)
        b.search_for(f"nid:{note_id}")
    except Exception:
        pass


def _build_web_dock():
    global _web_dock, _web_profile, _web_interaction_filter, _web_shortcuts_registered

    from PyQt6.QtWebEngineCore import (
        QWebEngineProfile as _WEProf,
        QWebEngineSettings as _WES,
    )

    dock = QDockWidget("Web", mw)
    dock.setObjectName("incremento_web_dock")
    dock.setMinimumWidth(600)

    container = QWidget()
    vbox = QVBoxLayout(container)
    vbox.setContentsMargins(0, 0, 0, 0)
    vbox.setSpacing(0)

    view = QWebEngineView(container)

    if _web_profile is None:
        _web_profile = _WEProf("incremento_web")
        _web_profile.setPersistentStoragePath(
            os.path.join(_ADDON_DIR, "user_files", "web_profile")
        )
        _web_profile.setPersistentCookiesPolicy(
            _WEProf.PersistentCookiesPolicy.ForcePersistentCookies
        )
        _web_profile.setHttpUserAgent(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        _web_profile.settings().setAttribute(
            _WES.WebAttribute.PlaybackRequiresUserGesture, False
        )

    _page = _WebDockPage(_web_profile)
    view.setPage(_page)

    vbox.addWidget(view, 1)

    ctrl = QWidget(container)
    ctrl_layout = QHBoxLayout(ctrl)
    ctrl_layout.setContentsMargins(8, 4, 8, 4)
    ctrl_layout.setSpacing(6)

    url_lbl = QLabel("")
    url_lbl.setStyleSheet("font-family: monospace; font-size: 11px; color: #888;")
    url_lbl.setWordWrap(False)
    url_lbl.setMaximumWidth(360)
    ctrl_layout.addWidget(url_lbl, 1)

    add_card_btn = QPushButton("+ Add Card")
    ctrl_layout.addWidget(add_card_btn)

    extract_btn = QPushButton("Extract")
    extract_btn.setToolTip(
        "Copy the current text selection into a field in the Add Card dock."
    )
    ctrl_layout.addWidget(extract_btn)

    snapshot_btn = QPushButton("Snapshot")
    snapshot_btn.setToolTip(
        "Capture an image from the current viewport, like the PDF snapshot tool."
    )
    ctrl_layout.addWidget(snapshot_btn)

    bookmark_btn = QPushButton("Bookmark")
    ctrl_layout.addWidget(bookmark_btn)

    cards_btn = QPushButton("Cards 0")
    cards_btn.setVisible(False)
    ctrl_layout.addWidget(cards_btn)

    home_btn = QPushButton("Home")
    home_btn.setFixedWidth(70)
    ctrl_layout.addWidget(home_btn)

    track_cb = QCheckBox("Track via Chrome extension")
    track_cb.setChecked(bool(_track_web_window_with_extension))
    track_cb.setToolTip(
        "When checked, opening this page externally lets the Incremento Companion "
        "extension keep the web card synced to the latest page visited in that tab."
    )
    ctrl_layout.addWidget(track_cb)

    window_btn = QPushButton("Open in Window")
    ctrl_layout.addWidget(window_btn)

    vbox.addWidget(ctrl)

    cards_panel = QTextBrowser(container)
    cards_panel.setOpenLinks(False)
    cards_panel.anchorClicked.connect(_open_result_link)
    cards_panel.setVisible(False)
    cards_panel.setMaximumHeight(220)
    cards_panel.setStyleSheet(
        "border-top: 1px solid rgba(120,120,120,0.25);"
        "background: rgba(74,144,217,0.04);"
    )
    vbox.addWidget(cards_panel)

    dock.setWidget(container)
    mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    dock._view = view
    dock._url_lbl = url_lbl
    dock._track_cb = track_cb
    dock._extract_btn = extract_btn
    dock._snapshot_btn = snapshot_btn
    dock._bookmark_btn = bookmark_btn
    dock._cards_btn = cards_btn
    dock._cards_panel = cards_panel

    if _web_interaction_filter is None:
        _web_interaction_filter = _WebInteractionFilter(mw)
    app = QApplication.instance()
    if app is not None:
        app.installEventFilter(_web_interaction_filter)

    def _on_url_changed(qurl):
        url_str = qurl.toString()
        display = url_str if len(url_str) <= 80 else url_str[:77] + "..."
        try:
            url_lbl.setText(display)
        except RuntimeError:
            pass
        _persist_web_url(_current_web_card_id, url_str)
        _refresh_web_cards_panel()
        _refresh_web_bookmark_button()

    def _on_load_finished(ok):
        global _pending_web_restore
        if not ok or _current_web_card_id is None:
            return
        url_str = view.url().toString()
        _persist_web_url(_current_web_card_id, url_str)
        _set_web_snapshot_mode(False)
        try:
            view.page().runJavaScript(_build_web_bridge_js())
        except Exception:
            pass
        restore_cfg = _pending_web_restore or {}
        if int(restore_cfg.get("card_id") or 0) == int(_current_web_card_id):
            QTimer.singleShot(
                0,
                lambda url=url_str, cfg=dict(restore_cfg): _apply_web_restore_state(
                    url,
                    allow_bookmark=bool(cfg.get("allow_bookmark", True)),
                    allow_scroll=bool(cfg.get("allow_scroll", True)),
                ),
            )
        _pending_web_restore = None
        _refresh_web_cards_panel()
        _refresh_web_bookmark_button()

    def _on_selection_changed():
        _update_native_selection_state()

    view.urlChanged.connect(_on_url_changed)
    view.loadFinished.connect(_on_load_finished)
    view.page().selectionChanged.connect(_on_selection_changed)
    qconnect(home_btn.clicked, _web_go_home)
    qconnect(extract_btn.clicked, _extract_web_selection_with_picker)
    qconnect(snapshot_btn.clicked, _toggle_snapshot_mode)
    qconnect(bookmark_btn.clicked, _save_web_bookmark)
    qconnect(cards_btn.clicked, _toggle_web_cards_panel)
    qconnect(window_btn.clicked, _open_web_in_window)
    qconnect(track_cb.toggled, _on_track_web_window_toggled)

    def _open_add_card():
        from . import add_card_dock as _add_card_dock_mod

        _add_card_dock_mod.open_add_card_dock()

    qconnect(add_card_btn.clicked, _open_add_card)

    if not _web_shortcuts_registered:
        for idx in range(4):
            for prefix in ("Ctrl", "Meta"):
                sc = QShortcut(QKeySequence(f"{prefix}+{idx + 1}"), mw)
                sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
                sc.activated.connect(
                    lambda idx=idx: (
                        _extract_web_selection_to_field(idx)
                        if _web_dock is not None and _web_dock.isVisible()
                        else None
                    )
                )
                _web_shortcuts.append(sc)
        esc = QShortcut(QKeySequence("Escape"), mw)
        esc.setContext(Qt.ShortcutContext.ApplicationShortcut)
        esc.activated.connect(
            lambda: _set_web_snapshot_mode(False) if _web_snapshot_mode else None
        )
        _web_shortcuts.append(esc)
        _web_shortcuts_registered = True

    _web_dock = dock
    _refresh_web_bookmark_button()
    return dock


def _on_track_web_window_toggled(checked: bool) -> None:
    global _track_web_window_with_extension
    _track_web_window_with_extension = bool(checked)


def _open_web_in_window() -> None:
    if _current_web_card_id is None:
        tooltip("Incremento: no web card is currently open.")
        return

    current_url = _current_web_display_url()
    if not current_url:
        tooltip("Incremento: this web card has no valid URL.")
        return

    track_enabled = False
    if _web_dock is not None:
        try:
            track_enabled = bool(_web_dock._track_cb.isChecked())
        except Exception:
            track_enabled = False

    open_url = build_external_web_url(
        current_url,
        card_id=int(_current_web_card_id),
        track_with_extension=track_enabled,
    )
    try:
        set_web_url(_ADDON_DIR, _current_web_card_id, current_url)
    except Exception:
        pass

    try:
        ok = bool(QDesktopServices.openUrl(QUrl(open_url)))
    except Exception:
        ok = False
    if not ok:
        tooltip("Incremento: failed to open system browser.")
        return

    if track_enabled:
        tooltip(
            "Incremento: browser tracking enabled for this web card tab "
            "(requires the Incremento Companion extension)."
        )


def _web_go_home() -> None:
    if _web_dock is None or not _current_web_home_url:
        return
    try:
        _web_dock._view.load(QUrl(_current_web_home_url))
    except (RuntimeError, AttributeError):
        pass


def show_web_in_dock(
    card_id: int,
    home_url: str,
    last_url: str,
    *,
    prefer_bookmark: bool = True,
    restore_scroll: bool = True,
) -> None:
    global _web_dock, _current_web_card_id, _current_web_home_url, _pending_web_restore

    _current_web_card_id = card_id
    _current_web_home_url = home_url

    if _web_dock is None:
        _build_web_dock()
    else:
        try:
            _web_dock.widget()
        except RuntimeError:
            _web_dock = None
            _build_web_dock()

    progress = _web_progress_state(card_id)
    bookmark_url = str(progress.get("bookmark_url") or "").strip()
    load_url = (
        bookmark_url
        if prefer_bookmark and bookmark_url
        else (last_url if last_url else home_url)
    )
    current_url = ""
    try:
        current_url = (_web_dock._view.url().toString() or "").strip()
    except Exception:
        current_url = ""
    _web_dock.show()
    _web_dock.raise_()
    _set_web_snapshot_mode(False)
    try:
        _web_dock._cards_panel.hide()
        _web_dock._cards_panel.setHtml("")
        _web_dock._cards_btn.setVisible(False)
        _web_dock._cards_btn.setText("Cards 0")
    except Exception:
        pass
    _refresh_web_bookmark_button()
    _set_pending_web_restore(
        card_id,
        allow_bookmark=prefer_bookmark,
        allow_scroll=restore_scroll,
    )
    if load_url and current_url != load_url:
        _web_dock._view.load(QUrl(load_url))
    elif load_url:
        _apply_web_restore_state(
            load_url,
            allow_bookmark=prefer_bookmark,
            allow_scroll=restore_scroll,
        )
        _pending_web_restore = None
    else:
        _pending_web_restore = None


def open_web_location(card_id: int, target_url: str) -> bool:
    try:
        card = mw.col.get_card(int(card_id))
        note = mw.col.get_note(card.nid)
        home_url = note["URL"]
    except Exception:
        return False
    target = str(target_url or "").strip()
    if not target:
        target = get_web_url(_ADDON_DIR, int(card_id)) or home_url
    try:
        set_web_url(_ADDON_DIR, int(card_id), target)
    except Exception:
        pass
    show_web_in_dock(
        int(card_id),
        home_url,
        target,
        prefer_bookmark=False,
        restore_scroll=False,
    )
    return True


def sync_external_web_url(card_id: int, url: str) -> bool:
    """If this web card is currently open, load the latest externally synced URL."""
    global _web_dock

    try:
        target_card_id = int(card_id)
    except Exception:
        return False
    target_url = str(url or "").strip()
    if target_card_id <= 0 or not target_url:
        return False
    if _current_web_card_id != target_card_id:
        return False
    if _web_dock is None:
        return False

    try:
        current_url = (_web_dock._view.url().toString() or "").strip()
    except Exception:
        current_url = ""
    if current_url == target_url:
        return False

    try:
        _set_pending_web_restore(
            target_card_id,
            allow_bookmark=False,
            allow_scroll=False,
        )
        _web_dock._view.load(QUrl(target_url))
        return True
    except Exception:
        return False


def on_web_question_shown(card) -> None:
    global _web_dock
    try:
        if card is None:
            return
        try:
            note = mw.col.get_note(card.nid)
            model = mw.col.models.get(note.mid)
        except Exception:
            return
        if model is None or model.get("name") != WEB_NOTE_TYPE:
            if _web_dock is not None:
                _persist_current_web_state()
                try:
                    _web_dock.hide()
                except RuntimeError:
                    _web_dock = None
            return
        try:
            home_url = note["URL"]
        except (KeyError, TypeError):
            return
        if not home_url:
            return
        last_url = get_web_url(_ADDON_DIR, card.id)
        show_web_in_dock(card.id, home_url, last_url)
    except Exception as e:
        print(f"[Incremento] on_web_question_shown error: {e}")


def on_web_reviewer_will_end() -> None:
    _set_web_snapshot_mode(False)
    _persist_current_web_state()
    if _web_dock is not None:
        try:
            _web_dock.hide()
        except RuntimeError:
            pass


def on_add_cards_did_add_note(note) -> None:
    if _current_web_card_id is None or _web_dock is None:
        return
    try:
        if not _web_dock.isVisible():
            return
    except Exception:
        return
    current_url = _current_web_display_url()
    if not current_url:
        return
    parts = []
    for field in (note.fields or [])[:2]:
        plain = re.sub(r"<[^>]+>", "", field).strip()[:120]
        if plain:
            parts.append(plain)
    excerpt = " / ".join(parts)[:200]
    try:
        add_web_card_source(
            _ADDON_DIR,
            int(_current_web_card_id),
            current_url,
            note.id,
            excerpt,
        )
    except Exception:
        return
    _refresh_web_cards_panel()
    try:
        if _web_dock._cards_panel.isVisible():
            _web_dock._cards_panel.show()
    except Exception:
        pass


def sync_web_note_type() -> None:
    try:
        ensure_web_note_type(mw.col)
    except Exception:
        pass


def add_web_function() -> None:
    """Incremento -> Add Content -> Web Page"""
    deck_names = [d.name for d in mw.col.decks.all_names_and_ids()]
    from .add_web_dialog import AddWebDialog

    dlg = AddWebDialog(deck_names, default_deck="Topics", parent=mw)
    if not dlg.exec():
        return
    url = dlg.url
    if not url:
        showInfo("Please enter a URL.")
        return
    title = dlg.title or url
    try:
        add_web_card(mw.col, url, title, dlg.deck_name, tags=dlg.tags)
        mw.col.reset()
        tooltip(f"Web card '{title}' added to {dlg.deck_name}.")
    except Exception as e:
        showInfo(f"Failed to add web card:\n{e}")


def get_selected_text(callback) -> None:
    _resolve_web_selection(callback)
