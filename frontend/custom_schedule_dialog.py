from __future__ import annotations

from aqt.qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

try:
    from ..backend.custom_schedule import (
        MODE_FIXED_REPEAT,
        MODE_MINIMUM_CADENCE,
        MODE_ONE_TIME,
        configured_custom_schedule_default_mode,
        configured_custom_schedule_presets,
        format_custom_schedule_mode,
        format_custom_schedule_rule,
        normalize_custom_schedule_mode,
        normalize_custom_schedule_preset,
        normalize_custom_schedule_rule,
        normalize_custom_schedule_unit,
    )
    from ..backend.db import get_custom_schedule_rules
    from ..backend.paths import get_active_profile as _active_profile
except ImportError:
    from backend.custom_schedule import (  # type: ignore
        MODE_FIXED_REPEAT,
        MODE_MINIMUM_CADENCE,
        MODE_ONE_TIME,
        configured_custom_schedule_default_mode,
        configured_custom_schedule_presets,
        format_custom_schedule_mode,
        format_custom_schedule_rule,
        normalize_custom_schedule_mode,
        normalize_custom_schedule_preset,
        normalize_custom_schedule_rule,
        normalize_custom_schedule_unit,
    )
    from backend.db import get_custom_schedule_rules  # type: ignore
    from backend.paths import get_active_profile as _active_profile  # type: ignore


