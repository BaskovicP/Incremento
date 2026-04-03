"""
add_card_dock.py — persistent Add Card dock widget.

Wraps Anki's native AddCards dialog inside a QDockWidget so it stays
open across card reviews.

Public API:
    open_add_card_dock() — show or rebuild the dock
    fill_dock_field(idx, text) — append text (with PDF citation) to field idx
    do_fill(idx, text) — inner fill, bypasses citation
    get_add_card_dock() — return the current dock instance (may be None)
"""

import json
import time

from aqt import mw
from aqt import gui_hooks
from aqt.qt import (
    QDockWidget,
    QTimer,
    Qt,
)
from aqt.utils import tooltip

_add_card_dock = None  # QDockWidget instance, persists across card reviews
_SELECTION_TTL_SEC = 20.0
_last_selection_source = ""
_last_selection_text = ""
_last_selection_seen = 0.0
_ADDON_PKG = __name__.split(".")[0] if "." in __name__ else "incremento"
_DEFAULT_EXTRACT_SOURCE_LINKS = {
    "pdf": True,
    "web": True,
    "parent": True,
}


def _normalize_text(text) -> str:
    return str(text or "").replace("\u2029", "\n").strip()


def _has_recent_selection() -> bool:
    return bool(_last_selection_source) and (
        time.monotonic() - _last_selection_seen
    ) < _SELECTION_TTL_SEC


def _set_transfer_buttons_visible(editor, visible: bool) -> None:
    try:
        editor.web.eval(
            f"""
            (function() {{
              var visible = {json.dumps(bool(visible))};
              if (!window.incrementoTransferButtons) {{
                return;
              }}
              window.incrementoTransferButtons.setVisible(visible);
            }})();
            """
        )
    except Exception:
        pass


def _dock_editor():
    dock = get_add_card_dock()
    if dock is None:
        return None
    dlg = getattr(dock, "_addcards_dialog", None)
    if dlg is not None:
        return getattr(dlg, "editor", None)
    try:
        return dock.widget().editor
    except Exception:
        return None


def configured_extract_notetype_name(config: dict | None = None) -> str:
    cfg = config
    if cfg is None:
        try:
            cfg = mw.addonManager.getConfig(_ADDON_PKG) or {}
        except Exception:
            cfg = {}
    return str((cfg or {}).get("extract_notetype") or "").strip()


def configured_extract_source_links(config: dict | None = None) -> dict[str, bool]:
    cfg = config
    if cfg is None:
        try:
            cfg = mw.addonManager.getConfig(_ADDON_PKG) or {}
        except Exception:
            cfg = {}
    raw = (cfg or {}).get("extract_source_links", _DEFAULT_EXTRACT_SOURCE_LINKS)
    if isinstance(raw, bool):
        return {key: bool(raw) for key in _DEFAULT_EXTRACT_SOURCE_LINKS}
    if not isinstance(raw, dict):
        return dict(_DEFAULT_EXTRACT_SOURCE_LINKS)
    merged = dict(_DEFAULT_EXTRACT_SOURCE_LINKS)
    for key in merged:
        if key in raw:
            merged[key] = bool(raw.get(key))
    return merged


def should_add_extract_source_link(kind: str, config: dict | None = None) -> bool:
    return bool(configured_extract_source_links(config).get(str(kind or "").strip(), True))


def _note_has_content(note) -> bool:
    if note is None:
        return False
    try:
        if any(str(val or "").strip() for val in list(getattr(note, "fields", []) or [])):
            return True
    except Exception:
        pass
    try:
        if any(str(tag or "").strip() for tag in list(getattr(note, "tags", []) or [])):
            return True
    except Exception:
        pass
    return False


def should_apply_extract_notetype(
    configured_name: str,
    current_name: str,
    *,
    note_has_content: bool,
) -> bool:
    target = str(configured_name or "").strip()
    current = str(current_name or "").strip()
    return bool(target) and target != current and not note_has_content


