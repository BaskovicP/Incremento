from frontend.session_setup_model import (
    BASIC_MODE,
    ADVANCED_MODE,
    format_basic_session_summary,
    normalize_setup_mode,
)


def test_basic_summary_explains_the_four_primary_session_choices():
    assert format_basic_session_summary(
        session_card_count=30,
        topics_slider=25,
        pdf_slider=80,
        preset_name="Work",
    ) == (
        "30 cards · Topics 75% / Items 25% · "
        "Documents 20% / Other 80% · Preset: Work"
    )


def test_basic_summary_handles_current_settings_and_bounds_dirty_values():
    assert format_basic_session_summary(
        session_card_count=20_000,
        topics_slider=-50,
        pdf_slider=150,
        preset_name="",
    ) == (
        "9,999 cards · Topics 100% / Items 0% · "
        "Documents 0% / Other 100% · Preset: Current Settings"
    )


def test_setup_mode_is_fail_closed_to_basic():
    assert normalize_setup_mode("advanced") == ADVANCED_MODE
    assert normalize_setup_mode(" BASIC ") == BASIC_MODE
    assert normalize_setup_mode("expert") == BASIC_MODE
