import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import deque
from collections.abc import Callable
from pathlib import Path
from urllib.parse import unquote

try:
    from .db import get_connection
except ImportError:
    from db import get_connection

VIDEO_NOTE_TYPE = "Incremento Video"
LOCAL_VIDEO_FIELD = "Local_Video_File"

CARD_TEMPLATE_FRONT = """
<div style="text-align:center; padding:60px 20px; font-family:sans-serif; color:#888;">
  <div style="font-size:1.3em; margin-bottom:10px; color:#ccc;">{{Title}}</div>
  <div style="font-size:0.85em;">Video open in sidebar &nbsp;&middot;&nbsp; use &ldquo;Add Card&rdquo; button to bookmark moments</div>
</div>
{{YouTube_URL}}
""".strip()

CARD_TEMPLATE_BACK = "{{Title}}"

_VIDEO_EXTS = {".mkv", ".mp4", ".webm", ".mov", ".m4v"}
_YTDLP_PERCENT_RE = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")


def extract_video_id(url: str) -> str | None:
    """Return the 11-char YouTube video ID from any common YouTube URL format."""
    raw = (url or "").strip()
    if not raw:
        return None

    # Allow users to paste just the raw 11-char ID.
    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", raw):
        return raw

    # Decode URL-encoded wrappers (e.g. attribution links), then scan both forms.
    candidates = [raw]
    decoded = unquote(raw)
    if decoded != raw:
        candidates.append(decoded)

    pattern = re.compile(
        r"(?:v=|vi=|youtu\.be/|embed/|shorts/|live/)([a-zA-Z0-9_-]{11})"
    )
    for text in candidates:
        m = pattern.search(text)
        if m:
            return m.group(1)
    return None


def local_video_relpath(video_id: str, ext: str = ".mp4") -> str:
    e = ext if ext.startswith(".") else f".{ext}"
    return f"videos/{video_id}{e.lower()}"


def local_video_abspath(addon_dir: str, relpath: str) -> str:
    rel = (relpath or "").strip().replace("\\", "/")
    if rel.startswith("user_files/"):
        rel = rel[len("user_files/") :]
    return str((Path(addon_dir) / "user_files" / rel).resolve())


def _yt_dlp_cmd(allow_auto_install: bool = True) -> list[str] | None:
    yt_bin = shutil.which("yt-dlp")
    if yt_bin:
        return [yt_bin]

    # If the module is already installed in Anki's Python, use it directly.
    try:
        check = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception:
        check = None
    if check is not None and check.returncode == 0:
        return [sys.executable, "-m", "yt_dlp"]

    if not allow_auto_install:
        return None

    # Best-effort bootstrap for fresh installs.
    try:
        install = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "yt-dlp"],
            capture_output=True,
            text=True,
            timeout=240,
        )
    except Exception:
        return None
    if install.returncode != 0:
        return None
    try:
        check2 = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception:
        return None
    if check2.returncode == 0:
        return [sys.executable, "-m", "yt_dlp"]
    return None


def _video_tools(allow_auto_install_yt: bool = True) -> tuple[list[str] | None, str | None]:
    return _yt_dlp_cmd(allow_auto_install=allow_auto_install_yt), shutil.which("ffmpeg")


def video_download_requirements() -> list[str]:
    yt_dlp, ffmpeg = _video_tools(allow_auto_install_yt=False)
    missing = []
    if not yt_dlp:
        missing.append("yt-dlp")
    if not ffmpeg:
        missing.append("ffmpeg (optional for compression)")
    return missing


def _emit_progress(progress_cb: Callable[[int, str], None] | None, percent: float, label: str) -> None:
    if not progress_cb:
        return
    p = int(max(0, min(100, round(percent))))
    try:
        progress_cb(p, label)
    except Exception:
        pass


def _video_profile_dir(addon_dir: str) -> Path:
    return Path(addon_dir) / "user_files" / "video_profile"


