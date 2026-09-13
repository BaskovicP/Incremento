import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


ROOT = Path(__file__).resolve().parents[1]


def test_package_reader_shell_uses_initialized_locale_without_top_level_backend():
    script = dedent("""
        import os
        import sys
        import types
        from pathlib import Path

        root = Path(os.environ["INCREMENTO_TEST_ROOT"])
        for name, path in (
            ("incremento", root),
            ("incremento.backend", root / "backend"),
            ("incremento.frontend", root / "frontend"),
        ):
            package = types.ModuleType(name)
            package.__path__ = [str(path)]
            sys.modules[name] = package

        from incremento.backend.i18n import initialize_language
        initialize_language("hr", "en")
        from incremento.frontend.reader_shell import reader_shell_spec
        assert reader_shell_spec("pdf")[0].label == "Natrag"
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd="/private/tmp",
        env={**os.environ, "INCREMENTO_TEST_ROOT": str(ROOT)},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_epub_video_and_web_apply_the_shared_pdf_reader_shell_contract():
    for filename in ("epub_dock.py", "video_dock.py", "web_dock.py"):
        source = (ROOT / "frontend" / filename).read_text(encoding="utf-8")
        assert "configure_reader_shell_buttons(" in source, filename


def test_epub_reader_uses_pdf_style_bottom_customizable_controls():
    source = (ROOT / "frontend" / "epub_dock.py").read_text(encoding="utf-8")
    build_start = source.index("def _build_epub_dock()")
    build_end = source.index("\ndef _current_epub_section_title()", build_start)
    build_source = source[build_start:build_end]

    document_position = build_source.index("layout.addWidget(view, stretch=1)")
    controls_position = build_source.index("layout.addWidget(dock._controls_host)")

    assert document_position < controls_position
    assert 't("reader_customize_controls")' in build_source
    assert 't("reader_minimize_controls_label")' in build_source
    assert "reader_toolbar_clone_spec(\"epub\")" in build_source
    assert "reader_toolbar_expanded_group_rows(\"epub\")" in build_source
    assert "_make_epub_compound_group(" in build_source
    assert "_make_epub_toolbar_stack(" in build_source
    assert 't("reader_navigate")' in build_source
    assert 't("reader_zoom")' in build_source
    assert 't("reader_reading")' in build_source
    assert "_make_epub_progress_meter(" in build_source
    for label_id in ("reader_annotate", "reader_capture", "reader_review", "reader_cards", "reader_status"):
        assert f't("{label_id}")' in build_source
    for control_name in (
        "_location_btn",
        "_text_scale_lbl",
        "_read_to_here_btn",
        "_read_range_chip",
        "_progress_percent_lbl",
        "_progress_segments",
        "_highlight_color_buttons",
        "_highlights_btn",
        "_page_cards_btn",
        "_limit_status_widget",
        "_compact_location_btn",
        "_compact_scale_lbl",
    ):
        assert control_name in build_source
    assert "_set_epub_controls_collapsed" in build_source
    assert "_control_group_rows" in build_source


def test_epub_pdf_clone_keeps_subgroups_horizontal_and_scopes_group_styling():
    source = (ROOT / "frontend" / "epub_dock.py").read_text(encoding="utf-8")
    stack_start = source.index("def _make_epub_toolbar_stack(")
    stack_end = source.index("\ndef _make_epub_toolbar_separator(", stack_start)
    stack_source = source[stack_start:stack_end]
    group_start = source.index("def _make_epub_compound_group(")
    group_end = source.index("\ndef _epub_read_progress_state(", group_start)
    group_source = source[group_start:group_end]

    assert "actions_row = QHBoxLayout(actions)" in stack_source
    assert "_FlowLayout(actions" not in stack_source
    assert 'frame.setObjectName("incremento_epub_toolbar_group")' in group_source
    assert "QFrame#incremento_epub_toolbar_group" in group_source
    assert '"QFrame {"' not in group_source


def test_epub_buttons_use_the_pdf_default_geometry_and_colors():
    source = (ROOT / "frontend" / "epub_dock.py").read_text(encoding="utf-8")
    button_start = source.index("def _make_epub_button(")
    button_end = source.index("\ndef _make_epub_chip(", button_start)
    button_source = source[button_start:button_end]

    assert '" padding: 3px 12px;"' in button_source
    assert '" border-radius: 4px;"' in button_source
    assert '" border: 1px solid #555;"' in button_source
    assert '" background: #333;"' in button_source
    assert '" color: #ddd;"' in button_source
    assert '" font-size: 13px;"' in button_source


def test_epub_pdf_clone_centers_each_wrapped_reference_row():
    source = (ROOT / "frontend" / "epub_dock.py").read_text(encoding="utf-8")
    build_start = source.index("def _build_epub_dock()")
    build_end = source.index("\ndef _current_epub_section_title()", build_start)
    build_source = source[build_start:build_end]

    assert "center_lines=True" in build_source


def test_epub_pdf_clone_uses_reference_text_instead_of_platform_icons():
    source = (ROOT / "frontend" / "epub_dock.py").read_text(encoding="utf-8")
    build_start = source.index("def _build_epub_dock()")
    build_end = source.index("\ndef _current_epub_section_title()", build_start)
    build_source = source[build_start:build_end]

    for action_id in (
        "snapshot",
        "highlights",
        "bookmark",
        "review_due",
        "review_all",
        "reading_limit",
        "open_all_in_browser",
        "page_cards",
        "add_card",
        "finished_reading",
    ):
        assert f'_EPUB_TOOLBAR_TEXT["{action_id}"]' in build_source
    assert "icon=_standard_icon(" not in build_source


def test_epub_dynamic_counts_keep_the_pdf_text_and_icons_after_refresh():
    source = (ROOT / "frontend" / "epub_dock.py").read_text(encoding="utf-8")

    assert '_EPUB_TOOLBAR_TEXT["bookmarks"].format(count=len(bookmarks))' in source
    assert '_EPUB_TOOLBAR_TEXT["highlights"].format(count=len(highlights))' in source
    assert '_EPUB_TOOLBAR_TEXT["page_cards"].format(count=count)' in source
    assert '_EPUB_TOOLBAR_TEXT["clickable_links"].format(' in source


def test_epub_has_no_unlaid_search_button_over_the_native_close_control():
    source = (ROOT / "frontend" / "epub_dock.py").read_text(encoding="utf-8")
    build_start = source.index("def _build_epub_dock()")
    build_end = source.index("\ndef _current_epub_section_title()", build_start)
    build_source = source[build_start:build_end]

    assert "dock._find_btn" not in build_source
    assert "layout.addWidget(find_bar)" not in build_source
    assert "groups_layout.insertWidget(1, find_bar)" in build_source
    assert "legacy_controls_host.setVisible(False)" in build_source


def test_epub_find_row_matches_the_centered_pdf_find_position():
    source = (ROOT / "frontend" / "epub_dock.py").read_text(encoding="utf-8")
    build_start = source.index("def _build_epub_dock()")
    build_end = source.index("\ndef _current_epub_section_title()", build_start)
    build_source = source[build_start:build_end]
    find_start = build_source.index("find_bar = QWidget(")
    find_end = build_source.index("QShortcut(QKeySequence(\"Escape\")", find_start)
    find_source = build_source[find_start:find_end]

    assert "dock._find_input.setFixedWidth(260)" in find_source
    assert find_source.count("find_layout.addStretch(1)") == 2
    assert "find_layout.addWidget(dock._find_input, 1)" not in find_source


def test_shortcut_settings_surface_the_live_conflict_detector():
    source = (ROOT / "frontend" / "settings_dialog.py").read_text(encoding="utf-8")

    assert "find_shortcut_conflicts(" in source
    assert "_shortcut_conflict_label" in source
    assert "_accept_if_shortcuts_valid" in source
