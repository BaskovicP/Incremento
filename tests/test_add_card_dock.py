import add_card_dock as dock


class _FakeWindow:
    def __init__(self):
        self.set_menu_bar_args = []

    def setMenuBar(self, menu_bar):
        self.set_menu_bar_args.append(menu_bar)


def test_detach_embedded_window_menu_bar_removes_native_menu():
    window = _FakeWindow()

    dock._detach_embedded_window_menu_bar(window)

    assert window.set_menu_bar_args == [None]


def test_configured_extract_notetype_name_reads_config_value():
    assert dock.configured_extract_notetype_name({"extract_notetype": "Basic"}) == "Basic"
    assert dock.configured_extract_notetype_name({"extract_notetype": ""}) == ""
    assert dock.configured_extract_notetype_name({}) == ""


def test_configured_extract_source_links_supports_bool_backcompat():
    assert dock.configured_extract_source_links({"extract_source_links": True}) == {
        "pdf": True,
        "epub": True,
        "web": True,
        "parent": True,
    }
    assert dock.configured_extract_source_links({"extract_source_links": False}) == {
        "pdf": False,
        "epub": False,
        "web": False,
        "parent": False,
    }


def test_configured_extract_source_links_merges_partial_dict():
    assert dock.configured_extract_source_links(
        {"extract_source_links": {"pdf": False, "web": True}}
    ) == {
        "pdf": False,
        "epub": True,
        "web": True,
        "parent": True,
    }


def test_should_add_extract_source_link_reads_specific_kind():
    cfg = {"extract_source_links": {"pdf": False, "web": True, "parent": False}}
    assert dock.should_add_extract_source_link("pdf", cfg) is False
    assert dock.should_add_extract_source_link("web", cfg) is True
    assert dock.should_add_extract_source_link("parent", cfg) is False
    assert dock.should_add_extract_source_link("unknown", cfg) is True


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
