from __future__ import annotations

import json
import os

from aqt import mw
from aqt.qt import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    Qt,
    QUrl,
    qconnect,
)
from aqt.utils import showInfo
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView

try:
    from ..backend.epub_manager import (
        EPUB_FILE_FIELD,
        EPUB_NOTE_TYPE,
        get_epub_progress,
        get_epub_section_path,
        load_epub_metadata,
        set_epub_progress,
        ensure_epub_note_type,
    )
except ImportError:
    from epub_manager import (  # type: ignore
        EPUB_FILE_FIELD,
        EPUB_NOTE_TYPE,
        get_epub_progress,
        get_epub_section_path,
        load_epub_metadata,
        set_epub_progress,
        ensure_epub_note_type,
    )
try:
    from ..backend.epub_highlights import load_highlights, add_highlight, remove_highlight
except ImportError:
    from epub_highlights import load_highlights, add_highlight, remove_highlight  # type: ignore
try:
    from ..backend.db import add_epub_card_source, get_epub_card_sources, get_epub_section_card_counts
except ImportError:
    from db import add_epub_card_source, get_epub_card_sources, get_epub_section_card_counts  # type: ignore


_ADDON_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)

_epub_dock = None
_current_epub_card_id: int | None = None
_current_epub_filename: str | None = None
_current_epub_section_index = 0
_current_epub_scroll_ratio = 0.0
_current_epub_finished = False
_last_selection_meta: dict[str, object] = {}
_pending_focus_offset = -1
_pending_restore_ratio = 0.0
_pending_search_query = ""
_pending_explicit_navigation = False

_cb_open_add_card_dock = None
_cb_fill_dock_field = None
_cb_get_add_card_dock = None

_PYCMD_BRIDGE = "__incremento_epub__:"
_MSG_FILL_FIELD = "incremento_epub_fill_field:"
_MSG_HL_ADD = "incremento_epub_hl_add:"
_MSG_HL_DEL = "incremento_epub_hl_del:"
_MSG_PROGRESS = "incremento_epub_progress:"
_MSG_SELECTION_STATE = "incremento_selection_state:"


def register_add_card_callbacks(open_fn, fill_fn, get_dock_fn) -> None:
    global _cb_open_add_card_dock, _cb_fill_dock_field, _cb_get_add_card_dock
    _cb_open_add_card_dock = open_fn
    _cb_fill_dock_field = fill_fn
    _cb_get_add_card_dock = get_dock_fn


def epub_citation() -> str:
    if not _current_epub_card_id or not _current_epub_filename:
        return ""
    try:
        meta = load_epub_metadata(_ADDON_DIR, _current_epub_filename)
        sections = meta.get("sections") or []
        section = sections[_current_epub_section_index] if 0 <= _current_epub_section_index < len(sections) else None
        title = str((section or {}).get("title") or f"Section {_current_epub_section_index + 1}")
    except Exception:
        title = f"Section {_current_epub_section_index + 1}"
    start_offset = int(_last_selection_meta.get("startOffset", -1) or -1)
    cmd = f"incremento_open_epub:{int(_current_epub_card_id)}:{int(_current_epub_section_index)}:{start_offset}"
    return (
        f"<a onclick=\"pycmd('{cmd}'); return false;\" "
        f"style=\"cursor:pointer; color:#4a90d9; text-decoration:none;\">"
        f"{title}</a>"
    )


