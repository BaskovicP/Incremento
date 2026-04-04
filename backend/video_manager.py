import json
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections import deque
from collections.abc import Callable
from html import unescape as _html_unescape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

try:
    from .db import get_connection
    from . import paths as _paths
    from .video_providers import (
        extract_youtube_id as _extract_youtube_id,
        extract_vimeo_id,
        extract_video_key,
        detect_video_provider,
        is_supported_video_url,
        canonicalize_video_url as _canonicalize_video_url,
        extract_start_seconds,
        build_remote_video_watch_url as _build_remote_video_watch_url,
        supports_browser_cookie_auth,
        provider_display_name,
    )
except ImportError:
    from db import get_connection
    import paths as _paths
    from video_providers import (
        extract_youtube_id as _extract_youtube_id,
        extract_vimeo_id,
        extract_video_key,
        detect_video_provider,
        is_supported_video_url,
        canonicalize_video_url as _canonicalize_video_url,
        extract_start_seconds,
        build_remote_video_watch_url as _build_remote_video_watch_url,
        supports_browser_cookie_auth,
        provider_display_name,
    )

VIDEO_NOTE_TYPE = "Incremento Video"
LOCAL_VIDEO_FIELD = "Local_Video_File"
_INVISIBLE_DUPLICATE_MARK = "\u200b"

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
_VIMEO_EMBED_URL_RE = re.compile(r"https?://player\.vimeo\.com/video/\d+[^\s\"'<>]*")
_VIMEO_EMBED_CACHE: dict[str, str] = {}


def extract_video_id(url: str) -> str | None:
    """Backward-compatible alias for YouTube ID extraction."""
    return _extract_youtube_id(url)


def canonicalize_video_url(url: str) -> str:
    return _canonicalize_video_url(url)


def build_remote_video_watch_url(url: str, start_sec: int = 0, card_id: int | None = None) -> str | None:
    return _build_remote_video_watch_url(url, start_sec=start_sec, card_id=card_id)


def _extract_vimeo_embed_url_from_html(html_text: str, video_id: str) -> str | None:
    text = _html_unescape(html_text or "").replace("\\/", "/")
    if not text or not video_id:
        return None
    matches = re.findall(
        rf"https?://player\.vimeo\.com/video/{re.escape(video_id)}[^\s\"'<>]*",
        text,
    )
    if not matches:
        return None
    cleaned = [m.rstrip("\\") for m in matches]
    # Prefer tokenized embed URLs when present.
    for m in cleaned:
        if "h=" in m:
            return m
    return cleaned[0] if cleaned else None


def _merge_vimeo_urls(original_url: str, resolved_embed_url: str) -> str:
    original = urlparse(canonicalize_video_url(original_url))
    resolved = urlparse(_html_unescape(resolved_embed_url or ""))

    orig_q = dict(parse_qsl(original.query, keep_blank_values=True))
    res_q = dict(parse_qsl(resolved.query, keep_blank_values=True))
    merged_q = {**orig_q, **res_q}
    query = urlencode(list(merged_q.items()), doseq=True)

    scheme = resolved.scheme or original.scheme or "https"
    netloc = resolved.netloc or original.netloc or "player.vimeo.com"
    path = resolved.path or original.path
    fragment = original.fragment
    return urlunparse((scheme, netloc, path, "", query, fragment))


