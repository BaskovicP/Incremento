import importlib.util
import os


def _load():
    path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "frontend", "tag_colors.py")
    )
    spec = importlib.util.spec_from_file_location("_incremento_tag_colors", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_mod = _load()


def test_tag_color_is_case_insensitive_and_ignores_hash_prefix():
    assignments = _mod.assign_unique_tag_chip_colors(["topic", " #TOPIC "])
    assert list(assignments) == ["topic"]


def test_common_tags_receive_a_usefully_varied_palette():
    assignments = _mod.assign_unique_tag_chip_colors(
        ("topic", "psychology", "spiritual", "science", "history", "item")
    )
    assert len(set(assignments.values())) == 6


def test_tag_chip_stylesheet_contains_stable_color_and_legible_text():
    color = _mod.tag_chip_color_for_index(1)
    stylesheet = _mod.tag_chip_stylesheet(color)

    assert color in stylesheet
    assert "color: #FFFFFF" in stylesheet
    assert "border-radius" in stylesheet


def test_visible_tags_receive_unique_major_colors_even_when_hashes_collide():
    tags = ["habits", "psychology", "topic", "spiritual", "item"]
    assignments = _mod.assign_unique_tag_chip_colors(tags)

    assert len(set(assignments.values())) == len(tags)
    assert assignments["habits"] != assignments["psychology"]


def test_topic_uses_reserved_green_without_colliding_with_other_tags():
    assignments = _mod.assign_unique_tag_chip_colors(
        ["spiritual", "data", "topic", "psychology"]
    )

    assert assignments["topic"] == "#2E7D32"
    assert len(set(assignments.values())) == len(assignments)


def test_color_index_mapping_is_stable_and_extensible():
    assert _mod.tag_chip_color_for_index(0) == _mod.tag_chip_color_for_index(0)
    assert _mod.tag_chip_color_for_index(100).startswith("#")
    assert len(_mod.tag_chip_color_for_index(100)) == 7

    first_thousand = [_mod.tag_chip_color_for_index(index) for index in range(1000)]
    assert len(set(first_thousand)) == len(first_thousand)


def test_light_custom_color_uses_dark_text():
    stylesheet = _mod.tag_chip_stylesheet("#FFF59D")
    assert "color: #111111" in stylesheet