def _has_chromium_cookies(profile_dir: Path) -> bool:
    candidates = [
        profile_dir / "Cookies",
        profile_dir / "Network" / "Cookies",
        profile_dir / "Default" / "Cookies",
        profile_dir / "Default" / "Network" / "Cookies",
    ]
    return any(p.exists() for p in candidates)


def _ytdlp_error_message(lines: list[str]) -> str:
    text = "\n".join(lines)
    has_bot = (
        "Sign in to confirm you're not a bot" in text
        or "Sign in to confirm you’re not a bot" in text
    )
    has_js_runtime = "No supported JavaScript runtime could be found" in text

    if has_bot and has_js_runtime:
        return (
            "YouTube blocked this download and also requested a JS runtime.\n"
            "1) Open this video in Incremento's Video dock and sign in to YouTube.\n"
            "2) Install deno or node, then retry local download."
        )
    if has_bot:
        return (
            "YouTube blocked this download (sign-in / bot verification required).\n"
            "Open the video in Incremento's Video dock, sign in to YouTube, then retry."
        )
    if has_js_runtime:
        return (
            "yt-dlp needs a JavaScript runtime for this video extraction.\n"
            "Install deno or node, then retry local download."
        )
    tail = [ln for ln in lines[-4:] if ln]
    if tail:
        return "yt-dlp download failed:\n" + "\n".join(tail)
    return "yt-dlp download failed."


def _parse_ytdlp_percent(line: str) -> float | None:
    m = _YTDLP_PERCENT_RE.search(line or "")
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _ffprobe_bin(ffmpeg_bin: str) -> str | None:
    sibling = Path(ffmpeg_bin).with_name("ffprobe")
    if sibling.exists():
        return str(sibling)
    return shutil.which("ffprobe")


