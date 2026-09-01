"""Privacy-safe Incremento diagnostics and support-bundle export.

This module intentionally accepts only a small, typed event vocabulary.  It
never stores arbitrary strings, card/note identifiers, names, paths, URLs, tag
values, card text, or exception messages.  Export revalidates every persisted
event instead of copying the log files verbatim.
"""

from __future__ import annotations

import datetime as _datetime
import hashlib
import json
import math
import os
import platform
import queue
import re
import secrets
import sqlite3
import tempfile
import threading
import time
import zipfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

try:
    from .paths import get_db_path, get_diagnostic_events_path
except ImportError:
    from paths import get_db_path, get_diagnostic_events_path


DIAGNOSTIC_SCHEMA_VERSION = 1
SUPPORT_BUNDLE_SCHEMA_VERSION = 1
MAX_LOG_BYTES = 1_000_000
MAX_LOG_FILES = 3
MAX_EXPORTED_EVENTS = 5_000
MAX_PENDING_EVENTS = 2_048
RECORDER_FLUSH_TIMEOUT_SECONDS = 5.0

_SAFE_RUN_ID_RE = re.compile(r"^[a-f0-9]{12}$")
_SAFE_CONFIG_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,80}$")
_SAFE_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_SAFE_DURATION_RE = re.compile(r"^[1-9]\d{0,3}[mhd]$")
_SAFE_VERSION_RE = re.compile(r"^(?:unknown|[vV]?\d[0-9A-Za-z_.+()-]{0,39})$")

_SAFE_ERROR_TYPES = {
    "AssertionError",
    "AttributeError",
    "CancelledError",
    "ConnectionError",
    "DatabaseError",
    "Exception",
    "FileNotFoundError",
    "ImportError",
    "IndexError",
    "IntegrityError",
    "IOError",
    "JSONDecodeError",
    "KeyError",
    "MemoryError",
    "ModuleNotFoundError",
    "OperationalError",
    "OSError",
    "OverflowError",
    "PermissionError",
    "ProgrammingError",
    "RuntimeError",
    "TimeoutError",
    "TypeError",
    "UnicodeError",
    "UnknownError",
    "ValueError",
}

_UI_STATES = {
    "deckBrowser",
    "overview",
    "review",
    "resetRequired",
    "profileManager",
    "startup",
    "sync",
    "unknown",
}
_REFILL_REASONS = {"card_answered", "session_started", "other"}
_OPERATION_SCOPES = {"incremento", "anki", "other", "none"}
_SAFE_EVENT_ENUMS = {
    "action_stage": {
        "requested", "store", "bury", "timer", "advance", "completed", "other",
    },
    "content_kind": {
        "pdf", "epub", "video", "web", "writing", "local_file", "topic", "item", "other",
    },
    "explicit_source": {
        "media_review", "pdf_due_review", "epub_due_review", "quick_open", "selected_cards", "other",
    },
    "explicit_stage": {"selection", "deck_build", "activation", "review", "other"},
    "media_card_kind": {"both", "topics", "items", "other"},
    "media_order": {
        "attached", "media_position", "created_oldest", "created_newest",
        "due_first", "interval_shortest", "interval_longest", "random", "other",
    },
    "media_range": {"all", "to_current", "other"},
    "media_state": {"all", "due", "other"},
    "media_tree_scope": {"direct", "nested", "other"},
    "refill_outcome": {
        "added", "window_full", "exhausted", "duplicate_queue",
        "missing_deck", "closed", "disabled", "other",
    },
    "refill_skip_reason": {
        "advance_not_deferred", "already_pending", "closed", "disabled", "other",
    },
    "review_action": {"topic_postpone", "item_skip", "other"},
    "schedule_mode": {"minimum_cadence", "fixed_repeat", "one_time", "none", "other"},
    "schedule_reason": {
        "preview", "minimum_already_met", "revlog_snapshot", "no_rule", "other",
    },
    "schedule_stage": {
        "prepare", "revlog_snapshot", "load_state", "resolve", "undo_step",
        "revlog", "apply", "commit", "restore", "reconcile", "other",
    },
    "session_phase": {
        "selection_started", "selection_finished", "deck_build_started",
        "deck_build_finished", "activation_scheduled", "activation_started",
        "entered_review",
    },
    "session_stop_reason": {"no_cards", "activation_failed", "other"},
    "topic_choice": {"more", "same", "less"},
}