def _apply_configured_extract_notetype() -> None:
    dock = get_add_card_dock()
    if dock is None:
        return

    dlg = getattr(dock, "_addcards_dialog", None)
    editor = getattr(dlg, "editor", None) if dlg is not None else None
    if dlg is None or editor is None:
        return

    configured_name = configured_extract_notetype_name()
    if not configured_name:
        return

    try:
        model = mw.col.models.by_name(configured_name)
    except Exception:
        model = None
    if model is None:
        return

    note = getattr(editor, "note", None)
    current_name = ""
    try:
        if note is not None:
            current_name = str(note.note_type().get("name") or "")
    except Exception:
        current_name = ""

    if not should_apply_extract_notetype(
        configured_name,
        current_name,
        note_has_content=_note_has_content(note),
    ):
        return

    deck_id = None
    try:
        deck_id = dlg.deck_chooser.selected_deck_id
    except Exception:
        deck_id = None

    try:
        dlg.set_note_type(model["id"])
        if deck_id is not None:
            dlg.set_deck(deck_id)
    except Exception:
        return

    _set_transfer_buttons_visible(editor, _has_recent_selection())


def _inject_transfer_buttons(editor) -> None:
    note = getattr(editor, "note", None)
    field_names = []
    try:
        if note:
            field_names = [f["name"] for f in note.note_type()["flds"]]
    except Exception:
        field_names = []
    try:
        editor.web.eval(
            f"""
            (function() {{
              var visible = {json.dumps(_has_recent_selection())};
              var fieldNames = {json.dumps(field_names)};
              if (!window.incrementoTransferButtons) {{
                var styleId = 'incremento-transfer-style';
                if (!document.getElementById(styleId)) {{
                  var style = document.createElement('style');
                  style.id = styleId;
                  style.textContent = `
                    .incremento-transfer-btn {{
                      width: 24px;
                      height: 24px;
                      margin-left: 6px;
                      border: 1px solid rgba(120, 132, 156, 0.38);
                      border-radius: 999px;
                      background: transparent;
                      color: #98a2b3;
                      cursor: pointer;
                      display: none;
                      align-items: center;
                      justify-content: center;
                      font-size: 13px;
                      line-height: 1;
                      vertical-align: middle;
                    }}
                    .incremento-transfer-btn:hover {{
                      background: rgba(72, 128, 255, 0.12);
                      color: #7fb0ff;
                      border-color: rgba(45, 91, 209, 0.38);
                    }}
                  `;
                  document.head.appendChild(style);
                }}

                window.incrementoTransferButtons = {{
                  visible: false,
                  fieldNames: [],
                  fieldNodes: function() {{
                    var explicit = Array.from(
                      document.querySelectorAll(
                        '[contenteditable="true"][id^="f"], div[id^="f"][contenteditable], textarea[id^="f"]'
                      )
                    );
                    if (explicit.length) {{
                      return explicit;
                    }}
                    return Array.from(document.querySelectorAll('[contenteditable="true"], textarea'))
                      .filter(function(el) {{
                        return !el.closest('.note-editor-toolbar');
                      }});
                  }},
                  fieldIndex: function(field, fallbackIdx) {{
                    var match = /^f(\\d+)$/.exec(field.id || '');
                    if (match) {{
                      return Number(match[1]);
                    }}
                    var ord = field.getAttribute('data-ord');
                    if (ord !== null && ord !== '') {{
                      return Number(ord);
                    }}
                    return fallbackIdx;
                  }},
                  fieldHost: function(field) {{
                    return (
                      field.closest('[data-field-ord]')
                      || field.closest('.field')
                      || field.closest('[class*="field"]')
                      || field.parentElement
                    );
                  }},
                  actionHost: function(host, idx) {{
                    if (!host) {{
                      return null;
                    }}
                    var fieldName = this.fieldNames[idx] || '';
                    var candidates = Array.from(host.querySelectorAll('div, header, section'));
                    var named = candidates.filter(function(el) {{
                      var text = (el.textContent || '').trim();
                      return text && fieldName && text.indexOf(fieldName) !== -1;
                    }});
                    var namedWithButtons = named.find(function(el) {{
                      return !!el.querySelector('button');
                    }});
                    if (namedWithButtons) {{
                      var buttonParent = Array.from(namedWithButtons.querySelectorAll('button'))
                        .map(function(btn) {{ return btn.parentElement; }})
                        .find(function(el) {{ return !!el; }});
                      return buttonParent || namedWithButtons;
                    }}
                    var anyButtonParent = Array.from(host.querySelectorAll('button'))
                      .map(function(btn) {{ return btn.parentElement; }})
                      .find(function(el) {{ return !!el; }});
                    return anyButtonParent || host;
                  }},
                  render: function() {{
                    this.fieldNodes().forEach(function(field, fallbackIdx) {{
                      var idx = window.incrementoTransferButtons.fieldIndex(field, fallbackIdx);
                      var host = window.incrementoTransferButtons.fieldHost(field);
                      var actionHost = window.incrementoTransferButtons.actionHost(host, idx);
                      if (!actionHost) {{
                        return;
                      }}
                      var selector = '.incremento-transfer-btn[data-idx="' + idx + '"]';
                      var btn = actionHost.querySelector(selector);
                      if (!btn) {{
                        btn = document.createElement('button');
                        btn.type = 'button';
                        btn.className = 'incremento-transfer-btn';
                        btn.dataset.idx = String(idx);
                        var name = window.incrementoTransferButtons.fieldNames[idx] || ('Field ' + (idx + 1));
                        btn.title = 'Insert selected text into ' + name;
                        btn.innerHTML = '&#x21E2;';
                        btn.addEventListener('mousedown', function(evt) {{
                          evt.preventDefault();
                          evt.stopPropagation();
                        }});
                        btn.addEventListener('click', function(evt) {{
                          evt.preventDefault();
                          evt.stopPropagation();
                          pycmd('incremento_transfer_selection:' + idx);
                        }});
                        actionHost.appendChild(btn);
                      }}
                      btn.style.display = window.incrementoTransferButtons.visible
                        ? 'inline-flex'
                        : 'none';
                    }});
                  }},
                  setFieldNames: function(names) {{
                    this.fieldNames = Array.isArray(names) ? names.slice() : [];
                  }},
                  setVisible: function(nextVisible) {{
                    this.visible = !!nextVisible;
                    this.render();
                  }},
                }};

                if (!window.incrementoTransferButtonsObserver) {{
                  window.incrementoTransferButtonsObserver = new MutationObserver(function() {{
                    if (window.incrementoTransferButtons) {{
                      window.incrementoTransferButtons.render();
                    }}
                  }});
                  window.incrementoTransferButtonsObserver.observe(document.body, {{
                    childList: true,
                    subtree: true,
                  }});
                }}
              }}

              window.incrementoTransferButtons.setFieldNames(fieldNames);
              window.incrementoTransferButtons.setVisible(visible);
            }})();
            """
        )
    except Exception:
        pass


