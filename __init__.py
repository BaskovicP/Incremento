import copy
from html import escape as _html_escape
import json
import os
import sqlite3
import time
import weakref
import zipfile
from urllib.parse import unquote

from aqt import mw, gui_hooks
from .backend.deps import activate_pymupdf as _activate_pymupdf
from .backend.i18n import initialize_language as _initialize_language, t as _t, tn as _tn
from .backend import language_packs as _language_packs
from .backend.config_service import load_addon_config as _load_initial_config

from anki import lang as _anki_language
from aqt.errors import show_exception
from aqt.reviewer import Reviewer
from aqt.utils import showInfo, tooltip, tr
from aqt.operations.scheduling import bury_cards as _bury_cards_op
from aqt.qt import (
    QAction,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QEvent,
    QInputDialog,
    QMenu,
    QObject,
    QShortcut,
    QKeySequence,
    QTextBrowser,
    QTimer,
    Qt,
    QVBoxLayout,
    qconnect,
)

from .frontend.stats_dialog import StatsDialog
from .backend.scheduler_config import load_scheduler_config
from .backend.statistics import (
    load_daily_history as _load_daily_stat_history,
    record_reading_page as _record_reading_page_stat,
)
from .backend.pdf_manager import (
    PDF_NOTE_TYPE,
    PDF_COVER_FIELD,
    find_live_pdf_card_by_filename,
    get_page,
    get_zoom,
    get_read_page,
    extract_pdf_pages_text,
    regenerate_pdf_card_cover,
    sync_pdf_card_file_references,
)
from .backend.epub_manager import (
    EPUB_NOTE_TYPE,
    EPUB_FILE_FIELD,
    get_epub_progress,
    regenerate_epub_card_cover,
)
from .backend.video_manager import (
    VIDEO_NOTE_TYPE,
    LOCAL_VIDEO_FIELD,
    get_video_note_media,
    is_supported_video_url,
    resolve_video_url_for_embed,
    add_video_card,
    download_and_compress_video,
    import_local_video_file,
)
from .backend.writing_manager import (
    WRITING_FILE_FIELD,
    WRITING_NOTE_TYPE,
    add_writing_card,
    build_writing_relpath,
)
from .backend.local_file_manager import LOCAL_FILE_NOTE_TYPE, add_local_file_card
from .backend.note_metadata import (
    INCREMENTO_HIDDEN_FIELDS,
    build_incremento_metadata,
    derive_note_source_metadata,
    hidden_field_values,
    matches_hidden_field_reference,
    source_document_reference,
)
from .backend.operation_journal import ImportOperation
from .backend.db import (
    get_connection,
    get_pdf_card_source_filename,
    get_pdf_referenced_filenames,
)
from .backend.priority_manager import (
    configured_show_priority_dialog_after_answer,
    configured_priority_lower_is_more_important,
    get_priority,
    set_priority,
    get_all_priorities,
    invert_all_priorities,
)
from .backend.custom_schedule import (
    apply_custom_schedule_after_answer as _apply_custom_schedule_after_answer,
    apply_rule_now_to_card as _apply_custom_schedule_now_to_card,
    clear_custom_schedule_rules as _clear_custom_schedule_rules,
    configured_custom_schedule_default_mode as _configured_custom_schedule_default_mode,
    configured_custom_schedule_presets as _configured_custom_schedule_presets,
    format_custom_schedule_rule as _format_custom_schedule_rule,
    prepare_custom_schedule_answer as _prepare_custom_schedule_answer,
    reconcile_custom_schedule_state_after_anki_operation as _reconcile_custom_schedule_state_after_anki_operation,
    register_diagnostic_event_callback as _register_custom_schedule_diagnostic_event_callback,
    reset_custom_schedule_answer_runtime_state as _reset_custom_schedule_answer_runtime_state,
    save_custom_schedule_rule as _save_custom_schedule_rule,
)
from .backend.topic_a_factor_bulk import (
    apply_bulk_topic_a_factor as _apply_bulk_topic_a_factor,
)
from .backend.web_manager import (
    WEB_NOTE_TYPE,
    configured_track_web_window_with_extension,
    configured_remember_browser_card_scroll,
    configured_prefer_web_card_resume_in_original_page,
    get_web_progress,
)
from .backend.reviewer_buttons import (
    configured_use_fail_pass_on_items as _configured_use_fail_pass_on_items,
    item_fail_pass_buttons as _item_fail_pass_buttons,
    remap_item_fail_pass_ease as _remap_item_fail_pass_ease,
    reviewer_button_mode as _reviewer_button_mode_for_card,
)
from .backend.item_skip import (
    configured_item_skip_enabled as _configured_item_skip_enabled,
    configured_item_skip_minutes as _configured_item_skip_minutes,
    item_skip_due_label as _item_skip_due_label,
    next_timed_item_skip_at as _next_timed_item_skip_at,
    release_expired_timed_item_skips as _release_expired_timed_item_skips,
    store_timed_item_skip as _store_timed_item_skip,
)
from .backend import browser_bridge as _browser_bridge_mod
from .backend import diagnostics as _diagnostics_mod
from .backend.decks import create_topics_deck as _create_topics_deck
from .frontend.priority_dialog import PriorityDialog
from .frontend.custom_schedule_dialog import CustomScheduleDialog
from .frontend import timer_widget as _timer_mod
from .backend.topic_scheduler import (
    TOPIC_REVIEW_BUTTONS,
    configured_default_topic_a_factor as _configured_default_topic_a_factor,
    configured_topic_less_adjustment_percent as _configured_topic_less_adjustment_percent,
    configured_topic_maximum_interval_days as _configured_topic_maximum_interval_days,
    configured_topic_more_adjustment_percent as _configured_topic_more_adjustment_percent,
    configured_topic_card_tags as _configured_topic_card_tags,
    configured_topic_card_types as _configured_topic_card_types,
    is_topic_card as _is_topic_card,
    on_topic_card_answered as _on_topic_card_answered,
    prepare_topic_answer as _prepare_topic_answer,
    reconcile_topic_state_after_anki_operation as _reconcile_topic_state_after_anki_operation,
    register_diagnostic_event_callback as _register_topic_diagnostic_event_callback,
    reset_topic_answer_runtime_state as _reset_topic_answer_runtime_state,
    topic_due_label as _topic_due_label,
)
from .backend.topic_postpone import (
    TOPIC_POSTPONE_EASE as _TOPIC_POSTPONE_EASE,
    configured_topic_postpone_enabled as _configured_topic_postpone_enabled,
    configured_topic_postpone_mode as _configured_topic_postpone_mode,
    configured_topic_postpone_minutes as _configured_topic_postpone_minutes,
    has_session_postponed_cards as _has_session_postponed_cards,
    next_timed_postpone_at as _next_timed_postpone_at,
    postpone_topic_card as _postpone_topic_card,
    release_expired_timed_postpones as _release_expired_timed_postpones,
    release_session_postponed_cards as _release_session_postponed_cards,
    store_timed_topic_postpone as _store_timed_topic_postpone,
    topic_postpone_due_label as _topic_postpone_due_label,
)
from .frontend.timer_widget import (
    build_timer_toolbar,
    on_timer_question_shown as _on_timer_question_shown,
    timer_on_card_answered as _timer_on_card_answered,
)
from .frontend import pdf_dock as _pdf_dock_mod
from .frontend import epub_dock as _epub_dock_mod
from .frontend import reader_links as _reader_links_mod
from .frontend import video_dock as _video_dock_mod
from .frontend import web_dock as _web_dock_mod
from .frontend import writing_dock as _writing_dock_mod
from .frontend import local_file_dock as _local_file_dock_mod
from .frontend import add_card_dock as _add_card_dock_mod
from .frontend import image_rotation as _image_rotation_mod
from .frontend import browser_quick_tags as _browser_quick_tags_mod
from .frontend.extract_batch_dialog import ExtractBatchDialog
from .frontend import browser_priority_toolbar as _browser_priority_toolbar_mod
from .backend import review_time_tracker as _review_time_mod
from .backend import anki_compat as _anki_compat
from .backend import reconciliation as _reconciliation_mod
from .backend.note_type_updates import (
    NoteTypeApplyError as _NoteTypeApplyError,
    apply_incremento_note_type_updates as _apply_incremento_note_type_updates,
    detect_incremento_note_type_updates as _detect_incremento_note_type_updates,
)
from .backend.db import (
    close_current_connection,
    create_database_checkpoint,
    find_card_database_entries,
    get_connection,
    get_card_browser_media_ref,
    get_custom_schedule_rule,
    get_knowledge_tree_node,
    get_topic_schedule,
    prune_document_text_index_rows,
    prune_note_ocr_index_rows,
    get_recent_reviewer_tags,
    replace_pdf_text_index,
    search_pdf_text_index,
    touch_recent_reviewer_tags,
)
from .backend.reviewer_tags import append_missing_tags, normalize_tag_list
from .backend.paths import get_active_profile as _active_profile
from .backend import paths as _paths
from .backend import backup_schedule as _backup_schedule
from .backend.config_service import (
    configured_reviewer_button_group_visible,
    configured_reviewer_button_visibility,
    configured_topic_done_tag as _configured_topic_done_tag,
    load_addon_config as _load_addon_config,
    migrate_persisted_config as _migrate_persisted_config,
    save_addon_config as _save_addon_config,
)
from .backend.session import (
    diagnostic_session_snapshot,
    register_diagnostic_event_callback,
    reset_session_counts,
    get_session_counts,
    get_session_times,
    start_quick_open_review,
)
from .frontend.session_launcher import learnFunction
from .frontend.settings_dialog import (
    IncrementoSettingsDialog,
    localized_shortcut_action_specs,
    resolved_runtime_shortcuts,
)
from .frontend.command_palette import (
    build_palette_commands,
    create_command_palette_dialog,
)
from .frontend.activity_center import create_activity_center_dialog
from .frontend.onboarding_dialog import (
    create_onboarding_dialog,
    mark_onboarding_complete,
    should_show_onboarding,
)
from .frontend.pdf_quick_jump import _PdfQuickJumpDialog
from .frontend.pdf_bookshelf import (
    _DocumentBookshelfDialog,
    _load_bookshelf_snapshot,
)
from .frontend.reviewer_extract_button import build_reviewer_extract_button_js
from .frontend.reviewer_button_style import build_reviewer_button_style_js
from .frontend.reviewer_button_visibility import (
    add_reviewer_button_visibility_menu,
    build_reviewer_button_visibility_js,
    effective_reviewer_button_visibility,
)
from .frontend.reviewer_topic_actions import TopicReviewActions
from .frontend.reviewer_priority_badge import (
    build_reviewer_priority_badge_js,
    configured_reviewer_priority_badge_card_types,
    should_show_reviewer_priority_badge,
)
from .frontend.reviewer_shortcuts import filter_reviewer_shortcuts
from .frontend.reviewer_focus import (
    register_reviewer_focus_restore_hooks,
    schedule_reviewer_focus_restore,
)
from .frontend.reviewer_source_cover import build_reviewer_source_cover_js
from .frontend.database_entries_dialog import show_database_entries_dialog
from .frontend.reviewer_tag_dialog import ReviewerTagDialog
from .frontend.current_document_search_dialog import _CurrentDocumentSearchDialog
from .frontend.search_all import _SearchAllDialog
from .frontend.note_type_update_dialog import (
    ACTION_APPLY as _NOTE_TYPE_ACTION_APPLY,
    ACTION_SYNC_FIRST as _NOTE_TYPE_ACTION_SYNC_FIRST,
    IncrementoNoteTypeUpdateDialog,
)
from .backend.knowledge_tree import (
    NODE_KIND_ITEM as _KT_NODE_KIND_ITEM,
    NODE_KIND_TOPIC as _KT_NODE_KIND_TOPIC,
    apply_node_kind_to_cards as _kt_apply_node_kind_to_cards,
)
from .backend.reviewer_extract import (
    initial_extract_field_values as _initial_extract_field_values,
    knowledge_tree_link_state as _knowledge_tree_link_state,
)

_activate_pymupdf()

# Resolve only at addon startup. Saving Settings deliberately keeps the running
# reviewer/docks in their current language until the next Anki restart.
_startup_ui_language_choice = _load_initial_config(mw.addonManager, __name__).get("ui_language", "auto")
_initialize_language(
    _startup_ui_language_choice,
    getattr(_anki_language, "current_lang", "en"),
)

_ADDON_DIR = os.path.dirname(__file__)

_shortcut_actions: dict[str, list[object]] = {}
_topic_postpone_timer: QTimer | None = None
_item_skip_timer: QTimer | None = None
_menu: QMenu | None = None
_direct_review_card_ids: list[int] = []
_direct_review_active = False
_timerToggleAction: QAction | None = None
_knowledge_tree_dialog = None
_configured_shortcut_filter = None
_ocr_sync_editors: "weakref.WeakSet[object]" = weakref.WeakSet()
_diagnostic_recorder: _diagnostics_mod.DiagnosticRecorder | None = None
_diagnostic_pending_final_interval: int | None = None
_command_palette_dialog = None
_onboarding_dialog = None
_activity_center_dialog = None


def configured_show_incremento_fields(cfg: dict | None = None) -> bool:
    config = cfg if cfg is not None else _load_addon_config(mw.addonManager, __name__)
    return bool(config.get("show_incremento_fields", False))


def configured_auto_create_topics_deck(cfg: dict | None = None) -> bool:
    config = cfg if cfg is not None else _load_addon_config(mw.addonManager, __name__)
    return bool(config.get("auto_create_topics_deck", True))


def configured_auto_create_topics_deck_profiles(cfg: dict | None = None) -> list[str]:
    config = cfg if cfg is not None else _load_addon_config(mw.addonManager, __name__)
    raw = config.get("auto_create_topics_deck_profiles", [])
    if isinstance(raw, str):
        parts = raw.replace(",", "\n").splitlines()
    elif isinstance(raw, (list, tuple, set)):
        parts = list(raw)
    else:
        parts = []

    names: list[str] = []
    seen: set[str] = set()
    for item in parts:
        name = str(item or "").strip()
        if not name:
            continue
        normalized = name.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        names.append(name)
    return names


def should_auto_create_topics_deck(profile_name: str, cfg: dict | None = None) -> bool:
    if not configured_auto_create_topics_deck(cfg):
        return False
    selected_profiles = configured_auto_create_topics_deck_profiles(cfg)
    if not selected_profiles:
        return True
    target = str(profile_name or "").strip().casefold()
    return bool(target) and target in {name.casefold() for name in selected_profiles}


def _track_editor_for_ocr_sync(editor) -> None:
    try:
        _ocr_sync_editors.add(editor)
    except Exception:
        pass


def _register_shortcut_action(action_id: str, action_obj) -> None:
    targets = _shortcut_actions.setdefault(action_id, [])
    if action_obj not in targets:
        targets.append(action_obj)


def _apply_shortcuts_from_config() -> None:
    cfg, _config_changed = _migrate_persisted_config(mw.addonManager, __name__)
    user_shortcuts = cfg.get("shortcuts") or {}
    runtime_shortcuts = resolved_runtime_shortcuts(user_shortcuts)

    for action_id, action_targets in _shortcut_actions.items():
        shortcut_text = runtime_shortcuts.get(action_id, "")
        seq = QKeySequence(shortcut_text) if shortcut_text else QKeySequence()
        for action_obj in action_targets:
            if hasattr(action_obj, "setShortcut"):
                action_obj.setShortcut(seq)
            elif hasattr(action_obj, "setKey"):
                action_obj.setKey(seq)


def _configured_shortcut_text(action_id: str) -> str:
    cfg = _load_addon_config(mw.addonManager, __name__)
    user_shortcuts = cfg.get("shortcuts") or {}
    runtime_shortcuts = resolved_runtime_shortcuts(user_shortcuts)
    return str(runtime_shortcuts.get(action_id, "") or "").strip()


def _event_matches_shortcut_text(event, shortcut_text: str) -> bool:
    sequence = shortcut_text.strip()
    if not sequence:
        return False
    primary = sequence.split(",", 1)[0].strip()
    if not primary:
        return False

    parts = [part.strip() for part in primary.split("+") if part.strip()]
    if not parts:
        return False

    required_modifiers = Qt.KeyboardModifier.NoModifier
    key_name = ""
    for part in parts:
        normalized = part.lower()
        if normalized in {"ctrl", "control"}:
            required_modifiers |= Qt.KeyboardModifier.ControlModifier
        elif normalized in {"alt", "option"}:
            required_modifiers |= Qt.KeyboardModifier.AltModifier
        elif normalized in {"shift"}:
            required_modifiers |= Qt.KeyboardModifier.ShiftModifier
        elif normalized in {"meta", "cmd", "command"}:
            required_modifiers |= Qt.KeyboardModifier.MetaModifier
        else:
            key_name = part

    if not key_name:
        return False

    relevant_modifiers = (
        event.modifiers()
        & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.ShiftModifier
            | Qt.KeyboardModifier.MetaModifier
        )
    )
    if relevant_modifiers != required_modifiers:
        return False

    named_keys = {
        "left": Qt.Key.Key_Left,
        "right": Qt.Key.Key_Right,
        "up": Qt.Key.Key_Up,
        "down": Qt.Key.Key_Down,
        "space": Qt.Key.Key_Space,
        "escape": Qt.Key.Key_Escape,
        "esc": Qt.Key.Key_Escape,
        "enter": Qt.Key.Key_Return,
        "return": Qt.Key.Key_Return,
        "tab": Qt.Key.Key_Tab,
    }
    named = named_keys.get(key_name.lower())
    if named is not None:
        return event.key() == named

    if len(key_name) == 1:
        char = key_name.upper()
        event_text = (event.text() or "").upper()
        if event_text == char:
            return True
        code = ord(char)
        if 65 <= code <= 90:
            return event.key() == getattr(Qt.Key, f"Key_{char}", None)
        if 48 <= code <= 57:
            return event.key() == getattr(Qt.Key, f"Key_{char}", None)

    return False


def _invoke_shortcut_action(action_id: str) -> bool:
    for action_obj in _shortcut_actions.get(action_id, []):
        try:
            if hasattr(action_obj, "trigger"):
                action_obj.trigger()
                return True
            activated = getattr(action_obj, "activated", None)
            if activated is not None and hasattr(activated, "emit"):
                activated.emit()
                return True
            triggered = getattr(action_obj, "triggered", None)
            if triggered is not None and hasattr(triggered, "emit"):
                triggered.emit()
                return True
        except Exception:
            continue
    return False


def _open_command_palette() -> None:
    """Open a searchable snapshot of currently registered Incremento actions."""
    global _command_palette_dialog
    existing = _command_palette_dialog
    if existing is not None:
        try:
            if existing.isVisible():
                existing.raise_()
                existing.activateWindow()
                return
        except Exception:
            _command_palette_dialog = None

    cfg = _load_addon_config(mw.addonManager, __name__)
    runtime_shortcuts = resolved_runtime_shortcuts(cfg.get("shortcuts") or {})
    commands = build_palette_commands(
        [spec for spec in localized_shortcut_action_specs() if spec.get("id") != "command_palette"],
        _shortcut_actions,
        runtime_shortcuts,
        invoke=_invoke_shortcut_action,
        unavailable_reasons={
            "search_current_document": _t("root_palette_open_document"),
            "pdf_prev_page": _t("root_palette_open_pdf_pages"),
            "pdf_next_page": _t("root_palette_open_pdf_pages"),
            "pdf_zoom_out": _t("root_palette_open_pdf_zoom"),
            "pdf_zoom_in": _t("root_palette_open_pdf_zoom"),
            "pdf_mark_read": _t("root_palette_open_pdf_read"),
            "extract_card": _t("root_palette_open_reader_extract"),
        },
    )
    dialog = create_command_palette_dialog(mw, commands)
    _command_palette_dialog = dialog

    def _clear_palette(*_args) -> None:
        global _command_palette_dialog
        if _command_palette_dialog is dialog:
            _command_palette_dialog = None

    try:
        dialog.finished.connect(_clear_palette)
    except Exception:
        pass
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()


def _open_activity_center() -> None:
    global _activity_center_dialog
    existing = _activity_center_dialog
    if existing is not None:
        try:
            if existing.isVisible():
                existing.raise_()
                existing.activateWindow()
                return
        except Exception:
            _activity_center_dialog = None
    dialog = create_activity_center_dialog(mw)
    _activity_center_dialog = dialog

    def _clear(*_args) -> None:
        global _activity_center_dialog
        if _activity_center_dialog is dialog:
            _activity_center_dialog = None

    try:
        dialog.finished.connect(_clear)
    except Exception:
        pass
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()


class _ConfiguredShortcutFilter(QObject):
    def eventFilter(self, watched, event):
        try:
            if event.type() not in (
                QEvent.Type.ShortcutOverride,
                QEvent.Type.KeyPress,
            ):
                return False

            for action_id in tuple(_shortcut_actions.keys()):
                configured_text = _configured_shortcut_text(action_id)
                if not configured_text:
                    continue
                if not _event_matches_shortcut_text(event, configured_text):
                    continue

                event.accept()
                if event.type() == QEvent.Type.KeyPress:
                    return _invoke_shortcut_action(action_id)
                return True
            return False
        except Exception:
            return False


_ORIGINAL_REVIEWER_AFTER_ANSWERING = _anki_compat.original_reviewer_method(
    Reviewer, "_after_answering"
)


def _incremento_after_answering(self, ease: int) -> None:
    if not configured_show_priority_dialog_after_answer():
        _ORIGINAL_REVIEWER_AFTER_ANSWERING(self, ease)
        return

    original_next_card = self.nextCard

    def _next_card_with_priority_dialog() -> None:
        try:
            _open_priority_dialog_for_card(getattr(self, "card", None))
        except Exception as e:
            print(f"[Incremento] post-answer priority dialog error: {e}")
        original_next_card()

    self.nextCard = _next_card_with_priority_dialog
    try:
        _ORIGINAL_REVIEWER_AFTER_ANSWERING(self, ease)
    finally:
        self.nextCard = original_next_card


_anki_compat.install_reviewer_patch(
    Reviewer, "_after_answering", _incremento_after_answering
)

_ORIGINAL_REVIEWER_BUTTON_TIME = _anki_compat.original_reviewer_method(
    Reviewer, "_buttonTime"
)
_ORIGINAL_REVIEWER_DEFAULT_EASE = _anki_compat.original_reviewer_method(
    Reviewer, "_defaultEase"
)
_ORIGINAL_REVIEWER_SHORTCUT_KEYS = _anki_compat.original_reviewer_method(
    Reviewer, "_shortcutKeys"
)
_ORIGINAL_REVIEWER_ON_ENTER_KEY = _anki_compat.original_reviewer_method(
    Reviewer, "onEnterKey"
)
_ORIGINAL_REVIEWER_NEXT_CARD = _anki_compat.original_reviewer_method(
    Reviewer, "nextCard"
)
_ORIGINAL_REVIEWER_OP_EXECUTED = _anki_compat.original_reviewer_method(
    Reviewer, "op_executed"
)
_ORIGINAL_REVIEWER_SHOW_ANSWER_BUTTON = _anki_compat.original_reviewer_method(
    Reviewer, "_showAnswerButton"
)
_ORIGINAL_REVIEWER_SHOW_EASE_BUTTONS = _anki_compat.original_reviewer_method(
    Reviewer, "_showEaseButtons"
)
_ORIGINAL_REVIEWER_LINK_HANDLER = _anki_compat.original_reviewer_method(
    Reviewer, "_linkHandler"
)


def _reviewer_topic_card(card) -> bool:
    return _reviewer_button_mode_for_card(card) == "topic"


_topic_review_actions = TopicReviewActions(
    _reviewer_topic_card,
    _paths.get_active_profile,
    lambda: _configured_topic_done_tag(_load_addon_config(mw.addonManager, __name__)),
)


def _reviewer_items_fail_pass(card) -> bool:
    return _reviewer_button_mode_for_card(card) == "items_fail_pass"


def _reviewer_topic_postpone_enabled(card) -> bool:
    return _reviewer_topic_card(card) and _configured_topic_postpone_enabled()


def _reviewer_item_skip_enabled(card) -> bool:
    return bool(card is not None and not _reviewer_topic_card(card) and _configured_item_skip_enabled())


def _current_answer_button_count(card) -> int:
    if card is None:
        return 4
    try:
        return int(mw.col.sched.answerButtons(card))
    except Exception:
        return 4


def _topic_review_buttons(_buttons, _reviewer, card):
    if _reviewer_topic_card(card):
        return TOPIC_REVIEW_BUTTONS
    if _reviewer_items_fail_pass(card):
        return _item_fail_pass_buttons(_current_answer_button_count(card), card)
    return _buttons


def _perform_topic_postpone(reviewer, card) -> None:
    action_failed = False

    def _failed(stage: str, exc: Exception) -> None:
        nonlocal action_failed
        action_failed = True
        _record_diagnostic_event(
            "review_action_failed",
            action="topic_postpone",
            stage=stage,
            error_type=type(exc).__name__,
        )

    try:
        mode = _configured_topic_postpone_mode()
        if mode == "session":
            _postpone_topic_card(card, mode="session", bury=False)
    except Exception as e:
        _failed("requested", e)
        print(f"[Incremento] topic postpone error: {e}")
        try:
            _anki_compat.advance_reviewer(reviewer)
        except Exception as advance_error:
            _failed("advance", advance_error)
        return

    def _after_bury(_changes) -> None:
        if mode == "timed":
            try:
                _store_timed_topic_postpone(
                    card,
                    minutes=_configured_topic_postpone_minutes(),
                    bury=False,
                )
            except Exception as e:
                _failed("store", e)
                print(f"[Incremento] topic postpone timed save error: {e}")
            try:
                _schedule_topic_postpone_timer()
            except Exception as e:
                _failed("timer", e)
                print(f"[Incremento] topic postpone timer error: {e}")
        try:
            if mode == "session":
                tooltip(_t("root_topic_postponed_session"))
            else:
                tooltip(
                    _t("root_topic_postponed_minutes", minutes=_configured_topic_postpone_minutes())
                )
        except Exception:
            pass
        try:
            current = getattr(reviewer, "card", None)
            if current is not None and getattr(current, "id", None) == getattr(card, "id", None):
                _anki_compat.advance_reviewer(reviewer)
        except Exception as e:
            _failed("advance", e)
            print(f"[Incremento] topic postpone nextCard error: {e}")
        if not action_failed:
            _record_diagnostic_event(
                "review_action_completed",
                action="topic_postpone",
                stage="completed",
            )

    def _after_bury_failure(exc: Exception) -> None:
        _failed("bury", exc)
        print(f"[Incremento] topic postpone bury error: {exc}")
        show_exception(parent=reviewer.mw, exception=exc)

    try:
        (
            _bury_cards_op(parent=reviewer.mw, card_ids=[card.id])
            .success(_after_bury)
            .failure(_after_bury_failure)
            .run_in_background()
        )
    except Exception as e:
        _failed("bury", e)
        print(f"[Incremento] topic postpone bury error: {e}")
        try:
            _anki_compat.advance_reviewer(reviewer)
        except Exception as advance_error:
            _failed("advance", advance_error)


def _perform_item_skip(reviewer, card) -> None:
    action_failed = False

    def _failed(stage: str, exc: Exception) -> None:
        nonlocal action_failed
        action_failed = True
        _record_diagnostic_event(
            "review_action_failed",
            action="item_skip",
            stage=stage,
            error_type=type(exc).__name__,
        )

    try:
        _store_timed_item_skip(
            card,
            minutes=_configured_item_skip_minutes(),
            bury=False,
        )
    except Exception as e:
        _failed("store", e)
        print(f"[Incremento] item skip error: {e}")
    try:
        _schedule_item_skip_timer()
    except Exception as e:
        _failed("timer", e)
        print(f"[Incremento] item skip timer error: {e}")
    try:
        tooltip(_t("root_item_skipped_minutes", minutes=_configured_item_skip_minutes()))
    except Exception:
        pass
    try:
        current = getattr(reviewer, "card", None)
        if current is not None and getattr(current, "id", None) == getattr(card, "id", None):
            _anki_compat.advance_reviewer(reviewer)
    except Exception as e:
        _failed("advance", e)
        print(f"[Incremento] item skip nextCard error: {e}")
    if not action_failed:
        _record_diagnostic_event(
            "review_action_completed",
            action="item_skip",
            stage="completed",
        )


def _perform_item_skip_after_bury(reviewer, card) -> None:
    def _after_bury(_changes) -> None:
        _perform_item_skip(reviewer, card)

    def _after_bury_failure(exc: Exception) -> None:
        _record_diagnostic_event(
            "review_action_failed",
            action="item_skip",
            stage="bury",
            error_type=type(exc).__name__,
        )
        print(f"[Incremento] item skip bury error: {exc}")
        show_exception(parent=reviewer.mw, exception=exc)

    try:
        (
            _bury_cards_op(parent=reviewer.mw, card_ids=[card.id])
            .success(_after_bury)
            .failure(_after_bury_failure)
            .run_in_background()
        )
    except Exception as e:
        _record_diagnostic_event(
            "review_action_failed",
            action="item_skip",
            stage="bury",
            error_type=type(e).__name__,
        )
        print(f"[Incremento] item skip bury error: {e}")
        try:
            _anki_compat.advance_reviewer(reviewer)
        except Exception as advance_error:
            _record_diagnostic_event(
                "review_action_failed",
                action="item_skip",
                stage="advance",
                error_type=type(advance_error).__name__,
            )


def _reset_collection_after_queue_change() -> None:
    try:
        mw.col.reset()
    except Exception:
        pass


def _reviewer_has_active_card() -> bool:
    try:
        reviewer = getattr(mw, "reviewer", None)
        return (
            getattr(mw, "state", None) == "review"
            and getattr(reviewer, "card", None) is not None
        )
    except Exception:
        return False


def _release_expired_topic_postpones_now(*, refresh: bool = True) -> list[int]:
    try:
        restored_ids = _release_expired_timed_postpones()
    except Exception:
        restored_ids = []
    if not restored_ids:
        return []
    if refresh:
        try:
            mw.reset()
        except Exception:
            pass
    else:
        _reset_collection_after_queue_change()
    return restored_ids


def _release_expired_item_skips_now(*, refresh: bool = True) -> list[int]:
    try:
        restored_ids = _release_expired_timed_item_skips()
    except Exception:
        restored_ids = []
    if not restored_ids:
        return []
    if refresh:
        try:
            mw.reset()
        except Exception:
            pass
    else:
        _reset_collection_after_queue_change()
    return restored_ids


