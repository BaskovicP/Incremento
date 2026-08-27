from __future__ import annotations

import functools
import json
import sqlite3
import threading
import zipfile
from pathlib import Path

import diagnostics


PRIVATE_VALUES = (
    "SECRET CARD CONTENT",
    "Alice Private Profile",
    "personal-tag",
    "Private Deck",
    "/Users/alice/Documents/private.pdf",
    "https://private.example/alice",
    "alice@example.com",
    "super-secret-pin-hash",
)

FORBIDDEN_EVENT_FIELDS = {
    "card_id",
    "note_id",
    "content",
    "deck",
    "message",
    "path",
    "payload",
    "profile",
    "tag",
    "text",
    "url",
}


def _all_zip_text(path: Path) -> str:
    chunks: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            chunks.append(name)
            chunks.append(archive.read(name).decode("utf-8", errors="replace"))
    return "\n".join(chunks)


def test_recorder_accepts_only_whitelisted_typed_fields(tmp_path: Path) -> None:
    ticks = iter((100.0, 100.25, 101.0))
    recorder = diagnostics.DiagnosticRecorder(
        str(tmp_path),
        "Alice Private Profile",
        clock=lambda: next(ticks),
        run_id="abcdef123456",
    )

    assert recorder.record(
        "review_answered",
        rating=3,
        card_type=2,
        queue=2,
        interval_days=12,
        card_id=1771491223100,
        card_text=PRIVATE_VALUES[0],
        path=PRIVATE_VALUES[4],
    )
    assert recorder.record(
        "incremento_session_build_failed",
        error_type="RuntimeError",
        message=PRIVATE_VALUES[0],
    )
    assert recorder.record("made_up_event", payload=PRIVATE_VALUES[0]) is False
    assert recorder.flush()

    assert recorder.path == (
        tmp_path
        / "user_files"
        / "Alice Private Profile"
        / "diagnostics"
        / "events.jsonl"
    )
    raw = recorder.path.read_text(encoding="utf-8")
    assert "card_id" not in raw
    assert "card_text" not in raw
    assert "path" not in raw
    assert "message" not in raw
    assert "1771491223100" not in raw
    for private in PRIVATE_VALUES:
        assert private not in raw

    events = recorder.recent_events()
    assert [event["event"] for event in events] == [
        "review_answered",
        "incremento_session_build_failed",
    ]
    assert events[0]["elapsed_ms"] == 250
    assert events[0]["data"] == {
        "rating": 3,
        "card_type": 2,
        "queue": 2,
        "interval_days": 12,
    }
    assert "timestamp" not in events[0]
    assert recorder.close()


def test_event_schemas_cannot_accept_private_or_free_text_fields() -> None:
    for schema in diagnostics._EVENT_SCHEMAS.values():
        assert FORBIDDEN_EVENT_FIELDS.isdisjoint(schema)
        assert set(schema.values()) <= {
            "bool",
            "card_state",
            "count",
            "action_stage",
            "content_kind",
            "explicit_source",
            "explicit_stage",
            "factor",
            "interval",
            "media_card_kind",
            "media_order",
            "media_range",
            "media_state",
            "media_tree_scope",
            "operation_scope",
            "rating",
            "refill_outcome",
            "refill_reason",
            "refill_skip_reason",
            "review_action",
            "schedule_mode",
            "schedule_reason",
            "schedule_stage",
            "session_phase",
            "session_stop_reason",
            "state",
            "token",
            "topic_choice",
            "version",
        }


