from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_add_card_dock_has_autosave_recovery_and_visible_composer_language():
    source = (ROOT / "frontend" / "add_card_dock.py").read_text(encoding="utf-8")

    assert "save_extraction_draft" in source
    assert "load_extraction_draft" in source
    assert "_schedule_extract_draft_autosave" in source
    assert "_restore_extract_draft" in source
    assert 't("add_card_draft_accessible")' in source
    assert 't("add_card_extract_composer")' in source
    assert 't("add_card_draft_autosaves")' in source


def test_profile_path_helper_owns_the_extract_draft_location():
    source = (ROOT / "backend" / "paths.py").read_text(encoding="utf-8")

    assert "def get_extraction_draft_path" in source
