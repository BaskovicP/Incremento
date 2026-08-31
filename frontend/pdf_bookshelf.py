"""Visual bookshelf for opening Incremento PDF and EPUB documents by cover."""

from __future__ import annotations

import os
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from aqt import mw
from aqt.qt import (
    QAbstractItemView,
    QCheckBox,
    QColor,
    QComboBox,
    QCompleter,
    QDialog,
    QEvent,
    QHBoxLayout,
    QIcon,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPalette,
    QPixmap,
    QPushButton,
    QSize,
    QStyle,
    QTimer,
    QVBoxLayout,
    Qt,
    qconnect,
)
from PyQt6.QtPdf import QPdfDocument

try:
    from ..backend.paths import get_active_profile as _active_profile
except ImportError:
    from paths import get_active_profile as _active_profile

try:
    from ..backend.pdf_manager import (
        PDF_COVER_FIELD,
        PDF_NOTE_TYPE,
        pdf_storage_abspath,
    )
    from ..backend.epub_manager import (
        EPUB_COVER_FIELD,
        EPUB_FILE_FIELD,
        EPUB_NOTE_TYPE,
    )
    from ..backend.priority_manager import get_all_priorities
except ImportError:
    from pdf_manager import PDF_COVER_FIELD, PDF_NOTE_TYPE, pdf_storage_abspath  # type: ignore
    from epub_manager import EPUB_COVER_FIELD, EPUB_FILE_FIELD, EPUB_NOTE_TYPE  # type: ignore
    from priority_manager import get_all_priorities  # type: ignore


_PREVIEW_WIDTH = 160
_PREVIEW_HEIGHT = 220
_TILE_WIDTH = 196
_TILE_HEIGHT = 350
_KIND_ALL = "ALL"
_KIND_PDF = "PDF"
_KIND_EPUB = "EPUB"
_TAG_MODE_OR = "OR"
_TAG_MODE_AND = "AND"
_MAX_TAG_FILTER_CHARS = 4_096
_MAX_TAG_FILTER_TERMS = 64
_MAX_TAG_SUGGESTIONS = 10_000


@dataclass(frozen=True)
class _BookshelfEntry:
    title: str
    card_id: int
    kind: str
    cover_filename: str = ""
    source_filename: str = ""
    priority: float | None = None
    tags: tuple[str, ...] = ()


def _bookshelf_theme_colors(background_lightness: int) -> tuple[str, str]:
    """Return readable caption and secondary text colors for the active theme."""
    if int(background_lightness) < 128:
        return "#f4f4f5", "#b8bcc4"
    return "#202124", "#5f6368"


def _note_text(note, field_name: str) -> str:
    try:
        return str(note[field_name] or "").strip()
    except Exception:
        return ""


def _note_tags(note) -> tuple[str, ...]:
    """Return bounded, display-ready note tags without case-folding their labels."""
    try:
        raw_tags = getattr(note, "tags", ()) or ()
    except Exception:
        return ()
    if isinstance(raw_tags, str):
        raw_tags = raw_tags.split()
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw_tag in raw_tags:
        tag = str(raw_tag or "").strip()
        key = tag.casefold()
        if not tag or len(tag) > 512 or key in seen:
            continue
        cleaned.append(tag)
        seen.add(key)
        if len(cleaned) >= 512:
            break
    return tuple(cleaned)


def _parse_bookshelf_tag_query(raw_query: object) -> tuple[str, ...]:
    """Parse a bounded, case-insensitive list of exact Anki tag names."""
    candidate = str(raw_query or "")[:_MAX_TAG_FILTER_CHARS]
    terms: list[str] = []
    seen: set[str] = set()
    for raw_term in re.split(r"[\s,;]+", candidate):
        term = raw_term.strip().casefold()
        if not term or len(term) > 512 or term in seen:
            continue
        terms.append(term)
        seen.add(term)
        if len(terms) >= _MAX_TAG_FILTER_TERMS:
            break
    return tuple(terms)


def _is_bookshelf_tag_delimiter(character: str) -> bool:
    return character in ",;" or character.isspace()


def _bookshelf_tag_token_bounds(query: str, cursor_position: int) -> tuple[int, int]:
    raw_query = str(query or "")
    try:
        cursor = max(0, min(len(raw_query), int(cursor_position)))
    except (TypeError, ValueError):
        cursor = len(raw_query)

    start = cursor
    while start > 0 and not _is_bookshelf_tag_delimiter(raw_query[start - 1]):
        start -= 1

    end = cursor
    while end < len(raw_query) and not _is_bookshelf_tag_delimiter(raw_query[end]):
        end += 1
    return start, end


