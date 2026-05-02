"""Tests for video_manager and web_manager backend functions."""
import importlib.util
import os

import db
import pytest

# ── Load modules by path to avoid Qt dependency ──────────────────────────────

def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(
        name,
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", relpath)),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_vm = _load("_incremento_video_manager", "backend/video_manager.py")
_wm = _load("_incremento_web_manager", "backend/web_manager.py")
_nm = _load("_incremento_note_metadata", "backend/note_metadata.py")

extract_video_id = _vm.extract_video_id
extract_vimeo_id = _vm.extract_vimeo_id
extract_video_key = _vm.extract_video_key
is_supported_video_url = _vm.is_supported_video_url
extract_start_seconds = _vm.extract_start_seconds
canonicalize_video_url = _vm.canonicalize_video_url
build_remote_video_watch_url = _vm.build_remote_video_watch_url
resolve_video_url_for_embed = _vm.resolve_video_url_for_embed
supports_browser_cookie_auth = _vm.supports_browser_cookie_auth
provider_display_name = _vm.provider_display_name
fmt_time = _vm.fmt_time
get_video_position = _vm.get_video_position
set_video_position = _vm.set_video_position
local_video_relpath = _vm.local_video_relpath
local_video_abspath = _vm.local_video_abspath
video_download_requirements = _vm.video_download_requirements
parse_ytdlp_percent = _vm._parse_ytdlp_percent
hms_to_seconds = _vm._hms_to_seconds
ytdlp_format_selector = _vm._ytdlp_format_selector
extract_resolutions_from_info = _vm._extract_resolutions_from_info
supported_local_video_extensions = _vm.supported_local_video_extensions
supported_subtitle_extensions = _vm.supported_subtitle_extensions
extract_subtitle_tracks_from_info = _vm._extract_subtitle_tracks_from_info
parse_subtitle_cues = _vm.parse_subtitle_cues
import_local_subtitle_file = _vm.import_local_subtitle_file
load_subtitle_cues = _vm.load_subtitle_cues
get_video_note_media = _vm.get_video_note_media
update_video_note_media = _vm.update_video_note_media
TARGET_SUBTITLE_FILE_FIELD = _vm.TARGET_SUBTITLE_FILE_FIELD
TARGET_SUBTITLE_LABEL_FIELD = _vm.TARGET_SUBTITLE_LABEL_FIELD
REFERENCE_SUBTITLE_FILE_FIELD = _vm.REFERENCE_SUBTITLE_FILE_FIELD
REFERENCE_SUBTITLE_LABEL_FIELD = _vm.REFERENCE_SUBTITLE_LABEL_FIELD
VIDEO_SUBTITLE_FIELDS = _vm.VIDEO_SUBTITLE_FIELDS

get_web_url = _wm.get_web_url
set_web_url = _wm.set_web_url
build_external_web_url = _wm.build_external_web_url
get_web_progress = _wm.get_web_progress
set_web_scroll_position = _wm.set_web_scroll_position
set_web_bookmark = _wm.set_web_bookmark
set_web_media_progress = _wm.set_web_media_progress
configured_remember_browser_card_scroll = _wm.configured_remember_browser_card_scroll
build_web_restore_payload = _wm.build_web_restore_payload
build_web_media_resume_target = _wm.build_web_media_resume_target
reviewer_web_homepage_action = _wm.reviewer_web_homepage_action
build_reviewer_web_home_button_js = _wm.build_reviewer_web_home_button_js
SOURCE_LINK_FIELD = _nm.INCREMENTO_SOURCE_LINK_FIELD
SOURCE_TYPE_FIELD = _nm.INCREMENTO_SOURCE_TYPE_FIELD


# ── extract_video_id ──────────────────────────────────────────────────────────

class TestExtractVideoId:
    def test_standard_watch_url(self):
        assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_url(self):
        assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_embed_url(self):
        assert extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        assert extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_live_url(self):
        assert extract_video_id("https://www.youtube.com/live/dQw4w9WgXcQ?feature=share") == "dQw4w9WgXcQ"

    def test_url_with_extra_params(self):
        assert extract_video_id("https://youtube.com/watch?v=abcdefghijk&t=30") == "abcdefghijk"

    def test_plain_video_id(self):
        assert extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_url_encoded_wrapper(self):
        url = "https://www.youtube.com/attribution_link?a=1&u=%2Fwatch%3Fv%3DdQw4w9WgXcQ%26feature%3Dshare"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_returns_none_for_invalid_url(self):
        assert extract_video_id("https://example.com/video") is None

    def test_returns_none_for_empty_string(self):
        assert extract_video_id("") is None


class TestVimeoVideoParsing:
    def test_standard_vimeo_url(self):
        assert extract_vimeo_id("https://vimeo.com/148751763") == "148751763"

    def test_player_vimeo_url(self):
        assert extract_vimeo_id("https://player.vimeo.com/video/148751763") == "148751763"

    def test_channel_vimeo_url(self):
        assert extract_vimeo_id("https://vimeo.com/channels/staffpicks/148751763") == "148751763"

    def test_plain_vimeo_id(self):
        assert extract_vimeo_id("148751763") == "148751763"

    def test_vimeo_invalid(self):
        assert extract_vimeo_id("https://example.com/video") is None

    def test_supported_video_url_youtube_and_vimeo(self):
        assert is_supported_video_url("https://youtu.be/dQw4w9WgXcQ")
        assert is_supported_video_url("https://vimeo.com/148751763")
        assert not is_supported_video_url("https://example.com/video")

    def test_extract_video_key_youtube_compat(self):
        assert extract_video_key("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_extract_video_key_vimeo_prefixed(self):
        assert extract_video_key("https://vimeo.com/148751763") == "vimeo_148751763"

    def test_build_remote_watch_url_youtube(self):
        assert (
            build_remote_video_watch_url("https://youtu.be/dQw4w9WgXcQ", start_sec=44)
            == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=44s&autoplay=0"
        )

    def test_build_remote_watch_url_vimeo(self):
        assert (
            build_remote_video_watch_url("https://vimeo.com/148751763", start_sec=44)
            == "https://player.vimeo.com/video/148751763#t=44s"
        )

    def test_build_remote_watch_url_vimeo_uses_embedded_time_when_no_saved_position(self):
        assert (
            build_remote_video_watch_url(
                "https://player.vimeo.com/video/1173597756?title=0#t=21m23s",
                start_sec=0,
            )
            == "https://player.vimeo.com/video/1173597756?title=0#t=1283s"
        )

    def test_extract_start_seconds_hms_fragment(self):
        assert extract_start_seconds("https://vimeo.com/1173597756#t=21m23s") == 1283

    def test_extract_start_seconds_query_seconds(self):
        assert extract_start_seconds("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=4463s") == 4463

    def test_canonicalize_video_url_vimeo_player(self):
        assert (
            canonicalize_video_url(
                "https://player.vimeo.com/video/1173597756?title=0&byline=0#t=21m23s"
            )
            == "https://player.vimeo.com/video/1173597756?title=0&byline=0#t=1283s"
        )

    def test_canonicalize_video_url_vimeo_preserves_h_token(self):
        assert (
            canonicalize_video_url(
                "https://player.vimeo.com/video/1173597756?h=abc123&t=9s"
            )
            == "https://player.vimeo.com/video/1173597756?h=abc123#t=9s"
        )

    def test_canonicalize_video_url_vimeo_strips_wmode(self):
        assert (
            canonicalize_video_url(
                "https://player.vimeo.com/video/1177424090?title=0&byline=0&portrait=0&wmode=transparent&h=abc123"
            )
            == "https://player.vimeo.com/video/1177424090?title=0&byline=0&portrait=0&h=abc123"
        )

    def test_canonicalize_vimeo_unescapes_amp_query(self):
        assert (
            canonicalize_video_url(
                "https://player.vimeo.com/video/1177424090?title=0&amp;byline=0&amp;portrait=0&amp;wmode=transparent"
            )
            == "https://player.vimeo.com/video/1177424090?title=0&byline=0&portrait=0"
        )

    def test_extract_vimeo_embed_url_from_html_prefers_h(self):
        html = """
        <script>
          window.playerConfig = {"video":{"embed_code":"<iframe src=\\"https://player.vimeo.com/video/1177424090?h=abc123\\"></iframe>"}};
        </script>
        """
        got = _vm._extract_vimeo_embed_url_from_html(html, "1177424090")
        assert got == "https://player.vimeo.com/video/1177424090?h=abc123"

    def test_resolve_video_url_for_embed_merges_h_token(self, monkeypatch):
        _vm._VIMEO_EMBED_CACHE.clear()

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'<iframe src="https://player.vimeo.com/video/1177424090?h=abc123"></iframe>'

        monkeypatch.setattr(_vm, "urlopen", lambda *_args, **_kwargs: _Resp())
        url = "https://player.vimeo.com/video/1177424090?title=0"
        got = resolve_video_url_for_embed(url, timeout_sec=0.1)
        assert got == "https://player.vimeo.com/video/1177424090?title=0&h=abc123"

    def test_resolve_video_url_for_embed_fallback_on_network_error(self, monkeypatch):
        _vm._VIMEO_EMBED_CACHE.clear()
        monkeypatch.setattr(_vm, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(Exception("boom")))
        url = "https://player.vimeo.com/video/1177424090?title=0"
        got = resolve_video_url_for_embed(url, timeout_sec=0.1)
        assert got == "https://player.vimeo.com/video/1177424090?title=0"

    def test_cookie_auth_provider_split(self):
        assert supports_browser_cookie_auth("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert not supports_browser_cookie_auth("https://vimeo.com/148751763")

    def test_provider_display_name(self):
        assert provider_display_name("https://vimeo.com/148751763") == "Vimeo"
        assert provider_display_name("https://youtu.be/dQw4w9WgXcQ") == "YouTube"


# ── local video helpers ───────────────────────────────────────────────────────

class TestLocalVideoHelpers:
    def test_relpath_uses_videos_subfolder(self):
        assert local_video_relpath("dQw4w9WgXcQ") == "videos/dQw4w9WgXcQ.mp4"

    def test_unique_target_path_uses_uuid_suffix(self, tmp_path):
        got = _vm._unique_target_path(tmp_path, "lesson clip", ".mp4")
        assert got.parent == tmp_path
        assert got.name.startswith("lesson_clip-")
        assert got.suffix == ".mp4"

    def test_unique_target_path_truncates_long_stem_before_uuid_suffix(self, tmp_path):
        got = _vm._unique_target_path(tmp_path, "x" * 140, ".mp4")
        base, _, suffix = got.stem.rpartition("-")
        assert len(base) <= 80
        assert len(suffix) == 32

    def test_abspath_accepts_user_files_prefix(self, tmp_path):
        # "user_files/" prefix is stripped; path resolves under user_files/<profile>/
        got = local_video_abspath(str(tmp_path), "TestProfile", "user_files/videos/a.mp4")
        assert got == os.path.join(str(tmp_path), "user_files", "TestProfile", "videos", "a.mp4")

    def test_video_download_requirements_reports_missing_tools(self, monkeypatch):
        monkeypatch.setattr(_vm, "_yt_dlp_cmd", lambda allow_auto_install=False: None)
        monkeypatch.setattr(_vm.shutil, "which", lambda _name: None)
        assert video_download_requirements() == ["yt-dlp", "ffmpeg (optional for compression)"]

    def test_parse_ytdlp_percent(self):
        assert parse_ytdlp_percent("[download]  23.4% of 10.00MiB") == pytest.approx(23.4)

    def test_parse_ytdlp_percent_invalid(self):
        assert parse_ytdlp_percent("some other output") is None

    def test_hms_to_seconds(self):
        assert hms_to_seconds("01:02:03.5") == pytest.approx(3723.5)

    def test_hms_to_seconds_invalid(self):
        assert hms_to_seconds("n/a") is None

    def test_ytdlp_selector_prefers_h264_when_not_compressing(self):
        fmt = ytdlp_format_selector("download")
        assert "vcodec^=avc1" in fmt
        assert "acodec^=mp4a" in fmt

    def test_ytdlp_selector_uses_best_split_when_compressing(self):
        assert ytdlp_format_selector("compressible") == (
            "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[acodec^=mp4a]/"
            "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
            "bestvideo+bestaudio/"
            "best[vcodec!=none][acodec!=none]/"
            "best[vcodec!=none][acodec!=none]"
        )

    def test_ytdlp_selector_applies_height_cap_download(self):
        fmt = ytdlp_format_selector("download", max_height=720)
        assert "[height<=720]" in fmt
        assert "best[ext=mp4][height<=720][vcodec^=avc1][acodec^=mp4a]" in fmt

    def test_ytdlp_selector_applies_height_cap_compressible(self):
        fmt = ytdlp_format_selector("compressible", max_height=1080)
        assert "bestvideo[height<=1080][vcodec^=avc1][ext=mp4]+bestaudio[acodec^=mp4a]" in fmt
        assert "bestvideo[height<=1080]+bestaudio" in fmt
        assert "best[height<=1080][vcodec!=none][acodec!=none]" in fmt

    def test_ytdlp_selector_original_quality_mode(self):
        fmt = ytdlp_format_selector("original", max_height=2160)
        assert "bestvideo[height<=2160]+bestaudio" in fmt
        assert "vcodec^=avc1" not in fmt

    def test_ytdlp_selector_vimeo_download_prefers_mp4_aac(self):
        fmt = ytdlp_format_selector("download", max_height=1080, provider="vimeo")
        assert "best[ext=mp4][height<=1080][vcodec^=avc1][acodec^=mp4a]" in fmt
        assert "best[ext=mp4][height<=1080][acodec!=none]" in fmt

    def test_extract_resolutions_from_info(self):
        info = {
            "formats": [
                {"vcodec": "avc1.64001f", "height": 720},
                {"vcodec": "none", "height": 720},
                {"vcodec": "av01.0.08M.08", "height": 1080},
                {"vcodec": "vp9", "height": 1080},
                {"vcodec": "avc1", "height": 480},
                {"vcodec": "avc1", "height": None},
            ]
        }
        assert extract_resolutions_from_info(info) == [1080, 720, 480]

    def test_supported_local_video_extensions(self):
        exts = supported_local_video_extensions()
        assert ".mp4" in exts
        assert ".mkv" in exts


class TestSubtitleHelpers:
    def test_supported_subtitle_extensions(self):
        assert supported_subtitle_extensions() == (".srt", ".vtt")

    def test_extract_subtitle_tracks_from_info_prefers_manual_then_auto(self):
        info = {
            "subtitles": {
                "en": [{"ext": "vtt", "name": "English"}],
                "de": [{"ext": "srt"}],
            },
            "automatic_captions": {
                "en": [{"ext": "vtt", "name": "English auto"}],
            },
        }
        tracks = extract_subtitle_tracks_from_info(info)
        assert [track["track_id"] for track in tracks] == ["manual:de", "manual:en", "auto:en"]
        assert tracks[1]["label"] == "English [en] (manual)"
        assert tracks[2]["label"] == "English auto [en] (auto)"

    def test_parse_subtitle_cues_handles_srt(self):
        text = (
            "1\n"
            "00:00:01,000 --> 00:00:02,500\n"
            "Hello there\n\n"
            "2\n"
            "00:00:03,000 --> 00:00:05,000\n"
            "General Kenobi\n"
        )
        cues = parse_subtitle_cues(text, format_hint=".srt")
        assert cues == [
            {"start": 1.0, "end": 2.5, "text": "Hello there"},
            {"start": 3.0, "end": 5.0, "text": "General Kenobi"},
        ]

    def test_parse_subtitle_cues_handles_vtt_header_and_settings(self):
        text = (
            "WEBVTT\n\n"
            "00:00:01.000 --> 00:00:04.000 line:85%\n"
            "Target line\n"
        )
        cues = parse_subtitle_cues(text, format_hint=".vtt")
        assert cues == [{"start": 1.0, "end": 4.0, "text": "Target line"}]

    def test_import_local_subtitle_file_copies_into_profile_videos_dir(self, tmp_path):
        src = tmp_path / "lesson.srt"
        src.write_text("1\n00:00:01,000 --> 00:00:02,000\nHola\n", encoding="utf-8")
        relpath = import_local_subtitle_file(str(tmp_path), "TestProfile", str(src), preferred_stem="lesson-target")
        assert relpath.startswith("videos/lesson-target-")
        stored = load_subtitle_cues(str(tmp_path), "TestProfile", relpath)
        assert stored == [{"start": 1.0, "end": 2.0, "text": "Hola"}]

    def test_get_and_update_video_note_media_round_trip(self):
        class _Note(dict):
            pass

        note = _Note(
            {
                "Local_Video_File": "",
                TARGET_SUBTITLE_FILE_FIELD: "",
                TARGET_SUBTITLE_LABEL_FIELD: "",
                REFERENCE_SUBTITLE_FILE_FIELD: "",
                REFERENCE_SUBTITLE_LABEL_FIELD: "",
            }
        )
        changed = update_video_note_media(
            note,
            local_video_file="videos/example.mp4",
            target_subtitle_file="videos/example-target.vtt",
            target_subtitle_label="English",
            reference_subtitle_file="videos/example-reference.vtt",
            reference_subtitle_label="Croatian",
        )
        assert changed is True
        assert get_video_note_media(note) == {
            "local_video_file": "videos/example.mp4",
            "target_subtitle_file": "videos/example-target.vtt",
            "target_subtitle_label": "English",
            "reference_subtitle_file": "videos/example-reference.vtt",
            "reference_subtitle_label": "Croatian",
        }


# ── fmt_time ──────────────────────────────────────────────────────────────────

class TestFmtTime:
    def test_zero(self):
        assert fmt_time(0) == "0:00"

    def test_seconds_only(self):
        assert fmt_time(45) == "0:45"

    def test_one_minute(self):
        assert fmt_time(60) == "1:00"

    def test_minutes_and_seconds(self):
        assert fmt_time(90) == "1:30"

    def test_one_hour(self):
        assert fmt_time(3600) == "1:00:00"

    def test_hours_minutes_seconds(self):
        assert fmt_time(3723) == "1:02:03"

    def test_truncates_fractional_seconds(self):
        assert fmt_time(61.9) == "1:01"


# ── get/set_video_position ────────────────────────────────────────────────────

class TestVideoPosition:
    def test_default_when_not_set(self, tmp_path):
        assert get_video_position(str(tmp_path), "TestProfile", 1) == 0.0

    def test_stores_and_retrieves_position(self, tmp_path):
        set_video_position(str(tmp_path), "TestProfile", 1, 123.4)
        assert get_video_position(str(tmp_path), "TestProfile", 1) == pytest.approx(123.4)

    def test_overwrites_existing(self, tmp_path):
        set_video_position(str(tmp_path), "TestProfile", 1, 10.0)
        set_video_position(str(tmp_path), "TestProfile", 1, 99.9)
        assert get_video_position(str(tmp_path), "TestProfile", 1) == pytest.approx(99.9)

    def test_rounds_to_one_decimal(self, tmp_path):
        set_video_position(str(tmp_path), "TestProfile", 2, 55.555)
        assert get_video_position(str(tmp_path), "TestProfile", 2) == pytest.approx(round(55.555, 1))

    def test_different_cards_independent(self, tmp_path):
        set_video_position(str(tmp_path), "TestProfile", 1, 10.0)
        set_video_position(str(tmp_path), "TestProfile", 2, 20.0)
        assert get_video_position(str(tmp_path), "TestProfile", 1) == pytest.approx(10.0)
        assert get_video_position(str(tmp_path), "TestProfile", 2) == pytest.approx(20.0)


# ── get/set_web_url ───────────────────────────────────────────────────────────

class TestWebUrl:
    def test_default_when_not_set(self, tmp_path):
        assert get_web_url(str(tmp_path), "TestProfile", 1) == ""
        assert get_web_progress(str(tmp_path), "TestProfile", 1) == {
            "url": "",
            "scroll_ratio": 0.0,
            "bookmark_url": "",
            "bookmark_payload": {},
            "media_url": "",
            "media_title": "",
            "media_seconds": 0.0,
            "media_updated_at": 0,
        }

    def test_stores_and_retrieves_url(self, tmp_path):
        set_web_url(str(tmp_path), "TestProfile", 1, "https://example.com")
        assert get_web_url(str(tmp_path), "TestProfile", 1) == "https://example.com"
        assert get_web_progress(str(tmp_path), "TestProfile", 1)["url"] == "https://example.com"

    def test_overwrites_existing(self, tmp_path):
        set_web_url(str(tmp_path), "TestProfile", 1, "https://old.com")
        set_web_url(str(tmp_path), "TestProfile", 1, "https://new.com")
        assert get_web_url(str(tmp_path), "TestProfile", 1) == "https://new.com"

    def test_different_cards_independent(self, tmp_path):
        set_web_url(str(tmp_path), "TestProfile", 1, "https://a.com")
        set_web_url(str(tmp_path), "TestProfile", 2, "https://b.com")
        assert get_web_url(str(tmp_path), "TestProfile", 1) == "https://a.com"
        assert get_web_url(str(tmp_path), "TestProfile", 2) == "https://b.com"

    def test_empty_string_stored(self, tmp_path):
        set_web_url(str(tmp_path), "TestProfile", 1, "https://example.com")
        set_web_url(str(tmp_path), "TestProfile", 1, "")
        assert get_web_url(str(tmp_path), "TestProfile", 1) == ""

    def test_scroll_position_updates_url_and_ratio_without_clearing_bookmark(self, tmp_path):
        set_web_bookmark(str(tmp_path), "TestProfile", 1,
            url="https://example.com/ch1",
            bookmark_payload={
                "path": [0, 1],
                "offsetRatio": 0.25,
                "scrollRatio": 0.4,
                "tag": "p",
                "text": "Chapter 1",
            },
        )
        set_web_scroll_position(str(tmp_path), "TestProfile", 1, "https://example.com/ch2", 0.65)
        progress = get_web_progress(str(tmp_path), "TestProfile", 1)
        assert progress["url"] == "https://example.com/ch2"
        assert progress["scroll_ratio"] == pytest.approx(0.65)
        assert progress["bookmark_url"] == "https://example.com/ch1"
        assert progress["bookmark_payload"]["path"] == [0, 1]

    def test_bookmark_overwrites_existing_bookmark(self, tmp_path):
        set_web_bookmark(str(tmp_path), "TestProfile", 1,
            url="https://example.com/first",
            bookmark_payload={"path": [0], "offsetRatio": 0.1, "scrollRatio": 0.2},
        )
        set_web_bookmark(str(tmp_path), "TestProfile", 1,
            url="https://example.com/second",
            bookmark_payload={"path": [2, 3], "offsetRatio": 0.7, "scrollRatio": 0.8},
        )
        progress = get_web_progress(str(tmp_path), "TestProfile", 1)
        assert progress["bookmark_url"] == "https://example.com/second"
        assert progress["bookmark_payload"]["path"] == [2, 3]
        assert progress["bookmark_payload"]["offsetRatio"] == pytest.approx(0.7)

    def test_selection_bookmark_round_trips_selection_fields(self, tmp_path):
        set_web_bookmark(str(tmp_path), "TestProfile", 1,
            url="https://example.com/selection",
            bookmark_payload={
                "mode": "selection",
                "path": [1, 2],
                "offsetRatio": 0.3,
                "scrollRatio": 0.4,
                "tag": "span",
                "text": "selected text",
                "selectionStartPath": [1, 2, 0],
                "selectionStartOffset": 5,
                "selectionEndPath": [1, 2, 1],
                "selectionEndOffset": 9,
            },
        )
        progress = get_web_progress(str(tmp_path), "TestProfile", 1)
        assert progress["bookmark_url"] == "https://example.com/selection"
        assert progress["bookmark_payload"]["mode"] == "selection"
        assert progress["bookmark_payload"]["selectionStartPath"] == [1, 2, 0]
        assert progress["bookmark_payload"]["selectionStartOffset"] == 5
        assert progress["bookmark_payload"]["selectionEndPath"] == [1, 2, 1]
        assert progress["bookmark_payload"]["selectionEndOffset"] == 9

    def test_can_clear_bookmark(self, tmp_path):
        set_web_bookmark(str(tmp_path), "TestProfile", 1,
            url="https://example.com/first",
            bookmark_payload={"path": [0], "offsetRatio": 0.1, "scrollRatio": 0.2},
        )
        set_web_bookmark(str(tmp_path), "TestProfile", 1, url="https://example.com/first", bookmark_payload=None)
        progress = get_web_progress(str(tmp_path), "TestProfile", 1)
        assert progress["bookmark_url"] == ""
        assert progress["bookmark_payload"] == {}

    def test_media_progress_round_trips(self, tmp_path):
        set_web_media_progress(
            str(tmp_path),
            "TestProfile",
            1,
            url="https://example.com/article",
            media_url="https://player.vimeo.com/video/148751763",
            media_title="Example clip",
            media_seconds=83.2,
            media_updated_at=1234567890,
        )
        progress = get_web_progress(str(tmp_path), "TestProfile", 1)
        assert progress["url"] == "https://example.com/article"
        assert progress["media_url"] == "https://player.vimeo.com/video/148751763"
        assert progress["media_title"] == "Example clip"
        assert progress["media_seconds"] == pytest.approx(83.2)
        assert progress["media_updated_at"] == 1234567890

    def test_media_progress_ignores_non_positive_seconds(self, tmp_path):
        set_web_media_progress(
            str(tmp_path),
            "TestProfile",
            1,
            url="https://example.com/article",
            media_seconds=44,
        )
        set_web_media_progress(
            str(tmp_path),
            "TestProfile",
            1,
            url="https://example.com/article",
            media_seconds=0,
        )
        progress = get_web_progress(str(tmp_path), "TestProfile", 1)
        assert progress["media_seconds"] == pytest.approx(44.0)

    def test_media_progress_falls_back_to_browser_media_ref(self, tmp_path):
        db.set_card_browser_media_ref(
            str(tmp_path),
            "TestProfile",
            1,
            page_url="https://example.com/article",
            media_url="https://player.example.com/video",
            media_title="Embedded video",
            media_seconds=127,
            updated_at=1234567890,
        )
        set_web_url(str(tmp_path), "TestProfile", 1, "https://example.com/article")

        progress = get_web_progress(str(tmp_path), "TestProfile", 1)

        assert progress["url"] == "https://example.com/article"
        assert progress["media_url"] == "https://player.example.com/video"
        assert progress["media_title"] == "Embedded video"
        assert progress["media_seconds"] == pytest.approx(127.0)
        assert progress["media_updated_at"] == 1234567890

    def test_build_web_media_resume_target_prefers_page_provider_url(self):
        assert (
            build_web_media_resume_target(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "https://player.vimeo.com/video/148751763",
                44,
            )
            == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=44s&autoplay=0"
        )

    def test_build_web_media_resume_target_falls_back_to_media_url(self):
        assert (
            build_web_media_resume_target(
                "https://example.com/article",
                "https://player.vimeo.com/video/148751763",
                44,
            )
            == "https://player.vimeo.com/video/148751763#t=44s"
        )

    def test_scroll_setting_defaults_true(self):
        assert configured_remember_browser_card_scroll({}) is True

    def test_scroll_setting_respects_config_override(self):
        assert configured_remember_browser_card_scroll({"remember_browser_card_scroll": False}) is False

    def test_restore_payload_prefers_matching_bookmark(self):
        payload = build_web_restore_payload(
            {
                "url": "https://example.com/last",
                "scroll_ratio": 0.55,
                "bookmark_url": "https://example.com/chapter",
                "bookmark_payload": {"path": [0], "offsetRatio": 0.1, "scrollRatio": 0.2},
            },
            "https://example.com/chapter",
            allow_bookmark=True,
            allow_scroll=True,
            remember_scroll=True,
        )
        assert payload["rememberScroll"] is True
        assert payload["scrollRatio"] == pytest.approx(0.55)
        assert payload["bookmark"] == {"path": [0], "offsetRatio": 0.1, "scrollRatio": 0.2}

    def test_restore_payload_skips_bookmark_when_url_differs(self):
        payload = build_web_restore_payload(
            {
                "url": "https://example.com/last",
                "scroll_ratio": 0.55,
                "bookmark_url": "https://example.com/chapter",
                "bookmark_payload": {"path": [0], "offsetRatio": 0.1, "scrollRatio": 0.2},
            },
            "https://example.com/other",
            allow_bookmark=True,
            allow_scroll=True,
            remember_scroll=True,
        )
        assert payload["bookmark"] is None
        assert payload["rememberScroll"] is True

    def test_restore_payload_can_disable_scroll_and_bookmark_independently(self):
        progress = {
            "url": "https://example.com/last",
            "scroll_ratio": 0.55,
            "bookmark_url": "https://example.com/chapter",
            "bookmark_payload": {"path": [0], "offsetRatio": 0.1, "scrollRatio": 0.2},
        }
        payload = build_web_restore_payload(
            progress,
            "https://example.com/chapter",
            allow_bookmark=False,
            allow_scroll=False,
            remember_scroll=True,
        )
        assert payload["bookmark"] is None
        assert payload["rememberScroll"] is False
        assert payload["scrollRatio"] == pytest.approx(0.55)

    def test_build_external_web_url_keeps_card_context_when_tracking_disabled(self):
        assert (
            build_external_web_url(
                "https://example.com/article?x=1",
                card_id=42,
                track_with_extension=False,
            )
            == "https://example.com/article?x=1&inc_card_id=42"
        )

    def test_build_external_web_url_appends_tracking_params(self):
        assert (
            build_external_web_url(
                "https://example.com/article?x=1",
                card_id=42,
                track_with_extension=True,
            )
            == "https://example.com/article?x=1&inc_card_id=42&inc_track_web=1"
        )

    def test_build_external_web_url_replaces_stale_tracking_params(self):
        assert (
            build_external_web_url(
                "https://example.com/article?inc_card_id=1&inc_track_web=0&x=1",
                card_id=42,
                track_with_extension=True,
            )
            == "https://example.com/article?x=1&inc_card_id=42&inc_track_web=1"
        )

    def test_reviewer_web_homepage_action_opens_homepage_for_web_cards(self):
        class _Card:
            id = 42
            nid = 420

        class _Note(dict):
            def note_type(self):
                return {"name": _wm.WEB_NOTE_TYPE}

        class _Col:
            def get_note(self, nid):
                assert nid == 420
                return _Note(URL="https://example.com/home")

        opened = []

        result = reviewer_web_homepage_action(
            _Col(),
            _Card(),
            open_location=lambda card_id, url: opened.append((card_id, url)) or True,
        )

        assert result is True
        assert opened == [(42, "https://example.com/home")]

    def test_reviewer_web_homepage_action_ignores_non_web_cards(self):
        class _Card:
            id = 42
            nid = 420

        class _Note(dict):
            def note_type(self):
                return {"name": "Basic"}

        class _Col:
            def get_note(self, nid):
                assert nid == 420
                return _Note(URL="https://example.com/home")

        opened = []

        result = reviewer_web_homepage_action(
            _Col(),
            _Card(),
            open_location=lambda card_id, url: opened.append((card_id, url)) or True,
        )

        assert result is False
        assert opened == []

    def test_build_reviewer_web_home_button_js_contains_expected_command(self):
        js = build_reviewer_web_home_button_js(True)

        assert "incremento_open_web_home" in js
        assert "Open Homepage" in js

    def test_build_reviewer_web_home_button_js_can_disable_button(self):
        js = build_reviewer_web_home_button_js(False)

        assert 'var enabled = false;' in js


# ── ensure_video_note_type ────────────────────────────────────────────────────

ensure_video_note_type = _vm.ensure_video_note_type
ensure_web_note_type = _wm.ensure_web_note_type


def _make_mock_col(note_type_exists=False, template_matches=True):
    """Build a minimal mock collection for note type tests."""
    from unittest.mock import MagicMock
    col = MagicMock()
    if not note_type_exists:
        col.models.by_name.return_value = None
    else:
        m = MagicMock()
        if template_matches:
            m.__getitem__ = lambda self, key: (
                [{"qfmt": _vm.CARD_TEMPLATE_FRONT, "afmt": _vm.CARD_TEMPLATE_BACK}]
                if key == "tmpls" else MagicMock()
            )
        else:
            m.__getitem__ = lambda self, key: (
                [{"qfmt": "old front", "afmt": "old back"}]
                if key == "tmpls" else MagicMock()
            )
        col.models.by_name.return_value = m
    return col


class TestEnsureVideoNoteType:
    def test_creates_new_note_type_when_absent(self):
        col = _make_mock_col(note_type_exists=False)
        ensure_video_note_type(col)
        col.models.add.assert_called_once()

    def test_adds_subtitle_fields_to_existing_model_when_missing(self):
        from unittest.mock import MagicMock
        col = MagicMock()
        col.models.new_field.side_effect = lambda name: {"name": name}
        model = {
            "flds": [
                {"name": "Title", "ord": 0},
                {"name": "YouTube_URL", "ord": 1},
                {"name": _vm.LOCAL_VIDEO_FIELD, "ord": 2},
            ],
            "tmpls": [{"qfmt": _vm.CARD_TEMPLATE_FRONT, "afmt": _vm.CARD_TEMPLATE_BACK}],
        }
        col.models.by_name.return_value = model

        ensure_video_note_type(col)

        added_field_names = [call.args[1]["name"] for call in col.models.add_field.call_args_list]
        for field_name in VIDEO_SUBTITLE_FIELDS:
            assert field_name in added_field_names
        col.models.update_dict.assert_called_once()

    def test_does_not_create_when_already_exists_with_matching_template(self):
        col = _make_mock_col(note_type_exists=True, template_matches=True)
        ensure_video_note_type(col)
        col.models.add.assert_not_called()

    def test_updates_template_when_stale(self):
        col = _make_mock_col(note_type_exists=True, template_matches=False)
        ensure_video_note_type(col)
        col.models.update_dict.assert_called_once()

    def test_repairs_invalid_field_ordinals(self):
        from unittest.mock import MagicMock
        col = MagicMock()
        m = {
            "flds": [
                {"name": "Title", "ord": 0},
                {"name": "YouTube_URL", "ord": None},
                {"name": _vm.LOCAL_VIDEO_FIELD, "ord": 2},
            ],
            "tmpls": [{"qfmt": _vm.CARD_TEMPLATE_FRONT, "afmt": _vm.CARD_TEMPLATE_BACK}],
        }
        col.models.by_name.return_value = m
        ensure_video_note_type(col)
        assert [f["ord"] for f in m["flds"]] == [0, 1, 2]
        col.models.update_dict.assert_called_once()


class TestEnsureWebNoteType:
    def test_creates_new_note_type_when_absent(self):
        col = _make_mock_col(note_type_exists=False)
        # patch CARD_TEMPLATE_FRONT/BACK on web_manager
        ensure_web_note_type(col)
        col.models.add.assert_called_once()

    def test_does_not_create_when_already_exists_with_matching_template(self):
        from unittest.mock import MagicMock
        col = MagicMock()
        m = MagicMock()
        m.__getitem__ = lambda self, key: (
            [{"qfmt": _wm.CARD_TEMPLATE_FRONT, "afmt": _wm.CARD_TEMPLATE_BACK}]
            if key == "tmpls" else MagicMock()
        )
        col.models.by_name.return_value = m
        ensure_web_note_type(col)
        col.models.add.assert_not_called()

    def test_updates_template_when_stale(self):
        from unittest.mock import MagicMock
        col = MagicMock()
        m = MagicMock()
        m.__getitem__ = lambda self, key: (
            [{"qfmt": "old", "afmt": "old"}]
            if key == "tmpls" else MagicMock()
        )
        col.models.by_name.return_value = m
        ensure_web_note_type(col)
        col.models.update_dict.assert_called_once()


# ── add_video_card / add_web_card ─────────────────────────────────────────────

add_video_card = _vm.add_video_card
add_web_card = _wm.add_web_card


def _make_mock_col_for_add(deck_exists=True):
    from unittest.mock import MagicMock
    col = MagicMock()
    col.models.by_name.return_value = None  # note type doesn't exist yet → create
    note = MagicMock()
    note.id = 999
    col.new_note.return_value = note
    col.find_cards.return_value = [12345]
    if deck_exists:
        col.decks.by_name.return_value = {"id": 1}
    else:
        col.decks.by_name.return_value = None
        col.decks.add_normal_deck_with_name.return_value.id = 1
    return col


class TestAddVideoCard:
    def test_returns_card_id(self):
        col = _make_mock_col_for_add()
        result = add_video_card(col, "https://youtube.com/watch?v=abc", "My Video")
        assert result == 12345

    def test_creates_deck_when_absent(self):
        col = _make_mock_col_for_add(deck_exists=False)
        add_video_card(col, "https://youtube.com/watch?v=abc", "My Video")
        col.decks.add_normal_deck_with_name.assert_called_once()

    def test_uses_existing_deck(self):
        col = _make_mock_col_for_add(deck_exists=True)
        add_video_card(col, "https://youtube.com/watch?v=abc", "My Video")
        col.decks.add_normal_deck_with_name.assert_not_called()

    def test_sets_local_video_file_field(self):
        col = _make_mock_col_for_add(deck_exists=True)
        add_video_card(
            col,
            "https://youtube.com/watch?v=abc",
            "My Video",
            local_video_file="videos/abc12345678.mp4",
        )
        setitem_calls = col.new_note.return_value.__setitem__.call_args_list
        assert any(
            c.args == (_vm.LOCAL_VIDEO_FIELD, "videos/abc12345678.mp4")
            for c in setitem_calls
        )
        assert any(
            c.args == (SOURCE_LINK_FIELD, "videos/abc12345678.mp4")
            for c in setitem_calls
        )

    def test_sets_video_metadata_fields(self):
        col = _make_mock_col_for_add(deck_exists=True)

        add_video_card(col, "https://youtube.com/watch?v=abc", "My Video")

        setitem_calls = col.new_note.return_value.__setitem__.call_args_list
        assert any(c.args == (SOURCE_TYPE_FIELD, "Video") for c in setitem_calls)
        assert any(
            c.args == (SOURCE_LINK_FIELD, "https://youtube.com/watch?v=abc")
            for c in setitem_calls
        )

    def test_initializes_subtitle_fields_as_empty(self):
        col = _make_mock_col_for_add(deck_exists=True)

        add_video_card(col, "https://youtube.com/watch?v=abc", "My Video")

        setitem_calls = col.new_note.return_value.__setitem__.call_args_list
        assert any(c.args == (TARGET_SUBTITLE_FILE_FIELD, "") for c in setitem_calls)
        assert any(c.args == (TARGET_SUBTITLE_LABEL_FIELD, "") for c in setitem_calls)
        assert any(c.args == (REFERENCE_SUBTITLE_FILE_FIELD, "") for c in setitem_calls)
        assert any(c.args == (REFERENCE_SUBTITLE_LABEL_FIELD, "") for c in setitem_calls)

    def test_uses_visible_duplicate_suffix_when_title_collides(self):
        col = _make_mock_col_for_add(deck_exists=True)
        first_note = col.new_note.return_value
        second_note = type(first_note)()
        second_note.id = 1000
        col.new_note.side_effect = [first_note, second_note]
        col.add_note.side_effect = [0, 1]

        result = add_video_card(col, "https://youtube.com/watch?v=abc", "My Video")

        assert result == 12345
        setitem_calls = second_note.__setitem__.call_args_list
        assert any(c.args == ("Title", "My Video [2]") for c in setitem_calls)


class TestAddWebCard:
    def test_returns_card_id(self):
        col = _make_mock_col_for_add()
        result = add_web_card(col, "https://example.com", "My Web Page")
        assert result == 12345

    def test_creates_deck_when_absent(self):
        col = _make_mock_col_for_add(deck_exists=False)
        add_web_card(col, "https://example.com", "Page")
        col.decks.add_normal_deck_with_name.assert_called_once()

    def test_uses_existing_deck(self):
        col = _make_mock_col_for_add(deck_exists=True)
        add_web_card(col, "https://example.com", "Page")
        col.decks.add_normal_deck_with_name.assert_not_called()

    def test_uses_visible_duplicate_suffix_when_title_collides(self):
        col = _make_mock_col_for_add(deck_exists=True)
        first_note = col.new_note.return_value
        second_note = type(first_note)()
        second_note.id = 1000
        col.new_note.side_effect = [first_note, second_note]
        col.add_note.side_effect = [0, 1]

        result = add_web_card(col, "https://example.com", "Page")

        assert result == 12345
        setitem_calls = second_note.__setitem__.call_args_list
        assert any(c.args == ("Title", "Page [2]") for c in setitem_calls)

    def test_sets_web_metadata_fields(self):
        col = _make_mock_col_for_add(deck_exists=True)

        add_web_card(col, "https://example.com", "Page")

        setitem_calls = col.new_note.return_value.__setitem__.call_args_list
        assert any(c.args == (SOURCE_TYPE_FIELD, "Web") for c in setitem_calls)
        assert any(c.args == (SOURCE_LINK_FIELD, "https://example.com") for c in setitem_calls)


# ── Tag handling edge cases ───────────────────────────────────────────────────


class TestVideoTagEdgeCases:
    def test_add_card_with_extra_tags(self):
        """Provide extra tags to exercise the tag loop."""
        col = _make_mock_col_for_add()
        result = add_video_card(
            col, "https://youtube.com/watch?v=abc", "Test", tags=["science", "physics"]
        )
        assert result == 12345


class TestWebTagEdgeCases:
    def test_add_card_with_extra_tags(self):
        """Provide extra tags to exercise the tag loop."""
        col = _make_mock_col_for_add()
        result = add_web_card(col, "https://example.com", "Test", tags=["health"])
        assert result == 12345