class _EpubDockPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source):
        del level, line, source
        if not message.startswith(_PYCMD_BRIDGE):
            return
        msg = message[len(_PYCMD_BRIDGE) :]
        if msg.startswith(_MSG_SELECTION_STATE):
            try:
                data = json.loads(msg[len(_MSG_SELECTION_STATE) :])
                from . import add_card_dock as _add_card_dock_mod

                _add_card_dock_mod.update_selection_state(
                    str(data.get("source") or "epub"),
                    has_text=bool(data.get("hasText")),
                )
            except Exception:
                pass
            return
        if msg.startswith(_MSG_FILL_FIELD):
            try:
                data = json.loads(msg[len(_MSG_FILL_FIELD) :])
                _on_epub_selection(
                    int(data.get("idx", 0)),
                    str(data.get("text") or ""),
                    int(data.get("startOffset", -1) or -1),
                    int(data.get("endOffset", -1) or -1),
                )
            except Exception as exc:
                print(f"[Incremento] epub_dock fill failed: {exc}")
            return
        if msg.startswith(_MSG_HL_ADD):
            try:
                data = json.loads(msg[len(_MSG_HL_ADD) :])
                add_highlight(_ADDON_DIR, int(data["cardId"]), data["highlight"])
            except Exception as exc:
                print(f"[Incremento] epub_dock highlight add failed: {exc}")
            return
        if msg.startswith(_MSG_HL_DEL):
            try:
                data = json.loads(msg[len(_MSG_HL_DEL) :])
                remove_highlight(_ADDON_DIR, int(data["cardId"]), str(data["id"]))
            except Exception as exc:
                print(f"[Incremento] epub_dock highlight remove failed: {exc}")
            return
        if msg.startswith(_MSG_PROGRESS):
            try:
                data = json.loads(msg[len(_MSG_PROGRESS) :])
                _record_progress(
                    int(data.get("sectionIndex", _current_epub_section_index) or 0),
                    float(data.get("scrollRatio", 0.0) or 0.0),
                )
            except Exception:
                pass