def _complete_bookshelf_tag_query(
    query: object,
    completion: object,
    cursor_position: int,
) -> tuple[str, int]:
    """Replace only the tag token at the cursor with a selected suggestion."""
    raw_query = str(query or "")
    try:
        cursor = max(0, min(len(raw_query), int(cursor_position)))
    except (TypeError, ValueError):
        cursor = len(raw_query)
    tag = str(completion or "").strip()
    if (
        not tag
        or len(tag) > 512
        or any(_is_bookshelf_tag_delimiter(character) for character in tag)
    ):
        return raw_query, cursor

    start, end = _bookshelf_tag_token_bounds(raw_query, cursor)
    completed_query = f"{raw_query[:start]}{tag}{raw_query[end:]}"
    return completed_query, start + len(tag)


def _bookshelf_tag_suggestions(
    entries: list[_BookshelfEntry],
) -> tuple[str, ...]:
    """Return relevant tags ranked by document frequency, then by name."""
    labels: dict[str, str] = {}
    counts: dict[str, int] = {}
    for entry in entries:
        seen_on_entry: set[str] = set()
        for raw_tag in entry.tags:
            tag = str(raw_tag or "").strip()
            key = tag.casefold()
            if (
                not tag
                or len(tag) > 512
                or key in seen_on_entry
                or any(_is_bookshelf_tag_delimiter(character) for character in tag)
            ):
                continue
            seen_on_entry.add(key)
            if key not in labels:
                if len(labels) >= _MAX_TAG_SUGGESTIONS:
                    continue
                labels[key] = tag
                counts[key] = 0
            counts[key] += 1

    ranked_keys = sorted(
        labels,
        key=lambda key: (-counts[key], labels[key].casefold(), labels[key]),
    )
    return tuple(labels[key] for key in ranked_keys)


class _BookshelfTagCompleter(QCompleter):
    """Complete the active tag token without replacing the whole query."""

    def splitPath(self, path: str) -> list[str]:
        query = str(path or "")
        widget = self.widget()
        try:
            cursor = int(widget.cursorPosition())
        except (AttributeError, RuntimeError, TypeError, ValueError):
            cursor = len(query)
        start, _end = _bookshelf_tag_token_bounds(query, cursor)
        return [query[start:cursor]]

    def pathFromIndex(self, index) -> str:
        completion = str(super().pathFromIndex(index) or "")
        widget = self.widget()
        try:
            query = str(widget.text() or "")
            cursor = int(widget.cursorPosition())
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return completion
        completed_query, completed_cursor = _complete_bookshelf_tag_query(
            query,
            completion,
            cursor,
        )

        def restore_cursor() -> None:
            try:
                if widget.text() == completed_query:
                    widget.setCursorPosition(completed_cursor)
            except (AttributeError, RuntimeError):
                return

        QTimer.singleShot(0, restore_cursor)
        return completed_query


def _load_bookshelf_entries(
    addon_dir: str,
    *,
    collection=None,
) -> list[_BookshelfEntry]:
    """Return every live PDF/EPUB note, including suspended reading cards."""
    col = collection or mw.col
    try:
        all_priorities = get_all_priorities(addon_dir, _active_profile())
    except Exception:
        all_priorities = {}

    entries: list[_BookshelfEntry] = []
    note_specs = (
        (PDF_NOTE_TYPE, _KIND_PDF, PDF_COVER_FIELD, "PDF_Filename"),
        (EPUB_NOTE_TYPE, _KIND_EPUB, EPUB_COVER_FIELD, EPUB_FILE_FIELD),
    )
    for note_type, kind, cover_field, source_field in note_specs:
        try:
            note_ids = col.find_notes(f'note:"{note_type}"')
        except Exception:
            continue
        for note_id in note_ids:
            try:
                note = col.get_note(note_id)
                card_ids = col.find_cards(f"nid:{note_id}")
            except Exception:
                continue
            if not card_ids:
                continue

            try:
                card_id = int(card_ids[0])
            except Exception:
                continue

            title = _note_text(note, "Title")
            if not title:
                fields = getattr(note, "fields", None)
                title = str(fields[0] if fields else note_id).strip()

            entries.append(
                _BookshelfEntry(
                    title=title or str(note_id),
                    card_id=card_id,
                    kind=kind,
                    cover_filename=_note_text(note, cover_field),
                    source_filename=_note_text(note, source_field),
                    priority=all_priorities.get(card_id),
                    tags=_note_tags(note),
                )
            )

    return sorted(entries, key=lambda entry: (entry.title.casefold(), entry.card_id))