_EVENT_SCHEMAS: dict[str, dict[str, str]] = {
    "addon_started": {
        "anki_version": "version",
        "addon_version": "version",
        "enabled_addons": "count",
    },
    "profile_opened": {},
    "profile_closing": {},
    "anki_compatibility_checked": {
        "required_methods": "count",
        "missing_methods": "count",
        "private_scheduler_available": "bool",
        "custom_next_card_supported": "bool",
    },
    "profile_reconciled": {
        "stale_rows": "count",
        "repaired_links": "count",
        "pending_recovered": "count",
        "pending_rolled_back": "count",
    },
    "profile_reconciliation_failed": {"error_type": "token"},
    "ui_state_changed": {"from_state": "state", "to_state": "state"},
    "anki_operation_completed": {
        "scope": "operation_scope",
        "browser_sidebar_changed": "bool",
        "browser_table_changed": "bool",
        "card_changed": "bool",
        "note_changed": "bool",
        "note_text_changed": "bool",
        "deck_changed": "bool",
        "deck_config_changed": "bool",
        "config_changed": "bool",
        "notetype_changed": "bool",
        "schema_changed": "bool",
        "study_queues_changed": "bool",
        "tag_changed": "bool",
    },
    "review_question_shown": {
        "card_type": "card_state",
        "queue": "card_state",
        "interval_days": "interval",
        "content_kind": "content_kind",
    },
    "review_ui_probe": {
        "main_window_enabled": "bool",
        "reviewer_web_enabled": "bool",
        "active_modal": "bool",
        "active_popup": "bool",
        "progress_levels": "count",
        "progress_window_visible": "bool",
        "background_operations": "count",
    },
    "review_answered": {
        "rating": "rating",
        "card_type": "card_state",
        "queue": "card_state",
        "interval_days": "interval",
        "content_kind": "content_kind",
    },
    "incremento_session_requested": {
        "branch_scoped": "bool",
        "target_count": "count",
        "auto_refill": "bool",
        "include_new": "bool",
        "include_learning": "bool",
        "include_due": "bool",
    },
    "incremento_session_build_succeeded": {
        "selected_count": "count",
        "auto_refill": "bool",
    },
    "incremento_session_build_failed": {"error_type": "token"},
    "incremento_session_phase": {
        "phase": "session_phase",
        "selected_count": "count",
    },
    "incremento_session_started": {
        "selected_count": "count",
        "window_size": "count",
        "auto_refill": "bool",
        "preserve_order": "bool",
    },
    "incremento_session_card_answered": {
        "rating": "rating",
        "reviewed_count": "count",
        "selected_count": "count",
    },
    "incremento_session_answer_tracking_failed": {"error_type": "token"},
    "incremento_session_exit_tracking_failed": {"error_type": "token"},
    "incremento_session_not_started": {"reason": "session_stop_reason"},
    "incremento_session_activation_failed": {"error_type": "token"},
    "incremento_session_refill_requested": {"reason": "refill_reason"},
    "incremento_session_refill_finished": {
        "live_count": "count",
        "added_count": "count",
        "outcome": "refill_outcome",
    },
    "incremento_session_refill_skipped": {"reason": "refill_skip_reason"},
    "incremento_session_refill_failed": {
        "reason": "refill_reason",
        "error_type": "token",
    },
    "incremento_session_ended": {
        "reviewed_count": "count",
        "selected_count": "count",
        "refill_pending": "bool",
    },
    "explicit_review_requested": {
        "source": "explicit_source",
        "content_kind": "content_kind",
        "requested_count": "count",
        "preserve_order": "bool",
        "media_order": "media_order",
        "media_card_kind": "media_card_kind",
        "media_tree_scope": "media_tree_scope",
        "media_range": "media_range",
        "media_state": "media_state",
        "limit": "count",
    },
    "media_review_inspection_started": {"content_kind": "content_kind"},
    "media_review_inspection_finished": {
        "content_kind": "content_kind",
        "candidate_count": "count",
    },
    "media_review_inspection_failed": {
        "content_kind": "content_kind",
        "error_type": "token",
    },
    "explicit_review_build_started": {
        "source": "explicit_source",
        "content_kind": "content_kind",
    },
    "explicit_review_build_finished": {
        "source": "explicit_source",
        "content_kind": "content_kind",
        "requested_count": "count",
        "selected_count": "count",
        "unavailable_count": "count",
    },
    "explicit_review_started": {
        "source": "explicit_source",
        "content_kind": "content_kind",
        "selected_count": "count",
    },
    "explicit_review_ended": {
        "source": "explicit_source",
        "content_kind": "content_kind",
    },
    "explicit_review_failed": {
        "source": "explicit_source",
        "content_kind": "content_kind",
        "stage": "explicit_stage",
        "error_type": "token",
    },
    "topic_schedule_applied": {
        "choice": "topic_choice",
        "anki_rating": "rating",
        "previous_interval_days": "interval",
        "requested_interval_days": "interval",
        "scheduled_interval_days": "interval",
        "previous_a_factor": "factor",
        "new_a_factor": "factor",
        "custom_mode": "schedule_mode",
    },
    "topic_schedule_skipped": {
        "choice": "topic_choice",
        "reason": "schedule_reason",
    },
    "topic_schedule_failed": {
        "choice": "topic_choice",
        "stage": "schedule_stage",
        "error_type": "token",
        "restore_failed": "bool",
    },
    "topic_schedule_reconcile_failed": {"error_type": "token"},
    "custom_schedule_applied": {
        "mode": "schedule_mode",
        "previous_interval_days": "interval",
        "scheduled_interval_days": "interval",
        "consumed_one_time": "bool",
    },
    "custom_schedule_skipped": {
        "mode": "schedule_mode",
        "reason": "schedule_reason",
        "current_interval_days": "interval",
        "target_interval_days": "interval",
    },
    "custom_schedule_failed": {
        "mode": "schedule_mode",
        "stage": "schedule_stage",
        "error_type": "token",
        "restore_failed": "bool",
    },
    "custom_schedule_reconcile_failed": {"error_type": "token"},
    "review_action_completed": {
        "action": "review_action",
        "stage": "action_stage",
    },
    "review_action_failed": {
        "action": "review_action",
        "stage": "action_stage",
        "error_type": "token",
    },
    "support_bundle_requested": {},
    "support_bundle_created": {
        "event_count": "count",
        "bundle_bytes": "count",
    },
    "support_bundle_failed": {"error_type": "token"},
}