def _build_page_script(
    *,
    card_id: int,
    section_index: int,
    scroll_ratio: float,
    focus_offset: int,
    search_query: str,
    highlights: list[dict],
) -> str:
    state = {
        "cardId": int(card_id),
        "sectionIndex": int(section_index),
        "scrollRatio": max(0.0, min(float(scroll_ratio), 1.0)),
        "focusOffset": int(focus_offset),
        "searchQuery": str(search_query or ""),
        "highlights": highlights,
    }
    return f"""
    (function() {{
      const STATE = {json.dumps(state)};
      const BRIDGE = {json.dumps(_PYCMD_BRIDGE)};
      function send(msg) {{
        console.log(BRIDGE + msg);
      }}
      function normText(text) {{
        return String(text || '').replace(/\\s+/g, ' ').trim();
      }}
      function ensureStyle() {{
        if (document.getElementById('incremento-epub-style')) return;
        const style = document.createElement('style');
        style.id = 'incremento-epub-style';
        style.textContent = `
          span.incremento-epub-highlight {{
            background: rgba(255, 225, 120, 0.75);
            border-radius: 2px;
            cursor: pointer;
          }}
        `;
        document.head.appendChild(style);
      }}
      function textNodes() {{
        const root = document.body || document.documentElement;
        if (!root) return [];
        const walker = document.createTreeWalker(
          root,
          NodeFilter.SHOW_TEXT,
          {{
            acceptNode(node) {{
              return node.nodeValue && node.nodeValue.length
                ? NodeFilter.FILTER_ACCEPT
                : NodeFilter.FILTER_REJECT;
            }},
          }}
        );
        const nodes = [];
        while (walker.nextNode()) {{
          nodes.push(walker.currentNode);
        }}
        return nodes;
      }}
      function pointFromOffset(target) {{
        let remain = Math.max(0, Number(target) || 0);
        const nodes = textNodes();
        for (const node of nodes) {{
          const len = node.nodeValue.length;
          if (remain <= len) {{
            return {{ node, offset: remain }};
          }}
          remain -= len;
        }}
        if (nodes.length) {{
          const last = nodes[nodes.length - 1];
          return {{ node: last, offset: last.nodeValue.length }};
        }}
        return null;
      }}
      function offsetFromPoint(node, offset) {{
        let total = 0;
        for (const textNode of textNodes()) {{
          if (textNode === node) {{
            return total + Math.max(0, Math.min(Number(offset) || 0, textNode.nodeValue.length));
          }}
          total += textNode.nodeValue.length;
        }}
        return total;
      }}
      function unwrapHighlight(node) {{
        if (!node || !node.parentNode) return;
        while (node.firstChild) {{
          node.parentNode.insertBefore(node.firstChild, node);
        }}
        node.remove();
      }}
      function applyHighlight(hl) {{
        const start = pointFromOffset(hl.startOffset);
        const end = pointFromOffset(hl.endOffset);
        if (!start || !end) return false;
        if (hl.endOffset <= hl.startOffset) return false;
        const range = document.createRange();
        range.setStart(start.node, Math.min(start.offset, start.node.nodeValue.length));
        range.setEnd(end.node, Math.min(end.offset, end.node.nodeValue.length));
        if (range.collapsed) return false;
        const wrapper = document.createElement('span');
        wrapper.className = 'incremento-epub-highlight';
        wrapper.dataset.id = String(hl.id || '');
        wrapper.dataset.color = String(hl.color || 'yellow');
        wrapper.title = 'Click to remove highlight';
        const fragment = range.extractContents();
        wrapper.appendChild(fragment);
        range.insertNode(wrapper);
        return true;
      }}
      function selectionMeta() {{
        const sel = window.getSelection ? window.getSelection() : null;
        if (!sel || !sel.rangeCount) return null;
        const range = sel.getRangeAt(0);
        if (range.collapsed) return null;
        const text = normText(sel.toString());
        if (!text) return null;
        return {{
          text,
          startOffset: offsetFromPoint(range.startContainer, range.startOffset),
          endOffset: offsetFromPoint(range.endContainer, range.endOffset),
        }};
      }}
      function reportSelection() {{
        const meta = selectionMeta();
        if (!meta) return;
        window._lastEpubSelection = meta.text;
        window._lastEpubSelectionMeta = meta;
        send('incremento_selection_state:' + JSON.stringify({{ source: 'epub', hasText: true }}));
      }}
      function reportProgress() {{
        const doc = document.documentElement || document.body;
        const maxScroll = Math.max(0, ((doc && doc.scrollHeight) || 0) - window.innerHeight);
        const ratio = maxScroll > 0 ? Math.max(0, Math.min(window.scrollY / maxScroll, 1)) : 0;
        send('incremento_epub_progress:' + JSON.stringify({{
          cardId: STATE.cardId,
          sectionIndex: STATE.sectionIndex,
          scrollRatio: ratio,
        }}));
      }}
      function clearSelection() {{
        const sel = window.getSelection ? window.getSelection() : null;
        if (sel) {{
          sel.removeAllRanges();
        }}
      }}
      window.incrementoAddEpubHighlight = function() {{
        const meta = selectionMeta();
        if (!meta) return false;
        const hl = {{
          id: 'hl-' + Date.now().toString(16) + '-' + Math.random().toString(16).slice(2, 8),
          sectionIndex: STATE.sectionIndex,
          color: 'yellow',
          text: meta.text,
          startOffset: meta.startOffset,
          endOffset: meta.endOffset,
        }};
        clearSelection();
        if (!applyHighlight(hl)) return false;
        send('incremento_epub_hl_add:' + JSON.stringify({{ cardId: STATE.cardId, highlight: hl }}));
        window._lastEpubSelectionMeta = meta;
        window._lastEpubSelection = meta.text;
        return true;
      }};
      ensureStyle();
      document.querySelectorAll('span.incremento-epub-highlight').forEach(unwrapHighlight);
      const highlights = Array.isArray(STATE.highlights) ? STATE.highlights.slice() : [];
      highlights.sort(function(a, b) {{ return Number(a.startOffset || 0) - Number(b.startOffset || 0); }});
      for (const hl of highlights) {{
        try {{ applyHighlight(hl); }} catch (err) {{}}
      }}
      document.removeEventListener('selectionchange', window._incrementoEpubSelectionListener, true);
      window._incrementoEpubSelectionListener = reportSelection;
      document.addEventListener('selectionchange', window._incrementoEpubSelectionListener, true);

      document.removeEventListener('keydown', window._incrementoEpubKeyListener, true);
      window._incrementoEpubKeyListener = function(event) {{
        const key = String(event.key || '');
        if ((event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey && /^[1-4]$/.test(key)) {{
          const meta = selectionMeta();
          if (!meta) return;
          event.preventDefault();
          send('incremento_epub_fill_field:' + JSON.stringify({{
            idx: Number(key) - 1,
            text: meta.text,
            startOffset: meta.startOffset,
            endOffset: meta.endOffset,
          }}));
          return;
        }}
        if (event.altKey && !event.metaKey && !event.ctrlKey && /^h$/i.test(key)) {{
          if (window.incrementoAddEpubHighlight()) {{
            event.preventDefault();
          }}
        }}
      }};
      document.addEventListener('keydown', window._incrementoEpubKeyListener, true);

      document.removeEventListener('click', window._incrementoEpubClickListener, true);
      window._incrementoEpubClickListener = function(event) {{
        const target = event.target && event.target.closest
          ? event.target.closest('span.incremento-epub-highlight')
          : null;
        if (!target) return;
        event.preventDefault();
        event.stopPropagation();
        const id = String(target.dataset.id || '');
        unwrapHighlight(target);
        send('incremento_epub_hl_del:' + JSON.stringify({{ cardId: STATE.cardId, id }}));
      }};
      document.addEventListener('click', window._incrementoEpubClickListener, true);

      if (window._incrementoEpubScrollTimer) {{
        clearTimeout(window._incrementoEpubScrollTimer);
      }}
      document.removeEventListener('scroll', window._incrementoEpubScrollListener, true);
      window._incrementoEpubScrollListener = function() {{
        clearTimeout(window._incrementoEpubScrollTimer);
        window._incrementoEpubScrollTimer = setTimeout(reportProgress, 140);
      }};
      document.addEventListener('scroll', window._incrementoEpubScrollListener, true);

      setTimeout(function() {{
        if (Number(STATE.focusOffset) >= 0) {{
          const point = pointFromOffset(STATE.focusOffset);
          if (point && point.node && point.node.parentElement && point.node.parentElement.scrollIntoView) {{
            point.node.parentElement.scrollIntoView({{ block: 'center' }});
          }}
        }} else if (Number(STATE.scrollRatio) > 0) {{
          const doc = document.documentElement || document.body;
          const maxScroll = Math.max(0, ((doc && doc.scrollHeight) || 0) - window.innerHeight);
          window.scrollTo(0, maxScroll * Number(STATE.scrollRatio));
        }}
        if (STATE.searchQuery) {{
          try {{
            window.find(STATE.searchQuery, false, false, true, false, false, false);
          }} catch (err) {{}}
        }}
        reportProgress();
      }}, 60);
    }})();
    """