def _filter_bookshelf_entries(
    entries: list[_BookshelfEntry],
    query: str,
    kind: str = _KIND_ALL,
    *,
    tag_query: str = "",
    tag_mode: str = _TAG_MODE_OR,
) -> list[_BookshelfEntry]:
    needle = str(query or "").strip().casefold()
    normalized_kind = str(kind or _KIND_ALL).strip().upper()
    requested_tags = _parse_bookshelf_tag_query(tag_query)
    normalized_tag_mode = (
        _TAG_MODE_AND
        if str(tag_mode or "").strip().upper() == _TAG_MODE_AND
        else _TAG_MODE_OR
    )

    def matches_tags(entry: _BookshelfEntry) -> bool:
        if not requested_tags:
            return True
        entry_tags = {
            str(tag or "").strip().casefold()
            for tag in entry.tags
            if str(tag or "").strip()
        }
        if normalized_tag_mode == _TAG_MODE_AND:
            return all(tag in entry_tags for tag in requested_tags)
        return any(tag in entry_tags for tag in requested_tags)

    return [
        entry
        for entry in entries
        if (normalized_kind == _KIND_ALL or entry.kind == normalized_kind)
        and (not needle or needle in entry.title.casefold())
        and matches_tags(entry)
    ]


def _bookshelf_count_text(
    all_entries: list[_BookshelfEntry],
    visible_entries: list[_BookshelfEntry],
    kind: str,
) -> str:
    normalized_kind = str(kind or _KIND_ALL).strip().upper()
    eligible = [
        entry
        for entry in all_entries
        if normalized_kind == _KIND_ALL or entry.kind == normalized_kind
    ]
    total = len(eligible)
    visible = len(visible_entries)
    if normalized_kind == _KIND_ALL:
        plural_label = "documents"
        count_label = "document" if total == 1 else "documents"
    else:
        plural_label = f"{normalized_kind}s"
        count_label = normalized_kind if total == 1 else plural_label
    if not total:
        return f"No Incremento {plural_label} found."
    if visible != total:
        return f"Showing {visible} of {total} {count_label}"
    if normalized_kind == _KIND_ALL:
        pdf_count = sum(entry.kind == _KIND_PDF for entry in eligible)
        epub_count = sum(entry.kind == _KIND_EPUB for entry in eligible)
        pdf_label = f"{pdf_count} PDF{'s' if pdf_count != 1 else ''}"
        epub_label = f"{epub_count} EPUB{'s' if epub_count != 1 else ''}"
        return f"{total} {count_label} · {pdf_label} · {epub_label}"
    return f"{total} {count_label}"


def _existing_media_preview_path(media_dir: str, cover_filename: str) -> str:
    """Resolve an Anki media preview without allowing it to escape media.dir()."""
    raw = str(cover_filename or "").strip()
    if not raw or not media_dir:
        return ""
    try:
        root = Path(media_dir).resolve()
        candidate = (root / raw).resolve()
        candidate.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return ""
    return str(candidate) if candidate.is_file() else ""


def _render_pdf_first_page(pdf_path: str, render_width: int = _PREVIEW_WIDTH):
    """Render one small first-page image; safe to call in Anki's task worker."""
    if not pdf_path or not os.path.isfile(pdf_path):
        return None
    doc = QPdfDocument(None)
    try:
        doc.load(pdf_path)
        if doc.pageCount() <= 0:
            return None
        page_size = doc.pagePointSize(0)
        page_width = float(page_size.width() or 0)
        page_height = float(page_size.height() or 0)
        render_height = int(render_width * 1.414)
        if page_width > 0 and page_height > 0:
            render_height = max(1, int(render_width * page_height / page_width))
        image = doc.render(0, QSize(render_width, render_height))
        return image if image is not None and not image.isNull() else None
    except Exception:
        return None
    finally:
        doc.close()