def _ensure_topic_postpone_timer() -> QTimer:
    global _topic_postpone_timer
    if _topic_postpone_timer is None:
        _topic_postpone_timer = QTimer(mw)
        _topic_postpone_timer.setSingleShot(False)
        _topic_postpone_timer.setInterval(1000)
        _topic_postpone_timer.timeout.connect(_on_topic_postpone_timer_timeout)
    return _topic_postpone_timer


def _schedule_topic_postpone_timer() -> None:
    try:
        next_until = _next_timed_postpone_at()
    except Exception:
        next_until = None

    timer = _ensure_topic_postpone_timer()
    if next_until is None:
        timer.stop()
        return

    if not timer.isActive():
        timer.start()


def _ensure_item_skip_timer() -> QTimer:
    global _item_skip_timer
    if _item_skip_timer is None:
        _item_skip_timer = QTimer(mw)
        _item_skip_timer.setSingleShot(False)
        _item_skip_timer.setInterval(1000)
        _item_skip_timer.timeout.connect(_on_item_skip_timer_timeout)
    return _item_skip_timer


def _schedule_item_skip_timer() -> None:
    try:
        next_until = _next_timed_item_skip_at()
    except Exception:
        next_until = None

    timer = _ensure_item_skip_timer()
    if next_until is None:
        timer.stop()
        return

    if not timer.isActive():
        timer.start()


def _on_topic_postpone_timer_timeout() -> None:
    try:
        restored_ids = _release_expired_topic_postpones_now(
            refresh=not _reviewer_has_active_card()
        )
    except Exception:
        restored_ids = []

    try:
        if _next_timed_postpone_at() is None:
            _ensure_topic_postpone_timer().stop()
    except Exception:
        pass

    if not restored_ids:
        return


def _on_item_skip_timer_timeout() -> None:
    try:
        restored_ids = _release_expired_item_skips_now(
            refresh=not _reviewer_has_active_card()
        )
    except Exception:
        restored_ids = []

    try:
        if _next_timed_item_skip_at() is None:
            _ensure_item_skip_timer().stop()
    except Exception:
        pass

    if not restored_ids:
        return


def _release_expired_topic_postpones_on_overview(new_state: str, _old_state: str) -> None:
    if new_state != "overview":
        return
    try:
        _release_expired_topic_postpones_now()
    except Exception:
        pass
    try:
        _schedule_topic_postpone_timer()
    except Exception:
        pass


def _release_expired_item_skips_on_overview(new_state: str, _old_state: str) -> None:
    if new_state != "overview":
        return
    try:
        _release_expired_item_skips_now()
    except Exception:
        pass
    try:
        _schedule_item_skip_timer()
    except Exception:
        pass


def _topic_reviewer_will_answer_card(response, _reviewer, card):
    proceed, ease = response
    if not proceed:
        return response
    if _reviewer_topic_card(card):
        if (
            _configured_topic_postpone_enabled()
            and int(ease) == _TOPIC_POSTPONE_EASE
        ):
            QTimer.singleShot(0, lambda r=_reviewer, c=card: _perform_topic_postpone(r, c))
            return (False, ease)
        return (proceed, _prepare_topic_answer(card, ease))
    _prepare_custom_schedule_answer(card)
    if _reviewer_items_fail_pass(card):
        return (proceed, _remap_item_fail_pass_ease(card, ease))
    return response


def _direct_review_v3_info(card):
    try:
        return _anki_compat.build_direct_review_v3_info(
            mw.col,
            card,
            [int(card.id), *_direct_review_card_ids]
        )
    except Exception as exc:
        _record_diagnostic_event(
            "explicit_review_failed",
            source="selected_cards",
            content_kind="other",
            stage="review",
            error_type=type(exc).__name__,
        )
        print(f"[Incremento] direct review queue build error: {exc}")
        return None


def _take_direct_review_card():
    global _direct_review_active
    if not _direct_review_active:
        return False, None, None

    while _direct_review_card_ids:
        card_id = _direct_review_card_ids.pop(0)
        try:
            card = mw.col.get_card(int(card_id))
        except Exception:
            card = None
        if card is None:
            continue
        try:
            if int(getattr(card, "queue", 0) or 0) < 0:
                continue
        except Exception:
            continue
        v3_info = _direct_review_v3_info(card)
        if v3_info is None:
            continue
        try:
            card.start_timer()
        except Exception:
            pass
        return True, card, v3_info

    _direct_review_active = False
    _record_diagnostic_event(
        "explicit_review_ended",
        source="selected_cards",
        content_kind="other",
    )
    return True, None, None


def _clear_direct_review_queue(*_args, **_kwargs) -> None:
    global _direct_review_active
    was_active = _direct_review_active
    _direct_review_card_ids.clear()
    _direct_review_active = False
    if was_active and bool(_kwargs.get("emit_diagnostic", True)):
        _record_diagnostic_event(
            "explicit_review_ended",
            source="selected_cards",
            content_kind="other",
        )


def _incremento_button_time(self, ease: int, v3_labels) -> str:
    card = getattr(self, "card", None)
    if _reviewer_items_fail_pass(card):
        return _ORIGINAL_REVIEWER_BUTTON_TIME(
            self,
            _remap_item_fail_pass_ease(card, ease),
            v3_labels,
        )
    if not _reviewer_topic_card(card):
        return _ORIGINAL_REVIEWER_BUTTON_TIME(self, ease, v3_labels)
    if not self.mw.col.conf.get("estTimes"):
        return ""
    label = _topic_due_label(card, ease)
    return f'<span class="nobold">{label}</span>' if label else ""


def _incremento_default_ease(self) -> int:
    card = getattr(self, "card", None)
    if _reviewer_topic_card(card):
        return 2
    if _reviewer_items_fail_pass(card):
        return 2
    return _ORIGINAL_REVIEWER_DEFAULT_EASE(self)


def _shortcut_callback_uses_on_enter(self, callback) -> bool:
    try:
        callback_func = getattr(callback, "__func__", None)
        return (
            getattr(callback, "__self__", None) is self
            and callback_func
            in {
                getattr(self.onEnterKey, "__func__", None),
                _ORIGINAL_REVIEWER_ON_ENTER_KEY,
            }
        )
    except Exception:
        return False


def _incremento_shortcut_keys(self):
    shortcuts = list(_ORIGINAL_REVIEWER_SHORTCUT_KEYS(self))
    card = getattr(self, "card", None)
    if not (_reviewer_topic_card(card) or _reviewer_items_fail_pass(card)):
        return shortcuts

    hidden_answer_keys: set[str] = set()
    try:
        if _reviewer_topic_card(card):
            key = str(mw.pm.get_answer_key(4) or "")
            if key:
                hidden_answer_keys.add(key)
        elif _reviewer_items_fail_pass(card):
            visible_eases = {
                1,
                2,
            }
            for ease in (1, 2, 3, 4):
                key = str(mw.pm.get_answer_key(ease) or "")
                if key and ease not in visible_eases:
                    hidden_answer_keys.add(key)
    except Exception:
        hidden_answer_keys = set()

    return filter_reviewer_shortcuts(
        shortcuts,
        state=str(getattr(self, "state", "") or ""),
        hidden_answer_keys=hidden_answer_keys,
        is_on_enter_callback=lambda callback: _shortcut_callback_uses_on_enter(
            self, callback
        ),
    )


def _incremento_on_enter_key(self) -> None:
    card = getattr(self, "card", None)
    if (
        self.state == "answer"
        and _reviewer_topic_card(card)
        and mw.pm.spacebar_rates_card()
    ):
        try:
            _anki_compat.answer_reviewer_card(self, 2)
        except _anki_compat.AnkiCompatibilityError:
            _ORIGINAL_REVIEWER_ON_ENTER_KEY(self)
        return
    if (
        self.state == "answer"
        and _reviewer_items_fail_pass(card)
        and mw.pm.spacebar_rates_card()
    ):
        try:
            _anki_compat.answer_reviewer_card(self, 2)
        except _anki_compat.AnkiCompatibilityError:
            _ORIGINAL_REVIEWER_ON_ENTER_KEY(self)
        return
    _ORIGINAL_REVIEWER_ON_ENTER_KEY(self)


def _incremento_next_card(self) -> None:
    try:
        _release_expired_topic_postpones_now(refresh=False)
    except Exception:
        pass
    try:
        _schedule_topic_postpone_timer()
    except Exception:
        pass
    try:
        _release_expired_item_skips_now(refresh=False)
    except Exception:
        pass
    try:
        _schedule_item_skip_timer()
    except Exception:
        pass

    self.previous_card = self.card
    self.card = None
    self._v3 = None
    direct_handled, direct_card, direct_v3 = _take_direct_review_card()
    if direct_card is not None:
        self.card = direct_card
        self._v3 = direct_v3
    elif direct_handled:
        self.card = None
    else:
        _anki_compat.fetch_next_v3_card(self)

    if (
        not direct_handled
        and not self.card
        and _has_session_postponed_cards()
    ):
        try:
            restored_ids = _release_session_postponed_cards()
        except Exception:
            restored_ids = []
        if restored_ids:
            _anki_compat.fetch_next_v3_card(self)

    _anki_compat.update_reviewer_card_info(self)

    if not self.card:
        self.mw.moveToState("overview")
        return

    if self._reps is None:
        _anki_compat.initialize_reviewer_web(self)

    _anki_compat.show_reviewer_question(self)


def _incremento_op_executed(self, changes, handler, focused) -> bool:
    try:
        if getattr(changes, "study_queues", False):
            card = getattr(self, "card", None)
            card_id = int(card.id) if card is not None else None
            if _add_card_dock_mod.consume_reviewer_extract_queue_refresh_suppression(
                card_id
            ):
                return False
    except Exception:
        pass
    return _ORIGINAL_REVIEWER_OP_EXECUTED(self, changes, handler, focused)


def _incremento_show_answer_button(self) -> None:
    card = getattr(self, "card", None)
    if not _reviewer_topic_postpone_enabled(card):
        if not _reviewer_item_skip_enabled(card):
            _ORIGINAL_REVIEWER_SHOW_ANSWER_BUTTON(self)
            _sync_reviewer_extract_button(self)
            return
        show_answer_key = tr.actions_shortcut_key(val=tr.studying_space())
        skip_due = _item_skip_due_label()
        middle = """
<table cellpadding=0 cellspacing=8><tr>
<td class=stat2 align=center>
<button title="{show_answer_key}" id="ansbut" onclick='pycmd("ans");'>{show_answer}<span class=stattxt>{remaining}</span></button>
</td>
<td class=stat2 align=center>
<button id="incremento-item-skip-but" onclick='pycmd("incremento_item_skip");'>{skip_label}<span class=stattxt>{skip_due}</span></button>
</td>
</tr></table>
""".format(
            show_answer_key=show_answer_key,
            show_answer=tr.studying_show_answer(),
            remaining=self._remaining(),
            skip_due=skip_due,
            skip_label=_t("root_reviewer_skip"),
        )
        if self.card.should_show_timer():
            maxTime = self.card.time_limit() / 1000
        else:
            maxTime = 0
        self.bottom.web.eval("showQuestion(%s,%d);" % (json.dumps(middle), maxTime))
        _sync_reviewer_extract_button(self)
        return

    show_answer_key = tr.actions_shortcut_key(val=tr.studying_space())
    postpone_key = ""
    try:
        raw_key = str(mw.pm.get_answer_key(_TOPIC_POSTPONE_EASE) or "")
        if raw_key:
            postpone_key = tr.actions_shortcut_key(val=raw_key)
    except Exception:
        postpone_key = ""

    postpone_due = _topic_postpone_due_label()
    middle = """
<table cellpadding=0 cellspacing=8><tr>
<td class=stat2 align=center>
<button title="{show_answer_key}" id="ansbut" onclick='pycmd("ans");'>{show_answer}<span class=stattxt>{remaining}</span></button>
</td>
<td class=stat2 align=center id="incremento-topic-postpone-cell">
<button title="{postpone_key}" id="incremento-postpone-but" onclick='pycmd("incremento_topic_postpone");'>{postpone_label}<span class=stattxt>{postpone_due}</span></button>
</td>
</tr></table>
""".format(
        show_answer_key=show_answer_key,
        show_answer=tr.studying_show_answer(),
        remaining=self._remaining(),
        postpone_key=postpone_key,
        postpone_due=postpone_due,
        postpone_label=_t("settings_postpone"),
    )
    if self.card.should_show_timer():
        maxTime = self.card.time_limit() / 1000
    else:
        maxTime = 0
    self.bottom.web.eval("showQuestion(%s,%d);" % (json.dumps(middle), maxTime))
    _sync_reviewer_extract_button(self)


def _sync_topic_answer_button_style(reviewer) -> None:
    try:
        enabled = json.dumps(_reviewer_topic_card(getattr(reviewer, "card", None)))
        reviewer.bottom.web.eval(
            """
            (function() {
              var enabled = %s;
              var styleId = "incremento-topic-answer-button-style";
              var style = document.getElementById(styleId);
              var attempts = 0;
              function apply() {
                var buttons = document.querySelectorAll('button[data-ease]');
                if (!buttons.length) {
                  attempts += 1;
                  if (attempts < 10) {
                    setTimeout(apply, 40);
                  }
                  return;
                }
                if (!enabled) {
                  if (style) {
                    style.remove();
                  }
                  return;
                }
                if (!style) {
                  style = document.createElement("style");
                  style.id = styleId;
                  style.textContent = `
                    button[data-ease="1"] {
                      background: rgba(160, 92, 92, 0.12) !important;
                      border-color: rgba(160, 92, 92, 0.32) !important;
                      color: #d8b0b0 !important;
                    }
                    button[data-ease="1"]:hover,
                    button[data-ease="1"]:focus {
                      background: rgba(160, 92, 92, 0.18) !important;
                      border-color: rgba(160, 92, 92, 0.42) !important;
                      color: #e3bebe !important;
                    }
                    button[data-ease="3"] {
                      background: rgba(92, 124, 170, 0.12) !important;
                      border-color: rgba(92, 124, 170, 0.32) !important;
                      color: #b7c7df !important;
                    }
                    button[data-ease="3"]:hover,
                    button[data-ease="3"]:focus {
                      background: rgba(92, 124, 170, 0.18) !important;
                      border-color: rgba(92, 124, 170, 0.42) !important;
                      color: #c7d5ea !important;
                    }
                  `;
                  document.head.appendChild(style);
                }
              }
              if (!enabled) {
                if (style) {
                  style.remove();
                }
                return;
              }
              apply();
            })();
            """
            % enabled
        )
    except Exception:
        pass


def _sync_reviewer_extract_button(reviewer) -> None:
    try:
        reviewer.bottom.web.eval(build_reviewer_button_style_js())
    except Exception:
        pass
    _sync_reviewer_button_visibility(reviewer)
    try:
        reviewer.bottom.web.eval(
            build_reviewer_extract_button_js(_configured_shortcut_text("extract_card"))
        )
    except Exception:
        pass
    try:
        _topic_review_actions.sync(reviewer)
    except Exception:
        pass


def _sync_reviewer_button_visibility(reviewer) -> None:
    try:
        cfg = _load_addon_config(mw.addonManager, __name__)
        reviewer.bottom.web.eval(
            build_reviewer_button_visibility_js(
                effective_reviewer_button_visibility(
                    configured_reviewer_button_visibility(cfg),
                    configured_reviewer_button_group_visible(cfg),
                )
            )
        )
    except Exception:
        pass


def _add_reviewer_button_visibility_menu(reviewer, menu) -> None:
    if mw.state != "review" or mw.reviewer is not reviewer or reviewer.card is None:
        return
    profile = _active_profile()
    config = _load_addon_config(mw.addonManager, __name__)
    menu.addSeparator()

    def on_toggle(key: str, checked: bool) -> None:
        if (
            mw.state != "review" or mw.reviewer is not reviewer
            or reviewer.card is None or _active_profile() != profile
        ):
            return
        updated = _load_addon_config(mw.addonManager, __name__)
        visibility = dict(updated.get("reviewer_button_visibility") or {})
        visibility[key] = checked
        updated["reviewer_button_visibility"] = visibility
        _save_addon_config(mw.addonManager, __name__, updated)
        _sync_reviewer_button_visibility(reviewer)

    def on_group_toggle(checked: bool) -> None:
        if (
            mw.state != "review" or mw.reviewer is not reviewer
            or reviewer.card is None or _active_profile() != profile
        ):
            return
        updated = _load_addon_config(mw.addonManager, __name__)
        updated["reviewer_button_group_visible"] = checked
        _save_addon_config(mw.addonManager, __name__, updated)
        _sync_reviewer_button_visibility(reviewer)

    add_reviewer_button_visibility_menu(
        menu, configured_reviewer_button_visibility(config), on_toggle,
        group_visible=configured_reviewer_button_group_visible(config),
        on_group_toggle=on_group_toggle,
    )


def _toggle_reviewer_button_group() -> None:
    reviewer = getattr(mw, "reviewer", None)
    if mw.state != "review" or reviewer is None or reviewer.card is None:
        return
    cfg = _load_addon_config(mw.addonManager, __name__)
    cfg["reviewer_button_group_visible"] = not configured_reviewer_button_group_visible(cfg)
    _save_addon_config(mw.addonManager, __name__, cfg)
    _sync_reviewer_button_visibility(reviewer)


def _incremento_show_ease_buttons(self) -> None:
    _ORIGINAL_REVIEWER_SHOW_EASE_BUTTONS(self)
    _sync_topic_answer_button_style(self)
    _sync_reviewer_extract_button(self)


def _incremento_link_handler(self, url: str) -> None:
    if _topic_review_actions.handle_command(self, url):
        return
    if url == "incremento_extract_card":
        _extract_card()
        return
    if url == "incremento_topic_postpone":
        card = getattr(self, "card", None)
        if self.state == "question" and _reviewer_topic_postpone_enabled(card):
            _perform_topic_postpone(self, card)
            return
    if url == "incremento_item_skip":
        card = getattr(self, "card", None)
        if self.state == "question" and _reviewer_item_skip_enabled(card):
            _perform_item_skip_after_bury(self, card)
            return
    _ORIGINAL_REVIEWER_LINK_HANDLER(self, url)


for _reviewer_method_name, _reviewer_replacement in (
    ("_buttonTime", _incremento_button_time),
    ("_defaultEase", _incremento_default_ease),
    ("_shortcutKeys", _incremento_shortcut_keys),
    ("onEnterKey", _incremento_on_enter_key),
    ("nextCard", _incremento_next_card),
    ("op_executed", _incremento_op_executed),
    ("_showAnswerButton", _incremento_show_answer_button),
    ("_showEaseButtons", _incremento_show_ease_buttons),
    ("_linkHandler", _incremento_link_handler),
):
    if (
        _reviewer_method_name == "nextCard"
        and not _anki_compat.custom_next_card_supported(Reviewer)
    ):
        continue
    _anki_compat.install_reviewer_patch(
        Reviewer, _reviewer_method_name, _reviewer_replacement
    )


mw.addonManager.setWebExports(__name__, r"web/.*")

# Last cards opened via the Quick Open dialog (used by Ctrl+L).
_last_opened_pdf_cid: int | None = None
_last_opened_writing_cid: int | None = None
_last_opened_document_cid: int | None = None


# Wire add_card_dock callbacks to pdf_dock.
_pdf_dock_mod.register_add_card_callbacks(
    _add_card_dock_mod.open_add_card_dock,
    _add_card_dock_mod.fill_dock_field,
    _add_card_dock_mod.get_add_card_dock,
)
_epub_dock_mod.register_add_card_callbacks(
    _add_card_dock_mod.open_add_card_dock,
    _add_card_dock_mod.fill_dock_field,
    _add_card_dock_mod.get_add_card_dock,
)
_pdf_dock_mod.register_pdf_view_callbacks(
    _review_time_mod.on_pdf_view_started,
    _review_time_mod.on_pdf_view_stopped,
)
_epub_dock_mod.register_epub_view_callbacks(
    _review_time_mod.on_pdf_view_started,
    _review_time_mod.on_pdf_view_stopped,
)


def _browser_selected_incremento_card_ids(browser) -> list[int]:
    card_ids: list[int] = []
    seen: set[int] = set()

    def _add_card_id(raw_card_id) -> None:
        try:
            card_id = int(raw_card_id)
        except Exception:
            return
        if card_id in seen:
            return
        seen.add(card_id)
        card_ids.append(card_id)

    for method_name in ("selected_cards", "selectedCards"):
        method = getattr(browser, method_name, None)
        if not callable(method):
            continue
        try:
            for card_id in list(method() or []):
                _add_card_id(card_id)
        except Exception:
            pass

    for method_name in ("selected_notes", "selectedNotes"):
        method = getattr(browser, method_name, None)
        if not callable(method):
            continue
        try:
            note_ids = list(method() or [])
        except Exception:
            note_ids = []
        for raw_note_id in note_ids:
            try:
                note_id = int(raw_note_id)
                note_card_ids = mw.col.find_cards(f"nid:{note_id}")
            except Exception:
                note_card_ids = []
            for card_id in note_card_ids:
                _add_card_id(card_id)

    return card_ids


def _convert_browser_selection_to_knowledge_kind(browser, node_kind: str) -> None:
    card_ids = _browser_selected_incremento_card_ids(browser)
    if not card_ids:
        showInfo(_t("root_browser_select_rows"))
        return

    result = _kt_apply_node_kind_to_cards(card_ids, node_kind)
    changed_count = int(result.get("changed_count") or 0)
    error_count = int(result.get("error_count") or 0)
    kind_key = (
        "root_browser_cards_to_topics"
        if node_kind == _KT_NODE_KIND_TOPIC
        else "root_browser_cards_to_items"
    )

    try:
        mw.col.reset()
    except Exception:
        pass
    try:
        browser.search()
    except Exception:
        pass

    converted = _tn(kind_key, changed_count)
    if error_count:
        showInfo(_t("root_browser_conversion_partial", converted=converted, failed=_tn("root_browser_failed_cards", error_count)))
        return
    tooltip(_t("root_browser_conversion_done", converted=converted))


def _open_custom_schedule_dialog(card_ids: list[int]) -> None:
    normalized_ids = sorted({int(card_id) for card_id in (card_ids or [])})
    if not normalized_ids:
        showInfo(_t("root_browser_select_rows"))
        return

    cfg = _load_addon_config(mw.addonManager, __name__)
    dlg = CustomScheduleDialog(
        _ADDON_DIR,
        normalized_ids,
        config=cfg,
        parent=mw,
    )
    if not dlg.exec():
        return

    if dlg.clear_requested:
        cleared = _clear_custom_schedule_rules(normalized_ids)
        tooltip(_tn("root_browser_schedule_cleared", cleared))
        return

    rule = dlg.selected_rule
    updated = _save_custom_schedule_rule(
        normalized_ids,
        mode=str(rule.get("mode") or ""),
        interval_value=int(rule.get("interval_value") or 0),
        interval_unit=str(rule.get("interval_unit") or ""),
        preset_label=str(rule.get("preset_label") or ""),
    )
    applied_now = 0
    if dlg.apply_now:
        for card_id in normalized_ids:
            try:
                applied_now += 1 if _apply_custom_schedule_now_to_card(int(card_id), rule) else 0
            except Exception:
                pass

    summary = _format_custom_schedule_rule(rule)
    if dlg.apply_now:
        tooltip(_t("root_browser_schedule_saved_applied", summary=summary, saved=_tn("root_browser_schedule_saved_cards", updated), applied=applied_now))
    else:
        tooltip(_t("root_browser_schedule_saved", summary=summary, saved=_tn("root_browser_schedule_saved_cards", updated)))


def _open_browser_a_factor_dialog(browser, card_ids: list[int]) -> None:
    normalized_ids = sorted({int(card_id) for card_id in (card_ids or [])})
    if not normalized_ids:
        showInfo(_t("root_browser_select_rows"))
        return

    value, accepted = QInputDialog.getDouble(
        mw,
        _t("root_browser_a_factor_title"),
        _t("root_browser_a_factor_label"),
        3.5,
        1.1,
        100.0,
        3,
    )
    if not accepted:
        return

    try:
        result = _apply_bulk_topic_a_factor(
            _ADDON_DIR,
            _active_profile(),
            normalized_ids,
            value,
            get_card=mw.col.get_card,
            is_topic_card=_is_topic_card,
        )
    except ValueError as exc:
        showInfo(str(exc))
        return

    updated = int(result.get("updated") or 0)
    skipped = int(result.get("skipped") or 0)
    errors = int(result.get("errors") or 0)
    if not updated:
        if errors:
            showInfo(_t("root_browser_a_factor_no_updates_error", failed=_tn("root_browser_failed_cards", errors)))
        else:
            showInfo(_t("root_browser_no_topic_cards"))
        return

    try:
        mw.col.reset()
    except Exception:
        pass
    try:
        browser.search()
    except Exception:
        pass

    msg = _t("root_browser_a_factor_set", value=f"{float(value):.3f}", updated=_tn("root_browser_topic_cards", updated))
    if skipped:
        msg += " " + _tn("root_browser_skipped_non_topic", skipped)
    if errors:
        msg += " " + _tn("root_browser_failed_cards", errors) + "."
    tooltip(msg)


def _browser_selected_pdf_card_ids(browser) -> tuple[list[int], int]:
    selected_card_ids = _browser_selected_incremento_card_ids(browser)
    if not selected_card_ids:
        return [], 0

    pdf_card_ids: list[int] = []
    skipped = 0
    seen_notes: set[int] = set()
    for raw_card_id in selected_card_ids:
        try:
            card = mw.col.get_card(int(raw_card_id))
        except Exception:
            skipped += 1
            continue
        if card is None:
            skipped += 1
            continue
        try:
            note = mw.col.get_note(card.nid)
            model = mw.col.models.get(note.mid)
            model_name = str((model or {}).get("name") or "")
        except Exception:
            skipped += 1
            continue
        if model_name != PDF_NOTE_TYPE:
            skipped += 1
            continue
        note_id = int(getattr(card, "nid", 0) or 0)
        if note_id > 0 and note_id in seen_notes:
            continue
        if note_id > 0:
            seen_notes.add(note_id)
        pdf_card_ids.append(int(card.id))
    return pdf_card_ids, skipped


def _browser_selected_epub_card_ids(browser) -> tuple[list[int], int]:
    selected_card_ids = _browser_selected_incremento_card_ids(browser)
    if not selected_card_ids:
        return [], 0

    epub_card_ids: list[int] = []
    skipped = 0
    seen_notes: set[int] = set()
    for raw_card_id in selected_card_ids:
        try:
            card = mw.col.get_card(int(raw_card_id))
        except Exception:
            skipped += 1
            continue
        if card is None:
            skipped += 1
            continue
        try:
            note = mw.col.get_note(card.nid)
            model = mw.col.models.get(note.mid)
            model_name = str((model or {}).get("name") or "")
        except Exception:
            skipped += 1
            continue
        if model_name != EPUB_NOTE_TYPE:
            skipped += 1
            continue
        note_id = int(getattr(card, "nid", 0) or 0)
        if note_id > 0 and note_id in seen_notes:
            continue
        if note_id > 0:
            seen_notes.add(note_id)
        epub_card_ids.append(int(card.id))
    return epub_card_ids, skipped


def _regenerate_pdf_covers_for_browser_selection(browser) -> None:
    pdf_card_ids, skipped = _browser_selected_pdf_card_ids(browser)
    if not pdf_card_ids:
        showInfo(_t("root_browser_no_pdf_cards"))
        return

    regenerated = 0
    cleared = 0
    failed: list[str] = []

    mw.progress.start(label=_t("root_browser_cover_progress_pdf_label"), immediate=True)
    try:
        total = len(pdf_card_ids)
        for index, card_id in enumerate(pdf_card_ids, start=1):
            try:
                mw.progress.update(label=_t("root_browser_cover_progress_pdf", index=index, total=total))
            except Exception:
                pass
            try:
                cover_filename = regenerate_pdf_card_cover(_ADDON_DIR, mw.col, int(card_id))
                if cover_filename:
                    regenerated += 1
                else:
                    cleared += 1
            except Exception as exc:
                failed.append(_t("root_browser_cover_failed_card", card_id=card_id, error=exc))
    finally:
        try:
            mw.progress.finish()
        except Exception:
            pass

    try:
        mw.col.reset()
    except Exception:
        pass
    try:
        browser.search()
    except Exception:
        pass

    if failed:
        details = "\n".join(failed[:10])
        if len(failed) > 10:
            details += "\n" + _t("root_browser_more_failures", count=len(failed) - 10)
        message = _t("root_browser_cover_summary_pdf", regenerated=_tn("root_browser_pdf_covers", regenerated), cleared=cleared)
        if skipped:
            message += " " + _tn("root_browser_skipped_non_pdf", skipped)
        message += "\n\n" + _t("root_browser_failures_heading") + "\n" + details
        showInfo(message)
        return

    message = _t("root_browser_cover_summary_pdf", regenerated=_tn("root_browser_pdf_covers", regenerated), cleared=cleared)
    if skipped:
        message += " " + _tn("root_browser_skipped_non_pdf", skipped)
    tooltip(message)


def _regenerate_epub_covers_for_browser_selection(browser) -> None:
    epub_card_ids, skipped = _browser_selected_epub_card_ids(browser)
    if not epub_card_ids:
        showInfo(_t("root_browser_no_epub_cards"))
        return

    regenerated = 0
    cleared = 0
    failed: list[str] = []

    mw.progress.start(label=_t("root_browser_cover_progress_epub_label"), immediate=True)
    try:
        total = len(epub_card_ids)
        for index, card_id in enumerate(epub_card_ids, start=1):
            try:
                mw.progress.update(label=_t("root_browser_cover_progress_epub", index=index, total=total))
            except Exception:
                pass
            try:
                cover_filename = regenerate_epub_card_cover(_ADDON_DIR, mw.col, int(card_id))
                if cover_filename:
                    regenerated += 1
                else:
                    cleared += 1
            except Exception as exc:
                failed.append(_t("root_browser_cover_failed_card", card_id=card_id, error=exc))
    finally:
        try:
            mw.progress.finish()
        except Exception:
            pass

    try:
        mw.col.reset()
    except Exception:
        pass
    try:
        browser.search()
    except Exception:
        pass

    if failed:
        details = "\n".join(failed[:10])
        if len(failed) > 10:
            details += "\n" + _t("root_browser_more_failures", count=len(failed) - 10)
        message = _t("root_browser_cover_summary_epub", regenerated=_tn("root_browser_epub_covers", regenerated), cleared=cleared)
        if skipped:
            message += " " + _tn("root_browser_skipped_non_epub", skipped)
        message += "\n\n" + _t("root_browser_failures_heading") + "\n" + details
        showInfo(message)
        return

    message = _t("root_browser_cover_summary_epub", regenerated=_tn("root_browser_epub_covers", regenerated), cleared=cleared)
    if skipped:
        message += " " + _tn("root_browser_skipped_non_epub", skipped)
    tooltip(message)


