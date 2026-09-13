import writing_dock


def test_writing_bookmarks_localize_links_but_preserve_user_labels(monkeypatch):
    from types import SimpleNamespace
    from backend.i18n import Translator
    translator = Translator('hr')
    monkeypatch.setattr(writing_dock, 't', translator.t)
    html = []
    monkeypatch.setattr(writing_dock, '_writing_dock', SimpleNamespace(
        _bookmarks_btn=SimpleNamespace(setText=lambda value: None),
        _bookmarks_panel=SimpleNamespace(setHtml=html.append)))
    monkeypatch.setattr(writing_dock, '_writing_bookmarks', lambda: [
        {'id': 'bookmark-1', 'label': '<My bookmark>'}])
    writing_dock._refresh_writing_bookmarks_panel()
    assert '>Idi</a>' in html[-1] and '>Izbriši</a>' in html[-1]
    assert '&lt;My bookmark&gt;' in html[-1]
    assert 'inc://writing-bookmark-open/bookmark-1' in html[-1]
    monkeypatch.setattr(writing_dock, '_writing_bookmarks', lambda: [])
    writing_dock._refresh_writing_bookmarks_panel()
    assert 'No bookmarks yet' not in html[-1]
    assert 'Još nema' in html[-1]


def test_empty_markdown_placeholder_translates_but_selected_text_stays_unchanged(monkeypatch):
    from types import SimpleNamespace
    from backend.i18n import Translator
    monkeypatch.setattr(writing_dock, 't', Translator('zh-Hans').t)
    selected = ['']
    inserted = []
    cursor = SimpleNamespace(selectedText=lambda: selected[0], beginEditBlock=lambda: None,
                             endEditBlock=lambda: None, insertText=inserted.append)
    editor = SimpleNamespace(textCursor=lambda: cursor, setTextCursor=lambda value: None,
                             setFocus=lambda: None)
    monkeypatch.setattr(writing_dock, '_writing_dock', SimpleNamespace(_editor=editor))
    writing_dock._apply_markdown_transform('number')
    assert inserted[-1] == '1. 列表项'
    selected[0] = 'My original English text'
    writing_dock._apply_markdown_transform('number')
    assert inserted[-1] == '1. My original English text'


def test_configured_writing_defaults():
    assert writing_dock.configured_writing_wrap_enabled({}) is True
    assert writing_dock.configured_writing_focus_mode({}) is False
    assert writing_dock.configured_writing_preview_visible({}) is True
    assert writing_dock.configured_writing_highlight_current_line({}) is True
    assert writing_dock.configured_writing_restore_bookmark({}) is True
    assert writing_dock.configured_writing_backups_enabled({}) is True
    assert writing_dock.configured_writing_backup_tiers({}) == ("1m", "30m", "1d")
    assert writing_dock.configured_writing_progress_visible({}) is True
    assert writing_dock.configured_writing_progress_default_scope({}) == "today"
    assert writing_dock.configured_writing_word_count_mode({}) == "simple"


def test_configured_writing_flags_read_config_values():
    cfg = {
        "writing_wrap_enabled": False,
        "writing_focus_mode": True,
        "writing_preview_visible": False,
        "writing_highlight_current_line": False,
        "writing_restore_bookmark": False,
        "writing_backups_enabled": False,
        "writing_backup_tiers": ["5m", "1h", "7d"],
        "writing_progress_visible": False,
        "writing_progress_default_scope": "all_time",
        "writing_word_count_mode": "word_like",
    }
    assert writing_dock.configured_writing_wrap_enabled(cfg) is False
    assert writing_dock.configured_writing_focus_mode(cfg) is True
    assert writing_dock.configured_writing_preview_visible(cfg) is False
    assert writing_dock.configured_writing_highlight_current_line(cfg) is False
    assert writing_dock.configured_writing_restore_bookmark(cfg) is False
    assert writing_dock.configured_writing_backups_enabled(cfg) is False
    assert writing_dock.configured_writing_backup_tiers(cfg) == ("5m", "1h", "7d")
    assert writing_dock.configured_writing_progress_visible(cfg) is False
    assert writing_dock.configured_writing_progress_default_scope(cfg) == "all_time"
    assert writing_dock.configured_writing_word_count_mode(cfg) == "word_like"


def test_configured_writing_backup_tiers_falls_back_to_defaults_for_invalid_values():
    assert writing_dock.configured_writing_backup_tiers({"writing_backup_tiers": ["bogus"]}) == (
        "1m",
        "30m",
        "1d",
    )


def test_wrap_selection_text_uses_placeholder_for_empty_selection():
    assert writing_dock._wrap_selection_text("", "**", "**", "bold") == "**bold**"


def test_wrap_selection_text_normalizes_multiline_selection():
    assert writing_dock._wrap_selection_text("first\u2029second", "*", "*", "x") == "*first\nsecond*"


def test_prefix_lines_text_prefixes_each_line():
    assert writing_dock._prefix_lines_text("one\ntwo", "- ", "item") == "- one\n- two"


def test_prefix_lines_text_uses_placeholder_when_empty():
    assert writing_dock._prefix_lines_text("", "> ", "Quote") == "> Quote"


def test_clamp_font_scale_bounds_values():
    assert writing_dock._clamp_font_scale(-1) == 0.7
    assert writing_dock._clamp_font_scale(99) == 2.4
    assert writing_dock._clamp_font_scale("1.35") == 1.35


def test_count_words_simple_counts_plain_tokens():
    assert writing_dock._count_words("", "simple") == 0
    assert writing_dock._count_words("one two\nthree", "simple") == 3
    assert writing_dock._count_words("  markdown   words  ", "simple") == 2


def test_count_words_word_like_handles_punctuation_and_hyphens():
    assert writing_dock._count_words("state-of-the-art writing", "word_like") == 2
    assert writing_dock._count_words("don't stop believing", "word_like") == 3
    assert writing_dock._count_words("word... another", "word_like") == 2


def test_count_words_falls_back_to_simple_for_unknown_mode():
    assert writing_dock._count_words("one two", "unknown") == 2


def test_scope_label_formats_human_text():
    assert writing_dock._scope_label("today") == "Words today"
    assert writing_dock._scope_label("session") == "Words this session"
    assert writing_dock._scope_label("all_time") == "Words total"


def test_backup_timestamp_uses_the_locale_date_formatter(monkeypatch):
    monkeypatch.setattr(writing_dock, "format_date", lambda _value: "LOCAL-DATE")

    assert writing_dock._format_backup_timestamp(0).startswith("LOCAL-DATE ")
