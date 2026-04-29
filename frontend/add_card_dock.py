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
import os
import time
import weakref

from aqt import mw
from aqt import gui_hooks
from aqt.qt import (
    QDockWidget,
    QTimer,
    Qt,
)
from aqt.utils import tooltip

try:
    from ..backend.reviewer_tags import append_missing_tags
except Exception:
    try:
        from reviewer_tags import append_missing_tags  # type: ignore
    except Exception:
        append_missing_tags = None  # type: ignore

try:
    from ..backend.reviewer_extract import knowledge_tree_link_state
except Exception:
    try:
        from reviewer_extract import knowledge_tree_link_state  # type: ignore
    except Exception:
        knowledge_tree_link_state = None  # type: ignore

_add_card_dock = None  # QDockWidget instance, persists across card reviews
_SELECTION_TTL_SEC = 20.0
_last_selection_source = ""
_last_selection_text = ""
_last_selection_seen = 0.0
_last_add_mode_editor = None
_current_extract_priority: float | None = None
_current_extract_mark_topic: bool | None = None
_current_extract_link_to_knowledge_tree: bool | None = None
_pending_extract_options: dict | None = None
_pending_extract_context: dict | None = None
_last_fill_source = ""
_last_fill_seen = 0.0
_tracked_tag_button_editors: list[weakref.ReferenceType] = []
_ADDON_PKG = __name__.split(".")[0] if "." in __name__ else "incremento"
_ADDON_DIR = os.path.dirname(os.path.dirname(__file__))
_DEFAULT_EXTRACT_SOURCE_LINKS = {
    "pdf": True,
    "epub": True,
    "web": True,
    "parent": True,
}
_DEFAULT_ADD_CARD_TOPIC_TAGS = ["topic"]
_DEFAULT_ADD_CARD_ITEM_TAGS = ["item"]
_TOPIC_TAG_BUTTON_ID = "incremento-add-card-topic-tag"
_ITEM_TAG_BUTTON_ID = "incremento-add-card-item-tag"


def _clamp_priority(value) -> float:
    try:
        number = float(value)
    except Exception:
        number = 50.0
    return round(max(0.0, min(100.0, number)), 4)


def _config(config: dict | None = None) -> dict:
    if config is not None:
        return config or {}
    try:
        return mw.addonManager.getConfig(_ADDON_PKG) or {}
    except Exception:
        return {}


def _detach_embedded_window_menu_bar(window) -> None:
    """Prevent an embedded QMainWindow from overriding Anki's native menu bar."""
    try:
        window.setMenuBar(None)
    except Exception:
        pass


def _normalize_text(text) -> str:
    return str(text or "").replace("\u2029", "\n").strip()


def _normalize_tag_list(raw_tags, default: list[str] | None = None) -> list[str]:
    if isinstance(raw_tags, str):
        parts = raw_tags.replace("\n", ",").split(",")
    elif isinstance(raw_tags, (list, tuple, set)):
        parts = list(raw_tags)
    elif default is not None:
        parts = list(default)
    else:
        parts = []

    tags: list[str] = []
    seen: set[str] = set()
    for item in parts:
        tag = str(item or "").strip()
        if not tag:
            continue
        normalized = tag.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        tags.append(tag)
    return tags


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


def _current_add_mode_editor():
    editor = _dock_editor()
    if editor is not None:
        return editor
    global _last_add_mode_editor
    try:
        if _last_add_mode_editor is not None and getattr(_last_add_mode_editor, "note", None) is not None:
            return _last_add_mode_editor
    except Exception:
        _last_add_mode_editor = None
    return None


def _iter_tracked_tag_button_editors():
    alive: list[weakref.ReferenceType] = []
    editors = []
    for ref in _tracked_tag_button_editors:
        try:
            editor = ref()
        except Exception:
            editor = None
        if editor is None:
            continue
        alive.append(ref)
        editors.append(editor)
    if len(alive) != len(_tracked_tag_button_editors):
        _tracked_tag_button_editors[:] = alive
    return editors


def _track_tag_button_editor(editor) -> None:
    for existing in _iter_tracked_tag_button_editors():
        if existing is editor:
            return
    try:
        _tracked_tag_button_editors.append(weakref.ref(editor))
    except Exception:
        pass


def configured_extract_notetype_name(config: dict | None = None) -> str:
    cfg = _config(config)
    return str((cfg or {}).get("extract_notetype") or "").strip()


def configured_extract_priority(config: dict | None = None) -> float:
    cfg = _config(config)
    if "extract_priority" in cfg:
        return _clamp_priority(cfg.get("extract_priority"))
    lower_is_more_important = bool(cfg.get("priority_lower_is_more_important", True))
    return 40.0 if lower_is_more_important else 60.0


def configured_extract_priority_multiplier(config: dict | None = None) -> float:
    cfg = _config(config)
    lower_is_more_important = bool(cfg.get("priority_lower_is_more_important", True))
    default = 0.98 if lower_is_more_important else 1.02
    try:
        value = float(cfg.get("extract_priority_multiplier", default))
    except Exception:
        value = default
    return round(max(0.01, min(10.0, value)), 4)


def calculate_extract_priority(
    source_priority,
    config: dict | None = None,
    *,
    fallback_priority=None,
) -> float:
    cfg = _config(config)
    fallback = configured_extract_priority(cfg) if fallback_priority is None else _clamp_priority(fallback_priority)
    try:
        source = float(source_priority)
    except Exception:
        return fallback
    return _clamp_priority(source * configured_extract_priority_multiplier(cfg))


def configured_extract_mark_topic(config: dict | None = None) -> bool:
    cfg = _config(config)
    return bool(cfg.get("extract_mark_topic", True))


def configured_extract_copy_source_tags(config: dict | None = None) -> bool:
    cfg = _config(config)
    return bool(cfg.get("extract_copy_source_tags", False))


def configured_add_card_topic_tags(config: dict | None = None) -> list[str]:
    cfg = _config(config)
    return _normalize_tag_list(
        (cfg or {}).get("add_card_topic_tags"),
        default=_DEFAULT_ADD_CARD_TOPIC_TAGS,
    )