def _on_editor_did_load_note(editor) -> None:
    if not getattr(editor, "addMode", False):
        return
    _inject_transfer_buttons(editor)


gui_hooks.editor_did_load_note.append(_on_editor_did_load_note)


def build_add_card_dock():
    """Embed the native AddCards dialog into a left dock widget."""
    global _add_card_dock
    from aqt.addcards import AddCards

    dock = QDockWidget("Add Card", mw)
    dock.setObjectName("incremento_add_card_dock")
    dock.setMinimumWidth(400)

    # Open the native dialog; hide it before the event loop renders it as a
    # floating window, then reparent it into the dock as a plain widget.
    dlg = AddCards(mw)
    dlg.hide()
    dlg.setParent(dock)
    dlg.setWindowFlags(Qt.WindowType.Widget)
    dock.setWidget(dlg)
    dock._addcards_dialog = dlg

    mw.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
    _add_card_dock = dock
    dlg.show()
    _apply_configured_extract_notetype()
    _inject_transfer_buttons(dlg.editor)

    def _set_field(idx, text):
        note = dlg.editor.note
        if note and idx < len(note.fields):
            existing = note.fields[idx]
            note.fields[idx] = (existing + '<br><br>' + text) if existing else text
            try:
                dlg.editor.loadNote()
            except Exception:
                pass
            _set_transfer_buttons_visible(dlg.editor, _has_recent_selection())

    dock._set_field = _set_field
    return dock


def open_add_card_dock():
    global _add_card_dock
    if _add_card_dock is not None:
        try:
            _add_card_dock.show()
            _add_card_dock.raise_()
            _apply_configured_extract_notetype()
            editor = _dock_editor()
            if editor is not None:
                _set_transfer_buttons_visible(editor, _has_recent_selection())
            return
        except RuntimeError:
            _add_card_dock = None
    build_add_card_dock()