def _format_database_entry_value(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bytes):
        return repr(value)
    return str(value)


def _format_browser_database_entries(payload: dict[str, object]) -> str:
    card_ids = [int(card_id) for card_id in list(payload.get("card_ids") or [])]
    entries = list(payload.get("entries") or [])
    lines = [
        _t("root_browser_database_selected_ids") + ": " + ", ".join(str(card_id) for card_id in card_ids),
        _t("root_browser_database_profile", profile=payload.get('profile') or ''),
        _t("root_browser_database_path", path=payload.get('db_path') or ''),
    ]
    separator = "-" * 72
    for card_id in card_ids:
        card_entries = [
            entry
            for entry in entries
            if int((entry or {}).get("card_id") or 0) == int(card_id)
        ]
        lines.extend(["", separator, _t("root_browser_database_card", card_id=card_id)])
        if not card_entries:
            lines.append(_t("root_browser_database_no_rows", card_id=card_id))
            continue

        current_group = ""
        for entry in sorted(
            card_entries,
            key=lambda item: (
                str(item.get("table") or ""),
                str(item.get("column") or ""),
                int(item.get("rowid") or 0),
            ),
        ):
            group = f"{entry.get('table')}.{entry.get('column')}"
            if group != current_group:
                current_group = group
                lines.extend(["", group])
            if entry.get("virtual"):
                row_label = _t("root_browser_database_effective_values")
            else:
                rowid = entry.get("rowid")
                row_label = _t("root_browser_database_rowid", rowid=rowid) if rowid is not None else _t("root_browser_database_row")
            lines.append(f"  {row_label}")
            values = dict(entry.get("values") or {})
            columns = list(entry.get("columns") or values.keys())
            for column in columns:
                lines.append(f"    {column}: {_format_database_entry_value(values.get(column))}")
    return "\n".join(lines)


def _add_effective_topic_schedule_entries(payload: dict[str, object]) -> dict[str, object]:
    entries = list(payload.get("entries") or [])
    existing_topic_schedule_ids = {
        int((entry or {}).get("card_id") or 0)
        for entry in entries
        if str((entry or {}).get("table") or "") == "topic_schedule"
    }

    augmented = dict(payload)
    for raw_card_id in list(payload.get("card_ids") or []):
        try:
            card_id = int(raw_card_id)
            card = mw.col.get_card(card_id)
        except Exception:
            continue
        if card is None or not _is_topic_card(card) or card_id in existing_topic_schedule_ids:
            continue
        try:
            a_factor, interval = get_topic_schedule(_ADDON_DIR, _active_profile(), card_id)
        except Exception:
            continue
        entries.append(
            {
                "card_id": card_id,
                "table": "topic_schedule (effective default)",
                "column": "card_id",
                "rowid": None,
                "columns": ["card_id", "a_factor", "interval", "persisted"],
                "values": {
                    "card_id": card_id,
                    "a_factor": a_factor,
                    "interval": interval,
                    "persisted": "no",
                },
                "virtual": True,
            }
        )
    augmented["entries"] = entries
    return augmented


def _show_browser_database_entries(browser) -> None:
    card_ids = _browser_selected_incremento_card_ids(browser)
    if not card_ids:
        showInfo(_t("root_browser_select_rows"))
        return

    try:
        payload = find_card_database_entries(_ADDON_DIR, _active_profile(), card_ids)
    except Exception as exc:
        showInfo(_t("root_browser_database_read_failed", error=exc))
        return

    payload = _add_effective_topic_schedule_entries(payload)
    show_database_entries_dialog(mw, text=_format_browser_database_entries(payload))


def _start_direct_browser_review(card_ids: list[int]) -> None:
    global _direct_review_active
    requested_ids = list(card_ids or [])
    requested_count = len(requested_ids)
    _record_diagnostic_event(
        "explicit_review_requested",
        source="selected_cards",
        content_kind="other",
        requested_count=requested_count,
        preserve_order=True,
    )
    _record_diagnostic_event(
        "explicit_review_build_started",
        source="selected_cards",
        content_kind="other",
    )
    if not _anki_compat.custom_next_card_supported(Reviewer):
        _record_diagnostic_event(
            "explicit_review_failed",
            source="selected_cards",
            content_kind="other",
            stage="compatibility",
            error_type="UnsupportedAnkiReviewerAPI",
        )
        showInfo(_t("root_browser_review_unsupported"))
        return
    normalized_ids: list[int] = []
    seen: set[int] = set()
    skipped = 0

    for raw_card_id in requested_ids:
        try:
            card_id = int(raw_card_id)
        except Exception:
            skipped += 1
            continue
        if card_id <= 0 or card_id in seen:
            continue
        seen.add(card_id)
        try:
            card = mw.col.get_card(card_id)
        except Exception:
            card = None
        if card is None:
            skipped += 1
            continue
        try:
            if int(getattr(card, "queue", 0) or 0) < 0:
                skipped += 1
                continue
        except Exception:
            skipped += 1
            continue
        normalized_ids.append(card_id)

    _record_diagnostic_event(
        "explicit_review_build_finished",
        source="selected_cards",
        content_kind="other",
        requested_count=requested_count,
        selected_count=len(normalized_ids),
        unavailable_count=skipped,
    )

    if not normalized_ids:
        showInfo(_t("root_browser_no_selected_cards"))
        return

    try:
        first_card = mw.col.get_card(normalized_ids[0])
    except Exception:
        first_card = None
    if first_card is None or _direct_review_v3_info(first_card) is None:
        showInfo(_t("root_browser_review_queue_failed"))
        return

    _direct_review_card_ids[:] = normalized_ids
    _direct_review_active = True

    if skipped:
        tooltip(_t("root_browser_review_start_skipped", studying=_tn("root_browser_review_studying", len(normalized_ids)), skipped=_tn("root_browser_review_skipped", skipped)))

    try:
        if getattr(mw, "state", None) == "review" and getattr(mw, "reviewer", None):
            _anki_compat.advance_reviewer(mw.reviewer)
        else:
            mw.moveToState("review")
        _record_diagnostic_event(
            "explicit_review_started",
            source="selected_cards",
            content_kind="other",
            selected_count=len(normalized_ids),
        )
    except Exception as exc:
        _record_diagnostic_event(
            "explicit_review_failed",
            source="selected_cards",
            content_kind="other",
            stage="activation",
            error_type=type(exc).__name__,
        )
        _clear_direct_review_queue(emit_diagnostic=False)
        showInfo(_t("root_browser_review_start_failed", error=exc))


def _on_browser_context_menu(browser, menu: QMenu) -> None:
    card_ids = _browser_selected_incremento_card_ids(browser)
    if not card_ids:
        return

    menu.addSeparator()
    submenu = QMenu(_t("root_menu_incremento"), menu)
    count_label = _tn("root_browser_selected_card", len(card_ids))
    study_action = QAction(_t("root_browser_study_selected", count_label=count_label), submenu)
    topic_action = QAction(_t("root_browser_make_topic", count_label=count_label), submenu)
    item_action = QAction(_t("root_browser_make_item", count_label=count_label), submenu)
    a_factor_action = QAction(_t("root_browser_set_a_factor", count_label=count_label), submenu)
    schedule_action = QAction(_t("root_browser_custom_schedule", count_label=count_label), submenu)
    pdf_cover_action = QAction(_t("root_browser_regenerate_pdf_covers", count_label=count_label), submenu)
    epub_cover_action = QAction(_t("root_browser_regenerate_epub_covers", count_label=count_label), submenu)
    ocr_action = QAction(_t("root_browser_ocr_image_text", count_label=count_label), submenu)
    hidden_fields_action = QAction(_t("root_browser_show_hidden_fields", count_label=count_label), submenu)
    database_entries_action = QAction(_t("root_browser_show_database_entries", count_label=count_label), submenu)

    qconnect(
        study_action.triggered,
        lambda _checked=False, card_ids=list(card_ids): _start_direct_browser_review(card_ids),
    )
    qconnect(
        topic_action.triggered,
        lambda _checked=False, b=browser: _convert_browser_selection_to_knowledge_kind(
            b,
            _KT_NODE_KIND_TOPIC,
        ),
    )
    qconnect(
        item_action.triggered,
        lambda _checked=False, b=browser: _convert_browser_selection_to_knowledge_kind(
            b,
            _KT_NODE_KIND_ITEM,
        ),
    )
    qconnect(
        schedule_action.triggered,
        lambda _checked=False, card_ids=list(card_ids): _open_custom_schedule_dialog(card_ids),
    )
    qconnect(
        a_factor_action.triggered,
        lambda _checked=False, b=browser, card_ids=list(card_ids): _open_browser_a_factor_dialog(
            b,
            card_ids,
        ),
    )
    qconnect(
        pdf_cover_action.triggered,
        lambda _checked=False, b=browser: _regenerate_pdf_covers_for_browser_selection(b),
    )
    qconnect(
        epub_cover_action.triggered,
        lambda _checked=False, b=browser: _regenerate_epub_covers_for_browser_selection(b),
    )
    qconnect(
        ocr_action.triggered,
        lambda _checked=False, b=browser: _ocr_browser_selection(b),
    )
    qconnect(
        hidden_fields_action.triggered,
        lambda _checked=False, b=browser: _show_browser_hidden_fields(b),
    )
    qconnect(
        database_entries_action.triggered,
        lambda _checked=False, b=browser: _show_browser_database_entries(b),
    )

    submenu.addAction(study_action)
    submenu.addSeparator()
    submenu.addAction(topic_action)
    submenu.addAction(item_action)
    submenu.addSeparator()
    submenu.addAction(a_factor_action)
    submenu.addAction(schedule_action)
    submenu.addAction(pdf_cover_action)
    submenu.addAction(epub_cover_action)
    submenu.addAction(ocr_action)
    submenu.addAction(hidden_fields_action)
    submenu.addAction(database_entries_action)
    menu.addMenu(submenu)


def _open_pdf_reference(
    card_id: int,
    page: int,
    filename: str = "",
    excerpt: str = "",
    highlight_id: str = "",
    scroll_ratio: float | None = None,
) -> None:
    clean_filename = str(filename or "").strip()
    clean_excerpt = str(excerpt or "").strip()
    clean_highlight_id = str(highlight_id or "").strip()
    live_card_id = int(card_id or 0)
    try:
        if live_card_id > 0:
            card = mw.col.get_card(live_card_id)
            note = mw.col.get_note(card.nid)
            note_filename = str(note["PDF_Filename"] or "").strip()
            if note_filename:
                clean_filename = sync_pdf_card_file_references(
                    _ADDON_DIR,
                    _active_profile(),
                    mw.col,
                    live_card_id,
                ) or note_filename
    except Exception:
        pass

    if not clean_filename:
        try:
            clean_filename = get_pdf_card_source_filename(_ADDON_DIR, _active_profile(), live_card_id, page)
        except Exception:
            clean_filename = ""
    if not clean_filename:
        try:
            clean_filename = get_pdf_card_source_filename(_ADDON_DIR, _active_profile(), live_card_id, 0)
        except Exception:
            clean_filename = ""

    if not clean_filename and live_card_id <= 0:
        return

    if clean_filename:
        try:
            resolved_card_id = find_live_pdf_card_by_filename(mw.col, clean_filename)
            if resolved_card_id is not None:
                live_card_id = resolved_card_id
        except Exception:
            pass

    zoom = get_zoom(_ADDON_DIR, _active_profile(), live_card_id or card_id)
    if live_card_id > 0:
        _pdf_dock_mod.show_pdf_in_dock(
            live_card_id,
            clean_filename,
            page,
            zoom,
            via_link=True,
            jump_excerpt=clean_excerpt,
            jump_highlight_id=clean_highlight_id,
            scroll_ratio_override=scroll_ratio,
        )
    else:
        _pdf_dock_mod.show_pdf_in_dock(
            0,
            clean_filename,
            page,
            zoom,
            via_link=True,
            jump_excerpt=clean_excerpt,
            jump_highlight_id=clean_highlight_id,
            offer_due_review_prompt=False,
            scroll_ratio_override=scroll_ratio,
        )


def _on_js_message(handled, message, context) -> tuple:
    if not isinstance(message, str) or not message.startswith("incremento_"):
        return handled

    if message == "incremento_open_add_card":
        _add_card_dock_mod.open_add_card_dock()
        return (True, None)

    if message.startswith("incremento_selection_state:"):
        try:
            data = json.loads(message[len("incremento_selection_state:") :])
            _add_card_dock_mod.update_selection_state(
                str(data.get("source") or ""),
                has_text=bool(data.get("hasText")),
            )
        except Exception:
            pass
        return (True, None)

    if message.startswith("incremento_fill_field:"):
        try:
            data = json.loads(message[len("incremento_fill_field:") :])
            _add_card_dock_mod.fill_dock_field(int(data["idx"]), data["text"])
        except Exception:
            pass
        return (True, None)

    if message.startswith("incremento_transfer_selection:"):
        try:
            idx = int(message[len("incremento_transfer_selection:") :])
            _add_card_dock_mod.transfer_selection_to_field(idx)
        except Exception:
            pass
        return (True, None)

    if message.startswith("incremento_extract_options:"):
        try:
            data = json.loads(message[len("incremento_extract_options:") :])
            mark_topic = bool(data.get("markTopic"))
            _add_card_dock_mod.set_current_extract_options(
                priority=data.get("priority"),
                mark_topic=mark_topic,
                link_to_knowledge_tree=bool(data.get("linkToKnowledgeTree")),
            )
            _add_card_dock_mod.sync_pending_extract_options_from_current()
            editor = _add_card_dock_mod._dock_editor()
            if editor is not None:
                _add_card_dock_mod._push_extract_mark_topic_sync_suspension()
                try:
                    _add_card_dock_mod.apply_extract_topic_mark_to_editor(editor, mark_topic)
                finally:
                    _add_card_dock_mod._pop_extract_mark_topic_sync_suspension()
                _add_card_dock_mod.schedule_extract_draft_autosave(editor)
        except Exception:
            pass
        return (True, None)

    if message.startswith("incremento_scratch_priority:"):
        try:
            data = json.loads(message[len("incremento_scratch_priority:") :])
            editor = _add_card_dock_mod._current_add_mode_editor(context)
            if editor is not None:
                _add_card_dock_mod.set_scratch_priority_for_editor(
                    editor,
                    data.get("priority"),
                )
        except Exception:
            pass
        return (True, None)

    if message == "incremento_open_extract_batch":
        try:
            snapshot = _add_card_dock_mod.snapshot_extract_batch_state()
        except Exception as exc:
            showInfo(str(exc))
            return (True, None)
        try:
            dlg = ExtractBatchDialog(snapshot, parent=mw)
            if dlg.exec():
                summary = _add_card_dock_mod.create_extract_batch_notes(
                    note_type_name=str(snapshot.get("note_type_name") or ""),
                    deck_name=str(snapshot.get("deck_name") or ""),
                    question_field=dlg.question_field,
                    answer_field=dlg.answer_field,
                    rows=dlg.preview_rows,
                    extract_options=dict(snapshot.get("extract_options") or {}),
                    extract_context=dict(snapshot.get("extract_context") or {}),
                )
                created = int(summary.get("created") or 0)
                skipped = int(summary.get("skipped") or 0)
                failed = int(summary.get("failed") or 0)
                lines = [_t("root_batch_created", count=created), _t("root_batch_skipped", count=skipped), _t("root_batch_failed", count=failed)]
                errors = list(summary.get("errors") or [])
                if errors:
                    lines.extend(["", *errors[:10]])
                showInfo("\n".join(lines))
                if created:
                    try:
                        mw.reset()
                    except Exception:
                        pass
        except Exception as exc:
            showInfo(_t("root_batch_create_failed", error=exc))
        return (True, None)

    if message.startswith("incremento_open_card:"):
        try:
            note_id = int(message[len("incremento_open_card:") :])
            QTimer.singleShot(0, lambda nid=note_id: _pdf_dock_mod.show_pdf_page_card_preview(nid))
        except Exception:
            pass
        return (True, None)

    if message.startswith("incremento_open_pdf_ref:"):
        try:
            data = json.loads(message[len("incremento_open_pdf_ref:") :])
            _open_pdf_reference(
                int(data.get("card_id") or 0),
                int(data.get("page") or 1),
                str(data.get("filename") or ""),
                str(data.get("excerpt") or ""),
                str(data.get("highlight_id") or ""),
                data.get("scroll_ratio"),
            )
        except Exception:
            pass
        return (True, None)

    if message.startswith("incremento_open_pdf:"):
        parts = message.split(":")
        if len(parts) == 3:
            try:
                _open_pdf_reference(int(parts[1]), int(parts[2]))
            except Exception:
                pass
        return (True, None)

    if message.startswith("incremento_open_web:"):
        parts = message.split(":", 2)
        if len(parts) == 3:
            try:
                card_id = int(parts[1])
                target_url = unquote(parts[2])
                _web_dock_mod.open_web_location(card_id, target_url)
            except Exception:
                pass
        return (True, None)

    if message.startswith("incremento_open_epub:"):
        try:
            anchor = _epub_dock_mod.parse_epub_anchor_command(message)
            if anchor is not None:
                _epub_dock_mod.open_epub_location(
                    int(anchor["card_id"]),
                    int(anchor["section_index"]),
                    focus_offset=int(anchor["focus_offset"]),
                    scroll_ratio_override=anchor.get("scroll_ratio"),
                )
        except Exception:
            pass
        return (True, None)

    if message.startswith("incremento_open_video:"):
        parts = message.split(":")
        if len(parts) == 3:
            try:
                card_id = int(parts[1])
                position = float(parts[2])
                card = mw.col.get_card(card_id)
                note = mw.col.get_note(card.nid)
                try:
                    url = note["YouTube_URL"]
                except Exception:
                    url = ""
                media = get_video_note_media(note)
                QTimer.singleShot(
                    0,
                    lambda: _video_dock_mod.show_video_in_dock(
                        card_id,
                        url,
                        position,
                        media.get("local_video_file") or "",
                        target_subtitle_file=media.get("target_subtitle_file") or "",
                        target_subtitle_label=media.get("target_subtitle_label") or "",
                        reference_subtitle_file=media.get("reference_subtitle_file") or "",
                        reference_subtitle_label=media.get("reference_subtitle_label") or "",
                    ),
                )
            except Exception:
                pass
        return (True, None)

    return handled


def _repair_legacy_pdf_reference_links(text: str, card, context: str) -> str:
    try:
        return _pdf_dock_mod.repair_legacy_pdf_reference_links_html(text)
    except Exception:
        return text


gui_hooks.add_cards_did_add_note.append(_pdf_dock_mod.on_add_cards_did_add_note)
gui_hooks.add_cards_did_add_note.append(_epub_dock_mod.on_add_cards_did_add_note)
gui_hooks.add_cards_did_add_note.append(_web_dock_mod.on_add_cards_did_add_note)
gui_hooks.add_cards_did_add_note.append(_add_card_dock_mod.on_add_cards_did_add_note)

gui_hooks.reviewer_did_show_question.append(_on_timer_question_shown)
gui_hooks.reviewer_did_show_question.append(_review_time_mod.on_reviewer_question_shown)
gui_hooks.reviewer_did_show_question.append(_pdf_dock_mod.on_pdf_question_shown)
gui_hooks.reviewer_did_show_question.append(_epub_dock_mod.on_epub_question_shown)
gui_hooks.reviewer_did_show_question.append(_video_dock_mod.on_video_question_shown)
gui_hooks.reviewer_did_show_question.append(_web_dock_mod.on_web_question_shown)
gui_hooks.reviewer_did_show_question.append(_writing_dock_mod.on_writing_question_shown)
gui_hooks.reviewer_did_show_question.append(_local_file_dock_mod.on_local_file_question_shown)
gui_hooks.reviewer_did_show_answer.append(_review_time_mod.on_reviewer_answer_shown)
gui_hooks.state_did_change.append(_review_time_mod.on_state_did_change)
gui_hooks.reviewer_did_answer_card.append(_timer_on_card_answered)
gui_hooks.reviewer_did_answer_card.append(_on_topic_card_answered)
gui_hooks.reviewer_did_answer_card.append(_apply_custom_schedule_after_answer)
gui_hooks.reviewer_will_init_answer_buttons.append(_topic_review_buttons)
gui_hooks.reviewer_will_show_context_menu.append(_topic_review_actions.add_context_menu)
gui_hooks.reviewer_will_show_context_menu.append(_add_reviewer_button_visibility_menu)
gui_hooks.profile_will_close.append(_topic_review_actions.reset)
gui_hooks.profile_will_close.append(_pdf_dock_mod.reset_for_profile_switch)
gui_hooks.reviewer_will_answer_card.append(_topic_reviewer_will_answer_card)
gui_hooks.reviewer_will_end.append(_clear_direct_review_queue)
gui_hooks.reviewer_will_end.append(lambda: _release_session_postponed_cards())
gui_hooks.state_did_change.append(_release_expired_topic_postpones_on_overview)
gui_hooks.state_did_change.append(_release_expired_item_skips_on_overview)
gui_hooks.reviewer_will_end.append(_pdf_dock_mod.on_pdf_reviewer_will_end)
gui_hooks.reviewer_will_end.append(_epub_dock_mod.on_epub_reviewer_will_end)
gui_hooks.reviewer_will_end.append(_video_dock_mod.on_video_reviewer_will_end)
gui_hooks.reviewer_will_end.append(_web_dock_mod.on_web_reviewer_will_end)
gui_hooks.reviewer_will_end.append(_writing_dock_mod.on_writing_reviewer_will_end)
gui_hooks.reviewer_will_end.append(_local_file_dock_mod.on_local_file_reviewer_will_end)
gui_hooks.profile_will_close.append(_video_dock_mod.flush_video_progress)
if hasattr(gui_hooks, "card_will_show"):
    gui_hooks.card_will_show.append(_repair_legacy_pdf_reference_links)
gui_hooks.webview_did_receive_js_message.append(_on_js_message)


def _diagnostic_addon_version() -> str:
    try:
        addon_id = mw.addonManager.addonFromModule(__name__)
        addon_meta = getattr(mw.addonManager, "addon_meta", None)
        if callable(addon_meta):
            metadata = addon_meta(addon_id)
        else:
            metadata = mw.addonManager.addonMeta(addon_id)
        for key in ("human_version", "version"):
            if isinstance(metadata, dict):
                value = metadata.get(key)
            else:
                value = getattr(metadata, key, None)
            if value:
                return str(value)
    except Exception:
        pass
    return "unknown"


def _diagnostic_enabled_addon_count() -> int:
    try:
        addon_ids = list(mw.addonManager.allAddons() or [])
    except Exception:
        return 0
    enabled = 0
    for addon_id in addon_ids:
        try:
            if mw.addonManager.isEnabled(addon_id):
                enabled += 1
        except Exception:
            continue
    return enabled


def _diagnostic_environment_values() -> dict[str, object]:
    metadata = getattr(getattr(mw, "pm", None), "meta", {}) or {}
    anki_version = metadata.get("ankiVersion", "unknown") if isinstance(metadata, dict) else "unknown"
    if not anki_version or anki_version == "unknown":
        try:
            from anki.buildinfo import version as anki_version
        except Exception:
            anki_version = "unknown"
    return {
        "anki_version": str(anki_version or "unknown"),
        "addon_version": _diagnostic_addon_version(),
        "enabled_addons": _diagnostic_enabled_addon_count(),
    }


def _record_diagnostic_event(event: str, fields: dict | None = None, **kwargs) -> None:
    global _diagnostic_pending_final_interval
    payload = dict(fields or {})
    payload.update(kwargs)
    if event in {"topic_schedule_applied", "custom_schedule_applied"}:
        try:
            scheduled_interval = int(payload.get("scheduled_interval_days") or 0)
            _diagnostic_pending_final_interval = (
                scheduled_interval if scheduled_interval > 0 else None
            )
        except Exception:
            _diagnostic_pending_final_interval = None
    recorder = _diagnostic_recorder
    if recorder is None:
        return
    try:
        recorder.record(event, **payload)
    except Exception:
        # Diagnostics must never interfere with normal Anki or Incremento work.
        pass


def _record_diagnostic_state_change(new_state: str, old_state: str) -> None:
    _record_diagnostic_event(
        "ui_state_changed",
        from_state=old_state,
        to_state=new_state,
    )


def _diagnostic_operation_scope(handler) -> str:
    return _diagnostics_mod.operation_scope_for(handler, __name__)


def _record_diagnostic_operation(changes, handler=None) -> None:
    _record_diagnostic_event(
        "anki_operation_completed",
        scope=_diagnostic_operation_scope(handler),
        browser_sidebar_changed=bool(getattr(changes, "browser_sidebar", False)),
        browser_table_changed=bool(getattr(changes, "browser_table", False)),
        card_changed=bool(getattr(changes, "card", False)),
        note_changed=bool(getattr(changes, "note", False)),
        note_text_changed=bool(getattr(changes, "note_text", False)),
        deck_changed=bool(getattr(changes, "deck", False)),
        deck_config_changed=bool(getattr(changes, "deck_config", False)),
        config_changed=bool(getattr(changes, "config", False)),
        notetype_changed=bool(getattr(changes, "notetype", False)),
        schema_changed=bool(getattr(changes, "schema", False)),
        study_queues_changed=bool(getattr(changes, "study_queues", False)),
        tag_changed=bool(getattr(changes, "tag", False)),
    )


def _diagnostic_content_kind(card) -> str:
    """Classify only shipped Incremento note types; never export a model name."""
    try:
        note = mw.col.get_note(card.nid)
        model = mw.col.models.get(note.mid)
        model_name = str((model or {}).get("name") or "")
    except Exception:
        return "other"
    return {
        PDF_NOTE_TYPE: "pdf",
        EPUB_NOTE_TYPE: "epub",
        VIDEO_NOTE_TYPE: "video",
        WEB_NOTE_TYPE: "web",
        WRITING_NOTE_TYPE: "writing",
        LOCAL_FILE_NOTE_TYPE: "local_file",
    }.get(model_name, "other")


def _diagnostic_card_fields(card) -> dict[str, object]:
    def _number(name: str, default: int = 0) -> int:
        try:
            return int(getattr(card, name, default) or 0)
        except Exception:
            return default

    return {
        "card_type": _number("type"),
        "queue": _number("queue"),
        "interval_days": max(0, _number("ivl")),
        "content_kind": _diagnostic_content_kind(card),
    }


def _diagnostic_ui_health_fields() -> dict[str, object]:
    """Return identifiers-free Qt state useful for diagnosing input locks."""
    app = QApplication.instance()
    try:
        active_modal = app.activeModalWidget() if app is not None else None
    except Exception:
        active_modal = None
    try:
        active_popup = app.activePopupWidget() if app is not None else None
    except Exception:
        active_popup = None

    progress = getattr(mw, "progress", None)
    try:
        progress_levels = int(progress.busy() or 0) if progress is not None else 0
    except Exception:
        progress_levels = 0
    progress_window = getattr(progress, "_win", None) if progress is not None else None
    try:
        progress_window_visible = bool(
            progress_window is not None and progress_window.isVisible()
        )
    except Exception:
        progress_window_visible = False

    reviewer_web = getattr(mw, "web", None)
    try:
        main_window_enabled = bool(mw.isEnabled())
    except Exception:
        main_window_enabled = False
    try:
        reviewer_web_enabled = bool(
            reviewer_web is not None and reviewer_web.isEnabled()
        )
    except Exception:
        reviewer_web_enabled = False
    try:
        background_operations = max(
            0, int(getattr(mw, "_background_op_count", 0) or 0)
        )
    except Exception:
        background_operations = 0

    return {
        "main_window_enabled": main_window_enabled,
        "reviewer_web_enabled": reviewer_web_enabled,
        "active_modal": active_modal is not None,
        "active_popup": active_popup is not None,
        "progress_levels": progress_levels,
        "progress_window_visible": progress_window_visible,
        "background_operations": background_operations,
    }


def _record_diagnostic_question(card) -> None:
    global _diagnostic_pending_final_interval
    # Clear a result that could not be consumed because another hook aborted a
    # previous answer. This is runtime state only; no card identifier is kept.
    _diagnostic_pending_final_interval = None
    _record_diagnostic_event("review_question_shown", **_diagnostic_card_fields(card))
    expected_profile = _active_profile()

    def _probe_if_current_profile() -> None:
        if expected_profile != _active_profile():
            return
        _record_diagnostic_event(
            "review_ui_probe", **_diagnostic_ui_health_fields()
        )

    # Run after question-shown hooks and zero-delay reader callbacks.  If a
    # hidden dialog or stale Anki progress window steals input, this probe runs
    # inside that event loop and captures only safe booleans/counters.
    QTimer.singleShot(250, _probe_if_current_profile)


def _record_diagnostic_answer(_reviewer, card, ease: int) -> None:
    global _diagnostic_pending_final_interval
    card_fields = _diagnostic_card_fields(card)
    if _diagnostic_pending_final_interval is not None:
        card_fields["interval_days"] = _diagnostic_pending_final_interval
    _diagnostic_pending_final_interval = None
    _record_diagnostic_event(
        "review_answered",
        rating=ease,
        **card_fields,
    )


def _close_diagnostic_profile() -> None:
    global _diagnostic_pending_final_interval, _diagnostic_recorder
    _record_diagnostic_event("profile_closing")
    if _diagnostic_recorder is not None:
        # Profile shutdown is UI-thread work. Stop accepting immediately and
        # let the daemon worker drain without delaying Anki's transition.
        _diagnostic_recorder.close(timeout=0.0)
    _diagnostic_recorder = None
    _diagnostic_pending_final_interval = None


def _persist_reader_page_stat(
    document_type: str,
    card_id: int,
    page_number: int,
    day_end_time: str,
) -> None:
    """Profile-aware boundary for best-effort reader page statistics."""
    try:
        _record_reading_page_stat(
            _ADDON_DIR,
            _active_profile(),
            document_type,
            card_id,
            page_number,
            day_end_time=day_end_time,
        )
    except Exception:
        # Supplemental statistics must never interrupt reader navigation.
        return


def _load_reader_daily_stat(day_end_time: str) -> dict:
    try:
        history = _load_daily_stat_history(
            _ADDON_DIR,
            _active_profile(),
            days=1,
            day_end_time=day_end_time,
        )
        if history and isinstance(history[0].get("reading"), dict):
            return dict(history[0]["reading"])
    except Exception:
        pass
    return {"pdf_pages": 0, "epub_pages": 0, "pages": 0}