def configured_add_card_item_tags(config: dict | None = None) -> list[str]:
    cfg = _config(config)
    return _normalize_tag_list(
        (cfg or {}).get("add_card_item_tags"),
        default=_DEFAULT_ADD_CARD_ITEM_TAGS,
    )


def configured_extract_source_links(config: dict | None = None) -> dict[str, bool]:
    cfg = _config(config)
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
        extract_priority = (
            _extract_priority_for_transfer()
            if _current_extract_priority is not None
            else (
                source_relative_extract_priority_for_source(_last_selection_source)
                if _has_recent_selection()
                else configured_extract_priority()
            )
        )
        extract_mark_topic = _extract_mark_topic_for_transfer()
        tree_context = pending_extract_context() or {}
        tree_link_enabled = bool(tree_context.get("knowledge_tree_link_enabled"))
        tree_link_checked = bool(
            tree_context.get("link_to_knowledge_tree")
            if _current_extract_link_to_knowledge_tree is None
            else _current_extract_link_to_knowledge_tree
        )
        tree_link_tooltip = str(tree_context.get("knowledge_tree_tooltip") or "")
        editor.web.eval(
            f"""
            (function() {{
              var visible = {json.dumps(_has_recent_selection())};
              var fieldNames = {json.dumps(field_names)};
              var defaultExtractPriority = {json.dumps(extract_priority)};
              var defaultExtractTopic = {json.dumps(extract_mark_topic)};
              var defaultExtractTreeLink = {json.dumps(tree_link_checked)};
              var extractTreeLinkEnabled = {json.dumps(tree_link_enabled)};
              var extractTreeLinkTooltip = {json.dumps(tree_link_tooltip)};
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
                    .incremento-extract-options {{
                      display: none;
                      align-items: center;
                      gap: 8px;
                      margin: 7px 0 9px;
                      padding: 7px 9px;
                      border: 1px solid rgba(120, 132, 156, 0.28);
                      border-radius: 10px;
                      background: rgba(72, 128, 255, 0.08);
                      color: inherit;
                      font-size: 12px;
                    }}
                    .incremento-extract-options input[type="number"] {{
                      width: 62px;
                      padding: 2px 5px;
                      border-radius: 6px;
                      border: 1px solid rgba(120, 132, 156, 0.42);
                      background: rgba(255, 255, 255, 0.92);
                      color: #101828;
                      font-weight: 700;
                    }}
                    .incremento-extract-options label {{
                      display: inline-flex;
                      align-items: center;
                      gap: 4px;
                      white-space: nowrap;
                    }}
                  `;
                  document.head.appendChild(style);
                }}

                window.incrementoTransferButtons = {{
                  visible: false,
                  fieldNames: [],
                  extractPriority: defaultExtractPriority,
                  extractTopic: defaultExtractTopic,
                  extractTreeLink: defaultExtractTreeLink,
                  syncExtractOptions: function() {{
                    pycmd('incremento_extract_options:' + JSON.stringify({{
                      priority: this.extractPriority,
                      markTopic: this.extractTopic,
                      linkToKnowledgeTree: this.extractTreeLink
                    }}));
                  }},
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
                  ensureExtractOptions: function() {{
                    var firstField = this.fieldNodes()[0];
                    if (!firstField) {{
                      return null;
                    }}
                    var host = this.fieldHost(firstField) || firstField.parentElement;
                    if (!host) {{
                      return null;
                    }}
                    var panel = document.getElementById('incremento-extract-options');
                    if (!panel) {{
                      panel = document.createElement('div');
                      panel.id = 'incremento-extract-options';
                      panel.className = 'incremento-extract-options';
                      panel.innerHTML = [
                        '<strong>Extract</strong>',
                        '<label>Priority <input id="incremento-extract-priority" type="number" min="0" max="100" step="0.1"></label>',
                        '<label><input id="incremento-extract-topic" type="checkbox"> Topic</label>',
                        '<label id="incremento-extract-tree-link-wrap"><input id="incremento-extract-tree-link" type="checkbox"> Tree child</label>'
                      ].join('');
                      host.parentElement.insertBefore(panel, host);
                      var prio = panel.querySelector('#incremento-extract-priority');
                      var topic = panel.querySelector('#incremento-extract-topic');
                      var treeLink = panel.querySelector('#incremento-extract-tree-link');
                      var treeLinkWrap = panel.querySelector('#incremento-extract-tree-link-wrap');
                      prio.value = String(this.extractPriority);
                      topic.checked = !!this.extractTopic;
                      treeLink.checked = !!this.extractTreeLink;
                      treeLink.disabled = !extractTreeLinkEnabled;
                      treeLinkWrap.style.display = extractTreeLinkEnabled ? 'inline-flex' : 'none';
                      treeLinkWrap.title = extractTreeLinkTooltip;
                      prio.addEventListener('change', function() {{
                        var value = Number(prio.value);
                        if (!Number.isFinite(value)) {{
                          value = defaultExtractPriority;
                        }}
                        value = Math.max(0, Math.min(100, value));
                        prio.value = String(value);
                        window.incrementoTransferButtons.extractPriority = value;
                        window.incrementoTransferButtons.syncExtractOptions();
                      }});
                      topic.addEventListener('change', function() {{
                        window.incrementoTransferButtons.extractTopic = !!topic.checked;
                        window.incrementoTransferButtons.syncExtractOptions();
                      }});
                      treeLink.addEventListener('change', function() {{
                        window.incrementoTransferButtons.extractTreeLink = !!treeLink.checked;
                        window.incrementoTransferButtons.syncExtractOptions();
                      }});
                      this.syncExtractOptions();
                    }}
                    return panel;
                  }},
                  render: function() {{
                    var panel = this.ensureExtractOptions();
                    if (panel) {{
                      panel.style.display = this.visible ? 'flex' : 'none';
                    }}
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

              if (window.incrementoTransferButtons) {{
                window.incrementoTransferButtons.extractPriority = defaultExtractPriority;
                window.incrementoTransferButtons.extractTopic = defaultExtractTopic;
                window.incrementoTransferButtons.extractTreeLink = defaultExtractTreeLink;
                var existingPanel = document.getElementById('incremento-extract-options');
                if (existingPanel) {{
                  var existingPrio = existingPanel.querySelector('#incremento-extract-priority');
                  var existingTopic = existingPanel.querySelector('#incremento-extract-topic');
                  var existingTreeLink = existingPanel.querySelector('#incremento-extract-tree-link');
                  var existingTreeLinkWrap = existingPanel.querySelector('#incremento-extract-tree-link-wrap');
                  if (existingPrio) {{
                    existingPrio.value = String(defaultExtractPriority);
                  }}
                  if (existingTopic) {{
                    existingTopic.checked = !!defaultExtractTopic;
                  }}
                  if (existingTreeLink) {{
                    existingTreeLink.checked = !!defaultExtractTreeLink;
                    existingTreeLink.disabled = !extractTreeLinkEnabled;
                  }}
                  if (existingTreeLinkWrap) {{
                    existingTreeLinkWrap.style.display = extractTreeLinkEnabled ? 'inline-flex' : 'none';
                    existingTreeLinkWrap.title = extractTreeLinkTooltip;
                  }}
                  window.incrementoTransferButtons.syncExtractOptions();
                }}
              }}
              window.incrementoTransferButtons.setFieldNames(fieldNames);
              window.incrementoTransferButtons.setVisible(visible);
            }})();
            """
        )
    except Exception:
        pass
    try:
        _apply_extract_topic_default_to_editor(editor)
    except Exception:
        pass


