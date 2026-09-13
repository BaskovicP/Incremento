import json
import os
import re
import copy
import math
from html import escape, unescape

from aqt import mw
from aqt.qt import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
    QFormLayout,
    QLabel, QSlider, QCheckBox, QComboBox, QPushButton, QWidget, Qt, qconnect,
    QTimeEdit, QTime, QSpinBox, QLineEdit, QMessageBox, QFileDialog, QFrame,
    QInputDialog, QScrollArea, QObject, QEvent, QGraphicsOpacityEffect, QSplitter,
    QTextBrowser, QTableWidget, QTableWidgetItem, QHeaderView, QTimer, QColor,
)
from aqt.utils import showInfo, tooltip

try:
    from ..backend.i18n import t, tn
except ImportError:
    from backend.i18n import t, tn  # type: ignore

try:
    from .session_setup_model import (
        ADVANCED_MODE,
        BASIC_MODE,
        format_basic_session_summary,
        normalize_setup_mode,
    )
except ImportError:
    from session_setup_model import (  # type: ignore
        ADVANCED_MODE,
        BASIC_MODE,
        format_basic_session_summary,
        normalize_setup_mode,
    )

try:
    from ..backend.paths import get_active_profile as _active_profile
except ImportError:
    from paths import get_active_profile as _active_profile

try:
    from ..backend import cards as _card_utils
    from ..backend.config_service import load_addon_config, save_addon_config
    from ..backend.scheduler_config import (
        MAX_SESSION_CARD_COUNT,
        SchedulerConfig,
        NO_TAGS_KEY,
        build_ready_filter,
    )
    from ..backend.scheduler_preview import compute_expected_mix
    from ..backend.session_selection import select_session_cards
    from ..backend.pdf_manager import (
        PDF_NOTE_TYPE,
        get_page,
        get_pdf_daily_limit_settings,
        get_pdf_daily_limit_status,
        get_read_page,
        pdf_storage_abspath,
        save_pdf_daily_limit_settings,
    )
    from ..backend.statistics import (
        delete_all_stats,
        delete_daily_stats,
        delete_lifetime_stats,
        export_stats_data,
    )
except ImportError:
    import cards as _card_utils
    from config_service import load_addon_config, save_addon_config  # type: ignore
    from scheduler_config import (
        MAX_SESSION_CARD_COUNT,
        SchedulerConfig,
        NO_TAGS_KEY,
        build_ready_filter,
    )
    from scheduler_preview import compute_expected_mix
    from session_selection import select_session_cards
    from pdf_manager import (
        PDF_NOTE_TYPE,
        get_page,
        get_pdf_daily_limit_settings,
        get_pdf_daily_limit_status,
        get_read_page,
        pdf_storage_abspath,
        save_pdf_daily_limit_settings,
    )
    from statistics import (  # type: ignore
        delete_all_stats,
        delete_daily_stats,
        delete_lifetime_stats,
        export_stats_data,
    )

# Addon root: one level above this file (frontend/)
_ADDON_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_ADDON_PKG = __name__.split(".")[0]


def _write_named_scheduler_profile(name: str, profile_data: dict, profiles: dict[str, dict]) -> dict[str, dict]:
    updated_profiles = dict(profiles or {})
    updated_profiles[name] = profile_data
    config = load_addon_config(mw.addonManager, _ADDON_PKG)
    config["scheduler_presets"] = updated_profiles
    config["profiles"] = updated_profiles
    save_addon_config(mw.addonManager, _ADDON_PKG, config)
    return updated_profiles


def _rename_named_scheduler_profile(old_name: str, new_name: str, profiles: dict[str, dict]) -> dict[str, dict]:
    updated_profiles: dict[str, dict] = {}
    for name, profile in (profiles or {}).items():
        updated_profiles[new_name if name == old_name else name] = profile
    config = load_addon_config(mw.addonManager, _ADDON_PKG)
    config["scheduler_presets"] = updated_profiles
    config["profiles"] = updated_profiles
    dialog_config = config.get("dialog") or {}
    if dialog_config.get("selected_profile") == old_name:
        dialog_config["selected_profile"] = new_name
        config["dialog"] = dialog_config
    save_addon_config(mw.addonManager, _ADDON_PKG, config)
    return updated_profiles


def _normalize_selected_scheduler_profile(
    selected_profile: str | None,
    profiles: dict[str, dict] | None,
) -> str | None:
    name = str(selected_profile or "").strip()
    if not name:
        return None
    if name not in (profiles or {}):
        return None
    return name


def _initial_scheduler_dialog_state(
    dialog_config: dict | None,
    profiles: dict[str, dict] | None,
    selected_profile: str | None,
) -> dict:
    base = dict(dialog_config or {})
    normalized_selected = _normalize_selected_scheduler_profile(
        selected_profile,
        profiles,
    )
    if not normalized_selected:
        return base

    selected_profile_data = (profiles or {}).get(normalized_selected)
    if not isinstance(selected_profile_data, dict):
        return base

    merged = dict(base)
    merged.update(copy.deepcopy(selected_profile_data))
    merged["selected_profile"] = normalized_selected
    return merged


def _compute_expected_mix(
    session_card_count: int,
    topics_slider: int,
    pdf_slider: int,
    random_slider: int,
) -> dict:
    """Compatibility wrapper for UI code and potential test imports."""
    return compute_expected_mix(
        session_card_count=session_card_count,
        topics_slider=topics_slider,
        pdf_slider=pdf_slider,
        random_slider=random_slider,
    )


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


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _field_to_plain_text(text: str) -> str:
    s = (text or "")
    s = s.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    s = _HTML_TAG_RE.sub("", s)
    return unescape(s).strip()


def _compact_text(text: str, max_len: int = 120) -> str:
    flat = " ".join(_field_to_plain_text(text).split())
    if len(flat) <= max_len:
        return flat
    return flat[: max_len - 1] + "…"


def _normalize_branch_scope(branch_scope: dict | None) -> dict | None:
    if not isinstance(branch_scope, dict):
        return None

    normalized_ids: list[int] = []
    seen: set[int] = set()
    for raw_card_id in list(branch_scope.get("card_ids") or []):
        try:
            card_id = int(raw_card_id)
        except Exception:
            continue
        if card_id in seen:
            continue
        seen.add(card_id)
        normalized_ids.append(card_id)

    return {
        "root_card_id": (
            None
            if branch_scope.get("root_card_id") is None
            else int(branch_scope["root_card_id"])
        ),
        "root_title": str(branch_scope.get("root_title") or "").strip(),
        "card_ids": normalized_ids,
    }


def _cid_clause(card_ids: list[int]) -> str:
    if not card_ids:
        return ""
    return "(" + " OR ".join(f"cid:{int(card_id)}" for card_id in card_ids) + ")"


def _compose_branch_query(query: str, branch_clause: str) -> str:
    base = str(query or "").strip()
    branch = str(branch_clause or "").strip()
    if base and branch:
        return f"({base}) {branch}"
    if branch:
        return branch
    return base


def session_type_label(value: object) -> str:
    """Translate known presentation values without changing scheduler identity."""
    key = str(value or "?")
    message_id = {
        "topics": "session_topics", "topic": "session_topics",
        "items": "session_items", "item": "session_items",
        "video": "ui_type_video", "youtube": "ui_type_video",
        "webpage": "ui_type_webpage", "web": "ui_type_webpage",
        "writing": "ui_type_writing", "local_file": "ui_type_local_file",
        "other": "session_other",
    }.get(key)
    return t(message_id) if message_id else key.upper() if key in {"pdf", "epub"} else key


def session_mode_label(value: object) -> str:
    key = str(value or "?")
    message_id = {"priority": "session_priority", "random": "session_random"}.get(key)
    return t(message_id) if message_id else key


def _preview_tag_label(value: object) -> str:
    if value == NO_TAGS_KEY:
        return t("session_other")
    return str(value) if value else t("admin_session_no_tag")


class _SortTableWidgetItem(QTableWidgetItem):
    """Table item that sorts by explicit key when provided."""

    def __lt__(self, other):
        if not isinstance(other, QTableWidgetItem):
            return super().__lt__(other)
        a = self.data(Qt.ItemDataRole.UserRole)
        b = other.data(Qt.ItemDataRole.UserRole)
        if a is not None and b is not None:
            try:
                return a < b
            except Exception:
                pass
        return self.text().lower() < other.text().lower()


