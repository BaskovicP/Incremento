import json
import os

from aqt import mw
from aqt.qt import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QCheckBox, QComboBox, QPushButton, QWidget, Qt, qconnect,
    QTimeEdit, QTime, QSpinBox, QLineEdit, QMessageBox, QFileDialog, QFrame,
)
from aqt.utils import showInfo

from .scheduler_config import SchedulerConfig, NO_TAGS_KEY
from .statistics import load_stats, delete_daily_stats, delete_lifetime_stats, delete_all_stats

# Addon root: one level above this file (utils/)
_ADDON_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


_DAY_END_PRESETS = [
    ("00:00", "12:00 AM (midnight)"),
    ("01:00", "1:00 AM"),
    ("02:00", "2:00 AM"),
    ("03:00", "3:00 AM"),
    ("04:00", "4:00 AM"),
    ("05:00", "5:00 AM"),
    ("06:00", "6:00 AM"),
    (None,    "Custom…"),
]

_PRIORITY_DIMS = [
    ("tags",  "Tags"),
    ("type",  "Type (topics / items)"),
    ("mode",  "Mode (priority / random)"),
]


class SchedulerConfigDialog(QDialog):
    def __init__(self, parent=None, on_clear_session=None):
        super().__init__(parent)
        self.setWindowTitle("Scheduler Settings")
        self.setMinimumWidth(520)
        self._linked_rows: list[dict] = []
        self._updating = False
        self._on_clear_session = on_clear_session
        config = mw.addonManager.getConfig(__name__) or {}
        self._saved = config.get("dialog", {})
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Configure how Incremento selects cards for each study session."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: gray;")
        layout.addWidget(intro)

        # -- Session size --
        count_row = QHBoxLayout()
        count_row.addWidget(QLabel("Cards per session:"))
        self._count_spin = QSpinBox()
        self._count_spin.setRange(1, 500)
        self._count_spin.setValue(self._saved.get("session_card_count", 50))
        self._count_spin.setToolTip("How many cards to schedule in this session.")
        count_row.addWidget(self._count_spin)
        count_row.addStretch()
        layout.addLayout(count_row)

        # -- Card type filter --
        card_types_row = QHBoxLayout()
        card_types_row.addWidget(QLabel("Card types:"))
        self._cb_new = QCheckBox("New")
        self._cb_new.setToolTip("Include cards that have never been studied (is:new)")
        self._cb_new.setChecked(self._saved.get("include_new", True))
        card_types_row.addWidget(self._cb_new)
        self._cb_learning = QCheckBox("Learning")
        self._cb_learning.setToolTip("Include cards currently in learning steps (is:learn)")
        self._cb_learning.setChecked(self._saved.get("include_learning", True))
        card_types_row.addWidget(self._cb_learning)
        self._cb_due = QCheckBox("Due / Review")
        self._cb_due.setToolTip("Include review cards that are due for study (is:due)")
        self._cb_due.setChecked(self._saved.get("include_due", True))
        card_types_row.addWidget(self._cb_due)
        card_types_row.addStretch()
        layout.addLayout(card_types_row)

        # -- Topics / Items row --
        # Left label shows topics%, right label shows items% (they sum to 100).
        # topics_rate = 1 - slider/100, so slider right = more items.
        topics_val = self._saved.get("topics_slider", 10)
        topics_row = QHBoxLayout()
        self._topics_left_lbl = QLabel(f"{100 - topics_val}%")
        self._topics_left_lbl.setFixedWidth(36)
        topics_row.addWidget(self._topics_left_lbl)
        _lbl_topics = QLabel("Topics")
        _lbl_topics.setToolTip("Concept cards — notes, articles, long-form reading material")
        topics_row.addWidget(_lbl_topics)
        self._topics_slider = QSlider(Qt.Orientation.Horizontal)
        self._topics_slider.setRange(0, 100)
        self._topics_slider.setValue(topics_val)
        self._topics_slider.setToolTip(
            "Slide right for more item cards; slide left for more topic cards.\n"
            "The percentages show the approximate share each type gets per session."
        )
        topics_row.addWidget(self._topics_slider)
        _lbl_items = QLabel("Items")
        _lbl_items.setToolTip("Fact cards — Q&A flashcards, vocabulary, quick-recall items")
        topics_row.addWidget(_lbl_items)
        self._topics_right_lbl = QLabel(f"{topics_val}%")
        self._topics_right_lbl.setFixedWidth(36)
        topics_row.addWidget(self._topics_right_lbl)
        layout.addLayout(topics_row)

        self._counts_lbl = QLabel("")
        layout.addWidget(self._counts_lbl)

        # -- PDF / Other row --
        # Left label shows pdf% (100-v), right label shows other% (v).
        # Slider right = more Other; pdf_rate = (100-slider)/100.
        pdf_val = self._saved.get("pdf_slider", 0)
        pdf_row = QHBoxLayout()
        self._pdf_left_lbl = QLabel(f"{100 - pdf_val}%")
        self._pdf_left_lbl.setFixedWidth(36)
        pdf_row.addWidget(self._pdf_left_lbl)
        _lbl_pdf = QLabel("PDF")
        _lbl_pdf.setToolTip("Incremento PDF reading cards — always eligible regardless of scheduling state")
        pdf_row.addWidget(_lbl_pdf)
        self._pdf_slider = QSlider(Qt.Orientation.Horizontal)
        self._pdf_slider.setRange(0, 100)
        self._pdf_slider.setValue(pdf_val)
        self._pdf_slider.setToolTip(
            "Slide right for more non-PDF cards; slide left for more PDF reading cards.\n"
            "PDF cards are always eligible — they don't need to be 'due' to appear."
        )
        pdf_row.addWidget(self._pdf_slider)
        _lbl_other = QLabel("Other")
        _lbl_other.setToolTip("All non-PDF cards (topics and items)")
        pdf_row.addWidget(_lbl_other)
        self._pdf_right_lbl = QLabel(f"{pdf_val}%")
        self._pdf_right_lbl.setFixedWidth(36)
        pdf_row.addWidget(self._pdf_right_lbl)
        layout.addLayout(pdf_row)

        qconnect(self._pdf_slider.valueChanged,
                 lambda v: (self._pdf_left_lbl.setText(f"{100 - v}%"),
                             self._pdf_right_lbl.setText(f"{v}%")))

        # -- Priority / Random row --
        # Left label shows priority%, right label shows random%.
        # random_rate = slider/100, so slider right = more random.
        random_val = self._saved.get("random_slider", 99)
        random_row = QHBoxLayout()
        self._random_left_lbl = QLabel(f"{100 - random_val}%")
        self._random_left_lbl.setFixedWidth(36)
        random_row.addWidget(self._random_left_lbl)
        _lbl_priority = QLabel("Priority")
        _lbl_priority.setToolTip(
            "Pick cards in priority order — most overdue or highest-rated appear first"
        )
        random_row.addWidget(_lbl_priority)
        self._random_slider = QSlider(Qt.Orientation.Horizontal)
        self._random_slider.setRange(0, 100)
        self._random_slider.setValue(random_val)
        self._random_slider.setToolTip(
            "Slide right for more randomness; slide left to always pick the highest-priority card first."
        )
        random_row.addWidget(self._random_slider)
        _lbl_random = QLabel("Random")
        _lbl_random.setToolTip("Pick cards at random from the eligible pool")
        random_row.addWidget(_lbl_random)
        self._random_right_lbl = QLabel(f"{random_val}%")
        self._random_right_lbl.setFixedWidth(36)
        random_row.addWidget(self._random_right_lbl)
        layout.addLayout(random_row)

        qconnect(self._topics_slider.valueChanged,
                 lambda v: (self._topics_left_lbl.setText(f"{100 - v}%"),
                             self._topics_right_lbl.setText(f"{v}%")))
        qconnect(self._random_slider.valueChanged,
                 lambda v: (self._random_left_lbl.setText(f"{100 - v}%"),
                             self._random_right_lbl.setText(f"{v}%")))
        qconnect(self._cb_new.stateChanged,      lambda _: self._refresh_counts())
        qconnect(self._cb_learning.stateChanged, lambda _: self._refresh_counts())
        qconnect(self._cb_due.stateChanged,      lambda _: self._refresh_counts())

        # -- Scheduler scope --
        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel("Scheduler scope:"))
        self._scope_combo = QComboBox()
        self._scope_combo.addItem("This session",  "session")
        self._scope_combo.addItem("Today",          "daily")
        self._scope_combo.addItem("All time",       "lifetime")
        self._scope_combo.setToolTip(
            "How far back the scheduler looks when balancing card types and tags.\n"
            "• This session — resets each time you open this dialog\n"
            "• Today — remembers picks across multiple same-day sessions\n"
            "• All time — balances over your entire study history"
        )
        saved_scope = self._saved.get("scheduler_scope", "session")
        for i in range(self._scope_combo.count()):
            if self._scope_combo.itemData(i) == saved_scope:
                self._scope_combo.setCurrentIndex(i)
                break
        scope_row.addWidget(self._scope_combo)

        self._day_end_label = QLabel("  Day ends at:")
        self._day_end_label.setToolTip(
            "If you study past midnight, set this to after your usual bedtime.\n"
            "Cards studied before this time will still count as part of yesterday."
        )
        scope_row.addWidget(self._day_end_label)

        self._day_end_preset = QComboBox()
        self._day_end_preset.setToolTip(
            "If you study past midnight, set this to after your usual bedtime.\n"
            "Cards studied before this time will still count as part of yesterday."
        )
        for value, label in _DAY_END_PRESETS:
            self._day_end_preset.addItem(label, value)
        scope_row.addWidget(self._day_end_preset)

        self._day_end_edit = QTimeEdit()
        self._day_end_edit.setDisplayFormat("HH:mm")
        scope_row.addWidget(self._day_end_edit)

        scope_row.addStretch()
        layout.addLayout(scope_row)

        # Restore saved day-end time
        saved_time = self._saved.get("day_end_time", "00:00")
        preset_idx = next(
            (i for i in range(self._day_end_preset.count())
             if self._day_end_preset.itemData(i) == saved_time),
            None,
        )
        if preset_idx is not None:
            self._day_end_preset.setCurrentIndex(preset_idx)
        else:
            self._day_end_preset.setCurrentIndex(self._day_end_preset.count() - 1)
            h, m = map(int, saved_time.split(":"))
            self._day_end_edit.setTime(QTime(h, m))

        self._update_day_end_visibility()
        qconnect(self._scope_combo.currentIndexChanged, lambda _: self._update_day_end_visibility())
        qconnect(self._day_end_preset.currentIndexChanged, lambda _: self._on_day_end_preset_changed())

        # -- Priority order --
        priority_header = QHBoxLayout()
        self._enforce_cb = QCheckBox("Strict enforcement")
        self._enforce_cb.setToolTip(
            "Strict (checked): each bucket is filled in full before moving to the next.\n"
            "Example: all tag-A cards are picked, then tag-B, then the rest.\n\n"
            "Soft (unchecked): the scheduler picks from all dimensions at every step,\n"
            "gradually converging to your target ratios without any hard ordering."
        )
        self._enforce_cb.setChecked(self._saved.get("enforce_priority", True))
        priority_header.addWidget(QLabel("Scheduling priority order:"))
        priority_header.addStretch()
        priority_header.addWidget(self._enforce_cb)
        layout.addLayout(priority_header)

        _priority_desc = QLabel(
            "Which dimension's quota is filled first when cards are limited."
        )
        _priority_desc.setStyleSheet("color: gray;")
        layout.addWidget(_priority_desc)

        self._priority_order_widget = QWidget()
        priority_row = QHBoxLayout(self._priority_order_widget)
        priority_row.setContentsMargins(0, 0, 0, 0)
        self._priority_combos: list[QComboBox] = []
        saved_order = self._saved.get("priority_order", ["tags", "type", "mode"])
        for i in range(3):
            if i > 0:
                priority_row.addWidget(QLabel("→"))
            combo = QComboBox()
            self._priority_combos.append(combo)
            priority_row.addWidget(combo)
        priority_row.addStretch()
        layout.addWidget(self._priority_order_widget)
        self._refresh_priority_combos(saved_order)
        for _combo in self._priority_combos:
            _combo.setToolTip(
                "The leftmost item is the hardest constraint (filled first).\n"
                "Move a dimension left to give it higher priority."
            )
        self._priority_order_widget.setEnabled(self._enforce_cb.isChecked())
        qconnect(self._enforce_cb.stateChanged,
                 lambda _: self._priority_order_widget.setEnabled(self._enforce_cb.isChecked()))
        qconnect(self._priority_combos[0].currentIndexChanged,
                 lambda _: self._on_priority_changed(0))
        qconnect(self._priority_combos[1].currentIndexChanged,
                 lambda _: self._on_priority_changed(1))

        # -- Tag distribution --
        _tag_header = QLabel("Tag quotas")
        _tag_header.setStyleSheet("font-weight: bold;")
        layout.addWidget(_tag_header)
        _tag_desc = QLabel(
            "Set what percentage of the session each tag receives. "
            "Sliders are independent — the remainder goes to untagged cards."
        )
        _tag_desc.setWordWrap(True)
        _tag_desc.setStyleSheet("color: gray;")
        layout.addWidget(_tag_desc)

        add_tag_row = QHBoxLayout()
        self._tag_combo = QComboBox()
        self._tag_combo.addItems(sorted(mw.col.tags.all()))
        add_tag_row.addWidget(self._tag_combo)
        add_btn = QPushButton("Add")
        qconnect(add_btn.clicked, lambda: self._add_tag_row(self._tag_combo.currentText()))
        add_tag_row.addWidget(add_btn)
        layout.addLayout(add_tag_row)

        self._no_tags_cb = QCheckBox("After exhausting tag groups, fill with rest of cards")
        self._no_tags_cb.setToolTip(
            "When all tag quotas are filled, use any remaining cards\n"
            "to reach the session target — regardless of their tags."
        )
        self._no_tags_cb.setChecked(self._saved.get("no_tags_checked", True))
        layout.addWidget(self._no_tags_cb)

        self._tags_container = QWidget()
        self._tags_layout = QVBoxLayout(self._tags_container)
        self._tags_layout.setContentsMargins(0, 0, 0, 0)
        self._tags_layout.setSpacing(2)
        layout.addWidget(self._tags_container)

        # Restore saved tag rows
        for entry in self._saved.get("tag_rows", []):
            self._add_tag_row(entry["tag"], entry.get("weight", 20),
                              locked=entry.get("locked", False))

        self._other_lbl = QLabel("")
        layout.addWidget(self._other_lbl)
        self._update_other_label()

        # -- Advanced: deck filters --
        _adv_header = QLabel("Advanced")
        _adv_header.setStyleSheet("font-weight: bold;")
        layout.addWidget(_adv_header)

        topics_filter_row = QHBoxLayout()
        topics_filter_row.addWidget(QLabel("Topics filter:"))
        self._topics_filter_edit = QLineEdit()
        self._topics_filter_edit.setPlaceholderText("deck:Topics")
        self._topics_filter_edit.setToolTip(
            "Anki search query that identifies topic (concept) cards.\n"
            "Default: deck:Topics"
        )
        self._topics_filter_edit.setText(self._saved.get("topics_filter", "deck:Topics"))
        topics_filter_row.addWidget(self._topics_filter_edit)
        test_topics_btn = QPushButton("Test")
        test_topics_btn.setFixedWidth(48)
        qconnect(test_topics_btn.clicked,
                 lambda: self._test_filter(self._topics_filter_edit.text().strip() or "deck:Topics"))
        topics_filter_row.addWidget(test_topics_btn)
        layout.addLayout(topics_filter_row)

        items_filter_row = QHBoxLayout()
        items_filter_row.addWidget(QLabel("Items filter:"))
        self._items_filter_edit = QLineEdit()
        self._items_filter_edit.setPlaceholderText("-deck:Topics")
        self._items_filter_edit.setToolTip(
            "Anki search query that identifies item (flashcard) cards.\n"
            "Default: -deck:Topics"
        )
        self._items_filter_edit.setText(self._saved.get("items_filter", "-deck:Topics"))
        items_filter_row.addWidget(self._items_filter_edit)
        test_items_btn = QPushButton("Test")
        test_items_btn.setFixedWidth(48)
        qconnect(test_items_btn.clicked,
                 lambda: self._test_filter(self._items_filter_edit.text().strip() or "-deck:Topics"))
        items_filter_row.addWidget(test_items_btn)
        layout.addLayout(items_filter_row)

        self._preserve_order_cb = QCheckBox("Present cards in scheduler order")
        self._preserve_order_cb.setToolTip(
            "When checked, cards appear in the exact order the scheduler selected them.\n"
            "Stopping early gives a proportional sample matching your tag/type ratios.\n"
            "Works best with soft scheduling (strict enforcement disabled).\n\n"
            "When unchecked, cards are shown in random order."
        )
        self._preserve_order_cb.setChecked(self._saved.get("preserve_order", True))
        layout.addWidget(self._preserve_order_cb)

        self._show_debug_cb = QCheckBox("Show debug information on cards when starting")
        self._show_debug_cb.setChecked(self._saved.get("show_debug", False))
        layout.addWidget(self._show_debug_cb)

        qconnect(self._topics_filter_edit.textChanged, lambda _: self._refresh_counts())
        qconnect(self._items_filter_edit.textChanged,  lambda _: self._refresh_counts())

        self._refresh_counts()

        # -- Statistics history --
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("QFrame { color: rgba(128,128,128,0.35); }")
        layout.addWidget(sep)

        _stats_header = QLabel("Statistics history")
        _stats_header.setStyleSheet("font-weight: bold;")
        layout.addWidget(_stats_header)

        stats_row = QHBoxLayout()

        del_today_btn = QPushButton("Delete Today")
        del_today_btn.setToolTip("Permanently delete today's statistics")
        qconnect(del_today_btn.clicked, self._delete_daily)
        stats_row.addWidget(del_today_btn)

        del_session_btn = QPushButton("Delete Session")
        del_session_btn.setToolTip("Clear the last session's in-memory statistics")
        qconnect(del_session_btn.clicked, self._delete_session)
        stats_row.addWidget(del_session_btn)

        del_lifetime_btn = QPushButton("Delete All Time")
        del_lifetime_btn.setToolTip("Permanently delete all lifetime statistics")
        qconnect(del_lifetime_btn.clicked, self._delete_lifetime)
        stats_row.addWidget(del_lifetime_btn)

        del_all_btn = QPushButton("Delete All History")
        del_all_btn.setToolTip("Permanently delete all statistics (today + all time + session)")
        del_all_btn.setStyleSheet("color: #e05050;")
        qconnect(del_all_btn.clicked, self._delete_all)
        stats_row.addWidget(del_all_btn)

        stats_row.addStretch()

        export_btn = QPushButton("Export JSON")
        export_btn.setToolTip("Export all saved statistics as a JSON file")
        qconnect(export_btn.clicked, self._export_json)
        stats_row.addWidget(export_btn)

        layout.addLayout(stats_row)

        # -- OK / Cancel --
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        qconnect(btn_box.accepted, self.accept)
        qconnect(btn_box.rejected, self.reject)
        layout.addWidget(btn_box)

    def _update_day_end_visibility(self) -> None:
        is_daily = self._scope_combo.currentData() == "daily"
        self._day_end_label.setVisible(is_daily)
        self._day_end_preset.setVisible(is_daily)
        self._day_end_edit.setVisible(is_daily and self._day_end_preset.currentData() is None)

    def _on_day_end_preset_changed(self) -> None:
        self._day_end_edit.setVisible(
            self._scope_combo.currentData() == "daily"
            and self._day_end_preset.currentData() is None
        )

    def _get_day_end_time(self) -> str:
        preset = self._day_end_preset.currentData()
        if preset is None:
            return self._day_end_edit.time().toString("HH:mm")
        return preset

    # ------------------------------------------------------------------
    # Priority order helpers
    # ------------------------------------------------------------------

    def _refresh_priority_combos(self, order: list) -> None:
        """Populate the three priority combos so each shows only unused options."""
        for i, combo in enumerate(self._priority_combos):
            already_used = [order[j] for j in range(i)]
            combo.blockSignals(True)
            combo.clear()
            for key, label in _PRIORITY_DIMS:
                if key not in already_used:
                    combo.addItem(label, key)
            # Select the item matching order[i]
            for j in range(combo.count()):
                if combo.itemData(j) == order[i]:
                    combo.setCurrentIndex(j)
                    break
            combo.blockSignals(False)
        # Disable the last combo — it always has exactly one option
        self._priority_combos[2].setEnabled(False)

    def _on_priority_changed(self, changed_idx: int) -> None:
        """When combo i changes, rebuild subsequent combos with remaining dims."""
        used = [self._priority_combos[i].currentData() for i in range(changed_idx + 1)]
        remaining = [k for k, _ in _PRIORITY_DIMS if k not in used]
        self._refresh_priority_combos(used + remaining)

    def _get_priority_order(self) -> list:
        return [c.currentData() for c in self._priority_combos]

    # ------------------------------------------------------------------
    # Tag row helpers
    # ------------------------------------------------------------------

    def _make_row_base(self, label_text: str, weight: int,
                       locked: bool) -> tuple[QWidget, QHBoxLayout, QSlider, QLabel, QCheckBox, QLabel]:
        """Create the shared [label | slider | pct | lock] part of a tag row."""
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 5, 0, 5)
        name_label = QLabel(label_text)
        row_layout.addWidget(name_label)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(weight)
        row_layout.addWidget(slider)

        pct_label = QLabel(f"{weight}%")
        pct_label.setFixedWidth(36)
        row_layout.addWidget(pct_label)

        lock_cb = QCheckBox("🔒")
        lock_cb.setChecked(locked)
        lock_cb.setToolTip("Lock this weight so other sliders don't affect it")
        lock_cb.setFixedWidth(48)
        row_layout.addWidget(lock_cb)

        # Disable slider when locked; re-enable on toggle
        slider.setEnabled(not locked)
        qconnect(lock_cb.stateChanged,
                 lambda _, cb=lock_cb, s=slider: s.setEnabled(not cb.isChecked()))

        return row_widget, row_layout, slider, pct_label, lock_cb, name_label

    def _add_tag_row(self, tag: str, weight: int = 20, locked: bool = False) -> None:
        if not tag:
            return
        if any(r["tag"] == tag for r in self._linked_rows):
            return

        row_widget, row_layout, slider, pct_label, lock_cb, name_label = self._make_row_base(
            tag, weight, locked
        )

        row_dict = {"tag": tag, "slider": slider, "pct_label": pct_label,
                    "lock_cb": lock_cb, "widget": row_widget, "name_label": name_label}
        self._refresh_tag_count(row_dict)
        qconnect(slider.valueChanged, lambda v, r=row_dict: self._on_weight_changed(r))

        row_layout.addSpacing(6)
        remove_btn = QPushButton("✕")
        remove_btn.setFixedWidth(28)
        remove_btn.setStyleSheet(
            "QPushButton { color: #e05050; font-weight: bold; }"
            "QPushButton:hover { color: #c03030; }"
        )
        qconnect(remove_btn.clicked, lambda checked=False, r=row_dict: self._remove_row(r))
        row_layout.addWidget(remove_btn)

        self._tags_layout.addWidget(row_widget)
        self._linked_rows.append(row_dict)

        # Hide this tag in the picker so it can't be added twice
        idx = self._tag_combo.findText(tag)
        if idx >= 0:
            self._tag_combo.removeItem(idx)

        self._update_other_label()

    def _remove_row(self, row_dict: dict) -> None:
        tag = row_dict["tag"]
        if row_dict in self._linked_rows:
            self._linked_rows.remove(row_dict)
        row_dict["widget"].deleteLater()

        # Return the tag to the picker in alphabetical order
        items = [self._tag_combo.itemText(i) for i in range(self._tag_combo.count())]
        items.append(tag)
        items.sort()
        self._tag_combo.insertItem(items.index(tag), tag)

        self._update_other_label()

    # ------------------------------------------------------------------
    # Slider logic — each tag slider is independent (no forced rebalancing)
    # ------------------------------------------------------------------

    def _on_weight_changed(self, changed_row: dict) -> None:
        if self._updating:
            return
        changed_row["pct_label"].setText(f"{changed_row['slider'].value()}%")
        self._update_other_label()

    def _update_other_label(self) -> None:
        """Show what fraction of the session is left for untagged cards."""
        total = sum(r["slider"].value() for r in self._linked_rows)
        other = max(0, 100 - total)
        if not hasattr(self, "_other_lbl"):
            return
        if total > 100:
            self._other_lbl.setText(
                f'<span style="color: #e0a020; font-size: small;">'
                f'Other cards: {other}%  (tag weights exceed 100% — reduce some sliders)</span>'
            )
        else:
            self._other_lbl.setText(
                f'<span style="color: gray; font-size: small;">'
                f'Other cards: {other}%</span>'
            )

    def _ready_filter_from_checks(self) -> str:
        """Build the is:… clause from the card-type checkboxes."""
        parts = []
        if self._cb_new.isChecked():
            parts.append("is:new")
        if self._cb_learning.isChecked():
            parts.append("is:learn")
        if self._cb_due.isChecked():
            parts.append("is:due")
        if not parts:
            return "is:new"
        if len(parts) == 1:
            return parts[0]
        return "(" + " OR ".join(parts) + ")"

    def _refresh_tag_count(self, row_dict: dict) -> None:
        """Update the count annotation on one tag row."""
        tag = row_dict["tag"]
        ready = self._ready_filter_from_checks()
        # Use filter edits if they already exist (they're created after tag rows).
        tf_widget  = getattr(self, "_topics_filter_edit", None)
        itf_widget = getattr(self, "_items_filter_edit",  None)
        tf  = (tf_widget.text().strip()  or "deck:Topics")  if tf_widget  else "deck:Topics"
        itf = (itf_widget.text().strip() or "-deck:Topics") if itf_widget else "-deck:Topics"
        n_topics = len(mw.col.find_cards(f"{tf} tag:{tag} {ready}"))
        n_items  = len(mw.col.find_cards(f"{itf} tag:{tag} {ready}"))
        color = "#e0a020" if (n_topics == 0 or n_items == 0) else "gray"
        row_dict["name_label"].setText(
            f'{tag} <span style="color: {color}; font-size: small;">'
            f'({n_topics} topics / {n_items} items)</span>'
        )

    def _refresh_counts(self) -> None:
        """Refresh the global topics/items count label and all tag-row counts."""
        ready = self._ready_filter_from_checks()
        tf  = self._topics_filter_edit.text().strip() or "deck:Topics"
        itf = self._items_filter_edit.text().strip()  or "-deck:Topics"
        n_topics = len(mw.col.find_cards(f"{tf} {ready}"))
        n_items  = len(mw.col.find_cards(f"{itf} {ready}"))
        t_color = "#e0a020" if n_topics == 0 else "#c8a800"
        i_color = "#e0a020" if n_items  == 0 else "gray"
        self._counts_lbl.setText(
            f'<span style="color: {t_color};">Topics: {n_topics} ready</span>'
            f'  <span style="color: {i_color};">Items: {n_items} ready</span>'
        )
        for row in self._linked_rows:
            self._refresh_tag_count(row)

    def _test_filter(self, query: str) -> None:
        """Show the card count for a filter string."""
        ready = self._ready_filter_from_checks()
        count = len(mw.col.find_cards(f"{query} {ready}"))
        showInfo(f'Filter "{query}" matches {count} ready card(s).')

    def accept(self) -> None:
        """Warn if both filters return no cards, then accept."""
        try:
            ready = self._ready_filter_from_checks()
            tf  = self._topics_filter_edit.text().strip() or "deck:Topics"
            itf = self._items_filter_edit.text().strip()  or "-deck:Topics"
            n_topics = len(mw.col.find_cards(f"{tf} {ready}"))
            n_items  = len(mw.col.find_cards(f"{itf} {ready}"))
            if n_topics == 0 and n_items == 0:
                from aqt.qt import QMessageBox
                r = QMessageBox.warning(
                    self, "No Cards Found",
                    "Both filters returned 0 ready cards.\n"
                    "The session will be empty.\n\nContinue anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if r != QMessageBox.StandardButton.Yes:
                    return
        except Exception:
            pass
        super().accept()

    # ------------------------------------------------------------------
    # Statistics history actions
    # ------------------------------------------------------------------

    def _confirm(self, title: str, message: str) -> bool:
        return QMessageBox.question(
            self, title, message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    def _delete_daily(self) -> None:
        if not self._confirm("Delete Today's Data",
                             "Delete all statistics for today?\nThis cannot be undone."):
            return
        delete_daily_stats(_ADDON_DIR)
        showInfo("Today's statistics have been deleted.")

    def _delete_session(self) -> None:
        if not self._confirm("Delete Session Data",
                             "Clear the last session's statistics?"):
            return
        if self._on_clear_session:
            self._on_clear_session()
        showInfo("Session statistics have been cleared.")

    def _delete_lifetime(self) -> None:
        if not self._confirm("Delete All-Time Data",
                             "Delete all lifetime statistics?\nThis cannot be undone."):
            return
        delete_lifetime_stats(_ADDON_DIR)
        showInfo("All-time statistics have been deleted.")

    def _delete_all(self) -> None:
        if not self._confirm("Delete All History",
                             "Delete ALL statistics (today, all time, and session)?\n"
                             "This cannot be undone."):
            return
        delete_all_stats(_ADDON_DIR)
        if self._on_clear_session:
            self._on_clear_session()
        showInfo("All statistics history has been deleted.")

    def _export_json(self) -> None:
        raw = load_stats(_ADDON_DIR)
        if not raw:
            showInfo("No statistics data to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Statistics", "incremento_stats.json",
            "JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=2, sort_keys=True)
            showInfo(f"Statistics exported to:\n{path}")
        except Exception as e:
            showInfo(f"Export failed: {e}")

    # ------------------------------------------------------------------
    # Public accessor — call after exec() returns Accepted
    # ------------------------------------------------------------------

    def to_config(self) -> SchedulerConfig:
        """Return a SchedulerConfig built from the current widget state."""
        raw = {r["tag"]: r["slider"].value() for r in self._linked_rows}
        return SchedulerConfig(
            session_card_count=self._count_spin.value(),
            topics_rate=1.0 - self._topics_slider.value() / 100.0,
            random_rate=self._random_slider.value() / 100.0,
            pdf_rate=(100 - self._pdf_slider.value()) / 100.0,
            use_tags=bool(raw),
            tag_weights={tag: v / 100.0 for tag, v in raw.items()},
            include_rest=self._no_tags_cb.isChecked(),
            scheduler_scope=self._scope_combo.currentData(),
            day_end_time=self._get_day_end_time(),
            priority_order=self._get_priority_order(),
            enforce_priority=self._enforce_cb.isChecked(),
            topics_filter=self._topics_filter_edit.text().strip() or "deck:Topics",
            items_filter=self._items_filter_edit.text().strip() or "-deck:Topics",
            include_new=self._cb_new.isChecked(),
            include_learning=self._cb_learning.isChecked(),
            include_due=self._cb_due.isChecked(),
            preserve_order=self._preserve_order_cb.isChecked(),
            show_debug=self._show_debug_cb.isChecked(),
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_config(self) -> None:
        config = mw.addonManager.getConfig(__name__) or {}
        config["dialog"] = {
            "session_card_count": self._count_spin.value(),
            "topics_slider": self._topics_slider.value(),
            "random_slider": self._random_slider.value(),
            "pdf_slider": self._pdf_slider.value(),
            "no_tags_checked": self._no_tags_cb.isChecked(),
            "priority_order": self._get_priority_order(),
            "enforce_priority": self._enforce_cb.isChecked(),
            "scheduler_scope": self._scope_combo.currentData(),
            "day_end_time": self._get_day_end_time(),
            "tag_rows": [
                {
                    "tag": row["tag"],
                    "weight": row["slider"].value(),
                    "locked": row["lock_cb"].isChecked(),
                }
                for row in self._linked_rows
            ],
            "topics_filter": self._topics_filter_edit.text().strip() or "deck:Topics",
            "items_filter": self._items_filter_edit.text().strip() or "-deck:Topics",
            "include_new":      self._cb_new.isChecked(),
            "include_learning": self._cb_learning.isChecked(),
            "include_due":      self._cb_due.isChecked(),
            "preserve_order":   self._preserve_order_cb.isChecked(),
            "show_debug":       self._show_debug_cb.isChecked(),
        }
        mw.addonManager.writeConfig(__name__, config)
