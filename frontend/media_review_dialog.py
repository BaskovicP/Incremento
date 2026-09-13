"""Shared picker for reviewing cards attached to reader media."""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping

from aqt import mw
from aqt.qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QTabWidget,
    QTimer,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    qconnect,
)
from aqt.utils import showInfo
try:
    from ..backend.i18n import t, tn
except ImportError:
    from backend.i18n import t, tn


def _confirm_filtered_deck_release(parent, impact: str) -> bool:
    question = QMessageBox(parent)
    question.setIcon(QMessageBox.Icon.Question)
    question.setWindowTitle(t("reader_media_move_filtered_title"))
    question.setText(impact + "\n\n" + t("reader_media_continue_review"))
    question.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    question.button(QMessageBox.StandardButton.Yes).setText(t("reader_yes"))
    question.button(QMessageBox.StandardButton.No).setText(t("reader_no"))
    question.setDefaultButton(QMessageBox.StandardButton.No)
    return question.exec() == QMessageBox.StandardButton.Yes

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

_OPTION_MESSAGE_IDS = {
    "card_kind": {"both": "reader_media_topics_items", "topics": "reader_media_topics_only", "items": "reader_media_items_only"},
    "tree_scope": {"nested": "reader_media_direct_nested", "direct": "reader_media_direct_only"},
    "media_range": {"all": "reader_media_entire", "to_current": "reader_media_to_current"},
    "state": {"all": "reader_media_all_available", "due": "reader_media_due_only"},
    "order": {
        "attached": "reader_media_order_attached", "media_position": "reader_media_order_position",
        "created_oldest": "reader_media_order_oldest", "created_newest": "reader_media_order_newest",
        "due_first": "reader_media_order_due", "interval_shortest": "reader_media_order_shortest",
        "interval_longest": "reader_media_order_longest", "random": "reader_media_order_random",
    },
}


def _option_label(group: str, value: str, fallback: str) -> str:
    message_id = _OPTION_MESSAGE_IDS[group].get(value)
    return t(message_id) if message_id else fallback


def _default_options() -> dict:
    return {
        "order": MEDIA_REVIEW_ORDER_ATTACHED,
        "card_kind": MEDIA_REVIEW_CARD_KIND_BOTH,
        "tree_scope": MEDIA_REVIEW_TREE_NESTED,
        "media_range": MEDIA_REVIEW_RANGE_ALL,
        "state": MEDIA_REVIEW_STATE_ALL,
        "limit": 0,
        "include_filtered": False,
        "reschedule": True,
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
        "include_filtered": bool(raw.get("include_filtered", False)),
        "reschedule": bool(raw.get("reschedule", True)),
    }


def _media_position_label(media_kind: str, value) -> str:
    try:
        position = max(0.0, float(value))
    except Exception:
        return ""
    if media_kind == MEDIA_KIND_PDF:
        return t("reader_media_position_page", number=max(1, int(position)))
    if media_kind == MEDIA_KIND_EPUB:
        return t("reader_media_position_section", number=int(position) + 1)
    if media_kind == MEDIA_KIND_VIDEO:
        total_seconds = int(position)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours:d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:d}:{seconds:02d}"
    return ""


_EXCLUSION_REASON_LABELS = {
    "suspended": "reader_media_reason_suspended",
    "buried": "reader_media_reason_buried",
    "filtered": "reader_media_reason_filtered",
    "missing": "reader_media_reason_missing",
    "nested": "reader_media_reason_nested",
    "beyond_current": "reader_media_reason_beyond_current",
    "unknown_position": "reader_media_reason_unknown_position",
    "other_kind": "reader_media_reason_other_kind",
    "not_due": "reader_media_reason_not_due",
    "limit": "reader_media_reason_limit",
}


