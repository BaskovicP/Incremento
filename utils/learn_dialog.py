from aqt import mw
from aqt.qt import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QCheckBox, QComboBox, QPushButton, QWidget, Qt, qconnect,
    QTimeEdit, QTime,
)

from .scheduler_config import SchedulerConfig, NO_TAGS_KEY


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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scheduler Settings")
        self.setMinimumWidth(520)
        self._linked_rows: list[dict] = []
        self._updating = False
        config = mw.addonManager.getConfig(__name__) or {}
        self._saved = config.get("dialog", {})
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # -- Topics / Items row --
        # Left label shows topics%, right label shows items% (they sum to 100).
        # topics_rate = 1 - slider/100, so slider right = more items.
        topics_val = self._saved.get("topics_slider", 10)
        topics_row = QHBoxLayout()
        self._topics_left_lbl = QLabel(f"{100 - topics_val}%")
        self._topics_left_lbl.setFixedWidth(36)
        topics_row.addWidget(self._topics_left_lbl)
        topics_row.addWidget(QLabel("Topics"))
        self._topics_slider = QSlider(Qt.Orientation.Horizontal)
        self._topics_slider.setRange(0, 100)
        self._topics_slider.setValue(topics_val)
        topics_row.addWidget(self._topics_slider)
        topics_row.addWidget(QLabel("Items"))
        self._topics_right_lbl = QLabel(f"{topics_val}%")
        self._topics_right_lbl.setFixedWidth(36)
        topics_row.addWidget(self._topics_right_lbl)
        layout.addLayout(topics_row)

        # -- Priority / Random row --
        # Left label shows priority%, right label shows random%.
        # random_rate = slider/100, so slider right = more random.
        random_val = self._saved.get("random_slider", 99)
        random_row = QHBoxLayout()
        self._random_left_lbl = QLabel(f"{100 - random_val}%")
        self._random_left_lbl.setFixedWidth(36)
        random_row.addWidget(self._random_left_lbl)
        random_row.addWidget(QLabel("Priority"))
        self._random_slider = QSlider(Qt.Orientation.Horizontal)
        self._random_slider.setRange(0, 100)
        self._random_slider.setValue(random_val)
        random_row.addWidget(self._random_slider)
        random_row.addWidget(QLabel("Random"))
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

        # -- Scheduler scope --
        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel("Scheduler scope:"))
        self._scope_combo = QComboBox()
        self._scope_combo.addItem("Session",  "session")
        self._scope_combo.addItem("Daily",    "daily")
        self._scope_combo.addItem("Lifetime", "lifetime")
        saved_scope = self._saved.get("scheduler_scope", "session")
        for i in range(self._scope_combo.count()):
            if self._scope_combo.itemData(i) == saved_scope:
                self._scope_combo.setCurrentIndex(i)
                break
        scope_row.addWidget(self._scope_combo)

        self._day_end_label = QLabel("  Day ends at:")
        scope_row.addWidget(self._day_end_label)

        self._day_end_preset = QComboBox()
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
            "Checked: exhaust each quota in order (e.g. all tag-A cards, then tag-B).\n"
            "Unchecked: soft debt-based ordering — all dimensions interleave randomly."
        )
        self._enforce_cb.setChecked(self._saved.get("enforce_priority", True))
        priority_header.addWidget(QLabel("Scheduling priority order:"))
        priority_header.addStretch()
        priority_header.addWidget(self._enforce_cb)
        layout.addLayout(priority_header)

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
        self._priority_order_widget.setEnabled(self._enforce_cb.isChecked())
        qconnect(self._enforce_cb.stateChanged,
                 lambda _: self._priority_order_widget.setEnabled(self._enforce_cb.isChecked()))
        qconnect(self._priority_combos[0].currentIndexChanged,
                 lambda _: self._on_priority_changed(0))
        qconnect(self._priority_combos[1].currentIndexChanged,
                 lambda _: self._on_priority_changed(1))

        # -- Tag distribution --
        layout.addWidget(QLabel("Tag distribution"))

        add_tag_row = QHBoxLayout()
        self._tag_combo = QComboBox()
        self._tag_combo.addItems(sorted(mw.col.tags.all()))
        add_tag_row.addWidget(self._tag_combo)
        add_btn = QPushButton("Add")
        qconnect(add_btn.clicked, lambda: self._add_tag_row(self._tag_combo.currentText()))
        add_tag_row.addWidget(add_btn)
        layout.addLayout(add_tag_row)

        self._no_tags_cb = QCheckBox("After exhausting tag groups, fill with rest of cards")
        self._no_tags_cb.setChecked(self._saved.get("no_tags_checked", True))
        layout.addWidget(self._no_tags_cb)

        self._tags_container = QWidget()
        self._tags_layout = QVBoxLayout(self._tags_container)
        self._tags_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tags_container)

        # Restore saved tag rows (no redistribution until all are loaded)
        for entry in self._saved.get("tag_rows", []):
            self._add_tag_row(entry["tag"], entry.get("weight", 50),
                              locked=entry.get("locked", False), redistribute=False)
        self._rebalance()

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
                       locked: bool) -> tuple[QWidget, QHBoxLayout, QSlider, QLabel, QCheckBox]:
        """Create the shared [label | slider | pct | lock] part of a tag row."""
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(QLabel(label_text))

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

        # Disable slider when locked; re-enable and rebalance on toggle
        slider.setEnabled(not locked)
        qconnect(lock_cb.stateChanged,
                 lambda _, cb=lock_cb, s=slider: s.setEnabled(not cb.isChecked()))
        qconnect(lock_cb.stateChanged, lambda _: self._rebalance())

        return row_widget, row_layout, slider, pct_label, lock_cb

    def _add_tag_row(self, tag: str, weight: int = 50, locked: bool = False,
                     redistribute: bool = True) -> None:
        if not tag:
            return
        if any(r["tag"] == tag for r in self._linked_rows):
            return

        row_widget, row_layout, slider, pct_label, lock_cb = self._make_row_base(
            tag, weight, locked
        )
        row_dict = {"tag": tag, "slider": slider, "pct_label": pct_label,
                    "lock_cb": lock_cb, "widget": row_widget}
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

        if redistribute:
            self._rebalance()

    def _remove_row(self, row_dict: dict) -> None:
        if row_dict in self._linked_rows:
            self._linked_rows.remove(row_dict)
        row_dict["widget"].deleteLater()
        self._rebalance()

    # ------------------------------------------------------------------
    # Linked-slider logic (lock-aware)
    # ------------------------------------------------------------------

    def _rebalance(self) -> None:
        """Redistribute unlocked rows so all rows together sum to 100%."""
        rows = self._linked_rows
        if not rows:
            return
        locked_total = sum(r["slider"].value() for r in rows if r["lock_cb"].isChecked())
        unlocked = [r for r in rows if not r["lock_cb"].isChecked()]
        if not unlocked:
            return
        self._distribute_remaining(unlocked, max(0, 100 - locked_total))

    def _distribute_remaining(self, rows: list[dict], total: int) -> None:
        """Set sliders in rows to proportionally sum to total."""
        if not rows:
            return
        total = max(0, total)
        self._updating = True
        try:
            current = sum(r["slider"].value() for r in rows)
            if current == 0:
                base = total // len(rows)
                rem = total - base * len(rows)
                for i, r in enumerate(rows):
                    v = base + (rem if i == 0 else 0)
                    r["slider"].setValue(v)
                    r["pct_label"].setText(f"{v}%")
            else:
                new_vals = [round(r["slider"].value() / current * total) for r in rows]
                new_vals[-1] = max(0, new_vals[-1] + (total - sum(new_vals)))
                for r, v in zip(rows, new_vals):
                    r["slider"].setValue(v)
                    r["pct_label"].setText(f"{v}%")
        finally:
            self._updating = False

    def _on_weight_changed(self, changed_row: dict) -> None:
        if self._updating:
            return

        locked_total = sum(r["slider"].value() for r in self._linked_rows
                           if r["lock_cb"].isChecked() and r is not changed_row)
        budget = 100 - locked_total  # max this slider + unlocked others can share

        unlocked_others = [r for r in self._linked_rows
                           if r is not changed_row and not r["lock_cb"].isChecked()]

        # If this is the only free slider it must hold the entire remaining budget.
        if not unlocked_others:
            self._updating = True
            try:
                changed_row["slider"].setValue(budget)
                changed_row["pct_label"].setText(f"{budget}%")
            finally:
                self._updating = False
            return

        # Clamp so locked rows are never crowded out.
        new_val = min(changed_row["slider"].value(), budget)
        self._updating = True
        try:
            changed_row["slider"].setValue(new_val)
        finally:
            self._updating = False
        changed_row["pct_label"].setText(f"{new_val}%")

        self._distribute_remaining(unlocked_others, budget - new_val)

    # ------------------------------------------------------------------
    # Public accessor — call after exec() returns Accepted
    # ------------------------------------------------------------------

    def to_config(self) -> SchedulerConfig:
        """Return a SchedulerConfig built from the current widget state."""
        raw = {r["tag"]: r["slider"].value() for r in self._linked_rows}
        total = sum(raw.values()) or 1
        return SchedulerConfig(
            topics_rate=1.0 - self._topics_slider.value() / 100.0,
            random_rate=self._random_slider.value() / 100.0,
            use_tags=bool(raw),
            tag_weights={tag: v / total for tag, v in raw.items()},
            include_rest=self._no_tags_cb.isChecked(),
            scheduler_scope=self._scope_combo.currentData(),
            day_end_time=self._get_day_end_time(),
            priority_order=self._get_priority_order(),
            enforce_priority=self._enforce_cb.isChecked(),
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_config(self) -> None:
        config = mw.addonManager.getConfig(__name__) or {}
        config["dialog"] = {
            "topics_slider": self._topics_slider.value(),
            "random_slider": self._random_slider.value(),
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
        }
        mw.addonManager.writeConfig(__name__, config)