def resolve_video_url_for_embed(url: str, timeout_sec: float = 4.0) -> str:
    """
    Return canonical URL, and for Vimeo attempt to resolve/embed-tokenize URL (h=...).
    Network failures fall back to canonical URL.
    """
    canonical = canonicalize_video_url(url)
    if detect_video_provider(canonical) != "vimeo":
        return canonical

    parsed = urlparse(canonical)
    q = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if q.get("h"):
        return canonical

    vm_id = extract_vimeo_id(canonical)
    if not vm_id:
        return canonical

    cache_key = f"{vm_id}"
    cached = _VIMEO_EMBED_CACHE.get(cache_key)
    if cached:
        return _merge_vimeo_urls(canonical, cached)

    req = Request(
        canonical,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urlopen(req, timeout=max(1.0, float(timeout_sec))) as resp:
            html_text = resp.read().decode("utf-8", errors="replace")
    except (URLError, HTTPError, TimeoutError, ValueError):
        return canonical
    except Exception:
        return canonical

    resolved = _extract_vimeo_embed_url_from_html(html_text, vm_id)
    if not resolved:
        return canonical
    _VIMEO_EMBED_CACHE[cache_key] = resolved
    return _merge_vimeo_urls(canonical, resolved)


def local_video_relpath(video_id: str, ext: str = ".mp4") -> str:
    e = ext if ext.startswith(".") else f".{ext}"
    return f"videos/{video_id}{e.lower()}"


def local_video_abspath(addon_dir: str, profile: str, relpath: str) -> str:
    rel = (relpath or "").strip().replace("\\", "/")
    if rel.startswith("user_files/"):
        rel = rel[len("user_files/"):]
    return str((_paths.get_user_files_dir(addon_dir, profile) / rel).resolve())


def supported_local_video_extensions() -> tuple[str, ...]:
    """Extensions accepted by local video import (lowercase, sorted)."""
    return tuple(sorted(_VIDEO_EXTS))


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
    if "Requested format is not available" in text:
        return (
            "Selected format is not available for this video.\n"
            "Try 'Best available' or 'Original quality (no re-encoding)'."
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


def _ytdlp_format_selector_youtube(mode: str, max_height: int | None = None) -> str:
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
        "best[vcodec!=none][acodec!=none]/"
        "best"
    )


def _ytdlp_format_selector_vimeo(mode: str, max_height: int | None = None) -> str:
    """
    Vimeo often exposes many codec variants; prefer Qt-friendly MP4/H.264/AAC first.
    """
    h = ""
    try:
        if max_height and int(max_height) > 0:
            h = f"[height<={int(max_height)}]"
    except Exception:
        h = ""

    if mode == "download":
        return (
            f"best[ext=mp4]{h}[vcodec^=avc1][acodec^=mp4a]/"
            f"best[ext=mp4]{h}[vcodec^=h264][acodec^=mp4a]/"
            f"best[ext=mp4]{h}[acodec^=mp4a]/"
            f"best[ext=mp4]{h}[acodec!=none]/"
            f"best{h}[vcodec!=none][acodec!=none]/"
            "best[vcodec!=none][acodec!=none]/"
            "best"
        )
    return (
        f"bestvideo{h}+bestaudio/"
        f"best{h}[vcodec!=none][acodec!=none]/"
        "best[vcodec!=none][acodec!=none]/"
        "best"
    )


def _ytdlp_fallback_selector(mode: str) -> str:
    if mode == "download":
        return "best"
    return "bestvideo+bestaudio/best"


def _ytdlp_format_selector(
    mode: str,
    max_height: int | None = None,
    provider: str | None = None,
) -> str:
    if provider == "vimeo":
        return _ytdlp_format_selector_vimeo(mode, max_height=max_height)
    return _ytdlp_format_selector_youtube(mode, max_height=max_height)


def _is_requested_format_unavailable(lines: list[str]) -> bool:
    return any("Requested format is not available" in (ln or "") for ln in (lines or []))


def _is_format_selection_issue(lines: list[str]) -> bool:
    text = "\n".join(lines or []).lower()
    return (
        "requested format is not available" in text
        or "no video formats found" in text
        or "format not available" in text
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


def list_available_video_resolutions(addon_dir: str, profile: str, video_url: str) -> list[int]:
    """Return sorted available video heights (e.g. [2160, 1440, 1080, 720])."""
    if not is_supported_video_url(video_url or ""):
        raise ValueError("Enter a valid YouTube or Vimeo URL first.")

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
        video_url,
    ]
    profile_dir = _paths.get_video_profile_dir(addon_dir, profile)
    cookie_attempt = (
        _has_chromium_cookies(profile_dir)
        and supports_browser_cookie_auth(video_url)
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
    profile: str,
    yt_dlp_cmd: list[str],
    video_url: str,
    output_template: Path,
    progress_cb: Callable[[int, str], None] | None,
    mode: str = "download",
    max_height: int | None = None,
) -> None:
    merge_mode = mode in ("compressible", "original")

    profile_dir = _paths.get_video_profile_dir(addon_dir, profile)
    cookie_attempt = (
        _has_chromium_cookies(profile_dir)
        and supports_browser_cookie_auth(video_url)
    )
    provider = detect_video_provider(video_url)
    provider_name = provider_display_name(video_url)

    selectors: list[str | None] = [_ytdlp_format_selector(mode, max_height=max_height, provider=provider)]
    fallback_selector = _ytdlp_fallback_selector(mode)
    if fallback_selector not in selectors:
        selectors.append(fallback_selector)
    # Last-resort fallback: let yt-dlp choose its own default format.
    selectors.append(None)

    all_tail: list[str] = []
    downloaded = False
    for selector_index, selector in enumerate(selectors):
        # Deduplicate selector sequence while preserving the final None fallback.
        if selector_index < len(selectors) - 1 and selector in selectors[:selector_index]:
            continue
        base_cmd = [
            *yt_dlp_cmd,
            "--no-playlist",
            "--newline",
        ]
        if selector:
            base_cmd.extend(["-f", selector])
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
                video_url,
            ]
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
                    f"Trying {provider_name} download with Incremento browser cookies…",
                )
            )
        start_label = (
            f"Starting {provider_name} download…"
            if selector_index == 0
            else (
                f"Retrying {provider_name} download with broader format fallback…"
                if selector is not None
                else f"Retrying {provider_name} download with yt-dlp default format…"
            )
        )
        attempts.append((base_cmd, start_label))

        selector_failed_format = False
        for i, (cmd, run_label) in enumerate(attempts):
            _emit_progress(progress_cb, 2, run_label)
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
                downloaded = True
                break
            all_tail = list(tail)
            # Retry once without cookie extraction if cookie-based attempt failed.
            if i + 1 < len(attempts):
                _emit_progress(progress_cb, 2, "Retrying download without browser cookies…")
                continue
            if (
                selector_index + 1 < len(selectors)
                and _is_format_selection_issue(all_tail)
            ):
                selector_failed_format = True
                _emit_progress(
                    progress_cb,
                    2,
                    (
                        "Selected format unavailable; trying broader fallback…"
                        if selector is not None
                        else "Format selection failed; trying next fallback…"
                    ),
                )
                break
            msg = _ytdlp_error_message(all_tail)
            print("[Incremento] yt-dlp failure tail:")
            for ln in all_tail:
                print(ln)
            raise RuntimeError(msg)

        if downloaded:
            break
        if selector_failed_format:
            continue

    if not downloaded:
        msg = _ytdlp_error_message(all_tail)
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