def _note_tags(note) -> list[str]:
    try:
        return [
            str(tag or "").strip()
            for tag in list(getattr(note, "tags", []) or [])
            if str(tag or "").strip()
        ]
    except Exception:
        return []


def _set_note_tags(note, tags: list[str]) -> None:
    try:
        note.tags = list(tags)
    except Exception:
        pass


def _set_editor_web_tags(editor, tags: list[str]) -> None:
    try:
        editor.web.eval(
            f"""
            require("anki/ui").loaded.then(() => {{
                setTags({json.dumps(list(tags or []))});
                triggerChanges();
            }});
            """
        )
    except Exception:
        pass


def _editor_tags(editor, note) -> list[str]:
    try:
        tags_widget = getattr(editor, "tags", None)
        if tags_widget is not None and hasattr(tags_widget, "text"):
            raw = str(tags_widget.text() or "")
            if hasattr(mw.col, "tags"):
                return _normalize_tag_list(mw.col.tags.split(raw))
            return _normalize_tag_list(raw)
    except Exception:
        pass
    return _note_tags(note)


def _set_editor_tags(editor, tags: list[str]) -> None:
    note = getattr(editor, "note", None)
    if note is not None:
        _set_note_tags(note, tags)
    _set_editor_web_tags(editor, tags)
    try:
        tags_widget = getattr(editor, "tags", None)
        if tags_widget is None:
            return
        if getattr(tags_widget, "col", None) != mw.col:
            tags_widget.setCol(mw.col)
        tags_widget.setText(" ".join(tags))
        if hasattr(tags_widget, "update"):
            tags_widget.update()
        if hasattr(tags_widget, "repaint"):
            tags_widget.repaint()
    except Exception:
        pass


def _sync_editor_tag_widget(editor) -> None:
    try:
        tags_widget = getattr(editor, "tags", None)
        note = getattr(editor, "note", None)
        if tags_widget is None or note is None:
            if note is not None:
                _set_editor_web_tags(editor, _note_tags(note))
            return
        if getattr(tags_widget, "col", None) != mw.col:
            tags_widget.setCol(mw.col)
        tags_widget.setText(note.string_tags().strip())
        _set_editor_web_tags(editor, _note_tags(note))
        if hasattr(tags_widget, "update"):
            tags_widget.update()
        if hasattr(tags_widget, "repaint"):
            tags_widget.repaint()
    except Exception:
        pass


def _schedule_editor_tag_widget_sync(editor) -> None:
    _sync_editor_tag_widget(editor)
    try:
        QTimer.singleShot(0, lambda editor=editor: _sync_editor_tag_widget(editor))
        QTimer.singleShot(40, lambda editor=editor: _sync_editor_tag_widget(editor))
    except Exception:
        pass


def _schedule_add_card_tag_button_refresh(editor) -> None:
    _refresh_add_card_tag_buttons_for_editor(editor)
    try:
        QTimer.singleShot(0, lambda editor=editor: _refresh_add_card_tag_buttons_for_editor(editor))
        QTimer.singleShot(80, lambda editor=editor: _refresh_add_card_tag_buttons_for_editor(editor))
        QTimer.singleShot(180, lambda editor=editor: _refresh_add_card_tag_buttons_for_editor(editor))
    except Exception:
        pass


def _note_has_any_tags(note, wanted_tags: list[str]) -> bool:
    normalized_wanted = {tag.lower() for tag in _normalize_tag_list(wanted_tags)}
    if not normalized_wanted:
        return False
    note_tag_set = {tag.lower() for tag in _note_tags(note)}
    return bool(note_tag_set.intersection(normalized_wanted))


def _apply_extract_topic_default_to_editor(editor) -> None:
    if not _has_recent_selection() or not _extract_mark_topic_for_transfer():
        return
    note = getattr(editor, "note", None)
    if note is None:
        return
    if _note_has_any_tags(note, configured_add_card_item_tags()):
        return
    if not add_topic_tags_to_note(note):
        _set_add_card_tag_button_state(editor, _TOPIC_TAG_BUTTON_ID, True)
        return
    _set_editor_tags(editor, _note_tags(note))
    _schedule_editor_tag_widget_sync(editor)
    _set_add_card_tag_button_state(editor, _TOPIC_TAG_BUTTON_ID, True)
    _schedule_add_card_tag_button_refresh(editor)


def _schedule_editor_note_reload(editor) -> None:
    try:
        QTimer.singleShot(0, lambda editor=editor: editor.loadNote())
        QTimer.singleShot(60, lambda editor=editor: editor.loadNote())
    except Exception:
        pass