def test_media_review_diagnostics_keep_only_fixed_options_and_counts() -> None:
    data = diagnostics._sanitize_event_data(
        "explicit_review_requested",
        {
            "source": "media_review",
            "content_kind": "pdf",
            "requested_count": 42,
            "preserve_order": True,
            "media_order": "created_newest",
            "media_card_kind": "topics",
            "media_tree_scope": "nested",
            "media_range": "to_current",
            "media_state": "due",
            "limit": 500,
            "filename": PRIVATE_VALUES[4],
            "private_option": PRIVATE_VALUES[0],
        },
    )
    assert data == {
        "source": "media_review",
        "content_kind": "pdf",
        "requested_count": 42,
        "preserve_order": True,
        "media_order": "created_newest",
        "media_card_kind": "topics",
        "media_tree_scope": "nested",
        "media_range": "to_current",
        "media_state": "due",
        "limit": 500,
    }
    assert PRIVATE_VALUES[4] not in repr(data)


def test_recorders_keep_profile_logs_isolated(tmp_path: Path) -> None:
    first = diagnostics.DiagnosticRecorder(
        str(tmp_path), "First", clock=lambda: 1.0, run_id="111111111111"
    )
    second = diagnostics.DiagnosticRecorder(
        str(tmp_path), "Second", clock=lambda: 1.0, run_id="222222222222"
    )
    first.record("profile_opened")
    second.record("support_bundle_requested")
    first.close()
    second.close()

    assert first.path != second.path
    assert [event["event"] for event in first.recent_events()] == ["profile_opened"]
    assert [event["event"] for event in second.recent_events()] == [
        "support_bundle_requested"
    ]


def test_export_revalidates_tampered_log_instead_of_copying_it(tmp_path: Path) -> None:
    recorder = diagnostics.DiagnosticRecorder(
        str(tmp_path), "P", clock=lambda: 1.0, run_id="abcdef123456"
    )
    recorder.record("profile_opened")
    assert recorder.flush()
    with recorder.path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "schema": 1,
                    "run": PRIVATE_VALUES[6],
                    "sequence": 2,
                    "elapsed_ms": 10,
                    "event": "review_answered",
                    "data": {"rating": 4, "card_text": PRIVATE_VALUES[0]},
                    "private": PRIVATE_VALUES[6],
                }
            )
            + "\n"
        )
        handle.write(
            json.dumps(
                {
                    "run": "abcdef123456",
                    "sequence": 3,
                    "elapsed_ms": 20,
                    "event": "private_event",
                    "data": {"value": PRIVATE_VALUES[0]},
                }
            )
            + "\n"
        )

    exported = json.dumps(recorder.recent_events(), sort_keys=True)
    assert PRIVATE_VALUES[0] not in exported
    assert PRIVATE_VALUES[6] not in exported
    assert "card_text" not in exported
    assert "private_event" not in exported
    assert '"rating": 4' in exported
    assert '"run": "invalid"' in exported
    assert recorder.close()


def test_recorder_writes_never_wait_for_the_io_worker(tmp_path: Path, monkeypatch) -> None:
    recorder = diagnostics.DiagnosticRecorder(
        str(tmp_path), "P", clock=lambda: 1.0, run_id="abcdef123456"
    )
    entered = threading.Event()
    release = threading.Event()
    original_write = recorder._write_encoded

    def _blocked_write(encoded: bytes):
        entered.set()
        release.wait(2.0)
        return original_write(encoded)

    monkeypatch.setattr(recorder, "_write_encoded", _blocked_write)
    assert recorder.record("profile_opened")
    assert entered.wait(1.0)

    result: list[bool] = []
    caller = threading.Thread(
        target=lambda: result.append(recorder.record("support_bundle_requested"))
    )
    caller.start()
    caller.join(0.25)
    try:
        assert not caller.is_alive()
        assert result == [True]
    finally:
        release.set()
        caller.join(1.0)

    assert recorder.flush()
    health = recorder.health_snapshot()
    assert health["accepted_events"] == 2
    assert health["written_events"] == 2
    assert health["dropped_events"] == 0
    assert recorder.close()