def _safe_video_slug(name: str) -> str:
    raw = (name or "").strip()
    if not raw:
        return "local_video"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._-")
    return slug or "local_video"


def _unique_target_path(out_dir: Path, stem: str, ext: str) -> Path:
    ext_norm = ext if ext.startswith(".") else f".{ext}"
    ext_norm = ext_norm.lower()
    base = _safe_video_slug(stem)
    return out_dir / f"{base}-{uuid.uuid4().hex}{ext_norm}"


def _copy_with_progress(
    src: Path,
    dst: Path,
    progress_cb: Callable[[int, str], None] | None = None,
) -> None:
    total = 0
    try:
        total = max(0, int(src.stat().st_size))
    except Exception:
        total = 0
    _emit_progress(progress_cb, 2, "Copying local video…")
    copied = 0
    with src.open("rb") as r, dst.open("wb") as w:
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            w.write(chunk)
            copied += len(chunk)
            if total > 0:
                ratio = min(1.0, max(0.0, copied / total))
                pct = 2 + ratio * 96
                _emit_progress(progress_cb, pct, f"Copying local video… {ratio * 100:.1f}%")
    _emit_progress(progress_cb, 99, "Finalizing local video…")


def _encode_local_video_h264(
    ffmpeg_bin: str,
    src: Path,
    dst: Path,
    *,
    quality_mode: str = "h264_high",
    progress_cb: Callable[[int, str], None] | None = None,
) -> None:
    quality = (quality_mode or "").strip().lower()
    if quality == "h264_small":
        crf, preset, abr = "23", "medium", "160k"
    else:
        crf, preset, abr = "18", "slow", "192k"

    duration = _probe_duration_seconds(ffmpeg_bin, src)
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(src),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-level",
        "4.1",
        "-crf",
        crf,
        "-preset",
        preset,
        "-c:a",
        "aac",
        "-b:a",
        abr,
        "-movflags",
        "+faststart",
        "-progress",
        "pipe:1",
        "-nostats",
        "-loglevel",
        "error",
        str(dst),
    ]
    _emit_progress(progress_cb, 2, "Encoding local video (H.264)…")
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
            pct = 2 + ratio * 96
            _emit_progress(progress_cb, pct, f"Encoding local video… {ratio * 100:.1f}%")
        elif txt.startswith("out_time=") and duration:
            out_secs = _hms_to_seconds(txt.split("=", 1)[1] or "")
            if out_secs is not None:
                ratio = min(1.0, max(0.0, out_secs / duration))
                pct = 2 + ratio * 96
                _emit_progress(progress_cb, pct, f"Encoding local video… {ratio * 100:.1f}%")
    rc = proc.wait()
    if rc != 0 or not dst.exists() or dst.stat().st_size <= 0:
        detail = "\n".join(tail) or "no output"
        raise RuntimeError(f"ffmpeg local encode failed.\n{detail}")
    _emit_progress(progress_cb, 99, "Finalizing encoded video…")


