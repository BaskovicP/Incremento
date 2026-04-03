import add_card_dock as dock


def test_configured_extract_notetype_name_reads_config_value():
    assert dock.configured_extract_notetype_name({"extract_notetype": "Basic"}) == "Basic"
    assert dock.configured_extract_notetype_name({"extract_notetype": ""}) == ""
    assert dock.configured_extract_notetype_name({}) == ""


def test_should_apply_extract_notetype_only_for_blank_mismatched_note():
    assert dock.should_apply_extract_notetype(
        "Basic",
        "Cloze",
        note_has_content=False,
    )
    assert not dock.should_apply_extract_notetype(
        "Basic",
        "Basic",
        note_has_content=False,
    )
    assert not dock.should_apply_extract_notetype(
        "Basic",
        "Cloze",
        note_has_content=True,
    )
    assert not dock.should_apply_extract_notetype(
        "",
        "Cloze",
        note_has_content=False,
    )
