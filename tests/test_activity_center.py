from pathlib import Path

from frontend.activity_center import activity_progress_text, activity_status_text


ROOT = Path(__file__).resolve().parents[1]


def test_activity_labels_are_plain_and_explain_indeterminate_work():
    assert activity_status_text("running") == "Running"
    assert activity_status_text("failed") == "Failed"
    assert activity_progress_text(None, "running") == "Working…"
    assert activity_progress_text(0.426, "running") == "43%"
    assert activity_progress_text(1, "succeeded") == "Complete"


def test_activity_center_dialog_and_entrypoint_are_wired():
    dialog_source = (ROOT / "frontend" / "activity_center.py").read_text(
        encoding="utf-8"
    )
    entrypoint = (ROOT / "__init__.py").read_text(encoding="utf-8")
    settings = (ROOT / "frontend" / "settings_dialog.py").read_text(
        encoding="utf-8"
    )

    assert "self._activity_tree" in dialog_source
    assert "self._cancel_button" in dialog_source
    assert "self._retry_button" in dialog_source
    assert "self._refresh_timer" in dialog_source
    assert "Activity Center…" in entrypoint
    assert '"id": "activity_center"' in settings


def test_long_running_pdf_index_and_video_download_report_to_activity_center():
    search = (ROOT / "frontend" / "search_all.py").read_text(encoding="utf-8")
    video = (ROOT / "frontend" / "video_dock.py").read_text(encoding="utf-8")

    for source in (search, video):
        assert "start_activity" in source
        assert "update_activity" in source
        assert "finish_activity" in source
        assert "fail_activity" in source