def format_filtered_deck_impact(decks: Iterable[dict] | None) -> str:
    """Explain the exact scope of Anki's required filtered-deck release."""
    parts = []
    for deck in list(decks or []):
        name = str(deck.get("deck_name") or t("reader_media_unknown_filtered_deck")).strip()
        count = max(0, int(deck.get("selected_count", 0) or 0))
        parts.append(t("reader_media_filtered_deck_item", name=name, count=count))
    if not parts:
        return ""
    return t("reader_media_filtered_deck_impact", decks=", ".join(parts))


def media_review_result_cells(row: Mapping, *, media_kind: str) -> tuple[str, str, str, str]:
    """Return plain, stable table cells for one Review All preview row."""
    try:
        card_id = int(row.get("card_id", 0) or 0)
    except Exception:
        card_id = 0
    label = str(row.get("card_label") or "").strip() or (
        t("reader_card_number", number=card_id) if card_id > 0 else t("reader_media_unknown_card")
    )
    card_type = t("reader_topic") if bool(row.get("is_topic")) else t("reader_item")
    position = _media_position_label(media_kind, row.get("media_position")) or "—"
    reason = str(row.get("exclusion_reason") or "").strip().lower()
    if reason:
        message_id = _EXCLUSION_REASON_LABELS.get(reason)
        status = t(message_id) if message_id else reason.replace("_", " ").title()
    elif str(row.get("availability") or "").strip().lower() == "filtered":
        deck_name = str(row.get("filtered_deck_name") or t("reader_media_another_filtered_deck")).strip()
        status = t("reader_media_will_move_from", deck=deck_name)
    else:
        status = t("reader_ready")
    return label, card_type, position, status