def _note_has_all_tags(note, wanted_tags: list[str]) -> bool:
    normalized_wanted = {tag.lower() for tag in _normalize_tag_list(wanted_tags)}
    if not normalized_wanted:
        return False
    note_tag_set = {tag.lower() for tag in _note_tags(note)}
    return normalized_wanted.issubset(note_tag_set)


def add_topic_tags_to_note(note) -> bool:
    normalized_tags = configured_add_card_topic_tags()
    if not normalized_tags or note is None:
        return False
    existing_tags = _note_tags(note)
    existing_set = {tag.lower() for tag in existing_tags}
    changed = False
    updated = list(existing_tags)
    for tag in normalized_tags:
        lowered = tag.lower()
        if lowered in existing_set:
            continue
        updated.append(tag)
        existing_set.add(lowered)
        changed = True
    if changed:
        _set_note_tags(note, updated)
    return changed


def copy_source_note_tags_to_note(note, source_note) -> list[str]:
    if note is None or source_note is None or append_missing_tags is None:
        return []
    try:
        updated_tags, added_tags = append_missing_tags(
            getattr(note, "tags", []) or [],
            getattr(source_note, "tags", []) or [],
        )
    except Exception:
        return []
    if not added_tags:
        return []
    _set_note_tags(note, updated_tags)
    return list(added_tags)


def _classification_tag_set() -> set[str]:
    return {
        tag.lower()
        for tag in (
            configured_add_card_topic_tags() + configured_add_card_item_tags()
        )
        if str(tag or "").strip()
    }


def copy_source_tags_to_note(note, source_tags, *, exclude_tags=None) -> list[str]:
    if note is None or append_missing_tags is None:
        return []
    source_list = _normalize_tag_list(source_tags or [])
    excluded = {
        str(tag or "").strip().lower()
        for tag in list(exclude_tags or [])
        if str(tag or "").strip()
    }
    if excluded:
        source_list = [tag for tag in source_list if tag.lower() not in excluded]
    if not source_list:
        return []
    try:
        updated_tags, added_tags = append_missing_tags(
            getattr(note, "tags", []) or [],
            source_list,
        )
    except Exception:
        return []
    if not added_tags:
        return []
    _set_note_tags(note, updated_tags)
    return list(added_tags)


def source_note_tags_for_card(source_card_id: int | None) -> list[str]:
    if source_card_id is None:
        return []
    try:
        source_card = mw.col.get_card(int(source_card_id))
        if source_card is None:
            return []
        source_note = source_card.note()
        return _normalize_tag_list(getattr(source_note, "tags", []) or [])
    except Exception:
        return []


def copy_source_card_tags_to_note(note, source_card_id: int | None, *, exclude_tags=None) -> list[str]:
    if note is None or source_card_id is None:
        return []
    return copy_source_tags_to_note(
        note,
        source_note_tags_for_card(source_card_id),
        exclude_tags=exclude_tags,
    )


def _toggle_note_tag_set(note, wanted_tags: list[str]) -> bool:
    normalized_wanted = _normalize_tag_list(wanted_tags)
    if not normalized_wanted:
        return False

    wanted_set = {tag.lower() for tag in normalized_wanted}
    existing_tags = _note_tags(note)
    existing_set = {tag.lower() for tag in existing_tags}
    has_all = wanted_set.issubset(existing_set)

    if has_all:
        updated = [tag for tag in existing_tags if tag.lower() not in wanted_set]
        _set_note_tags(note, updated)
        return False

    updated = list(existing_tags)
    for tag in normalized_wanted:
        lowered = tag.lower()
        if lowered not in existing_set:
            updated.append(tag)
            existing_set.add(lowered)
    _set_note_tags(note, updated)
    return True


def _activate_exclusive_note_tag_set(
    note,
    wanted_tags: list[str],
    unwanted_tags: list[str] | None = None,
) -> None:
    normalized_wanted = _normalize_tag_list(wanted_tags)
    normalized_unwanted = _normalize_tag_list(unwanted_tags or [])
    if not normalized_wanted:
        return

    unwanted_set = {tag.lower() for tag in normalized_unwanted}
    updated = [
        tag for tag in _note_tags(note)
        if tag.lower() not in unwanted_set
    ]
    existing_set = {tag.lower() for tag in updated}
    for tag in normalized_wanted:
        lowered = tag.lower()
        if lowered in existing_set:
            continue
        updated.append(tag)
        existing_set.add(lowered)
    _set_note_tags(note, updated)


def _ensure_add_card_tag_button_styles(editor) -> None:
    try:
        editor.web.eval(
            """
            (function() {
              var styleId = 'incremento-add-card-tag-buttons-style';
              if (document.getElementById(styleId)) {
                return;
              }
              var style = document.createElement('style');
              style.id = styleId;
              style.textContent = `
                button#incremento-add-card-topic-tag,
                button#incremento-add-card-item-tag {
                  min-width: 28px;
                  padding: 0 9px;
                  font-weight: 800;
                  letter-spacing: 0.02em;
                }
                button#incremento-add-card-topic-tag {
                  margin-left: 10px;
                  color: #5cff95;
                  border-color: rgba(92, 255, 149, 0.25);
                }
                button#incremento-add-card-item-tag {
                  margin-left: 6px;
                  color: #5aa8ff;
                  border-color: rgba(90, 168, 255, 0.25);
                }
                button#incremento-add-card-topic-tag[data-incremento-active="1"] {
                  background: rgba(55, 255, 132, 0.18);
                  color: #72ffab;
                  border-color: rgba(92, 255, 149, 0.58);
                  box-shadow: inset 0 0 0 1px rgba(92, 255, 149, 0.18);
                }
                button#incremento-add-card-item-tag[data-incremento-active="1"] {
                  background: rgba(74, 149, 255, 0.18);
                  color: #76b8ff;
                  border-color: rgba(90, 168, 255, 0.58);
                  box-shadow: inset 0 0 0 1px rgba(90, 168, 255, 0.18);
                }
              `;
              document.head.appendChild(style);
            })();
            """
        )
    except Exception:
        pass