def _probe_duration_seconds(ffmpeg_bin: str, src: Path) -> float | None:
    probe = _ffprobe_bin(ffmpeg_bin)
    if not probe:
        return None
    proc = subprocess.run(
        [
            probe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            str(src),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    out = (proc.stdout or "").strip()
    try:
        dur = float(out)
    except Exception:
        return None
    return dur if dur > 0 else None


def _hms_to_seconds(value: str) -> float | None:
    raw = (value or "").strip()
    if not raw:
        return None
    parts = raw.split(":")
    if len(parts) != 3:
        return None
    try:
        h = float(parts[0])
        m = float(parts[1])
        s = float(parts[2])
    except Exception:
        return None
    return h * 3600 + m * 60 + s


def _ytdlp_format_selector(mode: str, max_height: int | None = None) -> str:
    """
    Return yt-dlp format selector for the selected pipeline mode.
    - compressible: maximize source quality; ffmpeg will normalize afterward.
    - download: prefer broadly playable progressive H.264/AAC MP4 streams.
    """
    h = ""
    try:
        if max_height and int(max_height) > 0:
            h = f"[height<={int(max_height)}]"
    except Exception:
        h = ""

    if mode == "original":
        return (
            f"bestvideo{h}+bestaudio/"
            f"best{h}[vcodec!=none][acodec!=none]/"
            "best[vcodec!=none][acodec!=none]"
        )

    if mode == "compressible":
        return (
            f"bestvideo{h}[vcodec^=avc1][ext=mp4]+bestaudio[acodec^=mp4a]/"
            f"bestvideo{h}[vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
            f"bestvideo{h}+bestaudio/"
            f"best{h}[vcodec!=none][acodec!=none]/"
            "best[vcodec!=none][acodec!=none]"
        )
    return (
        f"best[ext=mp4]{h}[vcodec^=avc1][acodec^=mp4a]/"
        f"best[ext=mp4]{h}[vcodec^=avc1][acodec!=none]/"
        f"best[ext=mp4]{h}[vcodec!=none][acodec!=none]/"
        "best[vcodec!=none][acodec!=none]"
    )


def _extract_resolutions_from_info(info: dict) -> list[int]:
    if not isinstance(info, dict):
        return []
    formats = info.get("formats")
    if not isinstance(formats, list):
        return []
    heights: set[int] = set()
    for entry in formats:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("vcodec") or "").lower() == "none":
            continue
        h = entry.get("height")
        if isinstance(h, int) and h > 0:
            heights.add(h)
    return sorted(heights, reverse=True)


def list_available_video_resolutions(addon_dir: str, youtube_url: str) -> list[int]:
    """Return sorted available video heights (e.g. [2160, 1440, 1080, 720])."""
    if not extract_video_id(youtube_url or ""):
        raise ValueError("Enter a valid YouTube URL first.")

    yt_dlp_cmd = _yt_dlp_cmd()
    if not yt_dlp_cmd:
        raise RuntimeError(
            "Missing required tool: yt-dlp.\n"
            "Automatic install failed. Install manually with:\n"
            f"{sys.executable} -m pip install yt-dlp"
        )

    base_cmd = [
        *yt_dlp_cmd,
        "--no-playlist",
        "--no-warnings",
        "-J",
        youtube_url,
    ]
    profile_dir = _video_profile_dir(addon_dir)
    cookie_attempt = (
        _has_chromium_cookies(profile_dir)
        and "youtube.com" in (youtube_url or "").lower()
    )
    attempts: list[list[str]] = []
    if cookie_attempt:
        attempts.append(
            [
                *base_cmd,
                "--cookies-from-browser",
                f"chromium:{profile_dir}",
            ]
        )
    attempts.append(base_cmd)

    last_err = ""
    for cmd in attempts:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=90,
        )
        if proc.returncode == 0:
            try:
                info = json.loads(proc.stdout or "{}")
            except Exception as e:
                raise RuntimeError(f"Could not parse yt-dlp metadata output: {e}") from e
            return _extract_resolutions_from_info(info)
        lines = (proc.stdout or "").splitlines() + (proc.stderr or "").splitlines()
        lines = [ln.strip() for ln in lines if ln.strip()]
        last_err = _ytdlp_error_message(lines[-10:]) if lines else "yt-dlp metadata fetch failed."

    raise RuntimeError(last_err or "Could not fetch available resolutions.")


def _run_yt_dlp_with_progress(
    addon_dir: str,
    yt_dlp_cmd: list[str],
    youtube_url: str,
    output_template: Path,
    progress_cb: Callable[[int, str], None] | None,
    mode: str = "download",
    max_height: int | None = None,
) -> None:
    merge_mode = mode in ("compressible", "original")
    base_cmd = [
        *yt_dlp_cmd,
        "--no-playlist",
        "--newline",
        "-f",
        _ytdlp_format_selector(mode, max_height=max_height),
    ]
    if merge_mode:
        base_cmd.extend(
            [
                "--merge-output-format",
                "mkv",
            ]
        )
    base_cmd.extend(
        [
            "-o",
            str(output_template),
            youtube_url,
        ]
    )

    profile_dir = _video_profile_dir(addon_dir)
    cookie_attempt = (
        _has_chromium_cookies(profile_dir)
        and "youtube.com" in (youtube_url or "").lower()
    )
    attempts: list[tuple[list[str], str]] = []
    if cookie_attempt:
        attempts.append(
            (
                [
                    *base_cmd,
                    "--cookies-from-browser",
                    f"chromium:{profile_dir}",
                ],
                "Trying download with Incremento browser cookies…",
            )
        )
    attempts.append((base_cmd, "Starting YouTube download…"))

    all_tail: list[str] = []
    for i, (cmd, start_label) in enumerate(attempts):
        _emit_progress(progress_cb, 2, start_label)
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        tail = deque(maxlen=40)
        for line in (proc.stdout or []):
            txt = line.strip()
            if txt:
                tail.append(txt)
            pct = _parse_ytdlp_percent(txt)
            if pct is not None:
                if merge_mode:
                    overall = 2 + (pct / 100.0) * 58.0
                else:
                    overall = 2 + (pct / 100.0) * 96.0
                _emit_progress(progress_cb, overall, f"Downloading video… {pct:.1f}%")
                continue
            if merge_mode and "[Merger]" in txt:
                _emit_progress(progress_cb, 60, "Merging downloaded streams…")
        rc = proc.wait()
        if rc == 0:
            break
        all_tail = list(tail)
        # Retry once without cookie extraction if cookie-based attempt failed.
        if i + 1 < len(attempts):
            _emit_progress(progress_cb, 2, "Retrying download without browser cookies…")
            continue
        msg = _ytdlp_error_message(all_tail)
        print("[Incremento] yt-dlp failure tail:")
        for ln in all_tail:
            print(ln)
        raise RuntimeError(msg)

    if merge_mode:
        _emit_progress(progress_cb, 60, "Download finished. Starting compression…")
    else:
        _emit_progress(progress_cb, 99, "Finalizing downloaded file…")