register_diagnostic_event_callback(_record_diagnostic_event)
_register_topic_diagnostic_event_callback(_record_diagnostic_event)
_register_custom_schedule_diagnostic_event_callback(_record_diagnostic_event)
_timer_mod.register_reading_page_callback(_persist_reader_page_stat)
_timer_mod.register_reading_history_loader(_load_reader_daily_stat)


def _activate_profile_language(profile: str | None) -> None:
    """Load only this profile's pack, using the preference captured at startup."""
    pack = None
    if profile and _startup_ui_language_choice.startswith("custom:"):
        pack = _language_packs.load_pack(_ADDON_DIR, profile, _startup_ui_language_choice[7:])
    _initialize_language(
        _startup_ui_language_choice, getattr(_anki_language, "current_lang", "en"),
        custom_pack=pack,
    )
    _retranslate_incremento_menu()


def _on_profile_did_open() -> None:
    """Activate per-profile paths and run one-time migration on first load."""
    global _diagnostic_pending_final_interval, _diagnostic_recorder
    from .backend.migration import migrate_to_profile_dir
    profile = _current_profile_name()
    cfg = _load_addon_config(mw.addonManager, __name__)
    _reset_topic_answer_runtime_state()
    _reset_custom_schedule_answer_runtime_state()
    _diagnostic_pending_final_interval = None
    # Reset Qt WebEngine profile singletons before migration so they are
    # recreated with the correct per-profile storage path on next use.
    _video_dock_mod.reset_for_profile_switch()
    _web_dock_mod.reset_for_profile_switch()
    _pdf_dock_mod.reset_for_profile_switch()
    _paths.set_active_profile(profile)
    _activate_profile_language(profile)
    migrate_to_profile_dir(_ADDON_DIR, profile)
    if _diagnostic_recorder is not None:
        # A defensive profile-open without its matching close must not leave a
        # second recorder accepting events for the previous profile.
        _diagnostic_recorder.close(timeout=0.0)
    _diagnostic_recorder = _diagnostics_mod.DiagnosticRecorder(_ADDON_DIR, profile)
    environment = _diagnostic_environment_values()
    _record_diagnostic_event("profile_opened")
    _record_diagnostic_event("addon_started", **environment)
    compatibility = _anki_compat.compatibility_report(Reviewer, mw.col)
    _record_diagnostic_event(
        "anki_compatibility_checked",
        required_methods=compatibility.required_methods,
        missing_methods=compatibility.missing_methods,
        private_scheduler_available=compatibility.private_scheduler_available,
        custom_next_card_supported=compatibility.custom_next_card_supported,
    )
    try:
        if should_auto_create_topics_deck(profile, cfg):
            _create_topics_deck()
    except Exception:
        pass


gui_hooks.profile_did_open.append(_on_profile_did_open)
gui_hooks.profile_will_close.append(_close_diagnostic_profile)
gui_hooks.profile_will_close.append(lambda: _activate_profile_language(None))


def _start_profile_reconciliation() -> None:
    """Recover interrupted imports without scanning the full collection."""
    from aqt.operations import QueryOp

    profile = _active_profile()
    if not _reconciliation_mod.pending_import_recovery_needed(
        _ADDON_DIR,
        profile,
    ):
        _record_diagnostic_event(
            "profile_reconciled",
            stale_rows=0,
            repaired_links=0,
            pending_recovered=0,
            pending_rolled_back=0,
        )
        return

    def reconcile(col):
        if profile != _active_profile():
            return {}
        return _reconciliation_mod.reconcile_pending_imports(
            _ADDON_DIR,
            profile,
            col,
        )

    def succeeded(result) -> None:
        if profile != _active_profile():
            return
        _record_diagnostic_event(
            "profile_reconciled",
            stale_rows=int((result or {}).get("stale_rows", 0)),
            repaired_links=int((result or {}).get("repaired_links", 0)),
            pending_recovered=int((result or {}).get("pending_recovered", 0)),
            pending_rolled_back=int((result or {}).get("pending_rolled_back", 0)),
        )

    def failed(exc: Exception) -> None:
        if profile == _active_profile():
            _record_diagnostic_event(
                "profile_reconciliation_failed",
                error_type=type(exc).__name__,
            )

    QueryOp(parent=mw, op=reconcile, success=succeeded).failure(failed).run_in_background()


gui_hooks.profile_did_open.append(_start_profile_reconciliation)


def _reset_answer_schedule_runtime_state() -> None:
    _reset_topic_answer_runtime_state()
    _reset_custom_schedule_answer_runtime_state()


gui_hooks.profile_will_close.append(_reset_answer_schedule_runtime_state)


_note_type_update_prompted_profiles: set[str] = set()


def _start_native_anki_sync() -> None:
    """Open Anki's own sync flow after Incremento's explanatory dialog closes."""
    try:
        _anki_compat.start_native_sync(mw)
    except Exception as exc:
        showInfo(_t("root_sync_start_failed", error=exc))


def _show_incremento_note_type_updates(*, manual: bool = False) -> None:
    profile = _active_profile()
    if not profile or mw.col is None:
        return
    if not manual and profile in _note_type_update_prompted_profiles:
        return

    try:
        pending = _detect_incremento_note_type_updates(mw.col)
    except Exception as exc:
        if manual:
            showInfo(_t("root_note_formats_inspect_failed", error=exc))
        return
    if not pending:
        if manual:
            showInfo(_t("root_note_formats_current"))
        return

    _note_type_update_prompted_profiles.add(profile)
    dialog = IncrementoNoteTypeUpdateDialog(pending, parent=mw)
    if not dialog.exec():
        return

    if dialog.selected_action == _NOTE_TYPE_ACTION_SYNC_FIRST:
        # A successful native sync will trigger sync_did_finish and show the
        # consent dialog again with a freshly inspected collection.
        _note_type_update_prompted_profiles.discard(profile)
        showInfo(_t("root_note_formats_sync_first"))
        QTimer.singleShot(0, _start_native_anki_sync)
        return

    if dialog.selected_action != _NOTE_TYPE_ACTION_APPLY:
        return

    # Re-detect after the modal dialog so only still-pending updates are saved.
    try:
        latest = _detect_incremento_note_type_updates(mw.col)
        originally_shown = {update.note_type for update in pending}
        approved = tuple(
            update for update in latest if update.note_type in originally_shown
        )
        applied = _apply_incremento_note_type_updates(mw.col, approved)
    except _NoteTypeApplyError as exc:
        _note_type_update_prompted_profiles.discard(profile)
        already_applied = ", ".join(exc.applied) or _t("root_note_formats_none_confirmed")
        showInfo(_t("root_note_formats_apply_partial", note_type=exc.note_type, applied=already_applied, error=exc.cause))
        return
    except Exception as exc:
        _note_type_update_prompted_profiles.discard(profile)
        showInfo(_t("root_note_formats_apply_failed", error=exc))
        return

    if not applied:
        showInfo(_t("root_note_formats_already_current"))
        return

    showInfo(_t("root_note_formats_applied"))
    QTimer.singleShot(0, _start_native_anki_sync)


def _schedule_incremento_note_type_update_check(*_args) -> None:
    QTimer.singleShot(0, lambda: _show_incremento_note_type_updates(manual=False))


def _schedule_note_type_update_after_profile_open(*_args) -> None:
    """Wait for Anki's automatic opening sync instead of racing it."""
    try:
        auto_sync_pending = bool(mw.can_auto_sync())
    except Exception:
        auto_sync_pending = False
    if not auto_sync_pending:
        _schedule_incremento_note_type_update_check()


def _initialize_topic_postpone_runtime() -> None:
    try:
        _release_expired_topic_postpones_now()
    except Exception:
        pass
    try:
        _schedule_topic_postpone_timer()
    except Exception:
        pass


def _initialize_item_skip_runtime() -> None:
    try:
        _release_expired_item_skips_now()
    except Exception:
        pass
    try:
        _schedule_item_skip_timer()
    except Exception:
        pass


gui_hooks.main_window_did_init.append(_initialize_topic_postpone_runtime)
gui_hooks.main_window_did_init.append(_initialize_item_skip_runtime)
gui_hooks.profile_did_open.append(
    lambda: _browser_bridge_mod.start_browser_bridge(_ADDON_DIR)
)
gui_hooks.profile_will_close.append(_browser_bridge_mod.stop_browser_bridge)


def _close_profile_database() -> None:
    """Release the UI thread's handle without disrupting live workers."""
    close_current_connection(_ADDON_DIR, _active_profile())


gui_hooks.profile_will_close.append(_close_profile_database)


def _install_reviewer_selection_bridge(_card=None) -> None:
    reviewer = getattr(mw, "reviewer", None)
    web = getattr(reviewer, "web", None)
    if web is None:
        return
    try:
        web.eval(
            "(function() {"
            "  if (window._incrementoSelectionBridgeInstalled) { return; }"
            "  window._incrementoSelectionBridgeInstalled = true;"
            "  document.addEventListener('selectionchange', function() {"
            "    var sel = window.getSelection ? window.getSelection() : null;"
            "    var text = sel ? sel.toString().trim() : '';"
            "    if (!text) { return; }"
            "    window._incrementoLastSelection = text;"
            "    pycmd('incremento_selection_state:' + JSON.stringify({source: 'reviewer', hasText: true}));"
            "  });"
            "})();"
        )
    except Exception:
        pass


def _sync_reviewer_priority_badge(_card=None) -> None:
    reviewer = getattr(mw, "reviewer", None)
    web = getattr(reviewer, "web", None)
    if web is None:
        return

    priority = None
    a_factor = None
    browser_time_seconds = None
    custom_schedule_text = ""
    card = getattr(reviewer, "card", None)
    try:
        badge_config = _load_addon_config(mw.addonManager, __name__)
    except Exception:
        badge_config = {}
    if card is not None and should_show_reviewer_priority_badge(
        is_topic=_is_topic_card(card),
        config=badge_config,
    ):
        try:
            priority = get_priority(_ADDON_DIR, _active_profile(), int(card.id))
        except Exception:
            priority = None
        try:
            if _is_topic_card(card):
                from .backend.db import get_topic_schedule

                a_factor, _interval = get_topic_schedule(
                    _ADDON_DIR,
                    _active_profile(),
                    int(card.id),
                )
        except Exception:
            a_factor = None
        try:
            is_web_card = False
            try:
                note = mw.col.get_note(card.nid)
                model = mw.col.models.get(note.mid)
                is_web_card = bool(model is not None and model.get("name") == WEB_NOTE_TYPE)
            except Exception:
                is_web_card = False
            if is_web_card:
                browser_ref = get_web_progress(
                    _ADDON_DIR,
                    _active_profile(),
                    int(card.id),
                )
            else:
                browser_ref = get_card_browser_media_ref(
                    _ADDON_DIR,
                    _active_profile(),
                    int(card.id),
                )
            seconds = float(browser_ref.get("media_seconds") or 0.0)
            if seconds > 0:
                browser_time_seconds = seconds
        except Exception:
            browser_time_seconds = None
        try:
            rule = get_custom_schedule_rule(
                _ADDON_DIR,
                _active_profile(),
                int(card.id),
            )
            custom_schedule_text = _format_custom_schedule_rule(rule)
        except Exception:
            custom_schedule_text = ""

    try:
        web.eval(
            build_reviewer_priority_badge_js(
                priority,
                a_factor=a_factor,
                browser_time_seconds=browser_time_seconds,
                custom_schedule_text=custom_schedule_text,
                lower_is_more_important=configured_priority_lower_is_more_important(),
            )
        )
    except Exception:
        pass


def _reviewer_pdf_source_cover_payload(card) -> dict[str, str] | None:
    if card is None or getattr(mw, "col", None) is None:
        return None
    try:
        note = mw.col.get_note(card.nid)
    except Exception:
        note = None
    if note is None:
        return None

    model_name = ""
    try:
        model = mw.col.models.get(note.mid)
        model_name = str((model or {}).get("name") or "").strip()
    except Exception:
        model_name = ""
    if model_name == PDF_NOTE_TYPE:
        return None

    try:
        reference = source_document_reference(note)
    except Exception:
        reference = {}
    if str(reference.get("kind") or "").strip() != "pdf":
        return None
    if not bool(reference.get("has_inline_pdf_reference")):
        return None

    filename = os.path.basename(str(reference.get("filename") or "").strip())
    source_title = str(reference.get("title") or "").strip()
    cover_media = ""
    if filename:
        try:
            source_card_id = find_live_pdf_card_by_filename(mw.col, filename)
        except Exception:
            source_card_id = None
        if source_card_id is not None:
            try:
                source_card = mw.col.get_card(int(source_card_id))
                source_note = mw.col.get_note(source_card.nid) if source_card is not None else None
            except Exception:
                source_note = None
            if source_note is not None:
                try:
                    cover_media = str(source_note[PDF_COVER_FIELD] or "").strip()
                except Exception:
                    cover_media = ""
                try:
                    source_title = str(source_note["Title"] or "").strip() or source_title
                except Exception:
                    pass

    if not source_title and filename:
        source_title = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").strip()
    if not source_title and not cover_media:
        return None
    return {
        "title": source_title,
        "cover_media": cover_media,
        "source_label": _t("root_reviewer_source_pdf"),
    }


def _sync_reviewer_source_cover(_card=None) -> None:
    reviewer = getattr(mw, "reviewer", None)
    web = getattr(reviewer, "web", None)
    if web is None:
        return

    card = getattr(reviewer, "card", None)
    payload = _reviewer_pdf_source_cover_payload(card)
    try:
        web.eval(
            build_reviewer_source_cover_js(
                (payload or {}).get("title", ""),
                cover_media=str((payload or {}).get("cover_media") or ""),
                source_label=str((payload or {}).get("source_label") or _t("root_reviewer_source_pdf")),
            )
        )
    except Exception:
        pass


gui_hooks.reviewer_did_show_question.append(_install_reviewer_selection_bridge)
gui_hooks.reviewer_did_show_answer.append(_install_reviewer_selection_bridge)
gui_hooks.reviewer_did_show_question.append(_sync_reviewer_priority_badge)
gui_hooks.reviewer_did_show_answer.append(_sync_reviewer_priority_badge)
gui_hooks.reviewer_did_show_question.append(_sync_reviewer_source_cover)
gui_hooks.reviewer_did_show_answer.append(_sync_reviewer_source_cover)


def _restore_reviewer_focus_after_incremento_hooks(_card) -> None:
    schedule_reviewer_focus_restore(
        mw,
        timer=QTimer,
        application=QApplication.instance(),
    )


register_reviewer_focus_restore_hooks(
    gui_hooks,
    _restore_reviewer_focus_after_incremento_hooks,
)


def _complete_incremento_onboarding() -> None:
    config = _load_addon_config(mw.addonManager, __name__)
    updated = mark_onboarding_complete(config)
    _save_addon_config(mw.addonManager, __name__, updated)


def _show_incremento_onboarding(*, force: bool = False) -> None:
    global _onboarding_dialog
    config = _load_addon_config(mw.addonManager, __name__)
    if not force and not should_show_onboarding(config):
        return
    existing = _onboarding_dialog
    if existing is not None:
        try:
            if existing.isVisible():
                existing.raise_()
                existing.activateWindow()
                return
        except Exception:
            _onboarding_dialog = None

    dialog = create_onboarding_dialog(
        mw,
        on_complete=_complete_incremento_onboarding,
        actions={
            "add_pdf": addPdfFunction,
            "start_learning": learnFunction,
            "export_user_data": exportFunction,
        },
    )
    _onboarding_dialog = dialog

    def _clear_onboarding(*_args) -> None:
        global _onboarding_dialog
        if _onboarding_dialog is dialog:
            _onboarding_dialog = None

    try:
        dialog.finished.connect(_clear_onboarding)
    except Exception:
        pass
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()


def _schedule_incremento_onboarding() -> None:
    def _show_when_ready(attempt: int = 0) -> None:
        try:
            modal = QApplication.activeModalWidget()
        except Exception:
            modal = None
        if modal is not None:
            if attempt < 8:
                QTimer.singleShot(500, lambda: _show_when_ready(attempt + 1))
            return
        _show_incremento_onboarding()

    QTimer.singleShot(2400, _show_when_ready)


def _check_deps_first_run() -> None:
    """On first run after install, show the dependency setup dialog if anything is missing."""
    from .backend.deps import status
    config = _load_addon_config(mw.addonManager, __name__)
    if config.get("deps_notified"):
        return
    s = status()
    if s["pymupdf"] and s["tesseract"]:
        # Everything present — mark as notified and skip
        config["deps_notified"] = True
        _save_addon_config(mw.addonManager, __name__, config)
        return
    # Something is missing — show the setup dialog once
    config["deps_notified"] = True
    _save_addon_config(mw.addonManager, __name__, config)

    def _show():
        from .backend.deps import show_setup_dialog
        show_setup_dialog(mw)

    # Defer slightly so Anki finishes loading before the dialog appears
    from aqt.qt import QTimer
    QTimer.singleShot(1500, _show)


gui_hooks.main_window_did_init.append(_check_deps_first_run)
gui_hooks.main_window_did_init.append(_schedule_incremento_onboarding)


def _build_timer_toolbar() -> None:
    build_timer_toolbar(_timerToggleAction)


# ── Option+P quick-jump to PDF ────────────────────────────────────────────────


def _open_pdf_quick_jump() -> None:
    global _last_opened_pdf_cid, _last_opened_writing_cid
    dlg = _PdfQuickJumpDialog(
        mw,
        addon_dir=_ADDON_DIR,
        last_opened_pdf_cid=_last_opened_pdf_cid,
        last_opened_writing_cid=_last_opened_writing_cid,
    )
    if not dlg.exec():
        return
    cid = dlg.selected_card_id
    if cid is None:
        return
    try:
        if dlg.selected_card_type == "EPUB":
            _open_epub_card(cid)
            if dlg.open_card_to_study:
                start_quick_open_review(cid)
        elif dlg.selected_card_type == "WRITING":
            _open_writing_card(cid, relpath=dlg.selected_relpath)
        else:
            _open_pdf_card(cid, preserve_history=dlg.preserve_history)
            if dlg.open_card_to_study:
                start_quick_open_review(cid)
    except Exception as e:
        showInfo(_t("root_document_open_failed", error=e))


def _open_document_bookshelf() -> None:
    from aqt.operations import QueryOp

    captured_profile = _active_profile()

    def load_entries(col):
        return _load_bookshelf_snapshot(
            _ADDON_DIR,
            captured_profile,
            collection=col,
        )

    def show_bookshelf(snapshot) -> None:
        entries, attachment_counts = snapshot
        dlg = _DocumentBookshelfDialog(
            mw,
            addon_dir=_ADDON_DIR,
            last_opened_card_id=_last_opened_document_cid,
            entries=list(entries or []),
            attachment_counts=dict(attachment_counts or {}),
        )
        if not dlg.exec():
            return
        card_id = dlg.selected_card_id
        if card_id is None:
            return
        try:
            if dlg.selected_card_type == "EPUB":
                _open_epub_card(card_id)
            else:
                _open_pdf_card(card_id, preserve_history=dlg.preserve_history)
            if dlg.open_card_to_study:
                start_quick_open_review(card_id)
        except Exception as exc:
            showInfo(_t("root_document_open_failed", error=exc))

    def failed(exc: Exception) -> None:
        showInfo(_t("root_bookshelf_load_failed", error=exc))

    try:
        (
            QueryOp(parent=mw, op=load_entries, success=show_bookshelf)
            .failure(failed)
            .with_progress(_t("root_bookshelf_loading"))
            .run_in_background()
        )
    except Exception as exc:
        failed(exc)


def _open_writing_card(card_id: int, *, relpath: str = "") -> None:
    global _last_opened_writing_cid
    card = mw.col.get_card(card_id)
    note = mw.col.get_note(card.nid)
    title = str(note["Title"] or "").strip()
    stored_relpath = str(relpath or note[WRITING_FILE_FIELD] or "").strip()
    if not stored_relpath:
        stored_relpath = build_writing_relpath(title=title or f"writing-{card.id}")
        try:
            note[WRITING_FILE_FIELD] = stored_relpath
            mw.col.update_note(note)
        except Exception:
            pass
    _writing_dock_mod.show_writing_in_dock(card.id, title, stored_relpath)
    _last_opened_writing_cid = int(card.id)


def _open_pdf_card(
    card_id: int,
    page: int | None = None,
    search_query: str = "",
    jump_excerpt: str = "",
    preserve_history: bool = False,
) -> None:
    global _last_opened_document_cid, _last_opened_pdf_cid
    card = mw.col.get_card(card_id)
    note = mw.col.get_note(card.nid)
    filename = note["PDF_Filename"]
    open_page = page if page is not None else get_page(_ADDON_DIR, _active_profile(), card_id)
    zoom = get_zoom(_ADDON_DIR, _active_profile(), card_id)
    read_page = get_read_page(_ADDON_DIR, _active_profile(), card_id)
    _last_opened_pdf_cid = card_id
    _last_opened_document_cid = card_id
    _pdf_dock_mod.show_pdf_in_dock(
        card_id,
        filename,
        open_page,
        zoom,
        read_page=read_page,
        search_query=search_query,
        jump_excerpt=jump_excerpt,
        preserve_history=preserve_history,
    )


def _open_epub_card(
    card_id: int,
    section_index: int | None = None,
    *,
    focus_offset: int = -1,
    search_query: str = "",
) -> None:
    global _last_opened_document_cid
    card = mw.col.get_card(card_id)
    note = mw.col.get_note(card.nid)
    filename = note[EPUB_FILE_FIELD]
    current_section, current_ratio, _is_finished = get_epub_progress(_ADDON_DIR, _active_profile(), card_id)
    _epub_dock_mod.show_epub_in_dock(
        card_id,
        filename,
        section_index=current_section if section_index is None else int(section_index),
        scroll_ratio=current_ratio,
        focus_offset=focus_offset,
        search_query=search_query,
    )
    _last_opened_document_cid = card_id


def _open_search_all(initial_query: str = "") -> None:
    _SearchAllDialog(
        mw,
        addon_dir=_ADDON_DIR,
        open_pdf_card=_open_pdf_card,
        open_epub_card=_open_epub_card,
        initial_query=initial_query,
    ).exec()


def _open_current_document_search() -> bool:
    if _pdf_dock_mod.open_current_document_find():
        return True
    if _epub_dock_mod.open_current_document_find():
        return True
    return False


def _open_current_document_search_results() -> bool:
    pdf_context = _pdf_dock_mod.current_pdf_search_context()
    if pdf_context is not None:
        _CurrentDocumentSearchDialog(
            mw,
            document_kind="pdf",
            document_label=str(pdf_context.get("documentLabel") or "PDF"),
            initial_query=str(pdf_context.get("query") or ""),
            search_hits_fn=lambda query: _pdf_dock_mod.current_card_pdf_search_hits(
                int(pdf_context.get("cardId") or 0),
                query,
            ),
            open_hit_fn=lambda hit, index, query: _pdf_dock_mod.open_current_pdf_search_hit(
                hit,
                index,
                query,
            ),
            open_search_all_fn=_open_search_all,
        ).exec()
        return True

    epub_context = _epub_dock_mod.current_epub_search_context()
    if epub_context is not None:
        _CurrentDocumentSearchDialog(
            mw,
            document_kind="epub",
            document_label=str(epub_context.get("documentLabel") or "EPUB"),
            initial_query=str(epub_context.get("query") or ""),
            search_hits_fn=lambda query: _epub_dock_mod.current_card_epub_search_hits(
                int(epub_context.get("cardId") or 0),
                query,
            ),
            open_hit_fn=lambda hit, index, query: _epub_dock_mod.open_current_epub_search_hit(
                hit,
                index,
                query,
            ),
            open_search_all_fn=_open_search_all,
        ).exec()
        return True

    return False


_pdf_dock_mod.register_current_document_search_results_callback(_open_current_document_search_results)
_epub_dock_mod.register_current_document_search_results_callback(_open_current_document_search_results)


def _current_reviewer_card_id() -> int | None:
    reviewer = getattr(mw, "reviewer", None)
    card = getattr(reviewer, "card", None) if reviewer else None
    if card is None:
        return None
    try:
        return int(card.id)
    except Exception:
        return None


def _current_reviewer_video_card():
    reviewer = getattr(mw, "reviewer", None)
    card = getattr(reviewer, "card", None) if reviewer else None
    if card is None:
        return None
    try:
        note = card.note()
        model = mw.col.models.get(note.mid)
    except Exception:
        return None
    if model is None or model.get("name") != VIDEO_NOTE_TYPE:
        return None
    return card


def _download_current_reviewer_video_locally() -> None:
    if _current_reviewer_video_card() is None:
        tooltip(_t("root_reviewer_no_video_card"))
        return
    _video_dock_mod.download_current_video_locally()


def _configure_current_reviewer_video_captions() -> None:
    if _current_reviewer_video_card() is None:
        tooltip(_t("root_reviewer_no_video_card"))
        return
    _video_dock_mod.configure_current_video_captions()


def _open_knowledge_tree(*, select_card_id: int | None = None) -> None:
    global _knowledge_tree_dialog

    if select_card_id is None:
        select_card_id = _current_reviewer_card_id()

    current_profile = _active_profile()
    if _knowledge_tree_dialog is not None:
        try:
            if getattr(_knowledge_tree_dialog, "_profile", None) == current_profile:
                _knowledge_tree_dialog.reload(
                    select_card_id=select_card_id,
                    focus_card_id=select_card_id,
                )
                _knowledge_tree_dialog.show()
                _knowledge_tree_dialog.raise_()
                _knowledge_tree_dialog.activateWindow()
                return
            _knowledge_tree_dialog.close()
        except RuntimeError:
            _knowledge_tree_dialog = None

    from .frontend.knowledge_tree_dialog import KnowledgeTreeDialog

    dlg = KnowledgeTreeDialog(
        _ADDON_DIR,
        profile=current_profile,
        select_card_id=select_card_id,
        focus_card_id=select_card_id,
        open_priority_for_card=_open_priority_dialog_for_card,
        open_branch_study=_study_knowledge_tree_branch,
        parent=mw,
    )

    def _on_closed(*_args) -> None:
        global _knowledge_tree_dialog
        _knowledge_tree_dialog = None

    qconnect(dlg.finished, _on_closed)
    _knowledge_tree_dialog = dlg
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()


def _reveal_current_card_in_knowledge_tree() -> None:
    card_id = _current_reviewer_card_id()
    if card_id is None:
        tooltip(_t("root_reviewer_no_active_card"))
        return
    _open_knowledge_tree(select_card_id=card_id)


def _go_to_parent_in_knowledge_tree() -> None:
    card_id = _current_reviewer_card_id()
    if card_id is None:
        tooltip(_t("root_reviewer_no_active_card"))
        return

    row = get_knowledge_tree_node(_ADDON_DIR, _active_profile(), int(card_id))
    if row is None:
        tooltip(_t("root_reviewer_card_not_in_tree"))
        return

    parent_card_id = row.get("parent_card_id")
    if parent_card_id is None:
        tooltip(_t("root_reviewer_card_at_tree_top"))
        return

    _open_knowledge_tree(select_card_id=int(parent_card_id))


def _study_knowledge_tree_branch(card_id: int) -> None:
    try:
        from .backend.knowledge_tree import build_branch_study_scope

        branch_scope = build_branch_study_scope(
            _ADDON_DIR,
            _active_profile(),
            int(card_id),
        )
    except Exception as exc:
        showInfo(_t("root_branch_study_failed", error=exc))
        return

    if not branch_scope or not list(branch_scope.get("card_ids") or []):
        tooltip(_t("root_reviewer_branch_empty"))
        return

    learnFunction(branch_scope=branch_scope)


def _trigger_pdf_viewer_action(action: str) -> None:
    _pdf_dock_mod.trigger_viewer_action(action)


_pdf_jump_shortcut = QShortcut(QKeySequence("Ctrl+Alt+P"), mw)
_pdf_jump_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(_pdf_jump_shortcut.activated, _open_pdf_quick_jump)
_register_shortcut_action("quick_open_pdf", _pdf_jump_shortcut)

_document_bookshelf_shortcut = QShortcut(QKeySequence("Alt+Shift+P"), mw)
_document_bookshelf_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(_document_bookshelf_shortcut.activated, _open_document_bookshelf)
_register_shortcut_action("document_bookshelf", _document_bookshelf_shortcut)

_configured_shortcut_filter = _ConfiguredShortcutFilter(QApplication.instance() or mw)
(QApplication.instance() or mw).installEventFilter(_configured_shortcut_filter)


def showStatsFunction() -> None:
    base_time = get_session_times() or {"type": {}, "tags": {}}
    runtime_time = _review_time_mod.get_runtime_session_time() or {
        "type": {},
        "tags": {},
    }
    merged_time = {"type": {}, "tags": {}}
    for key in ("type", "tags"):
        for src in (base_time.get(key, {}), runtime_time.get(key, {})):
            for name, value in src.items():
                merged_time[key][name] = merged_time[key].get(name, 0.0) + float(value)

    cfg = load_scheduler_config()
    dlg = StatsDialog(
        addon_dir=os.path.dirname(__file__),
        session_counts=get_session_counts(),
        session_time=merged_time,
        day_end_time=cfg.day_end_time,
        parent=mw,
    )
    dlg.exec()


def addPdfFunction() -> None:
    from .frontend.pdf_dialog import AddPdfDialog

    deck_names = [d.name for d in mw.col.decks.all_names_and_ids()]
    dlg = AddPdfDialog(addon_dir=_ADDON_DIR, deck_names=deck_names, default_deck="Topics", parent=mw)
    if not dlg.exec():
        return

    created = dlg.created
    failed = dlg.failed
    deck = dlg.deck_name

    if not created and not failed:
        return

    def _fmt_size(path: str) -> str:
        try:
            b = os.path.getsize(path)
            return f"{b / 1_048_576:.1f} MB" if b >= 1_048_576 else f"{b // 1024} KB"
        except OSError:
            return "?"

    if created:
        lines = [_tn("root_import_pdf_added", len(created), deck=deck) + "\n"]
        for path, title in created:
            lines.append(f"• {title}")
            lines.append(f"  {os.path.basename(path)}  ·  {_fmt_size(path)}")
        if failed:
            lines.append("\n" + _t("root_batch_failed", count=len(failed)))
            for path, msg in failed[:10]:
                lines.append(f"• {os.path.basename(path)}: {msg}")
            if len(failed) > 10:
                lines.append("  " + _t("root_more_failures", count=len(failed) - 10))
        showInfo("\n".join(lines))
    else:
        failed_lines = "\n".join(
            f"• {os.path.basename(p)}: {msg}" for p, msg in failed[:10]
        )
        extra = "\n" + _t("root_more_failures", count=len(failed) - 10) if len(failed) > 10 else ""
        showInfo(_t("root_import_pdf_all_failed", count=len(failed), details=failed_lines, extra=extra))