def _set_add_card_tag_button_state(editor, button_id: str, active: bool) -> None:
    try:
        label = "T" if button_id == _TOPIC_TAG_BUTTON_ID else "I"
        title = (
            "Toggle configured topic tags"
            if button_id == _TOPIC_TAG_BUTTON_ID
            else "Toggle configured item tags"
        )
        editor.web.eval(
            f"""
            (function() {{
              var attempts = 0;
              function apply() {{
                var btn = document.getElementById({json.dumps(button_id)});
                if (!btn) {{
                  var buttons = Array.from(document.querySelectorAll('button'));
                  btn = buttons.find(function(candidate) {{
                    return (
                      (candidate.getAttribute('title') || '').indexOf({json.dumps(title)}) !== -1
                      || (candidate.textContent || '').trim() === {json.dumps(label)}
                    );
                  }});
                }}
                if (!btn) {{
                  attempts += 1;
                  if (attempts < 8) {{
                    setTimeout(apply, 60);
                  }}
                  return;
                }}
                btn.setAttribute('data-incremento-active', {json.dumps("1" if active else "0")});
                btn.setAttribute('aria-pressed', {json.dumps("true" if active else "false")});
                if ({json.dumps(bool(active))}) {{
                  btn.style.background = {json.dumps("rgba(55, 255, 132, 0.18)" if button_id == _TOPIC_TAG_BUTTON_ID else "rgba(74, 149, 255, 0.18)")};
                  btn.style.color = {json.dumps("#72ffab" if button_id == _TOPIC_TAG_BUTTON_ID else "#76b8ff")};
                  btn.style.borderColor = {json.dumps("rgba(92, 255, 149, 0.58)" if button_id == _TOPIC_TAG_BUTTON_ID else "rgba(90, 168, 255, 0.58)")};
                }} else {{
                  btn.style.background = '';
                  btn.style.color = '';
                  btn.style.borderColor = '';
                }}
              }}
              apply();
            }})();
            """
        )
    except Exception:
        pass


def _refresh_add_card_tag_buttons_for_editor(editor) -> None:
    note = getattr(editor, "note", None)
    if note is None:
        return
    _ensure_add_card_tag_button_styles(editor)
    _set_add_card_tag_button_state(
        editor,
        _TOPIC_TAG_BUTTON_ID,
        _note_has_all_tags(note, configured_add_card_topic_tags()),
    )
    _set_add_card_tag_button_state(
        editor,
        _ITEM_TAG_BUTTON_ID,
        _note_has_all_tags(note, configured_add_card_item_tags()),
    )


def set_current_extract_options(priority=None, mark_topic=None, link_to_knowledge_tree=None) -> None:
    global _current_extract_priority, _current_extract_mark_topic, _current_extract_link_to_knowledge_tree
    if priority is not None:
        _current_extract_priority = _clamp_priority(priority)
    if mark_topic is not None:
        _current_extract_mark_topic = bool(mark_topic)
    if link_to_knowledge_tree is not None:
        _current_extract_link_to_knowledge_tree = bool(link_to_knowledge_tree)


def _extract_priority_for_transfer() -> float:
    if _current_extract_priority is not None:
        return _clamp_priority(_current_extract_priority)
    return configured_extract_priority()


def _extract_mark_topic_for_transfer() -> bool:
    if _current_extract_mark_topic is not None:
        return bool(_current_extract_mark_topic)
    return configured_extract_mark_topic()


def _extract_link_to_knowledge_tree_for_transfer() -> bool:
    if _current_extract_link_to_knowledge_tree is not None:
        return bool(_current_extract_link_to_knowledge_tree)
    return bool((pending_extract_context() or {}).get("link_to_knowledge_tree"))


def _priority_for_card_id(card_id: int | None) -> float | None:
    if card_id is None:
        return None
    try:
        from ..backend.priority_manager import get_priority
        from ..backend.paths import get_active_profile as _active_profile
    except Exception:
        try:
            from priority_manager import get_priority  # type: ignore
            from paths import get_active_profile as _active_profile  # type: ignore
        except Exception:
            return None
    try:
        return float(get_priority(_ADDON_DIR, _active_profile(), int(card_id)))
    except Exception:
        return None


def _source_card_id_for_transfer(source: str) -> int | None:
    source = str(source or "").strip()
    try:
        if source == "pdf":
            from . import pdf_dock

            return pdf_dock.current_pdf_card_id()
        if source == "epub":
            from . import epub_dock

            return epub_dock.current_epub_card_id()
        if source == "web":
            from . import web_dock

            return web_dock.current_web_card_id()
        if source == "writing":
            from . import writing_dock

            return writing_dock.current_writing_card_id()
        if source == "reviewer":
            reviewer = getattr(mw, "reviewer", None)
            card = getattr(reviewer, "card", None) if reviewer else None
            return int(card.id) if card is not None else None
    except Exception:
        return None
    return None


def source_relative_extract_priority_for_card(card_id: int | None) -> float:
    return calculate_extract_priority(_priority_for_card_id(card_id))


def source_relative_extract_priority_for_source(source: str) -> float:
    return source_relative_extract_priority_for_card(_source_card_id_for_transfer(source))


def set_pending_extract_options(
    *,
    priority=None,
    mark_topic: bool | None = None,
    link_to_knowledge_tree: bool | None = None,
    source: str = "",
    source_card_id: int | None = None,
) -> dict:
    global _pending_extract_options
    resolved_source_card_id = source_card_id
    if resolved_source_card_id is None:
        resolved_source_card_id = _source_card_id_for_transfer(source)
    source_tags = source_note_tags_for_card(resolved_source_card_id)
    _pending_extract_options = {
        "priority": _clamp_priority(
            configured_extract_priority() if priority is None else priority
        ),
        "mark_topic": configured_extract_mark_topic() if mark_topic is None else bool(mark_topic),
        "link_to_knowledge_tree": (
            _extract_link_to_knowledge_tree_for_transfer()
            if link_to_knowledge_tree is None
            else bool(link_to_knowledge_tree)
        ),
        "source": str(source or ""),
        "source_card_id": (
            int(resolved_source_card_id) if resolved_source_card_id is not None else None
        ),
        "source_tags": source_tags,
        "seen": time.monotonic(),
    }
    return dict(_pending_extract_options)


