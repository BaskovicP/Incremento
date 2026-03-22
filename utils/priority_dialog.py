from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QDoubleSpinBox,
    QPushButton, QWidget, Qt,
)
from PyQt6.QtGui import QPainter, QLinearGradient, QColor

# ── Non-linear mapping ────────────────────────────────────────────────────────
# Slider range 0–10000.  First half (0–5000) maps to priority 0–30 (fine-grained).
# Second half (5000–10000) maps to priority 30–100.
# Lower priority value = more important.

SLIDER_MAX   = 10_000
SLIDER_HALF  = 5_000
PRIORITY_MID = 30.0


def _slider_to_priority(s: int) -> float:
    if s <= SLIDER_HALF:
        return round(s * PRIORITY_MID / SLIDER_HALF, 4)
    else:
        return round(PRIORITY_MID + (s - SLIDER_HALF) * (100.0 - PRIORITY_MID) / SLIDER_HALF, 4)


def _priority_to_slider(p: float) -> int:
    if p <= PRIORITY_MID:
        return round(p * SLIDER_HALF / PRIORITY_MID)
    else:
        return round(SLIDER_HALF + (p - PRIORITY_MID) * SLIDER_HALF / (100.0 - PRIORITY_MID))


# ── Gradient bar widget ───────────────────────────────────────────────────────

class _GradientBar(QWidget):
    """Horizontal rainbow bar: red (0, most important) → violet (100, least)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(14)
        self._marker = 0.0  # 0.0–1.0 position

    def set_fraction(self, f: float):
        self._marker = max(0.0, min(1.0, f))
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        # Rainbow gradient: red → orange → yellow → green → cyan → blue → violet
        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0.00, QColor("#ff0000"))
        grad.setColorAt(0.17, QColor("#ff8800"))
        grad.setColorAt(0.33, QColor("#ffff00"))
        grad.setColorAt(0.50, QColor("#00cc00"))
        grad.setColorAt(0.67, QColor("#00cccc"))
        grad.setColorAt(0.83, QColor("#0000ff"))
        grad.setColorAt(1.00, QColor("#8800cc"))

        from PyQt6.QtGui import QBrush
        p.fillRect(0, 0, w, h, QBrush(grad))

        # Marker triangle
        mx = int(self._marker * w)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("white"))
        from PyQt6.QtGui import QPolygon
        from PyQt6.QtCore import QPoint
        p.drawPolygon(QPolygon([
            QPoint(mx,     0),
            QPoint(mx - 5, h),
            QPoint(mx + 5, h),
        ]))


# ── Dialog ────────────────────────────────────────────────────────────────────

class PriorityDialog(QDialog):
    """Show a non-linear priority slider for a single card.

    Args:
        current_priority: existing value (0.0–100.0, default 50.0)
        card_label: short description shown in the title bar
    """

    def __init__(self, current_priority: float = 50.0,
                 card_label: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Priority")
        self.setMinimumWidth(360)

        self._building = False  # guard against recursive signal loops

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Info label
        if card_label:
            lbl = QLabel(card_label)
            lbl.setWordWrap(True)
            layout.addWidget(lbl)

        # Hint
        hint = QLabel(
            "<small><i>0 = highest importance &nbsp;·&nbsp; "
            "50 = default &nbsp;·&nbsp; 100 = lowest importance<br>"
            "First half of slider (0–30) gives finer control over important cards.</i></small>"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Gradient bar
        self._bar = _GradientBar()
        layout.addWidget(self._bar)

        # Slider
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, SLIDER_MAX)
        self._slider.setTickInterval(SLIDER_MAX // 10)
        self._slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        layout.addWidget(self._slider)

        # Scale labels
        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("0"))
        scale_row.addStretch()
        scale_row.addWidget(QLabel("30"))
        scale_row.addStretch()
        scale_row.addWidget(QLabel("100"))
        layout.addLayout(scale_row)

        # Spinbox
        spin_row = QHBoxLayout()
        spin_row.addWidget(QLabel("Priority value:"))
        self._spin = QDoubleSpinBox()
        self._spin.setRange(0.0, 100.0)
        self._spin.setDecimals(4)
        self._spin.setSingleStep(0.1)
        self._spin.setFixedWidth(110)
        spin_row.addWidget(self._spin)
        spin_row.addStretch()
        layout.addLayout(spin_row)

        # OK / Cancel
        btn_row = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        cancel_btn = QPushButton("Cancel")
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

        # Wire slider ↔ spinbox
        self._slider.valueChanged.connect(self._on_slider_changed)
        self._spin.valueChanged.connect(self._on_spin_changed)

        # Initialise to current priority
        self._set_priority(current_priority)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_priority(self, p: float):
        """Set both widgets to the given priority (0–100) without recursion."""
        self._building = True
        s = _priority_to_slider(p)
        self._spin.setValue(p)
        self._slider.setValue(s)
        self._bar.set_fraction(s / SLIDER_MAX)
        self._building = False

    def _on_slider_changed(self, s: int):
        if self._building:
            return
        p = _slider_to_priority(s)
        self._building = True
        self._spin.setValue(p)
        self._bar.set_fraction(s / SLIDER_MAX)
        self._building = False

    def _on_spin_changed(self, p: float):
        if self._building:
            return
        s = _priority_to_slider(p)
        self._building = True
        self._slider.setValue(s)
        self._bar.set_fraction(s / SLIDER_MAX)
        self._building = False

    # ── Public ────────────────────────────────────────────────────────────────

    @property
    def priority(self) -> float:
        """The selected priority value (0.0–100.0, 4 decimal places)."""
        return round(self._spin.value(), 4)
