import re
from html import unescape
from urllib.parse import parse_qs, parse_qsl, unquote, urlencode, urlparse


_YOUTUBE_ID_RE = re.compile(r"[a-zA-Z0-9_-]{11}")
_YOUTUBE_URL_RE = re.compile(r"(?:v=|vi=|youtu\.be/|embed/|shorts/|live/)([a-zA-Z0-9_-]{11})")
_VIMEO_ID_RE = re.compile(r"\d{5,}")
_VIMEO_URL_RE = re.compile(r"(?:player\.)?vimeo\.com/(?:[^?#\s]*/)*(\d{5,})(?:[/?#].*)?$")
_HMS_RE = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")


def _iter_candidates(url: str) -> list[str]:
    raw = (url or "").strip()
    if not raw:
        return []
    html_decoded = unescape(raw)
    variants = [raw, html_decoded]
    for item in list(variants):
        decoded = unquote(item)
        variants.append(decoded)
    out: list[str] = []
    seen: set[str] = set()
    for item in variants:
        v = (item or "").strip()
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def extract_youtube_id(url: str) -> str | None:
    """Return the 11-char YouTube video ID from common URL formats."""
    raw = (url or "").strip()
    if not raw:
        return None
    if _YOUTUBE_ID_RE.fullmatch(raw):
        return raw
    for text in _iter_candidates(raw):
        m = _YOUTUBE_URL_RE.search(text)
        if m:
            return m.group(1)
    return None


def extract_vimeo_id(url: str) -> str | None:
    """Return Vimeo numeric clip ID from common URL formats."""
    raw = (url or "").strip()
    if not raw:
        return None
    if _VIMEO_ID_RE.fullmatch(raw):
        return raw
    for text in _iter_candidates(raw):
        m = _VIMEO_URL_RE.search(text)
        if m:
            return m.group(1)
    return None


def detect_video_provider(url: str) -> str | None:
    if extract_youtube_id(url):
        return "youtube"
    if extract_vimeo_id(url):
        return "vimeo"
    return None


def provider_display_name(url: str) -> str:
    provider = detect_video_provider(url)
    if provider == "youtube":
        return "YouTube"
    if provider == "vimeo":
        return "Vimeo"
    return "Video"


def extract_video_key(url: str) -> str | None:
    """
    Return stable local filename key for supported providers.
    - YouTube keeps raw 11-char id for backward compatibility.
    - Vimeo is prefixed to avoid key collisions.
    """
    yt = extract_youtube_id(url)
    if yt:
        return yt
    vm = extract_vimeo_id(url)
    if vm:
        return f"vimeo_{vm}"
    return None


def is_supported_video_url(url: str) -> bool:
    return extract_video_key(url) is not None


def _parse_time_value(value: str) -> int | None:
    raw = (value or "").strip().lower()
    if not raw:
        return None
    if raw.startswith("t="):
        raw = raw[2:].strip()
    if raw.isdigit():
        return max(0, int(raw))
    if raw.endswith("s") and raw[:-1].isdigit():
        return max(0, int(raw[:-1]))
    m = _HMS_RE.fullmatch(raw)
    if m and any(m.groups()):
        h = int(m.group(1) or 0)
        mi = int(m.group(2) or 0)
        s = int(m.group(3) or 0)
        return h * 3600 + mi * 60 + s
    if ":" in raw:
        parts = raw.split(":")
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return None


def extract_start_seconds(url: str) -> int | None:
    for text in _iter_candidates(url):
        parsed = urlparse(text)
        query = parse_qs(parsed.query, keep_blank_values=False)
        for key in ("t", "start", "time"):
            vals = query.get(key) or []
            for v in vals:
                sec = _parse_time_value(v)
                if sec is not None:
                    return sec
        frag = (parsed.fragment or "").strip()
        if frag:
            sec = _parse_time_value(frag)
            if sec is not None:
                return sec
            frag_qs = parse_qs(frag, keep_blank_values=False)
            for key in ("t", "start", "time"):
                vals = frag_qs.get(key) or []
                for v in vals:
                    sec = _parse_time_value(v)
                    if sec is not None:
                        return sec
    return None


def _strip_time_query_params(query: str) -> str:
    pairs = parse_qsl(query or "", keep_blank_values=True)
    kept = [(k, v) for (k, v) in pairs if str(k).lower() not in ("t", "start", "time")]
    return urlencode(kept, doseq=True)


def canonicalize_video_url(url: str) -> str:
    raw = unescape((url or "").strip())
    yt = extract_youtube_id(raw)
    if yt:
        base = f"https://www.youtube.com/watch?v={yt}"
        start = extract_start_seconds(raw)
        if start and start > 0:
            return f"{base}&t={start}s"
        return base
    vm = extract_vimeo_id(raw)
    if vm:
        parsed = urlparse(raw)
        query = _strip_time_query_params(parsed.query)
        base = f"https://player.vimeo.com/video/{vm}"
        if query:
            base = f"{base}?{query}"
        start = extract_start_seconds(raw)
        if start and start > 0:
            return f"{base}#t={start}s"
        return base
    return raw


def build_remote_video_watch_url(url: str, start_sec: int = 0) -> str | None:
    yt = extract_youtube_id(url)
    if yt:
        s = max(0, int(start_sec))
        if s <= 0:
            s = extract_start_seconds(url) or 0
        return f"https://www.youtube.com/watch?v={yt}&t={s}s&autoplay=0"
    vm = extract_vimeo_id(url)
    if vm:
        parsed = urlparse(canonicalize_video_url(url))
        query = _strip_time_query_params(parsed.query)
        base = f"https://player.vimeo.com/video/{vm}"
        if query:
            base = f"{base}?{query}"
        s = max(0, int(start_sec))
        if s <= 0:
            s = extract_start_seconds(url) or 0
        return f"{base}#t={s}s" if s > 0 else base
    return None


def supports_browser_cookie_auth(url: str) -> bool:
    """Only YouTube currently uses browser cookie extraction."""
    return detect_video_provider(url) == "youtube"