def import_local_video_file(
    addon_dir: str,
    profile: str,
    source_path: str,
    *,
    encode_mode: str = "h264_high",
    progress_cb: Callable[[int, str], None] | None = None,
) -> str:
    """
    Import a local video file into user_files/videos and return relpath.
    encode_mode:
      - original: no re-encoding (copy source container/stream as-is)
      - h264_high: encode to MP4 H.264 high quality
      - h264_small: encode to MP4 H.264 smaller size
    """
    src = Path((source_path or "").strip()).expanduser()
    if not src.exists() or not src.is_file():
        raise ValueError("Selected local video file does not exist.")
    ext = src.suffix.lower()
    if ext not in _VIDEO_EXTS:
        supported = ", ".join(sorted(_VIDEO_EXTS))
        raise ValueError(f"Unsupported local video format: {ext or '(none)'} (supported: {supported})")

    out_dir = _paths.get_videos_dir(addon_dir, profile)
    out_dir.mkdir(parents=True, exist_ok=True)

    mode = (encode_mode or "h264_high").strip().lower()
    if mode == "original":
        target = _unique_target_path(out_dir, src.stem, ext)
        if src.resolve() == target.resolve():
            _emit_progress(progress_cb, 100, "Local video already in user_files/videos.")
            return f"videos/{target.name}"
        _copy_with_progress(src, target, progress_cb=progress_cb)
        _emit_progress(progress_cb, 100, "Local video imported.")
        return f"videos/{target.name}"

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError(
            "ffmpeg is required for local encoding.\n"
            "Install ffmpeg or select 'Original quality (no re-encoding)'."
        )

    target = _unique_target_path(out_dir, src.stem, ".mp4")
    with tempfile.TemporaryDirectory(prefix="incremento_local_video_") as tmp_dir:
        tmp_dst = Path(tmp_dir) / f"{target.stem}.mp4"
        _encode_local_video_h264(
            ffmpeg_bin,
            src,
            tmp_dst,
            quality_mode=mode,
            progress_cb=progress_cb,
        )
        if target.exists():
            target.unlink()
        tmp_dst.replace(target)
    _emit_progress(progress_cb, 100, "Local video imported.")
    return f"videos/{target.name}"


