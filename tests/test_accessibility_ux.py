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
    assert 'aria-label="PDF reader controls"' in source
    assert 'aria-live="polite"' in source
    assert 'aria-label="Previous PDF page"' in source
    assert 'aria-label="Next PDF page"' in source
    assert 'aria-label="Zoom out"' in source
    assert 'aria-label="Zoom in"' in source


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

    assert "Go to previous onboarding step" in onboarding
    assert "Go to next onboarding step" in onboarding
    assert "Include cards from other filtered decks" in media_review
    assert "Start attached-card review" in media_review
    assert "Show completed background activity" in activity
