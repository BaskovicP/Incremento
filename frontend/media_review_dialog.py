"""Shared picker for reviewing cards attached to reader media."""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping

from aqt import mw
from aqt.qt import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    qconnect,
)
from aqt.utils import showInfo

try:
    from ..backend.media_review import (
        MEDIA_KIND_EPUB,
        MEDIA_KIND_PDF,
        MEDIA_KIND_VIDEO,
        MEDIA_REVIEW_CARD_KIND_BOTH,
        MEDIA_REVIEW_CARD_KIND_OPTIONS,
        MEDIA_REVIEW_ORDER_ATTACHED,
        MEDIA_REVIEW_ORDER_OPTIONS,
        MEDIA_REVIEW_RANGE_ALL,
        MEDIA_REVIEW_RANGE_OPTIONS,
        MEDIA_REVIEW_STATE_ALL,
        MEDIA_REVIEW_STATE_OPTIONS,
        MEDIA_REVIEW_TREE_NESTED,
        MEDIA_REVIEW_TREE_OPTIONS,
        inspect_linked_media_review_rows,
        linked_media_review_card_ids,
        normalize_media_kind,
        normalize_media_review_card_kind,
        normalize_media_review_limit,
        normalize_media_review_order,
        normalize_media_review_range,
        normalize_media_review_state,
        normalize_media_review_tree_scope,
        select_linked_media_review_rows,
    )
    from ..backend.session import (
        record_media_review_inspection_failed,
        record_media_review_inspection_finished,
        record_media_review_inspection_started,
        start_explicit_review_from_selector,
    )
    from ..backend.topic_scheduler import resolve_topic_card_classifier
except ImportError:
    from media_review import (  # type: ignore
        MEDIA_KIND_EPUB,
        MEDIA_KIND_PDF,
        MEDIA_KIND_VIDEO,
        MEDIA_REVIEW_CARD_KIND_BOTH,
        MEDIA_REVIEW_CARD_KIND_OPTIONS,
        MEDIA_REVIEW_ORDER_ATTACHED,
        MEDIA_REVIEW_ORDER_OPTIONS,
        MEDIA_REVIEW_RANGE_ALL,
        MEDIA_REVIEW_RANGE_OPTIONS,
        MEDIA_REVIEW_STATE_ALL,
        MEDIA_REVIEW_STATE_OPTIONS,
        MEDIA_REVIEW_TREE_NESTED,
        MEDIA_REVIEW_TREE_OPTIONS,
        inspect_linked_media_review_rows,
        linked_media_review_card_ids,
        normalize_media_kind,
        normalize_media_review_card_kind,
        normalize_media_review_limit,
        normalize_media_review_order,
        normalize_media_review_range,
        normalize_media_review_state,
        normalize_media_review_tree_scope,
        select_linked_media_review_rows,
    )
    from session import (  # type: ignore
        record_media_review_inspection_failed,
        record_media_review_inspection_finished,
        record_media_review_inspection_started,
        start_explicit_review_from_selector,
    )
    from topic_scheduler import resolve_topic_card_classifier  # type: ignore


_last_options_by_media_kind: dict[str, dict] = {}


def _default_options() -> dict:
    return {
        "order": MEDIA_REVIEW_ORDER_ATTACHED,
        "card_kind": MEDIA_REVIEW_CARD_KIND_BOTH,
        "tree_scope": MEDIA_REVIEW_TREE_NESTED,
        "media_range": MEDIA_REVIEW_RANGE_ALL,
        "state": MEDIA_REVIEW_STATE_ALL,
        "limit": 0,
    }


def _normalized_options(options: dict | None) -> dict:
    raw = dict(options or {})
    return {
        "order": normalize_media_review_order(raw.get("order")),
        "card_kind": normalize_media_review_card_kind(raw.get("card_kind")),
        "tree_scope": normalize_media_review_tree_scope(raw.get("tree_scope")),
        "media_range": normalize_media_review_range(raw.get("media_range")),
        "state": normalize_media_review_state(raw.get("state")),
        "limit": normalize_media_review_limit(raw.get("limit")),
    }


