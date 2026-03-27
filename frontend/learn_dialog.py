import json
import os

from aqt import mw
from aqt.qt import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QCheckBox, QComboBox, QPushButton, QWidget, Qt, qconnect,
    QTimeEdit, QTime, QSpinBox, QLineEdit, QMessageBox, QFileDialog, QFrame,
    QInputDialog, QScrollArea, QObject, QEvent, QGraphicsOpacityEffect,
)
from aqt.utils import showInfo, tooltip

try:
    from ..backend.scheduler_config import SchedulerConfig, NO_TAGS_KEY
    from ..backend.statistics import load_stats, delete_daily_stats, delete_lifetime_stats, delete_all_stats
except ImportError:
    from scheduler_config import SchedulerConfig, NO_TAGS_KEY
    from statistics import load_stats, delete_daily_stats, delete_lifetime_stats, delete_all_stats

# Addon root: one level above this file (utils/)
_ADDON_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def _info_icon(tip: str) -> QLabel:
    """Filled blue circle with white 'i'; hover to read the explanation."""
    lbl = QLabel("i")
    lbl.setToolTip(tip)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setFixedSize(15, 15)
    lbl.setStyleSheet(
        "QLabel {"
        "  color: white;"
        "  background-color: #4a7ab5;"
        "  border-radius: 7px;"
        "  font-size: 9px;"
        "  font-style: italic;"
        "  font-weight: bold;"
        "  padding-bottom: 1px;"
        "}"
        "QLabel:hover { background-color: #3060a0; }"
    )
    return lbl


# ─── Phase funnel ─────────────────────────────────────────────────────────────

_PHASE_META = {
    "content_types": {
        "label": "Content Types",
        "icon":  "📄",
        "color": "#e07b39",
        "desc":  "Fill PDF / YouTube / Webpage quotas",
    },
    "tags": {
        "label": "Tag Quotas",
        "icon":  "🏷",
        "color": "#8e44ad",
        "desc":  "Fill per-tag quotas (e.g. statistics, psychology …)",
    },
    "type": {
        "label": "Card Type",
        "icon":  "📊",
        "color": "#2980b9",
        "desc":  "Topics ↔ Items ratio enforcement",
    },
    "mode": {
        "label": "Selection Mode",
        "icon":  "🎲",
        "color": "#27ae60",
        "desc":  "Priority-first ↔ Random enforcement",
    },
}

_DEFAULT_PHASE_ORDER = ["content_types", "tags", "type", "mode"]


class _PhaseCard(QFrame):
    """Single draggable phase card."""

    def __init__(self, phase_id: str, enabled: bool = True, parent=None):
        super().__init__(parent)
        self.phase_id = phase_id
        self._color = _PHASE_META[phase_id]["color"]
        self.setObjectName("PhaseCard")
        self._apply_style(dragging=False)
        self.setFixedHeight(62)

        row = QHBoxLayout(self)
        row.setContentsMargins(6, 4, 8, 4)
        row.setSpacing(6)

        self._handle = QLabel("⠿")
        self._handle.setFixedSize(20, 42)
        self._handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._handle.setStyleSheet(
            "color: rgba(128,128,128,0.55); font-size: 18px; border: none;"
        )
        self._handle.setCursor(Qt.CursorShape.OpenHandCursor)
        row.addWidget(self._handle)

        icon_lbl = QLabel(_PHASE_META[phase_id]["icon"])
        icon_lbl.setFixedWidth(22)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("border: none; font-size: 15px;")
        row.addWidget(icon_lbl)

        text_w = QWidget()
        text_w.setStyleSheet("border: none;")
        text_col = QVBoxLayout(text_w)
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        title = QLabel(_PHASE_META[phase_id]["label"])
        title.setStyleSheet("font-weight: bold; font-size: 12px;")
        desc = QLabel(_PHASE_META[phase_id]["desc"])
        desc.setStyleSheet("color: palette(mid); font-size: 11px;")
        text_col.addWidget(title)
        text_col.addWidget(desc)
        row.addWidget(text_w, 1)

        self._cb = QCheckBox()
        self._cb.setChecked(enabled)
        self._cb.setToolTip(
            "Enable this phase in strict mode.\n"
            "Soft mode uses all dimensions simultaneously regardless of this toggle."
        )
        self._cb.setStyleSheet("border: none;")
        row.addWidget(self._cb)

    @property
    def is_enabled(self) -> bool:
        return self._cb.isChecked()

    def set_enabled(self, v: bool) -> None:
        self._cb.setChecked(v)

    def _apply_style(self, dragging: bool) -> None:
        s = "dashed" if dragging else "solid"
        alpha = "0.2" if dragging else "0.35"
        self.setStyleSheet(
            f"QFrame#PhaseCard {{"
            f"  background: palette(base);"
            f"  border: 1px {s} rgba(128,128,128,{alpha});"
            f"  border-left: 5px {s} {self._color};"
            f"  border-radius: 6px;"
            f"}}"
        )


class _HandleEventFilter(QObject):
    """Routes mouse events on drag handles to the parent _FunnelWidget."""

    def __init__(self, funnel: "FunnelWidget"):
        super().__init__(funnel)
        self._f = funnel

    def eventFilter(self, obj, event):
        if not self._f.isEnabled():
            return False
        card = self._f._handle_map.get(id(obj))
        if card is None:
            return False
        t = event.type()
        if t == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._f._on_press(card, event)
            return True
        if t == QEvent.Type.MouseMove:
            self._f._on_move(card, event)
            return True
        if t == QEvent.Type.MouseButtonRelease:
            self._f._on_release(card, event)
            return True
        return False


