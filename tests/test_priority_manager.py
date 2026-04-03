"""Tests for priority_manager functions in backend/priority_manager.py."""
import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "_incremento_priority_manager",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", "priority_manager.py")),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

get_priority = _mod.get_priority
set_priority = _mod.set_priority
get_all_priorities = _mod.get_all_priorities
configured_priority_lower_is_more_important = _mod.configured_priority_lower_is_more_important


class TestGetPriority:
    def test_default_when_not_set(self, tmp_path):
        assert get_priority(str(tmp_path), 101) == 50.0

    def test_returns_stored_value(self, tmp_path):
        set_priority(str(tmp_path), 42, 10.0)
        assert get_priority(str(tmp_path), 42) == 10.0

    def test_different_cards_independent(self, tmp_path):
        set_priority(str(tmp_path), 1, 25.0)
        set_priority(str(tmp_path), 2, 75.0)
        assert get_priority(str(tmp_path), 1) == 25.0
        assert get_priority(str(tmp_path), 2) == 75.0


class TestSetPriority:
    def test_overwrite_existing(self, tmp_path):
        set_priority(str(tmp_path), 7, 20.0)
        set_priority(str(tmp_path), 7, 80.0)
        assert get_priority(str(tmp_path), 7) == 80.0

    def test_rounds_to_four_decimal_places(self, tmp_path):
        set_priority(str(tmp_path), 99, 33.33333)
        result = get_priority(str(tmp_path), 99)
        assert result == round(33.33333, 4)

    def test_zero_priority(self, tmp_path):
        set_priority(str(tmp_path), 5, 0.0)
        assert get_priority(str(tmp_path), 5) == 0.0

    def test_max_priority(self, tmp_path):
        set_priority(str(tmp_path), 5, 100.0)
        assert get_priority(str(tmp_path), 5) == 100.0


class TestGetAllPriorities:
    def test_empty_when_none_set(self, tmp_path):
        assert get_all_priorities(str(tmp_path)) == {}

    def test_returns_all_entries(self, tmp_path):
        set_priority(str(tmp_path), 1, 10.0)
        set_priority(str(tmp_path), 2, 90.0)
        result = get_all_priorities(str(tmp_path))
        assert result == {1: 10.0, 2: 90.0}

    def test_keys_are_ints(self, tmp_path):
        set_priority(str(tmp_path), 100, 50.0)
        result = get_all_priorities(str(tmp_path))
        key = list(result.keys())[0]
        assert isinstance(key, int)


class TestConfiguredPriorityDirection:
    def test_defaults_to_lower_priority_more_important(self):
        assert configured_priority_lower_is_more_important({}) is True

    def test_reads_false_from_config(self):
        assert configured_priority_lower_is_more_important(
            {"priority_lower_is_more_important": False}
        ) is False