def download_and_compress_video(
    addon_dir: str,
    profile: str,
    video_url: str,
    *,
    overwrite: bool = False,
    progress_cb: Callable[[int, str], None] | None = None,
    max_height: int | None = None,
    original_quality: bool = False,
) -> str:
    """
    Download a YouTube/Vimeo video into user_files/videos/.
    If ffmpeg is available, compress to mp4; otherwise keep downloaded container.
    Returns relpath (e.g. videos/dQw4w9WgXcQ.mp4 or videos/vimeo_12345.mp4).
    """
    video_key = extract_video_key(video_url or "")
    if not video_key:
        raise ValueError("Could not extract a valid YouTube or Vimeo video ID.")

    out_dir = _paths.get_videos_dir(addon_dir, profile)
    out_dir.mkdir(parents=True, exist_ok=True)

    yt_dlp_cmd, ffmpeg_bin = _video_tools()
    if not yt_dlp_cmd:
        raise RuntimeError(
            "Missing required tool: yt-dlp.\n"
            "Automatic install failed. Install manually with:\n"
            f"{sys.executable} -m pip install yt-dlp"
        )

    with tempfile.TemporaryDirectory(prefix="incremento_video_") as tmp_dir:
        tmp = Path(tmp_dir)
        dl_template = tmp / f"{video_key}.%(ext)s"
        if original_quality and ffmpeg_bin:
            dl_mode = "original"
        else:
            dl_mode = "compressible" if ffmpeg_bin else "download"
        _run_yt_dlp_with_progress(
            addon_dir,
            profile,
            yt_dlp_cmd,
            video_url,
            dl_template,
            progress_cb,
            mode=dl_mode,
            max_height=max_height,
        )

        candidates = [p for p in tmp.glob(f"{video_key}.*") if p.suffix.lower() in _VIDEO_EXTS]
        if not candidates:
            raise RuntimeError("yt-dlp finished, but no downloaded video file was found.")
        source_path = max(candidates, key=lambda p: p.stat().st_size)

        if original_quality:
            final_ext = source_path.suffix.lower() or ".mp4"
            final_path = _unique_target_path(out_dir, video_key, final_ext)
            source_path.replace(final_path)
            _emit_progress(progress_cb, 100, "Video ready (original quality).")
            return f"videos/{final_path.name}"

        final_ext = ".mp4"
        final_path = _unique_target_path(out_dir, video_key, final_ext)
        if ffmpeg_bin:
            encoded_path = tmp / f"{video_key}.compressed.mp4"
            _compress_video(ffmpeg_bin, source_path, encoded_path, progress_cb=progress_cb)
            encoded_path.replace(final_path)
        else:
            final_ext = source_path.suffix.lower() or ".mp4"
            final_path = _unique_target_path(out_dir, video_key, final_ext)
            source_path.replace(final_path)
    _emit_progress(progress_cb, 100, "Video ready.")
    return f"videos/{final_path.name}"




def fmt_time(seconds: float) -> str:
    """Format seconds as M:SS or H:MM:SS."""
    t = int(seconds)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def get_video_position(addon_dir: str, profile: str, card_id: int) -> float:
    row = get_connection(addon_dir, profile).execute(
        "SELECT position FROM video_progress WHERE card_id = ?", (card_id,)
    ).fetchone()
    return row[0] if row else 0.0


def set_video_position(addon_dir: str, profile: str, card_id: int, position: float) -> None:
    conn = get_connection(addon_dir, profile)
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

    def _build_note(stored_title: str):
        note = col.new_note(model)
        note["Title"] = stored_title
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
        return note

    for attempt in range(6):
        stored_title = title if attempt == 0 else f"{title}{_INVISIBLE_DUPLICATE_MARK * attempt}"
        note = _build_note(stored_title)
        added = col.add_note(note, deck_id)
        if not added:
            continue
        cards = col.find_cards(f"nid:{note.id}")
        if cards:
            return cards[0]
    raise RuntimeError("Failed to add video card. Anki rejected the note.")