_KNOWN_CONFIG_KEYS = {
    "add_card_item_tags",
    "add_card_topic_tags",
    "auto_create_topics_deck",
    "auto_create_topics_deck_profiles",
    "auto_timer_card_types",
    "auto_timer_enabled",
    "auto_timer_minutes",
    "auto_timer_tags",
    "custom_schedule_default_mode",
    "custom_schedule_presets",
    "config_schema_version",
    "default_topic_a_factor",
    "deps_notified",
    "dialog",
    "extract_copy_source_tags",
    "extract_mark_topic",
    "extract_notetype",
    "extract_priority",
    "extract_priority_multiplier",
    "extract_source_links",
    "highlight_when_extracting",
    "item_skip_enabled",
    "item_skip_minutes",
    "onboarding_completed_version",
    "pdf_highlight_extract_field",
    "pin_hash",
    "prefer_web_card_resume_in_original_page",
    "priority_lower_is_more_important",
    "profiles",
    "remember_browser_card_scroll",
    "scheduler_scope",
    "scheduler_presets",
    "search_all_filter_pdf_content",
    "search_all_search_while_typing",
    "shortcuts",
    "show_incremento_fields",
    "show_priority_dialog_after_answer",
    "show_timer",
    "timer_completion_beep",
    "topic_card_tags",
    "topic_card_types",
    "topic_less_adjustment_percent",
    "topic_maximum_interval_days",
    "topic_more_adjustment_percent",
    "topic_postpone_enabled",
    "topic_postpone_minutes",
    "topic_postpone_mode",
    "track_web_window_with_extension",
    "use_fail_pass_on_items",
    "writing_backup_tiers",
    "writing_backups_enabled",
    "writing_external_app",
    "writing_external_app_custom_path",
    "writing_focus_mode",
    "writing_highlight_current_line",
    "writing_preview_visible",
    "writing_progress_default_scope",
    "writing_progress_visible",
    "writing_restore_bookmark",
    "writing_word_count_mode",
    "writing_wrap_enabled",
}

_SAFE_NESTED_CONFIG_KEYS = {
    "allow_content_tag_fallback",
    "auto_refill_session",
    "content_type_rows",
    "content_types",
    "day_end_time",
    "enabled",
    "enforce_priority",
    "epub",
    "group",
    "include_due",
    "include_learning",
    "include_new",
    "interval_unit",
    "interval_value",
    "items_filter",
    "kind",
    "label",
    "local_file",
    "locked",
    "main_groups",
    "main_locks",
    "mode",
    "no_tags_checked",
    "order",
    "parent",
    "pdf",
    "pdf_epub",
    "pdf_slider",
    "phase_order",
    "phases_enabled",
    "preserve_order",
    "priority",
    "priority_order",
    "prioritized_tags_first",
    "prioritized_tags_mode",
    "priority_order_enabled",
    "priority_order_entries",
    "priority_slider",
    "random_slider",
    "scheduler_scope",
    "selected_profile",
    "session_card_count",
    "show_debug",
    "sort_order",
    "tag",
    "tag_rows",
    "tags",
    "topics",
    "topics_filter",
    "topics_slider",
    "type",
    "use_live_preview",
    "value",
    "video",
    "weight",
    "web",
    "webpage",
    "writing",
    "youtube",
}

_SAFE_SHORTCUT_IDS = {
    "add_epub",
    "add_local_file",
    "add_pdf",
    "add_web_page",
    "add_writing",
    "append_tags_reviewer",
    "export_user_data",
    "extract_card",
    "go_to_parent_knowledge_tree",
    "open_knowledge_tree",
    "open_settings",
    "pdf_mark_read",
    "pdf_next_page",
    "pdf_prev_page",
    "pdf_zoom_in",
    "pdf_zoom_out",
    "quick_open_pdf",
    "reveal_current_knowledge_tree",
    "search_all",
    "search_current_document",
    "set_priority",
    "start_learning",
    "statistics",
    "toggle_focus_timer",
    "webpage_to_pdf",
    "youtube_video",
}

_SAFE_ENUM_STRINGS = {
    "all_time",
    "anki",
    "content_types",
    "content_type",
    "custom",
    "days",
    "daily",
    "epub",
    "exhaust",
    "fixed_repeat",
    "global",
    "items",
    "local_file",
    "lifetime",
    "minimum_cadence",
    "mode",
    "months",
    "obsidian",
    "one_time",
    "parent",
    "pdf",
    "pdf_epub",
    "priority",
    "random",
    "session",
    "simple",
    "tags",
    "tag",
    "timed",
    "today",
    "topics",
    "type",
    "video",
    "web",
    "webpage",
    "weeks",
    "weighted",
    "word_like",
    "writing",
    "youtube",
}

_SENSITIVE_COLLECTION_KEYS = {
    "add_card_item_tags",
    "add_card_topic_tags",
    "auto_create_topics_deck_profiles",
    "auto_timer_tags",
    "prioritized_tags_first",
    "topic_card_tags",
}
_ALWAYS_REDACT_CONFIG_KEYS = {
    # Keep credentials private even if a future config migration changes the
    # stored type from text to a number or another JSON value.
    "pin_hash",
}
_SENSITIVE_STRING_FRAGMENTS = {
    "author",
    "deck",
    "field",
    "file",
    "filter",
    "hash",
    "host",
    "label",
    "link",
    "name",
    "notetype",
    "password",
    "path",
    "pin",
    "profile",
    "query",
    "secret",
    "tag",
    "title",
    "token",
    "url",
}

_SAFE_DATABASE_TABLES = (
    "browser_media_refs",
    "browser_quick_tag_settings",
    "browser_recent_tag_groups",
    "browser_tag_colors",
    "custom_schedule_review_history",
    "custom_schedule_rule_versions",
    "custom_schedule_rules",
    "content_items",
    "document_index_state",
    "epub_card_sources",
    "epub_daily_limit_usage",
    "epub_daily_limits",
    "epub_due_review_prompts",
    "epub_highlights",
    "epub_progress",
    "epub_text_index",
    "item_postpones",
    "import_journal",
    "knowledge_tree_nodes",
    "knowledge_tree_postpone_presets",
    "note_ocr_index",
    "pdf_card_sources",
    "pdf_daily_limit_usage",
    "pdf_daily_limits",
    "pdf_due_review_prompts",
    "pdf_highlights",
    "pdf_progress",
    "pdf_text_index",
    "priorities",
    "reader_bookmarks",
    "reconciliation_runs",
    "reviewer_recent_tags",
    "schema_migrations",
    "stats",
    "topic_postpones",
    "topic_review_history",
    "topic_schedule",
    "video_progress",
    "web_card_sources",
    "web_progress",
    "writing_progress",
    "writing_word_stats",
)