def _build_epub_dock() -> None:
    global _epub_dock

    dock = QDockWidget("EPUB", mw)
    dock.setObjectName("incremento_epub_dock")
    dock.setMinimumWidth(430)

    container = QWidget(dock)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.setSpacing(6)

    toolbar = QHBoxLayout()
    dock._prev_btn = QPushButton("Prev")
    dock._next_btn = QPushButton("Next")
    dock._title_lbl = QLabel("EPUB")
    dock._title_lbl.setWordWrap(True)
    dock._title_lbl.setStyleSheet("font-weight: bold;")
    dock._source_lbl = QLabel("")
    dock._source_lbl.setStyleSheet("font-size: 11px; color: gray;")
    dock._add_card_btn = QPushButton("Add Card")
    dock._highlight_btn = QPushButton("Highlight")
    dock._finished_btn = QPushButton("Finished")
    dock._finished_btn.setCheckable(True)
    toolbar.addWidget(dock._prev_btn)
    toolbar.addWidget(dock._next_btn)
    toolbar.addWidget(dock._title_lbl, 1)
    toolbar.addWidget(dock._source_lbl)
    toolbar.addWidget(dock._add_card_btn)
    toolbar.addWidget(dock._highlight_btn)
    toolbar.addWidget(dock._finished_btn)
    layout.addLayout(toolbar)

    page = _EpubDockPage(dock)
    s = page.settings()
    s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
    s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

    view = QWebEngineView(dock)
    view.setPage(page)
    dock._view = view
    layout.addWidget(view, stretch=1)

    dock._sources = QTextBrowser()
    dock._sources.setMaximumHeight(120)
    dock._sources.setOpenLinks(False)
    dock._sources.setOpenExternalLinks(False)
    dock._sources.anchorClicked.connect(_open_source_link)
    layout.addWidget(dock._sources)

    dock.setWidget(container)
    mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    qconnect(dock._prev_btn.clicked, lambda: _jump_relative(-1))
    qconnect(dock._next_btn.clicked, lambda: _jump_relative(1))
    qconnect(dock._add_card_btn.clicked, lambda: _cb_open_add_card_dock and _cb_open_add_card_dock())
    qconnect(dock._highlight_btn.clicked, _request_highlight)
    qconnect(dock._finished_btn.clicked, _toggle_finished)
    qconnect(view.loadFinished, _on_load_finished)
    qconnect(view.urlChanged, _on_view_url_changed)

    _epub_dock = dock