def addEpubFunction() -> None:
    from .frontend.epub_dialog import AddEpubDialog

    deck_names = [d.name for d in mw.col.decks.all_names_and_ids()]
    dlg = AddEpubDialog(addon_dir=_ADDON_DIR, deck_names=deck_names, default_deck="Topics", parent=mw)
    if not dlg.exec():
        return

    created = dlg.created
    failed = dlg.failed
    deck = dlg.deck_name

    if not created and not failed:
        return

    if created:
        lines = [_tn("root_import_epub_added", len(created), deck=deck) + "\n"]
        for path, title in created:
            lines.append(f"• {title}")
            lines.append(f"  {os.path.basename(path)}")
        if failed:
            lines.append("\n" + _t("root_batch_failed", count=len(failed)))
            for path, msg in failed[:10]:
                lines.append(f"• {os.path.basename(path)}: {msg}")
            if len(failed) > 10:
                lines.append("  " + _t("root_more_failures", count=len(failed) - 10))
        showInfo("\n".join(lines))
    else:
        failed_lines = "\n".join(
            f"• {os.path.basename(p)}: {msg}" for p, msg in failed[:10]
        )
        extra = "\n" + _t("root_more_failures", count=len(failed) - 10) if len(failed) > 10 else ""
        showInfo(_t("root_import_epub_all_failed", count=len(failed), details=failed_lines, extra=extra))


def addMarkdownDocumentFunction() -> None:
    from .frontend.markdown_document_dialog import AddMarkdownDocumentDialog

    deck_names = [d.name for d in mw.col.decks.all_names_and_ids()]
    dlg = AddMarkdownDocumentDialog(_ADDON_DIR, deck_names, default_deck="Topics", parent=mw)
    if dlg.exec() and dlg.created:
        showInfo(_t("root_import_markdown_documents_added", count=len(dlg.created), deck=dlg.deck_name), textFormat="plain")


def importNotebookCitationsFunction() -> None:
    from .frontend.notebook_citation_import_dialog import NotebookCitationImportDialog

    dlg = NotebookCitationImportDialog(addon_dir=_ADDON_DIR, parent=mw)
    dlg.exec()


def exportFunction() -> None:
    import datetime
    from aqt.qt import QFileDialog, QMessageBox

    choice = QMessageBox(mw)
    choice.setWindowTitle(_t("root_backup_full_title"))
    choice.setText(_t("root_backup_choice_description"))
    export_button = choice.addButton(_t("root_backup_export_now"), QMessageBox.ButtonRole.AcceptRole)
    automatic_button = choice.addButton(
        _t("root_backup_automatic_button"), QMessageBox.ButtonRole.ActionRole
    )
    choice.addButton(QMessageBox.StandardButton.Cancel).setText(_t("common_cancel"))
    choice.exec()
    if choice.clickedButton() is automatic_button:
        configureAutomaticBackupsFunction()
        return
    if choice.clickedButton() is not export_button:
        return

    today = datetime.date.today().isoformat()
    profile = _active_profile()
    default_name = os.path.expanduser(
        f"~/incremento_{profile}_full_backup_{today}.zip"
    )
    path, _ = QFileDialog.getSaveFileName(
        mw, _t("root_backup_file_dialog_title"), default_name, _t("root_backup_file_filter")
    )
    if path:
        _start_full_backup(path if path.lower().endswith(".zip") else path + ".zip")


def restoreFullBackupFunction() -> None:
    """Restore a validated full ZIP into the currently open Anki profile."""
    from .frontend.full_restore import restore_full_backup

    profile = _active_profile()
    config = _load_addon_config(mw.addonManager, __name__)
    restore_full_backup(
        mw,
        addon_dir=_ADDON_DIR,
        profile_key=profile,
        profile_name=_current_profile_name(),
        current_config=config,
        save_config=lambda updated: _save_addon_config(
            mw.addonManager, __name__, updated
        ),
        backup_running=lambda: _full_backup_running,
        reset_close_gate=_reset_close_backup_gate,
    )


_auto_backup_timer: QTimer | None = None
_auto_backup_generation = 0
_full_backup_running = False
_backup_idle_callbacks: list = []
_close_backup_gate = None


def configureAutomaticBackupsFunction() -> None:
    from .frontend.automatic_backup_dialog import AutomaticBackupDialog

    profile = _active_profile()
    cfg = _load_addon_config(mw.addonManager, __name__)
    policies = cfg.get("automatic_backups", {})
    dlg = AutomaticBackupDialog(
        _current_profile_name(), _paths.get_user_files_dir(_ADDON_DIR, profile),
        policies.get(profile, {}), mw,
    )
    if not dlg.exec():
        return
    policies[profile] = dlg.policy
    cfg["automatic_backups"] = policies
    _save_addon_config(mw.addonManager, __name__, cfg)
    if dlg.policy["enabled"] and dlg.policy["interval_hours"]:
        _attempt_automatic_backup("interval", profile, _auto_backup_generation)


def _attempt_automatic_backup(trigger: str, profile: str, generation: int) -> None:
    if generation != _auto_backup_generation or _active_profile() != profile:
        return
    cfg = _load_addon_config(mw.addonManager, __name__)
    policy = _backup_schedule.normalize_policy(cfg.get("automatic_backups", {}).get(profile))
    if not _backup_schedule.is_due(policy, trigger, time.time()):
        return
    try:
        folder = _backup_schedule.validate_destination(
            policy["directory"], _paths.get_user_files_dir(_ADDON_DIR, profile)
        )
        path = _backup_schedule.next_backup_path(folder, profile, policy["versions"])
    except (OSError, ValueError) as exc:
        tooltip(_t("root_backup_folder_unavailable", error=exc))
        return
    _start_full_backup(str(path), automatic_policy=policy)


def _start_automatic_backups() -> None:
    global _auto_backup_timer, _auto_backup_generation
    _auto_backup_generation += 1
    generation = _auto_backup_generation
    profile = _active_profile()
    try:
        cfg = _load_addon_config(mw.addonManager, __name__)
        policy = _backup_schedule.normalize_policy(
            cfg.get("automatic_backups", {}).get(profile)
        )
        if policy["last_close_failed"]:
            tooltip(_t("root_backup_close_failed"))
    except Exception:
        pass
    if _auto_backup_timer is not None:
        _auto_backup_timer.stop()
    _auto_backup_timer = QTimer(mw)
    _auto_backup_timer.setInterval(15 * 60 * 1000)
    _auto_backup_timer.timeout.connect(
        lambda: _attempt_automatic_backup("interval", profile, generation)
    )
    _auto_backup_timer.start()
    QTimer.singleShot(
        12000, lambda: _attempt_automatic_backup("open", profile, generation)
    )


def _stop_automatic_backups() -> None:
    global _auto_backup_generation
    _auto_backup_generation += 1
    if _auto_backup_timer is not None:
        _auto_backup_timer.stop()


def _record_close_backup_result(profile: str, *, failed: bool) -> None:
    """Keep a non-sensitive failure marker visible after Anki restarts."""
    try:
        cfg = _load_addon_config(mw.addonManager, __name__)
        policies = cfg.get("automatic_backups", {})
        if profile not in policies:
            return
        policy = _backup_schedule.normalize_policy(policies[profile])
        policy["last_close_failed"] = bool(failed)
        policies[profile] = policy
        cfg["automatic_backups"] = policies
        _save_addon_config(mw.addonManager, __name__, cfg)
    except Exception:
        pass


def _prepare_profile_close(resume_close) -> None:
    """Keep the collection alive until any active and requested close export ends."""
    profile = _active_profile()
    if _full_backup_running:
        _backup_idle_callbacks.append(lambda: _prepare_profile_close(resume_close))
        return
    cfg = _load_addon_config(mw.addonManager, __name__)
    policy = _backup_schedule.normalize_policy(
        cfg.get("automatic_backups", {}).get(profile)
    )
    if not _backup_schedule.is_due(policy, "close", time.time()):
        resume_close()
        return
    try:
        folder = _backup_schedule.validate_destination(
            policy["directory"], _paths.get_user_files_dir(_ADDON_DIR, profile)
        )
        path = _backup_schedule.next_backup_path(folder, profile, policy["versions"])
    except (OSError, ValueError) as exc:
        tooltip(_t("root_backup_close_folder_unavailable", error=exc))
        _record_close_backup_result(profile, failed=True)
        resume_close()
        return
    if _start_full_backup(str(path), automatic_policy=policy, close_triggered=True):
        _backup_idle_callbacks.append(resume_close)
    else:
        _record_close_backup_result(profile, failed=True)
        resume_close()


def _install_close_backup_gate() -> None:
    global _close_backup_gate
    if _close_backup_gate is not None:
        return
    from .frontend.backup_close_gate import ProfileCloseBackupGate

    _close_backup_gate = ProfileCloseBackupGate(mw, _prepare_profile_close)
    _close_backup_gate.install()


def _reset_close_backup_gate() -> None:
    if _close_backup_gate is not None:
        _close_backup_gate.reset()


gui_hooks.profile_did_open.append(_start_automatic_backups)
gui_hooks.profile_did_open.append(_reset_close_backup_gate)
gui_hooks.profile_will_close.append(_stop_automatic_backups)
gui_hooks.main_window_did_init.append(_install_close_backup_gate)


