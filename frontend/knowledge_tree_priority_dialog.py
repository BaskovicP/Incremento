from __future__ import annotations

from aqt.qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    qconnect,
)
from aqt.utils import showInfo


OP_SET_SELECTED = "set_selected"
OP_SHIFT_SUBTREE = "shift_subtree"
OP_LINEAR_SPREAD = "linear_spread"
OP_RANDOMIZE = "randomize_subtree"
OP_FOCUS_BRANCH = "focus_branch"
OP_FADE_CHILDREN = "fade_children"


def _priority_spin(*, minimum: float = 0.0, maximum: float = 100.0) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setDecimals(4)
    spin.setSingleStep(0.1)
    spin.setFixedWidth(120)
    return spin


class KnowledgeTreePriorityDialog(QDialog):
    def __init__(
        self,
        *,
        card_label: str,
        current_priority: float,
        subtree_stats: dict,
        current_a_factor: float | None = None,
        current_interval: int | None = None,
        lower_is_more_important: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self._subtree_stats = subtree_stats or {}
        self._lower_is_more_important = bool(lower_is_more_important)

        self.setWindowTitle("Knowledge-tree Priority")
        self.setMinimumWidth(520)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        title_label = QLabel(card_label or "Selected knowledge-tree node")
        title_label.setWordWrap(True)
        root.addWidget(title_label)

        important_end = "0" if self._lower_is_more_important else "100"
        stats = QLabel(
            "Subtree: "
            f"{int(self._subtree_stats.get('total_count') or 0)} card(s) total"
            f"  ·  {int(self._subtree_stats.get('descendant_count') or 0)} descendants"
            f"  ·  {int(self._subtree_stats.get('direct_child_count') or 0)} direct children"
            f"  ·  max depth {int(self._subtree_stats.get('max_depth') or 0)}"
            f"  ·  important end {important_end}"
        )
        stats.setWordWrap(True)
        stats.setStyleSheet("color:#666;font-size:11px;")
        root.addWidget(stats)

        min_priority = self._subtree_stats.get("min_priority")
        max_priority = self._subtree_stats.get("max_priority")
        if min_priority is not None and max_priority is not None:
            range_label = QLabel(
                f"Current subtree priority range: {float(min_priority):.1f} to {float(max_priority):.1f}"
            )
            range_label.setWordWrap(True)
            range_label.setStyleSheet("color:#666;font-size:11px;")
            root.addWidget(range_label)

        operation_row = QHBoxLayout()
        operation_row.addWidget(QLabel("Operation:"))
        self._operation_combo = QComboBox()
        self._operation_combo.addItem("Set Selected Node", OP_SET_SELECTED)
        self._operation_combo.addItem("Shift Whole Subtree", OP_SHIFT_SUBTREE)
        self._operation_combo.addItem("Linear Spread By Depth", OP_LINEAR_SPREAD)
        self._operation_combo.addItem("Randomize Subtree", OP_RANDOMIZE)
        self._operation_combo.addItem("Focus This Branch", OP_FOCUS_BRANCH)
        self._operation_combo.addItem("Fade Children", OP_FADE_CHILDREN)
        operation_row.addWidget(self._operation_combo, 1)
        root.addLayout(operation_row)

        self._operation_hint = QLabel("")
        self._operation_hint.setWordWrap(True)
        self._operation_hint.setStyleSheet("color:#666;font-size:11px;")
        root.addWidget(self._operation_hint)

        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        self._selected_priority_spin = _priority_spin()
        self._selected_priority_spin.setValue(float(current_priority))

        selected_page = QWidget()
        selected_form = QFormLayout(selected_page)
        selected_form.setSpacing(8)
        selected_form.addRow("Priority:", self._selected_priority_spin)
        self._selected_a_factor_spin: QDoubleSpinBox | None = None
        if current_a_factor is not None:
            self._selected_a_factor_spin = QDoubleSpinBox()
            self._selected_a_factor_spin.setRange(1.1, 100.0)
            self._selected_a_factor_spin.setDecimals(3)
            self._selected_a_factor_spin.setSingleStep(0.1)
            self._selected_a_factor_spin.setFixedWidth(120)
            self._selected_a_factor_spin.setValue(float(current_a_factor))
            selected_form.addRow("A-Factor:", self._selected_a_factor_spin)
            if current_interval is not None:
                selected_form.addRow("Last interval:", QLabel(f"{int(current_interval)} d"))
        self._stack.addWidget(selected_page)

        shift_page = QWidget()
        shift_form = QFormLayout(shift_page)
        shift_form.setSpacing(8)
        self._shift_delta_spin = _priority_spin(minimum=-100.0, maximum=100.0)
        self._shift_delta_spin.setValue(0.0)
        shift_form.addRow("Delta:", self._shift_delta_spin)
        self._stack.addWidget(shift_page)

        spread_page = QWidget()
        spread_form = QFormLayout(spread_page)
        spread_form.setSpacing(8)
        self._spread_start_spin = _priority_spin()
        self._spread_start_spin.setValue(float(current_priority))
        self._spread_end_spin = _priority_spin()
        self._spread_end_spin.setValue(float(current_priority))
        self._spread_include_root = QCheckBox("Include selected node in spread")
        self._spread_include_root.setChecked(False)
        spread_form.addRow("Start priority:", self._spread_start_spin)
        spread_form.addRow("End priority:", self._spread_end_spin)
        spread_form.addRow("", self._spread_include_root)
        self._stack.addWidget(spread_page)

        randomize_page = QWidget()
        randomize_form = QFormLayout(randomize_page)
        randomize_form.setSpacing(8)
        self._randomize_min_spin = _priority_spin()
        self._randomize_min_spin.setValue(max(0.0, float(current_priority) - 10.0))
        self._randomize_max_spin = _priority_spin()
        self._randomize_max_spin.setValue(min(100.0, float(current_priority) + 10.0))
        self._randomize_include_root = QCheckBox("Include selected node in randomization")
        self._randomize_include_root.setChecked(True)
        randomize_form.addRow("Minimum:", self._randomize_min_spin)
        randomize_form.addRow("Maximum:", self._randomize_max_spin)
        randomize_form.addRow("", self._randomize_include_root)
        self._stack.addWidget(randomize_page)

        focus_page = QWidget()
        focus_layout = QVBoxLayout(focus_page)
        focus_layout.setContentsMargins(0, 0, 0, 0)
        focus_layout.addWidget(
            QLabel(
                "Moves the selected node and its descendants toward the important end,"
                " with the selected node shifting the most."
            )
        )
        focus_layout.addStretch(1)
        self._stack.addWidget(focus_page)

        fade_page = QWidget()
        fade_layout = QVBoxLayout(fade_page)
        fade_layout.setContentsMargins(0, 0, 0, 0)
        fade_layout.addWidget(
            QLabel(
                "Keeps the selected node anchored and progressively makes descendants"
                " less important by depth."
            )
        )
        fade_layout.addStretch(1)
        self._stack.addWidget(fade_page)

        self._preview_label = QLabel("")
        self._preview_label.setWordWrap(True)
        self._preview_label.setStyleSheet("color:#666;font-size:11px;")
        root.addWidget(self._preview_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        apply_btn = QPushButton("Apply")
        apply_btn.setDefault(True)
        cancel_btn = QPushButton("Cancel")
        button_row.addWidget(apply_btn)
        button_row.addWidget(cancel_btn)
        root.addLayout(button_row)

        qconnect(apply_btn.clicked, self.accept)
        qconnect(cancel_btn.clicked, self.reject)
        qconnect(self._operation_combo.currentIndexChanged, self._refresh_ui)
        qconnect(self._spread_include_root.stateChanged, lambda _state: self._refresh_preview())
        qconnect(self._randomize_include_root.stateChanged, lambda _state: self._refresh_preview())

        self._refresh_ui()

    def _refresh_ui(self, *_args) -> None:
        index = self._operation_combo.currentIndex()
        self._stack.setCurrentIndex(index)
        hints = {
            OP_SET_SELECTED: "Update only the selected node. Topic nodes can also change A-Factor here.",
            OP_SHIFT_SUBTREE: "Apply the same signed delta to the selected node and every descendant.",
            OP_LINEAR_SPREAD: "Redistribute priorities by tree depth from the start value to the end value.",
            OP_RANDOMIZE: "Assign random priorities within the chosen range.",
            OP_FOCUS_BRANCH: "Bias the whole branch toward the important end so this branch is studied more.",
            OP_FADE_CHILDREN: "Reduce child urgency while leaving the selected node fixed.",
        }
        self._operation_hint.setText(hints.get(self.operation, ""))
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        total_count = int(self._subtree_stats.get("total_count") or 0)
        descendant_count = int(self._subtree_stats.get("descendant_count") or 0)
        if self.operation == OP_SET_SELECTED:
            affected_count = 1
        elif self.operation == OP_SHIFT_SUBTREE:
            affected_count = total_count
        elif self.operation == OP_LINEAR_SPREAD:
            affected_count = total_count if self._spread_include_root.isChecked() else descendant_count
        elif self.operation == OP_RANDOMIZE:
            affected_count = total_count if self._randomize_include_root.isChecked() else descendant_count
        elif self.operation == OP_FOCUS_BRANCH:
            affected_count = total_count
        else:
            affected_count = descendant_count

        self._preview_label.setText(
            f"This will affect {affected_count} card{'s' if affected_count != 1 else ''}."
        )

    def accept(self) -> None:
        descendant_count = int(self._subtree_stats.get("descendant_count") or 0)
        if self.operation == OP_LINEAR_SPREAD and not self._spread_include_root.isChecked() and descendant_count <= 0:
            showInfo("This node has no children to spread priorities across.")
            return
        if self.operation == OP_FADE_CHILDREN and descendant_count <= 0:
            showInfo("This node has no child priorities to fade.")
            return
        if self.operation == OP_RANDOMIZE and not self._randomize_include_root.isChecked() and descendant_count <= 0:
            showInfo("This node has no children to randomize.")
            return
        super().accept()

    @property
    def operation(self) -> str:
        return str(self._operation_combo.currentData() or OP_SET_SELECTED)

    @property
    def selected_priority(self) -> float:
        return round(float(self._selected_priority_spin.value()), 4)

    @property
    def selected_a_factor(self) -> float | None:
        if self._selected_a_factor_spin is None:
            return None
        return round(float(self._selected_a_factor_spin.value()), 3)

    @property
    def operation_payload(self) -> dict:
        if self.operation == OP_SET_SELECTED:
            return {
                "priority": self.selected_priority,
                "a_factor": self.selected_a_factor,
            }
        if self.operation == OP_SHIFT_SUBTREE:
            return {"delta": round(float(self._shift_delta_spin.value()), 4)}
        if self.operation == OP_LINEAR_SPREAD:
            return {
                "start_priority": round(float(self._spread_start_spin.value()), 4),
                "end_priority": round(float(self._spread_end_spin.value()), 4),
                "include_root": bool(self._spread_include_root.isChecked()),
            }
        if self.operation == OP_RANDOMIZE:
            return {
                "minimum_priority": round(float(self._randomize_min_spin.value()), 4),
                "maximum_priority": round(float(self._randomize_max_spin.value()), 4),
                "include_root": bool(self._randomize_include_root.isChecked()),
            }
        return {}