def clear_pending_extract_options() -> None:
    global _pending_extract_options
    _pending_extract_options = None


def pending_extract_options() -> dict | None:
    return dict(_pending_extract_options) if _pending_extract_options else None


def set_pending_extract_context(
    *,
    metadata: dict | None = None,
    parent_card_id: int | None = None,
    knowledge_tree_link_enabled: bool = False,
    link_to_knowledge_tree: bool = False,
    knowledge_tree_tooltip: str = "",
) -> dict:
    global _pending_extract_context
    _pending_extract_context = {
        "metadata": dict(metadata or {}),
        "parent_card_id": int(parent_card_id) if parent_card_id is not None else None,
        "knowledge_tree_link_enabled": bool(knowledge_tree_link_enabled),
        "link_to_knowledge_tree": bool(link_to_knowledge_tree),
        "knowledge_tree_tooltip": str(knowledge_tree_tooltip or ""),
        "seen": time.monotonic(),
    }
    return dict(_pending_extract_context)


def clear_pending_extract_context() -> None:
    global _pending_extract_context
    _pending_extract_context = None


def pending_extract_context() -> dict | None:
    return dict(_pending_extract_context) if _pending_extract_context else None


def sync_pending_extract_options_from_current() -> dict | None:
    source = str(_last_selection_source or "").strip()
    if not source:
        return None
    return set_pending_extract_options(
        priority=_extract_priority_for_transfer(),
        mark_topic=_extract_mark_topic_for_transfer(),
        link_to_knowledge_tree=_extract_link_to_knowledge_tree_for_transfer(),
        source=source,
    )


def recent_fill_source(ttl_sec: float = 30.0) -> str:
    try:
        if time.monotonic() - float(_last_fill_seen) <= float(ttl_sec):
            return str(_last_fill_source or "")
    except Exception:
        pass
    return ""


def _card_ids_for_note(note) -> list[int]:
    note_id = getattr(note, "id", None)
    try:
        cards = note.cards()
        ids = [int(card.id) for card in cards if getattr(card, "id", None) is not None]
        if ids:
            return ids
    except Exception:
        pass
    if note_id is None:
        return []
    try:
        return [int(cid) for cid in mw.col.find_cards(f"nid:{int(note_id)}")]
    except Exception:
        return []


def _save_note_tag_changes(note) -> None:
    try:
        mw.col.update_note(note)
        return
    except Exception:
        pass
    try:
        note.flush()
    except Exception:
        pass


def apply_priority_to_note_cards(note, priority: float) -> int:
    try:
        from ..backend.priority_manager import set_priority
        from ..backend.paths import get_active_profile as _active_profile
    except Exception:
        try:
            from priority_manager import set_priority  # type: ignore
            from paths import get_active_profile as _active_profile  # type: ignore
        except Exception:
            return 0

    changed = 0
    for card_id in _card_ids_for_note(note):
        try:
            set_priority(_ADDON_DIR, _active_profile(), int(card_id), _clamp_priority(priority))
            changed += 1
        except Exception:
            pass
    return changed


def consume_pending_extract_options_for_note(note) -> dict | None:
    options = pending_extract_options()
    if not options:
        return None
    clear_pending_extract_options()
    tags_changed = False
    copied_tags: list[str] = []
    classification_excludes = _classification_tag_set()
    if configured_extract_copy_source_tags():
        copied_tags = copy_source_tags_to_note(
            note,
            options.get("source_tags") or [],
            exclude_tags=classification_excludes,
        )
        if not copied_tags:
            copied_tags = copy_source_card_tags_to_note(
                note,
                options.get("source_card_id"),
                exclude_tags=classification_excludes,
            )
        tags_changed = bool(copied_tags)
    if bool(options.get("mark_topic")) and add_topic_tags_to_note(note):
        tags_changed = True
    if tags_changed:
        _save_note_tag_changes(note)
    changed = apply_priority_to_note_cards(note, float(options.get("priority", 50.0)))
    options["copied_source_tags"] = copied_tags
    options["priority_cards_changed"] = changed
    return options


def consume_pending_extract_context_for_note(note, options: dict | None = None) -> dict | None:
    context = pending_extract_context()
    if not context:
        return None
    clear_pending_extract_context()

    metadata = dict(context.get("metadata") or {})
    metadata_saved = False
    if metadata:
        try:
            from ..backend.note_metadata import (
                apply_incremento_metadata,
                ensure_incremento_metadata_fields,
            )
        except Exception:
            try:
                from note_metadata import apply_incremento_metadata, ensure_incremento_metadata_fields  # type: ignore
            except Exception:
                apply_incremento_metadata = None  # type: ignore
                ensure_incremento_metadata_fields = None  # type: ignore
        if apply_incremento_metadata is not None and ensure_incremento_metadata_fields is not None:
            try:
                ensure_incremento_metadata_fields(mw.col.models, note.note_type() or {})
                apply_incremento_metadata(note, metadata)
                _save_note_tag_changes(note)
                metadata_saved = True
            except Exception as exc:
                context["metadata_error"] = str(exc)

    link_error = ""
    if (
        bool((options or {}).get("link_to_knowledge_tree"))
        and context.get("knowledge_tree_link_enabled")
        and context.get("parent_card_id") is not None
    ):
        try:
            from ..backend.knowledge_tree import (
                NODE_KIND_ITEM,
                NODE_KIND_TOPIC,
                link_card_to_tree,
            )
            from ..backend.paths import get_active_profile as _active_profile
        except Exception:
            try:
                from knowledge_tree import NODE_KIND_ITEM, NODE_KIND_TOPIC, link_card_to_tree  # type: ignore
                from paths import get_active_profile as _active_profile  # type: ignore
            except Exception:
                link_card_to_tree = None  # type: ignore
                _active_profile = None  # type: ignore
                NODE_KIND_ITEM = "item"  # type: ignore
                NODE_KIND_TOPIC = "topic"  # type: ignore
        if link_card_to_tree is not None and _active_profile is not None:
            try:
                created_card_ids = _card_ids_for_note(note)
                if created_card_ids:
                    is_topic = _note_has_all_tags(note, configured_add_card_topic_tags())
                    link_card_to_tree(
                        _ADDON_DIR,
                        _active_profile(),
                        int(created_card_ids[0]),
                        NODE_KIND_TOPIC if is_topic else NODE_KIND_ITEM,
                        parent_card_id=int(context["parent_card_id"]),
                    )
            except Exception as exc:
                link_error = str(exc)

    context["metadata_saved"] = metadata_saved
    context["knowledge_tree_link_error"] = link_error
    return context


