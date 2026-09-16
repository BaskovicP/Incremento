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
        "Within Topics: Documents 20% / Other 80% · "
        "Target: 5 Documents + 18 other Topics + 7 Items · Preset: Work"
    )


def test_basic_summary_handles_current_settings_and_bounds_dirty_values():
    assert format_basic_session_summary(
        session_card_count=20_000,
        topics_slider=-50,
        pdf_slider=150,
        preset_name="",
    ) == (
        "9,999 cards · Topics 100% / Items 0% · "
        "Within Topics: Documents 0% / Other 100% · "
        "Target: 0 Documents + 9999 other Topics + 0 Items · Preset: Current Settings"
    )


def test_items_only_summary_shows_no_document_topics_but_retains_all_items():
    assert format_basic_session_summary(
        session_card_count=100, topics_slider=100, pdf_slider=10, preset_name="Items",
    ) == (
        "100 cards · Topics 0% / Items 100% · Within Topics: Documents 0% / Other 100% · "
        "Target: 0 Documents + 0 other Topics + 100 Items · Preset: Items"
    )


def test_basic_summary_uses_the_i18n_message_boundary(monkeypatch):
    import frontend.session_setup_model as model

    seen = []

    def translate(message_id, **values):
        seen.append((message_id, values))
        return "localized summary"

    monkeypatch.setattr(model, "t", translate)

    assert model.format_basic_session_summary(
        session_card_count=30,
        topics_slider=25,
        pdf_slider=80,
        preset_name="Work",
    ) == "localized summary"
    assert seen == [
        (
            "session_basic_summary",
            {
                "count": 30,
                "topic_percent": 75,
                "item_percent": 25,
                "document_percent": 20,
                "other_percent": 80,
                "preset": "Work",
                "document_count": 5,
                "other_topic_count": 18,
                "item_count": 7,
            },
        )
    ]


def test_basic_summary_uses_the_croatian_catalog(monkeypatch):
    import frontend.session_setup_model as model
    from backend.i18n import Translator

    monkeypatch.setattr(model, "t", Translator("hr").t)

    assert model.format_basic_session_summary(
        session_card_count=30,
        topics_slider=25,
        pdf_slider=80,
        preset_name="Work",
    ) == (
        "30 kartica · Teme 75% / Stavke 25% · Unutar tema: Dokumenti 20% / Ostalo 80% "
        "· Cilj: 5 dokumenata + 18 ostalih tema + 7 stavki · Predložak: Work"
    )


def test_setup_mode_is_fail_closed_to_basic():
    assert normalize_setup_mode("advanced") == ADVANCED_MODE
    assert normalize_setup_mode(" BASIC ") == BASIC_MODE
    assert normalize_setup_mode("expert") == BASIC_MODE