class _LiveSchedulerPreviewDialog(QDialog):
    """Modeless dialog showing currently scheduled cards and per-card preview."""

    def __init__(self, owner: "SchedulerConfigDialog"):
        super().__init__(owner)
        self._owner = owner
        self._entries: list[dict] = []

        self.setWindowTitle(t("session_live_preview_title"))
        self.resize(980, 620)
        self._current_entry: dict | None = None
        self._pdf_limit_loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self._summary_lbl = QLabel(t("session_live_preview_refresh_hint"))
        self._summary_lbl.setWordWrap(True)
        self._summary_lbl.setStyleSheet("color: gray;")
        root.addWidget(self._summary_lbl)

        self._disclaimer_lbl = QLabel(t("session_live_preview_disclaimer"))
        self._disclaimer_lbl.setWordWrap(True)
        self._disclaimer_lbl.setStyleSheet("color: #8a4b00; font-size: small;")
        root.addWidget(self._disclaimer_lbl)

        self._use_live_preview_cb = QCheckBox(t("session_use_previewed_list"))
        self._use_live_preview_cb.setChecked(owner._use_live_preview_enabled)
        self._use_live_preview_cb.setToolTip(
            t("session_use_previewed_list_tooltip")
        )
        qconnect(
            self._use_live_preview_cb.stateChanged,
            lambda _: self._owner.set_use_live_preview_enabled(self._use_live_preview_cb.isChecked()),
        )
        root.addWidget(self._use_live_preview_cb)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["#", t("session_type"), t("session_mode"), t("session_tag"), t("session_card")]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(True)
        hdr = self._table.horizontalHeader()
        hdr.setSortIndicatorShown(True)
        hdr.setSectionsClickable(True)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        splitter.addWidget(self._table)

        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self._preview = QTextBrowser()
        self._preview.setOpenExternalLinks(False)
        right_layout.addWidget(self._preview, 1)

        self._pdf_limit_box = QFrame(self)
        self._pdf_limit_box.setStyleSheet(
            "QFrame { border: 1px solid rgba(120,120,120,0.35); border-radius: 6px; padding: 4px; }"
        )
        pdf_limit_layout = QVBoxLayout(self._pdf_limit_box)
        pdf_limit_layout.setContentsMargins(8, 8, 8, 8)
        pdf_limit_layout.setSpacing(6)

        pdf_limit_title = QLabel(t("session_pdf_daily_limit"))
        pdf_limit_title.setStyleSheet("font-weight: 600;")
        pdf_limit_layout.addWidget(pdf_limit_title)

        self._pdf_limit_summary = QLabel(t("session_pdf_limit_select_card"))
        self._pdf_limit_summary.setWordWrap(True)
        self._pdf_limit_summary.setStyleSheet("color: gray;")
        pdf_limit_layout.addWidget(self._pdf_limit_summary)

        pdf_limit_form = QFormLayout()
        pdf_limit_form.setContentsMargins(0, 0, 0, 0)
        pdf_limit_form.setSpacing(6)

        self._pdf_limit_enabled = QCheckBox(t("session_pdf_limit_enable"))
        qconnect(self._pdf_limit_enabled.toggled, self._on_pdf_limit_form_changed)
        pdf_limit_form.addRow(t("common_enabled"), self._pdf_limit_enabled)

        limit_row = QWidget(self)
        limit_row_layout = QHBoxLayout(limit_row)
        limit_row_layout.setContentsMargins(0, 0, 0, 0)
        limit_row_layout.setSpacing(6)
        self._pdf_limit_spin = QSpinBox(self)
        self._pdf_limit_spin.setRange(1, 5000)
        self._pdf_limit_spin.setValue(10)
        qconnect(self._pdf_limit_spin.valueChanged, self._on_pdf_limit_form_changed)
        limit_row_layout.addWidget(self._pdf_limit_spin)
        self._pdf_limit_mode = QComboBox(self)
        self._pdf_limit_mode.addItem(t("session_pdf_limit_warning"), "warning")
        self._pdf_limit_mode.addItem(t("session_pdf_limit_soft_lock"), "soft_lock")
        self._pdf_limit_mode.addItem(t("session_pdf_limit_hard_stop"), "hard_stop")
        qconnect(self._pdf_limit_mode.currentIndexChanged, self._on_pdf_limit_form_changed)
        limit_row_layout.addWidget(self._pdf_limit_mode, 1)
        pdf_limit_form.addRow(t("session_pdf_limit"), limit_row)
        pdf_limit_layout.addLayout(pdf_limit_form)

        pdf_limit_actions = QHBoxLayout()
        pdf_limit_actions.setContentsMargins(0, 0, 0, 0)
        pdf_limit_actions.addStretch()
        self._pdf_limit_save_btn = QPushButton(t("session_save_pdf_limit"))
        qconnect(self._pdf_limit_save_btn.clicked, self._save_selected_pdf_limit)
        pdf_limit_actions.addWidget(self._pdf_limit_save_btn)
        pdf_limit_layout.addLayout(pdf_limit_actions)

        right_layout.addWidget(self._pdf_limit_box)
        splitter.addWidget(right)

        splitter.setSizes([520, 460])
        root.addWidget(splitter, 1)

        row = QHBoxLayout()
        row.addStretch()
        self._refresh_btn = QPushButton(t("common_refresh"))
        qconnect(self._refresh_btn.clicked, self.refresh_now)
        row.addWidget(self._refresh_btn)
        close_btn = QPushButton(t("common_close"))
        qconnect(close_btn.clicked, self.close)
        row.addWidget(close_btn)
        root.addLayout(row)

        qconnect(self._table.currentCellChanged, self._on_row_changed)
        self._set_pdf_limit_editor_visible(False)

    def sync_use_preview_checkbox(self) -> None:
        self._use_live_preview_cb.blockSignals(True)
        self._use_live_preview_cb.setChecked(self._owner._use_live_preview_enabled)
        self._use_live_preview_cb.blockSignals(False)

    def _set_pdf_limit_editor_visible(self, visible: bool) -> None:
        self._pdf_limit_box.setVisible(bool(visible))

    def _set_pdf_limit_form_enabled_state(self) -> None:
        enabled = self._pdf_limit_enabled.isChecked()
        self._pdf_limit_spin.setEnabled(enabled)
        self._pdf_limit_mode.setEnabled(enabled)
        self._pdf_limit_save_btn.setEnabled(self._current_entry is not None)

    def _on_pdf_limit_form_changed(self, *_args) -> None:
        if self._pdf_limit_loading:
            return
        self._set_pdf_limit_form_enabled_state()

    def _load_pdf_limit_editor(self, entry: dict | None) -> None:
        self._current_entry = entry
        if not entry or entry.get("card_type") != "pdf":
            self._set_pdf_limit_editor_visible(False)
            self._set_pdf_limit_form_enabled_state()
            return

        self._set_pdf_limit_editor_visible(True)
        settings = dict(entry.get("pdf_limit_settings") or {
            "enabled": False,
            "daily_page_limit": 10,
            "enforcement_mode": "warning",
        })
        status = entry.get("pdf_limit_status") or {}

        self._pdf_limit_loading = True
        self._pdf_limit_enabled.setChecked(bool(settings.get("enabled")))
        self._pdf_limit_spin.setValue(max(1, int(settings.get("daily_page_limit", 10) or 10)))
        idx = self._pdf_limit_mode.findData(str(settings.get("enforcement_mode") or "warning"))
        self._pdf_limit_mode.setCurrentIndex(max(0, idx))
        self._pdf_limit_loading = False

        if status:
            self._pdf_limit_summary.setText(t(
                "session_pdf_limit_status",
                used=status["pages_used"],
                limit=status["daily_page_limit"],
                remaining=status["pages_remaining"],
                current_page=entry.get("pdf_page") or 1,
                read_through=entry.get("pdf_read_page") or 0,
            ))
        else:
            self._pdf_limit_summary.setText(t("session_pdf_limit_not_set"))
        self._set_pdf_limit_form_enabled_state()

    def _selected_entry_index(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        if item is None:
            return None
        idx = item.data(Qt.ItemDataRole.UserRole + 1)
        try:
            return int(idx)
        except Exception:
            return None

    def _save_selected_pdf_limit(self) -> None:
        entry = self._current_entry
        if not entry or entry.get("card_type") != "pdf":
            return
        cid = int(entry["card_id"])
        save_pdf_daily_limit_settings(
            _ADDON_DIR,
            _active_profile(),
            cid,
            enabled=self._pdf_limit_enabled.isChecked(),
            daily_page_limit=int(self._pdf_limit_spin.value()),
            enforcement_mode=str(self._pdf_limit_mode.currentData() or "warning"),
        )
        try:
            status = get_pdf_daily_limit_status(
                _ADDON_DIR,
                _active_profile(),
                cid,
                current_page=entry.get("pdf_page"),
                persist_usage=False,
            )
        except Exception:
            status = None
        settings = get_pdf_daily_limit_settings(_ADDON_DIR, _active_profile(), cid)
        entry["pdf_limit_status"] = status if status and status.get("enabled") else None
        entry["pdf_limit_settings"] = settings
        self._show_entry(entry)
        self._load_pdf_limit_editor(entry)
        tooltip(t("session_pdf_limit_saved"))

    def _on_row_changed(self, row: int, _old_row: int, _col: int, _old_col: int) -> None:
        if row < 0:
            self._load_pdf_limit_editor(None)
            return
        first_item = self._table.item(row, 0)
        if first_item is None:
            self._load_pdf_limit_editor(None)
            return
        entry_idx = first_item.data(Qt.ItemDataRole.UserRole + 1)
        if entry_idx is None:
            self._load_pdf_limit_editor(None)
            return
        try:
            idx = int(entry_idx)
        except Exception:
            self._load_pdf_limit_editor(None)
            return
        if idx < 0 or idx >= len(self._entries):
            self._load_pdf_limit_editor(None)
            return
        self._show_entry(self._entries[idx])
        self._load_pdf_limit_editor(self._entries[idx])

    @staticmethod
    def _fmt_counts(counts: dict) -> str:
        if not counts:
            return t("common_none")
        return ", ".join(f"{k}: {v}" for k, v in sorted(counts.items(), key=lambda x: x[0]))

    def _update_summary(self, selected_ids: list[int], picked_meta: dict[int, dict], target: int) -> None:
        type_counts: dict[str, int] = {}
        mode_counts: dict[str, int] = {}
        tag_counts: dict[str, int] = {}
        prioritized_count = 0
        for cid in selected_ids:
            meta = picked_meta.get(cid, {})
            ct = session_type_label(meta.get("card_type", "?"))
            md = session_mode_label(meta.get("mode", "?"))
            tg = _preview_tag_label(meta.get("tag"))
            if meta.get("selection_stage") in {"prioritized_tags", "ordered_priority"}:
                prioritized_count += 1
            type_counts[ct] = type_counts.get(ct, 0) + 1
            mode_counts[md] = mode_counts.get(md, 0) + 1
            tag_counts[tg] = tag_counts.get(tg, 0) + 1

        status = t("session_preview_scheduled", count=len(selected_ids), target=target)
        if len(selected_ids) < target:
            status += " " + t("session_preview_limited")
        if prioritized_count:
            status += " " + t("session_preview_ordered", count=prioritized_count)

        self._summary_lbl.setText(
            t("session_preview_counts", status=status,
              types=self._fmt_counts(type_counts), modes=self._fmt_counts(mode_counts),
              tags=self._fmt_counts(tag_counts))
        )

    def _show_entry(self, entry: dict) -> None:
        parts = [
            "<div style='font-family:sans-serif; padding: 6px 8px;'>",
            f"<h3 style='margin:0 0 8px 0;'>{escape(entry['title'])}</h3>",
            f"<div><b>{escape(t('session_preview_card_id'))}</b> {entry['card_id']}</div>",
            f"<div><b>{escape(t('session_preview_type'))}</b> {escape(session_type_label(entry['card_type']))}</div>",
            f"<div><b>{escape(t('session_preview_mode'))}</b> {escape(session_mode_label(entry['mode']))}</div>",
            f"<div><b>{escape(t('session_preview_tag'))}</b> {escape(entry['tag'])}</div>",
        ]
        if entry.get("selection_stage") == "prioritized_tags":
            parts.append(f"<div><b>{escape(t('session_preview_selection_stage'))}</b> {escape(t('session_preview_tag_first'))}</div>")
        if entry.get("selection_stage") == "ordered_priority":
            order = entry.get("priority_order")
            suffix = "" if order is None else t("session_preview_order", order=str(order))
            parts.append(f"<div><b>{escape(t('session_preview_selection_stage'))}</b> {escape(t('session_preview_priority_pass') + suffix)}</div>")
        if entry.get("pdf_filename"):
            parts.append(f"<div><b>{escape(t('session_preview_pdf_file'))}</b> {escape(entry['pdf_filename'])}</div>")
            if entry.get("pdf_exists") is not None:
                status_text = t("session_preview_file_found") if entry['pdf_exists'] else t(
                    "session_preview_file_missing", path='user_files/' + _active_profile() + '/pdfs')
                parts.append(
                    f"<div><b>{escape(t('session_preview_pdf_status'))}</b> {escape(status_text)}</div>"
                )
            if entry.get("pdf_page") is not None:
                parts.append(f"<div><b>{escape(t('session_preview_current_page'))}</b> {entry['pdf_page']}</div>")
            if entry.get("pdf_read_page") is not None:
                parts.append(f"<div><b>{escape(t('session_preview_read_page'))}</b> {entry['pdf_read_page']}</div>")
            if entry.get("pdf_limit_status"):
                limit_status = entry["pdf_limit_status"]
                mode = str(limit_status.get('enforcement_mode') or 'warning')
                mode_id = {'warning': 'session_pdf_limit_warning', 'soft_lock': 'session_pdf_limit_soft_lock',
                           'hard_stop': 'session_pdf_limit_hard_stop'}.get(mode, 'session_pdf_limit_warning')
                detail = t('session_preview_limit_details', used=limit_status['pages_used'],
                           limit=limit_status['daily_page_limit'], remaining=limit_status['pages_remaining'], mode=t(mode_id))
                parts.append(
                    f"<div><b>{escape(t('session_preview_daily_limit'))}</b> {escape(detail)}</div>"
                )
        if entry.get("tags"):
            parts.append(f"<div><b>{escape(t('session_preview_note_tags'))}</b> {escape(entry['tags'])}</div>")

        for field_name, field_value in entry["fields"]:
            parts.append(
                "<div style='margin-top:10px;'>"
                f"<div style='font-weight:600; margin-bottom:4px;'>{escape(field_name)}</div>"
                "<div style='white-space:pre-wrap; background:#f6f6f6; border:1px solid #ddd; "
                f"border-radius:4px; padding:6px; color:#111;'>{escape(field_value)}</div>"
                "</div>"
            )
        parts.append("</div>")
        self._preview.setHtml("".join(parts))

    @staticmethod
    def _safe_note_field(note, field_name: str) -> str:
        try:
            v = note[field_name]
            return str(v).strip()
        except Exception:
            return ""

    def refresh_now(self) -> None:
        self._refresh_btn.setEnabled(False)
        try:
            cfg = self._owner.to_config()
            result = select_session_cards(
                cfg,
                _ADDON_DIR,
                branch_scope=self._owner._branch_scope,
            )
            selected_ids = result.selected_ids
            picked_meta = result.picked_meta
            self._update_summary(selected_ids, picked_meta, cfg.session_card_count)
            self._owner._cache_live_preview_result(result)

            entries: list[dict] = []
            self._table.setSortingEnabled(False)
            self._table.setRowCount(0)
            for i, cid in enumerate(selected_ids):
                meta = picked_meta.get(cid, {})
                card = mw.col.get_card(cid)
                note = mw.col.get_note(card.nid)
                note_fields = getattr(note, "fields", []) or []
                try:
                    model = note.note_type()
                    field_names = [f.get("name", t("session_preview_field_number", number=ix + 1)) for ix, f in enumerate(model.get("flds", []))]
                except Exception:
                    field_names = [t("session_preview_field_number", number=ix + 1) for ix, _ in enumerate(note_fields)]
                if len(field_names) < len(note_fields):
                    for ix in range(len(field_names), len(note_fields)):
                        field_names.append(t("session_preview_field_number", number=ix + 1))

                readable_fields = []
                for idx, raw_val in enumerate(note_fields):
                    readable_fields.append((field_names[idx], _field_to_plain_text(raw_val)))

                card_type = str(meta.get("card_type", "?"))
                mode = str(meta.get("mode", "?"))
                tag = meta.get("tag")
                tag_text = _preview_tag_label(tag)
                title = _compact_text(note_fields[0] if note_fields else str(cid), max_len=160)
                tags = ", ".join(getattr(note, "tags", []) or [])
                pdf_filename = ""
                pdf_page = None
                pdf_read_page = None
                pdf_exists = None
                pdf_limit_status = None
                pdf_limit_settings = None
                if card_type == "pdf":
                    pdf_filename = self._safe_note_field(note, "PDF_Filename")
                    try:
                        pdf_page = int(get_page(_ADDON_DIR, _active_profile(), cid))
                    except Exception:
                        pdf_page = None
                    try:
                        pdf_read_page = int(get_read_page(_ADDON_DIR, _active_profile(), cid))
                    except Exception:
                        pdf_read_page = None
                    if pdf_filename:
                        try:
                            pdf_exists = os.path.exists(pdf_storage_abspath(pdf_filename))
                        except Exception:
                            pdf_exists = None
                    try:
                        pdf_limit_settings = get_pdf_daily_limit_settings(
                            _ADDON_DIR,
                            _active_profile(),
                            cid,
                        )
                    except Exception:
                        pdf_limit_settings = None
                    try:
                        status = get_pdf_daily_limit_status(
                            _ADDON_DIR,
                            _active_profile(),
                            cid,
                            current_page=pdf_page,
                            persist_usage=False,
                        )
                        if status.get("enabled"):
                            pdf_limit_status = status
                    except Exception:
                        pdf_limit_status = None

                entries.append(
                    {
                        "card_id": cid,
                        "card_type": card_type,
                        "mode": mode,
                        "tag": tag_text,
                        "selection_stage": meta.get("selection_stage"),
                        "priority_order": meta.get("priority_order"),
                        "title": title or t("knowledge_tree_card_number", card_id=cid),
                        "tags": tags,
                        "fields": readable_fields,
                        "pdf_filename": pdf_filename,
                        "pdf_page": pdf_page,
                        "pdf_read_page": pdf_read_page,
                        "pdf_exists": pdf_exists,
                        "pdf_limit_status": pdf_limit_status,
                        "pdf_limit_settings": pdf_limit_settings,
                    }
                )

            self._entries = entries
            self._table.setRowCount(len(entries))
            for row, entry in enumerate(entries):
                row_num_item = _SortTableWidgetItem(str(row + 1))
                row_num_item.setData(Qt.ItemDataRole.UserRole, row + 1)
                row_num_item.setData(Qt.ItemDataRole.UserRole + 1, row)
                self._table.setItem(row, 0, row_num_item)

                ct_item = _SortTableWidgetItem(session_type_label(entry["card_type"]))
                ct_item.setData(Qt.ItemDataRole.UserRole, entry["card_type"].lower())
                ct_item.setData(Qt.ItemDataRole.UserRole + 1, row)
                self._table.setItem(row, 1, ct_item)

                mode_item = _SortTableWidgetItem(session_mode_label(entry["mode"]))
                mode_item.setData(Qt.ItemDataRole.UserRole, entry["mode"].lower())
                mode_item.setData(Qt.ItemDataRole.UserRole + 1, row)
                self._table.setItem(row, 2, mode_item)

                tag_item = _SortTableWidgetItem(entry["tag"])
                tag_item.setData(Qt.ItemDataRole.UserRole, entry["tag"].lower())
                tag_item.setData(Qt.ItemDataRole.UserRole + 1, row)
                self._table.setItem(row, 3, tag_item)

                title_item = _SortTableWidgetItem(entry["title"])
                title_item.setData(Qt.ItemDataRole.UserRole, entry["title"].lower())
                title_item.setData(Qt.ItemDataRole.UserRole + 1, row)
                self._table.setItem(row, 4, title_item)

            self._table.setSortingEnabled(True)
            self._table.sortByColumn(0, Qt.SortOrder.AscendingOrder)

            if entries:
                self._table.selectRow(0)
                self._on_row_changed(0, -1, 0, -1)
            else:
                self._preview.setHtml(
                    f"<div style='color:#666; padding:10px;'>{escape(t('session_preview_no_cards'))}</div>"
                )
                self._load_pdf_limit_editor(None)
        except Exception as e:
            self._summary_lbl.setText(t("session_preview_failed", error=e))
            self._preview.setHtml("")
            self._table.setRowCount(0)
            self._entries = []
            self._owner._clear_live_preview_cache()
            self._load_pdf_limit_editor(None)
        finally:
            self._refresh_btn.setEnabled(True)

    def load_cached_or_refresh(self) -> None:
        if self._owner._live_preview_cache_is_current() and self._entries:
            self.sync_use_preview_checkbox()
            return
        if self._owner._live_preview_cache_is_current():
            cached = self._owner._live_preview_cache or {}
            if cached.get("selected_ids") is not None and cached.get("picked_meta") is not None:
                self.refresh_now()
                return
        self.refresh_now()


# ─── Phase funnel ─────────────────────────────────────────────────────────────

_PHASE_META = {
    "content_types": {
        "label_id": "session_phase_content_types",
        "icon":  "📄",
        "color": "#e07b39",
        "desc_id":  "session_phase_content_types_hint",
    },
    "tags": {
        "label_id": "session_phase_tags",
        "icon":  "🏷",
        "color": "#8e44ad",
        "desc_id":  "session_phase_tags_hint",
    },
    "type": {
        "label_id": "session_phase_card_type",
        "icon":  "📊",
        "color": "#2980b9",
        "desc_id":  "session_phase_card_type_hint",
    },
    "mode": {
        "label_id": "session_phase_selection_mode",
        "icon":  "🎲",
        "color": "#27ae60",
        "desc_id":  "session_phase_selection_mode_hint",
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
        title = QLabel(t(_PHASE_META[phase_id]["label_id"]))
        title.setStyleSheet("font-weight: bold; font-size: 12px;")
        desc = QLabel(t(_PHASE_META[phase_id]["desc_id"]))
        desc.setStyleSheet("color: palette(mid); font-size: 11px;")
        text_col.addWidget(title)
        text_col.addWidget(desc)
        row.addWidget(text_w, 1)

        self._cb = QCheckBox()
        self._cb.setChecked(enabled)
        self._cb.setToolTip(t("session_phase_enabled_tooltip"))
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
        ft = QLabel(t("session_fill_remaining"))
        ft.setStyleSheet("font-weight: bold; font-size: 12px;")
        fd = QLabel(t("session_fill_remaining_hint"))
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
        self._on_changed = None

    # ── Public API ────────────────────────────────────────────────────────────

    def add_phase(self, phase_id: str, enabled: bool = True) -> _PhaseCard:
        card = _PhaseCard(phase_id, enabled, self._container)
        self._handle_map[id(card._handle)] = card
        card._handle.installEventFilter(self._ev)
        qconnect(card._cb.stateChanged, lambda _: self._emit_changed())
        self._cards.append(card)
        self._rebuild()
        return card

    def set_on_changed(self, callback) -> None:
        self._on_changed = callback

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
        self._emit_changed()

    def get_order(self) -> list[str]:
        return [c.phase_id for c in self._cards]

    def get_enabled(self) -> dict[str, bool]:
        return {c.phase_id: c.is_enabled for c in self._cards}

    def _emit_changed(self) -> None:
        if callable(self._on_changed):
            self._on_changed()

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
                self._emit_changed()
            card._apply_style(dragging=False)
            self._ind.hide()
        self._drag_card = None
        self._drag_active = False


# ─── End funnel ───────────────────────────────────────────────────────────────

def _day_end_presets() -> list[tuple[str | None, str]]:
    return [
        ("00:00", t("session_day_end_midnight")),
        ("01:00", t("session_day_end_one_am")),
        ("02:00", t("session_day_end_two_am")),
        ("03:00", t("session_day_end_three_am")),
        ("04:00", t("session_day_end_four_am")),
        ("05:00", t("session_day_end_five_am")),
        ("06:00", t("session_day_end_six_am")),
        (None, t("common_custom")),
    ]

def _priority_dims() -> list[tuple[str, str]]:
    return [
        ("tags", t("session_priority_dimension_tags")),
        ("type", t("session_priority_dimension_type")),
        ("mode", t("session_priority_dimension_mode")),
    ]

_DEFAULT_MAIN_GROUPS = {
    "topics": "topics",
    "pdf": "pdf",
    "priority": "priority",
}


def _keep_button_label_readable(button: QPushButton) -> None:
    """Respect the active Qt style's font and padding instead of a fixed width."""
    natural_width = int(button.sizeHint().width())
    if natural_width > 0:
        button.setMinimumWidth(natural_width)


class SchedulerConfigDialog(QDialog):
    _CURRENT_SETTINGS_LABEL = "Current Settings"

    @staticmethod
    def _current_settings_display() -> str:
        """Present the stable no-preset sentinel without using it as identity."""
        return t("session_current_settings")

    def __init__(self, parent=None, on_clear_session=None, branch_scope: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle(t("session_scheduler_settings_title"))
        self.setMinimumWidth(520)
        self._linked_rows: list[dict] = []
        self._updating = False
        self._on_clear_session = on_clear_session
        self._branch_scope = _normalize_branch_scope(branch_scope)
        self._branch_clause = _cid_clause(
            list((self._branch_scope or {}).get("card_ids") or [])
        )
        self._live_preview_dialog: _LiveSchedulerPreviewDialog | None = None
        self._live_preview_cache: dict | None = None
        self._live_preview_signature: str | None = None
        self._preview_refresh_timer = QTimer(self)
        self._preview_refresh_timer.setSingleShot(True)
        self._preview_refresh_timer.setInterval(180)
        qconnect(self._preview_refresh_timer.timeout, self._refresh_live_preview_if_open)
        config = load_addon_config(mw.addonManager, _ADDON_PKG)
        self._profiles: dict[str, dict] = config.get("scheduler_presets", {})
        self._selected_profile_name = _normalize_selected_scheduler_profile(
            (config.get("dialog", {}) or {}).get("selected_profile"),
            self._profiles,
        )
        self._saved = _initial_scheduler_dialog_state(
            config.get("dialog", {}),
            self._profiles,
            self._selected_profile_name,
        )
        self._saved_priority_order_map = self._priority_order_map_from_dict(self._saved)
        self._use_live_preview_enabled = bool(self._saved.get("use_live_preview", False))
        self._pdf_limit_targets: list[dict] = []
        self._pdf_limit_main_loading = False
        self._setup_ui()
        self._refresh_pdf_limit_targets()
        self._apply_initial_size()

    def _apply_initial_size(self) -> None:
        """Open at about 2x area of the natural layout size to reduce manual resizing."""
        hint = self.sizeHint()
        if hint.width() <= 0 or hint.height() <= 0:
            return

        linear_scale = math.sqrt(2.0)  # ~2x area while keeping aspect ratio
        target_w = max(820, int(round(hint.width() * linear_scale)))
        target_h = max(680, int(round(hint.height() * linear_scale)))

        screen = self.screen()
        if screen is not None:
            avail = screen.availableGeometry()
            target_w = min(target_w, max(640, int(avail.width() * 0.95)))
            target_h = min(target_h, max(520, int(avail.height() * 0.95)))

        self.resize(target_w, target_h)

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
        _scroll_layout = QVBoxLayout(_scroll_content)
        _scroll_layout.setContentsMargins(12, 12, 12, 12)
        _scroll_layout.setSpacing(8)

        setup_mode_row = QHBoxLayout()
        setup_mode_label = QLabel(t("session_setup_view"))
        setup_mode_label.setAccessibleName(t("session_setup_view_accessible"))
        setup_mode_row.addWidget(setup_mode_label)
        self._basic_mode_button = QPushButton(t("session_basic"))
        self._basic_mode_button.setCheckable(True)
        self._basic_mode_button.setAccessibleName(t("session_basic_accessible"))
        setup_mode_row.addWidget(self._basic_mode_button)
        self._advanced_mode_button = QPushButton(t("session_advanced"))
        self._advanced_mode_button.setCheckable(True)
        self._advanced_mode_button.setAccessibleName(t("session_advanced_accessible"))
        setup_mode_row.addWidget(self._advanced_mode_button)
        setup_mode_row.addStretch(1)
        _scroll_layout.addLayout(setup_mode_row)

        self._basic_panel = QWidget()
        self._basic_layout = QVBoxLayout(self._basic_panel)
        self._basic_layout.setContentsMargins(0, 4, 0, 8)
        self._basic_layout.setSpacing(10)
        _scroll_layout.addWidget(self._basic_panel)

        self._advanced_panel = QWidget()
        layout = QVBoxLayout(self._advanced_panel)
        layout.setContentsMargins(0, 4, 0, 8)
        layout.setSpacing(8)
        _scroll_layout.addWidget(self._advanced_panel)

        intro = QLabel(t("session_intro"))
        intro.setWordWrap(True)
        intro.setStyleSheet("color: gray;")
        layout.addWidget(intro)

        if self._branch_scope:
            branch_card = QFrame()
            branch_card.setStyleSheet(
                "QFrame {"
                "  background: rgba(74,122,181,0.08);"
                "  border: 1px solid rgba(74,122,181,0.25);"
                "  border-radius: 8px;"
                "}"
            )
            branch_layout = QVBoxLayout(branch_card)
            branch_layout.setContentsMargins(10, 8, 10, 8)
            branch_layout.setSpacing(4)

            branch_title = QLabel(
                t("session_branch_study", title=self._branch_scope_label())
            )
            branch_title.setStyleSheet("font-weight: bold; color: #4a7ab5;")
            branch_layout.addWidget(branch_title)

            branch_note = QLabel(t("session_branch_study_note"))
            branch_note.setWordWrap(True)
            branch_note.setStyleSheet("color: gray;")
            branch_layout.addWidget(branch_note)
            layout.addWidget(branch_card)

        # -- Profiles --
        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel(t("session_preset")))
        self._profile_combo = QComboBox()
        self._profile_combo.setMinimumWidth(160)
        self._profile_combo.setToolTip(
            t("session_preset_tooltip")
        )
        qconnect(self._profile_combo.currentIndexChanged, self._on_profile_combo_changed)
        profile_row.addWidget(self._profile_combo)

        self._profile_load_btn = QPushButton(t("common_load"))
        _keep_button_label_readable(self._profile_load_btn)
        self._profile_load_btn.setToolTip(t("session_load_preset_tooltip"))
        qconnect(self._profile_load_btn.clicked, self._load_profile)
        profile_row.addWidget(self._profile_load_btn)

        self._profile_save_btn = QPushButton(t("common_save"))
        _keep_button_label_readable(self._profile_save_btn)
        self._profile_save_btn.setToolTip(t("session_save_preset_tooltip"))
        qconnect(self._profile_save_btn.clicked, self._save_profile)
        profile_row.addWidget(self._profile_save_btn)

        add_btn = QPushButton(t("common_add"))
        _keep_button_label_readable(add_btn)
        add_btn.setToolTip(t("session_add_preset_tooltip"))
        qconnect(add_btn.clicked, self._add_profile)
        profile_row.addWidget(add_btn)

        self._profile_rename_btn = QPushButton(t("common_rename"))
        _keep_button_label_readable(self._profile_rename_btn)
        self._profile_rename_btn.setToolTip(t("session_rename_preset_tooltip"))
        qconnect(self._profile_rename_btn.clicked, self._rename_profile)
        profile_row.addWidget(self._profile_rename_btn)

        self._profile_delete_btn = QPushButton(t("common_delete"))
        _keep_button_label_readable(self._profile_delete_btn)
        self._profile_delete_btn.setToolTip(t("session_delete_preset_tooltip"))
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
        count_row.addWidget(QLabel(t("session_cards_per_session")))
        self._count_spin = QSpinBox()
        self._count_spin.setRange(1, MAX_SESSION_CARD_COUNT)
        self._count_spin.setValue(self._saved.get("session_card_count", 50))
        count_row.addWidget(self._count_spin)
        count_row.addWidget(_info_icon(
            t("session_cards_per_session_tooltip")
        ))
        count_row.addStretch()
        layout.addLayout(count_row)

        # ── 2. Card type filter ───────────────────────────────────────────────
        card_types_row = QHBoxLayout()
        card_types_row.addWidget(QLabel(t("session_card_types")))
        self._cb_new = QCheckBox(t("session_card_type_new"))
        self._cb_new.setToolTip(t("session_card_type_new_tooltip"))
        self._cb_new.setChecked(self._saved.get("include_new", True))
        card_types_row.addWidget(self._cb_new)
        self._cb_learning = QCheckBox(t("session_card_type_learning"))
        self._cb_learning.setToolTip(t("session_card_type_learning_tooltip"))
        self._cb_learning.setChecked(self._saved.get("include_learning", True))
        card_types_row.addWidget(self._cb_learning)
        self._cb_due = QCheckBox(t("session_card_type_due"))
        self._cb_due.setToolTip(t("session_card_type_due_tooltip"))
        self._cb_due.setChecked(self._saved.get("include_due", True))
        card_types_row.addWidget(self._cb_due)
        card_types_row.addWidget(_info_icon(
            t("session_card_types_help")
        ))
        card_types_row.addStretch()
        layout.addLayout(card_types_row)

        # ── 3. Topics / Items ratio ───────────────────────────────────────────
        topics_val = self._saved.get("topics_slider", 10)
        main_locks = self._saved.get("main_locks", {}) or {}
        main_groups = self._saved.get("main_groups", {}) or {}
        if (
            self._normalize_group_name(str(main_groups.get("topics", ""))) == "topics_pdf"
            and self._normalize_group_name(str(main_groups.get("pdf", ""))) == "topics_pdf"
        ):
            main_groups = dict(main_groups)
            main_groups["topics"] = _DEFAULT_MAIN_GROUPS["topics"]
            main_groups["pdf"] = _DEFAULT_MAIN_GROUPS["pdf"]
        topics_row = QHBoxLayout()
        self._topics_left_lbl = QLabel(t("session_percent", value=100 - topics_val))
        self._topics_left_lbl.setFixedWidth(36)
        topics_row.addWidget(self._topics_left_lbl)
        _lbl_topics = QLabel(t("session_topics"))
        _lbl_topics.setToolTip(t("session_topics_tooltip"))
        topics_row.addWidget(_lbl_topics)
        self._topics_slider = QSlider(Qt.Orientation.Horizontal)
        self._topics_slider.setRange(0, 100)
        self._topics_slider.setValue(topics_val)
        topics_row.addWidget(self._topics_slider)
        _lbl_items = QLabel(t("session_items"))
        _lbl_items.setToolTip(t("session_items_tooltip"))
        topics_row.addWidget(_lbl_items)
        self._topics_right_lbl = QLabel(t("session_percent", value=topics_val))
        self._topics_right_lbl.setFixedWidth(36)
        topics_row.addWidget(self._topics_right_lbl)
        self._topics_lock_cb = QCheckBox("🔒")
        self._topics_lock_cb.setChecked(bool(main_locks.get("topics", False)))
        self._topics_lock_cb.setToolTip(
            t("session_lock_topics_tooltip")
        )
        self._topics_lock_cb.setFixedWidth(48)
        topics_row.addWidget(self._topics_lock_cb)
        topics_row.addWidget(QLabel(t("session_group")))
        self._topics_group_edit = QLineEdit(str(main_groups.get("topics", _DEFAULT_MAIN_GROUPS["topics"])))
        self._topics_group_edit.setFixedWidth(90)
        self._topics_group_edit.setToolTip(t("session_group_tooltip"))
        topics_row.addWidget(self._topics_group_edit)
        topics_row.addWidget(_info_icon(
            t("session_topics_ratio_help")
        ))
        layout.addLayout(topics_row)

        self._counts_lbl = QLabel("")
        layout.addWidget(self._counts_lbl)

        pdf_limit_card = QFrame()
        pdf_limit_card.setStyleSheet(
            "QFrame {"
            "  background: rgba(74,122,181,0.06);"
            "  border: 1px solid rgba(74,122,181,0.20);"
            "  border-radius: 8px;"
            "}"
        )
        pdf_limit_layout = QVBoxLayout(pdf_limit_card)
        pdf_limit_layout.setContentsMargins(10, 8, 10, 8)
        pdf_limit_layout.setSpacing(6)

        pdf_limit_header = QLabel(t("session_pdf_daily_limit"))
        pdf_limit_header.setStyleSheet("font-weight: bold; color: #4a7ab5;")
        pdf_limit_layout.addWidget(pdf_limit_header)

        pdf_limit_intro = QLabel(t("session_pdf_limit_intro"))
        pdf_limit_intro.setWordWrap(True)
        pdf_limit_intro.setStyleSheet("color: gray;")
        pdf_limit_layout.addWidget(pdf_limit_intro)

        pdf_limit_pick_row = QHBoxLayout()
        pdf_limit_pick_row.addWidget(QLabel(t("session_find_pdf")))
        self._pdf_limit_search_edit = QLineEdit()
        self._pdf_limit_search_edit.setPlaceholderText(t("session_search_pdf_title"))
        pdf_limit_pick_row.addWidget(self._pdf_limit_search_edit, 1)
        pdf_limit_pick_row.addWidget(QLabel(t("session_pdf")))
        self._pdf_limit_combo = QComboBox()
        self._pdf_limit_combo.setMinimumWidth(280)
        pdf_limit_pick_row.addWidget(self._pdf_limit_combo, 2)
        self._pdf_limit_refresh_btn = QPushButton(t("session_refresh_pdfs"))
        pdf_limit_pick_row.addWidget(self._pdf_limit_refresh_btn)
        pdf_limit_layout.addLayout(pdf_limit_pick_row)

        pdf_limit_form_row = QHBoxLayout()
        self._pdf_limit_main_enabled = QCheckBox(t("session_enable"))
        pdf_limit_form_row.addWidget(self._pdf_limit_main_enabled)
        self._pdf_limit_main_spin = QSpinBox()
        self._pdf_limit_main_spin.setRange(1, 5000)
        self._pdf_limit_main_spin.setValue(10)
        self._pdf_limit_main_spin.setFixedWidth(90)
        pdf_limit_form_row.addWidget(self._pdf_limit_main_spin)
        pdf_limit_form_row.addWidget(QLabel(t("session_pages_per_day")))
        self._pdf_limit_main_mode = QComboBox()
        self._pdf_limit_main_mode.addItem(t("session_pdf_limit_warning"), "warning")
        self._pdf_limit_main_mode.addItem(t("session_pdf_limit_soft_lock"), "soft_lock")
        self._pdf_limit_main_mode.addItem(t("session_pdf_limit_hard_stop"), "hard_stop")
        pdf_limit_form_row.addWidget(self._pdf_limit_main_mode)
        self._pdf_limit_main_save_btn = QPushButton(t("session_save_pdf_limit"))
        pdf_limit_form_row.addWidget(self._pdf_limit_main_save_btn)
        pdf_limit_form_row.addStretch()
        pdf_limit_layout.addLayout(pdf_limit_form_row)

        self._pdf_limit_main_status_lbl = QLabel("")
        self._pdf_limit_main_status_lbl.setWordWrap(True)
        self._pdf_limit_main_status_lbl.setStyleSheet("color: gray; font-size: 11px;")
        pdf_limit_layout.addWidget(self._pdf_limit_main_status_lbl)

        # ── 5. PDF soft-mix rate ──────────────────────────────────────────────
        pdf_val = self._saved.get("pdf_slider", 100)
        pdf_row = QHBoxLayout()
        self._pdf_left_lbl = QLabel(t("session_percent", value=100 - pdf_val))
        self._pdf_left_lbl.setFixedWidth(36)
        pdf_row.addWidget(self._pdf_left_lbl)
        _lbl_pdf = QLabel(t("session_documents"))
        _lbl_pdf.setToolTip(t("session_documents_tooltip"))
        pdf_row.addWidget(_lbl_pdf)
        self._pdf_slider = QSlider(Qt.Orientation.Horizontal)
        self._pdf_slider.setRange(0, 100)
        self._pdf_slider.setValue(pdf_val)
        pdf_row.addWidget(self._pdf_slider)
        _lbl_other = QLabel(t("session_other"))
        _lbl_other.setToolTip(t("session_other_tooltip"))
        pdf_row.addWidget(_lbl_other)
        self._pdf_right_lbl = QLabel(t("session_percent", value=pdf_val))
        self._pdf_right_lbl.setFixedWidth(36)
        pdf_row.addWidget(self._pdf_right_lbl)
        self._pdf_lock_cb = QCheckBox("🔒")
        self._pdf_lock_cb.setChecked(bool(main_locks.get("pdf", False)))
        self._pdf_lock_cb.setToolTip(
            t("session_lock_pdf_tooltip")
        )
        self._pdf_lock_cb.setFixedWidth(48)
        pdf_row.addWidget(self._pdf_lock_cb)
        pdf_row.addWidget(QLabel(t("session_group")))
        self._pdf_group_edit = QLineEdit(str(main_groups.get("pdf", _DEFAULT_MAIN_GROUPS["pdf"])))
        self._pdf_group_edit.setFixedWidth(90)
        self._pdf_group_edit.setToolTip(t("session_group_tooltip"))
        pdf_row.addWidget(self._pdf_group_edit)
        pdf_row.addWidget(_info_icon(
            t("session_document_mix_help")
        ))
        layout.addLayout(pdf_row)

        qconnect(self._pdf_slider.valueChanged,
                 lambda v: (self._pdf_left_lbl.setText(t("session_percent", value=100 - v)),
                             self._pdf_right_lbl.setText(t("session_percent", value=v))))
        qconnect(self._pdf_limit_search_edit.textChanged, lambda _: self._refresh_pdf_limit_combo())
        qconnect(self._pdf_limit_combo.currentIndexChanged, lambda _: self._load_main_pdf_limit_editor())
        qconnect(self._pdf_limit_refresh_btn.clicked, self._refresh_pdf_limit_targets)
        qconnect(self._pdf_limit_main_enabled.toggled, self._on_main_pdf_limit_form_changed)
        qconnect(self._pdf_limit_main_spin.valueChanged, self._on_main_pdf_limit_form_changed)
        qconnect(self._pdf_limit_main_mode.currentIndexChanged, self._on_main_pdf_limit_form_changed)
        qconnect(self._pdf_limit_main_save_btn.clicked, self._save_main_pdf_limit)

        # ── 6. Priority / Random selection mode ───────────────────────────────
        random_val = self._saved.get("random_slider", 99)
        random_row = QHBoxLayout()
        self._random_left_lbl = QLabel(t("session_percent", value=100 - random_val))
        self._random_left_lbl.setFixedWidth(36)
        random_row.addWidget(self._random_left_lbl)
        _lbl_priority = QLabel(t("session_priority"))
        _lbl_priority.setToolTip(t("session_priority_tooltip"))
        random_row.addWidget(_lbl_priority)
        self._random_slider = QSlider(Qt.Orientation.Horizontal)
        self._random_slider.setRange(0, 100)
        self._random_slider.setValue(random_val)
        random_row.addWidget(self._random_slider)
        _lbl_random = QLabel(t("session_random"))
        _lbl_random.setToolTip(t("session_random_tooltip"))
        random_row.addWidget(_lbl_random)
        self._random_right_lbl = QLabel(t("session_percent", value=random_val))
        self._random_right_lbl.setFixedWidth(36)
        random_row.addWidget(self._random_right_lbl)
        self._priority_lock_cb = QCheckBox("🔒")
        self._priority_lock_cb.setChecked(bool(main_locks.get("priority", False)))
        self._priority_lock_cb.setToolTip(
            t("session_lock_priority_tooltip")
        )
        self._priority_lock_cb.setFixedWidth(48)
        random_row.addWidget(self._priority_lock_cb)
        random_row.addWidget(QLabel(t("session_group")))
        self._priority_group_edit = QLineEdit(str(main_groups.get("priority", _DEFAULT_MAIN_GROUPS["priority"])))
        self._priority_group_edit.setFixedWidth(90)
        self._priority_group_edit.setToolTip(t("session_group_tooltip"))
        random_row.addWidget(self._priority_group_edit)
        random_row.addWidget(_info_icon(
            t("session_selection_mode_help")
        ))
        layout.addLayout(random_row)

        self._axis_hint_lbl = QLabel(t("session_group_axis_hint"))
        self._axis_hint_lbl.setWordWrap(True)
        self._axis_hint_lbl.setStyleSheet("color: gray; font-size: small;")
        layout.addWidget(self._axis_hint_lbl)

        self._expected_mix_lbl = QLabel("")
        self._expected_mix_lbl.setWordWrap(True)
        self._expected_mix_lbl.setStyleSheet("color: #4a7ab5;")
        layout.addWidget(self._expected_mix_lbl)

        self._expected_counts_lbl = QLabel("")
        self._expected_counts_lbl.setWordWrap(True)
        self._expected_counts_lbl.setStyleSheet("color: gray; font-size: small;")
        layout.addWidget(self._expected_counts_lbl)

        self._tag_content_title_lbl = QLabel(t("session_tag_content_estimate"))
        self._tag_content_title_lbl.setStyleSheet("color: gray; font-size: small;")
        layout.addWidget(self._tag_content_title_lbl)
        self._tag_content_table = QTableWidget(0, 5)
        self._tag_content_table.setHorizontalHeaderLabels(
            [t("session_tag"), t("session_pdf"), t("session_topics"), t("session_items"), t("session_total")]
        )
        self._tag_content_table.verticalHeader().setVisible(False)
        self._tag_content_table.setAlternatingRowColors(True)
        self._tag_content_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tag_content_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._tag_content_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._tag_content_table.setMinimumHeight(112)
        self._tag_content_table.setMaximumHeight(220)
        _hdr = self._tag_content_table.horizontalHeader()
        _hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        _hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        _hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        _hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        _hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._tag_content_table)

        self._tag_content_note_lbl = QLabel("")
        self._tag_content_note_lbl.setWordWrap(True)
        self._tag_content_note_lbl.setStyleSheet("color: gray; font-size: small;")
        layout.addWidget(self._tag_content_note_lbl)

        _live_preview_row = QHBoxLayout()
        self._live_preview_btn = QPushButton(t("session_live_card_preview"))
        self._live_preview_btn.setToolTip(
            t("session_live_preview_button_tooltip")
        )
        qconnect(self._live_preview_btn.clicked, self._open_live_preview)
        _live_preview_row.addWidget(self._live_preview_btn)
        _live_preview_row.addStretch()
        layout.addLayout(_live_preview_row)

        self._live_preview_hint_lbl = QLabel(t("session_live_preview_hint"))
        self._live_preview_hint_lbl.setWordWrap(True)
        self._live_preview_hint_lbl.setStyleSheet("color: gray; font-size: small;")
        layout.addWidget(self._live_preview_hint_lbl)

        qconnect(self._topics_slider.valueChanged,
                 lambda v: (self._topics_left_lbl.setText(f"{100 - v}%"),
                             self._topics_right_lbl.setText(f"{v}%")))
        qconnect(self._random_slider.valueChanged,
                 lambda v: (self._random_left_lbl.setText(f"{100 - v}%"),
                             self._random_right_lbl.setText(f"{v}%")))
        qconnect(self._topics_slider.valueChanged, lambda _: self._on_main_slider_changed("topics"))
        qconnect(self._pdf_slider.valueChanged,    lambda _: self._on_main_slider_changed("pdf"))
        qconnect(self._random_slider.valueChanged, lambda _: self._on_main_slider_changed("priority"))
        qconnect(self._topics_lock_cb.stateChanged,   lambda _: self._on_main_lock_toggled("topics"))
        qconnect(self._pdf_lock_cb.stateChanged,      lambda _: self._on_main_lock_toggled("pdf"))
        qconnect(self._priority_lock_cb.stateChanged, lambda _: self._on_main_lock_toggled("priority"))
        qconnect(self._topics_group_edit.textChanged,   lambda _: self._on_main_group_changed())
        qconnect(self._pdf_group_edit.textChanged,      lambda _: self._on_main_group_changed())
        qconnect(self._priority_group_edit.textChanged, lambda _: self._on_main_group_changed())
        qconnect(self._count_spin.valueChanged, lambda _: self._refresh_expected_mix_preview())
        qconnect(self._topics_slider.valueChanged, lambda _: self._refresh_expected_mix_preview())
        qconnect(self._pdf_slider.valueChanged,    lambda _: self._refresh_expected_mix_preview())
        qconnect(self._random_slider.valueChanged, lambda _: self._refresh_expected_mix_preview())
        qconnect(self._cb_new.stateChanged,      lambda _: self._refresh_counts())
        qconnect(self._cb_learning.stateChanged, lambda _: self._refresh_counts())
        qconnect(self._cb_due.stateChanged,      lambda _: self._refresh_counts())
        qconnect(self._count_spin.valueChanged,   lambda _: self._schedule_live_preview_refresh())
        qconnect(self._topics_slider.valueChanged, lambda _: self._schedule_live_preview_refresh())
        qconnect(self._pdf_slider.valueChanged,    lambda _: self._schedule_live_preview_refresh())
        qconnect(self._random_slider.valueChanged, lambda _: self._schedule_live_preview_refresh())
        qconnect(self._cb_new.stateChanged,        lambda _: self._schedule_live_preview_refresh())
        qconnect(self._cb_learning.stateChanged,   lambda _: self._schedule_live_preview_refresh())
        qconnect(self._cb_due.stateChanged,        lambda _: self._schedule_live_preview_refresh())
        qconnect(self._topics_lock_cb.stateChanged,   lambda _: self._schedule_live_preview_refresh())
        qconnect(self._pdf_lock_cb.stateChanged,      lambda _: self._schedule_live_preview_refresh())
        qconnect(self._priority_lock_cb.stateChanged, lambda _: self._schedule_live_preview_refresh())
        qconnect(self._topics_group_edit.textChanged,   lambda _: self._schedule_live_preview_refresh())
        qconnect(self._pdf_group_edit.textChanged,      lambda _: self._schedule_live_preview_refresh())
        qconnect(self._priority_group_edit.textChanged, lambda _: self._schedule_live_preview_refresh())
        self._topics_slider.setEnabled(not self._topics_lock_cb.isChecked())
        self._pdf_slider.setEnabled(not self._pdf_lock_cb.isChecked())
        self._random_slider.setEnabled(not self._priority_lock_cb.isChecked())
        self._rebalance_main_pool(changed_key=None)
        self._refresh_expected_mix_preview()

        # ── 7. Scheduler scope ────────────────────────────────────────────────
        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel(t("session_scheduler_scope")))
        self._scope_combo = QComboBox()
        self._scope_combo.addItem(t("session_scope_this_session"), "session")
        self._scope_combo.addItem(t("session_scope_today"), "daily")
        self._scope_combo.addItem(t("session_scope_all_time"), "lifetime")
        saved_scope = self._saved.get("scheduler_scope", "session")
        for i in range(self._scope_combo.count()):
            if self._scope_combo.itemData(i) == saved_scope:
                self._scope_combo.setCurrentIndex(i)
                break
        scope_row.addWidget(self._scope_combo)
        scope_row.addWidget(_info_icon(
            t("session_scheduler_scope_help")
        ))

        self._day_end_label = QLabel(t("session_day_ends_at"))
        self._day_end_label.setToolTip(
            t("session_day_end_tooltip")
        )
        scope_row.addWidget(self._day_end_label)

        self._day_end_preset = QComboBox()
        self._day_end_preset.setToolTip(
            t("session_day_end_tooltip")
        )
        for value, label in _day_end_presets():
            self._day_end_preset.addItem(label, value)
        scope_row.addWidget(self._day_end_preset)

        self._day_end_edit = QTimeEdit()
        self._day_end_edit.setDisplayFormat("HH:mm")
        scope_row.addWidget(self._day_end_edit)

        scope_row.addStretch()
        layout.addLayout(scope_row)

        saved_time = self._saved.get("day_end_time", "04:00")
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
        qconnect(self._scope_combo.currentIndexChanged, lambda _: self._schedule_live_preview_refresh())
        qconnect(self._day_end_preset.currentIndexChanged, lambda _: self._schedule_live_preview_refresh())
        qconnect(self._day_end_edit.timeChanged, lambda _: self._schedule_live_preview_refresh())

        self._current_profile_tags = sorted(set(mw.col.tags.all()))
        self._current_profile_tags_map = {t.casefold(): t for t in self._current_profile_tags}

        # ── 8. Ordered priority pre-pass ─────────────────────────────────────
        priority_order_row = QHBoxLayout()
        self._priority_order_cb = QCheckBox(t("session_prioritize_order"))
        self._priority_order_cb.setChecked(bool(self._saved.get("priority_order_enabled", False)))
        if (
            "priority_order_enabled" not in self._saved
            and "priority_order_entries" not in self._saved
            and self._saved.get("prioritized_tags_first")
        ):
            self._priority_order_cb.setChecked(True)
        self._priority_order_cb.setToolTip(
            t("session_prioritize_order_tooltip")
        )
        priority_order_row.addWidget(self._priority_order_cb)
        priority_order_row.addWidget(_info_icon(
            t("session_priority_order_help")
        ))
        priority_order_row.addStretch()
        layout.addLayout(priority_order_row)
        qconnect(self._priority_order_cb.stateChanged, lambda _: self._sync_priority_order_visibility())
        qconnect(self._priority_order_cb.stateChanged, lambda _: self._schedule_live_preview_refresh())

        # ── 9. Tag quotas ─────────────────────────────────────────────────────
        _tag_hrow = QHBoxLayout()
        _tag_header = QLabel(t("session_tag_quotas"))
        _tag_header.setStyleSheet("font-weight: bold;")
        _tag_hrow.addWidget(_tag_header)
        _tag_hrow.addWidget(_info_icon(
            t("session_tag_quotas_help")
        ))
        _tag_hrow.addStretch()
        layout.addLayout(_tag_hrow)

        _tag_desc = QLabel(t("session_tag_quotas_summary"))
        _tag_desc.setWordWrap(True)
        _tag_desc.setStyleSheet("color: gray;")
        layout.addWidget(_tag_desc)

        add_tag_row = QHBoxLayout()
        self._tag_combo = QComboBox()
        self._tag_combo.addItems(self._current_profile_tags)
        add_tag_row.addWidget(self._tag_combo)
        add_btn = QPushButton(t("common_add"))
        qconnect(add_btn.clicked, lambda: self._add_tag_row(self._tag_combo.currentText(), group_name="tags"))
        qconnect(add_btn.clicked, lambda: self._schedule_live_preview_refresh())
        add_tag_row.addWidget(add_btn)
        layout.addLayout(add_tag_row)

        self._no_tags_cb = QCheckBox(t("session_include_other_cards"))
        self._no_tags_cb.setToolTip(
            t("session_include_other_cards_tooltip")
        )
        self._no_tags_cb.setChecked(self._saved.get("no_tags_checked", True))
        self._no_tags_cb.setEnabled(False)
        layout.addWidget(self._no_tags_cb)

        self._tags_container = QWidget()
        self._tags_layout = QVBoxLayout(self._tags_container)
        self._tags_layout.setContentsMargins(0, 0, 0, 0)
        self._tags_layout.setSpacing(2)
        layout.addWidget(self._tags_container)

        skipped_missing_tags = 0
        for entry in self._saved.get("tag_rows", []):
            tag = entry.get("tag")
            if self._resolve_tag_for_current_profile(tag) is None:
                skipped_missing_tags += 1
                continue
            self._add_tag_row(tag, entry.get("weight", 20),
                              locked=entry.get("locked", False),
                              group_name=entry.get("group", "tags"),
                              order=self._priority_order_for("tag", tag),
                              defer_finalize=True)
        self._ensure_other_tag_row(
            default_enabled=self._saved.get("no_tags_checked", True),
            defer_finalize=True,
        )
        self._finalize_tag_row_batch_restore()
        if skipped_missing_tags > 0:
            tooltip(tn("session_tag_rows_skipped", skipped_missing_tags))

        self._other_lbl = QLabel("")
        layout.addWidget(self._other_lbl)
        self._update_other_label()

        # ── 10. Scheduling funnel (collapsible) ───────────────────────────────
        _funnel_sep = QFrame()
        _funnel_sep.setFrameShape(QFrame.Shape.HLine)
        _funnel_sep.setStyleSheet("QFrame { color: rgba(128,128,128,0.25); }")
        layout.addWidget(_funnel_sep)

        _funnel_hrow = QHBoxLayout()
        _funnel_toggle = QPushButton(t("session_funnel_collapsed"))
        _funnel_toggle.setCheckable(True)
        _funnel_toggle.setChecked(False)
        _funnel_toggle.setFlat(True)
        _funnel_toggle.setStyleSheet(
            "QPushButton { font-weight: bold; text-align: left; padding: 4px 2px; border: none; }"
            "QPushButton:hover { color: palette(highlight); }"
        )
        _funnel_hrow.addWidget(_funnel_toggle)
        _funnel_hrow.addWidget(_info_icon(
            t("session_funnel_help")
        ))
        self._enforce_cb = QCheckBox(t("session_strict_enforcement"))
        self._enforce_cb.setToolTip(
            t("session_strict_enforcement_tooltip")
        )
        self._enforce_cb.setChecked(self._saved.get("enforce_priority", True))
        _funnel_hrow.addStretch()
        _funnel_hrow.addWidget(self._enforce_cb)
        layout.addLayout(_funnel_hrow)

        self._strict_mode_lbl = QLabel(t("session_strict_mode_warning"))
        self._strict_mode_lbl.setStyleSheet(
            "color: #8a4b00;"
            "background: rgba(255,180,0,0.12);"
            "border: 1px solid rgba(160,100,0,0.35);"
            "border-radius: 4px;"
            "padding: 5px 8px;"
            "font-size: 11px;"
        )
        self._strict_mode_lbl.setWordWrap(True)
        layout.addWidget(self._strict_mode_lbl)

        _funnel_body = QWidget()
        _funnel_body.setVisible(False)
        _funnel_body_layout = QVBoxLayout(_funnel_body)
        _funnel_body_layout.setContentsMargins(12, 0, 0, 8)
        _funnel_body_layout.setSpacing(6)

        # ── Content type priorities ────────────────────────────────────────────
        _ct_hrow = QHBoxLayout()
        _ct_header = QLabel(t("session_content_type_priorities"))
        _ct_header.setStyleSheet("font-weight: bold;")
        _ct_hrow.addWidget(_ct_header)
        _ct_hrow.addWidget(_info_icon(
            t("session_content_type_priorities_help")
        ))
        _ct_hrow.addStretch()
        _funnel_body_layout.addLayout(_ct_hrow)

        _ct_desc = QLabel(t("session_content_type_priorities_summary"))
        _ct_desc.setWordWrap(True)
        _ct_desc.setStyleSheet("color: gray;")
        _funnel_body_layout.addWidget(_ct_desc)

        _ct_tip = QLabel(t("session_content_type_priorities_tip"))
        _ct_tip.setWordWrap(True)
        _ct_tip.setStyleSheet("color: #4a7ab5; font-size: small; padding: 2px 0;")
        _funnel_body_layout.addWidget(_ct_tip)

        _ct_tips = {
            "pdf": t("session_content_pdf_help"),
            "youtube": t("session_content_video_help"),
            "webpage": t("session_content_webpage_help"),
        }
        ct_saved = {r["type"]: r for r in self._saved.get("content_type_rows", [])}
        self._ct_rows: list[dict] = []
        for ct_type, ct_label in [
            ("pdf", t("session_content_pdf")),
            ("youtube", t("session_content_video")),
            ("webpage", t("session_content_webpage")),
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
            ct_slider.setToolTip(t("session_content_type_weight_tooltip"))
            ct_layout.addWidget(ct_slider)

            ct_pct = QLabel(t("session_percent", value=ct_weight))
            ct_pct.setFixedWidth(36)
            ct_layout.addWidget(ct_pct)

            ct_count = QLabel("")
            ct_count.setStyleSheet("color: gray; font-size: small;")
            ct_layout.addWidget(ct_count)

            order_label = QLabel(t("session_order"))
            ct_layout.addWidget(order_label)
            order_edit = QLineEdit()
            order_edit.setFixedWidth(54)
            order_edit.setPlaceholderText(t("session_order_placeholder"))
            order_edit.setToolTip(t("session_order_tooltip"))
            self._set_order_edit_value(order_edit, self._priority_order_for("content_type", ct_type))
            ct_layout.addWidget(order_edit)

            ct_layout.addWidget(_info_icon(_ct_tips[ct_type]))
            _funnel_body_layout.addWidget(ct_widget)

            ct_row = {
                "type": ct_type,
                "cb": ct_cb,
                "slider": ct_slider,
                "pct_label": ct_pct,
                "count_label": ct_count,
                "order_label": order_label,
                "order_edit": order_edit,
            }
            self._ct_rows.append(ct_row)

            qconnect(ct_cb.stateChanged,
                     lambda _, r=ct_row: r["slider"].setEnabled(r["cb"].isChecked()))
            qconnect(ct_slider.valueChanged,
                     lambda v, r=ct_row: r["pct_label"].setText(t("session_percent", value=v)))
            qconnect(ct_cb.stateChanged, lambda _: self._schedule_live_preview_refresh())
            qconnect(ct_slider.valueChanged, lambda _: self._schedule_live_preview_refresh())
            qconnect(order_edit.textChanged, lambda _: self._schedule_live_preview_refresh())

        self._refresh_ct_counts()
        self._sync_priority_order_visibility()

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
        self._funnel.set_on_changed(self._schedule_live_preview_refresh)
        _funnel_body_layout.addWidget(self._funnel)

        # Soft-mode banner — shown below the funnel when strict enforcement is off
        self._soft_mode_lbl = QLabel(t("session_soft_mode_warning"))
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
            _funnel_toggle.setText(t("session_funnel_expanded") if checked else t("session_funnel_collapsed"))
            _funnel_body.setVisible(checked)
        qconnect(_funnel_toggle.toggled, _toggle_funnel)

        def _update_funnel_state():
            strict = self._enforce_cb.isChecked()
            self._funnel.setEnabled(strict)
            _eff = QGraphicsOpacityEffect(self._funnel)
            _eff.setOpacity(1.0 if strict else 0.35)
            self._funnel.setGraphicsEffect(_eff)
            self._strict_mode_lbl.setVisible(strict)
            self._soft_mode_lbl.setVisible(not strict)

        _update_funnel_state()
        qconnect(self._enforce_cb.stateChanged, lambda _: _update_funnel_state())
        qconnect(self._enforce_cb.stateChanged, lambda _: self._schedule_live_preview_refresh())

        # ── 11. Advanced (collapsible, starts collapsed) ──────────────────────
        _adv_sep = QFrame()
        _adv_sep.setFrameShape(QFrame.Shape.HLine)
        _adv_sep.setStyleSheet("QFrame { color: rgba(128,128,128,0.25); }")
        layout.addWidget(_adv_sep)

        _adv_toggle = QPushButton(t("session_advanced_collapsed"))
        _adv_toggle.setCheckable(True)
        _adv_toggle.setChecked(False)
        _adv_toggle.setFlat(True)
        _adv_toggle.setStyleSheet(
            "QPushButton { font-weight: bold; text-align: left; padding: 4px 2px; border: none; }"
            "QPushButton:hover { color: palette(highlight); }"
        )
        _adv_toggle_info = _info_icon(
            t("session_advanced_filters_help")
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
        _adv_body_layout.addWidget(pdf_limit_card)

        topics_filter_row = QHBoxLayout()
        topics_filter_row.addWidget(QLabel(t("session_topics_filter")))
        self._topics_filter_edit = QLineEdit()
        self._topics_filter_edit.setPlaceholderText(t("session_filter_placeholder"))
        self._topics_filter_edit.setToolTip(
            t("session_topics_filter_tooltip")
        )
        self._topics_filter_edit.setText(self._normalized_saved_filter("topics_filter"))
        topics_filter_row.addWidget(self._topics_filter_edit)
        test_topics_btn = QPushButton(t("common_test"))
        test_topics_btn.setFixedWidth(48)
        qconnect(test_topics_btn.clicked,
                 lambda: self._test_filter("topics", self._topics_filter_edit.text().strip()))
        topics_filter_row.addWidget(test_topics_btn)
        _adv_body_layout.addLayout(topics_filter_row)

        items_filter_row = QHBoxLayout()
        items_filter_row.addWidget(QLabel(t("session_items_filter")))
        self._items_filter_edit = QLineEdit()
        self._items_filter_edit.setPlaceholderText(t("session_filter_placeholder"))
        self._items_filter_edit.setToolTip(
            t("session_items_filter_tooltip")
        )
        self._items_filter_edit.setText(self._normalized_saved_filter("items_filter"))
        items_filter_row.addWidget(self._items_filter_edit)
        test_items_btn = QPushButton(t("common_test"))
        test_items_btn.setFixedWidth(48)
        qconnect(test_items_btn.clicked,
                 lambda: self._test_filter("items", self._items_filter_edit.text().strip()))
        items_filter_row.addWidget(test_items_btn)
        _adv_body_layout.addLayout(items_filter_row)

        self._preserve_order_cb = QCheckBox(t("session_present_scheduler_order"))
        self._preserve_order_cb.setToolTip(
            t("session_present_scheduler_order_tooltip")
        )
        self._preserve_order_cb.setChecked(self._saved.get("preserve_order", True))
        _adv_body_layout.addWidget(self._preserve_order_cb)

        self._auto_refill_session_cb = QCheckBox(
            t("session_auto_refill")
        )
        self._auto_refill_session_cb.setToolTip(
            t("session_auto_refill_tooltip")
        )
        self._auto_refill_session_cb.setChecked(self._saved.get("auto_refill_session", False))
        _adv_body_layout.addWidget(self._auto_refill_session_cb)

        self._allow_content_tag_fallback_cb = QCheckBox(
            t("session_allow_media_outside_tags")
        )
        self._allow_content_tag_fallback_cb.setToolTip(
            t("session_allow_media_outside_tags_tooltip")
        )
        self._allow_content_tag_fallback_cb.setChecked(
            bool(self._saved.get("allow_content_tag_fallback", False))
        )
        _adv_body_layout.addWidget(self._allow_content_tag_fallback_cb)

        self._show_debug_cb = QCheckBox(t("session_show_debug"))
        self._show_debug_cb.setChecked(self._saved.get("show_debug", False))
        _adv_body_layout.addWidget(self._show_debug_cb)

        layout.addWidget(_adv_body)

        def _toggle_adv(checked):
            _adv_toggle.setText(t("session_advanced_expanded") if checked else t("session_advanced_collapsed"))
            _adv_body.setVisible(checked)
        qconnect(_adv_toggle.toggled, _toggle_adv)

        qconnect(self._topics_filter_edit.textChanged, lambda _: self._refresh_counts())
        qconnect(self._items_filter_edit.textChanged,  lambda _: self._refresh_counts())
        qconnect(self._topics_filter_edit.textChanged, lambda _: self._schedule_live_preview_refresh())
        qconnect(self._items_filter_edit.textChanged,  lambda _: self._schedule_live_preview_refresh())
        qconnect(self._preserve_order_cb.stateChanged, lambda _: self._schedule_live_preview_refresh())
        qconnect(self._auto_refill_session_cb.stateChanged, lambda _: self._schedule_live_preview_refresh())
        qconnect(self._allow_content_tag_fallback_cb.stateChanged, lambda _: self._schedule_live_preview_refresh())

        self._refresh_counts()

        # ── Statistics history (collapsible, starts collapsed) ────────────────
        _stats_sep = QFrame()
        _stats_sep.setFrameShape(QFrame.Shape.HLine)
        _stats_sep.setStyleSheet("QFrame { color: rgba(128,128,128,0.25); }")
        layout.addWidget(_stats_sep)

        _stats_toggle = QPushButton(t("session_statistics_collapsed"))
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

        del_today_btn = QPushButton(t("session_delete_today"))
        del_today_btn.setToolTip(t("session_delete_today_tooltip"))
        del_today_btn.setStyleSheet("color: palette(text); opacity: 0.8;")
        qconnect(del_today_btn.clicked, self._delete_daily)
        stats_row.addWidget(del_today_btn)

        del_session_btn = QPushButton(t("session_delete_session"))
        del_session_btn.setToolTip(t("session_delete_session_tooltip"))
        del_session_btn.setStyleSheet("color: palette(text); opacity: 0.8;")
        qconnect(del_session_btn.clicked, self._delete_session)
        stats_row.addWidget(del_session_btn)

        del_lifetime_btn = QPushButton(t("session_delete_all_time"))
        del_lifetime_btn.setToolTip(t("session_delete_all_time_tooltip"))
        del_lifetime_btn.setStyleSheet("color: palette(text); opacity: 0.8;")
        qconnect(del_lifetime_btn.clicked, self._delete_lifetime)
        stats_row.addWidget(del_lifetime_btn)

        del_all_btn = QPushButton(t("session_delete_all_history"))
        del_all_btn.setToolTip(t("session_delete_all_history_tooltip"))
        del_all_btn.setStyleSheet("color: #c0392b; font-weight: bold;")
        qconnect(del_all_btn.clicked, self._delete_all)
        stats_row.addWidget(del_all_btn)

        stats_row.addStretch()

        export_btn = QPushButton(t("session_export_json"))
        export_btn.setToolTip(t("session_export_json_tooltip"))
        qconnect(export_btn.clicked, self._export_json)
        stats_row.addWidget(export_btn)

        _stats_body_layout.addLayout(stats_row)
        layout.addWidget(_stats_body)

        def _toggle_stats(checked):
            _stats_toggle.setText(t("session_statistics_expanded") if checked else t("session_statistics_collapsed"))
            _stats_body.setVisible(checked)
        qconnect(_stats_toggle.toggled, _toggle_stats)

        self._populate_basic_panel()
        qconnect(
            self._basic_mode_button.clicked,
            lambda checked=False: checked and self._set_setup_mode(BASIC_MODE),
        )
        qconnect(
            self._advanced_mode_button.clicked,
            lambda checked=False: checked and self._set_setup_mode(ADVANCED_MODE),
        )
        self._set_setup_mode(self._saved.get("setup_mode", BASIC_MODE))

        # -- OK / Cancel (pinned outside scroll area) --
        _btn_sep = QFrame()
        _btn_sep.setFrameShape(QFrame.Shape.HLine)
        _btn_sep.setStyleSheet("QFrame { color: rgba(128,128,128,0.35); }")
        main_layout.addWidget(_btn_sep)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText(t("common_ok"))
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText(t("common_cancel"))
        btn_box.setContentsMargins(12, 4, 12, 4)
        qconnect(btn_box.accepted, self.accept)
        qconnect(btn_box.rejected, self.reject)
        main_layout.addWidget(btn_box)

    def _basic_summary_text(self) -> str:
        return format_basic_session_summary(
            session_card_count=self._count_spin.value(),
            topics_slider=self._topics_slider.value(),
            pdf_slider=self._pdf_slider.value(),
            preset_name=self.selected_dialog_profile_name(),
        )

    def _set_setup_mode(self, mode: str) -> None:
        resolved = normalize_setup_mode(mode)
        self._setup_mode = resolved
        is_basic = resolved == BASIC_MODE
        self._basic_panel.setVisible(is_basic)
        self._advanced_panel.setVisible(not is_basic)
        for button, checked in (
            (self._basic_mode_button, is_basic),
            (self._advanced_mode_button, not is_basic),
        ):
            button.blockSignals(True)
            button.setChecked(checked)
            button.blockSignals(False)
        if is_basic:
            self._sync_basic_controls_from_advanced()

    def _populate_basic_panel(self) -> None:
        intro = QLabel(t("session_basic_intro"))
        intro.setWordWrap(True)
        intro.setAccessibleName(t("session_basic_help_accessible"))
        self._basic_layout.addWidget(intro)

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel(t("session_preset")))
        self._basic_profile_combo = QComboBox()
        self._basic_profile_combo.setAccessibleName(t("session_preset_accessible"))
        self._basic_profile_combo.setMinimumWidth(220)
        profile_row.addWidget(self._basic_profile_combo, 1)
        profile_row.addStretch(1)
        self._basic_layout.addLayout(profile_row)

        count_row = QHBoxLayout()
        count_row.addWidget(QLabel(t("session_cards_per_session")))
        self._basic_count_spin = QSpinBox()
        self._basic_count_spin.setRange(1, MAX_SESSION_CARD_COUNT)
        self._basic_count_spin.setAccessibleName(t("session_cards_per_session_accessible"))
        count_row.addWidget(self._basic_count_spin)
        count_row.addStretch(1)
        self._basic_layout.addLayout(count_row)

        topics_row = QHBoxLayout()
        topics_row.addWidget(QLabel(t("session_topics")))
        self._basic_topics_left_label = QLabel("")
        self._basic_topics_left_label.setFixedWidth(42)
        topics_row.addWidget(self._basic_topics_left_label)
        self._basic_topics_slider = QSlider(Qt.Orientation.Horizontal)
        self._basic_topics_slider.setRange(0, 100)
        self._basic_topics_slider.setAccessibleName(t("session_topics_items_mix_accessible"))
        topics_row.addWidget(self._basic_topics_slider, 1)
        self._basic_topics_right_label = QLabel("")
        self._basic_topics_right_label.setFixedWidth(42)
        topics_row.addWidget(self._basic_topics_right_label)
        topics_row.addWidget(QLabel(t("session_items")))
        self._basic_layout.addLayout(topics_row)

        docs_row = QHBoxLayout()
        docs_row.addWidget(QLabel(t("session_documents")))
        self._basic_docs_left_label = QLabel("")
        self._basic_docs_left_label.setFixedWidth(42)
        docs_row.addWidget(self._basic_docs_left_label)
        self._basic_docs_slider = QSlider(Qt.Orientation.Horizontal)
        self._basic_docs_slider.setRange(0, 100)
        self._basic_docs_slider.setAccessibleName(t("session_documents_other_mix_accessible"))
        docs_row.addWidget(self._basic_docs_slider, 1)
        self._basic_docs_right_label = QLabel("")
        self._basic_docs_right_label.setFixedWidth(42)
        docs_row.addWidget(self._basic_docs_right_label)
        docs_row.addWidget(QLabel(t("session_other")))
        self._basic_layout.addLayout(docs_row)

        self._basic_summary_label = QLabel("")
        self._basic_summary_label.setWordWrap(True)
        self._basic_summary_label.setAccessibleName(t("session_summary_accessible"))
        self._basic_summary_label.setStyleSheet(
            "font-weight: bold; padding: 10px; "
            "background: rgba(74,122,181,0.10); "
            "border: 1px solid rgba(74,122,181,0.30); border-radius: 7px;"
        )
        self._basic_layout.addWidget(self._basic_summary_label)

        preview_row = QHBoxLayout()
        preview_row.addStretch(1)
        preview_button = QPushButton(t("session_preview_selected_cards"))
        preview_button.setAccessibleName(t("session_preview_selected_cards_accessible"))
        qconnect(preview_button.clicked, self._open_live_preview)
        preview_row.addWidget(preview_button)
        self._basic_layout.addLayout(preview_row)
        self._basic_layout.addStretch(1)

        qconnect(self._basic_profile_combo.currentIndexChanged, self._on_basic_profile_changed)
        qconnect(
            self._basic_count_spin.valueChanged,
            lambda value: self._count_spin.setValue(value),
        )
        qconnect(
            self._basic_topics_slider.valueChanged,
            lambda value: self._topics_slider.setValue(value),
        )
        qconnect(
            self._basic_docs_slider.valueChanged,
            lambda value: self._pdf_slider.setValue(value),
        )
        for widget in (self._count_spin, self._topics_slider, self._pdf_slider):
            qconnect(widget.valueChanged, lambda _value: self._sync_basic_controls_from_advanced())

        self._refresh_basic_profile_combo()
        self._sync_basic_controls_from_advanced()

    def _refresh_basic_profile_combo(self) -> None:
        combo = getattr(self, "_basic_profile_combo", None)
        if combo is None:
            return
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(self._current_settings_display(), None)
        for name in sorted(self._profiles.keys()):
            combo.addItem(name, name)
        selected_name = self.selected_dialog_profile_name()
        if selected_name:
            index = combo.findText(selected_name)
            combo.setCurrentIndex(max(0, index))
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _on_basic_profile_changed(self, _index: int) -> None:
        name = _normalize_selected_scheduler_profile(
            self._basic_profile_combo.currentData()
            or self._basic_profile_combo.currentText(),
            self._profiles,
        )
        self._selected_profile_name = name
        advanced_index = self._profile_combo.findText(
            name or self._current_settings_display()
        )
        self._profile_combo.blockSignals(True)
        self._profile_combo.setCurrentIndex(max(0, advanced_index))
        self._profile_combo.blockSignals(False)
        self._sync_profile_button_state()
        if name:
            self._load_profile_dict(self._profiles[name])
            self.save_config()
        self._sync_basic_controls_from_advanced()

    @staticmethod
    def _set_widget_value_without_signal(widget, value) -> None:
        widget.blockSignals(True)
        widget.setValue(value)
        widget.blockSignals(False)

    def _sync_basic_controls_from_advanced(self) -> None:
        if not hasattr(self, "_basic_count_spin"):
            return
        self._set_widget_value_without_signal(
            self._basic_count_spin,
            self._count_spin.value(),
        )
        topics_value = self._topics_slider.value()
        self._set_widget_value_without_signal(self._basic_topics_slider, topics_value)
        self._basic_topics_left_label.setText(t("session_percent", value=100 - topics_value))
        self._basic_topics_right_label.setText(t("session_percent", value=topics_value))
        docs_value = self._pdf_slider.value()
        self._set_widget_value_without_signal(self._basic_docs_slider, docs_value)
        self._basic_docs_left_label.setText(t("session_percent", value=100 - docs_value))
        self._basic_docs_right_label.setText(t("session_percent", value=docs_value))
        self._basic_summary_label.setText(self._basic_summary_text())

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

    def _resolve_tag_for_current_profile(self, tag: str) -> str | None:
        """Return canonical tag name for current profile, or None if missing."""
        raw = str(tag or "").strip()
        if not raw:
            return None
        if raw == NO_TAGS_KEY:
            return NO_TAGS_KEY

        current_tags = getattr(self, "_current_profile_tags", None)
        if current_tags is None:
            current_tags = sorted(set(mw.col.tags.all()))
            self._current_profile_tags = current_tags
            self._current_profile_tags_map = {t.casefold(): t for t in current_tags}

        tag_map = getattr(self, "_current_profile_tags_map", {})
        return tag_map.get(raw.casefold())

    @staticmethod
    def _tag_display_name(tag: str) -> str:
        return "Other" if tag == NO_TAGS_KEY else tag

    @staticmethod
    def _parse_order_value(value) -> int | None:
        try:
            order = int(str(value or "").strip())
        except Exception:
            return None
        if order <= 0:
            return None
        return order

    @classmethod
    def _priority_order_map_from_dict(cls, d: dict) -> dict[tuple[str, str], int]:
        result: dict[tuple[str, str], int] = {}
        if not isinstance(d, dict):
            return result

        if isinstance(d.get("priority_order_entries"), list):
            for entry in d.get("priority_order_entries") or []:
                if not isinstance(entry, dict):
                    continue
                kind = str(entry.get("kind") or "").strip()
                value = str(entry.get("value") or "").strip()
                order = cls._parse_order_value(entry.get("order"))
                if order is None:
                    continue
                if kind == "tag":
                    if not value or value == NO_TAGS_KEY:
                        continue
                    key_value = value.casefold()
                elif kind == "content_type":
                    value = value.lower()
                    if value not in {"pdf", "youtube", "webpage"}:
                        continue
                    key_value = value
                else:
                    continue
                result.setdefault((kind, key_value), order)
            return result

        row_has_order = False
        for row in d.get("tag_rows", []) or []:
            if not isinstance(row, dict) or "order" not in row:
                continue
            row_has_order = True
            tag = str(row.get("tag") or "").strip()
            order = cls._parse_order_value(row.get("order"))
            if tag and tag != NO_TAGS_KEY and order is not None:
                result.setdefault(("tag", tag.casefold()), order)
        for row in d.get("content_type_rows", []) or []:
            if not isinstance(row, dict) or "order" not in row:
                continue
            row_has_order = True
            ct = str(row.get("type") or "").strip().lower()
            order = cls._parse_order_value(row.get("order"))
            if ct in {"pdf", "youtube", "webpage"} and order is not None:
                result.setdefault(("content_type", ct), order)

        if not row_has_order and "priority_order_enabled" not in d:
            for idx, raw_tag in enumerate(d.get("prioritized_tags_first", []) or []):
                tag = str(raw_tag or "").strip()
                if tag and tag != NO_TAGS_KEY:
                    result.setdefault(("tag", tag.casefold()), idx + 1)
        return result

    def _priority_order_for(self, kind: str, value: str) -> int | None:
        key_value = str(value or "").strip()
        if kind == "tag":
            key_value = key_value.casefold()
        elif kind == "content_type":
            key_value = key_value.lower()
        return getattr(self, "_saved_priority_order_map", {}).get((kind, key_value))

    @staticmethod
    def _set_order_edit_value(edit: QLineEdit | None, order: int | None) -> None:
        if edit is None:
            return
        edit.setText("" if order is None else str(order))

    def _current_priority_order_entries(self) -> list[dict]:
        entries: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for row in getattr(self, "_linked_rows", []):
            tag = str(row.get("tag") or "")
            if tag == NO_TAGS_KEY:
                continue
            order = self._parse_order_value(row.get("order_edit").text() if row.get("order_edit") else "")
            if order is None:
                continue
            key = ("tag", tag.casefold())
            if key in seen:
                continue
            seen.add(key)
            entries.append({"kind": "tag", "value": tag, "order": order})
        for row in getattr(self, "_ct_rows", []):
            ct = str(row.get("type") or "").lower()
            order = self._parse_order_value(row.get("order_edit").text() if row.get("order_edit") else "")
            if order is None:
                continue
            key = ("content_type", ct)
            if key in seen:
                continue
            seen.add(key)
            entries.append({"kind": "content_type", "value": ct, "order": order})
        return entries

    def _sync_priority_order_visibility(self) -> None:
        enabled = bool(getattr(self, "_priority_order_cb", None) and self._priority_order_cb.isChecked())
        for row in list(getattr(self, "_linked_rows", [])) + list(getattr(self, "_ct_rows", [])):
            for key in ("order_label", "order_edit"):
                widget = row.get(key)
                if widget is not None:
                    widget.setVisible(enabled)

    def _find_other_tag_row(self) -> dict | None:
        for row in self._linked_rows:
            if row.get("tag") == NO_TAGS_KEY:
                return row
        return None

    def _move_other_tag_row_to_bottom(self) -> None:
        """Keep the always-present Other row visually and logically last."""
        other_row = self._find_other_tag_row()
        if other_row is None:
            return

        # Keep model ordering aligned with on-screen ordering.
        if self._linked_rows and self._linked_rows[-1] is not other_row:
            try:
                self._linked_rows.remove(other_row)
            except ValueError:
                pass
            self._linked_rows.append(other_row)

        # Re-add widget at the end of the layout so it renders last.
        try:
            self._tags_layout.removeWidget(other_row["widget"])
        except Exception:
            return
        self._tags_layout.addWidget(other_row["widget"])

    def _current_include_rest_from_other_slider(self) -> bool:
        other_row = self._find_other_tag_row()
        if other_row is None:
            cb = getattr(self, "_no_tags_cb", None)
            return bool(cb.isChecked()) if cb is not None else True
        if not any(
            row.get("tag") != NO_TAGS_KEY
            for row in self._linked_rows
        ):
            return True
        return int(other_row["slider"].value()) > 0

    def _sync_no_tags_checkbox_from_other_slider(self) -> None:
        cb = getattr(self, "_no_tags_cb", None)
        if cb is not None:
            cb.setChecked(self._current_include_rest_from_other_slider())

    def _ensure_other_tag_row(
        self,
        default_enabled: bool = True,
        defer_finalize: bool = False,
    ) -> None:
        if self._find_other_tag_row() is not None:
            self._move_other_tag_row_to_bottom()
            return
        real_total = sum(
            int(r["slider"].value())
            for r in self._linked_rows
            if r.get("tag") != NO_TAGS_KEY
        )
        default_weight = max(0, min(100, 100 - real_total)) if default_enabled else 0
        self._add_tag_row(
            NO_TAGS_KEY,
            weight=default_weight,
            locked=False,
            group_name="tags",
            defer_finalize=defer_finalize,
        )

    def _finalize_tag_row_batch_restore(self) -> None:
        self._rebalance_tag_groups(changed_row=None)
        self._move_other_tag_row_to_bottom()
        for row in self._linked_rows:
            row["pct_label"].setText(t("session_percent", value=row["slider"].value()))
        self._sync_no_tags_checkbox_from_other_slider()
        self._update_other_label()
        self._refresh_expected_mix_preview()
        self._sync_priority_order_visibility()
        self._schedule_live_preview_refresh()

    def _make_row_base(
        self,
        label_text: str,
        weight: int,
        locked: bool,
        group_name: str,
    ) -> tuple[QWidget, QHBoxLayout, QSlider, QLabel, QCheckBox, QLabel, QLineEdit]:
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
            t("session_tag_weight_tooltip")
        )
        row_layout.addWidget(slider)

        pct_label = QLabel(t("session_percent", value=weight))
        pct_label.setFixedWidth(36)
        row_layout.addWidget(pct_label)

        lock_cb = QCheckBox("🔒")
        lock_cb.setChecked(locked)
        lock_cb.setToolTip(t("session_tag_lock_tooltip"))
        lock_cb.setFixedWidth(48)
        row_layout.addWidget(lock_cb)

        row_layout.addWidget(QLabel(t("session_group")))
        group_edit = QLineEdit(group_name or "tags")
        group_edit.setFixedWidth(90)
        group_edit.setToolTip(t("session_tag_group_tooltip"))
        row_layout.addWidget(group_edit)

        # Disable slider when locked; re-enable on toggle.
        slider.setEnabled(not locked)
        qconnect(lock_cb.stateChanged,
                 lambda _, cb=lock_cb, s=slider: s.setEnabled(not cb.isChecked()))

        return row_widget, row_layout, slider, pct_label, lock_cb, name_label, group_edit

    def _add_tag_row(
        self,
        tag: str,
        weight: int = 20,
        locked: bool = False,
        group_name: str = "tags",
        order: int | None = None,
        defer_finalize: bool = False,
    ) -> None:
        resolved = self._resolve_tag_for_current_profile(tag)
        if not resolved:
            return
        tag = resolved
        if any(r["tag"] == tag for r in self._linked_rows):
            return

        row_widget, row_layout, slider, pct_label, lock_cb, name_label, group_edit = self._make_row_base(
            self._tag_display_name(tag), weight, locked, group_name
        )

        row_dict = {"tag": tag, "slider": slider, "pct_label": pct_label,
                    "lock_cb": lock_cb, "widget": row_widget, "name_label": name_label,
                    "group_edit": group_edit}
        self._refresh_tag_count(row_dict)
        qconnect(slider.valueChanged, lambda v, r=row_dict: self._on_weight_changed(r))
        qconnect(slider.valueChanged, lambda _: self._schedule_live_preview_refresh())
        qconnect(lock_cb.stateChanged, lambda _, r=row_dict: self._on_tag_lock_or_group_changed(r))
        qconnect(group_edit.textChanged, lambda _, r=row_dict: self._on_tag_lock_or_group_changed(r))
        qconnect(group_edit.textChanged, lambda _: self._schedule_live_preview_refresh())

        if tag != NO_TAGS_KEY:
            order_label = QLabel(t("session_order"))
            row_layout.addWidget(order_label)
            order_edit = QLineEdit()
            order_edit.setFixedWidth(54)
            order_edit.setPlaceholderText(t("session_order_placeholder"))
            order_edit.setToolTip(t("session_order_tooltip"))
            self._set_order_edit_value(order_edit, order)
            row_dict["order_label"] = order_label
            row_dict["order_edit"] = order_edit
            qconnect(order_edit.textChanged, lambda _: self._schedule_live_preview_refresh())
            row_layout.addWidget(order_edit)
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
        self._move_other_tag_row_to_bottom()

        # Hide this tag in the picker so it can't be added twice
        idx = self._tag_combo.findText(tag)
        if idx >= 0:
            self._tag_combo.removeItem(idx)

        if defer_finalize:
            return

        self._rebalance_tag_groups(changed_row=None)
        self._move_other_tag_row_to_bottom()
        for row in self._linked_rows:
            row["pct_label"].setText(t("session_percent", value=row["slider"].value()))
        self._sync_no_tags_checkbox_from_other_slider()
        self._update_other_label()
        self._refresh_expected_mix_preview()
        self._sync_priority_order_visibility()
        self._schedule_live_preview_refresh()

    def _remove_row(self, row_dict: dict, allow_other: bool = False) -> None:
        tag = row_dict["tag"]
        if tag == NO_TAGS_KEY and not allow_other:
            return
        if row_dict in self._linked_rows:
            self._linked_rows.remove(row_dict)
        row_dict["widget"].deleteLater()

        # Return the tag to the picker in alphabetical order
        items = [self._tag_combo.itemText(i) for i in range(self._tag_combo.count())]
        items.append(tag)
        items.sort()
        self._tag_combo.insertItem(items.index(tag), tag)

        self._rebalance_tag_groups(changed_row=None)
        for row in self._linked_rows:
            row["pct_label"].setText(t("session_percent", value=row["slider"].value()))
        self._sync_no_tags_checkbox_from_other_slider()
        self._update_other_label()
        self._refresh_expected_mix_preview()
        self._sync_priority_order_visibility()
        self._schedule_live_preview_refresh()

    # ------------------------------------------------------------------
    # Slider logic — tag sliders constrain within same group name
    # ------------------------------------------------------------------

    def _get_tag_group_name(self, row_dict: dict) -> str:
        return self._normalize_group_name(row_dict["group_edit"].text())

    def _rebalance_tag_groups(self, changed_row: dict | None) -> None:
        if self._updating:
            return
        other_row = self._find_other_tag_row()
        lone_other = other_row is not None and not any(
            row.get("tag") != NO_TAGS_KEY
            for row in self._linked_rows
        )
        groups: dict[str, list[dict]] = {}
        for row in self._linked_rows:
            g = self._get_tag_group_name(row)
            if not g:
                continue
            groups.setdefault(g, []).append(row)

        if not groups and not lone_other:
            return

        current = {r["tag"]: int(r["slider"].value()) for r in self._linked_rows}
        locks = {r["tag"]: bool(r["lock_cb"].isChecked()) for r in self._linked_rows}
        if lone_other:
            current[NO_TAGS_KEY] = 100
        changed_key = changed_row["tag"] if changed_row else None
        changed_group = self._get_tag_group_name(changed_row) if changed_row else None

        for group_name, rows in groups.items():
            keys = [r["tag"] for r in rows]
            if len(keys) <= 1:
                continue
            active_changed = changed_key if (changed_key and group_name == changed_group) else None
            self._rebalance_group_subset(
                values=current,
                locks=locks,
                keys=keys,
                changed_key=active_changed,
            )

        self._updating = True
        try:
            for row in self._linked_rows:
                row["slider"].setValue(max(0, min(100, int(current.get(row["tag"], row["slider"].value())))))
                row["slider"].setEnabled(
                    not row["lock_cb"].isChecked()
                    and not (lone_other and row.get("tag") == NO_TAGS_KEY)
                )
        finally:
            self._updating = False

    def _on_weight_changed(self, changed_row: dict) -> None:
        if self._updating:
            return
        self._rebalance_tag_groups(changed_row)
        changed_row["pct_label"].setText(t("session_percent", value=changed_row["slider"].value()))
        for row in self._linked_rows:
            row["pct_label"].setText(t("session_percent", value=row["slider"].value()))
        self._sync_no_tags_checkbox_from_other_slider()
        self._update_other_label()
        self._refresh_expected_mix_preview()
        self._schedule_live_preview_refresh()

    def _on_tag_lock_or_group_changed(self, row_dict: dict) -> None:
        if self._updating:
            return
        row_dict["slider"].setEnabled(not row_dict["lock_cb"].isChecked())
        self._rebalance_tag_groups(changed_row=None)
        for row in self._linked_rows:
            row["pct_label"].setText(t("session_percent", value=row["slider"].value()))
        self._sync_no_tags_checkbox_from_other_slider()
        self._update_other_label()
        self._refresh_expected_mix_preview()
        self._schedule_live_preview_refresh()

    def _update_other_label(self) -> None:
        """Show configured vs effective "Other cards" target."""
        if not hasattr(self, "_other_lbl"):
            return
        other_row = self._find_other_tag_row()
        real_total = sum(
            int(r["slider"].value())
            for r in self._linked_rows
            if r.get("tag") != NO_TAGS_KEY
        )
        cb = getattr(self, "_no_tags_cb", None)
        include_rest = (int(other_row["slider"].value()) > 0) if other_row is not None else (bool(cb.isChecked()) if cb is not None else True)
        effective_other = max(0, 100 - real_total) if include_rest else 0
        configured_other = int(other_row["slider"].value()) if other_row is not None else effective_other
        if configured_other != effective_other:
            self._other_lbl.setText(t("session_other_slider_status", configured=configured_other, effective=effective_other))
            return
        self._other_lbl.setText(t("session_other_cards_status", effective=effective_other))

    def _get_main_lock_state(self) -> dict[str, bool]:
        return {
            "topics": self._topics_lock_cb.isChecked(),
            "pdf": self._pdf_lock_cb.isChecked(),
            "priority": self._priority_lock_cb.isChecked(),
        }

    def _selected_main_pdf_limit_card_id(self) -> int | None:
        data = self._pdf_limit_combo.currentData()
        try:
            return int(data)
        except Exception:
            return None

    def _set_main_pdf_limit_form_enabled_state(self) -> None:
        has_card = self._selected_main_pdf_limit_card_id() is not None
        enabled = has_card and self._pdf_limit_main_enabled.isChecked()
        self._pdf_limit_search_edit.setEnabled(bool(self._pdf_limit_targets))
        self._pdf_limit_combo.setEnabled(bool(self._pdf_limit_targets))
        self._pdf_limit_refresh_btn.setEnabled(True)
        self._pdf_limit_main_enabled.setEnabled(has_card)
        self._pdf_limit_main_spin.setEnabled(enabled)
        self._pdf_limit_main_mode.setEnabled(enabled)
        self._pdf_limit_main_save_btn.setEnabled(has_card)

    def _refresh_pdf_limit_combo(self) -> None:
        query = " ".join(self._pdf_limit_search_edit.text().strip().lower().split())
        selected_card_id = self._selected_main_pdf_limit_card_id()
        self._pdf_limit_combo.blockSignals(True)
        self._pdf_limit_combo.clear()

        matches = []
        for target in self._pdf_limit_targets:
            hay = target.get("search", "")
            if query and query not in hay:
                continue
            matches.append(target)

        for target in matches:
            self._pdf_limit_combo.addItem(target["label"], target["card_id"])

        if not self._pdf_limit_targets:
            self._pdf_limit_combo.addItem(t("session_no_pdf_cards"), None)
        elif not matches:
            self._pdf_limit_combo.addItem(t("session_no_pdf_match"), None)

        if selected_card_id is not None:
            idx = self._pdf_limit_combo.findData(selected_card_id)
            if idx >= 0:
                self._pdf_limit_combo.setCurrentIndex(idx)
        self._pdf_limit_combo.blockSignals(False)
        self._load_main_pdf_limit_editor()

    def _refresh_pdf_limit_targets(self) -> None:
        targets: list[dict] = []
        try:
            for cid in mw.col.find_cards(f'note:"{PDF_NOTE_TYPE}"'):
                try:
                    card = mw.col.get_card(cid)
                    note = mw.col.get_note(card.nid)
                    title = _compact_text((getattr(note, "fields", []) or [""])[0], max_len=110) or f"PDF {cid}"
                    current_page = int(get_page(_ADDON_DIR, _active_profile(), cid))
                    label = t("session_preview_pdf_target", title=title, page=current_page, card_id=cid)
                    targets.append(
                        {
                            "card_id": int(cid),
                            "title": title,
                            "label": label,
                            "search": f"{title} {cid}".lower(),
                        }
                    )
                except Exception:
                    continue
        except Exception:
            targets = []
        targets.sort(key=lambda item: (item["title"].lower(), item["card_id"]))
        self._pdf_limit_targets = targets
        self._refresh_pdf_limit_combo()

    def _on_main_pdf_limit_form_changed(self, *_args) -> None:
        if self._pdf_limit_main_loading:
            return
        self._set_main_pdf_limit_form_enabled_state()

    def _load_main_pdf_limit_editor(self) -> None:
        cid = self._selected_main_pdf_limit_card_id()
        self._pdf_limit_main_loading = True
        if cid is None:
            self._pdf_limit_main_enabled.setChecked(False)
            self._pdf_limit_main_spin.setValue(10)
            idx = self._pdf_limit_main_mode.findData("warning")
            self._pdf_limit_main_mode.setCurrentIndex(max(0, idx))
            if self._pdf_limit_targets:
                self._pdf_limit_main_status_lbl.setText(t("session_pdf_limit_choose"))
            else:
                self._pdf_limit_main_status_lbl.setText(t("session_no_pdf_cards"))
            self._pdf_limit_main_loading = False
            self._set_main_pdf_limit_form_enabled_state()
            return

        settings = get_pdf_daily_limit_settings(_ADDON_DIR, _active_profile(), cid)
        current_page = get_page(_ADDON_DIR, _active_profile(), cid)
        status = get_pdf_daily_limit_status(
            _ADDON_DIR,
            _active_profile(),
            cid,
            current_page=current_page,
            persist_usage=False,
        )

        self._pdf_limit_main_enabled.setChecked(bool(settings.get("enabled")))
        self._pdf_limit_main_spin.setValue(max(1, int(settings.get("daily_page_limit", 10) or 10)))
        idx = self._pdf_limit_main_mode.findData(str(settings.get("enforcement_mode") or "warning"))
        self._pdf_limit_main_mode.setCurrentIndex(max(0, idx))
        if status.get("enabled"):
            self._pdf_limit_main_status_lbl.setText(t("session_pdf_limit_detailed_status", used=status["pages_used"], limit=status["daily_page_limit"], remaining=status["pages_remaining"], current_page=current_page, allowed_page=status["allowed_max_page"]))
        else:
            self._pdf_limit_main_status_lbl.setText(
                t("session_pdf_no_limit_current_page", current_page=current_page)
            )
        self._pdf_limit_main_loading = False
        self._set_main_pdf_limit_form_enabled_state()

    def _save_main_pdf_limit(self) -> None:
        cid = self._selected_main_pdf_limit_card_id()
        if cid is None:
            return
        save_pdf_daily_limit_settings(
            _ADDON_DIR,
            _active_profile(),
            cid,
            enabled=self._pdf_limit_main_enabled.isChecked(),
            daily_page_limit=int(self._pdf_limit_main_spin.value()),
            enforcement_mode=str(self._pdf_limit_main_mode.currentData() or "warning"),
        )
        self._refresh_pdf_limit_targets()
        idx = self._pdf_limit_combo.findData(cid)
        if idx >= 0:
            self._pdf_limit_combo.setCurrentIndex(idx)
        self._load_main_pdf_limit_editor()
        tooltip(t("session_pdf_limit_saved"))

    @staticmethod
    def _normalize_group_name(name: str) -> str:
        return " ".join((name or "").strip().split()).lower()

    def _get_main_group_state(self) -> dict[str, str]:
        return {
            "topics": self._normalize_group_name(self._topics_group_edit.text()),
            "pdf": self._normalize_group_name(self._pdf_group_edit.text()),
            "priority": self._normalize_group_name(self._priority_group_edit.text()),
        }

    def _get_main_targets(self) -> dict[str, int]:
        return {
            "topics": max(0, min(100, 100 - self._topics_slider.value())),
            "pdf": max(0, min(100, 100 - self._pdf_slider.value())),
            "priority": max(0, min(100, 100 - self._random_slider.value())),
        }

    @staticmethod
    def _split_total_by_weights(total: int, keys: list[str], weights: dict[str, float]) -> dict[str, int]:
        if not keys:
            return {}
        total = max(0, int(total))
        clamped = {k: max(0.0, float(weights.get(k, 0.0))) for k in keys}
        weight_sum = sum(clamped.values())
        if weight_sum <= 0:
            base = total // len(keys)
            rem = total - (base * len(keys))
            out = {k: base for k in keys}
            for i in range(rem):
                out[keys[i % len(keys)]] += 1
            return out

        raw = {k: (clamped[k] / weight_sum) * total for k in keys}
        out = {k: int(raw[k]) for k in keys}
        rem = total - sum(out.values())
        if rem > 0:
            ranked = sorted(keys, key=lambda k: (raw[k] - out[k], k), reverse=True)
            for i in range(rem):
                out[ranked[i % len(ranked)]] += 1
        return out

    def _apply_main_targets(self, targets: dict[str, int]) -> None:
        t = max(0, min(100, int(targets.get("topics", 0))))
        p = max(0, min(100, int(targets.get("pdf", 0))))
        pr = max(0, min(100, int(targets.get("priority", 0))))
        self._updating = True
        try:
            self._topics_slider.setValue(100 - t)
            self._pdf_slider.setValue(100 - p)
            self._random_slider.setValue(100 - pr)
        finally:
            self._updating = False

    def _rebalance_group_subset(
        self,
        values: dict[str, int],
        locks: dict[str, bool],
        keys: list[str],
        changed_key: str | None,
    ) -> None:
        if len(keys) <= 1:
            return
        locked_keys = [k for k in keys if locks.get(k, False)]
        unlocked_keys = [k for k in keys if not locks.get(k, False)]
        locked_sum = sum(values[k] for k in locked_keys)
        if locked_sum > 100:
            reduced = self._split_total_by_weights(
                total=100,
                keys=locked_keys,
                weights={k: values[k] for k in locked_keys},
            )
            for k in keys:
                values[k] = reduced.get(k, 0)
            return

        if changed_key is not None and changed_key in unlocked_keys:
            max_changed = max(0, 100 - locked_sum)
            values[changed_key] = min(values[changed_key], max_changed)
            remaining = 100 - locked_sum - values[changed_key]
            other_unlocked = [k for k in unlocked_keys if k != changed_key]
            if other_unlocked:
                redistributed = self._split_total_by_weights(
                    total=remaining,
                    keys=other_unlocked,
                    weights={k: values[k] for k in other_unlocked},
                )
                for k in other_unlocked:
                    values[k] = redistributed[k]
            else:
                values[changed_key] += max(0, remaining)
            return

        remaining = 100 - locked_sum
        if unlocked_keys:
            redistributed = self._split_total_by_weights(
                total=remaining,
                keys=unlocked_keys,
                weights={k: values[k] for k in unlocked_keys},
            )
            for k in unlocked_keys:
                values[k] = redistributed[k]
        else:
            normalized = self._split_total_by_weights(
                total=100,
                keys=keys,
                weights={k: values[k] for k in keys},
            )
            for k in keys:
                values[k] = normalized[k]

    def _rebalance_main_pool(self, changed_key: str | None) -> None:
        targets = self._get_main_targets()
        locks = self._get_main_lock_state()
        groups = self._get_main_group_state()
        all_keys = ["topics", "pdf", "priority"]

        self._topics_slider.setEnabled(not locks["topics"])
        self._pdf_slider.setEnabled(not locks["pdf"])
        self._random_slider.setEnabled(not locks["priority"])

        if changed_key is not None and locks.get(changed_key, False):
            return

        if changed_key is not None:
            group_name = groups.get(changed_key, "")
            subset = [k for k in all_keys if groups.get(k, "") == group_name and group_name]
            self._rebalance_group_subset(
                values=targets,
                locks=locks,
                keys=subset,
                changed_key=changed_key,
            )
        else:
            handled: set[str] = set()
            for key in all_keys:
                group_name = groups.get(key, "")
                if not group_name or group_name in handled:
                    continue
                handled.add(group_name)
                subset = [k for k in all_keys if groups.get(k, "") == group_name]
                self._rebalance_group_subset(
                    values=targets,
                    locks=locks,
                    keys=subset,
                    changed_key=None,
                )

        self._apply_main_targets(targets)

    def _on_main_slider_changed(self, changed_key: str) -> None:
        if self._updating:
            return
        self._rebalance_main_pool(changed_key=changed_key)

    def _on_main_lock_toggled(self, _changed_key: str) -> None:
        if self._updating:
            return
        self._rebalance_main_pool(changed_key=None)

    def _on_main_group_changed(self) -> None:
        if self._updating:
            return
        self._rebalance_main_pool(changed_key=None)

    @staticmethod
    def _format_pct(value: float) -> str:
        return f"{value * 100:.1f}%"

    @staticmethod
    def _apportion_counts(total: int, shares: dict[str, float]) -> dict[str, int]:
        if total <= 0:
            return {k: 0 for k in shares}
        raw = {k: max(0.0, v) * total for k, v in shares.items()}
        if sum(raw.values()) <= 0:
            return {k: 0 for k in shares}
        counts = {k: int(raw[k]) for k in shares}
        remainder = total - sum(counts.values())
        if remainder <= 0:
            return counts
        ranked = sorted(
            shares.keys(),
            key=lambda k: (raw[k] - counts[k], k),
            reverse=True,
        )
        for i in range(remainder):
            counts[ranked[i % len(ranked)]] += 1
        return counts


    def _set_heatmap_cell(
        self,
        table: QTableWidget,
        row: int,
        col: int,
        count: int,
        content_total: int,
    ) -> None:
        pct = (count / content_total) if content_total > 0 else 0.0
        text = f"{count}" if content_total <= 0 else f"{count} ({pct * 100:.0f}%)"
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        intensity = min(1.0, max(0.0, pct))
        alpha = int(28 + intensity * 150)
        item.setBackground(QColor(84, 132, 196, alpha))
        table.setItem(row, col, item)

    def _update_tag_content_heatmap(
        self,
        rows: list[tuple[str, float]],
        tag_shares_for_content: dict[str, float],
        tags_normalized: bool,
        cc: dict[str, int],
    ) -> None:
        if not hasattr(self, "_tag_content_table"):
            return

        table = self._tag_content_table
        content_cols = [("PDF", cc["pdf"]), ("Topics", cc["topics"]), ("Items", cc["items"])]

        if rows:
            tag_labels = [tag for tag, _ in rows]
            if NO_TAGS_KEY in tag_shares_for_content:
                tag_labels.append(NO_TAGS_KEY)
        else:
            tag_labels = [NO_TAGS_KEY]

        matrix: dict[str, dict[str, int]] = {tag: {"PDF": 0, "Topics": 0, "Items": 0} for tag in tag_labels}
        for content_name, content_count in content_cols:
            per_content_counts = self._apportion_counts(content_count, tag_shares_for_content)
            for tag in tag_labels:
                matrix[tag][content_name] = int(per_content_counts.get(tag, 0))

        table.setRowCount(len(tag_labels))
        for r, tag in enumerate(tag_labels):
            tag_item = QTableWidgetItem(_preview_tag_label(tag))
            table.setItem(r, 0, tag_item)
            total = 0
            for c, (content_name, content_total) in enumerate(content_cols, start=1):
                count = matrix[tag][content_name]
                total += count
                self._set_heatmap_cell(table, r, c, count, content_total)
            tot_item = QTableWidgetItem(str(total))
            tot_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(r, 4, tot_item)

        note = t("session_heatmap_note")
        if tags_normalized:
            note += " " + t("session_heatmap_normalized")
        self._tag_content_note_lbl.setText(note)

    def _refresh_expected_mix_preview(self) -> None:
        """Update the explanatory mix preview beneath the primary sliders."""
        if not hasattr(self, "_expected_mix_lbl") or not hasattr(self, "_expected_counts_lbl"):
            return

        mix = _compute_expected_mix(
            session_card_count=self._count_spin.value(),
            topics_slider=self._topics_slider.value(),
            pdf_slider=self._pdf_slider.value(),
            random_slider=self._random_slider.value(),
        )

        cs = mix["content_shares"]
        ms = mix["mode_shares"]
        cc = mix["content_counts"]
        mc = mix["mode_counts"]

        self._expected_mix_lbl.setText(t("session_expected_mix", pdf=self._format_pct(cs["pdf"]), topics=self._format_pct(cs["topics"]), items=self._format_pct(cs["items"]), random=self._format_pct(ms["random"]), priority=self._format_pct(ms["priority"])))
        self._expected_counts_lbl.setText(t("session_expected_counts", count=self._count_spin.value(), pdf=cc["pdf"], topics=cc["topics"], items=cc["items"], random=mc["random"], priority=mc["priority"]))
        self._tag_content_title_lbl.setText(t("session_tag_content_estimate"))
        real_rows = [
            (str(r["tag"]), max(0.0, r["slider"].value() / 100.0))
            for r in self._linked_rows
            if r["tag"] != NO_TAGS_KEY and r["slider"].value() > 0
        ]
        other_row = self._find_other_tag_row()
        cb = getattr(self, "_no_tags_cb", None)
        include_rest = (int(other_row["slider"].value()) > 0) if other_row is not None else (bool(cb.isChecked()) if cb is not None else True)
        tags_total = sum(w for _, w in real_rows)
        tags_normalized = False
        if not real_rows:
            tag_shares_for_content = {NO_TAGS_KEY: 1.0 if include_rest else 0.0}
        elif tags_total <= 1.0:
            tag_shares_for_content = {tag: w for tag, w in real_rows}
            tag_shares_for_content[NO_TAGS_KEY] = max(0.0, 1.0 - tags_total) if include_rest else 0.0
        else:
            tags_normalized = True
            norm = 1.0 / tags_total
            tag_shares_for_content = {tag: (w * norm) for tag, w in real_rows}
            if include_rest:
                tag_shares_for_content[NO_TAGS_KEY] = 0.0

        self._update_tag_content_heatmap(
            rows=real_rows,
            tag_shares_for_content=tag_shares_for_content,
            tags_normalized=tags_normalized,
            cc=cc,
        )

    def _branch_scope_label(self) -> str:
        if not self._branch_scope:
            return ""
        title = str(self._branch_scope.get("root_title") or "").strip() or t("session_selected_branch")
        card_count = len(list(self._branch_scope.get("card_ids") or []))
        return tn("session_subtree_card_count", card_count, title=title)

    def _apply_branch_scope_query(self, query: str) -> str:
        return _compose_branch_query(query, self._branch_clause)

    def _selection_signature_payload(self) -> dict:
        d = self._build_current_dict()
        return {
            "session_card_count": d.get("session_card_count"),
            "auto_refill_session": d.get("auto_refill_session"),
            "topics_slider": d.get("topics_slider"),
            "random_slider": d.get("random_slider"),
            "pdf_slider": d.get("pdf_slider"),
            "main_locks": d.get("main_locks"),
            "main_groups": d.get("main_groups"),
            "no_tags_checked": d.get("no_tags_checked"),
            "phase_order": d.get("phase_order"),
            "phases_enabled": d.get("phases_enabled"),
            "enforce_priority": d.get("enforce_priority"),
            "scheduler_scope": d.get("scheduler_scope"),
            "day_end_time": d.get("day_end_time"),
            "priority_order_enabled": d.get("priority_order_enabled"),
            "priority_order_entries": d.get("priority_order_entries"),
            "tag_rows": d.get("tag_rows"),
            "content_type_rows": d.get("content_type_rows"),
            "allow_content_tag_fallback": d.get("allow_content_tag_fallback"),
            "topics_filter": d.get("topics_filter"),
            "items_filter": d.get("items_filter"),
            "include_new": d.get("include_new"),
            "include_learning": d.get("include_learning"),
            "include_due": d.get("include_due"),
            "branch_scope_root_card_id": (self._branch_scope or {}).get("root_card_id"),
            "branch_scope_card_ids": list((self._branch_scope or {}).get("card_ids") or []),
        }

    def _selection_signature(self) -> str:
        return json.dumps(self._selection_signature_payload(), sort_keys=True, ensure_ascii=True)

    def _cache_live_preview_result(self, result) -> None:
        self._live_preview_cache = {
            "selected_ids": list(result.selected_ids),
            "picked_meta": copy.deepcopy(result.picked_meta),
            "session_counts": copy.deepcopy(result.stats.session),
            "session_time": copy.deepcopy(result.stats.session_time),
            "picker_snapshot": copy.deepcopy(result.picker_snapshot),
        }
        self._live_preview_signature = self._selection_signature()

    def _clear_live_preview_cache(self) -> None:
        self._live_preview_cache = None
        self._live_preview_signature = None

    def _live_preview_cache_is_current(self) -> bool:
        if not self._live_preview_cache or not self._live_preview_signature:
            return False
        return self._live_preview_signature == self._selection_signature()

    def set_use_live_preview_enabled(self, enabled: bool) -> None:
        self._use_live_preview_enabled = bool(enabled)

    def get_preview_override(self) -> dict | None:
        if not self._use_live_preview_enabled:
            return None
        if not self._live_preview_cache_is_current():
            return None
        return copy.deepcopy(self._live_preview_cache)

    def _open_live_preview(self) -> None:
        if self._live_preview_dialog is None:
            self._live_preview_dialog = _LiveSchedulerPreviewDialog(self)
        self._live_preview_dialog.sync_use_preview_checkbox()
        self._live_preview_dialog.show()
        self._live_preview_dialog.raise_()
        self._live_preview_dialog.activateWindow()
        self._live_preview_dialog.load_cached_or_refresh()

    def _close_live_preview(self) -> None:
        if self._live_preview_dialog is None:
            return
        self._live_preview_dialog.close()
        self._live_preview_dialog = None

    def _schedule_live_preview_refresh(self) -> None:
        self._clear_live_preview_cache()
        if self._live_preview_dialog and self._live_preview_dialog.isVisible():
            self._preview_refresh_timer.start()

    def _refresh_live_preview_if_open(self) -> None:
        if self._live_preview_dialog and self._live_preview_dialog.isVisible():
            self._live_preview_dialog.refresh_now()

    def _ready_filter_from_checks(self) -> str:
        """Build the is:… clause from the card-type checkboxes."""
        return build_ready_filter(
            include_new=self._cb_new.isChecked(),
            include_learning=self._cb_learning.isChecked(),
            include_due=self._cb_due.isChecked(),
        )

    def _normalized_saved_filter(self, key: str, source: dict | None = None) -> str:
        lookup = self._saved if source is None else (source or {})
        value = str(lookup.get(key, "") or "").strip()
        legacy_defaults = {
            "topics_filter": {"deck:Topics", "deck:Topics OR tag:Incremento"},
            "items_filter": {"-deck:Topics", "-deck:Topics -tag:Incremento"},
        }
        if value in legacy_defaults.get(key, set()):
            return ""
        return value

    def _refresh_tag_count(self, row_dict: dict) -> None:
        """Update the count annotation on one tag row."""
        tag = row_dict["tag"]
        if tag == NO_TAGS_KEY:
            row_dict["name_label"].setText(t("session_other_tag_label"))
            return
        ready = self._ready_filter_from_checks()
        tf_widget = getattr(self, "_topics_filter_edit", None)
        itf_widget = getattr(self, "_items_filter_edit", None)
        tf = tf_widget.text().strip() if tf_widget else ""
        itf = itf_widget.text().strip() if itf_widget else ""
        _card_utils.clear_topic_item_cache()
        n_topics = _card_utils.count_ready_topic_cards_by_tag(
            tag,
            topics_filter=self._apply_branch_scope_query(tf),
            ready_filter=ready,
        )
        n_items = _card_utils.count_ready_item_cards_by_tag(
            tag,
            items_filter=self._apply_branch_scope_query(itf),
            ready_filter=ready,
        )
        color = "#e0a020" if (n_topics == 0 or n_items == 0) else "gray"
        row_dict["name_label"].setText(t("session_tag_counts", tag=tag, color=color, topics=n_topics, items=n_items))

    def _refresh_counts(self) -> None:
        """Refresh the global topics/items count label and all tag-row counts."""
        ready = self._ready_filter_from_checks()
        tf = self._topics_filter_edit.text().strip()
        itf = self._items_filter_edit.text().strip()
        _card_utils.clear_topic_item_cache()
        n_topics = _card_utils.count_ready_topic_cards(
            topics_filter=self._apply_branch_scope_query(tf),
            ready_filter=ready,
        )
        n_items = _card_utils.count_ready_item_cards(
            items_filter=self._apply_branch_scope_query(itf),
            ready_filter=ready,
        )
        t_color = "#e0a020" if n_topics == 0 else "#c8a800"
        i_color = "#e0a020" if n_items  == 0 else "gray"
        scope = t("session_ready_in_branch") if self._branch_scope else t("session_ready")
        self._counts_lbl.setText(t("session_topic_item_counts", topic_color=t_color, item_color=i_color, topics=n_topics, items=n_items, scope=scope))
        for row in self._linked_rows:
            self._refresh_tag_count(row)

    def _refresh_ct_counts(self) -> None:
        """Update available-card counts on all content type rows."""
        _ct_filter_map = {
            "pdf":     '(note:"Incremento PDF" OR note:"Incremento EPUB") -is:suspended',
            "youtube": 'note:"Incremento Video" -is:suspended',
            "webpage": 'note:"Incremento Web" -is:suspended',
        }
        for row in getattr(self, "_ct_rows", []):
            try:
                n = len(mw.col.find_cards(self._apply_branch_scope_query(_ct_filter_map[row["type"]])))
                row["count_label"].setText(t("session_available_count", count=n))
            except Exception:
                row["count_label"].setText("")

    def _test_filter(self, kind: str, query: str) -> None:
        """Show the classified card count for a narrowing filter string."""
        ready = self._ready_filter_from_checks()
        _card_utils.clear_topic_item_cache()
        scoped_query = self._apply_branch_scope_query(query)
        if kind == "topics":
            count = _card_utils.count_ready_topic_cards(
                topics_filter=scoped_query,
                ready_filter=ready,
            )
        else:
            count = _card_utils.count_ready_item_cards(
                items_filter=scoped_query,
                ready_filter=ready,
            )
        scope_note = t("session_active_branch") if self._branch_scope else ""
        label = t("knowledge_tree_topic") if kind == "topics" else t("knowledge_tree_item")
        query_label = query or t("session_no_extra_filter")
        showInfo(t("session_filter_result", label=label, query=query_label, count=count, scope=scope_note))

    def accept(self) -> None:
        """Validate preview state, then let background session construction run."""
        if self._use_live_preview_enabled and not self._live_preview_cache_is_current():
            QMessageBox.warning(
                self,
                t("session_live_preview_required_title"),
                t("session_live_preview_required_message"),
            )
            return
        self.save_config(save_selected_profile=True)
        self._close_live_preview()
        super().accept()

    def reject(self) -> None:
        self._close_live_preview()
        super().reject()

    # ------------------------------------------------------------------
    # Statistics history actions
    # ------------------------------------------------------------------

    def _confirm(self, title: str, message: str) -> bool:
        return self._ask_question(title, message) == QMessageBox.StandardButton.Yes

    def _ask_question(self, title: str, message: str):
        """Ask a translated Yes/No question."""
        box = QMessageBox(QMessageBox.Icon.Question, title, message,
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self)
        box.button(QMessageBox.StandardButton.Yes).setText(t("session_yes"))
        box.button(QMessageBox.StandardButton.No).setText(t("session_no"))
        return box.exec()

    def _delete_daily(self) -> None:
        if not self._confirm(t("session_delete_today_title"),
                             t("session_delete_today_message")):
            return
        delete_daily_stats(
            _ADDON_DIR,
            _active_profile(),
            self._get_day_end_time(),
        )
        showInfo(t("session_statistics_today_deleted"))

    def _delete_session(self) -> None:
        if not self._confirm(t("session_delete_session_title"),
                             t("session_delete_session_message")):
            return
        if self._on_clear_session:
            self._on_clear_session()
        showInfo(t("session_statistics_session_cleared"))

    def _delete_lifetime(self) -> None:
        if not self._confirm(t("session_delete_all_time_title"),
                             t("session_delete_all_time_message")):
            return
        delete_lifetime_stats(_ADDON_DIR, _active_profile())
        showInfo(t("session_statistics_all_time_deleted"))

    def _delete_all(self) -> None:
        if not self._confirm(t("session_delete_history_title"),
                             t("session_delete_history_message")):
            return
        delete_all_stats(_ADDON_DIR, _active_profile())
        if self._on_clear_session:
            self._on_clear_session()
        showInfo(t("session_statistics_history_deleted"))

    def _export_json(self) -> None:
        raw = export_stats_data(
            _ADDON_DIR,
            _active_profile(),
            day_end_time=self._get_day_end_time(),
        )
        if not raw:
            showInfo(t("session_statistics_no_export"))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, t("session_export_statistics_title"), "incremento_stats.json",
            t("session_json_file_filter"),
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=2, sort_keys=True)
            showInfo(t("session_statistics_exported", path=path))
        except Exception as e:
            showInfo(t("session_statistics_export_failed", error=e))

    # ------------------------------------------------------------------
    # Public accessor — call after exec() returns Accepted
    # ------------------------------------------------------------------

    def to_config(self) -> SchedulerConfig:
        """Return a SchedulerConfig built from the current widget state."""
        raw = {
            r["tag"]: r["slider"].value()
            for r in self._linked_rows
            if r["tag"] != NO_TAGS_KEY and r["slider"].value() > 0
        }
        ct_weights = {
            r["type"]: r["slider"].value() / 100.0
            for r in self._ct_rows
            if r["cb"].isChecked() and r["slider"].value() > 0
        }
        return SchedulerConfig(
            session_card_count=self._count_spin.value(),
            auto_refill_session=self._auto_refill_session_cb.isChecked(),
            topics_rate=1.0 - self._topics_slider.value() / 100.0,
            random_rate=self._random_slider.value() / 100.0,
            pdf_rate=(100 - self._pdf_slider.value()) / 100.0,
            use_tags=bool(raw),
            tag_weights={tag: v / 100.0 for tag, v in raw.items()},
            include_rest=self._current_include_rest_from_other_slider(),
            allow_content_tag_fallback=self._allow_content_tag_fallback_cb.isChecked(),
            scheduler_scope=self._scope_combo.currentData(),
            day_end_time=self._get_day_end_time(),
            priority_order_enabled=self._priority_order_cb.isChecked(),
            priority_order_entries=self._current_priority_order_entries(),
            prioritized_tags_first=[],
            prioritized_tags_mode="exhaust",
            phase_order=self._funnel.get_order(),
            phases_enabled=self._funnel.get_enabled(),
            enforce_priority=self._enforce_cb.isChecked(),
            topics_filter=self._topics_filter_edit.text().strip(),
            items_filter=self._items_filter_edit.text().strip(),
            include_new=self._cb_new.isChecked(),
            include_learning=self._cb_learning.isChecked(),
            include_due=self._cb_due.isChecked(),
            preserve_order=self._preserve_order_cb.isChecked(),
            show_debug=self._show_debug_cb.isChecked(),
            content_type_weights=ct_weights,
        )

    def selected_dialog_profile_name(self) -> str | None:
        return _normalize_selected_scheduler_profile(
            self._selected_profile_name,
            self._profiles,
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _build_current_dict(self, *, include_selected_profile: bool = True) -> dict:
        """Serialize dialog state for config persistence or named-profile storage."""
        data = {
            "setup_mode": getattr(self, "_setup_mode", BASIC_MODE),
            "session_card_count": self._count_spin.value(),
            "auto_refill_session": self._auto_refill_session_cb.isChecked(),
            "allow_content_tag_fallback": self._allow_content_tag_fallback_cb.isChecked(),
            "topics_slider":      self._topics_slider.value(),
            "random_slider":      self._random_slider.value(),
            "pdf_slider":         self._pdf_slider.value(),
            "main_locks": {
                "topics": self._topics_lock_cb.isChecked(),
                "pdf": self._pdf_lock_cb.isChecked(),
                "priority": self._priority_lock_cb.isChecked(),
            },
            "main_groups": {
                "topics": self._topics_group_edit.text().strip() or _DEFAULT_MAIN_GROUPS["topics"],
                "pdf": self._pdf_group_edit.text().strip() or _DEFAULT_MAIN_GROUPS["pdf"],
                "priority": self._priority_group_edit.text().strip() or _DEFAULT_MAIN_GROUPS["priority"],
            },
            "no_tags_checked":    self._current_include_rest_from_other_slider(),
            "phase_order":        self._funnel.get_order(),
            "phases_enabled":     self._funnel.get_enabled(),
            "enforce_priority":   self._enforce_cb.isChecked(),
            "scheduler_scope":    self._scope_combo.currentData(),
            "day_end_time":       self._get_day_end_time(),
            "priority_order_enabled": self._priority_order_cb.isChecked(),
            "priority_order_entries": self._current_priority_order_entries(),
            "prioritized_tags_first": [],
            "prioritized_tags_mode": "exhaust",
            "tag_rows": [
                {
                    "tag": r["tag"],
                    "weight": r["slider"].value(),
                    "locked": r["lock_cb"].isChecked(),
                    "group": r["group_edit"].text().strip() or "tags",
                    "order": (
                        self._parse_order_value(r.get("order_edit").text())
                        if r.get("order_edit") is not None
                        else None
                    ),
                }
                for r in self._linked_rows
            ],
            "content_type_rows": [
                {
                    "type": r["type"],
                    "enabled": r["cb"].isChecked(),
                    "weight": r["slider"].value(),
                    "order": self._parse_order_value(r.get("order_edit").text()),
                }
                for r in self._ct_rows
            ],
            "topics_filter":    self._topics_filter_edit.text().strip(),
            "items_filter":     self._items_filter_edit.text().strip(),
            "include_new":      self._cb_new.isChecked(),
            "include_learning": self._cb_learning.isChecked(),
            "include_due":      self._cb_due.isChecked(),
            "preserve_order":   self._preserve_order_cb.isChecked(),
            "show_debug":       self._show_debug_cb.isChecked(),
            "use_live_preview": self._use_live_preview_enabled,
        }
        if include_selected_profile:
            data["selected_profile"] = self.selected_dialog_profile_name()
        return data

    def save_config(self, *, save_selected_profile: bool = False) -> None:
        """Persist dialog state and optionally overwrite its selected named preset."""
        config = load_addon_config(mw.addonManager, _ADDON_PKG)
        dialog_data = self._build_current_dict(include_selected_profile=True)
        config["dialog"] = dialog_data

        selected_name = (
            self.selected_dialog_profile_name()
            if save_selected_profile
            else None
        )
        if save_selected_profile and selected_name:
            profile_data = dict(dialog_data)
            profile_data.pop("selected_profile", None)
            updated_profiles = dict(self._profiles)
            updated_profiles[selected_name] = profile_data
            config["scheduler_presets"] = updated_profiles
            config["profiles"] = copy.deepcopy(updated_profiles)

        saved_config = save_addon_config(mw.addonManager, _ADDON_PKG, config)
        if save_selected_profile and selected_name:
            self._profiles = copy.deepcopy(saved_config.get("scheduler_presets") or {})

    # ------------------------------------------------------------------
    # Profile management
    # ------------------------------------------------------------------

    def _refresh_profile_combo(self) -> None:
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        self._profile_combo.addItem(self._current_settings_display(), None)
        for name in sorted(self._profiles.keys()):
            self._profile_combo.addItem(name)
        selected_name = self.selected_dialog_profile_name()
        if selected_name:
            idx = self._profile_combo.findText(selected_name)
            if idx >= 0:
                self._profile_combo.setCurrentIndex(idx)
            else:
                self._profile_combo.setCurrentIndex(0)
                self._selected_profile_name = None
        else:
            self._profile_combo.setCurrentIndex(0)
        self._profile_combo.blockSignals(False)
        self._sync_profile_button_state()
        self._refresh_basic_profile_combo()

    def _sync_profile_button_state(self) -> None:
        has_selected_profile = self.selected_dialog_profile_name() is not None
        self._profile_load_btn.setEnabled(has_selected_profile)
        self._profile_save_btn.setEnabled(has_selected_profile)
        self._profile_rename_btn.setEnabled(has_selected_profile)
        self._profile_delete_btn.setEnabled(has_selected_profile)

    def _on_profile_combo_changed(self, _index: int) -> None:
        self._selected_profile_name = _normalize_selected_scheduler_profile(
            self._profile_combo.currentData() or self._profile_combo.currentText(),
            self._profiles,
        )
        self._sync_profile_button_state()
        self._refresh_basic_profile_combo()
        self._sync_basic_controls_from_advanced()

    def _load_profile(self) -> None:
        name = self.selected_dialog_profile_name()
        if not name or name not in self._profiles:
            return
        self._load_profile_dict(self._profiles[name])
        self.save_config()

    def _add_profile(self) -> None:
        current = self.selected_dialog_profile_name() or ""
        name, ok = QInputDialog.getText(
            self, t("session_add_preset_title"), t("session_preset_name_prompt"), text=current
        )
        name = name.strip()
        if not ok or not name:
            return
        if name in self._profiles:
            QMessageBox.warning(
                self,
                t("session_add_preset_title"),
                t("session_preset_exists", name=name),
            )
            return
        self._profiles = _write_named_scheduler_profile(
            name,
            self._build_current_dict(include_selected_profile=False),
            self._profiles,
        )
        self._selected_profile_name = name
        self._refresh_profile_combo()
        self.save_config()
        tooltip(t("session_preset_added", name=name))

    def _save_profile(self) -> None:
        name = self.selected_dialog_profile_name()
        if not name or name not in self._profiles:
            return
        self._profiles = _write_named_scheduler_profile(
            name,
            self._build_current_dict(include_selected_profile=False),
            self._profiles,
        )
        self._selected_profile_name = name
        self._refresh_profile_combo()
        self.save_config()
        tooltip(t("session_preset_saved", name=name))

    def _rename_profile(self) -> None:
        old_name = self.selected_dialog_profile_name()
        if not old_name or old_name not in self._profiles:
            return
        new_name, ok = QInputDialog.getText(
            self, t("session_rename_preset_title"), t("session_preset_name_prompt"), text=old_name
        )
        new_name = new_name.strip()
        if not ok or not new_name or new_name == old_name:
            return
        if new_name in self._profiles:
            QMessageBox.warning(
                self,
                t("session_rename_preset_title"),
                t("session_preset_exists", name=new_name),
            )
            return
        self._profiles = _rename_named_scheduler_profile(
            old_name,
            new_name,
            self._profiles,
        )
        self._selected_profile_name = new_name
        self._refresh_profile_combo()
        self.save_config()
        tooltip(t("session_preset_renamed", old_name=old_name, new_name=new_name))

    def _delete_profile(self) -> None:
        name = self.selected_dialog_profile_name()
        if not name or name not in self._profiles:
            return
        r = self._ask_question(
            t("session_delete_preset_title"),
            t("session_delete_preset_message", name=name),
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        del self._profiles[name]
        self._selected_profile_name = None
        self._refresh_profile_combo()
        self.save_config()
        tooltip(t("session_preset_deleted", name=name))

    def _load_profile_dict(self, d: dict) -> None:
        """Apply a profile dict to all dialog widgets."""
        self._count_spin.setValue(d.get("session_card_count", 50))

        topics_val = d.get("topics_slider", 10)
        self._topics_slider.setValue(topics_val)
        self._topics_left_lbl.setText(t("session_percent", value=100 - topics_val))
        self._topics_right_lbl.setText(t("session_percent", value=topics_val))

        pdf_val = d.get("pdf_slider", 100)
        self._pdf_slider.setValue(pdf_val)
        self._pdf_left_lbl.setText(t("session_percent", value=100 - pdf_val))
        self._pdf_right_lbl.setText(t("session_percent", value=pdf_val))

        random_val = d.get("random_slider", 99)
        self._random_slider.setValue(random_val)
        self._random_left_lbl.setText(t("session_percent", value=100 - random_val))
        self._random_right_lbl.setText(t("session_percent", value=random_val))

        locks = d.get("main_locks", {}) or {}
        self._topics_lock_cb.setChecked(bool(locks.get("topics", False)))
        self._pdf_lock_cb.setChecked(bool(locks.get("pdf", False)))
        self._priority_lock_cb.setChecked(bool(locks.get("priority", False)))
        groups = d.get("main_groups", {}) or {}
        self._topics_group_edit.setText(str(groups.get("topics", _DEFAULT_MAIN_GROUPS["topics"])))
        self._pdf_group_edit.setText(str(groups.get("pdf", _DEFAULT_MAIN_GROUPS["pdf"])))
        self._priority_group_edit.setText(str(groups.get("priority", _DEFAULT_MAIN_GROUPS["priority"])))
        self._rebalance_main_pool(changed_key=None)

        self._cb_new.setChecked(d.get("include_new", True))
        self._cb_learning.setChecked(d.get("include_learning", True))
        self._cb_due.setChecked(d.get("include_due", True))
        self._no_tags_cb.setChecked(d.get("no_tags_checked", True))
        self._enforce_cb.setChecked(d.get("enforce_priority", True))
        self._auto_refill_session_cb.setChecked(bool(d.get("auto_refill_session", False)))
        self._allow_content_tag_fallback_cb.setChecked(
            bool(d.get("allow_content_tag_fallback", False))
        )

        saved_scope = d.get("scheduler_scope", "session")
        for i in range(self._scope_combo.count()):
            if self._scope_combo.itemData(i) == saved_scope:
                self._scope_combo.setCurrentIndex(i)
                break

        saved_time = d.get("day_end_time", "04:00")
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

        self._saved_priority_order_map = self._priority_order_map_from_dict(d)
        priority_order_enabled = bool(d.get("priority_order_enabled", False))
        if (
            "priority_order_enabled" not in d
            and "priority_order_entries" not in d
            and d.get("prioritized_tags_first")
        ):
            priority_order_enabled = True
        self._priority_order_cb.setChecked(priority_order_enabled)

        self._funnel.set_order(
            d.get("phase_order", _DEFAULT_PHASE_ORDER),
            enabled=d.get("phases_enabled", {}),
        )

        self._topics_filter_edit.setText(self._normalized_saved_filter("topics_filter", d))
        self._items_filter_edit.setText(self._normalized_saved_filter("items_filter", d))
        self._preserve_order_cb.setChecked(d.get("preserve_order", True))
        self._show_debug_cb.setChecked(d.get("show_debug", False))
        self._use_live_preview_enabled = bool(d.get("use_live_preview", False))
        if self._live_preview_dialog is not None:
            self._live_preview_dialog.sync_use_preview_checkbox()

        # Replace tag rows
        for row in list(self._linked_rows):
            self._remove_row(row, allow_other=True)
        skipped_missing_tags = 0
        for entry in d.get("tag_rows", []):
            tag = entry.get("tag")
            if self._resolve_tag_for_current_profile(tag) is None:
                skipped_missing_tags += 1
                continue
            self._add_tag_row(tag, entry.get("weight", 20),
                              locked=entry.get("locked", False),
                              group_name=entry.get("group", "tags"),
                              order=self._priority_order_for("tag", tag),
                              defer_finalize=True)
        self._ensure_other_tag_row(
            default_enabled=d.get("no_tags_checked", True),
            defer_finalize=True,
        )
        self._finalize_tag_row_batch_restore()
        if skipped_missing_tags > 0:
            tooltip(tn("session_tag_rows_skipped", skipped_missing_tags))

        # Restore content type rows
        ct_saved = {r["type"]: r for r in d.get("content_type_rows", [])}
        for row in self._ct_rows:
            saved = ct_saved.get(row["type"], {})
            row["cb"].setChecked(saved.get("enabled", False))
            w = saved.get("weight", 20)
            row["slider"].setValue(w)
            row["pct_label"].setText(f"{w}%")
            row["slider"].setEnabled(row["cb"].isChecked())
            self._set_order_edit_value(
                row.get("order_edit"),
                self._priority_order_for("content_type", row["type"]),
            )

        self._update_other_label()
        self._sync_priority_order_visibility()
        self._refresh_expected_mix_preview()
        self._refresh_counts()
        self._schedule_live_preview_refresh()
        self._sync_basic_controls_from_advanced()
