import importlib.util
import sys
import types
from datetime import date, datetime
from pathlib import Path

from i18n import Translator


def _load_dialog(filename: str):
    path = Path(__file__).resolve().parents[1] / "frontend" / filename
    spec = importlib.util.spec_from_file_location(f"i18n_test_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


postpone = _load_dialog("knowledge_tree_postpone_dialog.py")
priority = _load_dialog("knowledge_tree_priority_dialog.py")

_original_launcher = sys.modules.get("session_launcher")
sys.modules["session_launcher"] = types.SimpleNamespace(learnFunction=lambda **_kwargs: None)
try:
    subset = _load_dialog("knowledge_tree_subset_dialog.py")
finally:
    if _original_launcher is None:
        sys.modules.pop("session_launcher", None)
    else:
        sys.modules["session_launcher"] = _original_launcher


def test_postpone_summary_formats_structured_counts_through_catalog(monkeypatch):
    monkeypatch.setattr(postpone, "t", lambda key, **values: f"{key}:{values}", raising=False)
    monkeypatch.setattr(postpone, "tn", lambda key, count, **values: f"{key}:{count}", raising=False)
    result = postpone._format_postpone_summary({"elements_to_postpone": 2})
    assert "reader_postpone_elements" in result
    assert "reader_postpone_average_delay" in result


def test_priority_stats_translate_counts_without_changing_values(monkeypatch):
    monkeypatch.setattr(priority, "t", lambda key, **values: f"{key}:{values}", raising=False)
    monkeypatch.setattr(priority, "tn", lambda key, count, **values: f"{key}:{count}", raising=False)
    result = priority._priority_stats_text({"total_count": 3, "descendant_count": 2}, "0")
    assert "reader_tree_priority_stats" in result
    assert "reader_tree_priority_total_cards:3" in result


def test_subset_summary_translates_scope_and_count(monkeypatch):
    monkeypatch.setattr(subset, "t", lambda key, **values: f"{key}:{values}", raising=False)
    monkeypatch.setattr(subset, "tn", lambda key, count, **values: f"{key}:{count}:{values}", raising=False)
    result = subset._subset_summary_text("中文标题", 2, True)
    assert "reader_tree_subset_summary" in result
    assert "中文标题" in result


def test_tree_action_catalogs_translate_plurals_and_keep_user_title():
    hr = Translator("hr")
    zh = Translator("zh-Hans")
    assert hr.tn("reader_tree_priority_affected_count", 1) == "To će utjecati na 1 karticu."
    assert hr.tn("reader_tree_priority_affected_count", 2) == "To će utjecati na 2 kartice."
    assert hr.tn("reader_tree_priority_affected_count", 5) == "To će utjecati na 5 kartica."
    assert zh.tn("reader_tree_subset_summary", 2, title="中文标题", scope="整个子树") == "中文标题 · 2 张卡片，范围：整个子树。"
    assert priority.OP_SHIFT_SUBTREE == "shift_subtree"
    assert priority.OP_RANDOMIZE == "randomize_subtree"


def test_subset_review_dates_use_locale_formatter_without_changing_status(monkeypatch):
    monkeypatch.setattr(subset, "format_date", lambda value: f"localized:{value.isoformat()}")
    timestamp = datetime(2026, 9, 13).timestamp()
    assert subset._localized_review_day("Sep 13, 2026", timestamp) == "localized:2026-09-13"
    assert subset._localized_review_day("Sep 13, 2026", date(2026, 9, 13).toordinal()) == "localized:2026-09-13"
    assert subset._localized_review_day("Suspended", float("inf")) == "Suspended"
    assert subset._localized_review_day("739508", 739508) == "739508"


def test_subset_fallback_title_translates_without_touching_card_identity(monkeypatch):
    monkeypatch.setattr(subset, "t", lambda key, **values: f"卡片 {values['number']}")
    row = {"card_id": 42, "title": "Card 42", "display_title": "    Card 42"}
    assert subset._display_subset_title(row) == "    卡片 42"
    assert row["card_id"] == 42
    assert row["title"] == "Card 42"
