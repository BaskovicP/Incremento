"""Tests for SchedulerConfig and _config_from_dialog_dict in backend/scheduler_config.py."""
import importlib.util
import os
import sys

import pytest

_spec = importlib.util.spec_from_file_location(
    "_incremento_scheduler_config",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", "scheduler_config.py")),
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["_incremento_scheduler_config"] = _mod
_spec.loader.exec_module(_mod)

SchedulerConfig = _mod.SchedulerConfig
_config_from_dialog_dict = _mod._config_from_dialog_dict
NO_TAGS_KEY = _mod.NO_TAGS_KEY


class TestReadyFilter:
    def test_all_included(self):
        cfg = SchedulerConfig(include_new=True, include_learning=True, include_due=True)
        assert cfg.ready_filter == "(is:new OR is:learn OR is:due)"

    def test_only_new(self):
        cfg = SchedulerConfig(include_new=True, include_learning=False, include_due=False)
        assert cfg.ready_filter == "is:new"

    def test_only_learning(self):
        cfg = SchedulerConfig(include_new=False, include_learning=True, include_due=False)
        assert cfg.ready_filter == "is:learn"

    def test_only_due(self):
        cfg = SchedulerConfig(include_new=False, include_learning=False, include_due=True)
        assert cfg.ready_filter == "is:due"

    def test_new_and_due(self):
        cfg = SchedulerConfig(include_new=True, include_learning=False, include_due=True)
        assert cfg.ready_filter == "(is:new OR is:due)"

    def test_all_false_fallback(self):
        cfg = SchedulerConfig(include_new=False, include_learning=False, include_due=False)
        assert cfg.ready_filter == "is:new"


class TestConfigFromDialogDict:
    def test_empty_dict_gives_defaults(self):
        cfg = _config_from_dialog_dict({})
        assert cfg.session_card_count == 50
        assert cfg.topics_rate == pytest.approx(1.0 - 10 / 100)
        assert cfg.random_rate == pytest.approx(99 / 100)
        assert cfg.use_tags is False
        assert cfg.tag_weights == {}
        assert cfg.include_rest is True
        assert cfg.scheduler_scope == "session"
        assert cfg.day_end_time == "00:00"
        assert cfg.priority_order == ["tags", "type", "mode"]
        assert cfg.enforce_priority is True
        assert cfg.topics_filter == ""
        assert cfg.items_filter == ""
        assert cfg.include_new is True
        assert cfg.include_learning is True
        assert cfg.include_due is True
        assert cfg.preserve_order is True
        assert cfg.show_debug is False
        assert cfg.pdf_rate == pytest.approx(0.0)
        assert cfg.priority_lower_is_more_important is True
        assert cfg.priority_order_enabled is False
        assert cfg.priority_order_entries == []
        assert cfg.prioritized_tags_first == []
        assert cfg.prioritized_tags_mode == "exhaust"

    def test_session_card_count(self):
        cfg = _config_from_dialog_dict({"session_card_count": 100})
        assert cfg.session_card_count == 100

    def test_topics_slider_sets_rate(self):
        # topics_slider=20 → topics_rate = 1.0 - 20/100 = 0.8
        cfg = _config_from_dialog_dict({"topics_slider": 20})
        assert cfg.topics_rate == pytest.approx(0.8)

    def test_random_slider_sets_rate(self):
        cfg = _config_from_dialog_dict({"random_slider": 50})
        assert cfg.random_rate == pytest.approx(0.5)

    def test_tag_rows_excluded_no_tags_key(self):
        """Rows with NO_TAGS_KEY tag should not appear in tag_weights."""
        rows = [
            {"tag": NO_TAGS_KEY, "weight": 30},
            {"tag": "health", "weight": 20},
        ]
        cfg = _config_from_dialog_dict({"tag_rows": rows})
        assert NO_TAGS_KEY not in cfg.tag_weights
        assert cfg.tag_weights == {"health": pytest.approx(0.2)}
        assert cfg.use_tags is True

    def test_no_tag_rows_means_use_tags_false(self):
        cfg = _config_from_dialog_dict({"tag_rows": []})
        assert cfg.use_tags is False

    def test_include_rest_from_no_tags_checked(self):
        cfg = _config_from_dialog_dict({"no_tags_checked": False})
        assert cfg.include_rest is False

    def test_pdf_slider_sets_rate(self):
        cfg = _config_from_dialog_dict({"pdf_slider": 25})
        assert cfg.pdf_rate == pytest.approx(0.25)

    def test_migrate_old_topics_filter(self):
        cfg = _config_from_dialog_dict({"topics_filter": "deck:Topics"})
        assert cfg.topics_filter == ""

    def test_migrate_old_items_filter(self):
        cfg = _config_from_dialog_dict({"items_filter": "-deck:Topics"})
        assert cfg.items_filter == ""

    def test_migrate_old_tag_aware_defaults_to_empty_filters(self):
        cfg = _config_from_dialog_dict(
            {
                "topics_filter": "deck:Topics OR tag:Incremento",
                "items_filter": "-deck:Topics -tag:Incremento",
            }
        )
        assert cfg.topics_filter == ""
        assert cfg.items_filter == ""

    def test_custom_filters_not_migrated(self):
        cfg = _config_from_dialog_dict({
            "topics_filter": "deck:Science",
            "items_filter": "-deck:Science",
        })
        assert cfg.topics_filter == "deck:Science"
        assert cfg.items_filter == "-deck:Science"

    def test_scheduler_scope_and_day_end(self):
        cfg = _config_from_dialog_dict({"scheduler_scope": "daily", "day_end_time": "04:00"})
        assert cfg.scheduler_scope == "daily"
        assert cfg.day_end_time == "04:00"

    def test_enforce_priority_false(self):
        cfg = _config_from_dialog_dict({"enforce_priority": False})
        assert cfg.enforce_priority is False

    def test_priority_direction_false(self):
        cfg = _config_from_dialog_dict({"priority_lower_is_more_important": False})
        assert cfg.priority_lower_is_more_important is False

    def test_include_flags(self):
        cfg = _config_from_dialog_dict({"include_new": False, "include_due": False})
        assert cfg.include_new is False
        assert cfg.include_due is False
        assert cfg.include_learning is True  # default

    def test_prioritized_tags_are_cleaned_and_deduped(self):
        cfg = _config_from_dialog_dict(
            {
                "prioritized_tags_first": [" active_writing ", "Focus", "focus", ""],
                "prioritized_tags_mode": "unsupported",
            }
        )
        assert cfg.prioritized_tags_first == ["active_writing", "Focus"]
        assert cfg.prioritized_tags_mode == "exhaust"
        assert cfg.priority_order_enabled is True
        assert cfg.priority_order_entries == [
            {"kind": "tag", "value": "active_writing", "order": 1},
            {"kind": "tag", "value": "Focus", "order": 2},
        ]

    def test_priority_order_entries_are_cleaned(self):
        cfg = _config_from_dialog_dict(
            {
                "priority_order_enabled": True,
                "priority_order_entries": [
                    {"kind": "tag", "value": " Focus ", "order": "2"},
                    {"kind": "tag", "value": "focus", "order": 3},
                    {"kind": "tag", "value": NO_TAGS_KEY, "order": 1},
                    {"kind": "content_type", "value": "PDF", "order": "1"},
                    {"kind": "content_type", "value": "unknown", "order": 1},
                    {"kind": "content_type", "value": "youtube", "order": "bad"},
                ],
            }
        )

        assert cfg.priority_order_enabled is True
        assert cfg.priority_order_entries == [
            {"kind": "tag", "value": "Focus", "order": 2},
            {"kind": "content_type", "value": "pdf", "order": 1},
        ]

    def test_priority_order_values_from_rows_are_preserved_when_checkbox_off(self):
        cfg = _config_from_dialog_dict(
            {
                "priority_order_enabled": False,
                "tag_rows": [{"tag": "writing", "weight": 20, "order": 1}],
                "content_type_rows": [{"type": "webpage", "enabled": True, "weight": 10, "order": 2}],
            }
        )

        assert cfg.priority_order_enabled is False
        assert cfg.priority_order_entries == [
            {"kind": "tag", "value": "writing", "order": 1},
            {"kind": "content_type", "value": "webpage", "order": 2},
        ]
