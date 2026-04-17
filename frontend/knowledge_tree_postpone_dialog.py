from __future__ import annotations

from typing import Iterable

from aqt import mw
from aqt.qt import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    qconnect,
)
from aqt.utils import showInfo, tooltip

try:
    from aqt import dialogs
except Exception:
    dialogs = None

try:
    from ..backend.knowledge_tree_postpone import (
        METHOD_PARAMETERS,
        METHOD_SKIP_TOP,
        SCOPE_ALL_OUTSTANDING,
        SCOPE_CURRENT_BROWSER,
        SCOPE_SELECTED_BRANCH,
        SUBTREE_MODE_CONSERVATIVE,
        SUBTREE_MODE_IGNORE,
        SUBTREE_MODE_LIBERAL,
        SUBTREE_MODE_RESPECT,
        apply_postpone_plan,
        branch_scope_label,
        browser_scope_label,
        default_postpone_preset,
        delete_postpone_preset,
        format_simulation_summary,
        get_branch_attached_preset,
        get_postpone_preset,
        list_subbranch_presets,
        load_default_postpone_preset,
        load_postpone_presets,
        normalize_postpone_preset,
        save_postpone_preset,
        set_default_postpone_preset,
        simulate_postpone_plan,
    )
except ImportError:
    from knowledge_tree_postpone import (  # type: ignore
        METHOD_PARAMETERS,
        METHOD_SKIP_TOP,
        SCOPE_ALL_OUTSTANDING,
        SCOPE_CURRENT_BROWSER,
        SCOPE_SELECTED_BRANCH,
        SUBTREE_MODE_CONSERVATIVE,
        SUBTREE_MODE_IGNORE,
        SUBTREE_MODE_LIBERAL,
        SUBTREE_MODE_RESPECT,
        apply_postpone_plan,
        branch_scope_label,
        browser_scope_label,
        default_postpone_preset,
        delete_postpone_preset,
        format_simulation_summary,
        get_branch_attached_preset,
        get_postpone_preset,
        list_subbranch_presets,
        load_default_postpone_preset,
        load_postpone_presets,
        normalize_postpone_preset,
        save_postpone_preset,
        set_default_postpone_preset,
        simulate_postpone_plan,
    )


def resolve_current_browser_card_ids() -> list[int]:
    if dialogs is None or mw is None or getattr(mw, "col", None) is None:
        return []
    try:
        registry = getattr(dialogs, "_dialogs", {}) or {}
        entry = registry.get("Browser")
    except Exception:
        entry = None
    if not entry:
        return []

    browser = entry[1] if isinstance(entry, (tuple, list)) and len(entry) > 1 else entry
    if browser is None:
        return []

    try:
        selected = [int(card_id) for card_id in list(browser.selected_cards() or [])]
    except Exception:
        selected = []
    if selected:
        return _unique_ints(selected)

    search = ""
    for attr_name in ("_lastSearchTxt",):
        value = getattr(browser, attr_name, "")
        if isinstance(value, str) and value.strip():
            search = value.strip()
            break
    if not search:
        try:
            value = browser.current_search()
            search = str(value or "").strip()
        except Exception:
            search = ""
    if not search:
        try:
            model = browser.table._model
            raw_items = list(getattr(model, "_items", []) or [])
            return _unique_ints(raw_items)
        except Exception:
            return []
    try:
        return _unique_ints(mw.col.find_cards(search))
    except Exception:
        return []


def _unique_ints(values: Iterable[int]) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for raw in list(values or []):
        try:
            value = int(raw)
        except Exception:
            continue
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _make_double_spin(
    *,
    minimum: float = 0.0,
    maximum: float = 9999.0,
    decimals: int = 2,
    value: float = 0.0,
) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setDecimals(decimals)
    spin.setSingleStep(0.1)
    spin.setValue(value)
    spin.setMinimumWidth(92)
    return spin


def _make_int_spin(
    *,
    minimum: int = 0,
    maximum: int = 999999,
    value: int = 0,
) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(minimum, maximum)
    spin.setValue(value)
    spin.setMinimumWidth(92)
    return spin