class FunnelWidget(QWidget):
    """Drag-and-drop scheduling phase funnel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: list[_PhaseCard] = []
        self._handle_map: dict[int, _PhaseCard] = {}
        self._ev = _HandleEventFilter(self)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._container = QWidget(self)
        self._cl = QVBoxLayout(self._container)
        self._cl.setContentsMargins(2, 2, 2, 2)
        self._cl.setSpacing(0)
        outer.addWidget(self._container)

        # Drop-indicator: absolutely positioned inside _container
        self._ind = QFrame(self._container)
        self._ind.setFixedHeight(3)
        self._ind.setStyleSheet("background: #4a7ab5; border: none;")
        self._ind.hide()

        # Fixed "Fill Remaining" footer
        fill = QFrame()
        fill.setObjectName("FillFooter")
        fill.setStyleSheet(
            "QFrame#FillFooter {"
            "  background: palette(base);"
            "  border: 1px solid rgba(128,128,128,0.25);"
            "  border-left: 5px solid #7f8c8d;"
            "  border-radius: 6px;"
            "}"
        )
        fill.setFixedHeight(52)
        fill_row = QHBoxLayout(fill)
        fill_row.setContentsMargins(32, 4, 8, 4)
        fill_row.setSpacing(6)
        fi = QLabel("🔚")
        fi.setFixedWidth(22)
        fi.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fi.setStyleSheet("border: none; font-size: 15px;")
        fill_row.addWidget(fi)
        fw = QWidget()
        fw.setStyleSheet("border: none;")
        fc = QVBoxLayout(fw)
        fc.setContentsMargins(0, 0, 0, 0)
        fc.setSpacing(2)
        ft = QLabel("Fill Remaining")
        ft.setStyleSheet("font-weight: bold; font-size: 12px;")
        fd = QLabel("Any ready cards — always runs last")
        fd.setStyleSheet("color: palette(mid); font-size: 11px;")
        fc.addWidget(ft)
        fc.addWidget(fd)
        fill_row.addWidget(fw, 1)

        arr = QLabel("▼")
        arr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arr.setStyleSheet("color: rgba(128,128,128,0.45); font-size: 10px;")
        arr.setFixedHeight(16)
        outer.addWidget(arr)
        outer.addWidget(fill)

        # Drag state
        self._drag_card: _PhaseCard | None = None
        self._drag_start_y: int = 0
        self._drag_active: bool = False
        self._insert_before: int = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def add_phase(self, phase_id: str, enabled: bool = True) -> _PhaseCard:
        card = _PhaseCard(phase_id, enabled, self._container)
        self._handle_map[id(card._handle)] = card
        card._handle.installEventFilter(self._ev)
        self._cards.append(card)
        self._rebuild()
        return card

    def set_order(self, order: list[str], enabled: dict | None = None) -> None:
        id_map = {c.phase_id: c for c in self._cards}
        new = [id_map[pid] for pid in order if pid in id_map]
        for c in self._cards:
            if c not in new:
                new.append(c)
        self._cards = new
        if enabled:
            for c in self._cards:
                c.set_enabled(enabled.get(c.phase_id, True))
        self._rebuild()

    def get_order(self) -> list[str]:
        return [c.phase_id for c in self._cards]

    def get_enabled(self) -> dict[str, bool]:
        return {c.phase_id: c.is_enabled for c in self._cards}

    # ── Layout ────────────────────────────────────────────────────────────────

    def _rebuild(self) -> None:
        while self._cl.count():
            item = self._cl.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
        for i, card in enumerate(self._cards):
            if i > 0:
                a = QLabel("▼")
                a.setAlignment(Qt.AlignmentFlag.AlignCenter)
                a.setStyleSheet(
                    "color: rgba(128,128,128,0.45); font-size: 10px; padding: 0;"
                )
                a.setFixedHeight(16)
                self._cl.addWidget(a)
            card.setParent(self._container)
            self._cl.addWidget(card)
            card.show()

    # ── Drag ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _gpt(event):
        try:
            return event.globalPosition().toPoint()
        except AttributeError:
            return event.globalPos()

    def _cy(self, event) -> int:
        return self._container.mapFromGlobal(self._gpt(event)).y()

    def _midpoints(self) -> list[int]:
        return [c.pos().y() + c.height() // 2 for c in self._cards]

    def _ind_y(self, before: int) -> int:
        if not self._cards:
            return 2
        if before <= 0:
            return max(0, self._cards[0].pos().y() - 3)
        if before >= len(self._cards):
            c = self._cards[-1]
            return c.pos().y() + c.height() + 4
        return self._cards[before].pos().y() - 4

    def _on_press(self, card: _PhaseCard, event) -> None:
        self._drag_card = card
        self._drag_start_y = self._cy(event)
        self._drag_active = False

    def _on_move(self, card: _PhaseCard, event) -> None:
        if self._drag_card is not card:
            return
        cy = self._cy(event)
        if not self._drag_active and abs(cy - self._drag_start_y) > 6:
            self._drag_active = True
            card._apply_style(dragging=True)

        if self._drag_active:
            drag_idx = self._cards.index(card)
            insert = len(self._cards)
            for i, mid in enumerate(self._midpoints()):
                if cy < mid:
                    insert = i
                    break
            self._insert_before = insert
            if insert in (drag_idx, drag_idx + 1):
                self._ind.hide()
            else:
                self._ind.setGeometry(0, self._ind_y(insert), self._container.width(), 3)
                self._ind.raise_()
                self._ind.show()

    def _on_release(self, card: _PhaseCard, event) -> None:
        if self._drag_active and self._drag_card is card:
            drag_idx = self._cards.index(card)
            insert = self._insert_before
            if insert not in (drag_idx, drag_idx + 1):
                self._cards.pop(drag_idx)
                adj = insert - 1 if insert > drag_idx else insert
                self._cards.insert(adj, card)
                self._rebuild()
            card._apply_style(dragging=False)
            self._ind.hide()
        self._drag_card = None
        self._drag_active = False


# ─── End funnel ───────────────────────────────────────────────────────────────

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
        self._profiles: dict[str, dict] = config.get("profiles", {})
        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 8)
        main_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        main_layout.addWidget(scroll)

        _scroll_content = QWidget()
        scroll.setWidget(_scroll_content)
        layout = QVBoxLayout(_scroll_content)
        layout.setContentsMargins(12, 12, 12, 12)

        intro = QLabel(
            "Configure how Incremento selects cards for each study session."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: gray;")
        layout.addWidget(intro)

        # -- Profiles --
        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Profile:"))
        self._profile_combo = QComboBox()
        self._profile_combo.setMinimumWidth(160)
        self._profile_combo.setToolTip("Saved presets — pick one and click Load")
        profile_row.addWidget(self._profile_combo)

        self._profile_load_btn = QPushButton("Load")
        self._profile_load_btn.setFixedWidth(52)
        self._profile_load_btn.setToolTip("Apply the selected profile to all settings below")
        qconnect(self._profile_load_btn.clicked, self._load_profile)
        profile_row.addWidget(self._profile_load_btn)

        save_as_btn = QPushButton("Save As…")
        save_as_btn.setFixedWidth(72)
        save_as_btn.setToolTip("Save the current settings as a named profile")
        qconnect(save_as_btn.clicked, self._save_profile_as)
        profile_row.addWidget(save_as_btn)

        self._profile_delete_btn = QPushButton("Delete")
        self._profile_delete_btn.setFixedWidth(58)
        self._profile_delete_btn.setToolTip("Delete the selected profile")
        self._profile_delete_btn.setStyleSheet("color: #e05050;")
        qconnect(self._profile_delete_btn.clicked, self._delete_profile)
        profile_row.addWidget(self._profile_delete_btn)

        profile_row.addStretch()
        layout.addLayout(profile_row)
        self._refresh_profile_combo()

        _profile_sep = QFrame()
        _profile_sep.setFrameShape(QFrame.Shape.HLine)
        _profile_sep.setStyleSheet("QFrame { color: rgba(128,128,128,0.35); }")
        layout.addWidget(_profile_sep)

        # ── 1. Session size ───────────────────────────────────────────────────
        count_row = QHBoxLayout()
        count_row.addWidget(QLabel("Cards per session:"))
        self._count_spin = QSpinBox()
        self._count_spin.setRange(1, 500)
        self._count_spin.setValue(self._saved.get("session_card_count", 50))
        count_row.addWidget(self._count_spin)
        count_row.addWidget(_info_icon(
            "Total cards Incremento schedules for this session.\n\n"
            "Example: 50 → exactly 50 cards in the filtered deck.\n"
            "All other settings (quotas, rates, priorities) are percentages of this number."
        ))
        count_row.addStretch()
        layout.addLayout(count_row)

        # ── 2. Card type filter ───────────────────────────────────────────────
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
        card_types_row.addWidget(_info_icon(
            "Which Anki scheduling states are included in the session pool.\n\n"
            "• New — cards you've never studied before\n"
            "• Learning — cards currently in learning / relearning steps\n"
            "• Due / Review — mature cards scheduled for today\n\n"
            "Note: PDF, YouTube and Webpage cards are always eligible regardless\n"
            "of these checkboxes — they bypass Anki's scheduling state."
        ))
        card_types_row.addStretch()
        layout.addLayout(card_types_row)

        # ── 3. Topics / Items ratio ───────────────────────────────────────────
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
        topics_row.addWidget(self._topics_slider)
        _lbl_items = QLabel("Items")
        _lbl_items.setToolTip("Fact cards — Q&A flashcards, vocabulary, quick-recall items")
        topics_row.addWidget(_lbl_items)
        self._topics_right_lbl = QLabel(f"{topics_val}%")
        self._topics_right_lbl.setFixedWidth(36)
        topics_row.addWidget(self._topics_right_lbl)
        topics_row.addWidget(_info_icon(
            "Ratio of topic cards (concepts, long reads) vs item cards (flashcards, Q&A).\n\n"
            "Example: 90 % Topics with 50 cards → ~45 topic cards and ~5 item cards.\n\n"
            "Topics filter and Items filter (Advanced section) determine which cards\n"
            "belong to each group."
        ))
        layout.addLayout(topics_row)

        self._counts_lbl = QLabel("")
        layout.addWidget(self._counts_lbl)

        # ── 5. PDF soft-mix rate ──────────────────────────────────────────────
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
        pdf_row.addWidget(self._pdf_slider)
        _lbl_other = QLabel("Other")
        _lbl_other.setToolTip("All non-PDF cards (topics and items)")
        pdf_row.addWidget(_lbl_other)
        self._pdf_right_lbl = QLabel(f"{pdf_val}%")
        self._pdf_right_lbl.setFixedWidth(36)
        pdf_row.addWidget(self._pdf_right_lbl)
        pdf_row.addWidget(_info_icon(
            "Soft PDF mix rate — how often a PDF card is picked during normal scheduling.\n\n"
            "Unlike Content type priorities (which fill a hard quota first), this is a\n"
            "stochastic target: PDF cards are woven throughout the session.\n\n"
            "Example: PDF = 20 % → roughly 1 in 5 picks targets a PDF card.\n"
            "Set to 0 % (slider fully right) to exclude PDFs from soft mixing.\n\n"
            "You can use both: priority fills a hard quota first, then soft mixing\n"
            "adds more PDFs in the remaining slots."
        ))
        layout.addLayout(pdf_row)

        qconnect(self._pdf_slider.valueChanged,
                 lambda v: (self._pdf_left_lbl.setText(f"{100 - v}%"),
                             self._pdf_right_lbl.setText(f"{v}%")))

        # ── 6. Priority / Random selection mode ───────────────────────────────
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
        random_row.addWidget(self._random_slider)
        _lbl_random = QLabel("Random")
        _lbl_random.setToolTip("Pick cards at random from the eligible pool")
        random_row.addWidget(_lbl_random)
        self._random_right_lbl = QLabel(f"{random_val}%")
        self._random_right_lbl.setFixedWidth(36)
        random_row.addWidget(self._random_right_lbl)
        random_row.addWidget(_info_icon(
            "How cards are selected from the eligible pool at each pick.\n\n"
            "• Priority (left) — picks the most overdue card first (sorted by due date).\n"
            "  Use this to work through your backlog in order.\n"
            "• Random (right) — picks any eligible card at random.\n"
            "  Use this for a varied, low-stakes session.\n\n"
            "Example: 99 % Random → almost always picks randomly;\n"
            "1 % Priority → the most overdue card occasionally sneaks in."
        ))
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

        # ── 7. Scheduler scope ────────────────────────────────────────────────
        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel("Scheduler scope:"))
        self._scope_combo = QComboBox()
        self._scope_combo.addItem("This session",  "session")
        self._scope_combo.addItem("Today",          "daily")
        self._scope_combo.addItem("All time",       "lifetime")
        saved_scope = self._saved.get("scheduler_scope", "session")
        for i in range(self._scope_combo.count()):
            if self._scope_combo.itemData(i) == saved_scope:
                self._scope_combo.setCurrentIndex(i)
                break
        scope_row.addWidget(self._scope_combo)
        scope_row.addWidget(_info_icon(
            "How far back the scheduler looks when balancing card types and tags.\n\n"
            "• This session — debt resets each time you open this dialog.\n"
            "  Best for: fresh start every day.\n"
            "• Today — debt accumulates across multiple same-day sessions.\n"
            "  Best for: studying in several short bursts during the day.\n"
            "• All time — balances over your entire study history.\n"
            "  Best for: strict long-term ratio enforcement.\n\n"
            "Example (Today scope, 90 % Topics target): if your morning session\n"
            "was all topics, the afternoon session will lean toward items to compensate."
        ))

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

        # ── 8. Tag quotas ─────────────────────────────────────────────────────
        _tag_hrow = QHBoxLayout()
        _tag_header = QLabel("Tag quotas")
        _tag_header.setStyleSheet("font-weight: bold;")
        _tag_hrow.addWidget(_tag_header)
        _tag_hrow.addWidget(_info_icon(
            "Each slider sets the probability that any given card pick will target this tag.\n\n"
            "• Soft mode (strict enforcement off):\n"
            "  The % is a running target — the scheduler picks from this tag more often\n"
            "  when it's under-represented, less often when it's over-represented.\n"
            "  Example: physics = 20 % → roughly 1 in 5 picks tries to find a physics card.\n\n"
            "• Strict mode (strict enforcement on):\n"
            "  The % becomes a hard quota filled before the rest of the session.\n"
            "  Example: physics = 20 % with 50 cards → exactly ~10 physics cards reserved.\n\n"
            "Sliders are independent — the remainder goes to untagged cards.\n"
            "Total can exceed 100 % (a warning is shown)."
        ))
        _tag_hrow.addStretch()
        layout.addLayout(_tag_hrow)

        _tag_desc = QLabel(
            "Each slider is the probability that a given pick targets this tag. "
            "In strict mode it becomes a hard quota. "
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

        for entry in self._saved.get("tag_rows", []):
            self._add_tag_row(entry["tag"], entry.get("weight", 20),
                              locked=entry.get("locked", False))

        self._other_lbl = QLabel("")
        layout.addWidget(self._other_lbl)
        self._update_other_label()

        # ── 9. Scheduling funnel (collapsible) ────────────────────────────────
        _funnel_sep = QFrame()
        _funnel_sep.setFrameShape(QFrame.Shape.HLine)
        _funnel_sep.setStyleSheet("QFrame { color: rgba(128,128,128,0.25); }")
        layout.addWidget(_funnel_sep)

        _funnel_hrow = QHBoxLayout()
        _funnel_toggle = QPushButton("▶  Scheduling funnel")
        _funnel_toggle.setCheckable(True)
        _funnel_toggle.setChecked(False)
        _funnel_toggle.setFlat(True)
        _funnel_toggle.setStyleSheet(
            "QPushButton { font-weight: bold; text-align: left; padding: 4px 2px; border: none; }"
            "QPushButton:hover { color: palette(highlight); }"
        )
        _funnel_hrow.addWidget(_funnel_toggle)
        _funnel_hrow.addWidget(_info_icon(
            "Only active when Strict enforcement is ON.\n\n"
            "─── Strict mode (enforcement checked) ───\n"
            "Each enabled phase fills its quota in full before the next phase starts.\n"
            "Drag phases to change the order; use ✓ to enable/disable individual phases.\n\n"
            "Example order — Content Types → Tag Quotas → Card Type → Selection Mode:\n"
            "  1. Fill PDF / YouTube quotas\n"
            "  2. Fill tag quotas (statistics 30 %, psychology 20 %)\n"
            "  3. Fill remaining slots with the topics / items ratio\n"
            "  4. Fill any last slots using the priority / random ratio\n"
            "  5. Fill Remaining — any ready card, always last\n\n"
            "─── Soft mode (enforcement unchecked) ───\n"
            "The funnel is INACTIVE. Phase order and the ✓ checkboxes have no effect.\n"
            "Instead, the scheduler blends all your configured targets simultaneously\n"
            "at every single pick using a debt tracker — it steers toward whichever\n"
            "bucket (tag, type, mode) is most under-represented at that moment.\n"
            "Your ratios are converged to gradually, not enforced up front."
        ))
        self._enforce_cb = QCheckBox("Strict enforcement")
        self._enforce_cb.setToolTip(
            "Strict (checked): each phase is filled in full before the next.\n"
            "The funnel order and phase checkboxes are active.\n\n"
            "Soft (unchecked): the funnel is INACTIVE.\n"
            "All dimensions are blended simultaneously at every pick using a debt\n"
            "tracker — no hard quotas, no fixed order, just gradual convergence\n"
            "toward your configured ratios."
        )
        self._enforce_cb.setChecked(self._saved.get("enforce_priority", True))
        _funnel_hrow.addStretch()
        _funnel_hrow.addWidget(self._enforce_cb)
        layout.addLayout(_funnel_hrow)

        _funnel_body = QWidget()
        _funnel_body.setVisible(False)
        _funnel_body_layout = QVBoxLayout(_funnel_body)
        _funnel_body_layout.setContentsMargins(12, 0, 0, 8)
        _funnel_body_layout.setSpacing(6)

        # ── Content type priorities ────────────────────────────────────────────
        _ct_hrow = QHBoxLayout()
        _ct_header = QLabel("Content type priorities")
        _ct_header.setStyleSheet("font-weight: bold;")
        _ct_hrow.addWidget(_ct_header)
        _ct_hrow.addWidget(_info_icon(
            "Reserve the first part of every session for a specific media type.\n\n"
            "These cards are scheduled first (Phase 0), before Topics/Items ratios,\n"
            "Tag quotas, or Scheduling priority order take effect.\n\n"
            "Example: PDF = 30 % with 50 cards → the first 15 cards are always PDFs.\n"
            "After that, normal scheduling fills the remaining 35 slots.\n\n"
            "Leave unchecked for types you don't want to prioritise.\n"
            "If fewer cards are available than the quota, all available cards are used."
        ))
        _ct_hrow.addStretch()
        _funnel_body_layout.addLayout(_ct_hrow)

        _ct_desc = QLabel(
            "Checked types are scheduled first — their percentage is filled before the rest of the session."
        )
        _ct_desc.setWordWrap(True)
        _ct_desc.setStyleSheet("color: gray;")
        _funnel_body_layout.addWidget(_ct_desc)

        _ct_tip = QLabel(
            "Tip: Tag weights (below) also apply here — "
            "e.g. statistics = 80 % means 80 % of your PDF picks will target statistics-tagged PDFs."
        )
        _ct_tip.setWordWrap(True)
        _ct_tip.setStyleSheet("color: #4a7ab5; font-size: small; padding: 2px 0;")
        _funnel_body_layout.addWidget(_ct_tip)

        _ct_tips = {
            "pdf":     (
                "Incremento PDF reading cards (note type: Incremento PDF).\n"
                "Always eligible — not limited by New / Learning / Due state.\n\n"
                "Example: 20 % of 50 cards = first 10 cards are PDFs."
            ),
            "youtube": (
                "YouTube / video cards (note type: Incremento Video).\n"
                "Always eligible — not limited by New / Learning / Due state.\n\n"
                "Example: 10 % of 50 cards = first 5 cards are YouTube videos."
            ),
            "webpage": (
                "Webpage cards (note type: Incremento Web).\n"
                "Always eligible — not limited by New / Learning / Due state.\n\n"
                "Example: 10 % of 50 cards = first 5 cards are webpages."
            ),
        }
        ct_saved = {r["type"]: r for r in self._saved.get("content_type_rows", [])}
        self._ct_rows: list[dict] = []
        for ct_type, ct_label in [
            ("pdf",     "PDF"),
            ("youtube", "YouTube / Video"),
            ("webpage", "Webpage"),
        ]:
            saved_row = ct_saved.get(ct_type, {})
            ct_enabled = saved_row.get("enabled", False)
            ct_weight  = saved_row.get("weight", 20)

            ct_widget = QWidget()
            ct_layout = QHBoxLayout(ct_widget)
            ct_layout.setContentsMargins(0, 2, 0, 2)

            ct_cb = QCheckBox(ct_label)
            ct_cb.setChecked(ct_enabled)
            ct_cb.setFixedWidth(140)
            ct_layout.addWidget(ct_cb)

            ct_slider = QSlider(Qt.Orientation.Horizontal)
            ct_slider.setRange(0, 100)
            ct_slider.setValue(ct_weight)
            ct_slider.setEnabled(ct_enabled)
            ct_slider.setToolTip("Percentage of the session to fill with this content type first")
            ct_layout.addWidget(ct_slider)

            ct_pct = QLabel(f"{ct_weight}%")
            ct_pct.setFixedWidth(36)
            ct_layout.addWidget(ct_pct)

            ct_count = QLabel("")
            ct_count.setStyleSheet("color: gray; font-size: small;")
            ct_layout.addWidget(ct_count)

            ct_layout.addWidget(_info_icon(_ct_tips[ct_type]))
            _funnel_body_layout.addWidget(ct_widget)

            ct_row = {
                "type": ct_type,
                "cb": ct_cb,
                "slider": ct_slider,
                "pct_label": ct_pct,
                "count_label": ct_count,
            }
            self._ct_rows.append(ct_row)

            qconnect(ct_cb.stateChanged,
                     lambda _, r=ct_row: r["slider"].setEnabled(r["cb"].isChecked()))
            qconnect(ct_slider.valueChanged,
                     lambda v, r=ct_row: r["pct_label"].setText(f"{v}%"))

        self._refresh_ct_counts()

        # ── Phase order funnel ─────────────────────────────────────────────────
        _inner_sep = QFrame()
        _inner_sep.setFrameShape(QFrame.Shape.HLine)
        _inner_sep.setStyleSheet("QFrame { color: rgba(128,128,128,0.25); }")
        _funnel_body_layout.addWidget(_inner_sep)

        self._funnel = FunnelWidget()
        saved_order = self._saved.get("phase_order", _DEFAULT_PHASE_ORDER)
        saved_enabled = self._saved.get("phases_enabled", {})
        for pid in _DEFAULT_PHASE_ORDER:
            self._funnel.add_phase(pid, enabled=saved_enabled.get(pid, True))
        self._funnel.set_order(saved_order, enabled=saved_enabled)
        _funnel_body_layout.addWidget(self._funnel)

        # Soft-mode banner — shown below the funnel when strict enforcement is off
        self._soft_mode_lbl = QLabel(
            "⚠  Soft mode active — the funnel order and phase checkboxes are ignored.\n"
            "    All targets blend simultaneously at every pick (debt-based)."
        )
        self._soft_mode_lbl.setStyleSheet(
            "color: #b07800;"
            "background: rgba(255,200,0,0.12);"
            "border: 1px solid rgba(180,140,0,0.35);"
            "border-radius: 4px;"
            "padding: 5px 8px;"
            "font-size: 11px;"
        )
        self._soft_mode_lbl.setWordWrap(True)
        _funnel_body_layout.addWidget(self._soft_mode_lbl)

        layout.addWidget(_funnel_body)

        def _toggle_funnel(checked):
            _funnel_toggle.setText("▼  Scheduling funnel" if checked else "▶  Scheduling funnel")
            _funnel_body.setVisible(checked)
        qconnect(_funnel_toggle.toggled, _toggle_funnel)

        def _update_funnel_state():
            strict = self._enforce_cb.isChecked()
            self._funnel.setEnabled(strict)
            _eff = QGraphicsOpacityEffect(self._funnel)
            _eff.setOpacity(1.0 if strict else 0.35)
            self._funnel.setGraphicsEffect(_eff)
            self._soft_mode_lbl.setVisible(not strict)

        _update_funnel_state()
        qconnect(self._enforce_cb.stateChanged, lambda _: _update_funnel_state())

        # ── 10. Advanced (collapsible, starts collapsed) ──────────────────────
        _adv_sep = QFrame()
        _adv_sep.setFrameShape(QFrame.Shape.HLine)
        _adv_sep.setStyleSheet("QFrame { color: rgba(128,128,128,0.25); }")
        layout.addWidget(_adv_sep)

        _adv_toggle = QPushButton("▶  Advanced")
        _adv_toggle.setCheckable(True)
        _adv_toggle.setChecked(False)
        _adv_toggle.setFlat(True)
        _adv_toggle.setStyleSheet(
            "QPushButton { font-weight: bold; text-align: left; padding: 4px 2px; border: none; }"
            "QPushButton:hover { color: palette(highlight); }"
        )
        _adv_toggle_info = _info_icon(
            "Anki search filters that identify which cards are topics vs items.\n\n"
            "Default topics filter: deck:Topics OR tag:Incremento\n"
            "Default items filter:  -deck:Topics -tag:Incremento\n\n"
            "Use 'Test' to check how many ready cards match each filter.\n"
            "Changes here affect the counts shown next to Topics / Items above."
        )
        _adv_hrow = QHBoxLayout()
        _adv_hrow.setContentsMargins(0, 0, 0, 0)
        _adv_hrow.addWidget(_adv_toggle)
        _adv_hrow.addWidget(_adv_toggle_info)
        _adv_hrow.addStretch()
        layout.addLayout(_adv_hrow)

        _adv_body = QWidget()
        _adv_body.setVisible(False)
        _adv_body_layout = QVBoxLayout(_adv_body)
        _adv_body_layout.setContentsMargins(12, 0, 0, 8)
        _adv_body_layout.setSpacing(6)

        topics_filter_row = QHBoxLayout()
        topics_filter_row.addWidget(QLabel("Topics filter:"))
        self._topics_filter_edit = QLineEdit()
        self._topics_filter_edit.setPlaceholderText("deck:Topics")
        self._topics_filter_edit.setToolTip(
            "Anki search query that identifies topic (concept) cards.\n"
            "Default: deck:Topics OR tag:Incremento"
        )
        self._topics_filter_edit.setText(self._saved.get("topics_filter", "deck:Topics"))
        topics_filter_row.addWidget(self._topics_filter_edit)
        test_topics_btn = QPushButton("Test")
        test_topics_btn.setFixedWidth(48)
        qconnect(test_topics_btn.clicked,
                 lambda: self._test_filter(self._topics_filter_edit.text().strip() or "deck:Topics"))
        topics_filter_row.addWidget(test_topics_btn)
        _adv_body_layout.addLayout(topics_filter_row)

        items_filter_row = QHBoxLayout()
        items_filter_row.addWidget(QLabel("Items filter:"))
        self._items_filter_edit = QLineEdit()
        self._items_filter_edit.setPlaceholderText("-deck:Topics")
        self._items_filter_edit.setToolTip(
            "Anki search query that identifies item (flashcard) cards.\n"
            "Default: -deck:Topics -tag:Incremento"
        )
        self._items_filter_edit.setText(self._saved.get("items_filter", "-deck:Topics"))
        items_filter_row.addWidget(self._items_filter_edit)
        test_items_btn = QPushButton("Test")
        test_items_btn.setFixedWidth(48)
        qconnect(test_items_btn.clicked,
                 lambda: self._test_filter(self._items_filter_edit.text().strip() or "-deck:Topics"))
        items_filter_row.addWidget(test_items_btn)
        _adv_body_layout.addLayout(items_filter_row)

        self._preserve_order_cb = QCheckBox("Present cards in scheduler order")
        self._preserve_order_cb.setToolTip(
            "When checked, cards appear in the exact order the scheduler selected them.\n"
            "Stopping early gives a proportional sample matching your tag/type ratios.\n"
            "Works best with soft scheduling (strict enforcement disabled).\n\n"
            "When unchecked, cards are shown in random order."
        )
        self._preserve_order_cb.setChecked(self._saved.get("preserve_order", True))
        _adv_body_layout.addWidget(self._preserve_order_cb)

        self._show_debug_cb = QCheckBox("Show debug information on cards when starting")
        self._show_debug_cb.setChecked(self._saved.get("show_debug", False))
        _adv_body_layout.addWidget(self._show_debug_cb)

        layout.addWidget(_adv_body)

        def _toggle_adv(checked):
            _adv_toggle.setText("▼  Advanced" if checked else "▶  Advanced")
            _adv_body.setVisible(checked)
        qconnect(_adv_toggle.toggled, _toggle_adv)

        qconnect(self._topics_filter_edit.textChanged, lambda _: self._refresh_counts())
        qconnect(self._items_filter_edit.textChanged,  lambda _: self._refresh_counts())

        self._refresh_counts()

        # ── Statistics history (collapsible, starts collapsed) ────────────────
        _stats_sep = QFrame()
        _stats_sep.setFrameShape(QFrame.Shape.HLine)
        _stats_sep.setStyleSheet("QFrame { color: rgba(128,128,128,0.25); }")
        layout.addWidget(_stats_sep)

        _stats_toggle = QPushButton("▶  Statistics history")
        _stats_toggle.setCheckable(True)
        _stats_toggle.setChecked(False)
        _stats_toggle.setFlat(True)
        _stats_toggle.setStyleSheet(
            "QPushButton { font-weight: bold; text-align: left; padding: 4px 2px; border: none; }"
            "QPushButton:hover { color: palette(highlight); }"
        )
        layout.addWidget(_stats_toggle)

        _stats_body = QWidget()
        _stats_body.setVisible(False)
        _stats_body_layout = QVBoxLayout(_stats_body)
        _stats_body_layout.setContentsMargins(12, 0, 0, 8)
        _stats_body_layout.setSpacing(6)

        stats_row = QHBoxLayout()

        del_today_btn = QPushButton("Delete Today")
        del_today_btn.setToolTip("Permanently delete today's statistics")
        del_today_btn.setStyleSheet("color: palette(text); opacity: 0.8;")
        qconnect(del_today_btn.clicked, self._delete_daily)
        stats_row.addWidget(del_today_btn)

        del_session_btn = QPushButton("Delete Session")
        del_session_btn.setToolTip("Clear the last session's in-memory statistics")
        del_session_btn.setStyleSheet("color: palette(text); opacity: 0.8;")
        qconnect(del_session_btn.clicked, self._delete_session)
        stats_row.addWidget(del_session_btn)

        del_lifetime_btn = QPushButton("Delete All Time")
        del_lifetime_btn.setToolTip("Permanently delete all lifetime statistics")
        del_lifetime_btn.setStyleSheet("color: palette(text); opacity: 0.8;")
        qconnect(del_lifetime_btn.clicked, self._delete_lifetime)
        stats_row.addWidget(del_lifetime_btn)

        del_all_btn = QPushButton("Delete All History")
        del_all_btn.setToolTip("Permanently delete all statistics (today + all time + session)")
        del_all_btn.setStyleSheet("color: #c0392b; font-weight: bold;")
        qconnect(del_all_btn.clicked, self._delete_all)
        stats_row.addWidget(del_all_btn)

        stats_row.addStretch()

        export_btn = QPushButton("Export JSON")
        export_btn.setToolTip("Export all saved statistics as a JSON file")
        qconnect(export_btn.clicked, self._export_json)
        stats_row.addWidget(export_btn)

        _stats_body_layout.addLayout(stats_row)
        layout.addWidget(_stats_body)

        def _toggle_stats(checked):
            _stats_toggle.setText("▼  Statistics history" if checked else "▶  Statistics history")
            _stats_body.setVisible(checked)
        qconnect(_stats_toggle.toggled, _toggle_stats)

        # -- OK / Cancel (pinned outside scroll area) --
        _btn_sep = QFrame()
        _btn_sep.setFrameShape(QFrame.Shape.HLine)
        _btn_sep.setStyleSheet("QFrame { color: rgba(128,128,128,0.35); }")
        main_layout.addWidget(_btn_sep)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.setContentsMargins(12, 4, 12, 4)
        qconnect(btn_box.accepted, self.accept)
        qconnect(btn_box.rejected, self.reject)
        main_layout.addWidget(btn_box)

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
        slider.setToolTip(
            "Probability that any given pick in the session targets this tag.\n"
            "In soft mode: a running target (~20% → roughly 1 in 5 picks aims here).\n"
            "In strict mode: a hard quota filled before the rest of the session."
        )
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

    def _refresh_ct_counts(self) -> None:
        """Update available-card counts on all content type rows."""
        _ct_filter_map = {
            "pdf":     'note:"Incremento PDF" -is:suspended',
            "youtube": 'note:"Incremento Video" -is:suspended',
            "webpage": 'note:"Incremento Web" -is:suspended',
        }
        for row in getattr(self, "_ct_rows", []):
            try:
                n = len(mw.col.find_cards(_ct_filter_map[row["type"]]))
                row["count_label"].setText(f"({n} available)")
            except Exception:
                row["count_label"].setText("")

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
        ct_weights = {
            r["type"]: r["slider"].value() / 100.0
            for r in self._ct_rows
            if r["cb"].isChecked() and r["slider"].value() > 0
        }
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
            phase_order=self._funnel.get_order(),
            phases_enabled=self._funnel.get_enabled(),
            enforce_priority=self._enforce_cb.isChecked(),
            topics_filter=self._topics_filter_edit.text().strip() or "deck:Topics",
            items_filter=self._items_filter_edit.text().strip() or "-deck:Topics",
            include_new=self._cb_new.isChecked(),
            include_learning=self._cb_learning.isChecked(),
            include_due=self._cb_due.isChecked(),
            preserve_order=self._preserve_order_cb.isChecked(),
            show_debug=self._show_debug_cb.isChecked(),
            content_type_weights=ct_weights,
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _build_current_dict(self) -> dict:
        """Serialize all current widget state to a plain dict (profile / save format)."""
        return {
            "session_card_count": self._count_spin.value(),
            "topics_slider":      self._topics_slider.value(),
            "random_slider":      self._random_slider.value(),
            "pdf_slider":         self._pdf_slider.value(),
            "no_tags_checked":    self._no_tags_cb.isChecked(),
            "phase_order":        self._funnel.get_order(),
            "phases_enabled":     self._funnel.get_enabled(),
            "enforce_priority":   self._enforce_cb.isChecked(),
            "scheduler_scope":    self._scope_combo.currentData(),
            "day_end_time":       self._get_day_end_time(),
            "tag_rows": [
                {"tag": r["tag"], "weight": r["slider"].value(), "locked": r["lock_cb"].isChecked()}
                for r in self._linked_rows
            ],
            "content_type_rows": [
                {"type": r["type"], "enabled": r["cb"].isChecked(), "weight": r["slider"].value()}
                for r in self._ct_rows
            ],
            "topics_filter":    self._topics_filter_edit.text().strip() or "deck:Topics",
            "items_filter":     self._items_filter_edit.text().strip() or "-deck:Topics",
            "include_new":      self._cb_new.isChecked(),
            "include_learning": self._cb_learning.isChecked(),
            "include_due":      self._cb_due.isChecked(),
            "preserve_order":   self._preserve_order_cb.isChecked(),
            "show_debug":       self._show_debug_cb.isChecked(),
        }

    def save_config(self) -> None:
        config = mw.addonManager.getConfig(__name__) or {}
        config["dialog"] = self._build_current_dict()
        mw.addonManager.writeConfig(__name__, config)

    # ------------------------------------------------------------------
    # Profile management
    # ------------------------------------------------------------------

    def _refresh_profile_combo(self) -> None:
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        for name in sorted(self._profiles.keys()):
            self._profile_combo.addItem(name)
        has = self._profile_combo.count() > 0
        self._profile_load_btn.setEnabled(has)
        self._profile_delete_btn.setEnabled(has)
        self._profile_combo.blockSignals(False)

    def _load_profile(self) -> None:
        name = self._profile_combo.currentText()
        if not name or name not in self._profiles:
            return
        self._load_profile_dict(self._profiles[name])

    def _save_profile_as(self) -> None:
        current = self._profile_combo.currentText()
        name, ok = QInputDialog.getText(
            self, "Save Profile", "Profile name:", text=current
        )
        name = name.strip()
        if not ok or not name:
            return
        if name in self._profiles:
            r = QMessageBox.question(
                self, "Overwrite Profile",
                f'Profile "{name}" already exists. Overwrite?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if r != QMessageBox.StandardButton.Yes:
                return
        self._profiles[name] = self._build_current_dict()
        config = mw.addonManager.getConfig(__name__) or {}
        config["profiles"] = self._profiles
        mw.addonManager.writeConfig(__name__, config)
        self._refresh_profile_combo()
        idx = self._profile_combo.findText(name)
        if idx >= 0:
            self._profile_combo.setCurrentIndex(idx)
        tooltip(f'Profile "{name}" saved.')

    def _delete_profile(self) -> None:
        name = self._profile_combo.currentText()
        if not name or name not in self._profiles:
            return
        r = QMessageBox.question(
            self, "Delete Profile",
            f'Delete profile "{name}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        del self._profiles[name]
        config = mw.addonManager.getConfig(__name__) or {}
        config["profiles"] = self._profiles
        mw.addonManager.writeConfig(__name__, config)
        self._refresh_profile_combo()
        tooltip(f'Profile "{name}" deleted.')

    def _load_profile_dict(self, d: dict) -> None:
        """Apply a profile dict to all dialog widgets."""
        self._count_spin.setValue(d.get("session_card_count", 50))

        topics_val = d.get("topics_slider", 10)
        self._topics_slider.setValue(topics_val)
        self._topics_left_lbl.setText(f"{100 - topics_val}%")
        self._topics_right_lbl.setText(f"{topics_val}%")

        pdf_val = d.get("pdf_slider", 0)
        self._pdf_slider.setValue(pdf_val)
        self._pdf_left_lbl.setText(f"{100 - pdf_val}%")
        self._pdf_right_lbl.setText(f"{pdf_val}%")

        random_val = d.get("random_slider", 99)
        self._random_slider.setValue(random_val)
        self._random_left_lbl.setText(f"{100 - random_val}%")
        self._random_right_lbl.setText(f"{random_val}%")

        self._cb_new.setChecked(d.get("include_new", True))
        self._cb_learning.setChecked(d.get("include_learning", True))
        self._cb_due.setChecked(d.get("include_due", True))
        self._no_tags_cb.setChecked(d.get("no_tags_checked", True))
        self._enforce_cb.setChecked(d.get("enforce_priority", True))

        saved_scope = d.get("scheduler_scope", "session")
        for i in range(self._scope_combo.count()):
            if self._scope_combo.itemData(i) == saved_scope:
                self._scope_combo.setCurrentIndex(i)
                break

        saved_time = d.get("day_end_time", "00:00")
        preset_idx = next(
            (i for i in range(self._day_end_preset.count())
             if self._day_end_preset.itemData(i) == saved_time),
            None,
        )
        if preset_idx is not None:
            self._day_end_preset.setCurrentIndex(preset_idx)
        else:
            self._day_end_preset.setCurrentIndex(self._day_end_preset.count() - 1)
            try:
                h, m = map(int, saved_time.split(":"))
                self._day_end_edit.setTime(QTime(h, m))
            except Exception:
                pass
        self._update_day_end_visibility()

        self._funnel.set_order(
            d.get("phase_order", _DEFAULT_PHASE_ORDER),
            enabled=d.get("phases_enabled", {}),
        )

        self._topics_filter_edit.setText(d.get("topics_filter", "deck:Topics"))
        self._items_filter_edit.setText(d.get("items_filter", "-deck:Topics"))
        self._preserve_order_cb.setChecked(d.get("preserve_order", True))
        self._show_debug_cb.setChecked(d.get("show_debug", False))

        # Replace tag rows
        for row in list(self._linked_rows):
            self._remove_row(row)
        for entry in d.get("tag_rows", []):
            self._add_tag_row(entry["tag"], entry.get("weight", 20),
                              locked=entry.get("locked", False))

        # Restore content type rows
        ct_saved = {r["type"]: r for r in d.get("content_type_rows", [])}
        for row in self._ct_rows:
            saved = ct_saved.get(row["type"], {})
            row["cb"].setChecked(saved.get("enabled", False))
            w = saved.get("weight", 20)
            row["slider"].setValue(w)
            row["pct_label"].setText(f"{w}%")
            row["slider"].setEnabled(row["cb"].isChecked())

        self._update_other_label()
        self._refresh_counts()
