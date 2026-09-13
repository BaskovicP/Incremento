from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_painted_statistics_charts_have_screen_reader_summaries():
    source = (ROOT / "frontend" / "stats_dialog.py").read_text(encoding="utf-8")

    assert "_accessible_chart_summary" in source
    assert source.count("setAccessibleDescription(") >= 3


def test_pdf_reader_has_visible_keyboard_focus_reduced_motion_and_live_statuses():
    source = (ROOT / "frontend" / "src" / "PdfViewer.jsx").read_text(
        encoding="utf-8"
    )

    assert ":focus-visible" in source
    assert "prefers-reduced-motion: reduce" in source
    assert 'role="toolbar"' in source
    assert 'aria-label={tr("reader_pdf_controls")}' in source
    assert 'aria-live="polite"' in source
    assert 'aria-label={tr("reader_previous_pdf_page")}' in source
    assert 'aria-label={tr("reader_next_pdf_page")}' in source
    assert 'aria-label={tr("reader_zoom_out")}' in source
    assert 'aria-label={tr("reader_zoom_in")}' in source


def test_new_ux_dialogs_name_primary_navigation_and_destructive_controls():
    onboarding = (ROOT / "frontend" / "onboarding_dialog.py").read_text(
        encoding="utf-8"
    )
    media_review = (ROOT / "frontend" / "media_review_dialog.py").read_text(
        encoding="utf-8"
    )
    activity = (ROOT / "frontend" / "activity_center.py").read_text(
        encoding="utf-8"
    )

    assert 'setAccessibleName(t("onboarding_back_accessible"))' in onboarding
    assert 'setAccessibleName(t("onboarding_next_accessible"))' in onboarding
    assert 't("reader_media_include_filtered_accessible")' in media_review
    assert 'setAccessibleName(t("reader_media_start_review_accessible"))' in media_review
    assert 'setAccessibleName(_t("imports_activity_show_finished_accessible"))' in activity