def _start_full_backup(
    path: str, *, automatic_policy: dict | None = None, close_triggered: bool = False
) -> bool:
    import datetime
    import tempfile
    from pathlib import Path

    from anki import hooks
    from .backend.backup_media import FullBackupPackageExporter
    from .backend.db import (
        get_connection,
        DB_NAME,
        export_priorities_json,
        export_pdf_progress_json,
        export_highlights_json,
        export_stats_json,
    )
    from .backend.export_bundle import snapshot_tree
    from .frontend.backup_progress import AutomaticBackupProgress
    from .backend.activity_log import (
        start_activity, update_activity, finish_activity, fail_activity,
    )

    global _full_backup_running
    if _full_backup_running:
        if automatic_policy is None:
            tooltip(_t("root_backup_already_running"))
        return False
    today = datetime.date.today().isoformat()
    profile = _active_profile()
    profile_display_name = _current_profile_name()
    user_files_dir = str(_paths.get_user_files_dir(_ADDON_DIR, profile))
    try:
        destination = _backup_schedule.validate_destination(
            os.path.dirname(os.path.abspath(path)), Path(user_files_dir)
        )
        path = str(destination / os.path.basename(path))
        if Path(path).is_symlink():
            raise ValueError("The backup ZIP cannot replace a symbolic link.")
        archive_fd, archive_tmp_path = tempfile.mkstemp(
            prefix=".incremento-backup-", suffix=".zip", dir=str(destination),
        )
    except (OSError, ValueError) as exc:
        if automatic_policy is None:
            showInfo(_t("root_backup_destination_unavailable", error=exc))
        else:
            tooltip(_t("root_backup_auto_destination_unavailable", error=exc))
        return False
    os.close(archive_fd)
    try:
        config = _load_addon_config(mw.addonManager, __name__)
    except Exception:
        os.remove(archive_tmp_path)
        raise
    collection = mw.col
    activity_id = start_activity(
        _t("root_backup_activity_title"), category=_t("root_backup_activity_category"), detail=_t("root_backup_activity_preparing"),
    )
    progress = AutomaticBackupProgress(mw) if automatic_policy is not None else None
    if progress is not None:
        try:
            progress.start()
        except Exception as exc:
            fail_activity(activity_id, _t("root_backup_progress_failed", error=exc))
            os.remove(archive_tmp_path)
            return False
    _full_backup_running = True

    def _restore_instructions() -> str:
        return "\n".join(
            [
                "Incremento Current-Profile Backup Restore",
                "==============================",
                "",
                "This archive contains:",
                "1. anki/all_decks.apkg  -> Anki cards, scheduling, and referenced media",
                f"2. user_files/{profile}/ -> Incremento profile files and database",
                "3. config.json          -> Incremento add-on settings",
                "",
                "Recommended restore order:",
                "1. Install Anki.",
                "2. Install the Incremento add-on.",
                "3. Open the Anki profile you want to replace.",
                "4. Choose Incremento -> Restore Full Backup and select this ZIP.",
                "5. Review the pre-check and confirm replacement.",
                "6. Verify cards, media, PDFs, writing notes, highlights, and progress.",
                "7. Re-enable automatic collection/media sync only after checking the restored profile.",
                "",
                "Notes:",
                f"- This backup belongs to the Anki profile: {profile_display_name}",
                "- Both the APKG and Incremento runtime snapshot cover that profile only.",
                "- The runtime snapshot includes PDFs, EPUBs, videos, writing files, browser profiles, and the database.",
                "- A safety backup of the current Anki collection is made before replacement.",
                "- Automatic-backup folder settings for existing profiles are retained.",
                "- AnkiWeb is not checked; a later ordinary sync may merge remote changes or deletions.",
                "- If this restored collection should replace AnkiWeb, force a one-way Upload.",
                "  Download replaces the restored cards; media sync always merges separately.",
            ]
        )

    def _progress(label: str) -> None:
        update_activity(activity_id, detail=label)
        if progress is not None:
            progress.update(label)

    try:
        # This touches Qt/WebEngine-owned dock state and must stay on the main
        # thread. The archive worker only receives already-flushed files.
        _video_dock_mod.flush_video_progress()
    except Exception:
        pass

    def _task():
        if _active_profile() != profile:
            raise RuntimeError("The active profile changed before backup started")
        conn = get_connection(_ADDON_DIR, profile)
        conn.commit()

        database_integrity = str(
            conn.execute("PRAGMA integrity_check").fetchone()[0]
        )
        if database_integrity.casefold() != "ok":
            raise RuntimeError("Incremento database integrity check failed")
        database_schema_version = int(
            conn.execute("PRAGMA user_version").fetchone()[0]
        )

        priority_count = conn.execute("SELECT COUNT(*) FROM priorities").fetchone()[0]
        highlight_count = conn.execute("SELECT COUNT(*) FROM pdf_highlights").fetchone()[0]
        pdf_progress_count = conn.execute("SELECT COUNT(*) FROM pdf_progress").fetchone()[0]
        stats_count = conn.execute("SELECT COUNT(*) FROM stats").fetchone()[0]

        with tempfile.TemporaryDirectory(prefix="incremento_export_") as tmp_dir:
            tmp_root = Path(tmp_dir)
            apkg_path = tmp_root / "all_decks.apkg"
            db_snapshot_path = tmp_root / DB_NAME

            _progress(_t("root_backup_activity_creating_package"))
            exporter = FullBackupPackageExporter(collection)
            exporter.includeSched = True
            exporter.includeMedia = True
            exporter.did = None
            exporter.cids = None

            def _exported_media_count(cnt: int) -> None:
                _progress(_t("root_backup_exported_media", count=cnt))

            hooks.media_files_did_export.append(_exported_media_count)
            try:
                exporter.exportInto(str(apkg_path))
            finally:
                hooks.media_files_did_export.remove(_exported_media_count)

            if _active_profile() != profile:
                raise RuntimeError("The active profile changed while backup was running")

            _progress(_t("root_backup_activity_snapshotting"))
            snapshot_conn = sqlite3.connect(str(db_snapshot_path))
            try:
                conn.backup(snapshot_conn)
            finally:
                snapshot_conn.close()

            stage_root = tmp_root / "bundle"
            user_files_stage = stage_root / "user_files"
            profile_stage = user_files_stage / profile
            profile_stage.mkdir(parents=True, exist_ok=True)

            user_files_stats = snapshot_tree(
                user_files_dir,
                str(profile_stage),
                skip_relpaths={DB_NAME, f"{DB_NAME}-wal", f"{DB_NAME}-shm"},
            )
            db_stage_path = profile_stage / DB_NAME
            db_stage_path.write_bytes(db_snapshot_path.read_bytes())

            if _active_profile() != profile:
                raise RuntimeError("The active profile changed while backup was running")

            _progress(_t("root_backup_activity_writing_zip"))
            with zipfile.ZipFile(archive_tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(apkg_path, "anki/all_decks.apkg")
                zf.write(db_stage_path, f"user_files/{profile}/{DB_NAME}")

                for root, _, filenames in os.walk(user_files_stage):
                    for filename in filenames:
                        file_path = Path(root) / filename
                        if file_path == db_stage_path:
                            continue
                        arcname = file_path.relative_to(stage_root).as_posix()
                        zf.write(file_path, arcname)

                zf.writestr("config.json", json.dumps(config, ensure_ascii=False, indent=2))
                zf.writestr("restore.txt", _restore_instructions())
                zf.writestr("data/priorities.json", export_priorities_json(_ADDON_DIR, profile))
                zf.writestr("data/pdf_progress.json", export_pdf_progress_json(_ADDON_DIR, profile))
                zf.writestr("data/highlights.json", export_highlights_json(_ADDON_DIR, profile))
                zf.writestr("data/stats.json", export_stats_json(_ADDON_DIR, profile))

                manifest = {
                    "schema_version": 2,
                    "export_date": today,
                    "addon": "Incremento",
                    "scope": "current_profile",
                    "anki_version": getattr(mw.pm, "meta", {}).get(
                        "ankiVersion", "unknown"
                    ),
                    "profile": profile_display_name,
                    "profile_storage_key": profile,
                    "database": {
                        "integrity_check": database_integrity,
                        "schema_version": database_schema_version,
                    },
                    "counts": {
                        "anki_cards_exported": int(getattr(exporter, "count", 0) or 0),
                        "priorities": int(priority_count or 0),
                        "pdf_progress": int(pdf_progress_count or 0),
                        "highlights": int(highlight_count or 0),
                        "stats_rows": int(stats_count or 0),
                        "user_files_copied": int(user_files_stats["files_copied"]) + 1,
                        "user_files_skipped": int(user_files_stats["files_skipped"]),
                        "user_files_bytes": int(user_files_stats["bytes_copied"])
                        + int(db_stage_path.stat().st_size),
                    },
                    "files": {
                        "anki/all_decks.apkg": "All decks from the current Anki profile, including scheduling and media",
                        f"user_files/{profile}/": "Incremento runtime snapshot for the current profile (PDFs, EPUBs, videos, writing, browser profiles, database)",
                        "config.json": "Incremento add-on config",
                        "restore.txt": "Restore instructions for a fresh install",
                        "data/priorities.json": "Card priorities (human-readable copy)",
                        "data/pdf_progress.json": "PDF reading positions, zoom levels, and appearance choices",
                        "data/highlights.json": "PDF text highlights",
                        "data/stats.json": "Session, daily and lifetime statistics",
                    },
                }
                zf.writestr(
                    "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2)
                )

            with zipfile.ZipFile(archive_tmp_path, "r") as check_zip:
                corrupt_member = check_zip.testzip()
            if corrupt_member:
                raise RuntimeError("Backup ZIP validation failed")
            if _active_profile() != profile:
                raise RuntimeError("The active profile changed while backup was running")
            os.replace(archive_tmp_path, path)

            retention_error = None
            if automatic_policy is not None:
                try:
                    _backup_schedule.prune_backups(
                        Path(path).parent, profile, automatic_policy["versions"],
                        protected=Path(path),
                    )
                except OSError as exc:
                    retention_error = str(exc)

            return {
                "anki_cards_exported": int(getattr(exporter, "count", 0) or 0),
                "priority_count": int(priority_count or 0),
                "user_files_copied": int(user_files_stats["files_copied"]) + 1,
                "user_files_skipped": int(user_files_stats["files_skipped"]),
                "retention_error": retention_error,
            }

    def _on_done(fut) -> None:
        global _full_backup_running
        _full_backup_running = False
        if profile != _active_profile():
            try:
                os.remove(archive_tmp_path)
            except OSError:
                pass
            fail_activity(activity_id, _t("root_backup_profile_changed"))
            if close_triggered:
                _record_close_backup_result(profile, failed=True)
            return
        try:
            result = fut.result()
        except Exception as e:
            try:
                os.remove(archive_tmp_path)
            except OSError:
                pass
            message = _t("root_backup_failed_auto" if automatic_policy else "root_backup_failed_manual", error=e)
            fail_activity(activity_id, message)
            if close_triggered:
                _record_close_backup_result(profile, failed=True)
            tooltip(message)
            return

        finish_activity(activity_id, detail=_t("root_backup_saved_to", path=path))

        if automatic_policy is not None:
            try:
                cfg = _load_addon_config(mw.addonManager, __name__)
                policies = cfg.get("automatic_backups", {})
                current = _backup_schedule.normalize_policy(policies.get(profile))
                if current["enabled"] and current["directory"] == automatic_policy["directory"]:
                    current["last_success"] = time.time()
                    if close_triggered:
                        current["last_close_failed"] = False
                    policies[profile] = current
                    cfg["automatic_backups"] = policies
                    _save_addon_config(mw.addonManager, __name__, cfg)
            except Exception:
                tooltip(_t("root_backup_schedule_timestamp_failed"))
            if result["retention_error"]:
                tooltip(_t("root_backup_retention_failed", error=result['retention_error']))
            else:
                tooltip(_t("root_backup_automatic_saved"))
            return

        tooltip(_t("root_backup_saved"))

    def _on_done_and_resume(fut) -> None:
        global _backup_idle_callbacks
        try:
            _on_done(fut)
        finally:
            try:
                if progress is not None:
                    progress.finish()
            finally:
                callbacks = _backup_idle_callbacks
                _backup_idle_callbacks = []
                for callback in callbacks:
                    QTimer.singleShot(0, callback)

    try:
        mw.taskman.run_in_background(_task, _on_done_and_resume)
    except Exception as exc:
        _full_backup_running = False
        fail_activity(activity_id, _t("root_backup_start_failed", error=exc))
        if progress is not None:
            progress.finish()
        try:
            os.remove(archive_tmp_path)
        except OSError:
            pass
        return False
    return True


def exportSupportBundleFunction() -> None:
    """Export redacted settings and recent typed diagnostics for bug reports."""
    import datetime
    from aqt.qt import QFileDialog

    global _diagnostic_recorder

    today = datetime.date.today().isoformat()
    default_name = os.path.expanduser(f"~/incremento_support_bundle_{today}.zip")
    path, _ = QFileDialog.getSaveFileName(
        mw,
        _t("root_support_export_title"),
        default_name,
        _t("root_backup_file_filter"),
    )
    if not path:
        return
    if not path.casefold().endswith(".zip"):
        path += ".zip"

    profile = _active_profile()
    if _diagnostic_recorder is None:
        _diagnostic_recorder = _diagnostics_mod.DiagnosticRecorder(
            _ADDON_DIR,
            profile,
        )
    recorder = _diagnostic_recorder
    _record_diagnostic_event("support_bundle_requested")

    current_config = copy.deepcopy(_load_addon_config(mw.addonManager, __name__))
    try:
        with open(os.path.join(_ADDON_DIR, "config.json"), "r", encoding="utf-8") as handle:
            default_config = json.load(handle)
    except Exception:
        default_config = {}
    environment = _diagnostic_environment_values()
    runtime_state = {
        "ui_state": str(getattr(mw, "state", "unknown") or "unknown"),
        "ui_interaction": _diagnostic_ui_health_fields(),
        "incremento_session": diagnostic_session_snapshot(),
    }

    mw.progress.start(label=_t("root_support_progress"), immediate=True)

    def _task():
        return _diagnostics_mod.build_support_bundle(
            path,
            addon_dir=_ADDON_DIR,
            profile=profile,
            recorder=recorder,
            config=current_config,
            default_config=default_config,
            environment=environment,
            runtime_state=runtime_state,
        )

    def _on_done(future) -> None:
        mw.progress.finish()
        try:
            result = future.result()
        except Exception as exc:
            _record_diagnostic_event(
                "support_bundle_failed",
                error_type=_diagnostics_mod.safe_exception_type(exc),
            )
            showInfo(_t("root_support_create_failed", error=exc))
            return

        _record_diagnostic_event(
            "support_bundle_created",
            event_count=result.get("event_count", 0),
            bundle_bytes=result.get("bundle_bytes", 0),
        )
        showInfo(_t("root_support_created", count=result.get('event_count', 0), path=path))

    # The bundle reads its own SQLite connection and fixed shipped files. It
    # must not wait behind a stalled CollectionOp, which is often the problem
    # the user is trying to capture.
    mw.taskman.run_in_background(_task, _on_done, uses_collection=False)


def _extract_card() -> None:
    """Option+X: grab the reviewer's selected text, open the extract-card dialog."""
    reviewer = getattr(mw, "reviewer", None)
    card = getattr(reviewer, "card", None) if reviewer else None
    if card is None:
        return
    mw.reviewer.web.page().runJavaScript(
        "window.getSelection()?.toString() || ''",
        lambda text: _on_extract_selection(text.strip(), card),
    )


def _on_extract_selection(selected_text: str, parent_card) -> None:
    parent_note = parent_card.note()
    initial_field_values = _initial_extract_field_values(parent_note, selected_text)

    parent_label = (
        parent_note.fields[0][:60].strip()
        if parent_note.fields
        else f"Card {parent_card.id}"
    )
    parent_source = derive_note_source_metadata(parent_note)
    metadata = build_incremento_metadata(
        source_type="Extract",
        source_title=parent_source.get("source_title") or parent_label,
        source_link=parent_source.get("source_link") or "",
        source_author=parent_source.get("source_author") or "",
        parent=parent_label,
        parent_card_id=getattr(parent_card, "id", None),
    )
    parent_in_tree = get_knowledge_tree_node(
        _ADDON_DIR,
        _active_profile(),
        int(getattr(parent_card, "id", 0) or 0),
    ) is not None
    tree_link_state = _knowledge_tree_link_state(parent_in_tree)
    _add_card_dock_mod.prepare_reviewer_extract(
        selected_text=selected_text,
        note_type_name="",
        deck_name="",
        field_values=initial_field_values,
        metadata=metadata,
        parent_card_id=int(getattr(parent_card, "id", 0) or 0),
        priority=_add_card_dock_mod.source_card_priority_for_card(
            getattr(parent_card, "id", None)
        ),
        mark_topic=False,
        knowledge_tree_link_enabled=bool(tree_link_state.get("enabled")),
        link_to_knowledge_tree=bool(tree_link_state.get("checked")),
        knowledge_tree_tooltip=str(tree_link_state.get("tooltip") or ""),
    )


def _open_priority_dialog_for_card(card) -> bool:
    """Open the priority assignment dialog for a specific card."""
    from .backend.topic_scheduler import is_topic_card
    from .backend.db import get_topic_schedule, set_topic_schedule

    if card is None:
        return False

    current = get_priority(_ADDON_DIR, _active_profile(), card.id)
    note = card.note()
    label_text = note.fields[0][:80].strip() if note.fields else ""

    a_factor = None
    interval = None
    if is_topic_card(card):
        a_factor, interval = get_topic_schedule(_ADDON_DIR, _active_profile(), card.id)

    dlg = PriorityDialog(
        current_priority=current,
        card_label=label_text,
        current_a_factor=a_factor,
        current_interval=interval,
        lower_is_more_important=configured_priority_lower_is_more_important(),
        parent=mw,
    )
    if dlg.exec():
        set_priority(_ADDON_DIR, _active_profile(), card.id, dlg.priority)
        msg = _t("root_reviewer_priority_set", priority=f"{dlg.priority:.0f}")
        if dlg.a_factor is not None:
            set_topic_schedule(_ADDON_DIR, _active_profile(), card.id, dlg.a_factor, interval or 1)
            msg += _t("root_reviewer_a_factor_set", value=f"{dlg.a_factor:.3f}")
        reviewer = getattr(mw, "reviewer", None)
        current_card = getattr(reviewer, "card", None) if reviewer else None
        if current_card is not None and getattr(current_card, "id", None) == getattr(card, "id", None):
            _sync_reviewer_priority_badge()
        tooltip(msg)
        return True
    return False


_browser_priority_toolbar_mod.register_open_priority_dialog_callback(_open_priority_dialog_for_card)


def _open_priority_dialog() -> None:
    """Open the priority assignment dialog for the currently reviewed card."""
    reviewer = getattr(mw, "reviewer", None)
    card = getattr(reviewer, "card", None) if reviewer else None
    if card is None:
        showInfo(_t("root_reviewer_no_review_card"))
        return
    _open_priority_dialog_for_card(card)


def _save_note_tags(note, tags: list[str]) -> None:
    note.tags = list(tags)
    try:
        mw.col.update_note(note)
        return
    except Exception:
        pass
    try:
        note.flush()
    except Exception:
        pass


def _open_reviewer_tag_dialog() -> None:
    reviewer = getattr(mw, "reviewer", None)
    card = getattr(reviewer, "card", None) if reviewer else None
    if card is None:
        showInfo(_t("root_reviewer_no_review_card"))
        return
    try:
        note = card.note()
    except Exception:
        note = None
    if note is None:
        showInfo(_t("root_reviewer_note_load_failed"))
        return

    try:
        all_tags = sorted(mw.col.tags.all(), key=lambda value: (str(value).lower(), str(value)))
    except Exception:
        all_tags = []
    current_tags = normalize_tag_list(getattr(note, "tags", []) or [])
    recent_tags = get_recent_reviewer_tags(_ADDON_DIR, _active_profile(), limit=10)
    if not all_tags and not recent_tags:
        showInfo(_t("root_reviewer_no_tags"))
        return
    dlg = ReviewerTagDialog(
        current_tags=current_tags,
        recent_tags=recent_tags,
        all_tags=all_tags,
        parent=mw,
    )
    if not dlg.exec():
        return

    selected_tags = dlg.selected_tags()
    updated_tags, added_tags = append_missing_tags(current_tags, selected_tags)
    if not added_tags:
        tooltip(_t("root_reviewer_tags_present"))
        return

    _save_note_tags(note, updated_tags)
    touch_recent_reviewer_tags(_ADDON_DIR, _active_profile(), added_tags, limit=10)
    summary = ", ".join(added_tags[:4])
    if len(added_tags) > 4:
        summary += ", ..."
    tooltip(_t("root_reviewer_tags_added", tags=summary))


_priority_shortcut = QShortcut(QKeySequence("Alt+P"), mw)
_priority_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(_priority_shortcut.activated, _open_priority_dialog)
_register_shortcut_action("set_priority", _priority_shortcut)

_extract_shortcut = QShortcut(QKeySequence("Alt+X"), mw)
_extract_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(_extract_shortcut.activated, _extract_card)
_register_shortcut_action("extract_card", _extract_shortcut)

_reviewer_buttons_shortcut = QShortcut(QKeySequence(), mw)
_reviewer_buttons_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(_reviewer_buttons_shortcut.activated, _toggle_reviewer_button_group)
_register_shortcut_action("toggle_reviewer_buttons", _reviewer_buttons_shortcut)

_reviewer_tag_shortcut = QShortcut(QKeySequence("Alt+T"), mw)
_reviewer_tag_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(_reviewer_tag_shortcut.activated, _open_reviewer_tag_dialog)
_register_shortcut_action("append_tags_reviewer", _reviewer_tag_shortcut)

_pdf_prev_page_shortcut = QShortcut(QKeySequence("Ctrl+Alt+Left"), mw)
_pdf_prev_page_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(
    _pdf_prev_page_shortcut.activated,
    lambda: _trigger_pdf_viewer_action("prev_page"),
)
_register_shortcut_action("pdf_prev_page", _pdf_prev_page_shortcut)

_pdf_next_page_shortcut = QShortcut(QKeySequence("Ctrl+Alt+Right"), mw)
_pdf_next_page_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(
    _pdf_next_page_shortcut.activated,
    lambda: _trigger_pdf_viewer_action("next_page"),
)
_register_shortcut_action("pdf_next_page", _pdf_next_page_shortcut)

_pdf_zoom_out_shortcut = QShortcut(QKeySequence("Ctrl+Alt+-"), mw)
_pdf_zoom_out_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(
    _pdf_zoom_out_shortcut.activated,
    lambda: _trigger_pdf_viewer_action("zoom_out"),
)
_register_shortcut_action("pdf_zoom_out", _pdf_zoom_out_shortcut)

_pdf_zoom_in_shortcut = QShortcut(QKeySequence("Ctrl+Alt+="), mw)
_pdf_zoom_in_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(
    _pdf_zoom_in_shortcut.activated,
    lambda: _trigger_pdf_viewer_action("zoom_in"),
)
_register_shortcut_action("pdf_zoom_in", _pdf_zoom_in_shortcut)

_pdf_mark_read_shortcut = QShortcut(QKeySequence("Ctrl+Alt+M"), mw)
_pdf_mark_read_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(
    _pdf_mark_read_shortcut.activated,
    lambda: _trigger_pdf_viewer_action("mark_read"),
)
_register_shortcut_action("pdf_mark_read", _pdf_mark_read_shortcut)


def addVideoFunction() -> None:
    """Incremento -> Add Content -> Add Video"""
    deck_names = [d.name for d in mw.col.decks.all_names_and_ids()]
    from .frontend.add_video_dialog import AddVideoDialog

    dlg = AddVideoDialog(deck_names, default_deck="Topics", addon_dir=_ADDON_DIR, parent=mw)
    if not dlg.exec():
        return
    source_mode = dlg.source_mode
    deck_name = dlg.deck_name
    tags = dlg.tags
    active_profile = _active_profile()

    if source_mode in ("youtube", "vimeo"):
        url = resolve_video_url_for_embed(dlg.video_url)
        if not url:
            showInfo(_t("root_video_enter_url"))
            return
        if not is_supported_video_url(url):
            showInfo(_t("root_video_invalid_url"))
            return
        title = dlg.title or url
        max_height = dlg.download_max_height
        original_quality = dlg.download_original_quality
    else:
        url = ""
        local_path = dlg.local_video_path
        if not local_path:
            showInfo(_t("root_video_choose_file"))
            return
        if not os.path.isfile(local_path):
            showInfo(_t("root_video_file_missing"))
            return
        title = dlg.title or os.path.splitext(os.path.basename(local_path))[0]
        max_height = None
        original_quality = False
        local_encode_mode = dlg.local_encode_mode

    import_operation: ImportOperation | None = None

    def _add_card(local_relpath: str = "", youtube_url: str = url) -> bool:
        try:
            metadata = None
            if import_operation is not None:
                metadata = build_incremento_metadata(
                    source_type="Video",
                    source_title=title,
                    source_link=local_relpath or youtube_url,
                    content_id=import_operation.content_id,
                )
            card_id = add_video_card(
                mw.col,
                youtube_url,
                title,
                deck_name=deck_name,
                tags=tags,
                local_video_file=local_relpath,
                metadata=metadata,
            )
            if import_operation is not None:
                note_id = int(mw.col.get_card(int(card_id)).nid)
                import_operation.bind_anki(card_id=int(card_id), note_id=note_id)
                import_operation.commit(storage_key=local_relpath)
            mw.col.reset()
            if local_relpath:
                tooltip(_t("root_video_added_local", title=title, deck=deck_name))
            else:
                tooltip(_t("root_video_added", title=title, deck=deck_name))
            return True
        except Exception as e:
            if import_operation is not None:
                import_operation.rollback(error_code=type(e).__name__)
            showInfo(_t("root_video_add_failed", error=e))
            return False

    if source_mode == "local":
        import_operation = ImportOperation(
            _ADDON_DIR, active_profile, "video"
        )
        try:
            label = (
                _t("root_video_importing_local")
                if local_encode_mode == "original"
                else _t("root_video_importing_encoding")
            )
            mw.progress.start(
                label=label,
                immediate=True,
                value=0,
                max=100,
            )
        except TypeError:
            mw.progress.start(label=label, immediate=True)

        def _progress_main(percent: int, label: str) -> None:
            try:
                mw.progress.update(label=label, value=int(percent), max=100)
            except TypeError:
                mw.progress.update(label=label)

        def _progress_cb(percent: int, label: str) -> None:
            mw.taskman.run_on_main(
                lambda p=percent, label_text=label: _progress_main(p, label_text)
            )

        def _task():
            return import_local_video_file(
                _ADDON_DIR,
                active_profile,
                local_path,
                encode_mode=local_encode_mode,
                progress_cb=_progress_cb,
                created_relpath_cb=import_operation.track_created_relpath,
            )

        def _on_done(fut) -> None:
            mw.progress.finish()
            try:
                local_relpath = fut.result()
            except Exception as e:
                import_operation.rollback(error_code=type(e).__name__)
                showInfo(_t("root_video_local_import_failed", error=e))
                return
            if _active_profile() != active_profile:
                import_operation.rollback(error_code="profile_changed")
                showInfo(_t("root_video_profile_changed"))
                return
            _add_card(local_relpath=local_relpath, youtube_url="")

        mw.taskman.run_in_background(_task, _on_done, uses_collection=False)
        return

    if not dlg.download_locally:
        _add_card()
        return

    import_operation = ImportOperation(
        _ADDON_DIR, active_profile, "video"
    )

    try:
        label = (
            _t("root_video_downloading_original")
            if original_quality
            else _t("root_video_downloading_compressing")
        )
        mw.progress.start(
            label=label,
            immediate=True,
            value=0,
            max=100,
        )
    except TypeError:
        mw.progress.start(label=label, immediate=True)

    def _progress_main(percent: int, label: str) -> None:
        try:
            mw.progress.update(label=label, value=int(percent), max=100)
        except TypeError:
            mw.progress.update(label=label)

    def _progress_cb(percent: int, label: str) -> None:
        mw.taskman.run_on_main(
            lambda p=percent, label_text=label: _progress_main(p, label_text)
        )

    def _task():
        return download_and_compress_video(
            _ADDON_DIR,
            active_profile,
            url,
            overwrite=(max_height is not None) or original_quality,
            progress_cb=_progress_cb,
            max_height=max_height,
            original_quality=original_quality,
            created_relpath_cb=import_operation.track_created_relpath,
        )

    def _on_done(fut) -> None:
        mw.progress.finish()
        try:
            local_relpath = fut.result()
        except Exception as e:
            import_operation.rollback(error_code=type(e).__name__)
            showInfo(_t("root_video_download_failed", error=e))
            return
        if _active_profile() != active_profile:
            import_operation.rollback(error_code="profile_changed")
            showInfo(_t("root_video_profile_changed"))
            return
        _add_card(local_relpath=local_relpath)

    mw.taskman.run_in_background(_task, _on_done, uses_collection=False)


def addWritingFunction() -> None:
    """Incremento -> Add Content -> Add Markdown Writing"""
    from .frontend.add_writing_dialog import AddWritingDialog

    deck_names = [d.name for d in mw.col.decks.all_names_and_ids()]
    dlg = AddWritingDialog(deck_names, default_deck="Topics", parent=mw)
    if not dlg.exec():
        return

    title = dlg.title.strip()
    if not title:
        showInfo(_t("root_writing_enter_title"))
        return

    try:
        metadata = None
        if dlg.import_mode == "webpage_markdown" and dlg.source_url:
            metadata = build_incremento_metadata(
                source_type="Web",
                source_title=title,
                source_link=dlg.source_url,
            )
        add_writing_card(
            _ADDON_DIR,
            mw.col,
            title=title,
            deck_name=dlg.deck_name,
            tags=dlg.tags,
            initial_markdown=dlg.initial_markdown,
            preferred_filename=dlg.filename,
            metadata=metadata,
        )
        mw.col.reset()
        tooltip(_t("root_writing_card_added", title=title, deck=dlg.deck_name))
    except Exception as e:
        showInfo(_t("root_writing_add_failed", error=e))


def addLocalFileFunction() -> None:
    """Incremento -> Add Content -> Add Local File"""
    from .frontend.add_local_file_dialog import AddLocalFileDialog

    deck_names = [d.name for d in mw.col.decks.all_names_and_ids()]
    dlg = AddLocalFileDialog(deck_names, default_deck="Topics", parent=mw)
    if not dlg.exec():
        return

    source_path = dlg.source_path
    if not source_path:
        showInfo(_t("root_local_file_choose"))
        return
    if not os.path.isfile(source_path):
        showInfo(_t("root_local_file_missing"))
        return

    title = dlg.title or os.path.splitext(os.path.basename(source_path))[0]

    try:
        add_local_file_card(
            _ADDON_DIR,
            _active_profile(),
            mw.col,
            source_path=source_path,
            title=title,
            deck_name=dlg.deck_name,
            tags=dlg.tags,
            mode=dlg.storage_mode,
            note_text=dlg.note_text,
        )
        mw.col.reset()
        tooltip(_t("root_local_file_added", title=title, deck=dlg.deck_name))
    except Exception as e:
        showInfo(_t("root_local_file_add_failed", error=e))


def addWebpageFunction() -> None:
    from .frontend.webpage_dialog import WebpageToPdfDialog
    from .backend.pdf_manager import add_pdf_card

    dlg = WebpageToPdfDialog(mw)
    if not dlg.exec():
        return
    pdf_path = str(dlg.pdf_path or "")
    try:
        add_pdf_card(
            _ADDON_DIR,
            mw.col,
            pdf_path,
            dlg.title_text,
            tags=dlg.tags_to_apply,
            metadata=build_incremento_metadata(
                source_type="Web",
                source_title=dlg.title_text,
                source_link=dlg.source_url or "",
            ),
        )
        showInfo(_t("root_webpage_pdf_added", title=dlg.title_text))
    except Exception as e:
        showInfo(_t("root_webpage_pdf_failed", error=e))
    finally:
        if pdf_path:
            try:
                os.remove(pdf_path)
            except OSError:
                pass


def reindexPdfTextFunction() -> None:
    import threading

    from .backend.pdf_manager import get_pdf_dir
    from .backend.search_indexer import index_pdf_documents

    profile = _active_profile()
    try:
        note_ids = mw.col.find_notes(f'note:"{PDF_NOTE_TYPE}"')
    except Exception as e:
        showInfo(_t("root_pdf_list_failed", error=e))
        return

    if not note_ids:
        showInfo(_t("root_browser_no_pdf_reindex"))
        return

    pdf_dir = get_pdf_dir(profile)
    documents: list[tuple[int, str]] = []
    missing = 0
    for note_id in note_ids:
        try:
            note = mw.col.get_note(note_id)
            pdf_path = os.path.join(pdf_dir, str(note["PDF_Filename"] or ""))
            if not os.path.isfile(pdf_path):
                missing += 1
                continue
            documents.extend(
                (int(card_id), pdf_path)
                for card_id in mw.col.find_cards(f"nid:{int(note_id)}")
            )
        except Exception:
            missing += 1

    if not documents:
        showInfo(_t("root_browser_no_pdf_files"))
        return

    cancelled = threading.Event()
    try:
        mw.progress.start(
            label=_t("root_pdf_reindex_background"),
            immediate=True,
            max=len(documents),
            can_cancel=True,
        )
    except TypeError:
        mw.progress.start(label=_t("root_pdf_reindex_background"), immediate=True)

    def progress(completed: int, total: int) -> None:
        def update() -> None:
            try:
                mw.progress.update(
                    label=_t("root_pdf_reindex_progress", completed=completed, total=total),
                    value=completed,
                    max=total,
                )
            except TypeError:
                mw.progress.update(label=_t("root_pdf_reindex_progress", completed=completed, total=total))
            try:
                want_cancel = getattr(mw.progress, "want_cancel", None)
                if callable(want_cancel) and want_cancel():
                    cancelled.set()
            except Exception:
                pass

        mw.taskman.run_on_main(update)

    def task():
        return index_pdf_documents(
            _ADDON_DIR,
            profile,
            documents,
            cancelled=cancelled.is_set,
            progress=progress,
            force=True,
        )

    def done(future) -> None:
        mw.progress.finish()
        if profile != _active_profile():
            return
        try:
            result = future.result()
        except Exception as exc:
            showInfo(_t("root_pdf_reindex_failed", error=exc))
            return
        status_key = "root_pdf_reindex_cancelled" if result.cancelled else "root_pdf_reindex_complete"
        showInfo(_t(status_key) + "\n\n" + "\n".join([
            _t("root_pdf_reindex_processed", count=result.indexed),
            _t("root_pdf_reindex_skipped", count=result.skipped),
            _t("root_pdf_reindex_missing", count=missing),
            _t("root_pdf_reindex_errors", count=result.failed),
        ]))

    mw.taskman.run_in_background(task, done, uses_collection=False)


def _ocr_note_ids_for_card_ids(card_ids: list[int] | None = None) -> list[int]:
    note_ids: list[int] = []
    seen: set[int] = set()
    if card_ids is None:
        try:
            rows = mw.col.db.list("SELECT DISTINCT nid FROM cards")
        except Exception:
            rows = []
        for raw_note_id in rows:
            try:
                note_id = int(raw_note_id)
            except Exception:
                continue
            if note_id in seen:
                continue
            seen.add(note_id)
            note_ids.append(note_id)
        return note_ids

    for raw_card_id in list(card_ids or []):
        try:
            card = mw.col.get_card(int(raw_card_id))
            note_id = int(card.nid)
        except Exception:
            continue
        if note_id in seen:
            continue
        seen.add(note_id)
        note_ids.append(note_id)
    return note_ids


def _run_note_ocr_scan(note_ids: list[int], *, label: str) -> None:
    from .backend.image_ocr import ocr_note_images, tesseract_ready_message

    if not note_ids:
        showInfo(_t("root_browser_no_eligible_cards"))
        return

    missing_dep = tesseract_ready_message()
    if missing_dep:
        showInfo(_t("root_ocr_tesseract_required", details=missing_dep))
        return

    media_dir = ""
    try:
        media_dir = mw.col.media.dir()
    except Exception as exc:
        showInfo(_t("root_ocr_media_access_failed", error=exc))
        return

    scanned = 0
    updated = 0
    skipped_special = 0
    no_images = 0
    missing_images = 0
    failures: list[str] = []

    mw.progress.start(label=label, immediate=True)
    try:
        total = len(note_ids)
        for idx, note_id in enumerate(note_ids, start=1):
            try:
                mw.progress.update(label=_t("root_ocr_progress", index=idx, total=total, label=label))
            except Exception:
                pass
            try:
                note = mw.col.get_note(int(note_id))
            except Exception as exc:
                failures.append(f"nid:{note_id}: {exc}")
                continue
            scanned += 1
            try:
                result = ocr_note_images(
                    _ADDON_DIR,
                    _active_profile(),
                    note,
                    media_dir=media_dir,
                )
            except Exception as exc:
                failures.append(f"nid:{note_id}: {exc}")
                continue
            if not result.get("supported"):
                skipped_special += 1
                continue
            if not result.get("images_found"):
                no_images += 1
            if result.get("updated"):
                updated += 1
            missing_images += len(list(result.get("missing_images") or []))
            for msg in list(result.get("errors") or []):
                failures.append(f"nid:{note_id}: {msg}")
    finally:
        mw.progress.finish()

    try:
        mw.col.reset()
    except Exception:
        pass

    lines = [_t("root_ocr_complete", label=label) + "\n"]
    lines.append(_t("root_ocr_scanned", count=scanned))
    lines.append(_t("root_ocr_updated", count=updated))
    lines.append(_t("root_ocr_skipped_types", count=skipped_special))
    lines.append(_t("root_ocr_no_images", count=no_images))
    lines.append(_t("root_ocr_missing_images", count=missing_images))
    if failures:
        lines.append(_t("root_pdf_reindex_errors", count=len(failures)))
        for msg in failures[:10]:
            lines.append(f"  • {msg}")
        if len(failures) > 10:
            lines.append("  " + _t("root_more_failures", count=len(failures) - 10))
    showInfo("\n".join(lines))


def _rebuild_ocr_cache_for_note_ids(note_ids: list[int], *, label: str) -> None:
    from .backend.image_ocr import rebuild_note_ocr_index_from_field, supported_image_ocr_note

    if not note_ids:
        showInfo(_t("root_browser_no_eligible_cards"))
        return

    rebuilt = 0
    skipped_special = 0
    blank = 0
    failures: list[str] = []

    mw.progress.start(label=label, immediate=True)
    try:
        total = len(note_ids)
        for idx, note_id in enumerate(note_ids, start=1):
            try:
                mw.progress.update(label=_t("root_ocr_progress", index=idx, total=total, label=label))
            except Exception:
                pass
            try:
                note = mw.col.get_note(int(note_id))
            except Exception as exc:
                failures.append(f"nid:{note_id}: {exc}")
                continue
            if not supported_image_ocr_note(note):
                skipped_special += 1
                continue
            try:
                text = rebuild_note_ocr_index_from_field(_ADDON_DIR, _active_profile(), note)
            except Exception as exc:
                failures.append(f"nid:{note_id}: {exc}")
                continue
            if text:
                rebuilt += 1
            else:
                blank += 1
    finally:
        mw.progress.finish()

    lines = [_t("root_ocr_complete", label=label) + "\n"]
    lines.append(_t("root_ocr_rebuilt", count=rebuilt))
    lines.append(_t("root_ocr_blank", count=blank))
    lines.append(_t("root_ocr_skipped_types", count=skipped_special))
    if failures:
        lines.append(_t("root_pdf_reindex_errors", count=len(failures)))
        for msg in failures[:10]:
            lines.append(f"  • {msg}")
        if len(failures) > 10:
            lines.append("  " + _t("root_more_failures", count=len(failures) - 10))
    showInfo("\n".join(lines))


def ocrImageTextFunction() -> None:
    _run_note_ocr_scan(
        _ocr_note_ids_for_card_ids(),
        label=_t("root_ocr_image_text_label"),
    )


def reindexImageOcrCacheFunction() -> None:
    _rebuild_ocr_cache_for_note_ids(
        _ocr_note_ids_for_card_ids(),
        label=_t("root_ocr_reindex_label"),
    )


def _ocr_browser_selection(browser) -> None:
    card_ids = _browser_selected_incremento_card_ids(browser)
    if not card_ids:
        showInfo(_t("root_browser_select_rows"))
        return
    _run_note_ocr_scan(
        _ocr_note_ids_for_card_ids(card_ids),
        label=_t("root_ocr_image_text_label"),
    )


def _show_browser_hidden_fields(browser) -> None:
    card_ids = _browser_selected_incremento_card_ids(browser)
    if not card_ids:
        showInfo(_t("root_browser_select_rows"))
        return

    note_ids = _ocr_note_ids_for_card_ids(card_ids)
    if not note_ids:
        showInfo(_t("root_browser_no_notes"))
        return

    chunks: list[str] = []
    for note_id in note_ids:
        try:
            note = mw.col.get_note(int(note_id))
            model = mw.col.models.get(note.mid)
            model_name = str((model or {}).get("name") or _t("root_hidden_fields_note")).strip() or _t("root_hidden_fields_note")
        except Exception as exc:
            chunks.append(_t("root_hidden_fields_load_failed", note_id=note_id, error=exc))
            continue

        title = ""
        try:
            title = str((list(getattr(note, "fields", []) or [""])[:1] or [""])[0] or "").strip()
        except Exception:
            title = ""
        header = _t("root_hidden_fields_header", note_id=note_id, model=model_name)
        if title:
            header += "\n" + _t("root_hidden_fields_note_title", title=title)

        rows = hidden_field_values(note)
        if not rows:
            body = _t("root_hidden_fields_none")
        else:
            lines: list[str] = []
            for field_name in INCREMENTO_HIDDEN_FIELDS:
                match = next((value for name, value in rows if name == field_name), None)
                if match is None:
                    continue
                value_text = str(match or "").strip()
                lines.append(f"{field_name}:\n{value_text or _t('root_hidden_fields_empty')}")
            body = "\n\n".join(lines) if lines else _t("root_hidden_fields_none")
        chunks.append(f"{header}\n\n{body}")

    dlg = QDialog(mw)
    dlg.setWindowTitle(_t("root_hidden_fields_title"))
    dlg.resize(860, 620)
    layout = QVBoxLayout(dlg)
    browser = QTextBrowser(dlg)
    browser.setReadOnly(True)
    browser.setOpenExternalLinks(True)
    separator = "\n\n" + ("-" * 72) + "\n\n"
    browser.setPlainText(separator.join(chunks))
    layout.addWidget(browser, 1)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dlg)
    buttons.button(QDialogButtonBox.StandardButton.Close).setText(_t("admin_entries_close"))
    buttons.rejected.connect(dlg.reject)
    buttons.accepted.connect(dlg.accept)
    layout.addWidget(buttons)
    dlg.exec()


def _hide_incremento_hidden_fields_in_editor(editor) -> None:
    _track_editor_for_ocr_sync(editor)
    if configured_show_incremento_fields():
        return
    note = getattr(editor, "note", None)
    if note is None:
        return

    field_names: list[str] = []
    hidden_indexes: list[int] = []
    try:
        for idx, field in enumerate(list(note.note_type().get("flds") or [])):
            field_name = str((field or {}).get("name") or "").strip()
            if field_name in INCREMENTO_HIDDEN_FIELDS:
                field_names.append(field_name)
                hidden_indexes.append(idx)
    except Exception:
        field_names = []
        hidden_indexes = []
    if not field_names:
        return

    hidden_json = json.dumps(field_names)
    hidden_index_json = json.dumps(hidden_indexes)
    editor.web.eval(
        f"""
(() => {{
  const hidden = new Set({hidden_json});
  const hiddenIndexes = new Set({hidden_index_json});
  const hide = () => {{
    document.querySelectorAll(".field-container").forEach((container, idx) => {{
      const label = (container.querySelector(".field-name")?.textContent || "").trim();
      if (!hidden.has(label) && !hiddenIndexes.has(idx)) {{
        return;
      }}
      container.style.display = "none";
      container.dataset.incrementoHiddenField = "1";
    }});
  }};
  hide();
  requestAnimationFrame(hide);
  setTimeout(hide, 60);
}})();
"""
    )


def _filter_incremento_hidden_browser_columns(columns) -> None:
    if configured_show_incremento_fields():
        return
    for key, column in list((columns or {}).items()):
        candidates = [
            str(key or "").strip(),
            str(getattr(column, "cards_mode_label", "") or "").strip(),
            str(getattr(column, "notes_mode_label", "") or "").strip(),
        ]
        if any(matches_hidden_field_reference(candidate) for candidate in candidates):
            columns.pop(key, None)


def _sync_ocr_index_for_open_editor_notes(changes, handler=None) -> None:
    if not bool(getattr(changes, "note_text", False)):
        return

    try:
        from .backend.image_ocr import rebuild_note_ocr_index_from_field, supported_image_ocr_note
    except Exception:
        return

    synced_note_ids: set[int] = set()
    for editor in list(_ocr_sync_editors):
        note = getattr(editor, "note", None)
        note_id = int(getattr(note, "id", 0) or 0) if note is not None else 0
        if note is None or note_id <= 0 or note_id in synced_note_ids:
            continue
        try:
            if not supported_image_ocr_note(note):
                continue
            rebuild_note_ocr_index_from_field(_ADDON_DIR, _active_profile(), note)
            synced_note_ids.add(note_id)
        except Exception:
            continue


def _prune_incremento_hidden_browser_active_columns(browser) -> None:
    if configured_show_incremento_fields():
        return
    table = getattr(browser, "table", None)
    state = getattr(table, "_state", None)
    if state is None:
        return

    active_columns = list(getattr(state, "active_columns", []) or [])
    filtered_columns = [
        column_key
        for column_key in active_columns
        if not matches_hidden_field_reference(column_key)
    ]
    if filtered_columns == active_columns:
        return

    try:
        setattr(state, "_active_columns", filtered_columns)
    except Exception:
        pass

    col = getattr(browser, "col", None)
    if col is None:
        return
    try:
        if bool(getattr(state, "is_notes_mode", lambda: False)()):
            col.set_browser_note_columns(filtered_columns)
        else:
            col.set_browser_card_columns(filtered_columns)
    except Exception:
        return


def _prune_stale_progress_rows() -> dict[str, int]:
    """
    Remove progress rows whose card_id no longer exists.
    Returns per-table deleted counts.
    """
    conn = get_connection(_ADDON_DIR, _active_profile())
    counts = {"pdf_progress": 0, "video_progress": 0, "web_progress": 0}
    live_ids = _all_live_card_ids_any_profile()
    total_deleted = 0

    for table in ("pdf_progress", "video_progress", "web_progress"):
        try:
            rows = conn.execute(f"SELECT card_id FROM {table}").fetchall()
        except Exception:
            continue
        stale_ids = []
        for row in rows:
            try:
                cid = int(row[0])
            except Exception:
                continue
            if cid not in live_ids:
                stale_ids.append(cid)
        if not stale_ids:
            continue
        conn.executemany(
            f"DELETE FROM {table} WHERE card_id = ?",
            [(cid,) for cid in stale_ids],
        )
        counts[table] = len(stale_ids)
        total_deleted += len(stale_ids)

    if total_deleted:
        conn.commit()
    return counts


def _prune_stale_ocr_rows() -> dict[str, int]:
    """Delete OCR cache rows whose note_id or card_id no longer exists."""
    return prune_note_ocr_index_rows(
        _ADDON_DIR,
        _active_profile(),
        live_note_ids=_all_live_note_ids_any_profile(),
        live_card_ids=_all_live_card_ids_any_profile(),
    )


def _prune_stale_document_text_index_rows() -> dict[str, int]:
    """Delete PDF/EPUB search-index rows whose card_id no longer exists."""
    return prune_document_text_index_rows(
        _ADDON_DIR,
        _active_profile(),
        live_card_ids=_all_live_card_ids_any_profile(),
    )


def _format_pruned_progress_summary(counts: dict[str, int]) -> str:
    pdf_n = int(counts.get("pdf_progress", 0) or 0)
    video_n = int(counts.get("video_progress", 0) or 0)
    web_n = int(counts.get("web_progress", 0) or 0)
    total = pdf_n + video_n + web_n
    if total <= 0:
        return ""
    return _t("root_cleanup_progress_summary", total=total, pdf=pdf_n, video=video_n, web=web_n)


def _format_pruned_document_text_index_summary(counts: dict[str, int]) -> str:
    pdf_n = int(counts.get("pdf_text_index", 0) or 0)
    epub_n = int(counts.get("epub_text_index", 0) or 0)
    total = int(counts.get("document_text_index_total", 0) or 0)
    if total <= 0:
        return ""
    return _t("root_cleanup_index_summary", total=total, pdf=pdf_n, epub=epub_n)


def _format_pruned_ocr_summary(counts: dict[str, int]) -> str:
    missing_note = int(counts.get("note_ocr_index_missing_note", 0) or 0)
    missing_card = int(counts.get("note_ocr_index_missing_card", 0) or 0)
    total = int(counts.get("note_ocr_index_total", 0) or 0)
    if total <= 0:
        return ""
    return _t("root_cleanup_ocr_summary", total=total, notes=missing_note, cards=missing_card)


def _current_profile_name() -> str:
    pm = getattr(mw, "pm", None)
    if pm is None:
        return "Unknown"
    for attr in ("name", "profileName"):
        v = getattr(pm, attr, None)
        try:
            if callable(v):
                got = v()
            else:
                got = v
            if got:
                return str(got)
        except Exception:
            continue
    return "Unknown"


def _available_profile_names() -> list[str]:
    pm = getattr(mw, "pm", None)
    names: set[str] = set()
    current_name = _current_profile_name()
    if current_name and current_name != "Unknown":
        names.add(current_name)
    if pm is None:
        return sorted(names, key=str.casefold)

    base = getattr(pm, "base", None)
    try:
        base = base() if callable(base) else base
    except Exception:
        base = None
    if not base or not os.path.isdir(base):
        return sorted(names, key=str.casefold)

    for name in os.listdir(base):
        pdir = os.path.join(base, name)
        if not os.path.isdir(pdir):
            continue
        if os.path.isfile(os.path.join(pdir, "collection.anki2")):
            names.add(str(name))
    return sorted(names, key=str.casefold)


def _iter_other_profile_collections() -> list[tuple[str, str]]:
    """Return [(profile_name, collection_db_path)] for profiles other than current."""
    pm = getattr(mw, "pm", None)
    if pm is None:
        return []

    base = getattr(pm, "base", None)
    try:
        base = base() if callable(base) else base
    except Exception:
        base = None
    if not base or not os.path.isdir(base):
        return []

    current_name = _current_profile_name()
    current_folder = None
    pf = getattr(pm, "profileFolder", None)
    try:
        current_folder = pf() if callable(pf) else pf
    except Exception:
        current_folder = None
    if current_folder:
        current_folder = os.path.realpath(str(current_folder))

    out: list[tuple[str, str]] = []
    for name in sorted(os.listdir(base)):
        pdir = os.path.join(base, name)
        if not os.path.isdir(pdir):
            continue
        if name == current_name:
            continue
        if current_folder and os.path.realpath(pdir) == current_folder:
            continue
        db_path = os.path.join(pdir, "collection.anki2")
        if os.path.isfile(db_path):
            out.append((name, db_path))
    return out


def _all_live_card_ids_any_profile() -> set[int]:
    """Union of card IDs from current + other profiles."""
    live_ids = set(int(cid) for cid in mw.col.db.list("SELECT id FROM cards"))
    for _, db_path in _iter_other_profile_collections():
        conn = None
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            for (cid,) in conn.execute("SELECT id FROM cards"):
                try:
                    live_ids.add(int(cid))
                except Exception:
                    pass
        except Exception:
            continue
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
    return live_ids