def test_recorder_reports_bounded_queue_drops(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(diagnostics, "MAX_PENDING_EVENTS", 1)
    recorder = diagnostics.DiagnosticRecorder(
        str(tmp_path), "P", clock=lambda: 1.0, run_id="abcdef123456"
    )
    entered = threading.Event()
    release = threading.Event()
    original_write = recorder._write_encoded

    def _blocked_write(encoded: bytes):
        entered.set()
        release.wait(2.0)
        return original_write(encoded)

    monkeypatch.setattr(recorder, "_write_encoded", _blocked_write)
    assert recorder.record("profile_opened")
    assert entered.wait(1.0)
    assert recorder.record("support_bundle_requested")
    assert recorder.record("profile_closing") is False
    status = recorder.health_snapshot()
    assert status["queue_capacity"] == 1
    assert status["dropped_events"] == 1
    assert status["last_failure"] == "queue_full"
    release.set()
    assert recorder.flush()
    assert recorder.close()


def test_recorder_rotates_to_a_bounded_number_of_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(diagnostics, "MAX_LOG_BYTES", 350)
    tick = [0.0]

    def _clock() -> float:
        tick[0] += 0.01
        return tick[0]

    recorder = diagnostics.DiagnosticRecorder(
        str(tmp_path), "P", clock=_clock, run_id="abcdef123456"
    )
    for _ in range(20):
        assert recorder.record(
            "review_answered",
            rating=3,
            card_type=2,
            queue=2,
            interval_days=30,
        )
    recorder.close()

    diagnostic_dir = recorder.path.parent
    event_files = sorted(diagnostic_dir.glob("events*.jsonl"))
    assert [path.name for path in event_files] == [
        "events.1.jsonl",
        "events.2.jsonl",
        "events.jsonl",
    ]
    assert all(path.stat().st_size <= 350 for path in event_files)
    assert 1 <= len(recorder.recent_events()) < 20


def test_config_sanitizer_preserves_behavior_but_removes_private_values() -> None:
    config = {
        "auto_refill_session": True,  # deliberately unknown top-level key
        "topic_card_tags": [PRIVATE_VALUES[2]],
        "extract_notetype": "My private note type",
        "pin_hash": PRIVATE_VALUES[7],
        "writing_external_app_custom_path": PRIVATE_VALUES[4],
        "custom_schedule_default_mode": "minimum_cadence",
        "custom_schedule_presets": [
            {
                "label": "Alice's private cadence",
                "interval_value": 3,
                "interval_unit": "days",
                "sort_order": 1,
            }
        ],
        "shortcuts": {"start_learning": "Ctrl+I"},
        "dialog": {
            "session_card_count": 500,
            "auto_refill_session": True,
            "topics_filter": PRIVATE_VALUES[2],
            "priority_order_entries": [
                {"kind": "tag", "value": PRIVATE_VALUES[2], "order": 0},
                {"kind": "content_type", "value": "pdf", "order": 1},
            ],
            "tag_rows": [
                {
                    "tag": PRIVATE_VALUES[2],
                    "weight": 70,
                    "locked": False,
                    "group": "tags",
                }
            ],
        },
        "profiles": {
            PRIVATE_VALUES[1]: {
                "session_card_count": 40,
                "items_filter": PRIVATE_VALUES[3],
            }
        },
        "alice_private_key": PRIVATE_VALUES[6],
    }
    defaults = {
        "topic_card_tags": [],
        "extract_notetype": "",
        "custom_schedule_default_mode": "minimum_cadence",
        "custom_schedule_presets": [],
    }

    sanitized = diagnostics.sanitize_config(config, defaults)
    encoded = json.dumps(sanitized, sort_keys=True)
    for private in PRIVATE_VALUES:
        assert private not in encoded
    assert "Alice's private cadence" not in encoded
    assert "My private note type" not in encoded
    assert "alice_private_key" not in encoded

    settings = sanitized["settings"]
    assert settings["custom_schedule_default_mode"] == "minimum_cadence"
    assert settings["shortcuts"]["start_learning"] == "Ctrl+I"
    assert settings["dialog"]["session_card_count"] == 500
    assert settings["dialog"]["auto_refill_session"] is True
    assert settings["dialog"]["tag_rows"][0]["weight"] == 70
    assert settings["dialog"]["tag_rows"][0]["tag"]["redacted"] is True
    priority_entries = settings["dialog"]["priority_order_entries"]
    assert priority_entries[0]["kind"] == "tag"
    assert priority_entries[0]["value"]["redacted"] is True
    assert priority_entries[1] == {"kind": "content_type", "value": "pdf", "order": 1}
    assert settings["profiles"]["profile_names_redacted"] is True
    assert settings["profiles"]["entries"]["profile_1"]["session_card_count"] == 40
    assert sanitized["redacted_unknown_setting_count"] == 2

    numeric_secret = diagnostics.sanitize_config(
        {"pin_hash": 1771491223100},
        {"pin_hash": ""},
    )
    assert "1771491223100" not in json.dumps(numeric_secret)
    assert numeric_secret["settings"]["pin_hash"]["redacted"] is True


def test_shipped_config_keys_are_explicitly_known() -> None:
    config_path = Path(__file__).resolve().parents[1] / "config.json"
    shipped = json.loads(config_path.read_text(encoding="utf-8"))
    assert set(shipped) <= diagnostics._KNOWN_CONFIG_KEYS


def test_operation_scope_uses_callable_and_wrapped_function_modules() -> None:
    def incremento_handler():
        pass

    incremento_handler.__module__ = "incremento.backend.session"
    assert diagnostics.operation_scope_for(incremento_handler, "incremento") == "incremento"
    assert diagnostics.operation_scope_for(
        functools.partial(incremento_handler), "incremento"
    ) == "incremento"

    def anki_handler():
        pass

    anki_handler.__module__ = "aqt.operations"
    assert diagnostics.operation_scope_for(anki_handler, "incremento") == "anki"
    assert diagnostics.operation_scope_for(None, "incremento") == "none"


def test_support_bundle_contains_only_safe_summaries(tmp_path: Path) -> None:
    addon_dir = tmp_path / "addon-owned-by-alice"
    addon_dir.mkdir()
    (addon_dir / "backend").mkdir()
    (addon_dir / "backend" / "session.py").write_text(
        PRIVATE_VALUES[0], encoding="utf-8"
    )
    (addon_dir / "config.json").write_text("{}", encoding="utf-8")

    profile = "Alice Private Profile"
    database_path = addon_dir / "user_files" / profile / "incremento.db"
    database_path.parent.mkdir(parents=True)
    connection = sqlite3.connect(database_path)
    connection.execute(
        "CREATE TABLE priorities (card_id INTEGER, priority REAL, private_text TEXT)"
    )
    connection.execute(
        "INSERT INTO priorities VALUES (?, ?, ?)",
        (1771491223100, 55.0, PRIVATE_VALUES[0]),
    )
    connection.commit()
    connection.close()

    recorder = diagnostics.DiagnosticRecorder(
        str(addon_dir), profile, clock=lambda: 5.0, run_id="abcdef123456"
    )
    recorder.record(
        "review_answered",
        rating=3,
        card_type=2,
        queue=2,
        interval_days=4,
        card_text=PRIVATE_VALUES[0],
        card_id=1771491223100,
    )
    destination = tmp_path / "support.zip"
    result = diagnostics.build_support_bundle(
        destination,
        addon_dir=str(addon_dir),
        profile=profile,
        recorder=recorder,
        config={
            "topic_card_tags": [PRIVATE_VALUES[2]],
            "writing_external_app_custom_path": PRIVATE_VALUES[4],
            "dialog": {"session_card_count": 500, "topics_filter": PRIVATE_VALUES[2]},
        },
        default_config={"topic_card_tags": []},
        environment={
            "anki_version": "26.0.5",
            "addon_version": "1.2.3",
            "enabled_addons": 12,
            "username": PRIVATE_VALUES[1],
            "path": PRIVATE_VALUES[4],
        },
        runtime_state={
            "ui_state": "review",
            "incremento_session": {
                "active": True,
                "selected_count": 500,
                "reviewed_count": 3,
                "window_size": 40,
                "auto_refill": True,
                "card_id": 1771491223100,
                "card_text": PRIVATE_VALUES[0],
            },
        },
    )

    assert result["event_count"] == 1
    assert result["bundle_bytes"] > 0
    combined = _all_zip_text(destination)
    for private in PRIVATE_VALUES:
        assert private not in combined
    assert "1771491223100" not in combined
    assert "addon-owned-by-alice" not in combined

    with zipfile.ZipFile(destination) as archive:
        assert set(archive.namelist()) == {
            "README.txt",
            "manifest.json",
            "config/sanitized.json",
            "diagnostics/environment.json",
            "diagnostics/current_state.json",
            "diagnostics/recorder_status.json",
            "diagnostics/database_summary.json",
            "diagnostics/code_fingerprints.json",
            "diagnostics/events.jsonl",
        }
        manifest = json.loads(archive.read("manifest.json"))
        database = json.loads(archive.read("diagnostics/database_summary.json"))
        recorder_status = json.loads(archive.read("diagnostics/recorder_status.json"))
        events = archive.read("diagnostics/events.jsonl").decode("utf-8")
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())

    assert manifest["privacy"]["card_or_note_text"] is False
    assert manifest["privacy"]["absolute_event_timestamps"] is False
    assert database["tables"]["priorities"]["present"] is True
    assert database["tables"]["priorities"]["row_count"] == 1
    assert database["tables"]["priorities"]["column_count"] == 3
    assert len(database["schema_fingerprint_sha256"]) == 64
    assert recorder_status["dropped_events"] == 0
    assert recorder_status["last_flush_complete"] is True
    assert '"rating":3' in events
    assert "private_text" not in combined
    assert recorder.close()