class _SimulationDialog(QDialog):
    def __init__(self, summary_text: str, parent=None):
        super().__init__(parent)
        self._summary_text = str(summary_text or "").strip()
        self.setWindowTitle("Information")
        self.setMinimumWidth(560)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        self._body = QTextEdit()
        self._body.setReadOnly(True)
        self._body.setMinimumHeight(220)
        self._body.setText(self._summary_text)
        root.addWidget(self._body)

        buttons = QHBoxLayout()
        ok_btn = QPushButton("OK")
        copy_btn = QPushButton("Copy")
        buttons.addStretch(1)
        buttons.addWidget(ok_btn)
        buttons.addWidget(copy_btn)
        root.addLayout(buttons)

        qconnect(ok_btn.clicked, self.accept)
        qconnect(copy_btn.clicked, self._copy_text)

    def _copy_text(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._summary_text)
            tooltip("Simulation summary copied.")


class KnowledgeTreePostponeDialog(QDialog):
    def __init__(
        self,
        addon_dir: str,
        *,
        profile: str,
        branch_root_card_id: int | None = None,
        browser_card_ids: Iterable[int] | None = None,
        browser_scope_name: str | None = None,
        initial_scope: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._addon_dir = addon_dir
        self._profile = profile
        self._branch_root_card_id = None if branch_root_card_id is None else int(branch_root_card_id)
        self._browser_card_ids = _unique_ints(browser_card_ids)
        self._browser_scope_name = str(browser_scope_name or "").strip()
        self._initial_scope = str(initial_scope or "").strip()
        self._presets: list[dict] = []
        self._loading_preset = False
        self._last_simulation: dict | None = None

        self.setWindowTitle("Postpone outstanding elements")
        self.resize(980, 760)
        self._apply_style()

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        self._tabs = QTabWidget(self)
        root.addWidget(self._tabs, 1)

        self._scope_tab = QWidget(self)
        self._parameters_tab = QWidget(self)
        self._adjust_tab = QWidget(self)
        self._tabs.addTab(self._scope_tab, "Scope")
        self._tabs.addTab(self._parameters_tab, "Parameters")
        self._tabs.addTab(self._adjust_tab, "Adjust")

        self._build_scope_tab()
        self._build_parameters_tab()
        self._build_adjust_tab()

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._postpone_btn = QPushButton("Postpone")
        self._simulate_btn = QPushButton("Simulate")
        self._close_btn = QPushButton("Close")
        self._help_btn = QPushButton("Help")
        buttons.addWidget(self._postpone_btn)
        buttons.addWidget(self._simulate_btn)
        buttons.addWidget(self._close_btn)
        buttons.addWidget(self._help_btn)
        root.addLayout(buttons)

        qconnect(self._postpone_btn.clicked, self._apply_postpone)
        qconnect(self._simulate_btn.clicked, self._simulate_postpone)
        qconnect(self._close_btn.clicked, self.reject)
        qconnect(self._help_btn.clicked, self._show_help)

        self._refresh_presets()
        self._load_initial_preset()
        self._refresh_scope_state()
        self._refresh_delay_labels()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QGroupBox {
              border: 1px solid rgba(128,128,128,0.24);
              border-radius: 8px;
              margin-top: 10px;
              padding-top: 10px;
            }
            QGroupBox::title {
              subcontrol-origin: margin;
              left: 10px;
              padding: 0 4px;
              font-weight: 600;
            }
            QTextEdit, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
              min-height: 28px;
            }
            QLabel#PostponeHint {
              color: palette(mid);
              font-size: 11px;
            }
            QLabel#PostponeHeading {
              font-weight: 700;
            }
            """
        )

    def _build_scope_tab(self) -> None:
        outer = QVBoxLayout(self._scope_tab)
        outer.setSpacing(10)

        subset_box = QGroupBox("Subset")
        subset_layout = QVBoxLayout(subset_box)
        self._scope_group = QButtonGroup(self)
        self._scope_all = QRadioButton("All outstanding repetitions")
        self._scope_branch = QRadioButton("Selected branch or category")
        self._scope_browser = QRadioButton(self._browser_scope_name or "Current browser")
        self._scope_group.addButton(self._scope_all)
        self._scope_group.addButton(self._scope_branch)
        self._scope_group.addButton(self._scope_browser)
        subset_layout.addWidget(self._scope_all)
        subset_layout.addWidget(self._scope_branch)
        subset_layout.addWidget(self._scope_browser)
        outer.addWidget(subset_box)

        method_box = QGroupBox("Method")
        method_layout = QGridLayout(method_box)
        self._method_group = QButtonGroup(self)
        self._method_skip_top = QRadioButton("Skip the following number of top priority elements")
        self._method_parameters = QRadioButton("Skip elements as defined by Parameters (next page)")
        self._skip_top_spin = _make_int_spin(value=50)
        self._method_group.addButton(self._method_skip_top)
        self._method_group.addButton(self._method_parameters)
        method_layout.addWidget(self._method_skip_top, 0, 0)
        method_layout.addWidget(self._skip_top_spin, 0, 1)
        method_layout.addWidget(self._method_parameters, 1, 0, 1, 2)
        outer.addWidget(method_box)

        settings_box = QGroupBox("Settings")
        settings_layout = QGridLayout(settings_box)
        settings_layout.addWidget(QLabel("Name:"), 0, 0)
        self._preset_combo = QComboBox()
        self._preset_combo.setEditable(True)
        settings_layout.addWidget(self._preset_combo, 0, 1, 1, 3)
        settings_layout.addWidget(QLabel("Branch scope:"), 1, 0)
        self._branch_scope_edit = QLineEdit()
        self._branch_scope_edit.setReadOnly(True)
        settings_layout.addWidget(self._branch_scope_edit, 1, 1, 1, 3)
        self._save_btn = QPushButton("Save")
        self._default_btn = QPushButton("Default")
        self._delete_btn = QPushButton("Delete")
        settings_layout.addWidget(self._save_btn, 2, 1)
        settings_layout.addWidget(self._default_btn, 2, 2)
        settings_layout.addWidget(self._delete_btn, 2, 3)
        outer.addWidget(settings_box)

        outer.addStretch(1)

        qconnect(self._scope_all.toggled, lambda _checked: self._refresh_scope_state())
        qconnect(self._scope_branch.toggled, lambda _checked: self._refresh_scope_state())
        qconnect(self._scope_browser.toggled, lambda _checked: self._refresh_scope_state())
        qconnect(self._method_skip_top.toggled, lambda checked: self._skip_top_spin.setEnabled(bool(checked)))
        qconnect(self._preset_combo.activated, lambda _idx: self._load_selected_preset())
        if self._preset_combo.lineEdit() is not None:
            qconnect(self._preset_combo.lineEdit().editingFinished, self._load_selected_preset)
        qconnect(self._save_btn.clicked, self._save_current_preset)
        qconnect(self._default_btn.clicked, self._mark_current_preset_default)
        qconnect(self._delete_btn.clicked, self._delete_selected_preset)

    def _build_parameters_tab(self) -> None:
        outer = QVBoxLayout(self._parameters_tab)
        outer.setSpacing(10)

        top_row = QHBoxLayout()
        self._restore_defaults_btn = QPushButton("Restore defaults")
        top_row.addWidget(self._restore_defaults_btn)
        top_row.addStretch(1)
        outer.addLayout(top_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)

        grid.addWidget(QLabel(""), 0, 0)
        items_heading = QLabel("Items")
        items_heading.setObjectName("PostponeHeading")
        topics_heading = QLabel("Topics")
        topics_heading.setObjectName("PostponeHeading")
        grid.addWidget(items_heading, 0, 1, 1, 2)
        grid.addWidget(topics_heading, 0, 3, 1, 2)

        row = 1
        self._item_delay_factor = _make_double_spin(minimum=1.0, maximum=10.0, value=1.2)
        self._topic_delay_factor = _make_double_spin(minimum=1.0, maximum=10.0, value=1.5)
        self._item_delay_percent = QLabel("")
        self._topic_delay_percent = QLabel("")
        grid.addWidget(QLabel("Delay factor:"), row, 0)
        grid.addWidget(self._item_delay_factor, row, 1)
        grid.addWidget(self._item_delay_percent, row, 2)
        grid.addWidget(self._topic_delay_factor, row, 3)
        grid.addWidget(self._topic_delay_percent, row, 4)

        row += 1
        self._item_max_interval = _make_int_spin(value=50)
        self._topic_max_interval = _make_int_spin(value=100)
        grid.addWidget(QLabel("Maximum interval:"), row, 0)
        grid.addWidget(self._item_max_interval, row, 1, 1, 2)
        grid.addWidget(self._topic_max_interval, row, 3, 1, 2)

        row += 1
        self._item_min_interval = _make_int_spin(value=1)
        self._topic_min_interval = _make_int_spin(value=6)
        grid.addWidget(QLabel("Minimum interval:"), row, 0)
        grid.addWidget(self._item_min_interval, row, 1, 1, 2)
        grid.addWidget(self._topic_min_interval, row, 3, 1, 2)

        row += 1
        skip_hint = QLabel("Skip conditions:")
        skip_hint.setObjectName("PostponeHeading")
        grid.addWidget(skip_hint, row, 0)

        row += 1
        self._item_skip = QCheckBox("Skip items")
        self._topic_skip = QCheckBox("Skip topics")
        grid.addWidget(QLabel("Type:"), row, 0)
        grid.addWidget(self._item_skip, row, 1, 1, 2)
        grid.addWidget(self._topic_skip, row, 3, 1, 2)

        row += 1
        self._item_interval_beyond = _make_int_spin(value=500)
        self._topic_interval_beyond = _make_int_spin(value=800)
        grid.addWidget(QLabel("Interval beyond:"), row, 0)
        grid.addWidget(self._item_interval_beyond, row, 1, 1, 2)
        grid.addWidget(self._topic_interval_beyond, row, 3, 1, 2)

        row += 1
        self._item_fi_below = _make_double_spin(minimum=0.0, maximum=100.0, value=6.0)
        self._item_fi_below.setEnabled(False)
        self._item_fi_below.setSpecialValueText("N/A")
        self._item_fi_below.setValue(0.0)
        self._topic_fi_placeholder = QLineEdit("N/A")
        self._topic_fi_placeholder.setReadOnly(True)
        grid.addWidget(QLabel("Forgetting index below:"), row, 0)
        grid.addWidget(self._item_fi_below, row, 1, 1, 2)
        grid.addWidget(self._topic_fi_placeholder, row, 3, 1, 2)

        row += 1
        self._item_afactor_placeholder = QLineEdit("N/A")
        self._item_afactor_placeholder.setReadOnly(True)
        self._topic_a_factor_below = _make_double_spin(minimum=0.0, maximum=100.0, value=1.01)
        grid.addWidget(QLabel("A-Factor below:"), row, 0)
        grid.addWidget(self._item_afactor_placeholder, row, 1, 1, 2)
        grid.addWidget(self._topic_a_factor_below, row, 3, 1, 2)

        row += 1
        self._item_postpone_count = _make_int_spin(value=50)
        self._topic_postpone_count = _make_int_spin(value=100)
        grid.addWidget(QLabel("Postpone count:"), row, 0)
        grid.addWidget(self._item_postpone_count, row, 1, 1, 2)
        grid.addWidget(self._topic_postpone_count, row, 3, 1, 2)

        row += 1
        self._item_priority_threshold = _make_double_spin(minimum=0.0, maximum=100.0, value=6.0)
        self._topic_priority_threshold = _make_double_spin(minimum=0.0, maximum=100.0, value=3.0)
        grid.addWidget(QLabel("Priority (%):"), row, 0)
        grid.addWidget(self._item_priority_threshold, row, 1, 1, 2)
        grid.addWidget(self._topic_priority_threshold, row, 3, 1, 2)

        outer.addLayout(grid)
        outer.addStretch(1)

        qconnect(self._restore_defaults_btn.clicked, self._restore_defaults)
        qconnect(self._item_delay_factor.valueChanged, lambda _value: self._refresh_delay_labels())
        qconnect(self._topic_delay_factor.valueChanged, lambda _value: self._refresh_delay_labels())

    def _build_adjust_tab(self) -> None:
        outer = QVBoxLayout(self._adjust_tab)
        outer.setSpacing(10)

        subbranch_box = QGroupBox("Sub-branch postpones")
        subbranch_layout = QGridLayout(subbranch_box)
        self._subbranch_group = QButtonGroup(self)
        self._respect_settings = QRadioButton("Respect settings")
        self._ignore_settings = QRadioButton("Ignore settings")
        self._conservative_settings = QRadioButton("Always choose most conservative settings")
        self._liberal_settings = QRadioButton("Always choose most liberal settings")
        for button in (
            self._respect_settings,
            self._ignore_settings,
            self._conservative_settings,
            self._liberal_settings,
        ):
            self._subbranch_group.addButton(button)
        subbranch_layout.addWidget(self._respect_settings, 0, 0)
        subbranch_layout.addWidget(self._ignore_settings, 1, 0)
        subbranch_layout.addWidget(self._conservative_settings, 2, 0)
        subbranch_layout.addWidget(self._liberal_settings, 3, 0)
        self._list_presets_btn = QPushButton("List")
        subbranch_layout.addWidget(self._list_presets_btn, 1, 1)
        outer.addWidget(subbranch_box)

        self._include_non_outstanding = QCheckBox("Include elements that are not outstanding")
        self._modify_item_delay_by_fi = QCheckBox("Modify item delay in proportion to forgetting index")
        self._modify_item_delay_by_fi.setEnabled(False)
        self._modify_item_delay_by_fi.setToolTip("Item forgetting index is not available in Incremento yet.")
        self._modify_topic_delay_by_a_factor = QCheckBox("Modify topic delay in proportion to A-Factor")
        self._modify_delay_by_priority = QCheckBox("Modify delay in proportion to element priority")
        outer.addWidget(self._include_non_outstanding)
        outer.addWidget(self._modify_item_delay_by_fi)
        outer.addWidget(self._modify_topic_delay_by_a_factor)
        outer.addWidget(self._modify_delay_by_priority)

        hint = QLabel(
            "Sub-branch presets are attached to saved branch presets. Use Save on a selected branch to attach settings to that subtree."
        )
        hint.setObjectName("PostponeHint")
        hint.setWordWrap(True)
        outer.addWidget(hint)
        outer.addStretch(1)

        qconnect(self._list_presets_btn.clicked, self._show_subbranch_presets)

    def _refresh_delay_labels(self) -> None:
        self._item_delay_percent.setText(f"{max(0.0, (self._item_delay_factor.value() - 1.0) * 100.0):.0f}%")
        self._topic_delay_percent.setText(f"{max(0.0, (self._topic_delay_factor.value() - 1.0) * 100.0):.0f}%")

    def _refresh_scope_state(self) -> None:
        self._scope_branch.setEnabled(self._branch_root_card_id is not None)
        self._scope_browser.setEnabled(bool(self._browser_card_ids))
        if self._scope_branch.isChecked() and self._branch_root_card_id is None:
            self._scope_all.setChecked(True)
        if self._scope_browser.isChecked() and not self._browser_card_ids:
            self._scope_all.setChecked(True)

        if self._scope_branch.isChecked():
            label = branch_scope_label(
                self._addon_dir,
                self._profile,
                self._branch_root_card_id,
            )
        elif self._scope_browser.isChecked():
            label = self._browser_scope_label()
        else:
            label = "Global"
        self._branch_scope_edit.setText(label)

    def _browser_scope_label(self) -> str:
        if self._browser_scope_name:
            count = len(self._browser_card_ids)
            return f"{self._browser_scope_name} ({count} card{'s' if count != 1 else ''})"
        return browser_scope_label(self._browser_card_ids)

    def _refresh_presets(self) -> None:
        current_name = self._preset_combo.currentText().strip()
        self._presets = load_postpone_presets(self._addon_dir, self._profile)
        self._loading_preset = True
        try:
            self._preset_combo.clear()
            for preset in self._presets:
                self._preset_combo.addItem(str(preset.get("name") or ""))
            if current_name:
                self._preset_combo.setEditText(current_name)
            elif self._presets:
                self._preset_combo.setCurrentIndex(0)
        finally:
            self._loading_preset = False

    def _load_initial_preset(self) -> None:
        preset = None
        if self._branch_root_card_id is not None:
            preset = get_branch_attached_preset(
                self._addon_dir,
                self._profile,
                self._branch_root_card_id,
            )
        if preset is None:
            preset = load_default_postpone_preset(self._addon_dir, self._profile)
        if preset is not None:
            self._preset_combo.setEditText(str(preset.get("name") or ""))
            self._apply_preset_config(preset.get("config") or {})
            self._apply_initial_scope_override()
            return
        self._apply_preset_config(default_postpone_preset(branch_root_card_id=self._branch_root_card_id))
        self._apply_initial_scope_override()

    def _apply_initial_scope_override(self) -> None:
        scope = self._initial_scope
        if scope == SCOPE_SELECTED_BRANCH and self._branch_root_card_id is not None:
            self._scope_branch.setChecked(True)
        elif scope == SCOPE_CURRENT_BROWSER and self._browser_card_ids:
            self._scope_browser.setChecked(True)
        elif scope == SCOPE_ALL_OUTSTANDING:
            self._scope_all.setChecked(True)
        self._refresh_scope_state()

    def _load_selected_preset(self) -> None:
        if self._loading_preset:
            return
        name = self._preset_combo.currentText().strip()
        if not name:
            return
        preset = get_postpone_preset(self._addon_dir, self._profile, name)
        if preset is None:
            return
        self._apply_preset_config(preset.get("config") or {})

    def _apply_preset_config(self, config: dict) -> None:
        normalized = normalize_postpone_preset(
            config,
            branch_root_card_id=self._branch_root_card_id,
        )
        if normalized["scope"] == SCOPE_SELECTED_BRANCH and self._branch_root_card_id is not None:
            self._scope_branch.setChecked(True)
        elif normalized["scope"] == SCOPE_CURRENT_BROWSER and self._browser_card_ids:
            self._scope_browser.setChecked(True)
        else:
            self._scope_all.setChecked(True)

        if normalized["method"] == METHOD_SKIP_TOP:
            self._method_skip_top.setChecked(True)
        else:
            self._method_parameters.setChecked(True)
        self._skip_top_spin.setValue(int(normalized["skip_top_count"]))

        item = normalized["item"]
        topic = normalized["topic"]
        self._item_delay_factor.setValue(float(item["delay_factor"]))
        self._topic_delay_factor.setValue(float(topic["delay_factor"]))
        self._item_max_interval.setValue(int(item["maximum_interval"]))
        self._topic_max_interval.setValue(int(topic["maximum_interval"]))
        self._item_min_interval.setValue(int(item["minimum_interval"]))
        self._topic_min_interval.setValue(int(topic["minimum_interval"]))
        self._item_skip.setChecked(bool(item["skip"]))
        self._topic_skip.setChecked(bool(topic["skip"]))
        self._item_interval_beyond.setValue(int(item["interval_beyond"]))
        self._topic_interval_beyond.setValue(int(topic["interval_beyond"]))
        self._topic_a_factor_below.setValue(float(topic.get("a_factor_below") or 0.0))
        self._item_postpone_count.setValue(int(item["postpone_count"]))
        self._topic_postpone_count.setValue(int(topic["postpone_count"]))
        self._item_priority_threshold.setValue(float(item["priority_threshold"]))
        self._topic_priority_threshold.setValue(float(topic["priority_threshold"]))

        adjust = normalized["adjust"]
        mode = adjust["subbranch_mode"]
        if mode == SUBTREE_MODE_RESPECT:
            self._respect_settings.setChecked(True)
        elif mode == SUBTREE_MODE_CONSERVATIVE:
            self._conservative_settings.setChecked(True)
        elif mode == SUBTREE_MODE_LIBERAL:
            self._liberal_settings.setChecked(True)
        else:
            self._ignore_settings.setChecked(True)
        self._include_non_outstanding.setChecked(bool(adjust["include_non_outstanding"]))
        self._modify_item_delay_by_fi.setChecked(bool(adjust["modify_item_delay_by_fi"]))
        self._modify_topic_delay_by_a_factor.setChecked(bool(adjust["modify_topic_delay_by_a_factor"]))
        self._modify_delay_by_priority.setChecked(bool(adjust["modify_delay_by_priority"]))
        self._refresh_scope_state()
        self._refresh_delay_labels()

    def _current_config(self) -> dict:
        if self._scope_branch.isChecked() and self._branch_root_card_id is not None:
            scope = SCOPE_SELECTED_BRANCH
        elif self._scope_browser.isChecked() and self._browser_card_ids:
            scope = SCOPE_CURRENT_BROWSER
        else:
            scope = SCOPE_ALL_OUTSTANDING

        if self._respect_settings.isChecked():
            subbranch_mode = SUBTREE_MODE_RESPECT
        elif self._conservative_settings.isChecked():
            subbranch_mode = SUBTREE_MODE_CONSERVATIVE
        elif self._liberal_settings.isChecked():
            subbranch_mode = SUBTREE_MODE_LIBERAL
        else:
            subbranch_mode = SUBTREE_MODE_IGNORE

        config = {
            "scope": scope,
            "method": METHOD_SKIP_TOP if self._method_skip_top.isChecked() else METHOD_PARAMETERS,
            "skip_top_count": int(self._skip_top_spin.value()),
            "branch_root_card_id": self._branch_root_card_id,
            "item": {
                "delay_factor": float(self._item_delay_factor.value()),
                "maximum_interval": int(self._item_max_interval.value()),
                "minimum_interval": int(self._item_min_interval.value()),
                "skip": bool(self._item_skip.isChecked()),
                "interval_beyond": int(self._item_interval_beyond.value()),
                "postpone_count": int(self._item_postpone_count.value()),
                "priority_threshold": float(self._item_priority_threshold.value()),
                "forgetting_index_below": None,
            },
            "topic": {
                "delay_factor": float(self._topic_delay_factor.value()),
                "maximum_interval": int(self._topic_max_interval.value()),
                "minimum_interval": int(self._topic_min_interval.value()),
                "skip": bool(self._topic_skip.isChecked()),
                "interval_beyond": int(self._topic_interval_beyond.value()),
                "postpone_count": int(self._topic_postpone_count.value()),
                "priority_threshold": float(self._topic_priority_threshold.value()),
                "a_factor_below": float(self._topic_a_factor_below.value()),
            },
            "adjust": {
                "subbranch_mode": subbranch_mode,
                "include_non_outstanding": bool(self._include_non_outstanding.isChecked()),
                "modify_item_delay_by_fi": bool(self._modify_item_delay_by_fi.isChecked()),
                "modify_topic_delay_by_a_factor": bool(self._modify_topic_delay_by_a_factor.isChecked()),
                "modify_delay_by_priority": bool(self._modify_delay_by_priority.isChecked()),
            },
        }
        return normalize_postpone_preset(
            config,
            branch_root_card_id=self._branch_root_card_id,
        )

    def _restore_defaults(self) -> None:
        self._apply_preset_config(default_postpone_preset(branch_root_card_id=self._branch_root_card_id))

    def _save_current_preset(self) -> None:
        name = self._preset_combo.currentText().strip()
        if not name:
            showInfo("Enter a preset name before saving.")
            return
        scope = self._current_config()["scope"]
        branch_root_card_id = self._branch_root_card_id if scope == SCOPE_SELECTED_BRANCH else None
        save_postpone_preset(
            self._addon_dir,
            self._profile,
            name,
            self._current_config(),
            branch_root_card_id=branch_root_card_id,
            is_default=False,
        )
        self._refresh_presets()
        self._preset_combo.setEditText(name)
        tooltip("Postpone preset saved.")

    def _mark_current_preset_default(self) -> None:
        name = self._preset_combo.currentText().strip()
        if not name:
            showInfo("Choose or save a preset before marking it as default.")
            return
        if get_postpone_preset(self._addon_dir, self._profile, name) is None:
            self._save_current_preset()
        if set_default_postpone_preset(self._addon_dir, self._profile, name):
            self._refresh_presets()
            self._preset_combo.setEditText(name)
            tooltip("Preset set as default.")

    def _delete_selected_preset(self) -> None:
        name = self._preset_combo.currentText().strip()
        if not name:
            return
        if not delete_postpone_preset(self._addon_dir, self._profile, name):
            showInfo("Could not delete that postpone preset.")
            return
        self._refresh_presets()
        self._preset_combo.setEditText("")
        tooltip("Preset deleted.")

    def _show_subbranch_presets(self) -> None:
        if self._branch_root_card_id is None:
            showInfo("Select a knowledge-tree branch before listing sub-branch presets.")
            return
        presets = list_subbranch_presets(
            self._addon_dir,
            self._profile,
            self._branch_root_card_id,
        )
        if not presets:
            showInfo("No saved sub-branch presets were found below this branch.")
            return
        lines = [
            f"{row['branch_title']}  —  {row['preset_name']}"
            for row in presets
        ]
        showInfo("\n".join(lines))

    def _validate_scope(self) -> bool:
        if self._scope_branch.isChecked() and self._branch_root_card_id is None:
            showInfo("Selected branch scope is only available when a knowledge-tree node is selected.")
            return False
        if self._scope_browser.isChecked() and not self._browser_card_ids:
            showInfo(f"{self._scope_browser.text()} scope needs at least one card.")
            return False
        return True

    def _simulate_postpone(self) -> None:
        if not self._validate_scope():
            return
        try:
            summary = simulate_postpone_plan(
                self._addon_dir,
                self._profile,
                self._current_config(),
                branch_root_card_id=self._branch_root_card_id if self._scope_branch.isChecked() else None,
                browser_card_ids=self._browser_card_ids if self._scope_browser.isChecked() else None,
            )
        except Exception as exc:
            showInfo(f"Could not simulate branch postponing:\n{exc}")
            return
        self._last_simulation = summary
        _SimulationDialog(format_simulation_summary(summary), parent=self).exec()

    def _apply_postpone(self) -> None:
        if not self._validate_scope():
            return
        try:
            summary = apply_postpone_plan(
                self._addon_dir,
                self._profile,
                self._current_config(),
                branch_root_card_id=self._branch_root_card_id if self._scope_branch.isChecked() else None,
                browser_card_ids=self._browser_card_ids if self._scope_browser.isChecked() else None,
            )
        except Exception as exc:
            showInfo(f"Could not postpone the selected cards:\n{exc}")
            return
        count = int(summary.get("applied_count") or 0)
        if count <= 0:
            showInfo("No cards qualified for postponing with the current settings.")
            return
        tooltip(f"Postponed {count} card{'s' if count != 1 else ''}.")
        self.accept()

    def _show_help(self) -> None:
        showInfo(
            "Postpone outstanding elements delays cards by adding extra interval days.\n\n"
            "Delay factor controls the extra postponement percentage.\n"
            "Scope chooses whether to operate on all outstanding cards, the selected branch, or the current Browser.\n"
            "Simulate previews how many cards would be postponed before anything is changed."
        )