def _all_live_note_ids_any_profile() -> set[int]:
    """Union of note IDs from current + other profiles."""
    live_ids = set(int(nid) for nid in mw.col.db.list("SELECT id FROM notes"))
    for _, db_path in _iter_other_profile_collections():
        conn = None
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            for (nid,) in conn.execute("SELECT id FROM notes"):
                try:
                    live_ids.add(int(nid))
                except Exception:
                    pass
        except Exception:
            continue
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
    return live_ids


def _profiles_referencing_files(candidates: list[str], kind: str) -> dict[str, list[str]]:
    """
    For each candidate filename, return profile names that reference it in notes.flds
    or in profile-local source tables.
    kind: "pdf" or "video".
    """
    refs: dict[str, list[str]] = {}
    if not candidates:
        return refs

    for profile_name, db_path in _iter_other_profile_collections():
        conn = None
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            for fname in candidates:
                tokens = [fname]
                if kind == "video":
                    tokens = [f"videos/{fname}", fname]
                hit = False
                for token in tokens:
                    row = conn.execute(
                        "SELECT 1 FROM notes WHERE instr(flds, ?) > 0 LIMIT 1",
                        (token,),
                    ).fetchone()
                    if row:
                        hit = True
                        break
                if not hit and kind == "pdf":
                    row = conn.execute(
                        "SELECT 1 FROM pdf_card_sources WHERE pdf_filename = ? LIMIT 1",
                        (fname,),
                    ).fetchone()
                    if row:
                        hit = True
                if hit:
                    refs.setdefault(fname, []).append(profile_name)
        except Exception:
            continue
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
    return refs


def _partition_any_profile_ties(candidates: list[str], kind: str) -> tuple[list[str], list[str], dict[str, list[str]]]:
    """Split candidates into (deletable, protected, refs_map)."""
    refs_map = _profiles_referencing_files(candidates, kind)
    protected = sorted([f for f in candidates if f in refs_map])
    deletable = [f for f in candidates if f not in refs_map]
    return deletable, protected, refs_map


def _backfill_pdf_source_filenames() -> None:
    try:
        conn = get_connection(_ADDON_DIR, _active_profile())
        note_ids = mw.col.find_notes(f'note:"{PDF_NOTE_TYPE}"')
        for nid in note_ids:
            try:
                note = mw.col.get_note(nid)
                filename = str(note["PDF_Filename"] or "").strip()
                if not filename:
                    continue
                card_ids = mw.col.find_cards(f"nid:{nid}")
                if not card_ids:
                    continue
                try:
                    sync_pdf_card_file_references(
                        _ADDON_DIR,
                        _active_profile(),
                        mw.col,
                        int(card_ids[0]),
                    )
                except Exception:
                    conn.execute(
                        "UPDATE pdf_card_sources SET pdf_filename = ? "
                        "WHERE pdf_card_id = ? AND pdf_filename != ?",
                        (filename, int(card_ids[0]), filename),
                    )
            except Exception:
                continue
        conn.commit()
    except Exception:
        pass


def _count_stale_progress_rows() -> dict[str, int]:
    """Return per-table stale row counts without deleting."""
    conn = get_connection(_ADDON_DIR, _active_profile())
    counts = {"pdf_progress": 0, "video_progress": 0, "web_progress": 0}
    live_ids = _all_live_card_ids_any_profile()
    for table in ("pdf_progress", "video_progress", "web_progress"):
        try:
            rows = conn.execute(f"SELECT card_id FROM {table}").fetchall()
        except Exception:
            continue
        stale = 0
        for row in rows:
            try:
                cid = int(row[0])
            except Exception:
                continue
            if cid not in live_ids:
                stale += 1
        counts[table] = stale
    return counts


def _count_stale_ocr_rows() -> dict[str, int]:
    """Return stale OCR cache row counts without deleting."""
    conn = get_connection(_ADDON_DIR, _active_profile())
    counts = {
        "note_ocr_index_missing_note": 0,
        "note_ocr_index_missing_card": 0,
        "note_ocr_index_total": 0,
    }
    live_note_ids = _all_live_note_ids_any_profile()
    live_card_ids = _all_live_card_ids_any_profile()
    try:
        rows = conn.execute("SELECT note_id, card_id FROM note_ocr_index").fetchall()
    except Exception:
        return counts
    for note_id, card_id in rows:
        try:
            normalized_note_id = int(note_id or 0)
            normalized_card_id = int(card_id or 0)
        except Exception:
            continue
        if normalized_note_id not in live_note_ids:
            counts["note_ocr_index_missing_note"] += 1
            counts["note_ocr_index_total"] += 1
            continue
        if normalized_card_id not in live_card_ids:
            counts["note_ocr_index_missing_card"] += 1
            counts["note_ocr_index_total"] += 1
    return counts


def _count_stale_document_text_index_rows() -> dict[str, int]:
    """Return stale PDF/EPUB search-index row counts without deleting."""
    conn = get_connection(_ADDON_DIR, _active_profile())
    counts = {
        "pdf_text_index": 0,
        "epub_text_index": 0,
        "document_text_index_total": 0,
    }
    live_card_ids = _all_live_card_ids_any_profile()
    for table in ("pdf_text_index", "epub_text_index"):
        try:
            rows = conn.execute(f"SELECT card_id FROM {table}").fetchall()
        except Exception:
            continue
        stale = 0
        for (card_id,) in rows:
            try:
                normalized_card_id = int(card_id or 0)
            except Exception:
                continue
            if normalized_card_id not in live_card_ids:
                stale += 1
        counts[table] = stale
        counts["document_text_index_total"] += stale
    return counts


def _scan_orphan_pdfs() -> tuple[str, list[str], int]:
    from .backend.pdf_manager import get_pdf_dir

    _backfill_pdf_source_filenames()
    pdf_dir = get_pdf_dir()
    disk_files = {
        f for f in os.listdir(pdf_dir)
        if f.lower().endswith(".pdf")
    }
    if not disk_files:
        return pdf_dir, [], 0

    referenced = set()
    try:
        note_ids = mw.col.find_notes(f'note:"{PDF_NOTE_TYPE}"')
        for nid in note_ids:
            note = mw.col.get_note(nid)
            fname = str(note["PDF_Filename"] or "").strip()
            if fname:
                referenced.add(fname)
    except Exception:
        pass
    try:
        referenced.update(get_pdf_referenced_filenames(_ADDON_DIR, _active_profile()))
    except Exception:
        pass

    orphans = sorted(disk_files - referenced)
    total_bytes = 0
    for fname in orphans:
        fpath = os.path.join(pdf_dir, fname)
        try:
            total_bytes += os.path.getsize(fpath)
        except OSError:
            pass
    return pdf_dir, orphans, total_bytes


def _scan_orphan_videos() -> tuple[str, list[str], int]:
    videos_dir = str(_paths.get_videos_dir(_ADDON_DIR, _active_profile()))
    if not os.path.isdir(videos_dir):
        return videos_dir, [], 0

    disk_files = [
        f
        for f in os.listdir(videos_dir)
        if f.lower().endswith((".mp4", ".mkv", ".webm", ".mov", ".m4v"))
        and os.path.isfile(os.path.join(videos_dir, f))
    ]
    if not disk_files:
        return videos_dir, [], 0

    disk_map = {f.lower(): f for f in disk_files}
    card_ids = mw.col.find_cards(f'note:"{VIDEO_NOTE_TYPE}"')
    referenced: set[str] = set()
    for cid in card_ids:
        note = mw.col.get_card(cid).note()
        try:
            rel = (note[LOCAL_VIDEO_FIELD] or "").strip()
        except Exception:
            rel = ""
        if not rel:
            continue
        basename = os.path.basename(rel.replace("\\", "/")).strip()
        if basename:
            referenced.add(basename.lower())

    orphans = [disk_map[k] for k in sorted(set(disk_map.keys()) - referenced)]
    total_bytes = 0
    for fname in orphans:
        fpath = os.path.join(videos_dir, fname)
        try:
            total_bytes += os.path.getsize(fpath)
        except OSError:
            pass
    return videos_dir, orphans, total_bytes


def cleanupNonActiveProfileDataFunction() -> None:
    """
    Offer one-shot cleanup of artifacts not referenced by the active profile:
    orphan PDFs, orphan local videos, stale progress rows, stale search-index rows,
    and stale OCR cache rows.
    """
    try:
        pdf_dir, orphan_pdfs_all, _pdf_bytes_all = _scan_orphan_pdfs()
        videos_dir, orphan_videos_all, _video_bytes_all = _scan_orphan_videos()
        orphan_pdfs, protected_pdfs, pdf_refs_map = _partition_any_profile_ties(orphan_pdfs_all, "pdf")
        orphan_videos, protected_videos, video_refs_map = _partition_any_profile_ties(orphan_videos_all, "video")
        pdf_bytes = 0
        for fname in orphan_pdfs:
            try:
                pdf_bytes += os.path.getsize(os.path.join(pdf_dir, fname))
            except OSError:
                pass
        video_bytes = 0
        for fname in orphan_videos:
            try:
                video_bytes += os.path.getsize(os.path.join(videos_dir, fname))
            except OSError:
                pass
        stale_counts = _count_stale_progress_rows()
        stale_text_index_counts = _count_stale_document_text_index_rows()
        stale_ocr_counts = _count_stale_ocr_rows()
    except Exception as e:
        showInfo(_t("root_cleanup_profile_scan_failed", error=e))
        return

    stale_total = sum(int(stale_counts.get(k, 0) or 0) for k in ("pdf_progress", "video_progress", "web_progress"))
    stale_text_index_total = int(stale_text_index_counts.get("document_text_index_total", 0) or 0)
    stale_ocr_total = int(stale_ocr_counts.get("note_ocr_index_total", 0) or 0)
    if (
        not orphan_pdfs
        and not orphan_videos
        and stale_total <= 0
        and stale_text_index_total <= 0
        and stale_ocr_total <= 0
    ):
        showInfo(_t("root_cleanup_profile_none"))
        return

    profile_name = _current_profile_name()
    total_bytes = pdf_bytes + video_bytes
    total_str = (
        f"{total_bytes / 1_048_576:.1f} MB"
        if total_bytes >= 1_048_576
        else f"{total_bytes // 1024} KB"
    )

    lines = [
        _t("root_cleanup_active_profile", profile=profile_name),
        "",
        _t("root_cleanup_profile_explanation"),
        "",
        _t("root_cleanup_pdf_files", count=len(orphan_pdfs)),
        _t("root_cleanup_video_files", count=len(orphan_videos)),
        _t("root_cleanup_progress_rows", count=stale_total, pdf=stale_counts.get('pdf_progress', 0), video=stale_counts.get('video_progress', 0), web=stale_counts.get('web_progress', 0)),
        _t("root_cleanup_index_rows", count=stale_text_index_total, pdf=stale_text_index_counts.get('pdf_text_index', 0), epub=stale_text_index_counts.get('epub_text_index', 0)),
        _t("root_cleanup_cache_rows", count=stale_ocr_total, notes=stale_ocr_counts.get('note_ocr_index_missing_note', 0), cards=stale_ocr_counts.get('note_ocr_index_missing_card', 0)),
    ]
    if protected_pdfs:
        lines.append(_t("root_cleanup_protected_pdfs", count=len(protected_pdfs)))
    if protected_videos:
        lines.append(_t("root_cleanup_protected_videos", count=len(protected_videos)))
    if orphan_pdfs:
        lines.append(_t("root_cleanup_pdf_folder", path=pdf_dir))
    if orphan_videos:
        lines.append(_t("root_cleanup_video_folder", path=videos_dir))
    if total_bytes > 0:
        lines.append(_t("root_cleanup_recoverable_space", size=total_str))
    if protected_pdfs:
        lines.append("")
        lines.append(_t("root_cleanup_skipped_pdfs_heading"))
        preview = protected_pdfs[:6]
        for fname in preview:
            profs = ", ".join(pdf_refs_map.get(fname, []))
            lines.append(_t("root_cleanup_file_profiles", filename=fname, profiles=profs))
        if len(protected_pdfs) > len(preview):
            lines.append("  " + _t("root_more_failures", count=len(protected_pdfs) - len(preview)))
    if protected_videos:
        lines.append("")
        lines.append(_t("root_cleanup_skipped_videos_heading"))
        preview = protected_videos[:6]
        for fname in preview:
            profs = ", ".join(video_refs_map.get(fname, []))
            lines.append(_t("root_cleanup_file_profiles", filename=fname, profiles=profs))
        if len(protected_videos) > len(preview):
            lines.append("  " + _t("root_more_failures", count=len(protected_videos) - len(preview)))
    lines.append("")
    lines.append(_t("root_cleanup_delete_now"))

    from aqt.utils import askUser
    if not askUser("\n".join(lines), title=_t("root_menu_cleanup_profile_data")):
        return

    deleted_pdfs = 0
    deleted_videos = 0
    errors: list[str] = []

    for fname in orphan_pdfs:
        fpath = os.path.join(pdf_dir, fname)
        try:
            os.remove(fpath)
            deleted_pdfs += 1
        except OSError as e:
            errors.append(f"PDF {fname}: {e}")

    for fname in orphan_videos:
        fpath = os.path.join(videos_dir, fname)
        try:
            os.remove(fpath)
            deleted_videos += 1
        except OSError as e:
            errors.append(f"Video {fname}: {e}")

    try:
        pruned_counts = _prune_stale_progress_rows()
    except Exception as e:
        pruned_counts = {"pdf_progress": 0, "video_progress": 0, "web_progress": 0}
        errors.append(_t("root_cleanup_rows_error", error=e))
    try:
        pruned_text_index_counts = _prune_stale_document_text_index_rows()
    except Exception as e:
        pruned_text_index_counts = {
            "pdf_text_index": 0,
            "epub_text_index": 0,
            "document_text_index_total": 0,
        }
        errors.append(_t("root_cleanup_index_error", error=e))
    try:
        pruned_ocr_counts = _prune_stale_ocr_rows()
    except Exception as e:
        pruned_ocr_counts = {
            "note_ocr_index_missing_note": 0,
            "note_ocr_index_missing_card": 0,
            "note_ocr_index_total": 0,
        }
        errors.append(_t("root_cleanup_cache_error", error=e))

    summary = [
        _t("root_cleanup_deleted_pdfs", deleted=deleted_pdfs, total=len(orphan_pdfs)),
        _t("root_cleanup_deleted_videos", deleted=deleted_videos, total=len(orphan_videos)),
    ]
    pruned_summary = _format_pruned_progress_summary(pruned_counts)
    if pruned_summary:
        summary.append("")
        summary.append(pruned_summary)
    pruned_text_index_summary = _format_pruned_document_text_index_summary(pruned_text_index_counts)
    if pruned_text_index_summary:
        summary.append("")
        summary.append(pruned_text_index_summary)
    pruned_ocr_summary = _format_pruned_ocr_summary(pruned_ocr_counts)
    if pruned_ocr_summary:
        summary.append("")
        summary.append(pruned_ocr_summary)
    if total_bytes > 0:
        summary.append("")
        summary.append(_t("root_cleanup_recovered_space", size=total_str))
    if errors:
        summary.append("")
        summary.append(_t("root_pdf_reindex_errors", count=len(errors)))
        summary.extend([f"• {e}" for e in errors[:20]])
        if len(errors) > 20:
            summary.append("• " + _t("root_more_failures", count=len(errors) - 20))

    showInfo("\n".join(summary))


def cleanupStaleProgressFunction() -> None:
    """Delete stale progress, search-index, and OCR rows for removed cards/notes."""
    try:
        counts = _prune_stale_progress_rows()
        text_index_counts = _prune_stale_document_text_index_rows()
        ocr_counts = _prune_stale_ocr_rows()
    except Exception as e:
        showInfo(_t("root_cleanup_stale_failed", error=e))
        return

    summary = _format_pruned_progress_summary(counts)
    text_index_summary = _format_pruned_document_text_index_summary(text_index_counts)
    ocr_summary = _format_pruned_ocr_summary(ocr_counts)
    chunks = [chunk for chunk in (summary, text_index_summary, ocr_summary) if chunk]
    if chunks:
        showInfo("\n\n".join(chunks))
        return
    showInfo(_t("root_cleanup_stale_none"))


def cleanupOrphanPdfsFunction() -> None:
    """Delete PDF files in user_files/<profile>/pdfs/ that no card references."""
    from .backend.pdf_manager import get_pdf_dir

    _backfill_pdf_source_filenames()
    pdf_dir = get_pdf_dir()

    # All files currently on disk
    try:
        disk_files = {
            f for f in os.listdir(pdf_dir)
            if f.lower().endswith(".pdf")
        }
    except OSError as e:
        showInfo(_t("root_cleanup_pdf_read_failed", error=e))
        return

    if not disk_files:
        showInfo(_t("root_cleanup_pdf_none", path=pdf_dir))
        return

    # All filenames referenced by an Incremento PDF note
    try:
        note_ids = mw.col.find_notes(f'note:"{PDF_NOTE_TYPE}"')
        referenced = set()
        for nid in note_ids:
            note = mw.col.get_note(nid)
            fname = note["PDF_Filename"].strip()
            if fname:
                referenced.add(fname)
        referenced.update(get_pdf_referenced_filenames(_ADDON_DIR, _active_profile()))
    except Exception as e:
        showInfo(_t("root_cleanup_pdf_query_failed", error=e))
        return

    orphans = sorted(disk_files - referenced)
    deletable, protected, refs_map = _partition_any_profile_ties(orphans, "pdf")

    try:
        pruned_counts = _prune_stale_progress_rows()
    except Exception:
        pruned_counts = {"pdf_progress": 0, "video_progress": 0, "web_progress": 0}
    pruned_summary = _format_pruned_progress_summary(pruned_counts)
    try:
        pruned_text_index_counts = _prune_stale_document_text_index_rows()
    except Exception:
        pruned_text_index_counts = {
            "pdf_text_index": 0,
            "epub_text_index": 0,
            "document_text_index_total": 0,
        }
    pruned_text_index_summary = _format_pruned_document_text_index_summary(pruned_text_index_counts)
    cleanup_summaries = [chunk for chunk in (pruned_summary, pruned_text_index_summary) if chunk]

    if not deletable:
        msg = _t("root_cleanup_pdf_no_deletable", count=len(disk_files))
        if protected:
            msg += "\n\n" + _t("root_cleanup_other_profile_skip", count=len(protected))
        if cleanup_summaries:
            msg += f"\n\n{'\n\n'.join(cleanup_summaries)}"
        showInfo(msg)
        return

    def _fmt_size(path: str) -> str:
        try:
            b = os.path.getsize(path)
            return f"{b / 1_048_576:.1f} MB" if b >= 1_048_576 else f"{b // 1024} KB"
        except OSError:
            return "?"

    lines = [_t("root_cleanup_pdf_found", count=len(deletable)) + "\n"]
    total_bytes = 0
    for fname in deletable:
        fpath = os.path.join(pdf_dir, fname)
        try:
            total_bytes += os.path.getsize(fpath)
        except OSError:
            pass
        lines.append(f"• {fname}  ({_fmt_size(fpath)})")
    if protected:
        lines.append("\n" + _t("root_cleanup_other_profile_tied", count=len(protected)))
        preview = protected[:8]
        for fname in preview:
            profs = ", ".join(refs_map.get(fname, []))
            lines.append(_t("root_cleanup_file_profiles", filename=fname, profiles=profs))
        if len(protected) > len(preview):
            lines.append("  " + _t("root_more_failures", count=len(protected) - len(preview)))
    total_str = f"{total_bytes / 1_048_576:.1f} MB" if total_bytes >= 1_048_576 else f"{total_bytes // 1024} KB"
    lines.append("\n" + _t("root_cleanup_total", size=total_str))
    lines.append("\n" + _t("root_cleanup_delete_files"))

    from aqt.utils import askUser
    if not askUser("\n".join(lines), title=_t("root_menu_cleanup_orphan_pdfs")):
        return

    deleted = 0
    errors: list[str] = []
    for fname in deletable:
        fpath = os.path.join(pdf_dir, fname)
        try:
            os.remove(fpath)
            deleted += 1
        except OSError as e:
            errors.append(f"• {fname}: {e}")

    if not errors:
        msg = _t("root_cleanup_pdf_deleted", count=deleted, size=total_str)
        if protected:
            msg += "\n" + _t("root_cleanup_other_profile_tied", count=len(protected))
        if cleanup_summaries:
            msg += f"\n\n{'\n\n'.join(cleanup_summaries)}"
        showInfo(msg)
    else:
        showInfo(_t("root_cleanup_partial_deleted", deleted=deleted, total=len(deletable), errors="\n".join(errors)))


def cleanupOrphanVideosFunction() -> None:
    """Delete local videos in user_files/<profile>/videos/ that no video card references."""
    videos_dir = str(_paths.get_videos_dir(_ADDON_DIR, _active_profile()))
    if not os.path.isdir(videos_dir):
        showInfo(_t("root_cleanup_videos_none", path=videos_dir))
        return

    try:
        disk_files = [
            f
            for f in os.listdir(videos_dir)
            if f.lower().endswith((".mp4", ".mkv", ".webm", ".mov", ".m4v"))
            and os.path.isfile(os.path.join(videos_dir, f))
        ]
    except OSError as e:
        showInfo(_t("root_cleanup_videos_read_failed", error=e))
        return

    if not disk_files:
        showInfo(_t("root_cleanup_videos_none", path=videos_dir))
        return
    disk_map = {f.lower(): f for f in disk_files}

    try:
        card_ids = mw.col.find_cards(f'note:"{VIDEO_NOTE_TYPE}"')
        referenced: set[str] = set()
        for cid in card_ids:
            note = mw.col.get_card(cid).note()
            try:
                rel = (note[LOCAL_VIDEO_FIELD] or "").strip()
            except Exception:
                rel = ""
            if not rel:
                continue
            basename = os.path.basename(rel.replace("\\", "/")).strip()
            if basename:
                referenced.add(basename.lower())
    except Exception as e:
        showInfo(_t("root_cleanup_videos_query_failed", error=e))
        return

    try:
        pruned_counts = _prune_stale_progress_rows()
    except Exception:
        pruned_counts = {"pdf_progress": 0, "video_progress": 0, "web_progress": 0}
    pruned_summary = _format_pruned_progress_summary(pruned_counts)
    try:
        pruned_text_index_counts = _prune_stale_document_text_index_rows()
    except Exception:
        pruned_text_index_counts = {
            "pdf_text_index": 0,
            "epub_text_index": 0,
            "document_text_index_total": 0,
        }
    pruned_text_index_summary = _format_pruned_document_text_index_summary(pruned_text_index_counts)
    cleanup_summaries = [chunk for chunk in (pruned_summary, pruned_text_index_summary) if chunk]

    orphans = [disk_map[k] for k in sorted(set(disk_map.keys()) - referenced)]
    deletable, protected, refs_map = _partition_any_profile_ties(orphans, "video")
    if not deletable:
        msg = _t("root_cleanup_videos_no_deletable", count=len(disk_files))
        if protected:
            msg += "\n\n" + _t("root_cleanup_other_profile_skip", count=len(protected))
        if cleanup_summaries:
            msg += f"\n\n{'\n\n'.join(cleanup_summaries)}"
        showInfo(msg)
        return

    def _fmt_size(path: str) -> str:
        try:
            b = os.path.getsize(path)
            return f"{b / 1_048_576:.1f} MB" if b >= 1_048_576 else f"{b // 1024} KB"
        except OSError:
            return "?"

    total_bytes = 0
    lines = [_t("root_cleanup_videos_found", count=len(deletable)) + "\n"]
    for fname in deletable:
        fpath = os.path.join(videos_dir, fname)
        try:
            total_bytes += os.path.getsize(fpath)
        except OSError:
            pass
        lines.append(f"• {fname}  ({_fmt_size(fpath)})")
    if protected:
        lines.append("\n" + _t("root_cleanup_other_profile_tied", count=len(protected)))
        preview = protected[:8]
        for fname in preview:
            profs = ", ".join(refs_map.get(fname, []))
            lines.append(_t("root_cleanup_file_profiles", filename=fname, profiles=profs))
        if len(protected) > len(preview):
            lines.append("  " + _t("root_more_failures", count=len(protected) - len(preview)))
    total_str = (
        f"{total_bytes / 1_048_576:.1f} MB"
        if total_bytes >= 1_048_576
        else f"{total_bytes // 1024} KB"
    )
    lines.append("\n" + _t("root_cleanup_total", size=total_str))
    lines.append("\n" + _t("root_cleanup_delete_files"))

    from aqt.utils import askUser
    if not askUser("\n".join(lines), title=_t("root_menu_cleanup_orphan_videos")):
        return

    deleted = 0
    errors: list[str] = []
    for fname in deletable:
        fpath = os.path.join(videos_dir, fname)
        try:
            os.remove(fpath)
            deleted += 1
        except OSError as e:
            errors.append(f"• {fname}: {e}")

    if not errors:
        msg = _t("root_cleanup_videos_deleted", count=deleted, size=total_str)
        if protected:
            msg += "\n" + _t("root_cleanup_other_profile_tied", count=len(protected))
        if cleanup_summaries:
            msg += f"\n\n{'\n\n'.join(cleanup_summaries)}"
        showInfo(msg)
    else:
        showInfo(_t("root_cleanup_partial_deleted", deleted=deleted, total=len(deletable), errors="\n".join(errors)))


def _save_settings_with_language_pack(cfg: dict, pending_pack: dict | None, profile: str) -> None:
    """Restore the prior pack if Anki rejects the accompanying settings write."""
    previous = None
    if pending_pack is not None:
        previous = _language_packs.load_pack(_ADDON_DIR, profile, pending_pack["locale"])
    try:
        if pending_pack is not None:
            _language_packs.save_pack(_ADDON_DIR, profile, pending_pack)
        _save_addon_config(mw.addonManager, __name__, cfg)
    except Exception:
        if pending_pack is not None:
            if previous is None:
                _language_packs.delete_pack(_ADDON_DIR, profile, pending_pack["locale"])
            else:
                _language_packs.save_pack(_ADDON_DIR, profile, previous)
        raise


