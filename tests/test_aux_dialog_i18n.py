"""Browser and reviewer controls use the selected catalog language."""

import json

from backend.i18n import Translator
import reviewer_topic_actions


def test_activity_and_tag_controls_translate_with_tag_interpolation():
    tr = Translator("hr")
    assert tr.t("imports_activity_show_finished_accessible") == "Prikaži dovršene pozadinske aktivnosti"
    assert tr.t("imports_quick_tags_color_conflict", tag="biology") == "Tu boju već upotrebljava #biology. Odaberite drugu boju."
    assert Translator("zh-Hans").t("imports_reviewer_tags_title") == "追加标签"


def test_priority_and_extract_controls_translate_display_text():
    tr = Translator("hr")
    assert tr.t("imports_priority_title") == "Postavi prioritet"
    assert tr.t("imports_extract_title") == "Izdvoji karticu"
    assert Translator("zh-Hans").t("imports_topic_revisit_title") == "重新安排主题"


def test_topic_button_renders_selected_language_at_runtime(monkeypatch):
    monkeypatch.setattr(reviewer_topic_actions, "_t", Translator("hr").t)
    script = reviewer_topic_actions.build_topic_done_button_js("incremento_topic_done:one")
    assert f'button.textContent = {json.dumps("✓ Gotovo")}' in script
    assert json.dumps("Označi temu kao gotovu") in script
    assert 'const command = "incremento_topic_done:one"' in script