def test_safe_exception_type_never_includes_exception_message() -> None:
    exc = RuntimeError(f"failed for {PRIVATE_VALUES[4]}")
    assert diagnostics.safe_exception_type(exc) == "RuntimeError"

    class AlicePrivateFailure(Exception):
        pass

    assert diagnostics.safe_exception_type(AlicePrivateFailure("private")) == "UnknownError"


def test_environment_versions_reject_free_text() -> None:
    snapshot = diagnostics.safe_environment_snapshot(
        {
            "anki_version": PRIVATE_VALUES[1],
            "addon_version": PRIVATE_VALUES[6],
            "operating_system": "Darwin",
            "operating_system_release": PRIVATE_VALUES[0],
            "architecture": "arm64",
        }
    )
    assert snapshot["anki_version"] == "unknown"
    assert snapshot["addon_version"] == "unknown"
    assert snapshot["operating_system_release"] == "unknown"


def test_incremento_menu_wires_the_support_bundle_action() -> None:
    source = (Path(__file__).resolve().parents[1] / "__init__.py").read_text(
        encoding="utf-8"
    )
    assert 'QAction("Export Support Bundle…", mw)' in source
    assert "qconnect(_supportBundleAction.triggered, exportSupportBundleFunction)" in source
    support_export = source.split("def exportSupportBundleFunction()", 1)[1].split(
        "def _extract_card()", 1
    )[0]
    assert "uses_collection=False" in support_export
    assert "_register_topic_diagnostic_event_callback(_record_diagnostic_event)" in source
    assert "_register_custom_schedule_diagnostic_event_callback(_record_diagnostic_event)" in source
    assert "_diagnostic_pending_final_interval" in source
    answer_logger = source.split("def _record_diagnostic_answer", 1)[1].split(
        "def _close_diagnostic_profile", 1
    )[0]
    assert "mw.col.get_card" not in answer_logger