def _open_source_link(url: QUrl) -> None:
    try:
        s = url.toString()
        if s.startswith("inc://card/"):
            note_id = int(s.rsplit("/", 1)[1])
            from aqt import dialogs

            browser = dialogs.open("Browser", mw)
            browser.search_for(f"nid:{note_id}")
    except Exception:
        pass


def _current_metadata() -> dict:
    if not _current_epub_filename:
        return {}
    return load_epub_metadata(_ADDON_DIR, _current_epub_filename)


def _current_sections() -> list[dict]:
    return list((_current_metadata().get("sections") or []))


def _update_title_and_buttons() -> None:
    if _epub_dock is None:
        return
    sections = _current_sections()
    count = len(sections)
    if count:
        idx = max(0, min(_current_epub_section_index, count - 1))
        section = sections[idx]
        _epub_dock._title_lbl.setText(
            f"{section.get('title') or f'Section {idx + 1}'} ({idx + 1}/{count})"
        )
        _epub_dock._prev_btn.setEnabled(idx > 0)
        _epub_dock._next_btn.setEnabled(idx + 1 < count)
    else:
        _epub_dock._title_lbl.setText("EPUB")
        _epub_dock._prev_btn.setEnabled(False)
        _epub_dock._next_btn.setEnabled(False)
    _epub_dock._finished_btn.blockSignals(True)
    _epub_dock._finished_btn.setChecked(bool(_current_epub_finished))
    _epub_dock._finished_btn.blockSignals(False)