def _media_position_label(media_kind: str, value) -> str:
    try:
        position = max(0.0, float(value))
    except Exception:
        return ""
    if media_kind == MEDIA_KIND_PDF:
        return f"page {max(1, int(position))}"
    if media_kind == MEDIA_KIND_EPUB:
        return f"section {int(position) + 1}"
    if media_kind == MEDIA_KIND_VIDEO:
        total_seconds = int(position)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours:d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:d}:{seconds:02d}"
    return ""


def format_media_review_preview(summary: dict) -> str:
    selected = int(summary.get("selected_count", 0) or 0)
    topics = int(summary.get("topic_count", 0) or 0)
    items = int(summary.get("item_count", 0) or 0)
    first_line = (
        f"Ready to review: {selected} card{'s' if selected != 1 else ''} "
        f"({topics} topic{'s' if topics != 1 else ''}, "
        f"{items} item{'s' if items != 1 else ''})."
    )

    exclusions = dict(summary.get("exclusions") or {})
    labels = (
        ("suspended", "suspended"),
        ("buried", "buried"),
        ("filtered", "already in another filtered deck"),
        ("missing", "missing"),
        ("nested", "nested"),
        ("beyond_current", "after the current position"),
        ("unknown_position", "without a known media position"),
        ("other_kind", "outside the chosen Topic/Item type"),
        ("not_due", "not due now"),
        ("limit", "past the review limit"),
    )
    excluded_parts = [
        f"{int(exclusions.get(key, 0) or 0)} {label}"
        for key, label in labels
        if int(exclusions.get(key, 0) or 0) > 0
    ]
    if not excluded_parts:
        return first_line
    return first_line + "\nExcluded: " + ", ".join(excluded_parts) + "."


def _set_combo_value(combo: QComboBox, value: str) -> None:
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)


def _run_media_review_query(*, parent, op, success, failure) -> None:
    """Run the potentially large linked-card scan away from Qt's UI thread."""
    from aqt.operations import QueryOp

    (
        QueryOp(parent=parent, op=op, success=success)
        .failure(failure)
        .with_progress("Inspecting attached cards…")
        .run_in_background()
    )