def openSettingsFunction() -> None:
    settings_profile = _current_profile_name()
    cfg = copy.deepcopy(_load_addon_config(mw.addonManager, __name__))
    previous_priority_direction = configured_priority_lower_is_more_important(cfg)
    note_type_names = sorted(m.name for m in mw.col.models.all_names_and_ids())
    dlg = IncrementoSettingsDialog(
        cfg.get("shortcuts") or {},
        current_ui_language=cfg.get("ui_language", "auto"),
        language_pack_context=(_ADDON_DIR, settings_profile),
        note_type_names=note_type_names,
        current_extract_notetype=_add_card_dock_mod.configured_extract_notetype_name(cfg),
        current_extract_priority=_add_card_dock_mod.configured_extract_priority(cfg),
        current_extract_priority_multiplier=_add_card_dock_mod.configured_extract_priority_multiplier(cfg),
        current_extract_mark_topic=_add_card_dock_mod.configured_extract_mark_topic(cfg),
        current_extract_copy_source_tags=_add_card_dock_mod.configured_extract_copy_source_tags(cfg),
        current_extract_highlight_when_extracting=_pdf_dock_mod.configured_highlight_when_extracting(cfg),
        current_pdf_highlight_extract_field=_pdf_dock_mod.configured_pdf_highlight_extract_field(cfg),
        extract_source_links=_add_card_dock_mod.configured_extract_source_links(cfg),
        current_priority_lower_is_more_important=configured_priority_lower_is_more_important(cfg),
        current_show_priority_dialog_after_answer=configured_show_priority_dialog_after_answer(cfg),
        current_reviewer_priority_badge_card_types=configured_reviewer_priority_badge_card_types(cfg),
        current_reviewer_button_visibility=configured_reviewer_button_visibility(cfg),
        current_reviewer_button_group_visible=configured_reviewer_button_group_visible(cfg),
        current_show_incremento_fields=configured_show_incremento_fields(cfg),
        current_remember_browser_card_scroll=configured_remember_browser_card_scroll(cfg),
        current_pdf_scroll_to_top_on_page_change=_pdf_dock_mod.configured_scroll_to_top_on_page_change(cfg),
        current_pdf_default_appearance=_pdf_dock_mod.configured_pdf_default_appearance(cfg),
        current_pdf_force_default_appearance=_pdf_dock_mod.configured_pdf_force_default_appearance(cfg),
        current_prefer_web_card_resume_in_original_page=configured_prefer_web_card_resume_in_original_page(cfg),
        current_track_web_window_with_extension=configured_track_web_window_with_extension(cfg),
        current_use_fail_pass_on_items=_configured_use_fail_pass_on_items(cfg),
        current_item_skip_enabled=_configured_item_skip_enabled(cfg),
        current_item_skip_minutes=_configured_item_skip_minutes(cfg),
        current_auto_timer_enabled=_timer_mod.configured_auto_timer_enabled(cfg),
        current_auto_timer_card_types=_timer_mod.configured_auto_timer_card_types(cfg),
        current_auto_timer_tags=_timer_mod.configured_auto_timer_tags(cfg),
        current_auto_timer_minutes=_timer_mod.configured_auto_timer_minutes(cfg),
        current_timer_completion_beep=_timer_mod.configured_timer_completion_beep_enabled(cfg),
        current_topic_card_types=_configured_topic_card_types(cfg),
        current_topic_card_tags=_configured_topic_card_tags(cfg),
        current_default_topic_a_factor=_configured_default_topic_a_factor(cfg),
        current_topic_more_adjustment_percent=_configured_topic_more_adjustment_percent(cfg),
        current_topic_less_adjustment_percent=_configured_topic_less_adjustment_percent(cfg),
        current_topic_maximum_interval_days=_configured_topic_maximum_interval_days(cfg),
        current_topic_done_tag=_configured_topic_done_tag(cfg),
        current_add_card_topic_tags=_add_card_dock_mod.configured_add_card_topic_tags(cfg),
        current_add_card_item_tags=_add_card_dock_mod.configured_add_card_item_tags(cfg),
        current_auto_create_topics_deck=configured_auto_create_topics_deck(cfg),
        current_auto_create_topics_deck_profiles=configured_auto_create_topics_deck_profiles(cfg),
        available_profile_names=_available_profile_names(),
        current_topic_postpone_enabled=_configured_topic_postpone_enabled(cfg),
        current_topic_postpone_mode=cfg.get("topic_postpone_mode", "timed"),
        current_topic_postpone_minutes=cfg.get("topic_postpone_minutes", 30),
        current_writing_wrap_enabled=_writing_dock_mod.configured_writing_wrap_enabled(cfg),
        current_writing_focus_mode=_writing_dock_mod.configured_writing_focus_mode(cfg),
        current_writing_preview_visible=_writing_dock_mod.configured_writing_preview_visible(cfg),
        current_writing_highlight_current_line=_writing_dock_mod.configured_writing_highlight_current_line(cfg),
        current_writing_restore_bookmark=_writing_dock_mod.configured_writing_restore_bookmark(cfg),
        current_writing_backups_enabled=_writing_dock_mod.configured_writing_backups_enabled(cfg),
        current_writing_backup_tiers=_writing_dock_mod.configured_writing_backup_tiers(cfg),
        current_writing_progress_visible=_writing_dock_mod.configured_writing_progress_visible(cfg),
        current_writing_progress_default_scope=_writing_dock_mod.configured_writing_progress_default_scope(cfg),
        current_writing_word_count_mode=_writing_dock_mod.configured_writing_word_count_mode(cfg),
        current_custom_schedule_default_mode=_configured_custom_schedule_default_mode(cfg),
        current_custom_schedule_presets=_configured_custom_schedule_presets(cfg),
        open_database_editor_callback=_open_database_editor,
        parent=mw,
    )
    if not dlg.exec():
        return

    if settings_profile != _current_profile_name():
        showInfo(_t("settings_language_profile_changed"))
        return

    cfg["ui_language"] = dlg.ui_language
    cfg["shortcuts"] = dlg.shortcuts_map
    cfg["extract_notetype"] = dlg.extract_notetype_name
    cfg["extract_priority"] = dlg.extract_priority
    cfg["extract_priority_multiplier"] = dlg.extract_priority_multiplier
    cfg["extract_mark_topic"] = dlg.extract_mark_topic
    cfg["extract_copy_source_tags"] = dlg.extract_copy_source_tags
    cfg["highlight_when_extracting"] = dlg.extract_highlight_when_extracting
    cfg["pdf_highlight_extract_field"] = dlg.pdf_highlight_extract_field
    cfg["extract_source_links"] = dlg.extract_source_links
    cfg["priority_lower_is_more_important"] = dlg.priority_lower_is_more_important
    cfg["show_priority_dialog_after_answer"] = dlg.show_priority_dialog_after_answer
    cfg["reviewer_priority_badge_card_types"] = dlg.reviewer_priority_badge_card_types
    visibility = dict(cfg.get("reviewer_button_visibility") or {})
    visibility.update(dlg.reviewer_button_visibility)
    cfg["reviewer_button_visibility"] = visibility
    cfg["reviewer_button_group_visible"] = dlg.reviewer_button_group_visible
    cfg["show_incremento_fields"] = dlg.show_incremento_fields
    cfg["remember_browser_card_scroll"] = dlg.remember_browser_card_scroll
    cfg["pdf_scroll_to_top_on_page_change"] = dlg.pdf_scroll_to_top_on_page_change
    cfg["pdf_default_appearance"] = dlg.pdf_default_appearance
    cfg["pdf_force_default_appearance"] = dlg.pdf_force_default_appearance
    cfg["prefer_web_card_resume_in_original_page"] = dlg.prefer_web_card_resume_in_original_page
    cfg["track_web_window_with_extension"] = dlg.track_web_window_with_extension
    cfg["use_fail_pass_on_items"] = dlg.use_fail_pass_on_items
    cfg["item_skip_enabled"] = dlg.item_skip_enabled
    cfg["item_skip_minutes"] = dlg.item_skip_minutes
    cfg["auto_timer_enabled"] = dlg.auto_timer_enabled
    cfg["auto_timer_card_types"] = dlg.auto_timer_card_types
    cfg["auto_timer_tags"] = dlg.auto_timer_tags
    cfg["auto_timer_minutes"] = dlg.auto_timer_minutes
    cfg["timer_completion_beep"] = dlg.timer_completion_beep
    cfg["topic_card_types"] = dlg.topic_card_types
    cfg["topic_card_tags"] = dlg.topic_card_tags
    cfg["default_topic_a_factor"] = dlg.default_topic_a_factor
    cfg["topic_more_adjustment_percent"] = dlg.topic_more_adjustment_percent
    cfg["topic_less_adjustment_percent"] = dlg.topic_less_adjustment_percent
    cfg["topic_maximum_interval_days"] = dlg.topic_maximum_interval_days
    cfg["topic_done_tag"] = dlg.topic_done_tag
    cfg["add_card_topic_tags"] = dlg.add_card_topic_tags
    cfg["add_card_item_tags"] = dlg.add_card_item_tags
    cfg["auto_create_topics_deck"] = dlg.auto_create_topics_deck
    cfg["auto_create_topics_deck_profiles"] = dlg.auto_create_topics_deck_profiles
    cfg["topic_postpone_enabled"] = dlg.topic_postpone_enabled
    cfg["topic_postpone_mode"] = dlg.topic_postpone_mode
    cfg["topic_postpone_minutes"] = dlg.topic_postpone_minutes
    cfg["writing_wrap_enabled"] = dlg.writing_wrap_enabled
    cfg["writing_focus_mode"] = dlg.writing_focus_mode
    cfg["writing_preview_visible"] = dlg.writing_preview_visible
    cfg["writing_highlight_current_line"] = dlg.writing_highlight_current_line
    cfg["writing_restore_bookmark"] = dlg.writing_restore_bookmark
    cfg["writing_backups_enabled"] = dlg.writing_backups_enabled
    cfg["writing_backup_tiers"] = dlg.writing_backup_tiers
    cfg["writing_progress_visible"] = dlg.writing_progress_visible
    cfg["writing_progress_default_scope"] = dlg.writing_progress_default_scope
    cfg["writing_word_count_mode"] = dlg.writing_word_count_mode
    cfg["custom_schedule_default_mode"] = dlg.custom_schedule_default_mode
    cfg["custom_schedule_presets"] = dlg.custom_schedule_presets
    try:
        _save_settings_with_language_pack(cfg, dlg.pending_language_pack, settings_profile)
    except Exception:
        showInfo(_t("settings_save_failed"))
        return
    _sync_reviewer_priority_badge()
    if mw.state == "review" and getattr(mw, "reviewer", None) is not None:
        _sync_reviewer_button_visibility(mw.reviewer)
    try:
        if _web_dock_mod._runtime.dock is not None:
            checked = bool(dlg.track_web_window_with_extension)
            _web_dock_mod._runtime.track_window_with_extension = checked
            _web_dock_mod._runtime.dock._track_cb.setChecked(checked)
    except Exception:
        pass
    try:
        _pdf_dock_mod._pdf_dock._view.page().runJavaScript(
            f"window.incrementoSetAutoHighlightOnExtract && window.incrementoSetAutoHighlightOnExtract({json.dumps(dlg.extract_highlight_when_extracting)});"
        )
    except Exception:
        pass
    try:
        _pdf_dock_mod._pdf_dock._view.page().runJavaScript(
            f"window.incrementoSetScrollToTopOnPageChange && window.incrementoSetScrollToTopOnPageChange({json.dumps(dlg.pdf_scroll_to_top_on_page_change)});"
        )
    except Exception:
        pass
    try:
        resolved_pdf_appearance = _pdf_dock_mod.resolved_current_pdf_appearance(cfg)
        _pdf_dock_mod._pdf_dock._view.page().runJavaScript(
            "window.incrementoSetPdfAppearanceMode && "
            f"window.incrementoSetPdfAppearanceMode({json.dumps(resolved_pdf_appearance)});"
        )
    except Exception:
        pass
    try:
        if getattr(_epub_dock_mod, "_epub_dock", None) is not None:
            _epub_dock_mod._epub_dock._highlight_extract_cb.blockSignals(True)
            _epub_dock_mod._epub_dock._highlight_extract_cb.setChecked(
                bool(dlg.extract_highlight_when_extracting)
            )
            _epub_dock_mod._epub_dock._highlight_extract_cb.blockSignals(False)
            _epub_dock_mod._epub_dock._view.page().runJavaScript(
                f"window.incrementoSetAutoHighlightOnExtract && window.incrementoSetAutoHighlightOnExtract({json.dumps(dlg.extract_highlight_when_extracting)});"
            )
    except Exception:
        pass
    _apply_shortcuts_from_config()
    _add_card_dock_mod.refresh_add_card_dock_controls()
    if dlg.priority_lower_is_more_important != previous_priority_direction:
        from aqt.utils import askUser

        direction_label = (
            _t("root_settings_priority_lower")
            if dlg.priority_lower_is_more_important
            else _t("root_settings_priority_higher")
        )
        if askUser(
            "\n".join(
                [
                    _t("root_settings_priority_changed"),
                    _t("root_settings_priority_direction", direction=direction_label),
                    "",
                    _t("root_settings_priority_invert_question"),
                    _t("root_settings_priority_invert_detail"),
                    _t("root_settings_priority_invert_example"),
                ]
            ),
            title=_t("root_settings_priority_invert_title"),
        ):
            try:
                updated = invert_all_priorities(_ADDON_DIR, _active_profile())
            except Exception as exc:
                showInfo(_t("root_settings_priority_invert_failed", error=exc))
            else:
                tooltip(_tn("root_settings_priority_inverted", updated))
                return
    tooltip(_t("root_settings_updated"))


def _open_database_editor() -> None:
    from .frontend.sqlite_editor_dialog import SQLiteEditorDialog

    profile = _active_profile()
    mw.progress.start(label=_t("root_database_checkpoint_progress"), immediate=True)
    try:
        checkpoint_info = create_database_checkpoint(
            _ADDON_DIR,
            profile,
            label="sqlite_editor",
        )
    except Exception as exc:
        showInfo(_t("root_database_editor_failed", error=exc))
        return
    finally:
        mw.progress.finish()

    dialog = SQLiteEditorDialog(
        _ADDON_DIR,
        profile,
        checkpoint_info=checkpoint_info,
        parent=mw,
    )
    dialog.exec()


def openAboutFunction() -> None:
    points = "".join(f"<li>{_html_escape(_t(key))}</li>" for key in (
        "root_about_add_review",
        "root_about_open_docks",
        "root_about_extract",
        "root_about_track",
        "root_about_chrome_extension",
    ))
    showInfo(
        f"<h2>Incremento</h2>"
        f"<p><b>{_html_escape(_t('root_about_author'))}</b> Paulo Baskovic</p>"
        f"<p>{_html_escape(_t('root_about_intro'))}</p>"
        f"<p><b>{_html_escape(_t('root_about_general_info'))}</b></p>"
        f"<ul>{points}</ul>"
        f"<p><b>{_html_escape(_t('root_about_disclaimer_label'))}</b> {_html_escape(_t('root_about_disclaimer'))}</p>"
        f"<p><b>{_html_escape(_t('root_about_license_label'))}</b> {_html_escape(_t('root_about_license'))}</p>"
    )


def _retranslate_incremento_menu() -> None:
    """Refresh existing actions on profile changes without duplicating shortcuts."""
    if _menu is None:
        return

    def visit(menu):
        for action in [menu.menuAction(), *menu.actions()]:
            key = action.property("incremento_translation_key")
            if key:
                action.setText(_t(key))
        for action in menu.actions():
            if action.menu() is not None:
                visit(action.menu())

    visit(_menu)


def _ensure_settings_menu_action() -> None:
    if _menu is None:
        return
    for act in _menu.actions():
        if act.objectName() == "incremento_open_settings":
            return

    action = QAction(_t("root_menu_settings"), mw)
    action.setProperty("incremento_translation_key", "root_menu_settings")
    action.setObjectName("incremento_open_settings")
    action.setMenuRole(QAction.MenuRole.NoRole)
    qconnect(action.triggered, openSettingsFunction)

    inserted = False
    for act in _menu.actions():
        if act.isSeparator():
            _menu.insertAction(act, action)
            inserted = True
            break
    if not inserted:
        _menu.addAction(action)

    _register_shortcut_action("open_settings", action)
    _apply_shortcuts_from_config()


# ── Incremento top-level menu ─────────────────────────────────────────────────

def _build_incremento_menu() -> None:
    """Build and attach the Incremento menu, or re-attach it if Anki removed it."""
    global _menu, _timerToggleAction

    menubar = mw.menuBar()
    if menubar is None:
        return

    # Already attached — nothing to do.
    for act in menubar.actions():
        if act.objectName() == "incremento_menu":
            _menu = act.menu()
            menubar.update()
            return

    _menu = QMenu(_t("root_menu_incremento"), menubar)
    _menu.menuAction().setProperty("incremento_translation_key", "root_menu_incremento")
    _menu.menuAction().setObjectName("incremento_menu")
    menubar.addMenu(_menu)

    _startAction = QAction(_t("root_menu_start_learning"), mw)
    _startAction.setProperty("incremento_translation_key", "root_menu_start_learning")
    qconnect(_startAction.triggered, learnFunction)
    _menu.addAction(_startAction)
    _register_shortcut_action("start_learning", _startAction)

    _commandPaletteAction = QAction(_t("root_menu_command_palette"), mw)
    _commandPaletteAction.setProperty("incremento_translation_key", "root_menu_command_palette")
    qconnect(_commandPaletteAction.triggered, _open_command_palette)
    _menu.addAction(_commandPaletteAction)
    _register_shortcut_action("command_palette", _commandPaletteAction)

    _activityCenterAction = QAction(_t("root_menu_activity_center"), mw)
    _activityCenterAction.setProperty("incremento_translation_key", "root_menu_activity_center")
    qconnect(_activityCenterAction.triggered, _open_activity_center)
    _menu.addAction(_activityCenterAction)
    _register_shortcut_action("activity_center", _activityCenterAction)

    _settingsAction = QAction(_t("root_menu_settings"), mw)
    _settingsAction.setProperty("incremento_translation_key", "root_menu_settings")
    _settingsAction.setObjectName("incremento_open_settings")
    _settingsAction.setMenuRole(QAction.MenuRole.NoRole)
    qconnect(_settingsAction.triggered, openSettingsFunction)
    _menu.addAction(_settingsAction)
    _register_shortcut_action("open_settings", _settingsAction)

    _aboutAction = QAction(_t("root_menu_about"), mw)
    _aboutAction.setProperty("incremento_translation_key", "root_menu_about")
    _aboutAction.setMenuRole(QAction.MenuRole.NoRole)
    qconnect(_aboutAction.triggered, openAboutFunction)
    _menu.addAction(_aboutAction)

    _gettingStartedAction = QAction(_t("root_menu_getting_started"), mw)
    _gettingStartedAction.setProperty("incremento_translation_key", "root_menu_getting_started")
    _gettingStartedAction.setMenuRole(QAction.MenuRole.NoRole)
    qconnect(
        _gettingStartedAction.triggered,
        lambda _checked=False: _show_incremento_onboarding(force=True),
    )
    _menu.addAction(_gettingStartedAction)

    _menu.addSeparator()

    _addContentMenu = QMenu(_t("root_menu_add_content"), _menu)
    _addContentMenu.menuAction().setProperty("incremento_translation_key", "root_menu_add_content")
    _menu.addMenu(_addContentMenu)

    _addPdfAction = QAction(_t("root_menu_add_pdf"), mw)
    _addPdfAction.setProperty("incremento_translation_key", "root_menu_add_pdf")
    qconnect(_addPdfAction.triggered, addPdfFunction)
    _addContentMenu.addAction(_addPdfAction)
    _register_shortcut_action("add_pdf", _addPdfAction)

    _addEpubAction = QAction(_t("root_menu_add_epub"), mw)
    _addEpubAction.setProperty("incremento_translation_key", "root_menu_add_epub")
    qconnect(_addEpubAction.triggered, addEpubFunction)
    _addContentMenu.addAction(_addEpubAction)
    _register_shortcut_action("add_epub", _addEpubAction)

    _addMarkdownDocumentAction = QAction(_t("root_menu_add_markdown_document"), mw)
    _addMarkdownDocumentAction.setProperty("incremento_translation_key", "root_menu_add_markdown_document")
    qconnect(_addMarkdownDocumentAction.triggered, addMarkdownDocumentFunction)
    _addContentMenu.addAction(_addMarkdownDocumentAction)
    _register_shortcut_action("add_markdown_document", _addMarkdownDocumentAction)

    _editMarkdownDocumentAction = QAction(_t("root_menu_edit_markdown_document"), mw)
    _editMarkdownDocumentAction.setProperty("incremento_translation_key", "root_menu_edit_markdown_document")
    qconnect(_editMarkdownDocumentAction.triggered, _epub_dock_mod.edit_current_markdown_document)
    _menu.addAction(_editMarkdownDocumentAction)
    _register_shortcut_action("edit_markdown_document", _editMarkdownDocumentAction)

    _addWebpageAction = QAction(_t("root_menu_webpage_to_pdf"), mw)
    _addWebpageAction.setProperty("incremento_translation_key", "root_menu_webpage_to_pdf")
    qconnect(_addWebpageAction.triggered, addWebpageFunction)
    _addContentMenu.addAction(_addWebpageAction)
    _register_shortcut_action("webpage_to_pdf", _addWebpageAction)

    _addVideoAction = QAction(_t("root_menu_add_video"), mw)
    _addVideoAction.setProperty("incremento_translation_key", "root_menu_add_video")
    qconnect(_addVideoAction.triggered, addVideoFunction)
    _addContentMenu.addAction(_addVideoAction)
    _register_shortcut_action("youtube_video", _addVideoAction)

    _addWritingAction = QAction(_t("root_menu_add_markdown"), mw)
    _addWritingAction.setProperty("incremento_translation_key", "root_menu_add_markdown")
    qconnect(_addWritingAction.triggered, addWritingFunction)
    _addContentMenu.addAction(_addWritingAction)
    _register_shortcut_action("add_writing", _addWritingAction)

    _addWebAction = QAction(_t("root_menu_web_page"), mw)
    _addWebAction.setProperty("incremento_translation_key", "root_menu_web_page")
    qconnect(_addWebAction.triggered, _web_dock_mod.add_web_function)
    _addContentMenu.addAction(_addWebAction)
    _register_shortcut_action("add_web_page", _addWebAction)

    _addLocalFileAction = QAction(_t("root_menu_add_local_file"), mw)
    _addLocalFileAction.setProperty("incremento_translation_key", "root_menu_add_local_file")
    qconnect(_addLocalFileAction.triggered, addLocalFileFunction)
    _addContentMenu.addAction(_addLocalFileAction)
    _register_shortcut_action("add_local_file", _addLocalFileAction)

    _downloadCurrentVideoAction = QAction(_t("root_menu_download_video"), mw)
    _downloadCurrentVideoAction.setProperty("incremento_translation_key", "root_menu_download_video")
    qconnect(
        _downloadCurrentVideoAction.triggered,
        lambda _checked=False: _download_current_reviewer_video_locally(),
    )
    _menu.addAction(_downloadCurrentVideoAction)

    _configureCurrentVideoCaptionsAction = QAction(_t("root_menu_configure_captions"), mw)
    _configureCurrentVideoCaptionsAction.setProperty("incremento_translation_key", "root_menu_configure_captions")
    qconnect(
        _configureCurrentVideoCaptionsAction.triggered,
        lambda _checked=False: _configure_current_reviewer_video_captions(),
    )
    _menu.addAction(_configureCurrentVideoCaptionsAction)

    _knowledgeTreeAction = QAction(_t("root_menu_open_knowledge_tree"), mw)
    _knowledgeTreeAction.setProperty("incremento_translation_key", "root_menu_open_knowledge_tree")
    qconnect(_knowledgeTreeAction.triggered, lambda _checked=False: _open_knowledge_tree())
    _menu.addAction(_knowledgeTreeAction)
    _register_shortcut_action("open_knowledge_tree", _knowledgeTreeAction)

    _revealCurrentTreeAction = QAction(_t("root_menu_reveal_current_tree"), mw)
    _revealCurrentTreeAction.setProperty("incremento_translation_key", "root_menu_reveal_current_tree")
    qconnect(
        _revealCurrentTreeAction.triggered,
        lambda _checked=False: _reveal_current_card_in_knowledge_tree(),
    )
    _menu.addAction(_revealCurrentTreeAction)
    _register_shortcut_action("reveal_current_knowledge_tree", _revealCurrentTreeAction)

    _goToParentTreeAction = QAction(_t("root_menu_go_parent_tree"), mw)
    _goToParentTreeAction.setProperty("incremento_translation_key", "root_menu_go_parent_tree")
    qconnect(
        _goToParentTreeAction.triggered,
        lambda _checked=False: _go_to_parent_in_knowledge_tree(),
    )
    _menu.addAction(_goToParentTreeAction)
    _register_shortcut_action("go_to_parent_knowledge_tree", _goToParentTreeAction)

    _menu.addSeparator()

    _timerToggleAction = QAction(_t("root_menu_focus_timer"), mw)
    _timerToggleAction.setProperty("incremento_translation_key", "root_menu_focus_timer")
    _timerToggleAction.setCheckable(True)
    _timerToggleAction.setChecked(True)  # default; corrected by _build_timer_toolbar

    def _on_timer_toggle(checked: bool) -> None:
        if _timer_mod._timer_toolbar is not None:
            _timer_mod._timer_toolbar.setVisible(checked)
        cfg = _load_addon_config(mw.addonManager, __name__)
        cfg["show_timer"] = checked
        _save_addon_config(mw.addonManager, __name__, cfg)

    qconnect(_timerToggleAction.triggered, _on_timer_toggle)
    _menu.addAction(_timerToggleAction)
    _register_shortcut_action("toggle_focus_timer", _timerToggleAction)

    _menu.addSeparator()

    _utilsMenu = QMenu(_t("root_menu_utils"), _menu)
    _utilsMenu.menuAction().setProperty("incremento_translation_key", "root_menu_utils")
    _menu.addMenu(_utilsMenu)

    def _check_deps_manual() -> None:
        from .backend.deps import show_setup_dialog
        show_setup_dialog(mw, force=True)

    _checkDepsAction = QAction(_t("root_menu_check_deps"), mw)
    _checkDepsAction.setProperty("incremento_translation_key", "root_menu_check_deps")
    qconnect(_checkDepsAction.triggered, _check_deps_manual)
    _utilsMenu.addAction(_checkDepsAction)

    _cardFormatUpdatesAction = QAction(_t("root_menu_card_format_updates"), mw)
    _cardFormatUpdatesAction.setProperty("incremento_translation_key", "root_menu_card_format_updates")
    qconnect(
        _cardFormatUpdatesAction.triggered,
        lambda _checked=False: _show_incremento_note_type_updates(manual=True),
    )
    _utilsMenu.addAction(_cardFormatUpdatesAction)

    _utilsMenu.addSeparator()

    _reindexPdfTextAction = QAction(_t("root_menu_reindex_pdf_text"), mw)
    _reindexPdfTextAction.setProperty("incremento_translation_key", "root_menu_reindex_pdf_text")
    qconnect(_reindexPdfTextAction.triggered, reindexPdfTextFunction)
    _utilsMenu.addAction(_reindexPdfTextAction)

    _importNotebookCitationsAction = QAction(_t("root_menu_import_notebook_citations"), mw)
    _importNotebookCitationsAction.setProperty("incremento_translation_key", "root_menu_import_notebook_citations")
    qconnect(_importNotebookCitationsAction.triggered, importNotebookCitationsFunction)
    _utilsMenu.addAction(_importNotebookCitationsAction)

    _ocrImageTextAction = QAction(_t("root_menu_ocr_image_text"), mw)
    _ocrImageTextAction.setProperty("incremento_translation_key", "root_menu_ocr_image_text")
    qconnect(_ocrImageTextAction.triggered, ocrImageTextFunction)
    _utilsMenu.addAction(_ocrImageTextAction)

    _reindexImageOcrCacheAction = QAction(_t("root_menu_reindex_ocr_cache"), mw)
    _reindexImageOcrCacheAction.setProperty("incremento_translation_key", "root_menu_reindex_ocr_cache")
    qconnect(_reindexImageOcrCacheAction.triggered, reindexImageOcrCacheFunction)
    _utilsMenu.addAction(_reindexImageOcrCacheAction)

    _cleanupNonActiveProfileDataAction = QAction(_t("root_menu_cleanup_profile_data"), mw)
    _cleanupNonActiveProfileDataAction.setProperty("incremento_translation_key", "root_menu_cleanup_profile_data")
    qconnect(_cleanupNonActiveProfileDataAction.triggered, cleanupNonActiveProfileDataFunction)
    _utilsMenu.addAction(_cleanupNonActiveProfileDataAction)

    _utilsMenu.addSeparator()

    _cleanupOrphanPdfsAction = QAction(_t("root_menu_cleanup_orphan_pdfs"), mw)
    _cleanupOrphanPdfsAction.setProperty("incremento_translation_key", "root_menu_cleanup_orphan_pdfs")
    qconnect(_cleanupOrphanPdfsAction.triggered, cleanupOrphanPdfsFunction)
    _utilsMenu.addAction(_cleanupOrphanPdfsAction)

    _cleanupOrphanVideosAction = QAction(_t("root_menu_cleanup_orphan_videos"), mw)
    _cleanupOrphanVideosAction.setProperty("incremento_translation_key", "root_menu_cleanup_orphan_videos")
    qconnect(_cleanupOrphanVideosAction.triggered, cleanupOrphanVideosFunction)
    _utilsMenu.addAction(_cleanupOrphanVideosAction)

    _cleanupStaleProgressAction = QAction(_t("root_menu_cleanup_stale_rows"), mw)
    _cleanupStaleProgressAction.setProperty("incremento_translation_key", "root_menu_cleanup_stale_rows")
    qconnect(_cleanupStaleProgressAction.triggered, cleanupStaleProgressFunction)
    _utilsMenu.addAction(_cleanupStaleProgressAction)

    _statsAction = QAction(_t("root_menu_statistics"), mw)
    _statsAction.setProperty("incremento_translation_key", "root_menu_statistics")
    qconnect(_statsAction.triggered, showStatsFunction)
    _menu.addAction(_statsAction)
    _register_shortcut_action("statistics", _statsAction)

    _quickOpenPdfAction = QAction(_t("root_menu_quick_open_content"), mw)
    _quickOpenPdfAction.setProperty("incremento_translation_key", "root_menu_quick_open_content")
    qconnect(_quickOpenPdfAction.triggered, _open_pdf_quick_jump)
    _menu.addAction(_quickOpenPdfAction)
    _register_shortcut_action("quick_open_pdf", _quickOpenPdfAction)

    _documentBookshelfAction = QAction(_t("root_menu_document_bookshelf"), mw)
    _documentBookshelfAction.setProperty("incremento_translation_key", "root_menu_document_bookshelf")
    qconnect(_documentBookshelfAction.triggered, _open_document_bookshelf)
    _menu.addAction(_documentBookshelfAction)
    _register_shortcut_action("document_bookshelf", _documentBookshelfAction)

    _searchCurrentAction = QAction(_t("root_menu_find_current_document"), mw)
    _searchCurrentAction.setProperty("incremento_translation_key", "root_menu_find_current_document")
    qconnect(_searchCurrentAction.triggered, _open_current_document_search)
    _menu.addAction(_searchCurrentAction)
    _register_shortcut_action("search_current_document", _searchCurrentAction)

    _searchAllAction = QAction(_t("root_menu_search_all"), mw)
    _searchAllAction.setProperty("incremento_translation_key", "root_menu_search_all")
    qconnect(_searchAllAction.triggered, _open_search_all)
    _menu.addAction(_searchAllAction)
    _register_shortcut_action("search_all", _searchAllAction)

    _menu.addSeparator()

    _supportBundleAction = QAction(_t("root_menu_export_support_bundle"), mw)
    _supportBundleAction.setProperty("incremento_translation_key", "root_menu_export_support_bundle")
    qconnect(_supportBundleAction.triggered, exportSupportBundleFunction)
    _menu.addAction(_supportBundleAction)

    _exportAction = QAction(_t("root_menu_export_full_backup"), mw)
    _exportAction.setProperty("incremento_translation_key", "root_menu_export_full_backup")
    qconnect(_exportAction.triggered, exportFunction)
    _menu.addAction(_exportAction)
    _register_shortcut_action("export_user_data", _exportAction)

    _restoreAction = QAction(_t("root_menu_restore_full_backup"), mw)
    _restoreAction.setProperty("incremento_translation_key", "root_menu_restore_full_backup")
    qconnect(_restoreAction.triggered, restoreFullBackupFunction)
    _menu.addAction(_restoreAction)

    _autoBackupAction = QAction(_t("root_menu_configure_auto_backups"), mw)
    _autoBackupAction.setProperty("incremento_translation_key", "root_menu_configure_auto_backups")
    qconnect(_autoBackupAction.triggered, configureAutomaticBackupsFunction)
    _menu.addAction(_autoBackupAction)

    _apply_shortcuts_from_config()
    _ensure_settings_menu_action()
    menubar.update()


# Build menu first (sets _timerToggleAction), then build timer toolbar which uses it.
gui_hooks.main_window_did_init.append(_build_incremento_menu)
gui_hooks.main_window_did_init.append(_build_timer_toolbar)
gui_hooks.main_window_did_init.append(_schedule_note_type_update_after_profile_open)
gui_hooks.profile_did_open.append(_schedule_note_type_update_after_profile_open)
gui_hooks.sync_did_finish.append(_schedule_incremento_note_type_update_check)
gui_hooks.state_did_change.append(lambda *_: _build_incremento_menu())
gui_hooks.state_did_change.append(_record_diagnostic_state_change)
gui_hooks.operation_did_execute.append(_sync_ocr_index_for_open_editor_notes)
gui_hooks.operation_did_execute.append(_record_diagnostic_operation)
gui_hooks.reviewer_did_show_question.append(_record_diagnostic_question)
gui_hooks.reviewer_did_answer_card.append(_record_diagnostic_answer)
gui_hooks.undo_state_did_change.append(_reconcile_topic_state_after_anki_operation)
gui_hooks.undo_state_did_change.append(
    _reconcile_custom_schedule_state_after_anki_operation
)
gui_hooks.browser_will_show.append(_prune_incremento_hidden_browser_active_columns)
gui_hooks.editor_did_load_note.append(_hide_incremento_hidden_fields_in_editor)
gui_hooks.editor_will_process_mime.append(
    _reader_links_mod.force_reader_anchor_rich_paste
)
gui_hooks.browser_did_fetch_columns.append(_filter_incremento_hidden_browser_columns)
gui_hooks.browser_will_show_context_menu.append(_on_browser_context_menu)
gui_hooks.browser_menus_did_init.append(
    lambda browser: _browser_quick_tags_mod.install_browser_quick_tag_action(
        browser,
        _ADDON_DIR,
    )
)