_CRITICAL_CODE_FILES = (
    "__init__.py",
    "config.json",
    "manifest.json",
    "backend/answer_schedule.py",
    "backend/anki_compat.py",
    "backend/config_service.py",
    "backend/custom_schedule.py",
    "backend/db.py",
    "backend/db_connection.py",
    "backend/db_schema.py",
    "backend/diagnostics.py",
    "backend/item_skip.py",
    "backend/media_review.py",
    "backend/note_type_updates.py",
    "backend/operation_journal.py",
    "backend/paths.py",
    "backend/reviewer_buttons.py",
    "backend/reconciliation.py",
    "backend/scheduler.py",
    "backend/scheduler_config.py",
    "backend/search_indexer.py",
    "backend/search_repository.py",
    "backend/session.py",
    "backend/session_selection.py",
    "backend/topic_scheduler.py",
    "backend/topic_postpone.py",
    "frontend/custom_schedule_dialog.py",
    "frontend/learn_dialog.py",
    "frontend/media_review_dialog.py",
    "frontend/note_type_update_dialog.py",
    "frontend/pdf_dock.py",
    "frontend/reviewer_priority_badge.py",
    "frontend/search_all.py",
    "frontend/session_launcher.py",
    "frontend/epub_dock.py",
    "frontend/video_dock.py",
    "frontend/web_dock.py",
    "frontend/writing_dock.py",
    "frontend/settings_dialog.py",
    "web/dist/pdf_viewer.js",
    "chrome_extensions/incremento_companion/manifest.json",
)

_MISSING = object()


def safe_exception_type(exc: object) -> str:
    """Return only an exception class name; never its potentially private message."""
    name = type(exc).__name__ if exc is not None else "UnknownError"
    return name if name in _SAFE_ERROR_TYPES else "UnknownError"


def _bounded_int(value: object, minimum: int, maximum: int) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return max(minimum, min(number, maximum))


def _sanitize_event_field(kind: str, value: object) -> object:
    if kind == "bool":
        return value if isinstance(value, bool) else None
    if kind == "count":
        return _bounded_int(value, 0, 1_000_000_000)
    if kind == "interval":
        return _bounded_int(value, 0, 365_000)
    if kind == "rating":
        return _bounded_int(value, 0, 4)
    if kind == "card_state":
        return _bounded_int(value, -10, 10)
    if kind == "factor":
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(number):
            return None
        return round(max(0.0, min(number, 1_000.0)), 6)
    if kind == "state":
        candidate = str(value or "unknown")
        return candidate if candidate in _UI_STATES else "unknown"
    if kind == "refill_reason":
        candidate = str(value or "other")
        return candidate if candidate in _REFILL_REASONS else "other"
    if kind == "operation_scope":
        candidate = str(value or "none")
        return candidate if candidate in _OPERATION_SCOPES else "other"
    if kind in _SAFE_EVENT_ENUMS:
        candidate = str(value or "other").strip().casefold()
        allowed = _SAFE_EVENT_ENUMS[kind]
        return candidate if candidate in allowed else "other"
    if kind == "version":
        candidate = str(value or "unknown").strip()
        return candidate if _SAFE_VERSION_RE.fullmatch(candidate) else "unknown"
    if kind == "token":
        candidate = str(value or "UnknownError").strip()
        return candidate if candidate in _SAFE_ERROR_TYPES else "UnknownError"
    return None


def operation_scope_for(initiator: object, addon_module: str) -> str:
    """Classify an Anki operation initiator without exporting its name."""
    if initiator is None:
        return "none"
    # Collection operations frequently use functools.partial(). Its own
    # module is ``functools``; the wrapped callable is the useful attribution.
    wrapped = getattr(initiator, "func", None)
    module_name = str(getattr(wrapped, "__module__", "") or "")
    if not module_name:
        module_name = str(getattr(initiator, "__module__", "") or "")
    if not module_name:
        module_name = str(getattr(type(initiator), "__module__", "") or "")
    addon_root = str(addon_module or "").split(".", 1)[0]
    if addon_root and (
        module_name == addon_root or module_name.startswith(f"{addon_root}.")
    ):
        return "incremento"
    if module_name.startswith(("anki", "aqt")):
        return "anki"
    return "other"


def _sanitize_event_data(event: str, fields: Mapping[str, object] | None) -> dict:
    schema = _EVENT_SCHEMAS.get(str(event or ""))
    if schema is None:
        return {}
    source = fields if isinstance(fields, Mapping) else {}
    sanitized: dict[str, object] = {}
    for key, kind in schema.items():
        if key not in source:
            continue
        value = _sanitize_event_field(kind, source[key])
        if value is not None:
            sanitized[key] = value
    return sanitized


@dataclass(frozen=True)
class _FlushBarrier:
    completed: threading.Event