class CustomScheduleDialog(QDialog):
    def __init__(
        self,
        addon_dir: str,
        card_ids: list[int],
        *,
        config: dict | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._addon_dir = addon_dir
        self._card_ids = [int(card_id) for card_id in card_ids]
        self._config = config or {}
        self._clear_requested = False
        self.setWindowTitle("Custom Schedule")
        self.setMinimumWidth(460)

        self._existing_rules = get_custom_schedule_rules(
            addon_dir,
            _active_profile(),
            self._card_ids,
        )
        self._shared_rule = self._resolve_shared_rule()

        root = QVBoxLayout(self)
        root.setSpacing(10)

        selection_label = QLabel(
            f"Apply a recurring schedule rule to {len(self._card_ids)} selected "
            f"card{'s' if len(self._card_ids) != 1 else ''}."
        )
        selection_label.setWordWrap(True)
        root.addWidget(selection_label)

        self._current_rule_label = QLabel()
        self._current_rule_label.setWordWrap(True)
        root.addWidget(self._current_rule_label)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)

        self._preset_combo = QComboBox()
        self._preset_combo.addItem("Quick preset…", None)
        for index, preset in enumerate(configured_custom_schedule_presets(self._config), start=1):
            normalized = normalize_custom_schedule_preset(preset, index=index)
            self._preset_combo.addItem(str(normalized["label"]), normalized)
        self._preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        form.addRow("Preset:", self._preset_combo)

        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(1, 999)
        self._interval_spin.valueChanged.connect(self._update_preview)
        form.addRow("Repeat every:", self._interval_spin)

        self._unit_combo = QComboBox()
        self._unit_combo.addItem("Days", "days")
        self._unit_combo.addItem("Weeks", "weeks")
        self._unit_combo.addItem("Months", "months")
        self._unit_combo.currentIndexChanged.connect(self._update_preview)
        form.addRow("Unit:", self._unit_combo)

        self._mode_combo = QComboBox()
        self._mode_combo.addItem(format_custom_schedule_mode(MODE_MINIMUM_CADENCE), MODE_MINIMUM_CADENCE)
        self._mode_combo.addItem(format_custom_schedule_mode(MODE_FIXED_REPEAT), MODE_FIXED_REPEAT)
        self._mode_combo.addItem(format_custom_schedule_mode(MODE_ONE_TIME), MODE_ONE_TIME)
        self._mode_combo.currentIndexChanged.connect(self._update_preview)
        form.addRow("Behavior:", self._mode_combo)

        self._apply_now_cb = QCheckBox("Apply to the current due date now")
        self._apply_now_cb.setChecked(True)
        form.addRow("", self._apply_now_cb)

        root.addLayout(form)

        self._preview = QLabel()
        self._preview.setWordWrap(True)
        root.addWidget(self._preview)

        hint = QLabel(
            "Minimum cadence keeps normal scheduling but prevents the card from drifting later than this rule. "
            "Repeat exactly always resets the next due date to this rule. "
            "One-time set due applies once and then clears itself."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        buttons_row = QHBoxLayout()
        self._clear_btn = QPushButton("Clear Rule")
        self._clear_btn.clicked.connect(self._on_clear_clicked)
        buttons_row.addWidget(self._clear_btn)
        buttons_row.addStretch()
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)
        buttons_row.addWidget(self._button_box)
        root.addLayout(buttons_row)

        self._load_initial_state()
        self._update_preview()

    def _resolve_shared_rule(self) -> dict | None:
        unique: set[tuple[bool, str, int, str, str]] = set()
        candidate: dict | None = None
        for rule in self._existing_rules.values():
            normalized = normalize_custom_schedule_rule(rule)
            candidate = normalized
            unique.add(
                (
                    bool(normalized["enabled"]),
                    str(normalized["mode"]),
                    int(normalized["interval_value"]),
                    str(normalized["interval_unit"]),
                    str(normalized["preset_label"]),
                )
            )
        if len(unique) == 1:
            return candidate
        return None

    def _load_initial_state(self) -> None:
        if self._shared_rule:
            rule = normalize_custom_schedule_rule(self._shared_rule)
        else:
            rule = normalize_custom_schedule_rule(
                {
                    "mode": configured_custom_schedule_default_mode(self._config),
                    "interval_value": 2,
                    "interval_unit": "days",
                }
            )
        self._interval_spin.setValue(int(rule["interval_value"]))
        self._set_combo_data(self._unit_combo, str(rule["interval_unit"]))
        self._set_combo_data(self._mode_combo, str(rule["mode"]))
        self._refresh_current_rule_label()
        self._clear_btn.setEnabled(bool(self._existing_rules))

    def _refresh_current_rule_label(self) -> None:
        if self._shared_rule:
            self._current_rule_label.setText(
                f"Current rule: <b>{format_custom_schedule_rule(self._shared_rule)}</b>"
            )
            return
        if self._existing_rules:
            self._current_rule_label.setText("Current rule: <i>Mixed selection</i>")
            return
        self._current_rule_label.setText("Current rule: <i>No custom rule</i>")

    def _set_combo_data(self, combo: QComboBox, value: str) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return

    def _on_preset_changed(self, index: int) -> None:
        if index <= 0:
            return
        preset = self._preset_combo.itemData(index)
        if not isinstance(preset, dict):
            return
        normalized = normalize_custom_schedule_preset(preset, index=index)
        self._interval_spin.setValue(int(normalized["interval_value"]))
        self._set_combo_data(self._unit_combo, str(normalized["interval_unit"]))
        self._update_preview()

    def _on_clear_clicked(self) -> None:
        self._clear_requested = True
        self.accept()

    def _update_preview(self, *_args) -> None:
        rule = self.selected_rule
        self._preview.setText(f"Preview: <b>{format_custom_schedule_rule(rule)}</b>")

    @property
    def clear_requested(self) -> bool:
        return bool(self._clear_requested)

    @property
    def apply_now(self) -> bool:
        return bool(self._apply_now_cb.isChecked())

    @property
    def selected_rule(self) -> dict:
        interval_value = int(self._interval_spin.value())
        interval_unit = normalize_custom_schedule_unit(self._unit_combo.currentData())
        mode = normalize_custom_schedule_mode(self._mode_combo.currentData())
        preset = self._preset_combo.currentData()
        preset_label = ""
        if isinstance(preset, dict):
            normalized = normalize_custom_schedule_preset(preset)
            if (
                int(normalized["interval_value"]) == interval_value
                and str(normalized["interval_unit"]) == interval_unit
            ):
                preset_label = str(normalized["label"])
        return normalize_custom_schedule_rule(
            {
                "enabled": True,
                "mode": mode,
                "interval_value": interval_value,
                "interval_unit": interval_unit,
                "preset_label": preset_label,
            }
        )
