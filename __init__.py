import json
import os
import sqlite3
import time
import weakref
import zipfile
from urllib.parse import unquote

from aqt import mw, gui_hooks
from aqt.reviewer import QueuedCards, Reviewer, SchedulingContext, V3CardInfo
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
from .backend.local_file_manager import add_local_file_card
from .backend.note_metadata import (
    INCREMENTO_HIDDEN_FIELDS,
    build_incremento_metadata,
    derive_note_source_metadata,
    hidden_field_values,
    matches_hidden_field_reference,
    source_document_reference,
)
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
from .backend.decks import create_topics_deck as _create_topics_deck
from .frontend.priority_dialog import PriorityDialog
from .frontend.custom_schedule_dialog import CustomScheduleDialog
from .frontend import timer_widget as _timer_mod
from .backend.topic_scheduler import (
    TOPIC_REVIEW_BUTTONS,
    configured_default_topic_a_factor as _configured_default_topic_a_factor,
    configured_topic_card_tags as _configured_topic_card_tags,
    configured_topic_card_types as _configured_topic_card_types,
    is_topic_card as _is_topic_card,
    on_topic_card_answered as _on_topic_card_answered,
    remap_topic_review_ease as _remap_topic_review_ease,
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
from .frontend import video_dock as _video_dock_mod
from .frontend import web_dock as _web_dock_mod
from .frontend import writing_dock as _writing_dock_mod
from .frontend import local_file_dock as _local_file_dock_mod
from .frontend import add_card_dock as _add_card_dock_mod
from .frontend import browser_priority_toolbar as _browser_priority_toolbar_mod
from .backend import review_time_tracker as _review_time_mod
from .backend.db import (
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
from .backend.session import (
    learnFunction,
    reset_session_counts,
    get_session_counts,
    get_session_times,
    start_quick_open_review,
)
from .frontend.settings_dialog import IncrementoSettingsDialog, default_shortcuts
from .frontend.pdf_quick_jump import _PdfQuickJumpDialog
from .frontend.reviewer_extract_button import build_reviewer_extract_button_js
from .frontend.reviewer_priority_badge import build_reviewer_priority_badge_js
from .frontend.reviewer_shortcuts import filter_reviewer_shortcuts
from .frontend.reviewer_source_cover import build_reviewer_source_cover_js
from .frontend.database_entries_dialog import show_database_entries_dialog
from .frontend.reviewer_tag_dialog import ReviewerTagDialog
from .frontend.search_all import _SearchAllDialog
from .backend.knowledge_tree import (
    NODE_KIND_ITEM as _KT_NODE_KIND_ITEM,
    NODE_KIND_TOPIC as _KT_NODE_KIND_TOPIC,
    apply_node_kind_to_cards as _kt_apply_node_kind_to_cards,
)
from .backend.reviewer_extract import (
    initial_extract_field_values as _initial_extract_field_values,
    knowledge_tree_link_state as _knowledge_tree_link_state,
)

_ADDON_DIR = os.path.dirname(__file__)

try:
    _browser_bridge_mod.start_browser_bridge(_ADDON_DIR)
except Exception:
    pass

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


def configured_show_incremento_fields(cfg: dict | None = None) -> bool:
    config = cfg if cfg is not None else (mw.addonManager.getConfig(__name__) or {})
    return bool(config.get("show_incremento_fields", False))


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
    cfg = mw.addonManager.getConfig(__name__) or {}
    defaults = default_shortcuts()
    user_shortcuts = cfg.get("shortcuts") or {}

    for action_id, action_targets in _shortcut_actions.items():
        shortcut_text = user_shortcuts.get(action_id, defaults.get(action_id, ""))
        seq = QKeySequence(shortcut_text) if shortcut_text else QKeySequence()
        for action_obj in action_targets:
            if hasattr(action_obj, "setShortcut"):
                action_obj.setShortcut(seq)
            elif hasattr(action_obj, "setKey"):
                action_obj.setKey(seq)


def _configured_shortcut_text(action_id: str) -> str:
    cfg = mw.addonManager.getConfig(__name__) or {}
    defaults = default_shortcuts()
    user_shortcuts = cfg.get("shortcuts") or {}
    return str(user_shortcuts.get(action_id, defaults.get(action_id, "")) or "").strip()


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


_ORIGINAL_REVIEWER_AFTER_ANSWERING = getattr(
    Reviewer._after_answering,
    "_incremento_original",
    Reviewer._after_answering,
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


_incremento_after_answering._incremento_original = _ORIGINAL_REVIEWER_AFTER_ANSWERING
Reviewer._after_answering = _incremento_after_answering

_ORIGINAL_REVIEWER_BUTTON_TIME = getattr(
    Reviewer._buttonTime,
    "_incremento_original",
    Reviewer._buttonTime,
)
_ORIGINAL_REVIEWER_DEFAULT_EASE = getattr(
    Reviewer._defaultEase,
    "_incremento_original",
    Reviewer._defaultEase,
)
_ORIGINAL_REVIEWER_SHORTCUT_KEYS = getattr(
    Reviewer._shortcutKeys,
    "_incremento_original",
    Reviewer._shortcutKeys,
)
_ORIGINAL_REVIEWER_ON_ENTER_KEY = getattr(
    Reviewer.onEnterKey,
    "_incremento_original",
    Reviewer.onEnterKey,
)
_ORIGINAL_REVIEWER_NEXT_CARD = getattr(
    Reviewer.nextCard,
    "_incremento_original",
    Reviewer.nextCard,
)
_ORIGINAL_REVIEWER_OP_EXECUTED = getattr(
    Reviewer.op_executed,
    "_incremento_original",
    Reviewer.op_executed,
)
_ORIGINAL_REVIEWER_SHOW_ANSWER_BUTTON = getattr(
    Reviewer._showAnswerButton,
    "_incremento_original",
    Reviewer._showAnswerButton,
)
_ORIGINAL_REVIEWER_SHOW_EASE_BUTTONS = getattr(
    Reviewer._showEaseButtons,
    "_incremento_original",
    Reviewer._showEaseButtons,
)
_ORIGINAL_REVIEWER_LINK_HANDLER = getattr(
    Reviewer._linkHandler,
    "_incremento_original",
    Reviewer._linkHandler,
)


def _reviewer_topic_card(card) -> bool:
    return _reviewer_button_mode_for_card(card) == "topic"


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
    try:
        mode = _configured_topic_postpone_mode()
        if mode == "session":
            _postpone_topic_card(card, mode="session", bury=False)
    except Exception as e:
        print(f"[Incremento] topic postpone error: {e}")
        try:
            reviewer.nextCard()
        except Exception:
            pass
        return

    def _after_bury(_changes) -> None:
        if mode == "timed":
            try:
                _store_timed_topic_postpone(
                    card,
                    minutes=_configured_topic_postpone_minutes(),
                    bury=False,
                )
                _schedule_topic_postpone_timer()
            except Exception as e:
                print(f"[Incremento] topic postpone timed save error: {e}")
        try:
            if mode == "session":
                tooltip("Topic postponed to later in this review.")
            else:
                tooltip(
                    f"Topic postponed for {_configured_topic_postpone_minutes()} minutes."
                )
        except Exception:
            pass
        try:
            current = getattr(reviewer, "card", None)
            if current is not None and getattr(current, "id", None) == getattr(card, "id", None):
                reviewer.nextCard()
        except Exception as e:
            print(f"[Incremento] topic postpone nextCard error: {e}")

    try:
        _bury_cards_op(parent=reviewer.mw, card_ids=[card.id]).success(_after_bury).run_in_background()
    except Exception as e:
        print(f"[Incremento] topic postpone bury error: {e}")
        try:
            reviewer.nextCard()
        except Exception:
            pass


def _perform_item_skip(reviewer, card) -> None:
    try:
        _store_timed_item_skip(
            card,
            minutes=_configured_item_skip_minutes(),
            bury=False,
        )
        _schedule_item_skip_timer()
    except Exception as e:
        print(f"[Incremento] item skip error: {e}")
    try:
        tooltip(f"Skipped for {_configured_item_skip_minutes()} minutes.")
    except Exception:
        pass
    try:
        current = getattr(reviewer, "card", None)
        if current is not None and getattr(current, "id", None) == getattr(card, "id", None):
            reviewer.nextCard()
    except Exception as e:
        print(f"[Incremento] item skip nextCard error: {e}")


def _perform_item_skip_after_bury(reviewer, card) -> None:
    def _after_bury(_changes) -> None:
        _perform_item_skip(reviewer, card)

    try:
        _bury_cards_op(parent=reviewer.mw, card_ids=[card.id]).success(_after_bury).run_in_background()
    except Exception as e:
        print(f"[Incremento] item skip bury error: {e}")
        try:
            reviewer.nextCard()
        except Exception:
            pass


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
        return (proceed, _remap_topic_review_ease(ease))
    if _reviewer_items_fail_pass(card):
        return (proceed, _remap_item_fail_pass_ease(card, ease))
    return response


def _direct_review_queue_kind(card) -> int:
    try:
        queue = int(getattr(card, "queue", 0) or 0)
    except Exception:
        queue = 0
    try:
        card_type = int(getattr(card, "type", 0) or 0)
    except Exception:
        card_type = 0

    if queue == 0 or card_type == 0:
        return QueuedCards.NEW
    if queue in (1, 3) or card_type in (1, 3):
        return QueuedCards.LEARNING
    return QueuedCards.REVIEW


def _direct_review_counts(card_ids: list[int]) -> tuple[int, int, int]:
    counts = [0, 0, 0]
    for raw_card_id in card_ids:
        try:
            card = mw.col.get_card(int(raw_card_id))
        except Exception:
            continue
        if card is None:
            continue
        try:
            if int(getattr(card, "queue", 0) or 0) < 0:
                continue
        except Exception:
            continue
        kind = _direct_review_queue_kind(card)
        if kind == QueuedCards.NEW:
            counts[0] += 1
        elif kind == QueuedCards.LEARNING:
            counts[1] += 1
        else:
            counts[2] += 1
    return counts[0], counts[1], counts[2]


def _direct_review_v3_info(card) -> V3CardInfo | None:
    try:
        states = mw.col._backend.get_scheduling_states(int(card.id))
        new_count, learning_count, review_count = _direct_review_counts(
            [int(card.id), *_direct_review_card_ids]
        )
        try:
            deck_name = str(mw.col.decks.name(getattr(card, "did", 0)) or "")
        except Exception:
            deck_name = ""
        queued_cards = QueuedCards(
            cards=[
                QueuedCards.QueuedCard(
                    card=card._to_backend_card(),
                    queue=_direct_review_queue_kind(card),
                    states=states,
                    context=SchedulingContext(deck_name=deck_name),
                )
            ],
            new_count=new_count,
            learning_count=learning_count,
            review_count=review_count,
        )
        return V3CardInfo.from_queue(queued_cards)
    except Exception as exc:
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
    return True, None, None


def _clear_direct_review_queue(*_args, **_kwargs) -> None:
    global _direct_review_active
    _direct_review_card_ids.clear()
    _direct_review_active = False


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
        self._answerCard(2)
        return
    if (
        self.state == "answer"
        and _reviewer_items_fail_pass(card)
        and mw.pm.spacebar_rates_card()
    ):
        self._answerCard(2)
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
        self._get_next_v3_card()

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
            self._get_next_v3_card()

    self._previous_card_info.set_card(self.previous_card)
    self._card_info.set_card(self.card)

    if not self.card:
        self.mw.moveToState("overview")
        return

    if self._reps is None:
        self._initWeb()

    self._showQuestion()


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
<button id="incremento-item-skip-but" onclick='pycmd("incremento_item_skip");' style="border-color:#a34747;color:#ffb3b3;">Skip<span class=stattxt>{skip_due}</span></button>
</td>
</tr></table>
""".format(
            show_answer_key=show_answer_key,
            show_answer=tr.studying_show_answer(),
            remaining=self._remaining(),
            skip_due=skip_due,
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
<td class=stat2 align=center>
<button title="{postpone_key}" id="incremento-postpone-but" onclick='pycmd("incremento_topic_postpone");' style="border-color:#a34747;color:#ffb3b3;">Postpone<span class=stattxt>{postpone_due}</span></button>
</td>
</tr></table>
""".format(
        show_answer_key=show_answer_key,
        show_answer=tr.studying_show_answer(),
        remaining=self._remaining(),
        postpone_key=postpone_key,
        postpone_due=postpone_due,
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
        reviewer.bottom.web.eval(
            build_reviewer_extract_button_js(_configured_shortcut_text("extract_card"))
        )
    except Exception:
        pass


def _incremento_show_ease_buttons(self) -> None:
    _ORIGINAL_REVIEWER_SHOW_EASE_BUTTONS(self)
    _sync_topic_answer_button_style(self)
    _sync_reviewer_extract_button(self)


def _incremento_link_handler(self, url: str) -> None:
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


_incremento_button_time._incremento_original = _ORIGINAL_REVIEWER_BUTTON_TIME
Reviewer._buttonTime = _incremento_button_time
_incremento_default_ease._incremento_original = _ORIGINAL_REVIEWER_DEFAULT_EASE
Reviewer._defaultEase = _incremento_default_ease
_incremento_shortcut_keys._incremento_original = _ORIGINAL_REVIEWER_SHORTCUT_KEYS
Reviewer._shortcutKeys = _incremento_shortcut_keys
_incremento_on_enter_key._incremento_original = _ORIGINAL_REVIEWER_ON_ENTER_KEY
Reviewer.onEnterKey = _incremento_on_enter_key
_incremento_next_card._incremento_original = _ORIGINAL_REVIEWER_NEXT_CARD
Reviewer.nextCard = _incremento_next_card
_incremento_op_executed._incremento_original = _ORIGINAL_REVIEWER_OP_EXECUTED
Reviewer.op_executed = _incremento_op_executed
_incremento_show_answer_button._incremento_original = _ORIGINAL_REVIEWER_SHOW_ANSWER_BUTTON
Reviewer._showAnswerButton = _incremento_show_answer_button
_incremento_show_ease_buttons._incremento_original = _ORIGINAL_REVIEWER_SHOW_EASE_BUTTONS
Reviewer._showEaseButtons = _incremento_show_ease_buttons
_incremento_link_handler._incremento_original = _ORIGINAL_REVIEWER_LINK_HANDLER
Reviewer._linkHandler = _incremento_link_handler


mw.addonManager.setWebExports(__name__, r"web/.*")

# Last cards opened via the Quick Open dialog (used by Ctrl+L).
_last_opened_pdf_cid: int | None = None
_last_opened_writing_cid: int | None = None


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
        showInfo("Select one or more Browser rows first.")
        return

    result = _kt_apply_node_kind_to_cards(card_ids, node_kind)
    changed_count = int(result.get("changed_count") or 0)
    error_count = int(result.get("error_count") or 0)
    label = "topics" if node_kind == _KT_NODE_KIND_TOPIC else "items"

    try:
        mw.col.reset()
    except Exception:
        pass
    try:
        browser.search()
    except Exception:
        pass

    if error_count:
        showInfo(
            f"Converted {changed_count} selected card{'s' if changed_count != 1 else ''} "
            f"to {label}, but {error_count} failed."
        )
        return
    tooltip(
        f"Converted {changed_count} selected card{'s' if changed_count != 1 else ''} "
        f"to {label}."
    )


def _open_custom_schedule_dialog(card_ids: list[int]) -> None:
    normalized_ids = sorted({int(card_id) for card_id in (card_ids or [])})
    if not normalized_ids:
        showInfo("Select one or more Browser rows first.")
        return

    cfg = mw.addonManager.getConfig(__name__) or {}
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
        tooltip(
            f"Cleared custom schedule on {cleared} selected "
            f"card{'s' if cleared != 1 else ''}."
        )
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
        tooltip(
            f"Saved {summary} on {updated} card{'s' if updated != 1 else ''}. "
            f"Applied now to {applied_now}."
        )
    else:
        tooltip(
            f"Saved {summary} on {updated} card{'s' if updated != 1 else ''}."
        )


def _open_browser_a_factor_dialog(browser, card_ids: list[int]) -> None:
    normalized_ids = sorted({int(card_id) for card_id in (card_ids or [])})
    if not normalized_ids:
        showInfo("Select one or more Browser rows first.")
        return

    value, accepted = QInputDialog.getDouble(
        mw,
        "Set A-Factor",
        "A-Factor:",
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
            showInfo(
                f"No topic cards were updated. {errors} selected "
                f"card{'s' if errors != 1 else ''} failed to load or save."
            )
        else:
            showInfo("No topic cards found in the selected Browser rows.")
        return

    try:
        mw.col.reset()
    except Exception:
        pass
    try:
        browser.search()
    except Exception:
        pass

    msg = f"Set A-Factor {float(value):.3f} on {updated} topic card{'s' if updated != 1 else ''}."
    if skipped:
        msg += f" Skipped {skipped} non-topic card{'s' if skipped != 1 else ''}."
    if errors:
        msg += f" {errors} selected card{'s' if errors != 1 else ''} failed."
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
        showInfo("No Incremento PDF cards found in the selected Browser rows.")
        return

    regenerated = 0
    cleared = 0
    failed: list[str] = []

    mw.progress.start(label="Regenerating PDF covers…", immediate=True)
    try:
        total = len(pdf_card_ids)
        for index, card_id in enumerate(pdf_card_ids, start=1):
            try:
                mw.progress.update(label=f"({index}/{total}) Regenerating PDF covers…")
            except Exception:
                pass
            try:
                cover_filename = regenerate_pdf_card_cover(_ADDON_DIR, mw.col, int(card_id))
                if cover_filename:
                    regenerated += 1
                else:
                    cleared += 1
            except Exception as exc:
                failed.append(f"Card {card_id}: {exc}")
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
            details += f"\n… and {len(failed) - 10} more."
        message = (
            f"Regenerated {regenerated} PDF cover{'s' if regenerated != 1 else ''} "
            f"and cleared {cleared}."
        )
        if skipped:
            message += f" Skipped {skipped} non-PDF selected card{'s' if skipped != 1 else ''}."
        message += f"\n\nFailures:\n{details}"
        showInfo(message)
        return

    message = (
        f"Regenerated {regenerated} PDF cover{'s' if regenerated != 1 else ''} "
        f"and cleared {cleared}."
    )
    if skipped:
        message += f" Skipped {skipped} non-PDF selected card{'s' if skipped != 1 else ''}."
    tooltip(message)


def _regenerate_epub_covers_for_browser_selection(browser) -> None:
    epub_card_ids, skipped = _browser_selected_epub_card_ids(browser)
    if not epub_card_ids:
        showInfo("No Incremento EPUB cards found in the selected Browser rows.")
        return

    regenerated = 0
    cleared = 0
    failed: list[str] = []

    mw.progress.start(label="Regenerating EPUB covers…", immediate=True)
    try:
        total = len(epub_card_ids)
        for index, card_id in enumerate(epub_card_ids, start=1):
            try:
                mw.progress.update(label=f"({index}/{total}) Regenerating EPUB covers…")
            except Exception:
                pass
            try:
                cover_filename = regenerate_epub_card_cover(_ADDON_DIR, mw.col, int(card_id))
                if cover_filename:
                    regenerated += 1
                else:
                    cleared += 1
            except Exception as exc:
                failed.append(f"Card {card_id}: {exc}")
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
            details += f"\n… and {len(failed) - 10} more."
        message = (
            f"Regenerated {regenerated} EPUB cover{'s' if regenerated != 1 else ''} "
            f"and cleared {cleared}."
        )
        if skipped:
            message += f" Skipped {skipped} non-EPUB selected card{'s' if skipped != 1 else ''}."
        message += f"\n\nFailures:\n{details}"
        showInfo(message)
        return

    message = (
        f"Regenerated {regenerated} EPUB cover{'s' if regenerated != 1 else ''} "
        f"and cleared {cleared}."
    )
    if skipped:
        message += f" Skipped {skipped} non-EPUB selected card{'s' if skipped != 1 else ''}."
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
        "Selected card IDs: " + ", ".join(str(card_id) for card_id in card_ids),
        f"Profile: {payload.get('profile') or ''}",
        f"Database: {payload.get('db_path') or ''}",
    ]
    separator = "-" * 72
    for card_id in card_ids:
        card_entries = [
            entry
            for entry in entries
            if int((entry or {}).get("card_id") or 0) == int(card_id)
        ]
        lines.extend(["", separator, f"Card {card_id}"])
        if not card_entries:
            lines.append(f"No Incremento database rows found for card {card_id}.")
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
                row_label = "effective values (not yet persisted)"
            else:
                rowid = entry.get("rowid")
                row_label = f"rowid {rowid}" if rowid is not None else "row"
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
        showInfo("Select one or more Browser rows first.")
        return

    try:
        payload = find_card_database_entries(_ADDON_DIR, _active_profile(), card_ids)
    except Exception as exc:
        showInfo(f"Could not read Incremento database entries:\n{exc}")
        return

    payload = _add_effective_topic_schedule_entries(payload)
    show_database_entries_dialog(mw, text=_format_browser_database_entries(payload))


def _start_direct_browser_review(card_ids: list[int]) -> None:
    global _direct_review_active
    normalized_ids: list[int] = []
    seen: set[int] = set()
    skipped = 0

    for raw_card_id in card_ids or []:
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

    if not normalized_ids:
        showInfo("No selected cards are available to study.")
        return

    _direct_review_card_ids[:] = normalized_ids
    _direct_review_active = True

    if skipped:
        tooltip(
            f"Studying {len(normalized_ids)} selected card"
            f"{'s' if len(normalized_ids) != 1 else ''}. "
            f"Skipped {skipped} unavailable card{'s' if skipped != 1 else ''}."
        )

    try:
        if getattr(mw, "state", None) == "review" and getattr(mw, "reviewer", None):
            mw.reviewer.nextCard()
        else:
            mw.moveToState("review")
    except Exception as exc:
        _clear_direct_review_queue()
        showInfo(f"Could not start studying the selected cards:\n{exc}")


def _on_browser_context_menu(browser, menu: QMenu) -> None:
    card_ids = _browser_selected_incremento_card_ids(browser)
    if not card_ids:
        return

    menu.addSeparator()
    submenu = QMenu("Incremento", menu)
    count_label = f"{len(card_ids)} selected card{'s' if len(card_ids) != 1 else ''}"
    study_action = QAction(f"Study Selected Cards ({count_label})", submenu)
    topic_action = QAction(f"Make Topic ({count_label})", submenu)
    item_action = QAction(f"Make Item ({count_label})", submenu)
    a_factor_action = QAction(f"Set A-Factor… ({count_label})", submenu)
    schedule_action = QAction(f"Custom Schedule… ({count_label})", submenu)
    pdf_cover_action = QAction(f"Regenerate PDF Covers ({count_label})", submenu)
    epub_cover_action = QAction(f"Regenerate EPUB Covers ({count_label})", submenu)
    ocr_action = QAction(f"OCR Image Text ({count_label})", submenu)
    hidden_fields_action = QAction(f"Show Hidden Fields ({count_label})", submenu)
    database_entries_action = QAction(f"Show Database Entries ({count_label})", submenu)

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
) -> None:
    clean_filename = str(filename or "").strip()
    clean_excerpt = str(excerpt or "").strip()
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
        )
    else:
        _pdf_dock_mod.show_pdf_in_dock(
            0,
            clean_filename,
            page,
            zoom,
            via_link=True,
            jump_excerpt=clean_excerpt,
            offer_due_review_prompt=False,
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
            _add_card_dock_mod.set_current_extract_options(
                priority=data.get("priority"),
                mark_topic=bool(data.get("markTopic")),
                link_to_knowledge_tree=bool(data.get("linkToKnowledgeTree")),
            )
            _add_card_dock_mod.sync_pending_extract_options_from_current()
        except Exception:
            pass
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
        parts = message.split(":")
        if len(parts) >= 4:
            try:
                card_id = int(parts[1])
                section_index = int(parts[2])
                focus_offset = int(parts[3])
                _epub_dock_mod.open_epub_location(
                    card_id,
                    section_index,
                    focus_offset=focus_offset,
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


def _on_profile_did_open() -> None:
    """Activate per-profile paths and run one-time migration on first load."""
    from .backend.migration import migrate_to_profile_dir
    profile = _current_profile_name()
    # Reset Qt WebEngine profile singletons before migration so they are
    # recreated with the correct per-profile storage path on next use.
    _video_dock_mod.reset_for_profile_switch()
    _web_dock_mod.reset_for_profile_switch()
    _paths.set_active_profile(profile)
    migrate_to_profile_dir(_ADDON_DIR, profile)
    try:
        _create_topics_deck()
    except Exception:
        pass


gui_hooks.profile_did_open.append(_on_profile_did_open)


def _sync_pdf_note_type() -> None:
    """Update the PDF card template to the current code version on startup."""
    from .backend.pdf_manager import ensure_pdf_note_type

    def _run() -> None:
        try:
            ensure_pdf_note_type(mw.col)
        except Exception:
            pass

    mw.taskman.run_in_background(_run)


gui_hooks.main_window_did_init.append(_sync_pdf_note_type)
gui_hooks.main_window_did_init.append(_epub_dock_mod.sync_epub_note_type)
gui_hooks.main_window_did_init.append(_video_dock_mod.sync_video_note_type)
gui_hooks.main_window_did_init.append(_web_dock_mod.sync_web_note_type)
gui_hooks.main_window_did_init.append(_writing_dock_mod.sync_writing_note_type)
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
gui_hooks.main_window_did_init.append(
    lambda: _browser_bridge_mod.start_browser_bridge(_ADDON_DIR)
)
gui_hooks.profile_will_close.append(_browser_bridge_mod.stop_browser_bridge)


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
    if card is not None:
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
        "source_label": "Source PDF",
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
                source_label=str((payload or {}).get("source_label") or "Source PDF"),
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


def _check_deps_first_run() -> None:
    """On first run after install, show the dependency setup dialog if anything is missing."""
    from .backend.deps import status
    config = mw.addonManager.getConfig(__name__) or {}
    if config.get("deps_notified"):
        return
    s = status()
    if s["pymupdf"] and s["tesseract"]:
        # Everything present — mark as notified and skip
        config["deps_notified"] = True
        mw.addonManager.writeConfig(__name__, config)
        return
    # Something is missing — show the setup dialog once
    config["deps_notified"] = True
    mw.addonManager.writeConfig(__name__, config)

    def _show():
        from .backend.deps import show_setup_dialog
        show_setup_dialog(mw)

    # Defer slightly so Anki finishes loading before the dialog appears
    from aqt.qt import QTimer
    QTimer.singleShot(1500, _show)


gui_hooks.main_window_did_init.append(_check_deps_first_run)


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
        showInfo(f"Could not open document:\n{e}")


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
    preserve_history: bool = False,
) -> None:
    global _last_opened_pdf_cid
    card = mw.col.get_card(card_id)
    note = mw.col.get_note(card.nid)
    filename = note["PDF_Filename"]
    open_page = page if page is not None else get_page(_ADDON_DIR, _active_profile(), card_id)
    zoom = get_zoom(_ADDON_DIR, _active_profile(), card_id)
    read_page = get_read_page(_ADDON_DIR, _active_profile(), card_id)
    _last_opened_pdf_cid = card_id
    _pdf_dock_mod.show_pdf_in_dock(
        card_id,
        filename,
        open_page,
        zoom,
        read_page=read_page,
        search_query=search_query,
        preserve_history=preserve_history,
    )


def _open_epub_card(
    card_id: int,
    section_index: int | None = None,
    *,
    focus_offset: int = -1,
    search_query: str = "",
) -> None:
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


def _open_search_all() -> None:
    _SearchAllDialog(
        mw,
        addon_dir=_ADDON_DIR,
        open_pdf_card=_open_pdf_card,
        open_epub_card=_open_epub_card,
    ).exec()


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
        tooltip("No video review card is currently active.")
        return
    _video_dock_mod.download_current_video_locally()


def _configure_current_reviewer_video_captions() -> None:
    if _current_reviewer_video_card() is None:
        tooltip("No video review card is currently active.")
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
        tooltip("No review card is currently active.")
        return
    _open_knowledge_tree(select_card_id=card_id)


def _go_to_parent_in_knowledge_tree() -> None:
    card_id = _current_reviewer_card_id()
    if card_id is None:
        tooltip("No review card is currently active.")
        return

    row = get_knowledge_tree_node(_ADDON_DIR, _active_profile(), int(card_id))
    if row is None:
        tooltip("Current card is not linked in the knowledge tree.")
        return

    parent_card_id = row.get("parent_card_id")
    if parent_card_id is None:
        tooltip("Current card is already at the top of the knowledge tree.")
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
        showInfo(f"Could not prepare branch study session:\n{exc}")
        return

    if not branch_scope or not list(branch_scope.get("card_ids") or []):
        tooltip("Selected branch does not contain any knowledge-tree cards.")
        return

    learnFunction(branch_scope=branch_scope)


def _trigger_pdf_viewer_action(action: str) -> None:
    _pdf_dock_mod.trigger_viewer_action(action)


_pdf_jump_shortcut = QShortcut(QKeySequence("Ctrl+Alt+P"), mw)
_pdf_jump_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(_pdf_jump_shortcut.activated, _open_pdf_quick_jump)
_register_shortcut_action("quick_open_pdf", _pdf_jump_shortcut)

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
        lines = [f"Added {len(created)} PDF card(s) → {deck}\n"]
        for path, title in created:
            lines.append(f"• {title}")
            lines.append(f"  {os.path.basename(path)}  ·  {_fmt_size(path)}")
        if failed:
            lines.append(f"\nFailed: {len(failed)}")
            for path, msg in failed[:10]:
                lines.append(f"• {os.path.basename(path)}: {msg}")
            if len(failed) > 10:
                lines.append(f"  …and {len(failed) - 10} more")
        showInfo("\n".join(lines))
    else:
        failed_lines = "\n".join(
            f"• {os.path.basename(p)}: {msg}" for p, msg in failed[:10]
        )
        extra = f"\n…and {len(failed) - 10} more" if len(failed) > 10 else ""
        showInfo(f"All imports failed ({len(failed)}):\n\n{failed_lines}{extra}")


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
        lines = [f"Added {len(created)} EPUB card(s) → {deck}\n"]
        for path, title in created:
            lines.append(f"• {title}")
            lines.append(f"  {os.path.basename(path)}")
        if failed:
            lines.append(f"\nFailed: {len(failed)}")
            for path, msg in failed[:10]:
                lines.append(f"• {os.path.basename(path)}: {msg}")
            if len(failed) > 10:
                lines.append(f"  …and {len(failed) - 10} more")
        showInfo("\n".join(lines))
    else:
        failed_lines = "\n".join(
            f"• {os.path.basename(p)}: {msg}" for p, msg in failed[:10]
        )
        extra = f"\n…and {len(failed) - 10} more" if len(failed) > 10 else ""
        showInfo(f"All EPUB imports failed ({len(failed)}):\n\n{failed_lines}{extra}")


def exportFunction() -> None:
    import datetime
    import tempfile
    from pathlib import Path

    from anki import hooks
    from anki.exporting import AnkiPackageExporter
    from aqt.qt import QFileDialog
    from .backend.db import (
        get_connection,
        DB_NAME,
        export_priorities_json,
        export_pdf_progress_json,
        export_highlights_json,
        export_stats_json,
    )
    from .backend.export_bundle import snapshot_tree

    today = datetime.date.today().isoformat()
    default_name = os.path.expanduser(f"~/incremento_full_backup_{today}.zip")

    path, _ = QFileDialog.getSaveFileName(
        mw,
        "Export Incremento Full Backup",
        default_name,
        "ZIP files (*.zip)",
    )
    if not path:
        return
    if not path.lower().endswith(".zip"):
        path += ".zip"

    user_files_dir = str(_paths.get_user_files_dir(_ADDON_DIR, _active_profile()))
    config = mw.addonManager.getConfig(__name__) or {}

    def _restore_instructions() -> str:
        return "\n".join(
            [
                "Incremento Full Backup Restore",
                "==============================",
                "",
                "This archive contains:",
                "1. anki/all_decks.apkg  -> import this into a fresh Anki profile",
                "2. user_files/          -> copy into addons21/incremento/user_files/",
                "3. config.json          -> restore Incremento add-on config if needed",
                "",
                "Recommended restore order:",
                "1. Install Anki.",
                "2. Install the Incremento add-on.",
                "3. Import anki/all_decks.apkg in Anki.",
                "4. Close Anki.",
                "5. Replace the add-on's user_files/ folder with the exported user_files/ folder.",
                "6. If needed, paste config.json into Tools -> Add-ons -> Incremento -> Config.",
                "7. Start Anki and verify PDFs, videos, writing notes, highlights, and progress.",
                "",
                "Notes:",
                "- The APKG is generated from the currently open Anki profile.",
                "- The user_files snapshot contains Incremento runtime data such as PDFs, videos, writing files, and browser profiles.",
            ]
        )

    def _progress(label: str) -> None:
        mw.taskman.run_on_main(lambda: mw.progress.update(label=label))

    mw.progress.start(label="Preparing full backup…", immediate=True)

    def _task():
        _video_dock_mod.flush_video_progress()
        conn = get_connection(_ADDON_DIR, _active_profile())
        conn.commit()

        priority_count = conn.execute("SELECT COUNT(*) FROM priorities").fetchone()[0]
        highlight_count = conn.execute("SELECT COUNT(*) FROM pdf_highlights").fetchone()[0]
        pdf_progress_count = conn.execute("SELECT COUNT(*) FROM pdf_progress").fetchone()[0]
        stats_count = conn.execute("SELECT COUNT(*) FROM stats").fetchone()[0]

        with tempfile.TemporaryDirectory(prefix="incremento_export_") as tmp_dir:
            tmp_root = Path(tmp_dir)
            apkg_path = tmp_root / "all_decks.apkg"
            db_snapshot_path = tmp_root / DB_NAME

            _progress("Creating Anki package…")
            exporter = AnkiPackageExporter(mw.col)
            exporter.includeSched = True
            exporter.includeMedia = True
            exporter.did = None
            exporter.cids = None

            def _exported_media_count(cnt: int) -> None:
                _progress(f"Creating Anki package… exported media {cnt}")

            hooks.media_files_did_export.append(_exported_media_count)
            try:
                exporter.exportInto(str(apkg_path))
            finally:
                hooks.media_files_did_export.remove(_exported_media_count)

            _progress("Snapshotting Incremento user_files…")
            snapshot_conn = sqlite3.connect(str(db_snapshot_path))
            try:
                conn.backup(snapshot_conn)
            finally:
                snapshot_conn.close()

            stage_root = tmp_root / "bundle"
            user_files_stage = stage_root / "user_files"
            user_files_stage.mkdir(parents=True, exist_ok=True)

            user_files_stats = snapshot_tree(
                user_files_dir,
                str(user_files_stage),
                skip_relpaths={DB_NAME, f"{DB_NAME}-wal", f"{DB_NAME}-shm"},
            )
            db_stage_path = user_files_stage / DB_NAME
            db_stage_path.write_bytes(db_snapshot_path.read_bytes())

            _progress("Writing backup ZIP…")
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(apkg_path, "anki/all_decks.apkg")
                zf.write(db_stage_path, f"user_files/{DB_NAME}")

                for root, _, filenames in os.walk(user_files_stage):
                    for filename in filenames:
                        file_path = Path(root) / filename
                        if file_path == db_stage_path:
                            continue
                        arcname = file_path.relative_to(stage_root).as_posix()
                        zf.write(file_path, arcname)

                zf.writestr("config.json", json.dumps(config, ensure_ascii=False, indent=2))
                zf.writestr("restore.txt", _restore_instructions())
                zf.writestr("data/priorities.json", export_priorities_json(_ADDON_DIR, _active_profile()))
                zf.writestr("data/pdf_progress.json", export_pdf_progress_json(_ADDON_DIR, _active_profile()))
                zf.writestr("data/highlights.json", export_highlights_json(_ADDON_DIR, _active_profile()))
                zf.writestr("data/stats.json", export_stats_json(_ADDON_DIR, _active_profile()))

                manifest = {
                    "export_date": today,
                    "addon": "Incremento",
                    "anki_version": getattr(mw.pm, "meta", {}).get(
                        "ankiVersion", "unknown"
                    ),
                    "profile": _current_profile_name(),
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
                        "user_files/": "Full Incremento runtime snapshot (PDFs, videos, writing, browser profiles, database)",
                        "config.json": "Incremento add-on config",
                        "restore.txt": "Restore instructions for a fresh install",
                        "data/priorities.json": "Card priorities (human-readable copy)",
                        "data/pdf_progress.json": "PDF reading positions and zoom levels",
                        "data/highlights.json": "PDF text highlights",
                        "data/stats.json": "Session, daily and lifetime statistics",
                    },
                }
                zf.writestr(
                    "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2)
                )

            return {
                "anki_cards_exported": int(getattr(exporter, "count", 0) or 0),
                "priority_count": int(priority_count or 0),
                "user_files_copied": int(user_files_stats["files_copied"]) + 1,
                "user_files_skipped": int(user_files_stats["files_skipped"]),
            }

    def _on_done(fut) -> None:
        mw.progress.finish()
        try:
            result = fut.result()
        except Exception as e:
            showInfo(f"Export failed:\n{e}")
            return

        showInfo(
            f"Full backup complete.\n\n"
            f"  • {result['anki_cards_exported']} card(s) exported to anki/all_decks.apkg\n"
            f"  • {result['user_files_copied']} user_files item(s) copied\n"
            f"  • {result['priority_count']} card priorit{'y' if result['priority_count'] == 1 else 'ies'}\n"
            f"  • {result['user_files_skipped']} transient runtime file(s) skipped\n\n"
            f"Saved to:\n{path}"
        )

    mw.taskman.run_in_background(_task, _on_done)


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
        priority=_add_card_dock_mod.source_relative_extract_priority_for_card(
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
        msg = f"Priority set to {dlg.priority:.0f}"
        if dlg.a_factor is not None:
            set_topic_schedule(_ADDON_DIR, _active_profile(), card.id, dlg.a_factor, interval or 1)
            msg += f"  ·  A-Factor {dlg.a_factor:.3f}"
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
        showInfo("No card is currently being reviewed.")
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
        showInfo("No card is currently being reviewed.")
        return
    try:
        note = card.note()
    except Exception:
        note = None
    if note is None:
        showInfo("Could not load the current note.")
        return

    try:
        all_tags = sorted(mw.col.tags.all(), key=lambda value: (str(value).lower(), str(value)))
    except Exception:
        all_tags = []
    current_tags = normalize_tag_list(getattr(note, "tags", []) or [])
    recent_tags = get_recent_reviewer_tags(_ADDON_DIR, _active_profile(), limit=10)
    if not all_tags and not recent_tags:
        showInfo("No tags exist in this collection yet.")
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
        tooltip("All selected tags are already on this note.")
        return

    _save_note_tags(note, updated_tags)
    touch_recent_reviewer_tags(_ADDON_DIR, _active_profile(), added_tags, limit=10)
    summary = ", ".join(added_tags[:4])
    if len(added_tags) > 4:
        summary += ", ..."
    tooltip(f"Added tags: {summary}")


_priority_shortcut = QShortcut(QKeySequence("Alt+P"), mw)
_priority_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(_priority_shortcut.activated, _open_priority_dialog)
_register_shortcut_action("set_priority", _priority_shortcut)

_extract_shortcut = QShortcut(QKeySequence("Alt+X"), mw)
_extract_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(_extract_shortcut.activated, _extract_card)
_register_shortcut_action("extract_card", _extract_shortcut)

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

    if source_mode in ("youtube", "vimeo"):
        url = resolve_video_url_for_embed(dlg.video_url)
        if not url:
            showInfo("Please enter a video URL.")
            return
        if not is_supported_video_url(url):
            showInfo("Could not find a valid YouTube or Vimeo URL.")
            return
        title = dlg.title or url
        max_height = dlg.download_max_height
        original_quality = dlg.download_original_quality
    else:
        url = ""
        local_path = dlg.local_video_path
        if not local_path:
            showInfo("Please choose a local video file.")
            return
        if not os.path.isfile(local_path):
            showInfo("Selected local video file does not exist.")
            return
        title = dlg.title or os.path.splitext(os.path.basename(local_path))[0]
        max_height = None
        original_quality = False
        local_encode_mode = dlg.local_encode_mode

    def _add_card(local_relpath: str = "", youtube_url: str = url) -> bool:
        try:
            add_video_card(
                mw.col,
                youtube_url,
                title,
                deck_name=deck_name,
                tags=tags,
                local_video_file=local_relpath,
            )
            mw.col.reset()
            if local_relpath:
                tooltip(f"Video card '{title}' added to {deck_name} (local copy ready).")
            else:
                tooltip(f"Video card '{title}' added to {deck_name}.")
            return True
        except Exception as e:
            showInfo(f"Failed to add video card:\n{e}")
            return False

    if source_mode == "local":
        try:
            label = (
                "Importing local video…"
                if local_encode_mode == "original"
                else "Importing and encoding local video…"
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
            mw.taskman.run_on_main(lambda p=percent, l=label: _progress_main(p, l))

        def _task():
            return import_local_video_file(
                _ADDON_DIR,
                _active_profile(),
                local_path,
                encode_mode=local_encode_mode,
                progress_cb=_progress_cb,
            )

        def _on_done(fut) -> None:
            mw.progress.finish()
            try:
                local_relpath = fut.result()
            except Exception as e:
                showInfo(f"Local video import failed:\n{e}")
                return
            _add_card(local_relpath=local_relpath, youtube_url="")

        mw.taskman.run_in_background(_task, _on_done)
        return

    if not dlg.download_locally:
        _add_card()
        return

    try:
        label = (
            "Downloading original-quality video…"
            if original_quality
            else "Downloading and compressing video…"
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
        mw.taskman.run_on_main(lambda p=percent, l=label: _progress_main(p, l))

    def _task():
        return download_and_compress_video(
            _ADDON_DIR,
            _active_profile(),
            url,
            overwrite=(max_height is not None) or original_quality,
            progress_cb=_progress_cb,
            max_height=max_height,
            original_quality=original_quality,
        )

    def _on_done(fut) -> None:
        mw.progress.finish()
        try:
            local_relpath = fut.result()
        except Exception as e:
            showInfo(f"Video download/compression failed:\n{e}")
            return
        _add_card(local_relpath=local_relpath)

    mw.taskman.run_in_background(_task, _on_done)


def addWritingFunction() -> None:
    """Incremento -> Add Content -> Add to Markdown"""
    from .frontend.add_writing_dialog import AddWritingDialog

    deck_names = [d.name for d in mw.col.decks.all_names_and_ids()]
    dlg = AddWritingDialog(deck_names, default_deck="Topics", parent=mw)
    if not dlg.exec():
        return

    title = dlg.title.strip()
    if not title:
        showInfo("Please enter a title.")
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
        tooltip(f"Markdown card '{title}' added to {dlg.deck_name}.")
    except Exception as e:
        showInfo(f"Failed to add markdown card:\n{e}")


def addLocalFileFunction() -> None:
    """Incremento -> Add Content -> Add Local File"""
    from .frontend.add_local_file_dialog import AddLocalFileDialog

    deck_names = [d.name for d in mw.col.decks.all_names_and_ids()]
    dlg = AddLocalFileDialog(deck_names, default_deck="Topics", parent=mw)
    if not dlg.exec():
        return

    source_path = dlg.source_path
    if not source_path:
        showInfo("Please choose a local file.")
        return
    if not os.path.isfile(source_path):
        showInfo("Selected local file does not exist.")
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
        tooltip(f"Local file card '{title}' added to {dlg.deck_name}.")
    except Exception as e:
        showInfo(f"Failed to add local file card:\n{e}")


def addWebpageFunction() -> None:
    from .frontend.webpage_dialog import WebpageToPdfDialog
    from .backend.pdf_manager import add_pdf_card

    dlg = WebpageToPdfDialog(mw)
    if not dlg.exec():
        return
    try:
        add_pdf_card(
            _ADDON_DIR,
            mw.col,
            dlg.pdf_path,
            dlg.title_text,
            tags=dlg.tags_to_apply,
            metadata=build_incremento_metadata(
                source_type="Web",
                source_title=dlg.title_text,
                source_link=dlg.source_url or "",
            ),
        )
        showInfo(f'PDF card "{dlg.title_text}" added to the Topics deck.')
    except Exception as e:
        showInfo(f"Failed to import webpage as PDF:\n{e}")


def reindexPdfTextFunction() -> None:
    try:
        note_ids = mw.col.find_notes(f'note:"{PDF_NOTE_TYPE}"')
    except Exception as e:
        showInfo(f"Could not list PDF cards:\n{e}")
        return

    if not note_ids:
        showInfo("No PDF cards found to reindex.")
        return

    indexed = 0
    skipped = 0  # file missing or no text
    failed: list[tuple[str, str]] = []
    from .backend.pdf_manager import get_pdf_dir
    pdf_dir = get_pdf_dir()

    mw.progress.start(label="Reindexing PDF text…", immediate=True)
    try:
        total = len(note_ids)
        for i, nid in enumerate(note_ids, start=1):
            try:
                mw.progress.update(label=f"({i}/{total}) Reindexing PDF text…")
            except Exception:
                pass

            try:
                note = mw.col.get_note(nid)
                filename = note["PDF_Filename"]
                pdf_path = os.path.join(pdf_dir, filename)
                if not os.path.exists(pdf_path):
                    skipped += 1
                    continue
                page_texts = extract_pdf_pages_text(pdf_path)
                if not any(page_texts):
                    skipped += 1
                    continue
                for cid in mw.col.find_cards(f"nid:{nid}"):
                    replace_pdf_text_index(_ADDON_DIR, _active_profile(), cid, page_texts)
                indexed += 1
            except Exception as e:
                failed.append((str(nid), str(e)))
    finally:
        mw.progress.finish()

    lines = [f"PDF text reindex complete.\n"]
    lines.append(f"Indexed:  {indexed}")
    lines.append(f"Skipped (no text / missing file):  {skipped}")
    if failed:
        lines.append(f"Errors:   {len(failed)}")
        for nid_str, msg in failed[:10]:
            lines.append(f"  • nid:{nid_str}: {msg}")
        if len(failed) > 10:
            lines.append(f"  …and {len(failed) - 10} more")
    showInfo("\n".join(lines))


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
        showInfo("No eligible cards found.")
        return

    missing_dep = tesseract_ready_message()
    if missing_dep:
        showInfo(f"Tesseract OCR is required for this utility.\n\n{missing_dep}")
        return

    media_dir = ""
    try:
        media_dir = mw.col.media.dir()
    except Exception as exc:
        showInfo(f"Could not access Anki media directory:\n{exc}")
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
                mw.progress.update(label=f"({idx}/{total}) {label}")
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

    lines = [f"{label} complete.\n"]
    lines.append(f"Scanned notes: {scanned}")
    lines.append(f"Updated OCR text: {updated}")
    lines.append(f"Skipped special note types: {skipped_special}")
    lines.append(f"Notes without images: {no_images}")
    lines.append(f"Missing image files: {missing_images}")
    if failures:
        lines.append(f"Errors: {len(failures)}")
        for msg in failures[:10]:
            lines.append(f"  • {msg}")
        if len(failures) > 10:
            lines.append(f"  …and {len(failures) - 10} more")
    showInfo("\n".join(lines))


def _rebuild_ocr_cache_for_note_ids(note_ids: list[int], *, label: str) -> None:
    from .backend.image_ocr import rebuild_note_ocr_index_from_field, supported_image_ocr_note

    if not note_ids:
        showInfo("No eligible cards found.")
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
                mw.progress.update(label=f"({idx}/{total}) {label}")
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

    lines = [f"{label} complete.\n"]
    lines.append(f"Rebuilt notes: {rebuilt}")
    lines.append(f"Blank OCR fields: {blank}")
    lines.append(f"Skipped special note types: {skipped_special}")
    if failures:
        lines.append(f"Errors: {len(failures)}")
        for msg in failures[:10]:
            lines.append(f"  • {msg}")
        if len(failures) > 10:
            lines.append(f"  …and {len(failures) - 10} more")
    showInfo("\n".join(lines))


def ocrImageTextFunction() -> None:
    _run_note_ocr_scan(
        _ocr_note_ids_for_card_ids(),
        label="OCR image text",
    )


def reindexImageOcrCacheFunction() -> None:
    _rebuild_ocr_cache_for_note_ids(
        _ocr_note_ids_for_card_ids(),
        label="Reindex OCR search cache",
    )


def _ocr_browser_selection(browser) -> None:
    card_ids = _browser_selected_incremento_card_ids(browser)
    if not card_ids:
        showInfo("Select one or more Browser rows first.")
        return
    _run_note_ocr_scan(
        _ocr_note_ids_for_card_ids(card_ids),
        label="OCR image text",
    )


def _show_browser_hidden_fields(browser) -> None:
    card_ids = _browser_selected_incremento_card_ids(browser)
    if not card_ids:
        showInfo("Select one or more Browser rows first.")
        return

    note_ids = _ocr_note_ids_for_card_ids(card_ids)
    if not note_ids:
        showInfo("No notes found for the selected Browser rows.")
        return

    chunks: list[str] = []
    for note_id in note_ids:
        try:
            note = mw.col.get_note(int(note_id))
            model = mw.col.models.get(note.mid)
            model_name = str((model or {}).get("name") or "Note").strip() or "Note"
        except Exception as exc:
            chunks.append(f"Note {note_id}\nCould not load note: {exc}")
            continue

        title = ""
        try:
            title = str((list(getattr(note, "fields", []) or [""])[:1] or [""])[0] or "").strip()
        except Exception:
            title = ""
        header = f"Note {note_id} · {model_name}"
        if title:
            header += f"\nTitle: {title}"

        rows = hidden_field_values(note)
        if not rows:
            body = "No Incremento hidden fields exist on this note."
        else:
            lines: list[str] = []
            for field_name in INCREMENTO_HIDDEN_FIELDS:
                match = next((value for name, value in rows if name == field_name), None)
                if match is None:
                    continue
                value_text = str(match or "").strip()
                lines.append(f"{field_name}:\n{value_text or '(empty)'}")
            body = "\n\n".join(lines) if lines else "No Incremento hidden fields exist on this note."
        chunks.append(f"{header}\n\n{body}")

    dlg = QDialog(mw)
    dlg.setWindowTitle("Incremento Hidden Fields")
    dlg.resize(860, 620)
    layout = QVBoxLayout(dlg)
    browser = QTextBrowser(dlg)
    browser.setReadOnly(True)
    browser.setOpenExternalLinks(True)
    separator = "\n\n" + ("-" * 72) + "\n\n"
    browser.setPlainText(separator.join(chunks))
    layout.addWidget(browser, 1)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dlg)
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
    return (
        f"Stale progress rows removed: {total}\n"
        f"• PDF: {pdf_n}\n"
        f"• Video: {video_n}\n"
        f"• Web: {web_n}"
    )


def _format_pruned_document_text_index_summary(counts: dict[str, int]) -> str:
    pdf_n = int(counts.get("pdf_text_index", 0) or 0)
    epub_n = int(counts.get("epub_text_index", 0) or 0)
    total = int(counts.get("document_text_index_total", 0) or 0)
    if total <= 0:
        return ""
    return (
        f"Stale search index rows removed: {total}\n"
        f"• PDF pages: {pdf_n}\n"
        f"• EPUB sections: {epub_n}"
    )


def _format_pruned_ocr_summary(counts: dict[str, int]) -> str:
    missing_note = int(counts.get("note_ocr_index_missing_note", 0) or 0)
    missing_card = int(counts.get("note_ocr_index_missing_card", 0) or 0)
    total = int(counts.get("note_ocr_index_total", 0) or 0)
    if total <= 0:
        return ""
    return (
        f"Stale OCR cache rows removed: {total}\n"
        f"• Missing notes: {missing_note}\n"
        f"• Missing cards: {missing_card}"
    )


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
        showInfo(f"Could not scan non-active profile artifacts:\n{e}")
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
        showInfo(
            "No deletable cross-profile artifacts detected.\n\n"
            "Nothing is safe to delete without affecting some profile."
        )
        return

    profile_name = _current_profile_name()
    total_bytes = pdf_bytes + video_bytes
    total_str = (
        f"{total_bytes / 1_048_576:.1f} MB"
        if total_bytes >= 1_048_576
        else f"{total_bytes // 1024} KB"
    )

    lines = [
        f"Active profile: {profile_name}",
        "",
        "The following data is not referenced by this profile and may belong",
        "to another profile (or be truly orphaned):",
        "",
        f"• PDF files: {len(orphan_pdfs)}",
        f"• Video files: {len(orphan_videos)}",
        f"• Progress rows: {stale_total} (PDF {stale_counts.get('pdf_progress', 0)}, "
        f"Video {stale_counts.get('video_progress', 0)}, Web {stale_counts.get('web_progress', 0)})",
        f"• Search index rows: {stale_text_index_total} (PDF {stale_text_index_counts.get('pdf_text_index', 0)}, "
        f"EPUB {stale_text_index_counts.get('epub_text_index', 0)})",
        f"• OCR cache rows: {stale_ocr_total} (missing notes {stale_ocr_counts.get('note_ocr_index_missing_note', 0)}, "
        f"missing cards {stale_ocr_counts.get('note_ocr_index_missing_card', 0)})",
    ]
    if protected_pdfs:
        lines.append(f"• Skipped PDF files tied to other profile(s): {len(protected_pdfs)}")
    if protected_videos:
        lines.append(f"• Skipped video files tied to other profile(s): {len(protected_videos)}")
    if orphan_pdfs:
        lines.append(f"• PDF folder: {pdf_dir}")
    if orphan_videos:
        lines.append(f"• Video folder: {videos_dir}")
    if total_bytes > 0:
        lines.append(f"• Recoverable disk space: {total_str}")
    if protected_pdfs:
        lines.append("")
        lines.append("Skipped PDFs (kept):")
        preview = protected_pdfs[:6]
        for fname in preview:
            profs = ", ".join(pdf_refs_map.get(fname, []))
            lines.append(f"  - {fname}  (profiles: {profs})")
        if len(protected_pdfs) > len(preview):
            lines.append(f"  …and {len(protected_pdfs) - len(preview)} more")
    if protected_videos:
        lines.append("")
        lines.append("Skipped videos (kept):")
        preview = protected_videos[:6]
        for fname in preview:
            profs = ", ".join(video_refs_map.get(fname, []))
            lines.append(f"  - {fname}  (profiles: {profs})")
        if len(protected_videos) > len(preview):
            lines.append(f"  …and {len(protected_videos) - len(preview)} more")
    lines.append("")
    lines.append("Delete these now?")

    from aqt.utils import askUser
    if not askUser("\n".join(lines), title="Clean Non-Active Profile Data"):
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
        errors.append(f"Rows: {e}")
    try:
        pruned_text_index_counts = _prune_stale_document_text_index_rows()
    except Exception as e:
        pruned_text_index_counts = {
            "pdf_text_index": 0,
            "epub_text_index": 0,
            "document_text_index_total": 0,
        }
        errors.append(f"Search index: {e}")
    try:
        pruned_ocr_counts = _prune_stale_ocr_rows()
    except Exception as e:
        pruned_ocr_counts = {
            "note_ocr_index_missing_note": 0,
            "note_ocr_index_missing_card": 0,
            "note_ocr_index_total": 0,
        }
        errors.append(f"OCR cache: {e}")

    summary = [
        f"Deleted PDF files: {deleted_pdfs}/{len(orphan_pdfs)}",
        f"Deleted video files: {deleted_videos}/{len(orphan_videos)}",
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
        summary.append(f"Potential recovered space: {total_str}")
    if errors:
        summary.append("")
        summary.append("Errors:")
        summary.extend([f"• {e}" for e in errors[:20]])
        if len(errors) > 20:
            summary.append(f"• …and {len(errors) - 20} more")

    showInfo("\n".join(summary))


def cleanupStaleProgressFunction() -> None:
    """Delete stale progress, search-index, and OCR rows for removed cards/notes."""
    try:
        counts = _prune_stale_progress_rows()
        text_index_counts = _prune_stale_document_text_index_rows()
        ocr_counts = _prune_stale_ocr_rows()
    except Exception as e:
        showInfo(f"Could not clean stale Incremento rows:\n{e}")
        return

    summary = _format_pruned_progress_summary(counts)
    text_index_summary = _format_pruned_document_text_index_summary(text_index_counts)
    ocr_summary = _format_pruned_ocr_summary(ocr_counts)
    chunks = [chunk for chunk in (summary, text_index_summary, ocr_summary) if chunk]
    if chunks:
        showInfo("\n\n".join(chunks))
        return
    showInfo("No stale progress, search-index, or OCR cache rows found.")


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
        showInfo(f"Could not read PDF directory:\n{e}")
        return

    if not disk_files:
        showInfo(f"No PDF files found in {pdf_dir}.")
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
        showInfo(f"Could not query PDF cards:\n{e}")
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
        msg = (
            f"No deletable orphaned PDFs found.\n\n"
            f"{len(disk_files)} file(s) on disk; none are safe to delete."
        )
        if protected:
            msg += (
                f"\n\nSkipped {len(protected)} file(s) because they are "
                "referenced by another profile."
            )
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

    lines = [f"Found {len(deletable)} deletable orphaned PDF(s):\n"]
    total_bytes = 0
    for fname in deletable:
        fpath = os.path.join(pdf_dir, fname)
        try:
            total_bytes += os.path.getsize(fpath)
        except OSError:
            pass
        lines.append(f"• {fname}  ({_fmt_size(fpath)})")
    if protected:
        lines.append(f"\nSkipped {len(protected)} file(s) tied to other profile(s).")
        preview = protected[:8]
        for fname in preview:
            profs = ", ".join(refs_map.get(fname, []))
            lines.append(f"  - {fname}  (profiles: {profs})")
        if len(protected) > len(preview):
            lines.append(f"  …and {len(protected) - len(preview)} more")
    total_str = f"{total_bytes / 1_048_576:.1f} MB" if total_bytes >= 1_048_576 else f"{total_bytes // 1024} KB"
    lines.append(f"\nTotal: {total_str}")
    lines.append("\nDelete these files?")

    from aqt.utils import askUser
    if not askUser("\n".join(lines), title="Clean Up Orphaned PDFs"):
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
        msg = f"Deleted {deleted} orphaned PDF file(s).\nRecovered {total_str}."
        if protected:
            msg += f"\nSkipped {len(protected)} file(s) tied to other profile(s)."
        if cleanup_summaries:
            msg += f"\n\n{'\n\n'.join(cleanup_summaries)}"
        showInfo(msg)
    else:
        showInfo(
            f"Deleted {deleted} of {len(deletable)} file(s).\n\nErrors:\n" + "\n".join(errors)
        )


def cleanupOrphanVideosFunction() -> None:
    """Delete local videos in user_files/<profile>/videos/ that no video card references."""
    videos_dir = str(_paths.get_videos_dir(_ADDON_DIR, _active_profile()))
    if not os.path.isdir(videos_dir):
        showInfo(f"No local videos found in {videos_dir}.")
        return

    try:
        disk_files = [
            f
            for f in os.listdir(videos_dir)
            if f.lower().endswith((".mp4", ".mkv", ".webm", ".mov", ".m4v"))
            and os.path.isfile(os.path.join(videos_dir, f))
        ]
    except OSError as e:
        showInfo(f"Could not read video directory:\n{e}")
        return

    if not disk_files:
        showInfo(f"No local videos found in {videos_dir}.")
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
        showInfo(f"Could not query video cards:\n{e}")
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
        msg = (
            f"No deletable orphaned local videos found.\n\n"
            f"{len(disk_files)} file(s) on disk; none are safe to delete."
        )
        if protected:
            msg += (
                f"\n\nSkipped {len(protected)} file(s) because they are "
                "referenced by another profile."
            )
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
    lines = [f"Found {len(deletable)} deletable orphaned local video file(s):\n"]
    for fname in deletable:
        fpath = os.path.join(videos_dir, fname)
        try:
            total_bytes += os.path.getsize(fpath)
        except OSError:
            pass
        lines.append(f"• {fname}  ({_fmt_size(fpath)})")
    if protected:
        lines.append(f"\nSkipped {len(protected)} file(s) tied to other profile(s).")
        preview = protected[:8]
        for fname in preview:
            profs = ", ".join(refs_map.get(fname, []))
            lines.append(f"  - {fname}  (profiles: {profs})")
        if len(protected) > len(preview):
            lines.append(f"  …and {len(protected) - len(preview)} more")
    total_str = (
        f"{total_bytes / 1_048_576:.1f} MB"
        if total_bytes >= 1_048_576
        else f"{total_bytes // 1024} KB"
    )
    lines.append(f"\nTotal: {total_str}")
    lines.append("\nDelete these files?")

    from aqt.utils import askUser
    if not askUser("\n".join(lines), title="Clean Up Orphaned Videos"):
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
        msg = f"Deleted {deleted} orphaned video file(s).\nRecovered {total_str}."
        if protected:
            msg += f"\nSkipped {len(protected)} file(s) tied to other profile(s)."
        if cleanup_summaries:
            msg += f"\n\n{'\n\n'.join(cleanup_summaries)}"
        showInfo(msg)
    else:
        showInfo(
            f"Deleted {deleted} of {len(deletable)} file(s).\n\nErrors:\n" + "\n".join(errors)
        )


def openSettingsFunction() -> None:
    cfg = mw.addonManager.getConfig(__name__) or {}
    previous_priority_direction = configured_priority_lower_is_more_important(cfg)
    note_type_names = sorted(m.name for m in mw.col.models.all_names_and_ids())
    dlg = IncrementoSettingsDialog(
        cfg.get("shortcuts") or {},
        note_type_names=note_type_names,
        current_extract_notetype=_add_card_dock_mod.configured_extract_notetype_name(cfg),
        current_extract_priority=_add_card_dock_mod.configured_extract_priority(cfg),
        current_extract_priority_multiplier=_add_card_dock_mod.configured_extract_priority_multiplier(cfg),
        current_extract_mark_topic=_add_card_dock_mod.configured_extract_mark_topic(cfg),
        current_extract_copy_source_tags=_add_card_dock_mod.configured_extract_copy_source_tags(cfg),
        current_extract_highlight_when_extracting=_pdf_dock_mod.configured_highlight_when_extracting(cfg),
        extract_source_links=_add_card_dock_mod.configured_extract_source_links(cfg),
        current_priority_lower_is_more_important=configured_priority_lower_is_more_important(cfg),
        current_show_priority_dialog_after_answer=configured_show_priority_dialog_after_answer(cfg),
        current_show_incremento_fields=configured_show_incremento_fields(cfg),
        current_remember_browser_card_scroll=configured_remember_browser_card_scroll(cfg),
        current_pdf_scroll_to_top_on_page_change=_pdf_dock_mod.configured_scroll_to_top_on_page_change(cfg),
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
        current_add_card_topic_tags=_add_card_dock_mod.configured_add_card_topic_tags(cfg),
        current_add_card_item_tags=_add_card_dock_mod.configured_add_card_item_tags(cfg),
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

    cfg["shortcuts"] = dlg.shortcuts_map
    cfg["extract_notetype"] = dlg.extract_notetype_name
    cfg["extract_priority"] = dlg.extract_priority
    cfg["extract_priority_multiplier"] = dlg.extract_priority_multiplier
    cfg["extract_mark_topic"] = dlg.extract_mark_topic
    cfg["extract_copy_source_tags"] = dlg.extract_copy_source_tags
    cfg["highlight_when_extracting"] = dlg.extract_highlight_when_extracting
    cfg["extract_source_links"] = dlg.extract_source_links
    cfg["priority_lower_is_more_important"] = dlg.priority_lower_is_more_important
    cfg["show_priority_dialog_after_answer"] = dlg.show_priority_dialog_after_answer
    cfg["show_incremento_fields"] = dlg.show_incremento_fields
    cfg["remember_browser_card_scroll"] = dlg.remember_browser_card_scroll
    cfg["pdf_scroll_to_top_on_page_change"] = dlg.pdf_scroll_to_top_on_page_change
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
    cfg["add_card_topic_tags"] = dlg.add_card_topic_tags
    cfg["add_card_item_tags"] = dlg.add_card_item_tags
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
    mw.addonManager.writeConfig(__name__, cfg)
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
            "lower numbers are more important"
            if dlg.priority_lower_is_more_important
            else "higher numbers are more important"
        )
        if askUser(
            "\n".join(
                [
                    "You changed how Incremento interprets stored priority numbers.",
                    f"New direction: {direction_label}.",
                    "",
                    "Do you also want to invert all existing stored priorities for the current profile?",
                    "This rewrites each saved priority as 100 - priority.",
                    "Example: 20 -> 80, 95 -> 5.",
                ]
            ),
            title="Invert Existing Priorities?",
        ):
            try:
                updated = invert_all_priorities(_ADDON_DIR, _active_profile())
            except Exception as exc:
                showInfo(f"Could not invert stored priorities:\n{exc}")
            else:
                tooltip(
                    f"Incremento settings updated. Inverted {updated} stored priorit{'y' if updated == 1 else 'ies'}."
                )
                return
    tooltip("Incremento settings updated.")


def _open_database_editor() -> None:
    from .frontend.sqlite_editor_dialog import SQLiteEditorDialog

    profile = _active_profile()
    mw.progress.start(label="Creating database checkpoint…", immediate=True)
    try:
        checkpoint_info = create_database_checkpoint(
            _ADDON_DIR,
            profile,
            label="sqlite_editor",
        )
    except Exception as exc:
        showInfo(f"Could not prepare the database editor:\n{exc}")
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
    showInfo(
        """
        <h2>Incremento</h2>
        <p><b>Author:</b> Paulo Baskovic</p>
        <p>
          Incremento is an Anki add-on for incremental reading and study workflows.
          It keeps long-form material and review cards in one place inside Anki.
        </p>
        <p><b>General information</b></p>
        <ul>
          <li>Add and review PDFs, webpages, videos, and writing notes.</li>
          <li>Open PDF, webpage, video, and writing docks while reviewing cards.</li>
          <li>Extract selections into new cards and keep context linked to the source.</li>
          <li>Track PDF position, highlights, video progress, and study statistics.</li>
          <li>Use the Chrome extension to send the current webpage as PDF, webpage, or writing.</li>
        </ul>
        <p><b>Disclaimer:</b> By using this add-on, you accept full responsibility for any damage, data loss, or other issues that may result from its use.</p>
        <p><b>License:</b> All rights reserved. Using, copying, modifying, or distributing this code requires prior written permission from Paulo Baskovic.</p>
        """
    )


def _ensure_settings_menu_action() -> None:
    if _menu is None:
        return
    for act in _menu.actions():
        if act.text() == "Settings":
            return

    action = QAction("Settings", mw)
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
        if act.text() == "Incremento":
            _menu = act.menu()
            menubar.update()
            return

    _menu = QMenu("Incremento", menubar)
    menubar.addMenu(_menu)

    _startAction = QAction("Start Incremental Learning", mw)
    qconnect(_startAction.triggered, learnFunction)
    _menu.addAction(_startAction)
    _register_shortcut_action("start_learning", _startAction)

    _settingsAction = QAction("Settings", mw)
    _settingsAction.setMenuRole(QAction.MenuRole.NoRole)
    qconnect(_settingsAction.triggered, openSettingsFunction)
    _menu.addAction(_settingsAction)
    _register_shortcut_action("open_settings", _settingsAction)

    _aboutAction = QAction("About", mw)
    _aboutAction.setMenuRole(QAction.MenuRole.NoRole)
    qconnect(_aboutAction.triggered, openAboutFunction)
    _menu.addAction(_aboutAction)

    _menu.addSeparator()

    _addContentMenu = QMenu("Add Content", _menu)
    _menu.addMenu(_addContentMenu)

    _addPdfAction = QAction("Add PDF", mw)
    qconnect(_addPdfAction.triggered, addPdfFunction)
    _addContentMenu.addAction(_addPdfAction)
    _register_shortcut_action("add_pdf", _addPdfAction)

    _addEpubAction = QAction("Add EPUB", mw)
    qconnect(_addEpubAction.triggered, addEpubFunction)
    _addContentMenu.addAction(_addEpubAction)
    _register_shortcut_action("add_epub", _addEpubAction)

    _addWebpageAction = QAction("Webpage to PDF", mw)
    qconnect(_addWebpageAction.triggered, addWebpageFunction)
    _addContentMenu.addAction(_addWebpageAction)
    _register_shortcut_action("webpage_to_pdf", _addWebpageAction)

    _addVideoAction = QAction("Add Video", mw)
    qconnect(_addVideoAction.triggered, addVideoFunction)
    _addContentMenu.addAction(_addVideoAction)
    _register_shortcut_action("youtube_video", _addVideoAction)

    _addWritingAction = QAction("Add to Markdown", mw)
    qconnect(_addWritingAction.triggered, addWritingFunction)
    _addContentMenu.addAction(_addWritingAction)
    _register_shortcut_action("add_writing", _addWritingAction)

    _addWebAction = QAction("Web Page", mw)
    qconnect(_addWebAction.triggered, _web_dock_mod.add_web_function)
    _addContentMenu.addAction(_addWebAction)
    _register_shortcut_action("add_web_page", _addWebAction)

    _addLocalFileAction = QAction("Add Local File", mw)
    qconnect(_addLocalFileAction.triggered, addLocalFileFunction)
    _addContentMenu.addAction(_addLocalFileAction)
    _register_shortcut_action("add_local_file", _addLocalFileAction)

    _downloadCurrentVideoAction = QAction("Download Current Video Locally", mw)
    qconnect(
        _downloadCurrentVideoAction.triggered,
        lambda _checked=False: _download_current_reviewer_video_locally(),
    )
    _menu.addAction(_downloadCurrentVideoAction)

    _configureCurrentVideoCaptionsAction = QAction("Configure Current Video Captions…", mw)
    qconnect(
        _configureCurrentVideoCaptionsAction.triggered,
        lambda _checked=False: _configure_current_reviewer_video_captions(),
    )
    _menu.addAction(_configureCurrentVideoCaptionsAction)

    _knowledgeTreeAction = QAction("Open Knowledge tree", mw)
    qconnect(_knowledgeTreeAction.triggered, lambda _checked=False: _open_knowledge_tree())
    _menu.addAction(_knowledgeTreeAction)
    _register_shortcut_action("open_knowledge_tree", _knowledgeTreeAction)

    _revealCurrentTreeAction = QAction("Reveal Current Card In Knowledge Tree", mw)
    qconnect(
        _revealCurrentTreeAction.triggered,
        lambda _checked=False: _reveal_current_card_in_knowledge_tree(),
    )
    _menu.addAction(_revealCurrentTreeAction)
    _register_shortcut_action("reveal_current_knowledge_tree", _revealCurrentTreeAction)

    _goToParentTreeAction = QAction("Go To Parent In Knowledge Tree", mw)
    qconnect(
        _goToParentTreeAction.triggered,
        lambda _checked=False: _go_to_parent_in_knowledge_tree(),
    )
    _menu.addAction(_goToParentTreeAction)
    _register_shortcut_action("go_to_parent_knowledge_tree", _goToParentTreeAction)

    _menu.addSeparator()

    _timerToggleAction = QAction("Show Focus Timer", mw)
    _timerToggleAction.setCheckable(True)
    _timerToggleAction.setChecked(True)  # default; corrected by _build_timer_toolbar

    def _on_timer_toggle(checked: bool) -> None:
        if _timer_mod._timer_toolbar is not None:
            _timer_mod._timer_toolbar.setVisible(checked)
        cfg = mw.addonManager.getConfig(__name__) or {}
        cfg["show_timer"] = checked
        mw.addonManager.writeConfig(__name__, cfg)

    qconnect(_timerToggleAction.triggered, _on_timer_toggle)
    _menu.addAction(_timerToggleAction)
    _register_shortcut_action("toggle_focus_timer", _timerToggleAction)

    _menu.addSeparator()

    _utilsMenu = QMenu("Utils", _menu)
    _menu.addMenu(_utilsMenu)

    def _check_deps_manual() -> None:
        from .backend.deps import show_setup_dialog
        show_setup_dialog(mw, force=True)

    _checkDepsAction = QAction("Check Dependencies…", mw)
    qconnect(_checkDepsAction.triggered, _check_deps_manual)
    _utilsMenu.addAction(_checkDepsAction)

    _utilsMenu.addSeparator()

    _reindexPdfTextAction = QAction("Reindex PDF Text (Existing Cards)", mw)
    qconnect(_reindexPdfTextAction.triggered, reindexPdfTextFunction)
    _utilsMenu.addAction(_reindexPdfTextAction)

    _ocrImageTextAction = QAction("OCR Image Text (Existing Cards)…", mw)
    qconnect(_ocrImageTextAction.triggered, ocrImageTextFunction)
    _utilsMenu.addAction(_ocrImageTextAction)

    _reindexImageOcrCacheAction = QAction("Reindex OCR Search Cache (From Hidden Field)", mw)
    qconnect(_reindexImageOcrCacheAction.triggered, reindexImageOcrCacheFunction)
    _utilsMenu.addAction(_reindexImageOcrCacheAction)

    _cleanupNonActiveProfileDataAction = QAction("Clean Non-Active Profile Data…", mw)
    qconnect(_cleanupNonActiveProfileDataAction.triggered, cleanupNonActiveProfileDataFunction)
    _utilsMenu.addAction(_cleanupNonActiveProfileDataAction)

    _utilsMenu.addSeparator()

    _cleanupOrphanPdfsAction = QAction("Clean Up Orphaned PDF Files…", mw)
    qconnect(_cleanupOrphanPdfsAction.triggered, cleanupOrphanPdfsFunction)
    _utilsMenu.addAction(_cleanupOrphanPdfsAction)

    _cleanupOrphanVideosAction = QAction("Clean Up Orphaned Video Files…", mw)
    qconnect(_cleanupOrphanVideosAction.triggered, cleanupOrphanVideosFunction)
    _utilsMenu.addAction(_cleanupOrphanVideosAction)

    _cleanupStaleProgressAction = QAction("Clean Up Stale Progress / Search Index / OCR Rows…", mw)
    qconnect(_cleanupStaleProgressAction.triggered, cleanupStaleProgressFunction)
    _utilsMenu.addAction(_cleanupStaleProgressAction)

    _statsAction = QAction("Statistics", mw)
    qconnect(_statsAction.triggered, showStatsFunction)
    _menu.addAction(_statsAction)
    _register_shortcut_action("statistics", _statsAction)

    _quickOpenPdfAction = QAction("Quick Open Content", mw)
    qconnect(_quickOpenPdfAction.triggered, _open_pdf_quick_jump)
    _menu.addAction(_quickOpenPdfAction)
    _register_shortcut_action("quick_open_pdf", _quickOpenPdfAction)

    _searchAllAction = QAction("Search ALL", mw)
    qconnect(_searchAllAction.triggered, _open_search_all)
    _menu.addAction(_searchAllAction)
    _register_shortcut_action("search_all", _searchAllAction)

    _exportAction = QAction("Export Full Backup", mw)
    qconnect(_exportAction.triggered, exportFunction)
    _menu.addAction(_exportAction)
    _register_shortcut_action("export_user_data", _exportAction)

    _apply_shortcuts_from_config()
    _ensure_settings_menu_action()
    menubar.update()


# Build menu first (sets _timerToggleAction), then build timer toolbar which uses it.
gui_hooks.main_window_did_init.append(_build_incremento_menu)
gui_hooks.main_window_did_init.append(_build_timer_toolbar)
gui_hooks.state_did_change.append(lambda *_: _build_incremento_menu())
gui_hooks.operation_did_execute.append(_sync_ocr_index_for_open_editor_notes)
gui_hooks.browser_will_show.append(_prune_incremento_hidden_browser_active_columns)
gui_hooks.editor_did_load_note.append(_hide_incremento_hidden_fields_in_editor)
gui_hooks.browser_did_fetch_columns.append(_filter_incremento_hidden_browser_columns)
gui_hooks.browser_will_show_context_menu.append(_on_browser_context_menu)