class _DocumentBookshelfDialog(QDialog):
    """A searchable, progressively loaded grid of PDF and EPUB covers."""

    def __init__(
        self,
        parent=None,
        *,
        addon_dir: str,
        last_opened_card_id: int | None = None,
        entries: list[_BookshelfEntry] | None = None,
    ):
        super().__init__(parent)
        self._entries = (
            list(entries)
            if entries is not None
            else _load_bookshelf_entries(addon_dir)
        )
        self._last_opened_card_id = last_opened_card_id
        self._thumbnail_generation = 0
        self._thumbnail_queue: deque[tuple[QListWidgetItem, _BookshelfEntry]] = deque()
        self._thumbnail_cache: dict[tuple[str, int], QIcon] = {}
        try:
            self._media_dir = str(mw.col.media.dir() or "")
        except Exception:
            self._media_dir = ""

        self.setWindowTitle("Document Bookshelf")
        self.resize(1080, 760)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("<b>Document Bookshelf</b>")
        title.setStyleSheet("font-size: 20px;")
        layout.addWidget(title)

        hint = QLabel(
            "Click a cover to open that document. PDF first pages and EPUB "
            "covers load progressively so a large library stays responsive."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        kind_row = QHBoxLayout()
        kind_row.addWidget(QLabel("Show:"))
        self._kind_combo = QComboBox()
        self._kind_combo.addItem("All documents", _KIND_ALL)
        self._kind_combo.addItem("PDFs", _KIND_PDF)
        self._kind_combo.addItem("EPUBs", _KIND_EPUB)
        kind_row.addWidget(self._kind_combo)
        kind_row.addStretch(1)
        layout.addLayout(kind_row)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search document titles…")
        self._search.setClearButtonEnabled(True)
        layout.addWidget(self._search)

        tag_row = QHBoxLayout()
        tag_row.addWidget(QLabel("Tags:"))
        self._tag_search = QLineEdit()
        self._tag_search.setPlaceholderText(
            "Filter by tags — type a name or browse available tags…"
        )
        self._tag_search.setClearButtonEnabled(True)
        self._tag_search.setMaxLength(_MAX_TAG_FILTER_CHARS)
        self._tag_search.setToolTip(
            "Start typing any part of a tag name, or browse tags used by these "
            "documents. Matching ignores uppercase/lowercase."
        )
        self._tag_search.setAccessibleName("Bookshelf tag filter")
        tag_row.addWidget(self._tag_search, 1)

        tag_suggestions = _bookshelf_tag_suggestions(self._entries)
        self._tag_completer = _BookshelfTagCompleter(
            list(tag_suggestions),
            self._tag_search,
        )
        self._tag_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._tag_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._tag_completer.setCompletionMode(
            QCompleter.CompletionMode.PopupCompletion
        )
        self._tag_completer.setMaxVisibleItems(12)
        self._tag_search.setCompleter(self._tag_completer)

        self._browse_tags_button = QPushButton("Browse tags")
        self._browse_tags_button.setAccessibleName("Browse bookshelf tags")
        self._browse_tags_button.setEnabled(bool(tag_suggestions))
        self._browse_tags_button.setToolTip(
            "Show tags used by documents in this bookshelf, with the most common "
            "tags first."
            if tag_suggestions
            else "No document tags are available."
        )
        tag_row.addWidget(self._browse_tags_button)

        self._tag_mode_combo = QComboBox()
        self._tag_mode_combo.addItem("Any tag (OR)", _TAG_MODE_OR)
        self._tag_mode_combo.addItem("All tags (AND)", _TAG_MODE_AND)
        self._tag_mode_combo.setToolTip(
            "OR matches at least one entered tag; AND requires every entered tag."
        )
        tag_row.addWidget(self._tag_mode_combo)
        layout.addLayout(tag_row)

        self._count_label = QLabel("")
        try:
            background_lightness = self.palette().color(
                QPalette.ColorRole.Window
            ).lightness()
        except Exception:
            background_lightness = 255
        self._caption_color, muted_color = _bookshelf_theme_colors(
            background_lightness
        )
        self._count_label.setStyleSheet(f"color: {muted_color};")
        layout.addWidget(self._count_label)

        self._list = QListWidget()
        self._list.setViewMode(QListView.ViewMode.IconMode)
        self._list.setResizeMode(QListView.ResizeMode.Adjust)
        self._list.setMovement(QListView.Movement.Static)
        self._list.setWrapping(True)
        self._list.setWordWrap(True)
        self._list.setUniformItemSizes(True)
        self._list.setSpacing(8)
        self._list.setIconSize(QSize(_PREVIEW_WIDTH, _PREVIEW_HEIGHT))
        self._list.setGridSize(QSize(_TILE_WIDTH, _TILE_HEIGHT))
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._list.setStyleSheet(
            "QListWidget::item {"
            f" color: {self._caption_color};"
            " padding: 4px;"
            "}"
            "QListWidget::item:selected {"
            f" color: {self._caption_color};"
            "}"
        )
        layout.addWidget(self._list, 1)

        self._preserve_history_cb = QCheckBox(
            "Don't change cards attached to PDF reading history (PDFs only)"
        )
        self._preserve_history_cb.setChecked(False)
        layout.addWidget(self._preserve_history_cb)

        self._study_card_cb = QCheckBox("Open the card also to study")
        self._study_card_cb.setChecked(False)
        layout.addWidget(self._study_card_cb)

        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel_button = QPushButton("Cancel")
        qconnect(cancel_button.clicked, self.reject)
        footer.addWidget(cancel_button)
        layout.addLayout(footer)

        qconnect(self._search.textChanged, self._refresh)
        qconnect(self._kind_combo.currentIndexChanged, self._refresh)
        qconnect(self._tag_search.textChanged, self._refresh)
        qconnect(self._tag_mode_combo.currentIndexChanged, self._refresh)
        qconnect(self._browse_tags_button.clicked, self._show_tag_suggestions)
        qconnect(self._search.returnPressed, self._accept_current)
        qconnect(self._tag_search.returnPressed, self._accept_current)
        qconnect(self._list.itemClicked, self._accept_item)
        qconnect(self._list.itemActivated, self._accept_item)
        qconnect(self._list.currentItemChanged, self._update_option_availability)
        self._search.installEventFilter(self)
        self._tag_search.installEventFilter(self)

        self._refresh()
        self._search.setFocus()

    def eventFilter(self, watched, event):
        if (
            watched in (self._search, self._tag_search)
            and event.type() == QEvent.Type.KeyPress
        ):
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self._list.count():
                self._list.setFocus()
                return True
        return super().eventFilter(watched, event)

    def _current_kind(self) -> str:
        kind = self._kind_combo.currentData()
        return str(kind or _KIND_ALL).strip().upper()

    def _current_tag_mode(self) -> str:
        mode = self._tag_mode_combo.currentData()
        return (
            _TAG_MODE_AND
            if str(mode or "").strip().upper() == _TAG_MODE_AND
            else _TAG_MODE_OR
        )

    def _show_tag_suggestions(self) -> None:
        self._tag_search.setFocus()
        query = self._tag_search.text()
        cursor = self._tag_search.cursorPosition()
        start, _end = _bookshelf_tag_token_bounds(query, cursor)
        self._tag_completer.setCompletionPrefix(query[start:cursor])
        completion_model = self._tag_completer.completionModel()
        if completion_model.rowCount() <= 0:
            return
        popup = self._tag_completer.popup()
        popup.setCurrentIndex(completion_model.index(0, 0))
        self._tag_completer.complete()

    def _refresh(self, *_args) -> None:
        kind = self._current_kind()
        visible_entries = _filter_bookshelf_entries(
            self._entries,
            self._search.text(),
            kind,
            tag_query=self._tag_search.text(),
            tag_mode=self._current_tag_mode(),
        )
        self._thumbnail_generation += 1
        generation = self._thumbnail_generation
        self._thumbnail_queue.clear()
        self._list.clear()

        placeholder = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        selected_item = None
        for entry in visible_entries:
            item = QListWidgetItem(entry.title)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
            )
            item.setForeground(QColor(self._caption_color))
            title_font = item.font()
            title_font.setBold(True)
            item.setFont(title_font)
            # QListView's icon mode can ignore gridSize() for the item's own
            # paint rectangle, which clips the text directly beneath tall
            # covers. An explicit size hint reserves a real caption area.
            item.setSizeHint(QSize(_TILE_WIDTH, _TILE_HEIGHT))
            priority_text = (
                f"Priority: {int(round(entry.priority))}"
                if entry.priority is not None
                else "Priority: not set"
            )
            visible_tags = entry.tags[:20]
            tags_text = ", ".join(visible_tags) if visible_tags else "none"
            if len(entry.tags) > len(visible_tags):
                tags_text += f" (+{len(entry.tags) - len(visible_tags)} more)"
            item.setToolTip(
                f"{entry.title}\nType: {entry.kind}\nTags: {tags_text}\n"
                f"{priority_text}\nClick to open"
            )
            cache_key = (entry.kind, entry.card_id)
            cached = self._thumbnail_cache.get(cache_key)
            item.setIcon(cached or placeholder)
            self._list.addItem(item)
            if cached is None:
                self._thumbnail_queue.append((item, entry))
            if entry.card_id == self._last_opened_card_id:
                selected_item = item

        self._count_label.setText(
            _bookshelf_count_text(self._entries, visible_entries, kind)
        )

        if selected_item is None and self._list.count():
            selected_item = self._list.item(0)
        if selected_item is not None:
            self._list.setCurrentItem(selected_item)
            self._list.scrollToItem(selected_item)
        self._update_option_availability()

        QTimer.singleShot(0, lambda current=generation: self._load_next_thumbnail(current))

    def _load_next_thumbnail(self, generation: int) -> None:
        if generation != self._thumbnail_generation or not self.isVisible():
            return

        while self._thumbnail_queue:
            item, entry = self._thumbnail_queue.popleft()
            cover_path = _existing_media_preview_path(
                self._media_dir,
                entry.cover_filename,
            )
            if cover_path:
                pixmap = QPixmap(cover_path)
                if not pixmap.isNull():
                    self._set_thumbnail(item, entry, QIcon(pixmap), generation)
                    QTimer.singleShot(
                        0,
                        lambda current=generation: self._load_next_thumbnail(current),
                    )
                    return

            # EPUB imports already persist their extracted cover in Anki media.
            # Only PDFs have a safe, lightweight first-page fallback renderer.
            if entry.kind != _KIND_PDF:
                continue
            try:
                source_path = pdf_storage_abspath(entry.source_filename)
            except Exception:
                source_path = ""
            if not source_path or not os.path.isfile(source_path):
                continue

            def render(path=source_path):
                return _render_pdf_first_page(path)

            def finished(future, current_item=item, current_entry=entry, current=generation):
                if current != self._thumbnail_generation or not self.isVisible():
                    return
                try:
                    image = future.result()
                except Exception:
                    image = None
                if image is not None:
                    self._set_thumbnail(
                        current_item,
                        current_entry,
                        QIcon(QPixmap.fromImage(image)),
                        current,
                    )
                QTimer.singleShot(
                    0,
                    lambda active=current: self._load_next_thumbnail(active),
                )

            taskman = getattr(mw, "taskman", None)
            if taskman is not None and hasattr(taskman, "run_in_background"):
                taskman.run_in_background(render, finished)
                return

            image = render()
            if image is not None:
                self._set_thumbnail(item, entry, QIcon(QPixmap.fromImage(image)), generation)

        # No preview is available for remaining placeholder entries.

    def _set_thumbnail(
        self,
        item: QListWidgetItem,
        entry: _BookshelfEntry,
        icon: QIcon,
        generation: int,
    ) -> None:
        if generation != self._thumbnail_generation:
            return
        current_entry = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(current_entry, _BookshelfEntry):
            return
        if (current_entry.kind, current_entry.card_id) != (
            entry.kind,
            entry.card_id,
        ):
            return
        self._thumbnail_cache[(entry.kind, entry.card_id)] = icon
        item.setIcon(icon)

    def _accept_item(self, item: QListWidgetItem) -> None:
        entry = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if isinstance(entry, _BookshelfEntry):
            self._list.setCurrentItem(item)
            self.accept()

    def _accept_current(self) -> None:
        item = self._list.currentItem()
        if item is not None:
            self._accept_item(item)

    def _selected_entry(self) -> _BookshelfEntry | None:
        item = self._list.currentItem()
        entry = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return entry if isinstance(entry, _BookshelfEntry) else None

    def _update_option_availability(self, *_args) -> None:
        entry = self._selected_entry()
        is_pdf = entry is not None and entry.kind == _KIND_PDF
        self._preserve_history_cb.setEnabled(is_pdf)
        self._preserve_history_cb.setToolTip(
            "Keeps PDF-linked card history unchanged while opening the reader."
            if is_pdf
            else "This option applies only to PDF documents."
        )

    @property
    def selected_card_id(self) -> int | None:
        entry = self._selected_entry()
        return int(entry.card_id) if entry is not None else None

    @property
    def selected_card_type(self) -> str:
        entry = self._selected_entry()
        return str(entry.kind) if entry is not None else ""

    @property
    def preserve_history(self) -> bool:
        return bool(
            self.selected_card_type == _KIND_PDF
            and self._preserve_history_cb.isChecked()
        )

    @property
    def open_card_to_study(self) -> bool:
        return bool(self._study_card_cb.isChecked())
