"""Search ALL dialog — searches PDF/EPUB highlights, sources, content, and cards."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from html import escape, unescape
from urllib.parse import parse_qs, urlparse

from aqt import mw
from aqt.qt import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    Qt,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QTimer, QUrl

try:
    from .latest_query import LatestQuery
    from .search_all_results import AnnotationPreview, run_search, _document_result_url, _highlight_result_url
    from .search_all_preview import PREVIEW_CONTEXT_CHARS, annotation_source_html, annotation_note_html
except ImportError:
    from latest_query import LatestQuery  # type: ignore
    from search_all_results import AnnotationPreview, run_search, _document_result_url, _highlight_result_url  # type: ignore
    from search_all_preview import PREVIEW_CONTEXT_CHARS, annotation_source_html, annotation_note_html  # type: ignore

try:
    from ..backend.i18n import t
except ImportError:
    from backend.i18n import t  # type: ignore

try:
    from ..backend.paths import get_active_profile as _active_profile
except ImportError:
    from paths import get_active_profile as _active_profile

try:
    from ..backend.activity_log import (
        cancel_activity,
        fail_activity,
        finish_activity,
        start_activity,
        update_activity,
    )
except ImportError:
    from activity_log import (  # type: ignore
        cancel_activity,
        fail_activity,
        finish_activity,
        start_activity,
        update_activity,
    )

try:
    from ..backend.db import (
        split_search_terms,
    )
    from ..backend.config_service import load_addon_config, save_addon_config
    from ..backend.pdf_search import PdfIndexDocument, prepare_pdf_index_documents
    from ..backend.search_indexer import index_pdf_documents
    from ..backend.search_repository import (
        epub_section_text,
        pdf_candidate_card_ids,
        pdf_page_text,
    )
    from ..backend.epub_manager import EPUB_NOTE_TYPE, load_epub_metadata
    from ..backend.pdf_manager import PDF_NOTE_TYPE
except ImportError:
    from db import (  # type: ignore
        split_search_terms,
    )
    from config_service import load_addon_config, save_addon_config  # type: ignore
    from pdf_search import PdfIndexDocument, prepare_pdf_index_documents
    from search_indexer import index_pdf_documents  # type: ignore
    from search_repository import (  # type: ignore
        epub_section_text,
        pdf_candidate_card_ids,
        pdf_page_text,
    )
    from epub_manager import EPUB_NOTE_TYPE, load_epub_metadata  # type: ignore
    from pdf_manager import PDF_NOTE_TYPE  # type: ignore


_ADDON_PKG = __name__.split(".")[0]
_MIN_SEARCH_CHARS = 3
_SEARCH_DEBOUNCE_MS = 250
_SEARCH_WHILE_TYPING_CONFIG_KEY = "search_all_search_while_typing"
_SEARCH_ALL_FILTER_CONFIG_KEYS = {
    "annotations": "search_all_filter_annotations",
    "pdf_highlights": "search_all_filter_pdf_highlights",
    "epub_highlights": "search_all_filter_epub_highlights",
    "pdf_sources": "search_all_filter_pdf_sources",
    "epub_sources": "search_all_filter_epub_sources",
    "pdf_content": "search_all_filter_pdf_content",
    "epub_content": "search_all_filter_epub_content",
    "image_ocr": "search_all_filter_image_ocr",
    "cards": "search_all_filter_cards",
    "current_profile": "search_all_filter_current_profile",
}
_SEARCH_ALL_FILTER_DEFAULTS = {
    "annotations": True,
    "pdf_highlights": True,
    "epub_highlights": True,
    "pdf_sources": True,
    "epub_sources": True,
    "pdf_content": False,
    "epub_content": True,
    "image_ocr": True,
    "cards": True,
    "current_profile": True,
}


def _stabilize_search_splitter(splitter, results, preview_container) -> None:
    """Keep asynchronously loaded preview HTML from resizing either pane."""
    horizontal_policy = QSizePolicy.Policy.Ignored
    vertical_policy = QSizePolicy.Policy.Expanding
    results.setSizePolicy(horizontal_policy, vertical_policy)
    preview_container.setSizePolicy(horizontal_policy, vertical_policy)
    splitter.setChildrenCollapsible(False)
    splitter.setStretchFactor(0, 1)
    splitter.setStretchFactor(1, 1)


@dataclass(frozen=True)
class _DocumentPreviewTarget:
    media: str
    card_id: int
    position: int
    query: str
    highlight_text: str | None
    annotation: AnnotationPreview | None = None


def _document_preview_target(
    url: str,
    highlight_previews: dict[str, str | AnnotationPreview],
) -> _DocumentPreviewTarget | None:
    # QTextBrowser can retain HTML entities in an anchor's emitted QUrl.
    # Decode that layer before parsing; query text remains percent-encoded.
    parsed = urlparse(unescape(str(url or "")))
    media = parsed.netloc.lower()
    if parsed.scheme != "inc" or media not in {"pdf", "epub"}:
        return None
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 2:
        return None
    try:
        card_id = int(parts[0])
        position = int(parts[1])
    except (TypeError, ValueError):
        return None
    if card_id <= 0 or position < (1 if media == "pdf" else 0):
        return None

    params = parse_qs(parsed.query)
    query = (params.get("q") or [""])[0]
    highlight_keys = params.get("highlight") or []
    highlight_text: str | None = None
    annotation = None
    if highlight_keys:
        preview_key = str(highlight_keys[0] or "")
        if not preview_key or preview_key not in highlight_previews:
            return None
        preview = highlight_previews[preview_key]
        if isinstance(preview, AnnotationPreview):
            annotation = preview
            highlight_text = preview.note
        else:
            highlight_text = str(preview or "")
    return _DocumentPreviewTarget(
        media=media,
        card_id=card_id,
        position=position,
        query=query,
        highlight_text=highlight_text,
        annotation=annotation,
    )


def _config(config: dict | None = None) -> dict:
    if config is not None:
        return config or {}
    try:
        return load_addon_config(mw.addonManager, _ADDON_PKG)
    except Exception:
        return {}


def configured_search_all_search_while_typing(config: dict | None = None) -> bool:
    cfg = _config(config)
    return bool(cfg.get(_SEARCH_WHILE_TYPING_CONFIG_KEY, True))


def _set_search_all_search_while_typing(enabled: bool) -> None:
    cfg = _config()
    cfg[_SEARCH_WHILE_TYPING_CONFIG_KEY] = bool(enabled)
    try:
        save_addon_config(mw.addonManager, _ADDON_PKG, cfg)
    except Exception:
        return


def configured_search_all_filter_enabled(
    filter_id: str,
    config: dict | None = None,
) -> bool:
    cfg = _config(config)
    key = _SEARCH_ALL_FILTER_CONFIG_KEYS.get(filter_id)
    default = _SEARCH_ALL_FILTER_DEFAULTS.get(filter_id, True)
    if not key:
        return bool(default)
    return bool(cfg.get(key, default))


def _set_search_all_filter_enabled(filter_id: str, enabled: bool) -> None:
    key = _SEARCH_ALL_FILTER_CONFIG_KEYS.get(filter_id)
    if not key:
        return
    cfg = _config()
    cfg[key] = bool(enabled)
    try:
        save_addon_config(mw.addonManager, _ADDON_PKG, cfg)
    except Exception:
        return


class _SearchAllDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        addon_dir: str,
        open_pdf_card,
        open_epub_card,
        initial_query: str = "",
    ):
        super().__init__(parent)
        self._addon_dir = addon_dir
        self._open_pdf_card = open_pdf_card
        self._open_epub_card = open_epub_card
        self._profile = _active_profile()
        self._collection = getattr(mw, "col", None)
        self._highlight_previews: dict[str, str | AnnotationPreview] = {}
        self._pdf_index_cancel = threading.Event()
        self._pdf_index_running = False
        self._pdf_cache_checked = False
        self._pdf_index_attempted = False
        self._pdf_index_generation = 0
        self._pdf_index_activity_id = ""
        self._refresh_after_pdf_index = False
        self._closed = False
        self._search_query = LatestQuery(
            dispatch=self._dispatch_search,
            success=self._search_finished,
            failure=self._search_failed,
            progress=self._search_progress,
            accept=lambda request: (
                self._valid_context() and request["query"] == self._query_text()
            ),
        )
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(_SEARCH_DEBOUNCE_MS)
        self._search_debounce.timeout.connect(
            lambda: self._refresh(self._query_text())
            if self._query_ready() and self._cb_search_while_typing.isChecked()
            else None
        )
        self.setWindowTitle(t("search_all_title"))
        self.resize(1280, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self._search = self.__class__._make_search_box()
        search_row.addWidget(self._search, stretch=1)
        self._search_btn = QPushButton(t("common_search"))
        self._search_btn.clicked.connect(self._run_search)
        search_row.addWidget(self._search_btn)
        self._search_cancel_btn = QPushButton(t("common_cancel"))
        self._search_cancel_btn.clicked.connect(self._cancel_search)
        self._search_cancel_btn.setVisible(False)
        search_row.addWidget(self._search_cancel_btn)
        self._cb_search_while_typing = QCheckBox(t("search_all_while_typing"))
        self._cb_search_while_typing.setChecked(configured_search_all_search_while_typing())
        self._cb_search_while_typing.toggled.connect(self._on_search_while_typing_toggled)
        search_row.addWidget(self._cb_search_while_typing)
        layout.addLayout(search_row)
        self._search_status = QLabel("")
        self._search_status.setVisible(False)
        layout.addWidget(self._search_status)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(16)
        self._cb_highlights = QCheckBox(t("search_all_pdf_highlights"))
        self._cb_epub_highlights = QCheckBox(t("search_all_epub_highlights"))
        self._cb_annotations = QCheckBox(t("search_all_annotations"))
        self._cb_annotations.setToolTip(t("search_all_annotations_tooltip"))
        self._cb_sources = QCheckBox(t("search_all_pdf_sources"))
        self._cb_epub_sources = QCheckBox(t("search_all_epub_sources"))
        self._cb_content = QCheckBox(t("search_all_pdf_content"))
        self._cb_epub_content = QCheckBox(t("search_all_epub_content"))
        self._cb_ocr = QCheckBox(t("search_all_image_ocr"))
        self._cb_cards = QCheckBox(t("search_all_cards"))
        # Keep the legacy config/internal name for saved-setting compatibility.
        # Incremento data is already profile-scoped; this control hides rows
        # whose linked Anki card or source note has since been deleted.
        self._cb_current_profile = QCheckBox(t("search_all_existing_anki_items"))
        self._cb_current_profile.setToolTip(
            t("search_all_existing_anki_items_tooltip")
        )
        self._cb_current_profile.setAccessibleDescription(
            t("search_all_existing_anki_items_accessible")
        )
        self._filter_checkboxes = {
            "annotations": self._cb_annotations,
            "pdf_highlights": self._cb_highlights,
            "epub_highlights": self._cb_epub_highlights,
            "pdf_sources": self._cb_sources,
            "epub_sources": self._cb_epub_sources,
            "pdf_content": self._cb_content,
            "epub_content": self._cb_epub_content,
            "image_ocr": self._cb_ocr,
            "cards": self._cb_cards,
        }
        for filter_id, cb in self._filter_checkboxes.items():
            cb.setChecked(configured_search_all_filter_enabled(filter_id))
            cb.toggled.connect(
                lambda checked, fid=filter_id: self._on_filter_toggled(fid, checked)
            )
            filter_row.addWidget(cb)
        self._cb_current_profile.setChecked(
            configured_search_all_filter_enabled("current_profile")
        )
        self._cb_current_profile.toggled.connect(
            lambda checked: self._on_filter_toggled("current_profile", checked)
        )
        filter_row.addWidget(self._cb_current_profile)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        index_row = QHBoxLayout()
        self._pdf_index_status = QLabel("")
        self._pdf_index_status.setVisible(False)
        index_row.addWidget(self._pdf_index_status, stretch=1)
        self._pdf_index_cancel_btn = QPushButton(t("search_all_cancel_pdf_indexing"))
        self._pdf_index_cancel_btn.setVisible(False)
        self._pdf_index_cancel_btn.clicked.connect(self._cancel_pdf_index)
        index_row.addWidget(self._pdf_index_cancel_btn)
        layout.addLayout(index_row)

        # ── Splitter: results (left) | preview (right) ────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._results = QTextBrowser()
        self._results.setOpenLinks(False)
        self._results.anchorClicked.connect(self._open_link)
        self._results.highlighted[QUrl].connect(self._on_hover)
        splitter.addWidget(self._results)

        # Right: preview panel
        preview_container = QWidget()
        pc_layout = QVBoxLayout(preview_container)
        pc_layout.setContentsMargins(0, 0, 0, 0)
        pc_layout.setSpacing(0)
        self._preview_header = QLabel(t("common_preview"))
        self._preview_header.setStyleSheet(
            "font-size:11px;color:#888;padding:4px 8px;"
            "background:#f5f5f5;border-bottom:1px solid #ddd;"
        )
        pc_layout.addWidget(self._preview_header)
        self._preview = QWebEngineView()
        pc_layout.addWidget(self._preview, stretch=1)
        splitter.addWidget(preview_container)

        _stabilize_search_splitter(splitter, self._results, preview_container)
        splitter.setSizes([620, 560])
        layout.addWidget(splitter, stretch=1)

        close_btn = QPushButton(t("common_close"))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self._search.textChanged.connect(self._on_search_text_changed)
        self._search.returnPressed.connect(self._run_search)
        from aqt import gui_hooks
        self._hooks = gui_hooks
        self._hooks.operation_did_execute.append(self._on_collection_changed)
        self._hooks.profile_will_close.append(self._on_profile_close)
        self.finished.connect(self._dispose_search)
        initial_query = str(initial_query or "").strip()
        if initial_query:
            self._search.setText(initial_query)
            self._run_search()
        else:
            self._update_search_button()
            self._show_search_hint()
            self._show_placeholder()

    @staticmethod
    def _make_search_box():
        from aqt.qt import QLineEdit
        w = QLineEdit()
        w.setPlaceholderText(t("search_all_placeholder"))
        return w

    def _query_text(self) -> str:
        return (self._search.text() or "").strip()

    def _query_ready(self) -> bool:
        return len(self._query_text()) >= _MIN_SEARCH_CHARS

    def _update_search_button(self) -> None:
        self._search_btn.setEnabled(self._query_ready())

    def _show_search_hint(self) -> None:
        self._highlight_previews.clear()
        self._results.setHtml(
            "<div style='color:#888;padding:10px'>"
            f"{escape(t('search_all_minimum_characters', count=_MIN_SEARCH_CHARS))}</div>"
        )

    def _show_manual_search_hint(self) -> None:
        self._highlight_previews.clear()
        self._results.setHtml(
            "<div style='color:#888;padding:10px'>"
            f"{escape(t('search_all_press_search'))}</div>"
        )

    def _on_search_text_changed(self, _text: str) -> None:
        self._invalidate_search()
        self._results.clear()
        self._highlight_previews.clear()
        self._update_search_button()
        if not self._query_ready():
            self._search_debounce.stop()
            self._show_search_hint()
            return
        if self._cb_search_while_typing.isChecked():
            self._search_debounce.start()
        else:
            self._search_debounce.stop()
            self._show_manual_search_hint()

    def _on_search_while_typing_toggled(self, enabled: bool) -> None:
        _set_search_all_search_while_typing(enabled)
        self._maybe_refresh_from_controls()

    def _on_filter_toggled(self, filter_id: str, enabled: bool) -> None:
        _set_search_all_filter_enabled(filter_id, enabled)
        # Category changes apply immediately even when query-as-you-type is off;
        # otherwise results from a newly unchecked category remain on screen.
        self._maybe_refresh_from_controls(force=True)

    def _maybe_refresh_from_controls(self, *, force: bool = False) -> None:
        self._update_search_button()
        if not self._query_ready():
            self._show_search_hint()
            return
        if force or self._cb_search_while_typing.isChecked():
            self._refresh(self._search.text())
        else:
            self._invalidate_search()
            self._show_manual_search_hint()

    def _run_search(self) -> None:
        self._search_debounce.stop()
        self._update_search_button()
        if not self._query_ready():
            self._show_search_hint()
            return
        self._refresh(self._search.text())

    def _valid_context(self) -> bool:
        return (not self._closed and _active_profile() == self._profile
                and getattr(mw, "col", None) is self._collection)

    def _invalidate_search(self) -> None:
        self._search_query.invalidate()
        self._refresh_after_pdf_index = False
        self._search_cancel_btn.setVisible(False)
        self._search_status.setVisible(False)

    def _cancel_search(self) -> None:
        self._search_debounce.stop()
        self._invalidate_search()
        self._search_status.setText(t("search_all_cancelled"))
        self._search_status.setVisible(True)

    def _refresh(self, query: str) -> None:
        if not self._valid_context():
            return
        self._search_debounce.stop()
        self._highlight_previews.clear()
        self._results.clear()
        query = str(query or "").strip()
        if len(query) < _MIN_SEARCH_CHARS:
            self._invalidate_search()
            self._show_search_hint()
            return
        filters = {name for name, checkbox in self._filter_checkboxes.items() if checkbox.isChecked()}
        if self._cb_current_profile.isChecked():
            filters.add("current_profile")
        self._search_status.setText(t("search_all_searching"))
        self._search_status.setVisible(True)
        self._search_cancel_btn.setVisible(True)
        self._refresh_after_pdf_index = True
        self._search_query.submit({
            "addon_dir": self._addon_dir, "profile": self._profile, "collection": self._collection,
            "query": query, "filters": frozenset(filters),
            "check_pdf_cache": not self._pdf_cache_checked,
        })

    def _dispatch_search(self, ticket, success, failure, progress) -> None:
        from concurrent.futures import CancelledError
        from aqt.operations import QueryOp

        request = ticket.payload
        on_main = mw.taskman.run_on_main

        def search(col):
            if ticket.cancel.is_set() or col is not request["collection"]:
                raise CancelledError()
            return run_search(
                request["addon_dir"], request["profile"], col, request["query"], request["filters"],
                cancel=ticket.cancel, check_pdf_cache=request["check_pdf_cache"],
                progress=lambda result: on_main(lambda: progress(result)),
            )

        QueryOp(parent=self, op=search, success=success).failure(failure).run_in_background()

    def _search_progress(self, _request, result) -> None:
        position = self._results.verticalScrollBar().value()
        self._highlight_previews = result.highlight_previews
        self._results.setHtml(result.html)
        self._results.verticalScrollBar().setValue(position)

    def _search_finished(self, request, result) -> None:
        self._search_progress(request, result)
        self._search_cancel_btn.setVisible(False)
        self._search_status.setVisible(False)
        if request["check_pdf_cache"]:
            self._pdf_cache_checked = True
        if result.pdf_reindex_documents:
            if self._pdf_index_running or not self._cb_content.isChecked():
                self._pdf_cache_checked = False
            else:
                self._start_pdf_index(list(result.pdf_reindex_documents))
        elif result.pdf_needs_index:
            self._start_pdf_index()

    def _search_failed(self, _request, error) -> None:
        self._refresh_after_pdf_index = False
        self._search_cancel_btn.setVisible(False)
        self._search_status.setVisible(False)
        self._highlight_previews.clear()
        self._results.setHtml(
            "<div style='padding:8px'>" + escape(t("search_all_failed", error=error)) + "</div>"
        )

    def _on_collection_changed(self, changes, _handler=None) -> None:
        if self._valid_context() and any(
            getattr(changes, name, False) for name in ("note", "card", "deck", "notetype")
        ):
            self._pdf_cache_checked = False
            self._on_search_text_changed(self._query_text())

    def _dispose_search(self, *_args) -> None:
        if self._closed:
            return
        self._closed = True
        self._search_debounce.stop()
        self._search_query.close()
        # Do not mutate the profile-close callback list while it is iterating.
        QTimer.singleShot(0, self._remove_search_hooks)
        if self._pdf_index_running:
            self._cancel_pdf_index()

    def _remove_search_hooks(self) -> None:
        self._hooks.operation_did_execute.remove(self._on_collection_changed)
        self._hooks.profile_will_close.remove(self._on_profile_close)

    def _on_profile_close(self) -> None:
        if self._closed:
            return
        self._dispose_search()
        self.reject()


    def _pdf_title(self, card_id: int) -> str:
        try:
            card = mw.col.get_card(card_id)
            note = mw.col.get_note(card.nid)
            return note.fields[0] if note.fields else t("search_all_pdf_card", card_id=card_id)
        except Exception:
            return t("search_all_pdf_card", card_id=card_id)

    def _epub_title(self, card_id: int) -> str:
        try:
            card = mw.col.get_card(card_id)
            note = mw.col.get_note(card.nid)
            return note.fields[0] if note.fields else t("search_all_epub_card", card_id=card_id)
        except Exception:
            return t("search_all_epub_card", card_id=card_id)

    def _candidate_pdf_card_ids(self, collection, profile: str) -> list[int]:
        cids: set[int] = set()
        try:
            cids.update(collection.find_cards(f'note:"{PDF_NOTE_TYPE}"'))
        except Exception:
            pass
        try:
            cids.update(collection.find_cards("PDF_Filename:*"))
        except Exception:
            pass
        try:
            cids.update(
                pdf_candidate_card_ids(self._addon_dir, profile)
            )
        except Exception:
            pass
        return sorted(cids)

    def _candidate_pdf_documents(self, collection, profile: str) -> list[PdfIndexDocument]:
        return prepare_pdf_index_documents(
            self._addon_dir, profile, collection,
            self._candidate_pdf_card_ids(collection, profile), cancel=self._pdf_index_cancel,
        )

    def _request_pdf_index_cancel(self) -> None:
        self._pdf_index_cancel.set()
        self._pdf_index_status.setText(t("search_all_pdf_index_stopping"))
        self._pdf_index_cancel_btn.setEnabled(False)

    def _cancel_pdf_index(self) -> None:
        if self._pdf_index_activity_id and cancel_activity(
            self._pdf_index_activity_id
        ):
            return
        self._request_pdf_index_cancel()

    def _retry_pdf_index(self, activity_id: str) -> None:
        if self._closed:
            raise RuntimeError("Search ALL is closed.")
        self._pdf_index_running = False
        self._pdf_index_attempted = False
        self._pdf_index_activity_id = str(activity_id or "")
        self._start_pdf_index()

    def _update_pdf_index_progress(
        self,
        generation: int,
        completed: int,
        total: int,
    ) -> None:
        if self._closed or generation != self._pdf_index_generation:
            return
        if self._pdf_index_activity_id:
            update_activity(
                self._pdf_index_activity_id,
                progress=(completed / total) if total > 0 else None,
                detail=t("search_all_pdf_index_progress_detail", completed=completed, total=total),
            )
        self._pdf_index_status.setText(
            t("search_all_pdf_index_progress", completed=completed, total=total)
        )

    def _start_pdf_index(self, documents: list[PdfIndexDocument] | None = None) -> None:
        if (self._pdf_index_running or (self._pdf_index_attempted and documents is None)
                or not self._valid_context()):
            return
        self._pdf_index_attempted = True
        profile = self._profile
        self._pdf_index_running = True
        self._pdf_index_generation += 1
        generation = self._pdf_index_generation
        self._pdf_index_cancel = threading.Event()
        self._pdf_index_status.setText(t("search_all_pdf_index_preparing"))
        self._pdf_index_status.setVisible(True)
        self._pdf_index_cancel_btn.setEnabled(True)
        self._pdf_index_cancel_btn.setVisible(True)
        if self._pdf_index_activity_id:
            update_activity(
                self._pdf_index_activity_id,
                progress=0,
                detail=t("search_all_pdf_index_preparing_detail"),
            )
        else:
            activity_ref: dict[str, str] = {}
            activity_id = start_activity(
                t("search_all_pdf_index_activity"),
                category=t("common_search"),
                detail=t("search_all_pdf_index_preparing_detail"),
                progress=0,
                cancel=self._request_pdf_index_cancel,
                retry=lambda: self._retry_pdf_index(activity_ref["activity_id"]),
            )
            activity_ref["activity_id"] = activity_id
            self._pdf_index_activity_id = activity_id

        def collected(documents: list[PdfIndexDocument]) -> None:
            if generation != self._pdf_index_generation:
                return
            if not self._valid_context():
                self._pdf_index_running = False
                cancel_activity(self._pdf_index_activity_id)
                return
            if self._pdf_index_cancel.is_set():
                self._pdf_index_running = False
                self._pdf_index_cancel_btn.setVisible(False)
                self._pdf_index_status.setText(t("search_all_pdf_index_cancelled"))
                cancel_activity(self._pdf_index_activity_id)
                return
            if not documents:
                self._pdf_index_running = False
                self._pdf_index_cancel_btn.setVisible(False)
                self._pdf_index_status.setText(t("search_all_pdf_index_none"))
                finish_activity(
                    self._pdf_index_activity_id,
                    detail=t("search_all_pdf_index_none_detail"),
                )
                return

            self._pdf_index_status.setText(
                t("search_all_pdf_index_progress", completed=0, total=len(documents))
            )
            self._run_pdf_file_index(
                documents,
                profile=profile,
                generation=generation,
            )

        def collection_failed(_exc: Exception) -> None:
            if generation != self._pdf_index_generation:
                return
            self._pdf_index_running = False
            self._pdf_index_cancel_btn.setVisible(False)
            if not self._closed:
                self._pdf_index_status.setText(
                    t("search_all_pdf_index_prepare_failed")
                )
            fail_activity(
                self._pdf_index_activity_id,
                t("search_all_pdf_index_prepare_failed_detail"),
            )

        if documents is not None:
            collected(documents)
            return

        from aqt.operations import QueryOp

        QueryOp(
            parent=self,
            op=lambda col: self._candidate_pdf_documents(col, profile) if col is self._collection else [],
            success=collected,
        ).failure(collection_failed).run_in_background()

    def _run_pdf_file_index(
        self,
        documents: list[PdfIndexDocument],
        *,
        profile: str,
        generation: int,
    ) -> None:

        def progress(completed: int, total: int) -> None:
            mw.taskman.run_on_main(
                lambda c=completed, t=total: self._update_pdf_index_progress(
                    generation, c, t
                )
            )

        def task():
            return index_pdf_documents(
                self._addon_dir,
                profile,
                documents,
                cancelled=self._pdf_index_cancel.is_set,
                progress=progress,
            )

        def done(future) -> None:
            if generation != self._pdf_index_generation:
                return
            self._pdf_index_running = False
            self._pdf_index_cancel_btn.setVisible(False)
            if self._closed:
                return
            if _active_profile() != profile:
                self._pdf_index_status.setText(
                    t("search_all_pdf_index_previous_profile")
                )
                return
            try:
                result = future.result()
            except Exception:
                self._pdf_index_status.setText(t("search_all_pdf_index_failed"))
                fail_activity(
                    self._pdf_index_activity_id,
                    t("search_all_pdf_index_failed_detail"),
                )
                return
            if result.cancelled:
                self._pdf_index_status.setText(t("search_all_pdf_index_cancelled"))
                cancel_activity(self._pdf_index_activity_id)
            else:
                self._pdf_index_status.setText(
                    t("search_all_pdf_index_ready", updated=result.indexed, failed=result.failed)
                )
                finish_activity(
                    self._pdf_index_activity_id,
                    detail=(
                        t("search_all_pdf_index_ready_detail", updated=result.indexed, failed=result.failed)
                    ),
                )
                if (self._refresh_after_pdf_index and self._query_ready()
                        and self._cb_content.isChecked()):
                    self._refresh(self._query_text())

        mw.taskman.run_in_background(task, done, uses_collection=False)


    def closeEvent(self, event) -> None:
        self._dispose_search()
        super().closeEvent(event)


    # ── Preview panel ─────────────────────────────────────────────────────────

    def _show_placeholder(self) -> None:
        self._preview_header.setText(t("common_preview"))
        self._preview.setHtml(
            "<html><body style='font-family:sans-serif;color:#aaa;"
            f"padding:24px;font-size:13px'>{escape(t('search_all_preview_hover'))}</body></html>"
        )

    def _on_hover(self, url) -> None:
        if not self._valid_context():
            return
        # Qt6: highlighted emits QUrl; Qt5 emits str — handle both
        url_str = url.toString() if hasattr(url, "toString") else str(url)
        if not url_str:
            return
        try:
            if url_str.startswith(("inc://pdf/", "inc://epub/")):
                target = _document_preview_target(url_str, self._highlight_previews)
                if target is None:
                    return
                if target.highlight_text is not None:
                    self._preview_highlight(target)
                elif target.media == "pdf":
                    self._preview_pdf_page(
                        target.card_id,
                        target.position,
                        target.query,
                    )
                else:
                    self._preview_epub_section(
                        target.card_id,
                        target.position,
                        target.query,
                    )
            elif url_str.startswith("inc://card/"):
                nid = int(url_str.rsplit("/", 1)[1])
                self._preview_card(nid)
        except Exception:
            pass

    def _highlight_terms(self, text: str, q: str) -> str:
        """Return HTML-escaped text with query tokens wrapped in <mark>."""
        out = escape(text)
        if not q:
            return out
        for tok in split_search_terms(q):
            out = re.sub(
                rf"(?i)\b({re.escape(escape(tok))}\w*)",
                r"<mark style='background:#ffe08a'>\1</mark>",
                out,
            )
        return out

    def _preview_highlight(self, target: _DocumentPreviewTarget) -> None:
        if target.media == "pdf":
            title = self._pdf_title(target.card_id)
            location = t("search_all_page", page=target.position)
        else:
            title = self._epub_title(target.card_id)
            location = t("search_all_section", section=target.position + 1)
        body = (
            self._highlight_terms(target.highlight_text, target.query)
            if target.highlight_text
            else f"<i style='color:#aaa'>{escape(t('search_all_no_highlight_text'))}</i>"
        )
        if target.annotation is not None:
            if target.annotation.note_html:
                body = annotation_note_html(target.annotation.note, target.annotation.note_html,
                                            lambda text: self._highlight_terms(text, target.query))
            try:
                if target.media == "pdf":
                    page_text = pdf_page_text(self._addon_dir, self._profile, target.card_id, target.position,
                                              max_chars=PREVIEW_CONTEXT_CHARS)
                else:
                    _section_title, page_text = epub_section_text(
                        self._addon_dir, self._profile, target.card_id, target.position,
                        max_chars=PREVIEW_CONTEXT_CHARS,
                    )
            except Exception:
                page_text = ""
            source = annotation_source_html(
                page_text, target.annotation.source_text, target.annotation.color,
            )
            if not source:
                source = f"<i style='color:#777'>{escape(t('search_all_no_highlight_text'))}</i>"
            body = (
                f"<div><b>{escape(t('search_all_annotations'))}</b></div><div>{body}</div>"
                f"<div style='margin-top:18px'><b>{escape(t('reader_highlight'))}</b></div>"
                f"<div style='margin-top:8px'>{source}</div>"
                '<script id="incremento-search-source-scroll">'
                "window.addEventListener('load',function(){"
                "var source=document.getElementById('incremento-search-source');"
                "if(source)source.scrollIntoView({block:'center'});"
                "},{once:true});</script>"
            )
        self._preview_header.setText(
            t("search_all_highlight_preview", media=target.media.upper(), title=title, location=location)
        )
        self._preview.setHtml(
            f"<html><body style='font-family:sans-serif;font-size:13px;"
            f"padding:14px;line-height:1.6;white-space:pre-wrap'>{body}</body></html>"
        )

    def _preview_pdf_page(self, cid: int, page: int, q: str) -> None:
        title = self._pdf_title(cid)
        try:
            text = pdf_page_text(
                self._addon_dir,
                _active_profile(),
                cid,
                page,
            )
        except Exception:
            text = ""

        body = self._highlight_terms(text, q) if text else f"<i style='color:#aaa'>{escape(t('search_all_no_pdf_text'))}</i>"
        self._preview_header.setText(t("search_all_pdf_preview", title=title, page=page))
        self._preview.setHtml(
            f"<html><body style='font-family:sans-serif;font-size:13px;"
            f"padding:14px;line-height:1.6;white-space:pre-wrap'>{body}</body></html>"
        )

    def _preview_card(self, nid: int) -> None:
        try:
            note = mw.col.get_note(nid)
            model = mw.col.models.get(note.mid)
            model_name = escape(model.get("name", t("search_all_note")) if model else t("search_all_note"))
            fld_names = [f.get("name", "") for f in (model.get("flds") or [])] if model else []
            rows = ""
            for i, fval in enumerate(note.fields):
                fname = escape(fld_names[i]) if i < len(fld_names) else escape(t("search_all_field_number", field=i + 1))
                rows += (
                    f"<div style='margin-bottom:10px'>"
                    f"<div style='font-size:11px;color:#888;margin-bottom:2px'>{fname}</div>"
                    f"<div>{fval}</div></div>"
                )
            self._preview_header.setText(t("search_all_card_preview", model_name=model_name, note_id=nid))
            self._preview.setHtml(
                f"<html><body style='font-family:sans-serif;font-size:13px;padding:14px'>"
                f"{rows}</body></html>"
            )
        except Exception:
            pass

    def _preview_epub_section(self, cid: int, section_index: int, q: str) -> None:
        title = self._epub_title(cid)
        try:
            section_title, text = epub_section_text(
                self._addon_dir,
                _active_profile(),
                cid,
                section_index,
            )
        except Exception:
            section_title = ""
            text = ""

        body = self._highlight_terms(text or section_title, q) if (text or section_title) else f"<i style='color:#aaa'>{escape(t('search_all_no_epub_text'))}</i>"
        label = section_title or t("search_all_section", section=section_index + 1)
        self._preview_header.setText(t("search_all_epub_preview", title=title, label=label))
        self._preview.setHtml(
            f"<html><body style='font-family:sans-serif;font-size:13px;"
            f"padding:14px;line-height:1.6;white-space:pre-wrap'>{body}</body></html>"
        )

    def _open_link(self, qurl) -> None:
        if not self._valid_context():
            return
        s = qurl.toString()
        try:
            if s.startswith("inc://pdf/"):
                parsed = urlparse(s)
                parts = parsed.path.strip("/").split("/")
                if len(parts) >= 2:
                    cid = int(parts[0])
                    page = int(parts[1])
                    q = (parse_qs(parsed.query).get("q") or [""])[0]
                    self._open_pdf_card(cid, page, search_query=q)
                return
            if s.startswith("inc://epub/"):
                parsed = urlparse(s)
                parts = parsed.path.strip("/").split("/")
                if len(parts) >= 2:
                    cid = int(parts[0])
                    section_index = int(parts[1])
                    q = (parse_qs(parsed.query).get("q") or [""])[0]
                    self._open_epub_card(cid, section_index, search_query=q)
                return
            if s.startswith("inc://card/"):
                nid = int(s.rsplit("/", 1)[1])
                from aqt import dialogs

                b = dialogs.open("Browser", mw)
                b.search_for(f"nid:{nid}")
                return
        except Exception as e:
            from aqt.utils import showInfo
            showInfo(t("search_all_open_failed", error=e))