def on_add_cards_did_add_note(note) -> None:
    options = consume_pending_extract_options_for_note(note)
    consume_pending_extract_context_for_note(note, options)


def _set_editor_note_type_and_deck(editor, note_type_name: str, deck_name: str) -> None:
    dock = get_add_card_dock()
    dlg = getattr(dock, "_addcards_dialog", None) if dock is not None else None
    if dlg is None or editor is None:
        return

    configured_note_type = str(note_type_name or "").strip()
    if configured_note_type:
        try:
            model = mw.col.models.by_name(configured_note_type)
        except Exception:
            model = None
        if model is not None:
            try:
                dlg.set_note_type(model["id"])
            except Exception:
                pass

    configured_deck = str(deck_name or "").strip()
    if configured_deck:
        try:
            deck = mw.col.decks.by_name(configured_deck)
        except Exception:
            deck = None
        if deck is not None:
            try:
                dlg.set_deck(deck["id"])
            except Exception:
                pass


def _prime_editor_note_for_extract(
    editor,
    field_values: dict[str, str],
    mark_topic: bool,
    source_tags=None,
) -> None:
    note = getattr(editor, "note", None)
    if note is None:
        return
    try:
        for index in range(len(list(getattr(note, "fields", []) or []))):
            note.fields[index] = ""
    except Exception:
        pass
    try:
        note.tags = []
    except Exception:
        pass
    for field_name, value in dict(field_values or {}).items():
        try:
            if field_name in note:
                note[field_name] = str(value or "")
        except Exception:
            pass
    if configured_extract_copy_source_tags():
        copy_source_tags_to_note(note, source_tags or [])
    if mark_topic:
        add_topic_tags_to_note(note)
    try:
        editor.loadNote()
    except Exception:
        pass
    _set_editor_tags(editor, _note_tags(note))
    _schedule_editor_tag_widget_sync(editor)
    _schedule_add_card_tag_button_refresh(editor)


def prepare_reviewer_extract(
    *,
    selected_text: str,
    note_type_name: str,
    deck_name: str,
    field_values: dict[str, str],
    metadata: dict | None,
    parent_card_id: int | None,
    priority: float,
    mark_topic: bool,
    knowledge_tree_link_enabled: bool,
    link_to_knowledge_tree: bool,
    knowledge_tree_tooltip: str = "",
) -> None:
    open_add_card_dock()
    update_selection_state(
        "reviewer",
        text=selected_text,
        has_text=bool(str(selected_text or "").strip()),
    )
    set_current_extract_options(
        priority=priority,
        mark_topic=mark_topic,
        link_to_knowledge_tree=link_to_knowledge_tree,
    )
    set_pending_extract_options(
        priority=priority,
        mark_topic=mark_topic,
        link_to_knowledge_tree=link_to_knowledge_tree,
        source="reviewer",
        source_card_id=parent_card_id,
    )
    tree_state = (
        knowledge_tree_link_state(bool(knowledge_tree_link_enabled))
        if knowledge_tree_link_state is not None
        else {
            "enabled": bool(knowledge_tree_link_enabled),
            "checked": bool(link_to_knowledge_tree),
            "tooltip": str(knowledge_tree_tooltip or ""),
        }
    )
    if knowledge_tree_tooltip:
        tree_state["tooltip"] = knowledge_tree_tooltip
    set_pending_extract_context(
        metadata=metadata,
        parent_card_id=parent_card_id,
        knowledge_tree_link_enabled=bool(tree_state.get("enabled")),
        link_to_knowledge_tree=bool(
            tree_state.get("checked") and link_to_knowledge_tree
        ),
        knowledge_tree_tooltip=str(tree_state.get("tooltip") or ""),
    )
    editor = _dock_editor()
    if editor is None:
        return
    _set_editor_note_type_and_deck(editor, note_type_name, deck_name)
    editor = _dock_editor() or editor
    _prime_editor_note_for_extract(
        editor,
        field_values,
        mark_topic,
        (pending_extract_options() or {}).get("source_tags") or [],
    )
    _inject_transfer_buttons(editor)


def refresh_add_card_tag_buttons() -> None:
    for editor in _iter_tracked_tag_button_editors():
        _refresh_add_card_tag_buttons_for_editor(editor)


def refresh_add_card_dock_controls() -> None:
    _refresh_transfer_buttons()
    refresh_add_card_tag_buttons()


def _toggle_editor_tag_button(
    editor,
    tags: list[str],
    empty_message: str,
    *,
    opposite_tags: list[str] | None = None,
) -> None:
    note = getattr(editor, "note", None)
    if note is None:
        return
    normalized_tags = _normalize_tag_list(tags)
    if not normalized_tags:
        tooltip(empty_message)
        _refresh_add_card_tag_buttons_for_editor(editor)
        return

    current_tags = _editor_tags(editor, note)
    if current_tags != _note_tags(note):
        _set_note_tags(note, current_tags)

    if _note_has_all_tags(note, normalized_tags):
        _toggle_note_tag_set(note, normalized_tags)
    else:
        _activate_exclusive_note_tag_set(note, normalized_tags, opposite_tags)
    _set_editor_tags(editor, _note_tags(note))
    _schedule_editor_tag_widget_sync(editor)
    try:
        if getattr(editor, "tags", None) is not None and hasattr(editor, "on_tag_focus_lost"):
            editor.on_tag_focus_lost()
            _schedule_editor_note_reload(editor)
        elif not getattr(editor, "addMode", False) and hasattr(editor, "_save_current_note"):
            editor._save_current_note()
            _schedule_editor_note_reload(editor)
        else:
            gui_hooks.editor_did_update_tags(note)
    except Exception:
        pass
    if getattr(editor, "addMode", False):
        try:
            gui_hooks.editor_did_update_tags(note)
        except Exception:
            pass
    _refresh_add_card_tag_buttons_for_editor(editor)