class MediaAttachedReviewDialog(QDialog):
    def __init__(
        self,
        parent,
        *,
        media_label: str,
        media_kind: str,
        preview_rows: Iterable[dict],
        current_position=None,
        initial_options: dict | None = None,
        random_seed: int | None = None,
    ):
        super().__init__(parent)
        label = str(media_label or "media").strip() or "media"
        self._media_kind = normalize_media_kind(media_kind)
        self._preview_rows = [dict(row) for row in list(preview_rows or [])]
        self._current_position = current_position
        self._random_seed = random_seed
        options = _normalized_options(initial_options or _default_options())

        self.setWindowTitle(f"Review Cards from This {label}")
        self.setModal(True)
        self.resize(560, 360)

        layout = QVBoxLayout(self)
        summary = QLabel(
            f"Choose which cards attached to this {label} to review. "
            "Direct links include cards extracted from the media; nested links "
            "include their knowledge-tree descendants. Reviews use normal Anki "
            "scheduling."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        form = QFormLayout()

        self._card_kind_combo = QComboBox(self)
        for value, option_label in MEDIA_REVIEW_CARD_KIND_OPTIONS:
            self._card_kind_combo.addItem(option_label, value)
        _set_combo_value(self._card_kind_combo, options["card_kind"])
        self._card_kind_combo.setToolTip(
            "Topic and Item classification uses the same Incremento rules as the reviewer."
        )
        form.addRow("Review:", self._card_kind_combo)

        self._tree_scope_combo = QComboBox(self)
        for value, option_label in MEDIA_REVIEW_TREE_OPTIONS:
            self._tree_scope_combo.addItem(option_label, value)
        _set_combo_value(self._tree_scope_combo, options["tree_scope"])
        form.addRow("Links:", self._tree_scope_combo)

        self._range_combo = QComboBox(self)
        for value, option_label in MEDIA_REVIEW_RANGE_OPTIONS:
            self._range_combo.addItem(option_label, value)
        _set_combo_value(self._range_combo, options["media_range"])
        current_label = _media_position_label(self._media_kind, current_position)
        if current_label:
            self._range_combo.setToolTip(
                f"The current {label} position is {current_label}. Cards without a "
                "known position are excluded when this range is selected."
            )
        else:
            _set_combo_value(self._range_combo, MEDIA_REVIEW_RANGE_ALL)
            self._range_combo.setEnabled(False)
            self._range_combo.setToolTip(
                "Incremento could not determine a current media position for this reader."
            )
        form.addRow("Media range:", self._range_combo)

        self._state_combo = QComboBox(self)
        for value, option_label in MEDIA_REVIEW_STATE_OPTIONS:
            self._state_combo.addItem(option_label, value)
        _set_combo_value(self._state_combo, options["state"])
        self._state_combo.setToolTip(
            "Due only includes due review cards and learning/relearning cards ready now; "
            "new and future cards stay out."
        )
        form.addRow("Card state:", self._state_combo)

        self._order_combo = QComboBox(self)
        for value, option_label in MEDIA_REVIEW_ORDER_OPTIONS:
            self._order_combo.addItem(option_label, value)
        _set_combo_value(self._order_combo, options["order"])
        self._order_combo.setToolTip(
            "Media position uses PDF pages, EPUB sections, or video timestamps. "
            "Nested cards inherit their nearest positioned ancestor."
        )
        form.addRow("Review order:", self._order_combo)

        self._limit_spin = QSpinBox(self)
        self._limit_spin.setRange(0, 9999)
        self._limit_spin.setSpecialValueText("All")
        self._limit_spin.setValue(options["limit"])
        self._limit_spin.setToolTip(
            "Limit the number of cards after filtering and ordering. All means no limit."
        )
        form.addRow("Maximum cards:", self._limit_spin)
        layout.addLayout(form)

        self._preview_label = QLabel("")
        self._preview_label.setWordWrap(True)
        layout.addWidget(self._preview_label)

        buttons = QDialogButtonBox(self)
        self._review_button = buttons.addButton(
            "Start Review",
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        cancel_button = buttons.addButton(
            "Cancel",
            QDialogButtonBox.ButtonRole.RejectRole,
        )
        qconnect(self._review_button.clicked, self.accept)
        qconnect(cancel_button.clicked, self.reject)
        layout.addWidget(buttons)

        for combo in (
            self._card_kind_combo,
            self._tree_scope_combo,
            self._range_combo,
            self._state_combo,
            self._order_combo,
        ):
            qconnect(combo.currentIndexChanged, self._refresh_preview)
        qconnect(self._limit_spin.valueChanged, self._refresh_preview)
        self._refresh_preview()

    def selected_options(self) -> dict:
        return _normalized_options(
            {
                "order": self._order_combo.currentData(),
                "card_kind": self._card_kind_combo.currentData(),
                "tree_scope": self._tree_scope_combo.currentData(),
                "media_range": self._range_combo.currentData(),
                "state": self._state_combo.currentData(),
                "limit": self._limit_spin.value(),
            }
        )

    def selection_summary(self) -> dict:
        return select_linked_media_review_rows(
            self._preview_rows,
            current_position=self._current_position,
            random_seed=self._random_seed,
            **self.selected_options(),
        )

    def _refresh_preview(self, *_args) -> None:
        selection = self.selection_summary()
        count = int(selection.get("selected_count", 0) or 0)
        self._preview_label.setText(format_media_review_preview(selection))
        self._review_button.setEnabled(count > 0)
        self._review_button.setText(
            f"Review {count} Card{'s' if count != 1 else ''}" if count else "No Cards"
        )


def start_attached_media_review(
    *,
    addon_dir: str,
    profile: str,
    source_card_id: int,
    media_label: str,
    media_kind: str = "",
    deck_name: str,
    current_position=None,
    linked_source_rows: Iterable[dict] | None = None,
    linked_note_ids: Iterable[int] | None = None,
    linked_card_ids: Iterable[int] | None = None,
    linked_card_positions: Mapping[int, float] | None = None,
    on_finished=None,
    parent=None,
) -> bool:
    """Prepare a background preview, ask for scope, then build the review."""
    try:
        normalized_source_card_id = int(source_card_id)
    except Exception:
        normalized_source_card_id = 0
    if normalized_source_card_id <= 0:
        showInfo("Could not determine the current media card.")
        return False

    normalized_label = str(media_label or "media").strip() or "media"
    normalized_media_kind = normalize_media_kind(media_kind)
    if not normalized_media_kind:
        normalized_media_kind = normalize_media_kind(normalized_label)
    options_key = (
        f"{str(profile or '').strip()}\0"
        f"{normalized_media_kind or normalized_label.casefold()}"
    )
    initial_options = _normalized_options(
        _last_options_by_media_kind.get(options_key, _default_options())
    )
    source_rows = tuple(dict(row) for row in list(linked_source_rows or []))
    note_ids = tuple(linked_note_ids or ())
    card_ids = tuple(linked_card_ids or ())
    card_positions = dict(linked_card_positions or {})
    random_seed = random.SystemRandom().randrange(1, 2**31)
    dialog_parent = parent or mw

    try:
        topic_classifier = resolve_topic_card_classifier()
    except Exception:
        topic_classifier = None

    def _inspect(col) -> list[dict]:
        return inspect_linked_media_review_rows(
            addon_dir,
            profile,
            normalized_source_card_id,
            col=col,
            media_kind=normalized_media_kind,
            linked_source_rows=source_rows,
            linked_note_ids=note_ids,
            linked_card_ids=card_ids,
            linked_card_positions=card_positions,
            include_tree_descendants=True,
            target_deck_name=deck_name,
            topic_classifier=topic_classifier,
        )

    def _preview_ready(preview_rows: list[dict]) -> None:
        record_media_review_inspection_finished(
            normalized_media_kind,
            len(preview_rows or []),
        )
        dialog = MediaAttachedReviewDialog(
            dialog_parent,
            media_label=normalized_label,
            media_kind=normalized_media_kind,
            preview_rows=preview_rows,
            current_position=current_position,
            initial_options=initial_options,
            random_seed=random_seed,
        )
        if not dialog.exec():
            return

        selected_options = dialog.selected_options()
        _last_options_by_media_kind[options_key] = dict(selected_options)

        def _select_ids(col) -> list[int]:
            return linked_media_review_card_ids(
                addon_dir,
                profile,
                normalized_source_card_id,
                col=col,
                media_kind=normalized_media_kind,
                current_position=current_position,
                random_seed=random_seed,
                linked_source_rows=source_rows,
                linked_note_ids=note_ids,
                linked_card_ids=card_ids,
                linked_card_positions=card_positions,
                include_tree_descendants=True,
                target_deck_name=deck_name,
                topic_classifier=topic_classifier,
                **selected_options,
            )

        start_explicit_review_from_selector(
            _select_ids,
            deck_name=deck_name,
            preserve_order=True,
            empty_message=(
                f"No cards attached to this {normalized_label} match the selected "
                "Topic/Item, link, media-range, and card-state filters."
            ),
            error_message=(
                f"Could not start the attached {normalized_label} card review"
            ),
            on_finished=on_finished,
            diagnostic_source="media_review",
            diagnostic_content_kind=normalized_media_kind,
            diagnostic_media_order=selected_options["order"],
            diagnostic_media_card_kind=selected_options["card_kind"],
            diagnostic_media_tree_scope=selected_options["tree_scope"],
            diagnostic_media_range=selected_options["media_range"],
            diagnostic_media_state=selected_options["state"],
            diagnostic_limit=selected_options["limit"],
        )

    def _preview_failed(exc: Exception) -> None:
        record_media_review_inspection_failed(normalized_media_kind, exc)
        showInfo(
            f"Could not inspect cards attached to this {normalized_label}:\n\n{exc}"
        )

    try:
        record_media_review_inspection_started(normalized_media_kind)
        _run_media_review_query(
            parent=dialog_parent,
            op=_inspect,
            success=_preview_ready,
            failure=_preview_failed,
        )
    except Exception as exc:
        _preview_failed(exc)
        return False
    return True