def format_media_review_preview(summary: dict) -> str:
    selected = int(summary.get("selected_count", 0) or 0)
    topics = int(summary.get("topic_count", 0) or 0)
    items = int(summary.get("item_count", 0) or 0)
    first_line = tn(
        "reader_media_preview_ready", selected,
        topics=tn("reader_media_topic_count", topics),
        items=tn("reader_media_item_count", items),
    )
    filtered_count = int(summary.get("selected_filtered_count", 0) or 0)
    if filtered_count > 0:
        exact_impact = format_filtered_deck_impact(summary.get("filtered_decks"))
        first_line += "\n" + tn("reader_media_filtered_warning", filtered_count) + " "
        first_line += exact_impact or (
            t("reader_media_filtered_fallback")
        )

    exclusions = dict(summary.get("exclusions") or {})
    labels = (
        ("suspended", "reader_media_excluded_suspended"),
        ("buried", "reader_media_excluded_buried"),
        ("filtered", "reader_media_excluded_filtered"),
        ("missing", "reader_media_excluded_missing"),
        ("nested", "reader_media_excluded_nested"),
        ("beyond_current", "reader_media_excluded_beyond_current"),
        ("unknown_position", "reader_media_excluded_unknown_position"),
        ("other_kind", "reader_media_excluded_other_kind"),
        ("not_due", "reader_media_excluded_not_due"),
        ("limit", "reader_media_excluded_limit"),
    )
    excluded_parts = [
        t(label, count=int(exclusions.get(key, 0) or 0))
        for key, label in labels
        if int(exclusions.get(key, 0) or 0) > 0
    ]
    if not excluded_parts:
        return first_line
    return first_line + "\n" + t("reader_media_excluded_summary", items=", ".join(excluded_parts))


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
        .with_progress(t("reader_media_inspecting_cards"))
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
        label = str(media_label or t("reader_media_generic")).strip() or t("reader_media_generic")
        self._media_kind = normalize_media_kind(media_kind)
        self._preview_rows = [dict(row) for row in list(preview_rows or [])]
        self._current_position = current_position
        self._random_seed = random_seed
        options = _normalized_options(initial_options or _default_options())

        self.setWindowTitle(t("reader_media_review_title", media=label))
        self.setModal(True)
        # Leave enough room for the opt-in filtered-deck warning without
        # forcing the preview or action buttons below the initial viewport.
        self.resize(900, 650)

        layout = QVBoxLayout(self)
        summary = QLabel(t("reader_media_review_intro", media=label))
        summary.setWordWrap(True)
        layout.addWidget(summary)

        form = QFormLayout()

        self._card_kind_combo = QComboBox(self)
        for value, option_label in MEDIA_REVIEW_CARD_KIND_OPTIONS:
            self._card_kind_combo.addItem(_option_label("card_kind", value, option_label), value)
        _set_combo_value(self._card_kind_combo, options["card_kind"])
        self._card_kind_combo.setToolTip(
            t("reader_media_kind_hint")
        )
        form.addRow(t("reader_media_review_label"), self._card_kind_combo)

        self._tree_scope_combo = QComboBox(self)
        for value, option_label in MEDIA_REVIEW_TREE_OPTIONS:
            self._tree_scope_combo.addItem(_option_label("tree_scope", value, option_label), value)
        _set_combo_value(self._tree_scope_combo, options["tree_scope"])
        form.addRow(t("reader_media_links_label"), self._tree_scope_combo)

        self._range_combo = QComboBox(self)
        for value, option_label in MEDIA_REVIEW_RANGE_OPTIONS:
            self._range_combo.addItem(_option_label("media_range", value, option_label), value)
        _set_combo_value(self._range_combo, options["media_range"])
        current_label = _media_position_label(self._media_kind, current_position)
        if current_label:
            self._range_combo.setToolTip(
                t("reader_media_current_position_hint", media=label, position=current_label)
            )
        else:
            _set_combo_value(self._range_combo, MEDIA_REVIEW_RANGE_ALL)
            self._range_combo.setEnabled(False)
            self._range_combo.setToolTip(
                t("reader_media_unknown_position_hint")
            )
        form.addRow(t("reader_media_range_label"), self._range_combo)

        self._state_combo = QComboBox(self)
        for value, option_label in MEDIA_REVIEW_STATE_OPTIONS:
            self._state_combo.addItem(_option_label("state", value, option_label), value)
        _set_combo_value(self._state_combo, options["state"])
        self._state_combo.setToolTip(
            t("reader_media_due_hint")
        )
        form.addRow(t("reader_media_state_label"), self._state_combo)

        self._reminder_checkbox = QCheckBox(
            t("reader_media_reminder"),
            self,
        )
        self._reminder_checkbox.setChecked(not options["reschedule"])
        self._reminder_checkbox.setAccessibleName(t("reader_media_reminder"))
        self._reminder_checkbox.setToolTip(
            t("reader_media_reminder_hint")
        )
        form.addRow(t("reader_media_scheduling_label"), self._reminder_checkbox)

        self._order_combo = QComboBox(self)
        for value, option_label in MEDIA_REVIEW_ORDER_OPTIONS:
            self._order_combo.addItem(_option_label("order", value, option_label), value)
        _set_combo_value(self._order_combo, options["order"])
        self._order_combo.setToolTip(
            t("reader_media_order_hint")
        )
        form.addRow(t("reader_media_order_label"), self._order_combo)

        self._limit_spin = QSpinBox(self)
        self._limit_spin.setRange(0, 9999)
        self._limit_spin.setSpecialValueText(t("reader_all"))
        self._limit_spin.setValue(options["limit"])
        self._limit_spin.setToolTip(
            t("reader_media_limit_hint")
        )
        form.addRow(t("reader_media_max_cards_label"), self._limit_spin)

        self._include_filtered_checkbox = QCheckBox(
            t("reader_media_include_filtered"),
            self,
        )
        self._include_filtered_checkbox.setChecked(options["include_filtered"])
        self._include_filtered_checkbox.setAccessibleName(
            t("reader_media_include_filtered_accessible")
        )
        self._include_filtered_checkbox.setToolTip(
            t("reader_media_include_filtered_hint")
        )
        form.addRow(t("reader_media_other_filtered_label"), self._include_filtered_checkbox)
        layout.addLayout(form)

        self._preview_label = QLabel("")
        self._preview_label.setWordWrap(True)
        self._preview_label.setAccessibleName(t("reader_media_summary_accessible"))
        layout.addWidget(self._preview_label)

        self._filtered_deck_impact_label = QLabel("")
        self._filtered_deck_impact_label.setWordWrap(True)
        self._filtered_deck_impact_label.setAccessibleName(
            t("reader_media_filtered_warning_accessible")
        )
        layout.addWidget(self._filtered_deck_impact_label)

        self._result_tabs = QTabWidget(self)
        self._ready_tree = self._create_result_tree(t("reader_media_ready_tree_accessible"))
        self._excluded_tree = self._create_result_tree(t("reader_media_excluded_tree_accessible"))
        self._ready_tab_index = self._result_tabs.addTab(self._ready_tree, t("reader_ready"))
        self._excluded_tab_index = self._result_tabs.addTab(
            self._excluded_tree,
            t("reader_excluded"),
        )
        layout.addWidget(self._result_tabs, 1)

        buttons = QDialogButtonBox(self)
        self._review_button = buttons.addButton(
            t("reader_media_start_review"),
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        self._review_button.setAccessibleName(t("reader_media_start_review_accessible"))
        cancel_button = buttons.addButton(
            t("reader_cancel"),
            QDialogButtonBox.ButtonRole.RejectRole,
        )
        qconnect(self._review_button.clicked, self._accept_review)
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
        qconnect(self._include_filtered_checkbox.toggled, self._refresh_preview)
        qconnect(self._reminder_checkbox.toggled, self._refresh_preview)
        self._refresh_preview()

    def _create_result_tree(self, accessible_name: str) -> QTreeWidget:
        tree = QTreeWidget(self)
        tree.setColumnCount(4)
        tree.setHeaderLabels((t("reader_card"), t("reader_type"), t("reader_position"), t("reader_status")))
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        tree.setAccessibleName(accessible_name)
        return tree

    def selected_options(self) -> dict:
        return _normalized_options(
            {
                "order": self._order_combo.currentData(),
                "card_kind": self._card_kind_combo.currentData(),
                "tree_scope": self._tree_scope_combo.currentData(),
                "media_range": self._range_combo.currentData(),
                "state": self._state_combo.currentData(),
                "limit": self._limit_spin.value(),
                "include_filtered": self._include_filtered_checkbox.isChecked(),
                "reschedule": not self._reminder_checkbox.isChecked(),
            }
        )

    def selection_summary(self) -> dict:
        selection_options = self.selected_options()
        selection_options.pop("reschedule")
        return select_linked_media_review_rows(
            self._preview_rows,
            current_position=self._current_position,
            random_seed=self._random_seed,
            **selection_options,
        )

    def _refresh_preview(self, *_args) -> None:
        selection = self.selection_summary()
        count = int(selection.get("selected_count", 0) or 0)
        reminder = self._reminder_checkbox.isChecked()
        scheduling_text = (
            t("reader_media_reminder_schedule_status")
            if reminder else t("reader_media_review_schedule_status")
        )
        self._preview_label.setText(
            f"{format_media_review_preview(selection)}\n{scheduling_text}"
        )
        self._populate_result_trees(selection)
        filtered_decks = list(selection.get("filtered_decks") or [])
        if filtered_decks:
            self._filtered_deck_impact_label.setText(
                format_filtered_deck_impact(filtered_decks)
            )
            self._filtered_deck_impact_label.show()
        else:
            self._filtered_deck_impact_label.clear()
            self._filtered_deck_impact_label.hide()
        self._review_button.setEnabled(count > 0)
        action = t("reader_preview") if reminder else t("reader_review")
        self._review_button.setText(
            t("reader_media_action_count", action=action, cards=tn("reader_media_card_count_title", count)) if count else t("reader_media_no_cards")
        )

    def _populate_result_trees(self, selection: Mapping) -> None:
        ready_rows = list(selection.get("rows") or [])
        excluded_rows = list(selection.get("excluded_rows") or [])
        self._ready_tree.clear()
        self._excluded_tree.clear()
        for tree, rows in (
            (self._ready_tree, ready_rows),
            (self._excluded_tree, excluded_rows),
        ):
            for row in rows:
                item = QTreeWidgetItem(
                    list(media_review_result_cells(row, media_kind=self._media_kind))
                )
                label = str(row.get("card_label") or "").strip()
                if label:
                    item.setToolTip(0, label)
                tree.addTopLevelItem(item)
            tree.resizeColumnToContents(1)
            tree.resizeColumnToContents(2)
            tree.resizeColumnToContents(3)
        self._result_tabs.setTabText(
            self._ready_tab_index,
            t("reader_media_ready_tab", count=len(ready_rows)),
        )
        self._result_tabs.setTabText(
            self._excluded_tab_index,
            t("reader_media_excluded_tab", count=len(excluded_rows)),
        )

    def _accept_review(self) -> None:
        selection = self.selection_summary()
        filtered_decks = list(selection.get("filtered_decks") or [])
        if self._include_filtered_checkbox.isChecked() and filtered_decks:
            impact = format_filtered_deck_impact(filtered_decks)
            if not _confirm_filtered_deck_release(self, impact):
                return
        self.accept()


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
        showInfo(t("reader_media_card_unknown"))
        return False

    normalized_label = str(media_label or "media").strip() or "media"
    display_label = str(media_label or "").strip() or t("reader_media_generic")
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
    # Moving cards out of another filtered deck is intentionally one-shot.
    # Require explicit opt-in on every launch instead of remembering a choice
    # that can empty an unrelated study deck later.
    initial_options["include_filtered"] = False
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
            media_label=display_label,
            media_kind=normalized_media_kind,
            preview_rows=preview_rows,
            current_position=current_position,
            initial_options=initial_options,
            random_seed=random_seed,
        )
        if not dialog.exec():
            return

        selected_options = _normalized_options(dialog.selected_options())
        remembered_options = dict(selected_options)
        remembered_options["include_filtered"] = False
        _last_options_by_media_kind[options_key] = remembered_options
        reschedule = selected_options.pop("reschedule")

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

        def _start_selected_review() -> None:
            start_explicit_review_from_selector(
                _select_ids,
                deck_name=deck_name,
                preserve_order=True,
                reschedule=reschedule,
                empty_message=t("reader_media_no_matching_cards", media=display_label),
                error_message=t("reader_media_review_start_failed", media=display_label),
                on_finished=on_finished,
                diagnostic_source="media_review",
                diagnostic_content_kind=normalized_media_kind,
                diagnostic_media_order=selected_options["order"],
                diagnostic_media_card_kind=selected_options["card_kind"],
                diagnostic_media_tree_scope=selected_options["tree_scope"],
                diagnostic_media_range=selected_options["media_range"],
                diagnostic_media_state=selected_options["state"],
                diagnostic_limit=selected_options["limit"],
                release_from_other_filtered_decks=bool(
                    selected_options["include_filtered"]
                ),
            )

        if (
            selected_options["include_filtered"]
            and str(getattr(mw, "state", "") or "") == "review"
        ):
            try:
                mw.moveToState("overview")
            except Exception as exc:
                showInfo(t("reader_media_leave_review_failed", error=exc))
                return
            QTimer.singleShot(0, _start_selected_review)
        else:
            _start_selected_review()

    def _preview_failed(exc: Exception) -> None:
        record_media_review_inspection_failed(normalized_media_kind, exc)
        showInfo(t("reader_media_inspection_failed", media=display_label, error=exc))

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