def _sync_extract_mark_topic_from_note(note) -> None:
    if note is None:
        return
    mark_topic = _note_has_all_tags(note, configured_add_card_topic_tags())
    item_active = _note_has_all_tags(note, configured_add_card_item_tags())
    if item_active:
        mark_topic = False
    set_current_extract_options(mark_topic=mark_topic)
    sync_pending_extract_options_from_current()
    _refresh_transfer_buttons()


def _on_topic_tag_button(editor) -> None:
    _toggle_editor_tag_button(
        editor,
        configured_add_card_topic_tags(),
        "No Add Card topic-button tags configured.",
        opposite_tags=configured_add_card_item_tags(),
    )
    _sync_extract_mark_topic_from_note(getattr(editor, "note", None))


def _on_item_tag_button(editor) -> None:
    _toggle_editor_tag_button(
        editor,
        configured_add_card_item_tags(),
        "No Add Card item-button tags configured.",
        opposite_tags=configured_add_card_topic_tags(),
    )
    _sync_extract_mark_topic_from_note(getattr(editor, "note", None))


def _add_add_card_tag_toolbar_buttons(buttons, editor) -> None:
    buttons.append(
        editor.addButton(
            None,
            "incrementoToggleTopicTag",
            _on_topic_tag_button,
            tip="Toggle configured topic tags",
            label="T",
            id=_TOPIC_TAG_BUTTON_ID,
            disables=False,
        )
    )
    buttons.append(
        editor.addButton(
            None,
            "incrementoToggleItemTag",
            _on_item_tag_button,
            tip="Toggle configured item tags",
            label="I",
            id=_ITEM_TAG_BUTTON_ID,
            disables=False,
        )
    )


def _on_editor_did_load_note(editor) -> None:
    global _last_add_mode_editor
    note = getattr(editor, "note", None)
    if note is None:
        return
    _track_tag_button_editor(editor)
    if getattr(editor, "addMode", False):
        _last_add_mode_editor = editor
        _inject_transfer_buttons(editor)
    _refresh_add_card_tag_buttons_for_editor(editor)


def _on_editor_did_update_tags(note) -> None:
    for editor in _iter_tracked_tag_button_editors():
        current_note = getattr(editor, "note", None)
        if current_note is None:
            continue
        if current_note is note or getattr(current_note, "id", None) == getattr(note, "id", None):
            if getattr(editor, "addMode", False):
                _sync_extract_mark_topic_from_note(current_note)
            _refresh_add_card_tag_buttons_for_editor(editor)


gui_hooks.editor_did_load_note.append(_on_editor_did_load_note)
gui_hooks.editor_did_init_buttons.append(_add_add_card_tag_toolbar_buttons)
gui_hooks.editor_did_update_tags.append(_on_editor_did_update_tags)


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
    _detach_embedded_window_menu_bar(dlg)
    dlg.setParent(dock)
    dlg.setWindowFlags(Qt.WindowType.Widget)
    dock.setWidget(dlg)
    dock._addcards_dialog = dlg

    mw.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
    _add_card_dock = dock
    dlg.show()
    _apply_configured_extract_notetype()
    _inject_transfer_buttons(dlg.editor)

    def _set_field(idx, text, mark_topic: bool = False):
        note = dlg.editor.note
        if note and idx < len(note.fields):
            existing = note.fields[idx]
            note.fields[idx] = (existing + '<br><br>' + text) if existing else text
            if mark_topic:
                add_topic_tags_to_note(note)
            try:
                dlg.editor.loadNote()
            except Exception:
                pass
            _set_transfer_buttons_visible(dlg.editor, _has_recent_selection())
            if mark_topic:
                _set_editor_tags(dlg.editor, _note_tags(note))
                _schedule_editor_tag_widget_sync(dlg.editor)
                _set_add_card_tag_button_state(dlg.editor, _TOPIC_TAG_BUTTON_ID, True)
                _schedule_add_card_tag_button_refresh(dlg.editor)

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
    mark_topic: bool = False,
):
    global _add_card_dock, _last_fill_source, _last_fill_seen
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
    _last_fill_source = link_kind
    _last_fill_seen = time.monotonic()
    if _add_card_dock is None:
        build_add_card_dock()
        QTimer.singleShot(600, lambda: do_fill(idx, text, mark_topic=mark_topic))
        return
    try:
        _add_card_dock.show()
        _add_card_dock.raise_()
        _apply_configured_extract_notetype()
        do_fill(idx, text, mark_topic=mark_topic)
    except RuntimeError:
        _add_card_dock = None


def do_fill(idx, text, *, mark_topic: bool = False):
    if _add_card_dock is None:
        return
    try:
        _add_card_dock._set_field(idx, text, mark_topic=mark_topic)
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
            _inject_transfer_buttons(editor)
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
    elif source == "epub":
        try:
            from .epub_dock import get_selected_text

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
        priority = (
            _extract_priority_for_transfer()
            if _current_extract_priority is not None
            else source_relative_extract_priority_for_source(resolved_source)
        )
        mark_topic = _extract_mark_topic_for_transfer()
        fill_dock_field(
            idx,
            text,
            include_pdf_citation=(resolved_source == "pdf"),
            source_link_kind=resolved_source if resolved_source in {"pdf", "epub", "web"} else None,
            citation_html=(
                _web_citation()
                if resolved_source == "web"
                else _epub_citation()
            ),
            mark_topic=mark_topic,
        )
        set_pending_extract_options(
            priority=priority,
            mark_topic=mark_topic,
            link_to_knowledge_tree=_extract_link_to_knowledge_tree_for_transfer(),
            source=resolved_source,
        )

    def _web_citation() -> str | None:
        try:
            from .web_dock import web_citation

            return web_citation()
        except Exception:
            return None

    def _epub_citation() -> str | None:
        if source != "epub":
            return None
        try:
            from .epub_dock import epub_citation

            return epub_citation()
        except Exception:
            return None

    _resolve_selection_from_source(source, _apply)