def _update_sources_panel() -> None:
    if _epub_dock is None or _current_epub_card_id is None:
        return
    cards = get_epub_card_sources(_ADDON_DIR, _current_epub_card_id, _current_epub_section_index)
    counts = get_epub_section_card_counts(_ADDON_DIR, _current_epub_card_id)
    count = int(counts.get(_current_epub_section_index, 0) or 0)
    _epub_dock._source_lbl.setText(f"Cards here: {count}")
    if not cards:
        _epub_dock._sources.setHtml(
            "<div style='color:#888;font-size:12px;padding:6px'>No cards created from this section yet.</div>"
        )
        return
    html = ["<div style='font-family:sans-serif;font-size:12px'><b>Cards from this section</b><ul>"]
    for item in cards:
        note_id = int(item.get("note_id") or 0)
        excerpt = str(item.get("excerpt") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html.append(
            f"<li><a href='inc://card/{note_id}'>note {note_id}</a>"
            f" <span style='color:#888'>{excerpt}</span></li>"
        )
    html.append("</ul></div>")
    _epub_dock._sources.setHtml("".join(html))


def _record_progress(section_index: int, scroll_ratio: float) -> None:
    global _current_epub_section_index, _current_epub_scroll_ratio
    if _current_epub_card_id is None:
        return
    _current_epub_section_index = max(0, int(section_index))
    _current_epub_scroll_ratio = max(0.0, min(float(scroll_ratio), 1.0))
    try:
        set_epub_progress(
            _ADDON_DIR,
            _current_epub_card_id,
            section_index=_current_epub_section_index,
            scroll_ratio=_current_epub_scroll_ratio,
            is_finished=_current_epub_finished,
        )
    except Exception:
        pass
    _update_title_and_buttons()
    _update_sources_panel()


def _section_index_from_path(local_path: str) -> int | None:
    if not _current_epub_filename:
        return None
    normalized = os.path.normpath(local_path or "")
    for idx, _section in enumerate(_current_sections()):
        section_path = os.path.normpath(get_epub_section_path(_ADDON_DIR, _current_epub_filename, idx))
        if section_path == normalized:
            return idx
    return None


def _on_view_url_changed(url: QUrl) -> None:
    global _current_epub_section_index, _pending_focus_offset, _pending_restore_ratio, _pending_search_query, _pending_explicit_navigation
    idx = _section_index_from_path(url.toLocalFile())
    if idx is None:
        return
    _current_epub_section_index = idx
    if not _pending_explicit_navigation:
        _pending_focus_offset = -1
        _pending_restore_ratio = 0.0
        _pending_search_query = ""
    _pending_explicit_navigation = False
    _record_progress(_current_epub_section_index, 0.0 if _pending_focus_offset >= 0 else _current_epub_scroll_ratio)


def _on_load_finished(ok: bool) -> None:
    global _pending_focus_offset, _pending_restore_ratio, _pending_search_query
    if not ok or _epub_dock is None or _current_epub_card_id is None:
        return
    highlights = [
        hl
        for hl in load_highlights(_ADDON_DIR, _current_epub_card_id)
        if int(hl.get("sectionIndex", -1)) == int(_current_epub_section_index)
    ]
    js = _build_page_script(
        card_id=_current_epub_card_id,
        section_index=_current_epub_section_index,
        scroll_ratio=_pending_restore_ratio if _pending_focus_offset < 0 else 0.0,
        focus_offset=_pending_focus_offset,
        search_query=_pending_search_query,
        highlights=highlights,
    )
    _epub_dock._view.page().runJavaScript(js)
    _pending_focus_offset = -1
    _pending_restore_ratio = _current_epub_scroll_ratio
    _pending_search_query = ""
    _update_title_and_buttons()
    _update_sources_panel()


def _load_current_section() -> None:
    if _epub_dock is None or _current_epub_filename is None:
        return
    try:
        path = get_epub_section_path(_ADDON_DIR, _current_epub_filename, _current_epub_section_index)
    except Exception as exc:
        showInfo(f"Could not open EPUB section:\n{exc}")
        return
    _epub_dock._view.load(QUrl.fromLocalFile(path))


def show_epub_in_dock(
    card_id: int,
    filename: str,
    *,
    section_index: int,
    scroll_ratio: float = 0.0,
    focus_offset: int = -1,
    search_query: str = "",
) -> None:
    global _epub_dock, _current_epub_card_id, _current_epub_filename, _current_epub_section_index
    global _current_epub_scroll_ratio, _current_epub_finished, _pending_focus_offset, _pending_restore_ratio
    global _pending_search_query, _pending_explicit_navigation, _last_selection_meta

    if _epub_dock is None:
        _build_epub_dock()

    _current_epub_card_id = int(card_id)
    _current_epub_filename = str(filename or "").strip()
    _current_epub_section_index = max(0, int(section_index))
    _current_epub_scroll_ratio = max(0.0, min(float(scroll_ratio), 1.0))
    _pending_focus_offset = int(focus_offset)
    _pending_restore_ratio = _current_epub_scroll_ratio
    _pending_search_query = str(search_query or "")
    _pending_explicit_navigation = True
    _last_selection_meta = {}
    _, _, _current_epub_finished = get_epub_progress(_ADDON_DIR, _current_epub_card_id)

    _update_title_and_buttons()
    _update_sources_panel()
    _epub_dock.show()
    _epub_dock.raise_()
    _load_current_section()


def open_epub_location(
    card_id: int,
    section_index: int | None = None,
    *,
    focus_offset: int = -1,
    search_query: str = "",
) -> None:
    card = mw.col.get_card(card_id)
    note = mw.col.get_note(card.nid)
    filename = note[EPUB_FILE_FIELD]
    current_section, current_ratio, _is_finished = get_epub_progress(_ADDON_DIR, card_id)
    show_epub_in_dock(
        card_id,
        filename,
        section_index=current_section if section_index is None else int(section_index),
        scroll_ratio=current_ratio,
        focus_offset=focus_offset,
        search_query=search_query,
    )


def _on_epub_selection(idx: int, text: str, start_offset: int, end_offset: int) -> None:
    global _last_selection_meta
    cleaned = str(text or "").strip()
    if not cleaned or _cb_fill_dock_field is None:
        return
    _last_selection_meta = {
        "text": cleaned,
        "startOffset": int(start_offset),
        "endOffset": int(end_offset),
    }
    _cb_fill_dock_field(
        idx,
        cleaned,
        include_pdf_citation=False,
        citation_html=epub_citation(),
        source_link_kind="epub",
    )


def _jump_relative(delta: int) -> None:
    sections = _current_sections()
    if not sections or _current_epub_filename is None or _current_epub_card_id is None:
        return
    next_idx = max(0, min(_current_epub_section_index + int(delta), len(sections) - 1))
    if next_idx == _current_epub_section_index:
        return
    _record_progress(_current_epub_section_index, _current_epub_scroll_ratio)
    show_epub_in_dock(
        _current_epub_card_id,
        _current_epub_filename,
        section_index=next_idx,
        scroll_ratio=0.0,
    )


def _request_highlight() -> None:
    if _epub_dock is None:
        return
    _epub_dock._view.page().runJavaScript(
        "window.incrementoAddEpubHighlight && window.incrementoAddEpubHighlight();"
    )


def _toggle_finished(checked: bool) -> None:
    global _current_epub_finished
    _current_epub_finished = bool(checked)
    if _current_epub_card_id is None:
        return
    try:
        set_epub_progress(
            _ADDON_DIR,
            _current_epub_card_id,
            section_index=_current_epub_section_index,
            scroll_ratio=_current_epub_scroll_ratio,
            is_finished=_current_epub_finished,
        )
    except Exception:
        pass


def on_epub_question_shown(card) -> None:
    global _epub_dock
    try:
        if card is None:
            return
        note = mw.col.get_note(card.nid)
        model = mw.col.models.get(note.mid)
        if model is None or model.get("name") != EPUB_NOTE_TYPE:
            if _epub_dock is not None:
                try:
                    _epub_dock.hide()
                except RuntimeError:
                    _epub_dock = None
            return
        filename = note[EPUB_FILE_FIELD]
        section_index, scroll_ratio, _is_finished = get_epub_progress(_ADDON_DIR, card.id)
        show_epub_in_dock(
            card.id,
            filename,
            section_index=section_index,
            scroll_ratio=scroll_ratio,
        )
    except Exception as exc:
        print(f"[Incremento] on_epub_question_shown error: {exc}")


def on_epub_reviewer_will_end() -> None:
    global _epub_dock
    if _epub_dock is not None:
        try:
            _epub_dock.hide()
        except RuntimeError:
            _epub_dock = None


def on_add_cards_did_add_note(note) -> None:
    if _current_epub_card_id is None:
        return
    import re as _re

    parts = []
    for field in (note.fields or [])[:2]:
        plain = _re.sub(r"<[^>]+>", "", field).strip()[:120]
        if plain:
            parts.append(plain)
    excerpt = " / ".join(parts)[:200]
    try:
        add_epub_card_source(
            _ADDON_DIR,
            _current_epub_card_id,
            _current_epub_section_index,
            note.id,
            excerpt,
        )
    except Exception:
        pass
    _update_sources_panel()


def get_selected_text(callback) -> None:
    if _epub_dock is None:
        callback("")
        return
    try:
        _epub_dock._view.page().runJavaScript(
            "(function(){ return (window._lastEpubSelection || '').trim(); })();",
            lambda text: callback(str(text or "").strip()),
        )
    except Exception:
        callback("")


def sync_epub_note_type() -> None:
    try:
        ensure_epub_note_type(mw.col)
    except Exception:
        pass