def fill_dock_field(
    idx,
    text,
    include_pdf_citation: bool = True,
    citation_html: str | None = None,
    source_link_kind: str | None = None,
):
    global _add_card_dock
    citation = citation_html
    link_kind = str(source_link_kind or "").strip()
    if citation is None and include_pdf_citation:
        link_kind = link_kind or "pdf"
        try:
            from .pdf_dock import pdf_citation

            citation = pdf_citation()
        except Exception:
            citation = None
    if citation and (not link_kind or should_add_extract_source_link(link_kind)):
        text = text + '<br>' + citation
    if _add_card_dock is None:
        build_add_card_dock()
        QTimer.singleShot(600, lambda: do_fill(idx, text))
        return
    try:
        _add_card_dock.show()
        _add_card_dock.raise_()
        _apply_configured_extract_notetype()
        do_fill(idx, text)
    except RuntimeError:
        _add_card_dock = None


def do_fill(idx, text):
    if _add_card_dock is None:
        return
    try:
        _add_card_dock._set_field(idx, text)
    except (RuntimeError, AttributeError):
        pass


def get_add_card_dock():
    return _add_card_dock


def _refresh_transfer_buttons() -> None:
    dock = get_add_card_dock()
    if dock is None:
        return
    try:
        editor = _dock_editor()
        if editor is not None:
            _set_transfer_buttons_visible(editor, _has_recent_selection())
    except Exception:
        pass


def _expire_selection_if_stale(expected_seen: float) -> None:
    if expected_seen != _last_selection_seen:
        return
    _refresh_transfer_buttons()


def update_selection_state(
    source: str, text: str | None = None, has_text: bool | None = None
) -> None:
    global _last_selection_source, _last_selection_text, _last_selection_seen
    cleaned = _normalize_text(text) if text is not None else ""
    if cleaned:
        _last_selection_text = cleaned
        has_text = True
    if has_text is False and not cleaned:
        return
    if not has_text and not cleaned:
        return
    _last_selection_source = str(source or _last_selection_source or "")
    _last_selection_seen = time.monotonic()
    _refresh_transfer_buttons()
    QTimer.singleShot(
        int((_SELECTION_TTL_SEC + 0.2) * 1000),
        lambda seen=_last_selection_seen: _expire_selection_if_stale(seen),
    )


def _resolve_reviewer_selection(callback) -> None:
    reviewer = getattr(mw, "reviewer", None)
    web = getattr(reviewer, "web", None)
    if web is None:
        callback("")
        return
    try:
        web.page().runJavaScript(
            "(function(){ return (window._incrementoLastSelection || "
            "(window.getSelection && window.getSelection().toString()) || '').trim(); })();",
            lambda text: callback(_normalize_text(text)),
        )
    except Exception:
        callback("")


def _resolve_selection_from_source(source: str, callback) -> None:
    if source == "pdf":
        try:
            from .pdf_dock import get_selected_text

            get_selected_text(lambda text: callback(source, _normalize_text(text)))
            return
        except Exception:
            pass
    elif source == "reviewer":
        _resolve_reviewer_selection(lambda text: callback(source, text))
        return
    elif source == "web":
        try:
            from .web_dock import get_selected_text

            get_selected_text(lambda text: callback(source, _normalize_text(text)))
            return
        except Exception:
            pass
    elif source == "writing":
        try:
            from .writing_dock import get_selected_text

            callback(source, _normalize_text(get_selected_text()))
            return
        except Exception:
            pass
    callback(source, "")


def transfer_selection_to_field(idx: int) -> None:
    if not _has_recent_selection():
        tooltip("Select some text first.")
        return

    source = _last_selection_source
    fallback_text = _last_selection_text if source == "writing" else ""

    def _apply(resolved_source: str, resolved_text: str) -> None:
        text = resolved_text or fallback_text
        text = _normalize_text(text)
        if not text:
            tooltip("Select some text first.")
            return
        fill_dock_field(
            idx,
            text,
            include_pdf_citation=(resolved_source == "pdf"),
            source_link_kind=resolved_source if resolved_source in {"pdf", "web"} else None,
            citation_html=(
                _web_citation()
                if resolved_source == "web"
                else None
            ),
        )

    def _web_citation() -> str | None:
        try:
            from .web_dock import web_citation

            return web_citation()
        except Exception:
            return None

    _resolve_selection_from_source(source, _apply)