def _compress_video(
    ffmpeg_bin: str,
    src: Path,
    dst: Path,
    progress_cb: Callable[[int, str], None] | None = None,
) -> None:
    attempts = [
        ("copy", None, None, []),
        ("libx264", "18", "slow", ["-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1"]),
        ("libx265", "18", "slow", []),
    ]
    duration = _probe_duration_seconds(ffmpeg_bin, src)
    errors = []
    for codec, crf, preset, extra_flags in attempts:
        if dst.exists():
            try:
                dst.unlink()
            except Exception:
                pass
        if codec == "copy":
            cmd = [
                ffmpeg_bin,
                "-y",
                "-i",
                str(src),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                "-progress",
                "pipe:1",
                "-nostats",
                "-loglevel",
                "error",
                str(dst),
            ]
            _emit_progress(progress_cb, 61, "Preparing MP4 (no re-encode)…")
        else:
            cmd = [
                ffmpeg_bin,
                "-y",
                "-i",
                str(src),
                "-c:v",
                codec,
                *extra_flags,
                "-crf",
                crf,
                "-preset",
                preset,
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                "-progress",
                "pipe:1",
                "-nostats",
                "-loglevel",
                "error",
                str(dst),
            ]
            _emit_progress(progress_cb, 61, f"Compressing video ({codec})…")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        tail = deque(maxlen=24)
        for line in (proc.stdout or []):
            txt = line.strip()
            if txt:
                tail.append(txt)
            if txt.startswith("out_time_ms=") and duration:
                try:
                    out_secs = float(txt.split("=", 1)[1]) / 1_000_000.0
                except Exception:
                    out_secs = 0.0
                ratio = min(1.0, max(0.0, out_secs / duration))
                pct = 61 + ratio * 37
                if codec == "copy":
                    _emit_progress(progress_cb, pct, f"Preparing MP4… {ratio * 100:.1f}%")
                else:
                    _emit_progress(progress_cb, pct, f"Compressing video ({codec})… {ratio * 100:.1f}%")
            elif txt.startswith("out_time=") and duration:
                out_secs = _hms_to_seconds(txt.split("=", 1)[1] or "")
                if out_secs is not None:
                    ratio = min(1.0, max(0.0, out_secs / duration))
                    pct = 61 + ratio * 37
                    if codec == "copy":
                        _emit_progress(progress_cb, pct, f"Preparing MP4… {ratio * 100:.1f}%")
                    else:
                        _emit_progress(progress_cb, pct, f"Compressing video ({codec})… {ratio * 100:.1f}%")
            elif txt == "progress=end":
                _emit_progress(progress_cb, 99, "Finalizing compressed file…")
        rc = proc.wait()
        if rc != 0:
            detail = "\n".join(tail) or "no output"
            label = "remux" if codec == "copy" else f"{codec} compression"
            errors.append(f"ffmpeg {label} failed.\n{detail}")
            continue
        if dst.exists() and dst.stat().st_size > 0:
            _emit_progress(progress_cb, 99, "Finalizing compressed file…")
            return
        errors.append(f"ffmpeg {codec} produced no output.")
    raise RuntimeError("\n".join(errors))


