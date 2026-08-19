import importlib.util
import os


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(
        name,
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", relpath)),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load("_incremento_reviewer_tags", "backend/reviewer_tags.py")

append_missing_tags = _mod.append_missing_tags
filter_tags = _mod.filter_tags
normalize_tag_list = _mod.normalize_tag_list
deduplicate_tag_groups = _mod.deduplicate_tag_groups
recent_tag_groups_from_note_rows = _mod.recent_tag_groups_from_note_rows
tag_groups_with_new_tags = _mod.tag_groups_with_new_tags


def test_normalize_tag_list_dedupes_and_strips_hashes():
    assert normalize_tag_list(["  Biology ", "#biology", "Chemistry", ""]) == [
        "Biology",
        "Chemistry",
    ]


def test_normalize_tag_list_splits_common_manual_input_separators():
    assert normalize_tag_list("biology, chemistry; physics\nmath") == [
        "biology",
        "chemistry",
        "physics",
        "math",
    ]


def test_append_missing_tags_only_adds_new_values():
    updated, added = append_missing_tags(
        ["biology", "Chemistry"],
        ["chemistry", "Physics", "#Biology", "math"],
    )
    assert updated == ["biology", "Chemistry", "Physics", "math"]
    assert added == ["Physics", "math"]


def test_filter_tags_sorts_alphabetically_and_filters_by_query():
    assert filter_tags(["zeta", "Alpha", "beta", "alpine"], "al") == [
        "Alpha",
        "alpine",
    ]


def test_recent_tag_groups_from_note_rows_keeps_newest_first_and_deduplicates_sets():
    rows = [
        (" psychology topic ",),
        (" topic Psychology ",),
        (" spiritual topic ",),
        (" older ",),
    ]

    assert recent_tag_groups_from_note_rows(rows, limit=3) == [
        ["psychology", "topic"],
        ["spiritual", "topic"],
        ["older"],
    ]


def test_deduplicate_tag_groups_respects_limit_and_accepts_lists():
    assert deduplicate_tag_groups(
        [["one", "two"], ["three"], ["four"]],
        limit=2,
    ) == [
        ["one", "two"],
        ["three"],
    ]


def test_tag_groups_with_new_tags_ignores_known_tags_and_accepts_a_new_one():
    known = [["topic", "psychology"], ["spiritual", "topic"]]
    candidates = [
        ["psychology", "topic"],
        ["topic", "science"],
        ["science", "item"],
    ]

    assert tag_groups_with_new_tags(candidates, known) == [
        ["topic", "science"],
        ["science", "item"],
    ]