class DiagnosticRecorder:
    """Bounded per-profile JSONL recorder with non-blocking caller writes."""

    def __init__(
        self,
        addon_dir: str,
        profile: str,
        *,
        clock: Callable[[], float] = time.monotonic,
        run_id: str | None = None,
    ) -> None:
        self._path = get_diagnostic_events_path(addon_dir, profile)
        self._clock = clock
        self._started = float(clock())
        candidate_run_id = str(run_id or secrets.token_hex(6)).casefold()
        self._run_id = (
            candidate_run_id
            if _SAFE_RUN_ID_RE.fullmatch(candidate_run_id)
            else secrets.token_hex(6)
        )
        self._sequence = 0
        self._state_lock = threading.RLock()
        self._io_lock = threading.RLock()
        self._handle = None
        self._queue: queue.Queue[bytes | _FlushBarrier] = queue.Queue(
            maxsize=MAX_PENDING_EVENTS
        )
        self._stop_requested = threading.Event()
        self._accepting = True
        self._closed = False
        self._attempted = 0
        self._accepted = 0
        self._written = 0
        self._dropped = 0
        self._write_failures = 0
        self._rotations = 0
        self._last_failure = "none"
        self._last_flush_complete = True
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="IncrementoDiagnostics",
            daemon=True,
        )
        self._worker.start()

    @property
    def path(self) -> Path:
        return self._path

    def _rotated_path(self, index: int) -> Path:
        return self._path.with_name(f"events.{int(index)}.jsonl")

    def _rotate_if_needed(self, incoming_bytes: int) -> bool:
        try:
            current_bytes = self._path.stat().st_size
        except OSError:
            current_bytes = 0
        if current_bytes + max(0, int(incoming_bytes)) <= MAX_LOG_BYTES:
            return True

        self._close_handle()

        oldest = self._rotated_path(MAX_LOG_FILES - 1)
        try:
            oldest.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            return False

        for index in range(MAX_LOG_FILES - 2, 0, -1):
            source = self._rotated_path(index)
            if not source.exists():
                continue
            try:
                os.replace(source, self._rotated_path(index + 1))
            except OSError:
                return False
        if self._path.exists():
            try:
                os.replace(self._path, self._rotated_path(1))
            except OSError:
                return False
        with self._state_lock:
            self._rotations += 1
        return True

    def _close_handle(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            handle.flush()
        except Exception:
            pass
        try:
            handle.close()
        except Exception:
            pass

    def _write_encoded(self, encoded: bytes) -> str | None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return "mkdir"
        with self._io_lock:
            if not self._rotate_if_needed(len(encoded)):
                return "rotation"
            if self._handle is None:
                try:
                    self._handle = self._path.open("ab")
                except OSError:
                    return "open"
            try:
                self._handle.write(encoded)
                self._handle.flush()
            except Exception:
                self._close_handle()
                return "write"
        return None

    def _worker_loop(self) -> None:
        try:
            while True:
                try:
                    item = self._queue.get(timeout=0.1)
                except queue.Empty:
                    if self._stop_requested.is_set():
                        break
                    continue
                try:
                    if isinstance(item, _FlushBarrier):
                        with self._io_lock:
                            if self._handle is not None:
                                try:
                                    self._handle.flush()
                                except Exception:
                                    with self._state_lock:
                                        self._write_failures += 1
                                        self._last_failure = "write"
                        item.completed.set()
                        continue
                    failure = self._write_encoded(item)
                    with self._state_lock:
                        if failure is None:
                            self._written += 1
                        else:
                            self._write_failures += 1
                            self._dropped += 1
                            self._last_failure = failure
                except Exception:
                    with self._state_lock:
                        self._write_failures += 1
                        self._dropped += 1
                        self._last_failure = "worker"
                finally:
                    self._queue.task_done()
        finally:
            with self._io_lock:
                self._close_handle()

    def flush(self, *, timeout: float = RECORDER_FLUSH_TIMEOUT_SECONDS) -> bool:
        """Wait for queued events on a non-UI caller such as bundle export."""
        if not self._worker.is_alive():
            completed = self._queue.empty()
            with self._state_lock:
                self._last_flush_complete = completed
            return completed
        barrier = _FlushBarrier(threading.Event())
        bounded_timeout = max(0.0, float(timeout or 0.0))
        try:
            self._queue.put(barrier, timeout=bounded_timeout)
        except queue.Full:
            with self._state_lock:
                self._last_flush_complete = False
                self._last_failure = "flush_timeout"
            return False
        completed = barrier.completed.wait(bounded_timeout)
        with self._state_lock:
            self._last_flush_complete = bool(completed)
            if not completed:
                self._last_failure = "flush_timeout"
        return bool(completed)

    def health_snapshot(self) -> dict[str, object]:
        """Return fixed counters/flags only; never include exception text or paths."""
        with self._state_lock:
            return {
                "attempted_events": self._attempted,
                "accepted_events": self._accepted,
                "written_events": self._written,
                "dropped_events": self._dropped,
                "write_failures": self._write_failures,
                "rotations": self._rotations,
                "pending_events": self._queue.qsize(),
                "queue_capacity": MAX_PENDING_EVENTS,
                "worker_alive": self._worker.is_alive(),
                "closed": self._closed,
                "last_flush_complete": self._last_flush_complete,
                "last_failure": self._last_failure,
            }

    def close(self, *, timeout: float = RECORDER_FLUSH_TIMEOUT_SECONDS) -> bool:
        with self._state_lock:
            if self._closed:
                return not self._worker.is_alive()
            self._accepting = False
            self._closed = True
        flushed = self.flush(timeout=timeout)
        self._stop_requested.set()
        self._worker.join(timeout=max(0.0, float(timeout or 0.0)))
        return bool(flushed and not self._worker.is_alive())

    def record(self, event: str, **fields: object) -> bool:
        event_name = str(event or "")
        if event_name not in _EVENT_SCHEMAS:
            return False
        data = _sanitize_event_data(event_name, fields)
        with self._state_lock:
            self._attempted += 1
            if not self._accepting:
                self._dropped += 1
                self._last_failure = "closed"
                return False
            self._sequence += 1
            elapsed_ms = max(0, int((float(self._clock()) - self._started) * 1000))
            record = {
                "schema": DIAGNOSTIC_SCHEMA_VERSION,
                "run": self._run_id,
                "sequence": self._sequence,
                "elapsed_ms": elapsed_ms,
                "event": event_name,
                "data": data,
            }
            encoded = (
                json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n"
            ).encode("utf-8")
            if len(encoded) > MAX_LOG_BYTES:
                self._dropped += 1
                self._last_failure = "oversized"
                return False
            try:
                self._queue.put_nowait(encoded)
                self._accepted += 1
                return True
            except queue.Full:
                self._dropped += 1
                self._last_failure = "queue_full"
                return False

    def recent_events(self, *, limit: int = MAX_EXPORTED_EVENTS) -> list[dict]:
        bounded_limit = max(0, min(int(limit or 0), MAX_EXPORTED_EVENTS))
        if bounded_limit == 0:
            return []
        collected: deque[dict] = deque(maxlen=bounded_limit)
        paths = [
            self._rotated_path(index)
            for index in range(MAX_LOG_FILES - 1, 0, -1)
        ] + [self._path]

        self.flush()
        with self._io_lock:
            if self._handle is not None:
                try:
                    self._handle.flush()
                except Exception:
                    pass
            for path in paths:
                try:
                    handle = path.open("r", encoding="utf-8", errors="replace")
                except OSError:
                    continue
                with handle:
                    for line in handle:
                        try:
                            raw = json.loads(line)
                        except (TypeError, ValueError):
                            continue
                        sanitized = _revalidate_event_record(raw)
                        if sanitized is not None:
                            collected.append(sanitized)
        return list(collected)


def _revalidate_event_record(raw: object) -> dict | None:
    if not isinstance(raw, Mapping):
        return None
    schema = _bounded_int(raw.get("schema"), 0, 1_000_000)
    if schema != DIAGNOSTIC_SCHEMA_VERSION:
        return None
    event = str(raw.get("event") or "")
    if event not in _EVENT_SCHEMAS:
        return None
    run = str(raw.get("run") or "")
    if not _SAFE_RUN_ID_RE.fullmatch(run):
        run = "invalid"
    sequence = _bounded_int(raw.get("sequence"), 0, 1_000_000_000)
    elapsed_ms = _bounded_int(raw.get("elapsed_ms"), 0, 10_000_000_000)
    if sequence is None or elapsed_ms is None:
        return None
    return {
        "schema": DIAGNOSTIC_SCHEMA_VERSION,
        "run": run,
        "sequence": sequence,
        "elapsed_ms": elapsed_ms,
        "event": event,
        "data": _sanitize_event_data(event, raw.get("data")),
    }


def _redacted(kind: str, value: object) -> dict[str, object]:
    result: dict[str, object] = {"redacted": True, "kind": kind}
    if isinstance(value, (list, tuple, set, dict)):
        result["count"] = len(value)
    elif isinstance(value, str):
        result["empty"] = not bool(value)
    return result


def _key_is_sensitive(key: str) -> bool:
    parts = {part for part in str(key or "").casefold().split("_") if part}
    return bool(parts & _SENSITIVE_STRING_FRAGMENTS)


def _sanitize_shortcut(value: object) -> object:
    text = str(value or "").strip()
    if not text:
        return ""
    modifiers = {"alt", "ctrl", "control", "meta", "cmd", "command", "option", "shift"}
    named_keys = {
        "backspace", "delete", "down", "end", "enter", "esc", "escape",
        "home", "insert", "left", "pagedown", "pageup", "return", "right",
        "space", "tab", "up",
    }
    for chord in text.split(","):
        tokens = [token.strip() for token in chord.split("+") if token.strip()]
        if not tokens:
            return _redacted("shortcut", text)
        for token in tokens:
            folded = token.casefold()
            if folded in modifiers or folded in named_keys:
                continue
            if len(token) == 1 and token.isalnum():
                continue
            if re.fullmatch(r"F(?:[1-9]|1\d|2[0-4])", token, re.IGNORECASE):
                continue
            if token in {"-", "=", "/", "\\", "[", "]", ";", "'", ".", ","}:
                continue
            return _redacted("shortcut", text)
    return text


def _safe_default_for_list(default: object, index: int) -> object:
    if not isinstance(default, (list, tuple)) or not default:
        return _MISSING
    if index < len(default):
        return default[index]
    return default[0]


def _sanitize_config_value(value: object, path: tuple[str, ...], default: object) -> object:
    key = path[-1] if path else ""
    if key in _ALWAYS_REDACT_CONFIG_KEYS:
        return _redacted("private_value", value)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return max(-1_000_000_000, min(value, 1_000_000_000))
    if isinstance(value, float):
        if not math.isfinite(value):
            return _redacted("non_finite_number", value)
        return round(max(-1_000_000_000.0, min(value, 1_000_000_000.0)), 6)

    if key in _SENSITIVE_COLLECTION_KEYS and isinstance(value, (list, tuple, set)):
        return _redacted("private_collection", value)

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        if path and path[-2:-1] == ("shortcuts",):
            return _sanitize_shortcut(text)
        if _key_is_sensitive(key):
            return _redacted("private_string", text)
        if text.casefold() in _SAFE_ENUM_STRINGS:
            return text
        if _SAFE_TIME_RE.fullmatch(text):
            return text
        if _SAFE_DURATION_RE.fullmatch(text):
            return text
        return _redacted("free_text", text)

    if isinstance(value, Mapping):
        if key in {"profiles", "scheduler_presets"}:
            entries: dict[str, object] = {}
            for index, (_, profile_config) in enumerate(value.items(), start=1):
                entries[f"profile_{index}"] = _sanitize_config_value(
                    profile_config,
                    path + ("profile_config",),
                    _MISSING,
                )
            return {
                "profile_names_redacted": True,
                "count": len(entries),
                "entries": entries,
            }

        default_mapping = default if isinstance(default, Mapping) else {}
        output: dict[str, object] = {}
        unknown_count = 0
        for raw_key, child in value.items():
            child_key = str(raw_key or "")
            allowed = False
            if key == "shortcuts":
                allowed = child_key in _SAFE_SHORTCUT_IDS
            elif child_key in default_mapping:
                allowed = True
            elif child_key in _SAFE_NESTED_CONFIG_KEYS:
                allowed = True
            elif child_key in _KNOWN_CONFIG_KEYS:
                allowed = True
            if not allowed or not _SAFE_CONFIG_KEY_RE.fullmatch(child_key):
                unknown_count += 1
                continue
            output[child_key] = _sanitize_config_value(
                child,
                path + (child_key,),
                default_mapping.get(child_key, _MISSING),
            )
        if unknown_count:
            output["_redacted_unknown_entries"] = unknown_count
        return output

    if isinstance(value, (list, tuple, set)):
        sequence = list(value)
        return [
            _sanitize_config_value(
                child,
                path + ("item",),
                _safe_default_for_list(default, index),
            )
            for index, child in enumerate(sequence)
        ]

    return _redacted(type(value).__name__, value)


def sanitize_config(
    config: Mapping[str, object] | None,
    defaults: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Preserve safe configuration semantics while removing private labels/values."""
    current = config if isinstance(config, Mapping) else {}
    shipped = defaults if isinstance(defaults, Mapping) else {}
    known_keys = set(_KNOWN_CONFIG_KEYS) | {
        str(key) for key in shipped if _SAFE_CONFIG_KEY_RE.fullmatch(str(key))
    }
    settings: dict[str, object] = {}
    changed_from_defaults: list[str] = []
    unknown_count = 0
    for raw_key, value in current.items():
        key = str(raw_key or "")
        if key not in known_keys or not _SAFE_CONFIG_KEY_RE.fullmatch(key):
            unknown_count += 1
            continue
        default = shipped.get(key, _MISSING)
        settings[key] = _sanitize_config_value(value, (key,), default)
        if default is not _MISSING and value != default:
            changed_from_defaults.append(key)

    missing_default_settings = sorted(str(key) for key in shipped if key not in current)
    return {
        "schema": 1,
        "settings": settings,
        "changed_from_shipped_defaults": sorted(changed_from_defaults),
        "missing_shipped_default_settings": missing_default_settings,
        "redacted_unknown_setting_count": unknown_count,
    }


def safe_environment_snapshot(values: Mapping[str, object] | None = None) -> dict:
    source = values if isinstance(values, Mapping) else {}
    system = str(source.get("operating_system") or platform.system() or "unknown")
    if system not in {"Darwin", "Linux", "Windows", "unknown"}:
        system = "other"
    machine = str(source.get("architecture") or platform.machine() or "unknown")
    if machine not in {"arm64", "aarch64", "x86_64", "AMD64", "i386", "i686", "unknown"}:
        machine = "other"
    return {
        "anki_version": _sanitize_event_field("version", source.get("anki_version")),
        "addon_version": _sanitize_event_field("version", source.get("addon_version")),
        "python_version": _sanitize_event_field(
            "version", source.get("python_version") or platform.python_version()
        ),
        "operating_system": system,
        "operating_system_release": _sanitize_event_field(
            "version", source.get("operating_system_release") or platform.release()
        ),
        "architecture": machine,
        "enabled_addons": _bounded_int(source.get("enabled_addons"), 0, 100_000),
    }


def sanitize_runtime_state(values: Mapping[str, object] | None = None) -> dict:
    source = values if isinstance(values, Mapping) else {}
    session = source.get("incremento_session")
    session_source = session if isinstance(session, Mapping) else {}
    interaction = source.get("ui_interaction")
    interaction_source = interaction if isinstance(interaction, Mapping) else {}
    return {
        "ui_state": _sanitize_event_field("state", source.get("ui_state")),
        "ui_interaction": {
            "main_window_enabled": bool(
                interaction_source.get("main_window_enabled", False)
            ),
            "reviewer_web_enabled": bool(
                interaction_source.get("reviewer_web_enabled", False)
            ),
            "active_modal": bool(interaction_source.get("active_modal", False)),
            "active_popup": bool(interaction_source.get("active_popup", False)),
            "progress_levels": _bounded_int(
                interaction_source.get("progress_levels"), 0, 1_000
            ) or 0,
            "progress_window_visible": bool(
                interaction_source.get("progress_window_visible", False)
            ),
            "background_operations": _bounded_int(
                interaction_source.get("background_operations"), 0, 1_000
            ) or 0,
        },
        "incremento_session": {
            "active": bool(session_source.get("active", False)),
            "selected_count": _bounded_int(session_source.get("selected_count"), 0, 1_000_000_000) or 0,
            "reviewed_count": _bounded_int(session_source.get("reviewed_count"), 0, 1_000_000_000) or 0,
            "window_size": _bounded_int(session_source.get("window_size"), 0, 1_000_000_000) or 0,
            "auto_refill": bool(session_source.get("auto_refill", False)),
            "refill_pending": bool(session_source.get("refill_pending", False)),
            "closed": bool(session_source.get("closed", False)),
        },
        "diagnostic_retention": {
            "max_log_bytes_per_file": MAX_LOG_BYTES,
            "max_log_files": MAX_LOG_FILES,
            "max_exported_events": MAX_EXPORTED_EVENTS,
            "max_pending_events": MAX_PENDING_EVENTS,
            "absolute_event_timestamps_recorded": False,
        },
    }


def collect_database_summary(addon_dir: str, profile: str) -> dict:
    """Return only schema metadata and row counts, never database row contents."""
    path = get_db_path(addon_dir, profile)
    if not path.exists():
        return {"status": "missing", "database_bytes": 0, "tables": {}}
    try:
        database_bytes = max(0, int(path.stat().st_size))
    except OSError:
        database_bytes = 0

    connection = None
    try:
        uri = path.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=1.0)
        existing = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        tables: dict[str, dict[str, object]] = {}
        schema_fingerprint_rows: list[tuple[str, tuple[tuple[str, str], ...]]] = []
        for table in _SAFE_DATABASE_TABLES:
            if table not in existing:
                tables[table] = {"present": False, "row_count": 0, "column_count": 0}
                continue
            row = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
            column_rows = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
            normalized_columns = tuple(
                (str(column[1] or ""), str(column[2] or "").upper())
                for column in column_rows
            )
            schema_fingerprint_rows.append((table, normalized_columns))
            tables[table] = {
                "present": True,
                "row_count": max(0, int((row or [0])[0] or 0)),
                "column_count": len(normalized_columns),
            }
        schema_fingerprint = hashlib.sha256(
            json.dumps(
                schema_fingerprint_rows,
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return {
            "status": "available",
            "database_bytes": database_bytes,
            "known_table_count": sum(
                1 for value in tables.values() if bool(value.get("present"))
            ),
            "expected_known_table_count": len(_SAFE_DATABASE_TABLES),
            "schema_fingerprint_sha256": schema_fingerprint,
            "tables": tables,
        }
    except Exception as exc:
        return {
            "status": "error",
            "database_bytes": database_bytes,
            "error_type": safe_exception_type(exc),
            "tables": {},
        }
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def collect_code_fingerprints(addon_dir: str) -> dict[str, dict[str, object]]:
    """Fingerprint a fixed list of shipped files without exporting their contents."""
    root = Path(addon_dir)
    result: dict[str, dict[str, object]] = {}
    for relative in _CRITICAL_CODE_FILES:
        path = root / relative
        try:
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    size += len(chunk)
                    digest.update(chunk)
            result[relative] = {
                "present": True,
                "bytes": size,
                "sha256": digest.hexdigest(),
            }
        except OSError:
            result[relative] = {"present": False}
    return result


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    return info


def _write_zip_text(archive: zipfile.ZipFile, name: str, text: str) -> None:
    archive.writestr(_zip_info(name), text.encode("utf-8"))


def _write_zip_json(archive: zipfile.ZipFile, name: str, value: object) -> None:
    _write_zip_text(
        archive,
        name,
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
    )


_BUNDLE_README = """Incremento privacy-safe support bundle
========================================

This archive is intended for debugging and may be shared with the Incremento
developer. It does not contain card or note text, raw Anki identifiers, deck or
tag names, profile names, media, user or media filenames, local filesystem
paths, URLs, browser history, database rows, exception messages, or precise
activity timestamps.

Configuration booleans, numbers, safe enums, and shortcuts are preserved.
Names, labels, tags, filters, paths, URLs, hashes, and other free text are
replaced with redaction descriptors. Diagnostic events use elapsed time within
an Anki run and a fixed whitelist of typed fields. Persisted logs are parsed and
revalidated during export; their raw files are never copied into this archive.
Fixed shipped-code filenames appear only beside their hashes so the installed
build can be identified.

The event log begins only after a version containing this diagnostic recorder
has been installed. Retention is bounded, so the archive contains recent events
rather than an unlimited history.
"""


def build_support_bundle(
    destination: str | os.PathLike[str],
    *,
    addon_dir: str,
    profile: str,
    recorder: DiagnosticRecorder,
    config: Mapping[str, object] | None,
    default_config: Mapping[str, object] | None,
    environment: Mapping[str, object] | None,
    runtime_state: Mapping[str, object] | None,
) -> dict[str, int]:
    """Create an atomic, privacy-safe diagnostic ZIP and return safe counters."""
    destination_path = Path(destination)
    if not destination_path.name:
        raise ValueError("A support bundle destination is required.")
    if destination_path.suffix.casefold() != ".zip":
        destination_path = destination_path.with_suffix(destination_path.suffix + ".zip")
    if not destination_path.parent.exists():
        raise FileNotFoundError("The selected destination folder does not exist.")

    events = recorder.recent_events()
    recorder_status = recorder.health_snapshot()
    sanitized_config = sanitize_config(config, default_config)
    safe_environment = safe_environment_snapshot(environment)
    safe_runtime = sanitize_runtime_state(runtime_state)
    database_summary = collect_database_summary(addon_dir, profile)
    code_fingerprints = collect_code_fingerprints(addon_dir)
    manifest = {
        "schema": SUPPORT_BUNDLE_SCHEMA_VERSION,
        "created_date_utc": _datetime.datetime.now(_datetime.timezone.utc).date().isoformat(),
        "addon": "Incremento",
        "event_count": len(events),
        "privacy": {
            "card_or_note_text": False,
            "raw_card_or_note_ids": False,
            "deck_tag_or_profile_names": False,
            "media": False,
            "user_or_media_filenames": False,
            "local_paths_or_urls": False,
            "database_rows": False,
            "exception_messages_or_tracebacks": False,
            "absolute_event_timestamps": False,
        },
        "files": {
            "README.txt": "Privacy and scope explanation",
            "config/sanitized.json": "Configuration with private/free-text values redacted",
            "diagnostics/environment.json": "Non-identifying runtime versions and platform family",
            "diagnostics/current_state.json": "Safe current UI/session counters and flags",
            "diagnostics/recorder_status.json": "Safe writer health and dropped-event counters",
            "diagnostics/database_summary.json": "Known table row counts only",
            "diagnostics/code_fingerprints.json": "Hashes of a fixed list of shipped files",
            "diagnostics/events.jsonl": "Recent schema-whitelisted operational events",
        },
    }

    event_text = "".join(
        json.dumps(event, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
        for event in events
    )

    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination_path.parent,
            prefix=".incremento-support-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temp_name = temporary.name
        with zipfile.ZipFile(temp_name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            _write_zip_text(archive, "README.txt", _BUNDLE_README)
            _write_zip_json(archive, "manifest.json", manifest)
            _write_zip_json(archive, "config/sanitized.json", sanitized_config)
            _write_zip_json(archive, "diagnostics/environment.json", safe_environment)
            _write_zip_json(archive, "diagnostics/current_state.json", safe_runtime)
            _write_zip_json(archive, "diagnostics/recorder_status.json", recorder_status)
            _write_zip_json(archive, "diagnostics/database_summary.json", database_summary)
            _write_zip_json(archive, "diagnostics/code_fingerprints.json", code_fingerprints)
            _write_zip_text(archive, "diagnostics/events.jsonl", event_text)
        os.replace(temp_name, destination_path)
        temp_name = None
        return {
            "event_count": len(events),
            "bundle_bytes": max(0, int(destination_path.stat().st_size)),
        }
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink()
            except OSError:
                pass