def download_and_compress_youtube_video(
    addon_dir: str,
    youtube_url: str,
    *,
    overwrite: bool = False,
    progress_cb: Callable[[int, str], None] | None = None,
    max_height: int | None = None,
    original_quality: bool = False,
) -> str:
    """
    Download a YouTube video into user_files/videos/.
    If ffmpeg is available, compress to mp4; otherwise keep downloaded container.
    Returns relpath (e.g. videos/dQw4w9WgXcQ.mp4).
    """
    video_id = extract_video_id(youtube_url or "")
    if not video_id:
        raise ValueError("Could not extract a valid YouTube video ID.")

    out_dir = Path(addon_dir) / "user_files" / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Reuse any existing local copy regardless of extension.
    existing = None
    for ext in _VIDEO_EXTS:
        p = out_dir / f"{video_id}{ext}"
        if p.exists() and p.stat().st_size > 0:
            existing = p
            break
    if existing is not None and not overwrite:
        _emit_progress(progress_cb, 100, "Using existing local video copy.")
        return local_video_relpath(video_id, existing.suffix)

    yt_dlp_cmd, ffmpeg_bin = _video_tools()
    if not yt_dlp_cmd:
        raise RuntimeError(
            "Missing required tool: yt-dlp.\n"
            "Automatic install failed. Install manually with:\n"
            f"{sys.executable} -m pip install yt-dlp"
        )

    with tempfile.TemporaryDirectory(prefix="incremento_video_") as tmp_dir:
        tmp = Path(tmp_dir)
        dl_template = tmp / f"{video_id}.%(ext)s"
        if original_quality and ffmpeg_bin:
            dl_mode = "original"
        else:
            dl_mode = "compressible" if ffmpeg_bin else "download"
        _run_yt_dlp_with_progress(
            addon_dir,
            yt_dlp_cmd,
            youtube_url,
            dl_template,
            progress_cb,
            mode=dl_mode,
            max_height=max_height,
        )

        candidates = [p for p in tmp.glob(f"{video_id}.*") if p.suffix.lower() in _VIDEO_EXTS]
        if not candidates:
            raise RuntimeError("yt-dlp finished, but no downloaded video file was found.")
        source_path = max(candidates, key=lambda p: p.stat().st_size)

        if original_quality:
            final_ext = source_path.suffix.lower() or ".mp4"
            final_path = out_dir / f"{video_id}{final_ext}"
            if final_path.exists():
                final_path.unlink()
            source_path.replace(final_path)
            _emit_progress(progress_cb, 100, "Video ready (original quality).")
            return local_video_relpath(video_id, final_path.suffix)

        final_ext = ".mp4"
        final_path = out_dir / f"{video_id}{final_ext}"
        if ffmpeg_bin:
            encoded_path = tmp / f"{video_id}.compressed.mp4"
            _compress_video(ffmpeg_bin, source_path, encoded_path, progress_cb=progress_cb)
            if final_path.exists():
                final_path.unlink()
            encoded_path.replace(final_path)
        else:
            final_ext = source_path.suffix.lower() or ".mp4"
            final_path = out_dir / f"{video_id}{final_ext}"
            if final_path.exists():
                final_path.unlink()
            source_path.replace(final_path)
    _emit_progress(progress_cb, 100, "Video ready.")
    return local_video_relpath(video_id, final_path.suffix)


def fmt_time(seconds: float) -> str:
    """Format seconds as M:SS or H:MM:SS."""
    t = int(seconds)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def get_video_position(addon_dir: str, card_id: int) -> float:
    row = get_connection(addon_dir).execute(
        "SELECT position FROM video_progress WHERE card_id = ?", (card_id,)
    ).fetchone()
    return row[0] if row else 0.0


