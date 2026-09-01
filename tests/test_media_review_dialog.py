import importlib.util
import os
import sys
import types

import aqt
import media_review


_ADDON_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _load_dialog_module(monkeypatch):
    class _DialogBase:
        def __init__(self, *_args, **_kwargs):
            pass

    qt_module = sys.modules["aqt.qt"]
    for name in (
        "QComboBox",
        "QDialogButtonBox",
        "QFormLayout",
        "QLabel",
        "QSpinBox",
        "QVBoxLayout",
    ):
        monkeypatch.setattr(qt_module, name, type(name, (), {}), raising=False)
    monkeypatch.setattr(qt_module, "QDialog", _DialogBase, raising=False)
    monkeypatch.setattr(qt_module, "qconnect", lambda *_args: None, raising=False)
    monkeypatch.setattr(aqt, "mw", object(), raising=False)

    session_stub = types.ModuleType("session")
    session_stub.start_explicit_review_from_selector = lambda *_args, **_kwargs: True
    session_stub.record_media_review_inspection_started = lambda *_args: None
    session_stub.record_media_review_inspection_finished = lambda *_args: None
    session_stub.record_media_review_inspection_failed = lambda *_args: None
    monkeypatch.setitem(sys.modules, "session", session_stub)
    monkeypatch.setitem(sys.modules, "media_review", media_review)

    module_name = "media_review_dialog_under_test"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(
        module_name,
        os.path.join(_ADDON_ROOT, "frontend", "media_review_dialog.py"),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_launcher_previews_then_passes_all_selected_options_to_background_card_selector(
    monkeypatch,
):
    module = _load_dialog_module(monkeypatch)
    query_calls = []
    inspection_calls = []
    resolver_calls = []
    review_calls = []
    diagnostic_calls = []
    classifier = object()

    class _AcceptedDialog:
        def __init__(self, parent, **kwargs):
            assert kwargs["media_label"] == "PDF"
            assert kwargs["media_kind"] == "pdf"
            assert kwargs["current_position"] == 7
            assert kwargs["initial_options"]["order"] == media_review.MEDIA_REVIEW_ORDER_ATTACHED
            assert kwargs["initial_options"]["include_filtered"] is False
            assert kwargs["preview_rows"] == [{"card_id": 30}]

        def exec(self):
            return True

        def selected_options(self):
            return {
                "order": media_review.MEDIA_REVIEW_ORDER_CREATED_NEWEST,
                "card_kind": media_review.MEDIA_REVIEW_CARD_KIND_TOPICS,
                "tree_scope": media_review.MEDIA_REVIEW_TREE_DIRECT,
                "media_range": media_review.MEDIA_REVIEW_RANGE_TO_CURRENT,
                "state": media_review.MEDIA_REVIEW_STATE_DUE,
                "limit": 12,
                "include_filtered": True,
            }

    monkeypatch.setattr(module, "MediaAttachedReviewDialog", _AcceptedDialog)
    monkeypatch.setattr(module, "resolve_topic_card_classifier", lambda: classifier)
    monkeypatch.setattr(
        module,
        "inspect_linked_media_review_rows",
        lambda *args, **kwargs: inspection_calls.append((args, kwargs)) or [{"card_id": 30}],
    )
    monkeypatch.setattr(
        module,
        "linked_media_review_card_ids",
        lambda *args, **kwargs: resolver_calls.append((args, kwargs)) or [30, 20],
    )
    monkeypatch.setattr(
        module,
        "start_explicit_review_from_selector",
        lambda selector, **kwargs: review_calls.append((selector, kwargs)) or True,
    )
    monkeypatch.setattr(
        module,
        "record_media_review_inspection_started",
        lambda content_kind: diagnostic_calls.append(("started", content_kind)),
    )
    monkeypatch.setattr(
        module,
        "record_media_review_inspection_finished",
        lambda content_kind, count: diagnostic_calls.append(
            ("finished", content_kind, count)
        ),
    )
    monkeypatch.setattr(
        module,
        "_run_media_review_query",
        lambda **kwargs: query_calls.append(kwargs),
    )
    module._last_options_by_media_kind["Profile\0pdf"] = {
        **module._default_options(),
        "include_filtered": True,
    }

    assert module.start_attached_media_review(
        addon_dir="/addon",
        profile="Profile",
        source_card_id=55,
        media_label="PDF",
        media_kind="pdf",
        deck_name="Incremento PDF Review",
        current_position=7,
        linked_note_ids=[101, 102],
        linked_card_ids=[201],
        parent=object(),
    ) is True

    assert review_calls == []
    fake_col = object()
    preview_rows = query_calls[0]["op"](fake_col)
    query_calls[0]["success"](preview_rows)
    assert inspection_calls[0][1]["topic_classifier"] is classifier
    assert diagnostic_calls == [("started", "pdf"), ("finished", "pdf", 1)]

    selector, review_kwargs = review_calls[0]
    assert selector(fake_col) == [30, 20]
    resolver_kwargs = resolver_calls[0][1]
    assert resolver_calls[0][0] == ("/addon", "Profile", 55)
    assert resolver_kwargs["col"] is fake_col
    assert resolver_kwargs["media_kind"] == "pdf"
    assert resolver_kwargs["order"] == media_review.MEDIA_REVIEW_ORDER_CREATED_NEWEST
    assert resolver_kwargs["card_kind"] == media_review.MEDIA_REVIEW_CARD_KIND_TOPICS
    assert resolver_kwargs["tree_scope"] == media_review.MEDIA_REVIEW_TREE_DIRECT
    assert resolver_kwargs["media_range"] == media_review.MEDIA_REVIEW_RANGE_TO_CURRENT
    assert resolver_kwargs["state"] == media_review.MEDIA_REVIEW_STATE_DUE
    assert resolver_kwargs["limit"] == 12
    assert resolver_kwargs["include_filtered"] is True
    assert resolver_kwargs["current_position"] == 7
    assert resolver_kwargs["linked_note_ids"] == (101, 102)
    assert resolver_kwargs["linked_card_ids"] == (201,)
    assert resolver_kwargs["include_tree_descendants"] is True
    assert resolver_kwargs["topic_classifier"] is classifier
    assert review_kwargs["deck_name"] == "Incremento PDF Review"
    assert review_kwargs["preserve_order"] is True
    assert review_kwargs["release_from_other_filtered_decks"] is True
    assert "Topic/Item" in review_kwargs["empty_message"]
    assert review_kwargs["diagnostic_source"] == "media_review"
    assert review_kwargs["diagnostic_content_kind"] == "pdf"
    assert review_kwargs["diagnostic_media_order"] == "created_newest"
    assert review_kwargs["diagnostic_media_card_kind"] == "topics"
    assert review_kwargs["diagnostic_media_tree_scope"] == "direct"
    assert review_kwargs["diagnostic_media_range"] == "to_current"
    assert review_kwargs["diagnostic_media_state"] == "due"
    assert review_kwargs["diagnostic_limit"] == 12
    assert module._last_options_by_media_kind["Profile\0pdf"]["include_filtered"] is False


def test_filtered_deck_option_defaults_off_and_normalizes_boolean(monkeypatch):
    module = _load_dialog_module(monkeypatch)

    assert module._default_options()["include_filtered"] is False
    assert module._normalized_options({"include_filtered": 1})["include_filtered"] is True


def test_reclaiming_filtered_cards_leaves_active_reviewer_before_deck_mutation(
    monkeypatch,
):
    module = _load_dialog_module(monkeypatch)
    query_calls = []
    review_calls = []
    deferred = []
    moved = []

    class _AcceptedDialog:
        def __init__(self, *_args, **_kwargs):
            pass

        def exec(self):
            return True

        def selected_options(self):
            return {
                "order": "attached",
                "card_kind": "both",
                "tree_scope": "nested",
                "media_range": "all",
                "state": "all",
                "limit": 0,
                "include_filtered": True,
            }

    monkeypatch.setattr(module, "MediaAttachedReviewDialog", _AcceptedDialog)
    monkeypatch.setattr(module, "resolve_topic_card_classifier", lambda: object())
    monkeypatch.setattr(
        module,
        "inspect_linked_media_review_rows",
        lambda *_args, **_kwargs: [{"card_id": 30, "availability": "filtered"}],
    )
    monkeypatch.setattr(
        module,
        "start_explicit_review_from_selector",
        lambda *_args, **_kwargs: review_calls.append(_kwargs) or True,
    )
    monkeypatch.setattr(
        module,
        "_run_media_review_query",
        lambda **kwargs: query_calls.append(kwargs),
    )
    monkeypatch.setattr(
        module,
        "mw",
        types.SimpleNamespace(
            state="review",
            moveToState=lambda state: moved.append(state),
        ),
    )
    monkeypatch.setattr(
        module,
        "QTimer",
        types.SimpleNamespace(
            singleShot=lambda delay, callback: deferred.append((delay, callback))
        ),
        raising=False,
    )

    assert module.start_attached_media_review(
        addon_dir="/addon",
        profile="Profile",
        source_card_id=55,
        media_label="PDF",
        media_kind="pdf",
        deck_name="Incremento PDF Review",
        parent=object(),
    )
    preview_rows = query_calls[0]["op"](object())
    query_calls[0]["success"](preview_rows)

    assert moved == ["overview"]
    assert review_calls == []
    assert deferred[0][0] == 0

    deferred[0][1]()
    assert review_calls[0]["release_from_other_filtered_decks"] is True


def test_preview_text_reports_selected_topic_item_counts_and_exclusions(monkeypatch):
    module = _load_dialog_module(monkeypatch)

    text = module.format_media_review_preview(
        {
            "selected_count": 3,
            "topic_count": 1,
            "item_count": 2,
            "exclusions": {
                "suspended": 1,
                "filtered": 2,
                "not_due": 4,
            },
        }
    )

    assert "3 cards (1 topic, 2 items)" in text
    assert "1 suspended" in text
    assert "2 already in another filtered deck" in text
    assert "4 not due now" in text


def test_preview_warns_when_filtered_cards_will_be_moved(monkeypatch):
    module = _load_dialog_module(monkeypatch)

    text = module.format_media_review_preview(
        {
            "selected_count": 2,
            "topic_count": 0,
            "item_count": 2,
            "selected_filtered_count": 2,
            "exclusions": {},
        }
    )

    assert "2 cards currently in other filtered decks" in text
    assert "all cards in those decks" in text


def test_filtered_deck_warning_names_every_deck_that_will_be_emptied(monkeypatch):
    module = _load_dialog_module(monkeypatch)

    text = module.format_filtered_deck_impact(
        [
            {"deck_id": 91, "deck_name": "Filtered Work", "selected_count": 2},
            {"deck_id": 92, "deck_name": "Language Queue", "selected_count": 1},
        ]
    )

    assert "Filtered Work (2 selected)" in text
    assert "Language Queue (1 selected)" in text
    assert "Every card in these filtered decks" in text


def test_result_row_explains_type_position_and_exclusion(monkeypatch):
    module = _load_dialog_module(monkeypatch)

    result = module.media_review_result_cells(
        {
            "card_label": "Why does this work?",
            "is_topic": False,
            "media_position": 73,
            "exclusion_reason": "not_due",
        },
        media_kind="video",
    )

    assert result == (
        "Why does this work?",
        "Item",
        "1:13",
        "Not due now",
    )


def test_review_all_dialog_source_contains_ready_and_excluded_result_groups(monkeypatch):
    module = _load_dialog_module(monkeypatch)
    source = open(module.__file__, encoding="utf-8").read()

    assert "self._ready_tree" in source
    assert "self._excluded_tree" in source
    assert "_populate_result_trees" in source
    assert "_accept_review" in source


def test_inspection_failure_is_forwarded_to_privacy_safe_diagnostics(monkeypatch):
    module = _load_dialog_module(monkeypatch)
    query_calls = []
    diagnostic_calls = []
    shown = []
    monkeypatch.setattr(module, "resolve_topic_card_classifier", lambda: object())
    monkeypatch.setattr(
        module,
        "_run_media_review_query",
        lambda **kwargs: query_calls.append(kwargs),
    )
    monkeypatch.setattr(
        module,
        "record_media_review_inspection_started",
        lambda kind: diagnostic_calls.append(("started", kind)),
    )
    monkeypatch.setattr(
        module,
        "record_media_review_inspection_failed",
        lambda kind, exc: diagnostic_calls.append(("failed", kind, type(exc).__name__)),
    )
    monkeypatch.setattr(module, "showInfo", shown.append)

    assert module.start_attached_media_review(
        addon_dir="/addon",
        profile="Profile",
        source_card_id=55,
        media_label="Video",
        media_kind="video",
        deck_name="Incremento Video Review",
    )
    query_calls[0]["failure"](RuntimeError("private media filename"))

    assert diagnostic_calls == [
        ("started", "video"),
        ("failed", "video", "RuntimeError"),
    ]
    assert "Could not inspect cards" in shown[0]


def test_query_runner_uses_current_anki_queryop_constructor(monkeypatch):
    module = _load_dialog_module(monkeypatch)
    calls = []

    class _FakeQueryOp:
        def __init__(self, *, parent, op, success):
            calls.append(("init", parent, op, success))

        def failure(self, callback):
            calls.append(("failure", callback))
            return self

        def with_progress(self, label):
            calls.append(("progress", label))
            return self

        def run_in_background(self):
            calls.append(("run",))

    operations_module = types.ModuleType("aqt.operations")
    operations_module.QueryOp = _FakeQueryOp
    monkeypatch.setitem(sys.modules, "aqt.operations", operations_module)
    parent = object()
    op = lambda _col: []
    success = lambda _rows: None
    failure = lambda _exc: None

    module._run_media_review_query(
        parent=parent,
        op=op,
        success=success,
        failure=failure,
    )

    assert calls == [
        ("init", parent, op, success),
        ("failure", failure),
        ("progress", "Inspecting attached cards…"),
        ("run",),
    ]
