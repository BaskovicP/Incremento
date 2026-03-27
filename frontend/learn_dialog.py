import json
import os

from aqt import mw
from aqt.qt import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QCheckBox, QComboBox, QPushButton, QWidget, Qt, qconnect,
    QTimeEdit, QTime, QSpinBox, QLineEdit, QMessageBox, QFileDialog, QFrame,
    QInputDialog, QScrollArea,
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

        # ── 3. Content type priorities (Phase 0 — runs before everything else) ─
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
        layout.addLayout(_ct_hrow)

        _ct_desc = QLabel(
            "Checked types are scheduled first — their percentage is filled before the rest of the session."
        )
        _ct_desc.setWordWrap(True)
        _ct_desc.setStyleSheet("color: gray;")
        layout.addWidget(_ct_desc)

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
            layout.addWidget(ct_widget)

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

        # ── 4. Topics / Items ratio ───────────────────────────────────────────
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

        # ── 8. Scheduling priority order (Phase 1) ────────────────────────────
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
        priority_header.addWidget(_info_icon(
            "Controls how the remaining session slots (after Content type priorities)\n"
            "are ordered when Strict enforcement is on.\n\n"
            "The three combo boxes set which dimension's quota is filled first:\n"
            "• Tags — fill each tag's quota in full before moving to the next tag\n"
            "• Type — fill all topic slots before item slots (or vice-versa)\n"
            "• Mode — fill all Priority-mode slots before Random-mode slots\n\n"
            "Example (Tags → Type → Mode, strict on):\n"
            "  1. Fill tag:physics quota → 2. Fill remaining topics → 3. Fill items\n\n"
            "When Strict enforcement is off, all three dimensions are balanced\n"
            "simultaneously using a debt-based soft picker."
        ))
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

        # ── 9. Tag quotas ─────────────────────────────────────────────────────
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
            "  The % becomes a hard quota filled first in Phase 1.\n"
            "  Example: physics = 20 % with 50 cards → exactly ~10 physics cards reserved.\n\n"
            "Sliders are independent — the remainder goes to untagged cards.\n"
            "Total can exceed 100 % (a warning is shown).\n\n"
            "Tag quotas run during Phase 1, after Content type priorities (Phase 0)."
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

        # ── 10. Advanced ──────────────────────────────────────────────────────
        _adv_hrow = QHBoxLayout()
        _adv_header = QLabel("Advanced")
        _adv_header.setStyleSheet("font-weight: bold;")
        _adv_hrow.addWidget(_adv_header)
        _adv_hrow.addWidget(_info_icon(
            "Anki search filters that identify which cards are topics vs items.\n\n"
            "Default topics filter: deck:Topics OR tag:Incremento\n"
            "Default items filter:  -deck:Topics -tag:Incremento\n\n"
            "Use 'Test' to check how many ready cards match each filter.\n"
            "Changes here affect the counts shown next to Topics / Items above."
        ))
        _adv_hrow.addStretch()
        layout.addLayout(_adv_hrow)

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
        layout.addLayout(topics_filter_row)

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

        # ── Statistics history ────────────────────────────────────────────────
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
            priority_order=self._get_priority_order(),
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
            "priority_order":     self._get_priority_order(),
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
        self._priority_order_widget.setEnabled(self._enforce_cb.isChecked())

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

        self._refresh_priority_combos(d.get("priority_order", ["tags", "type", "mode"]))

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