def set_video_position(addon_dir: str, card_id: int, position: float) -> None:
    conn = get_connection(addon_dir)
    conn.execute(
        "INSERT INTO video_progress (card_id, position) VALUES (?, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET position = excluded.position",
        (card_id, round(float(position), 1)),
    )
    conn.commit()


def _normalize_field_ordinals(model_dict) -> bool:
    """
    Ensure every field has a valid integer `ord` so Anki can sort note fields.
    Returns True when a repair was applied.
    """
    try:
        fields = model_dict["flds"]
    except Exception:
        return False
    if not isinstance(fields, list):
        return False

    seen: set[int] = set()
    needs_fix = False
    for f in fields:
        if not isinstance(f, dict):
            needs_fix = True
            continue
        ord_val = f.get("ord")
        if not isinstance(ord_val, int) or ord_val < 0 or ord_val in seen:
            needs_fix = True
        else:
            seen.add(ord_val)

    if not needs_fix:
        return False

    for idx, f in enumerate(fields):
        if isinstance(f, dict):
            f["ord"] = idx
    return True


def ensure_video_note_type(col) -> None:
    """Create the Incremento Video note type, or sync its template if it already exists."""
    models = col.models
    m = models.by_name(VIDEO_NOTE_TYPE)
    if m is None:
        m = models.new(VIDEO_NOTE_TYPE)
        for field_name in ("Title", "YouTube_URL", LOCAL_VIDEO_FIELD):
            fld = models.new_field(field_name)
            models.add_field(m, fld)
        tmpl = models.new_template("Card 1")
        tmpl["qfmt"] = CARD_TEMPLATE_FRONT
        tmpl["afmt"] = CARD_TEMPLATE_BACK
        models.add_template(m, tmpl)
        models.add(m)
    else:
        changed = False
        # Keep old collections forward-compatible by adding new fields lazily.
        try:
            fields = m["flds"]
            if isinstance(fields, list):
                existing = {f.get("name", "") for f in fields if isinstance(f, dict)}
            else:
                existing = set()
        except Exception:
            existing = set()
        if LOCAL_VIDEO_FIELD not in existing:
            fld = models.new_field(LOCAL_VIDEO_FIELD)
            models.add_field(m, fld)
            changed = True

        if _normalize_field_ordinals(m):
            changed = True

        tmpl = m["tmpls"][0]
        if tmpl["qfmt"] != CARD_TEMPLATE_FRONT or tmpl["afmt"] != CARD_TEMPLATE_BACK:
            tmpl["qfmt"] = CARD_TEMPLATE_FRONT
            tmpl["afmt"] = CARD_TEMPLATE_BACK
            changed = True

        if changed:
            models.update_dict(m)


def add_video_card(
    col,
    youtube_url: str,
    title: str,
    deck_name: str = "Topics",
    tags: list[str] | None = None,
    local_video_file: str = "",
) -> int:
    """Create an Incremento Video note, return the card id."""
    ensure_video_note_type(col)
    deck = col.decks.by_name(deck_name)
    if deck is None:
        deck_id = col.decks.add_normal_deck_with_name(deck_name).id
    else:
        deck_id = deck["id"]
    model = col.models.by_name(VIDEO_NOTE_TYPE)
    note = col.new_note(model)
    note["Title"] = title
    note["YouTube_URL"] = youtube_url
    try:
        note[LOCAL_VIDEO_FIELD] = (local_video_file or "").strip()
    except Exception:
        pass
    for tag in ["Incremento"] + [t for t in (tags or []) if t != "Incremento"]:
        if not tag:
            continue
        if hasattr(note, "add_tag"):
            note.add_tag(tag)
        elif hasattr(note, "tags"):
            note.tags.append(tag)
    note.note_type()["did"] = deck_id
    col.add_note(note, deck_id)
    return col.find_cards(f"nid:{note.id}")[0]
