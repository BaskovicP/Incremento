import writing_dock


def test_configured_writing_defaults():
    assert writing_dock.configured_writing_wrap_enabled({}) is True
    assert writing_dock.configured_writing_focus_mode({}) is False
    assert writing_dock.configured_writing_highlight_current_line({}) is True
    assert writing_dock.configured_writing_restore_bookmark({}) is True
    assert writing_dock.configured_writing_progress_visible({}) is True
    assert writing_dock.configured_writing_progress_default_scope({}) == "today"
    assert writing_dock.configured_writing_word_count_mode({}) == "simple"


def test_configured_writing_flags_read_config_values():
    cfg = {
        "writing_wrap_enabled": False,
        "writing_focus_mode": True,
        "writing_highlight_current_line": False,
        "writing_restore_bookmark": False,
        "writing_progress_visible": False,
        "writing_progress_default_scope": "all_time",
        "writing_word_count_mode": "word_like",
    }
    assert writing_dock.configured_writing_wrap_enabled(cfg) is False
    assert writing_dock.configured_writing_focus_mode(cfg) is True
    assert writing_dock.configured_writing_highlight_current_line(cfg) is False
    assert writing_dock.configured_writing_restore_bookmark(cfg) is False
    assert writing_dock.configured_writing_progress_visible(cfg) is False
    assert writing_dock.configured_writing_progress_default_scope(cfg) == "all_time"
    assert writing_dock.configured_writing_word_count_mode(cfg) == "word_like"


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
