try:
    from .db import get_connection
    from .note_metadata import (
        apply_incremento_metadata,
        build_incremento_metadata,
        ensure_incremento_metadata_fields,
    )
except ImportError:
    from db import get_connection
    from note_metadata import (  # type: ignore
        apply_incremento_metadata,
        build_incremento_metadata,
        ensure_incremento_metadata_fields,
    )
import json
import time
from typing import Literal, TypedDict
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

WEB_NOTE_TYPE = "Incremento Web"
TRACK_CARD_ID_PARAM = "inc_card_id"
TRACK_WEB_FLAG_PARAM = "inc_track_web"
_DEFAULT_REMEMBER_BROWSER_CARD_SCROLL = True
_DEFAULT_PREFER_WEB_CARD_RESUME_IN_ORIGINAL_PAGE = True

CARD_TEMPLATE_FRONT = """
<div style="text-align:center; padding:60px 20px; font-family:sans-serif; color:#888;">
  <div style="font-size:1.3em; margin-bottom:10px; color:#ccc;">{{Title}}</div>
  <div style="font-size:0.85em;">Web page open in sidebar</div>
</div>
{{URL}}
""".strip()

CARD_TEMPLATE_BACK = "{{Title}}"


def _stored_web_title(title: str, attempt: int) -> str:
    base_title = str(title or "").strip() or "Untitled"
    if attempt <= 0:
        return base_title
    return f"{base_title} [{attempt + 1}]"


def is_web_note_type_name(name: str) -> bool:
    return str(name or "").strip() == WEB_NOTE_TYPE


def reviewer_web_homepage_action(col, reviewer_card, *, open_location) -> bool:
    if col is None or reviewer_card is None:
        return False
    try:
        card_id = int(getattr(reviewer_card, "id", 0) or 0)
        note_id = int(getattr(reviewer_card, "nid", 0) or 0)
    except Exception:
        return False
    if card_id <= 0 or note_id <= 0:
        return False
    try:
        note = col.get_note(note_id)
    except Exception:
        return False
    try:
        note_type = note.note_type() or {}
    except Exception:
        note_type = {}
    if not is_web_note_type_name(note_type.get("name")):
        return False
    try:
        homepage = str(note["URL"] or "").strip()
    except Exception:
        homepage = ""
    if not homepage:
        return False
    try:
        return bool(open_location(card_id, homepage))
    except Exception:
        return False


def build_reviewer_web_home_button_js(
    enabled: bool,
    *,
    label: str = "Open Homepage",
) -> str:
    safe_label = json.dumps(str(label or "Open Homepage"))
    enabled_js = "true" if enabled else "false"
    return f"""
(function() {{
  var enabled = {enabled_js};
  var wrapId = "incremento-web-homepage-wrap";
  var buttonId = "incremento-web-homepage-button";
  var styleId = "incremento-web-homepage-style";
  var existingWrap = document.getElementById(wrapId);
  if (existingWrap) {{
    existingWrap.remove();
  }}
  var style = document.getElementById(styleId);
  if (!enabled) {{
    if (style) {{
      style.remove();
    }}
    return;
  }}
  if (!document.body) {{
    return;
  }}
  if (!style) {{
    style = document.createElement("style");
    style.id = styleId;
    style.textContent = `
      #${{wrapId}} {{
        display: flex;
        justify-content: center;
        margin: 0 0 16px 0;
      }}
      #${{buttonId}} {{
        appearance: none;
        border: 1px solid rgba(74, 144, 217, 0.36);
        border-radius: 999px;
        background: rgba(74, 144, 217, 0.10);
        color: #8fbce9;
        cursor: pointer;
        font-size: 13px;
        font-weight: 600;
        line-height: 1.1;
        padding: 8px 14px;
        transition: background 120ms ease, border-color 120ms ease, color 120ms ease;
      }}
      #${{buttonId}}:hover,
      #${{buttonId}}:focus {{
        background: rgba(74, 144, 217, 0.16);
        border-color: rgba(74, 144, 217, 0.52);
        color: #c0daf4;
      }}
    `;
    (document.head || document.documentElement).appendChild(style);
  }}
  var wrap = document.createElement("div");
  wrap.id = wrapId;
  var button = document.createElement("button");
  button.id = buttonId;
  button.type = "button";
  button.textContent = {safe_label};
  button.addEventListener("click", function() {{
    pycmd("incremento_open_web_home");
  }});
  wrap.appendChild(button);
  if (document.body.firstChild) {{
    document.body.insertBefore(wrap, document.body.firstChild);
  }} else {{
    document.body.appendChild(wrap);
  }}
}})();
""".strip()


class WebBookmarkPayload(TypedDict, total=False):
    mode: Literal["element", "selection"]
    path: list[int]
    offsetRatio: float
    scrollRatio: float
    tag: str
    text: str
    selectionStartPath: list[int]
    selectionStartOffset: int
    selectionEndPath: list[int]
    selectionEndOffset: int


class WebProgressState(TypedDict):
    url: str
    scroll_ratio: float
    bookmark_url: str
    bookmark_payload: WebBookmarkPayload
    media_url: str
    media_title: str
    media_seconds: float
    media_updated_at: int


class WebRestorePayload(TypedDict):
    rememberScroll: bool
    scrollRatio: float
    bookmark: WebBookmarkPayload | None


def _resolved_config(config: dict | None = None) -> dict:
    if config is not None:
        return config or {}
    try:
        from aqt import mw

        addon_name = __name__.split(".")[0]
        return mw.addonManager.getConfig(addon_name) or {}
    except Exception:
        return {}


def configured_remember_browser_card_scroll(config: dict | None = None) -> bool:
    config = _resolved_config(config)
    return bool(
        (config or {}).get(
            "remember_browser_card_scroll",
            _DEFAULT_REMEMBER_BROWSER_CARD_SCROLL,
        )
    )


def configured_prefer_web_card_resume_in_original_page(
    config: dict | None = None,
) -> bool:
    config = _resolved_config(config)
    return bool(
        (config or {}).get(
            "prefer_web_card_resume_in_original_page",
            _DEFAULT_PREFER_WEB_CARD_RESUME_IN_ORIGINAL_PAGE,
        )
    )


def _default_web_progress() -> WebProgressState:
    return {
        "url": "",
        "scroll_ratio": 0.0,
        "bookmark_url": "",
        "bookmark_payload": {},
        "media_url": "",
        "media_title": "",
        "media_seconds": 0.0,
        "media_updated_at": 0,
    }


def _normalize_scroll_ratio(value) -> float:
    try:
        ratio = float(value or 0.0)
    except Exception:
        ratio = 0.0
    return max(0.0, min(ratio, 1.0))


def _collapse_ws(value) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalize_media_url(value) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except Exception:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return raw


def _normalize_media_title(value) -> str:
    return _collapse_ws(value)[:240]


def _normalize_media_seconds(value) -> float:
    try:
        seconds = float(value or 0.0)
    except Exception:
        seconds = 0.0
    if seconds <= 0:
        return 0.0
    return round(seconds, 1)


def _normalize_media_updated_at(value) -> int:
    try:
        ts = int(value or 0)
    except Exception:
        ts = 0
    return max(0, ts)


def _normalize_bookmark_payload(payload) -> WebBookmarkPayload:
    if not isinstance(payload, dict):
        return {}
    path = payload.get("path")
    if not isinstance(path, list):
        return {}
    normalized_path: list[int] = []
    for item in path:
        try:
            idx = int(item)
        except Exception:
            return {}
        if idx < 0:
            return {}
        normalized_path.append(idx)

    def _normalize_node_path(value) -> list[int]:
        if not isinstance(value, list):
            return []
        result: list[int] = []
        for item in value:
            try:
                idx = int(item)
            except Exception:
                return []
            if idx < 0:
                return []
            result.append(idx)
        return result

    def _normalize_offset(value) -> int:
        try:
            offset = int(value or 0)
        except Exception:
            offset = 0
        return max(0, offset)

    text = str(payload.get("text") or "").strip()[:240]
    tag = str(payload.get("tag") or "").strip().lower()[:40]
    mode = str(payload.get("mode") or "").strip().lower()
    if mode not in {"", "element", "selection"}:
        mode = ""
    try:
        offset_ratio = float(payload.get("offsetRatio", 0.0) or 0.0)
    except Exception:
        offset_ratio = 0.0
    try:
        scroll_ratio = float(payload.get("scrollRatio", 0.0) or 0.0)
    except Exception:
        scroll_ratio = 0.0

    result: WebBookmarkPayload = {
        "path": normalized_path,
        "offsetRatio": max(0.0, min(offset_ratio, 1.0)),
        "scrollRatio": max(0.0, min(scroll_ratio, 1.0)),
        "tag": tag,
        "text": text,
    }
    if mode:
        result["mode"] = mode

    start_path = _normalize_node_path(payload.get("selectionStartPath"))
    end_path = _normalize_node_path(payload.get("selectionEndPath"))
    if start_path and end_path:
        result["selectionStartPath"] = start_path
        result["selectionStartOffset"] = _normalize_offset(
            payload.get("selectionStartOffset")
        )
        result["selectionEndPath"] = end_path
        result["selectionEndOffset"] = _normalize_offset(
            payload.get("selectionEndOffset")
        )

    return result


def get_web_progress(addon_dir: str, profile: str, card_id: int) -> WebProgressState:
    row = get_connection(addon_dir, profile).execute(
        "SELECT url, scroll_ratio, bookmark_url, bookmark_payload, media_url, media_title, media_seconds, media_updated_at "
        "FROM web_progress WHERE card_id = ?",
        (card_id,),
    ).fetchone()
    if not row:
        return _default_web_progress()
    try:
        bookmark_payload = json.loads(row[3] or "{}")
    except Exception:
        bookmark_payload = {}
    return {
        "url": str(row[0] or "").strip(),
        "scroll_ratio": _normalize_scroll_ratio(row[1]),
        "bookmark_url": str(row[2] or "").strip(),
        "bookmark_payload": _normalize_bookmark_payload(bookmark_payload),
        "media_url": _normalize_media_url(row[4]),
        "media_title": _normalize_media_title(row[5]),
        "media_seconds": _normalize_media_seconds(row[6]),
        "media_updated_at": _normalize_media_updated_at(row[7]),
    }


def build_web_restore_payload(
    progress: WebProgressState,
    current_url: str,
    *,
    allow_bookmark: bool,
    allow_scroll: bool,
    remember_scroll: bool,
) -> WebRestorePayload:
    bookmark_url = str(progress.get("bookmark_url") or "").strip()
    bookmark_payload = progress.get("bookmark_payload") or {}
    bookmark = None
    if allow_bookmark and bookmark_url and bookmark_payload and current_url == bookmark_url:
        bookmark = bookmark_payload
    return {
        "rememberScroll": bool(allow_scroll and remember_scroll),
        "scrollRatio": _normalize_scroll_ratio(progress.get("scroll_ratio")),
        "bookmark": bookmark,
    }


def _ensure_web_progress_row(addon_dir: str, profile: str, card_id: int) -> None:
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO web_progress "
        "(card_id, url, scroll_ratio, bookmark_url, bookmark_payload) "
        "VALUES (?, '', 0.0, '', '') "
        "ON CONFLICT(card_id) DO NOTHING",
        (card_id,),
    )
    conn.commit()


def _update_web_progress_columns(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    url: str | None = None,
    scroll_ratio: float | None = None,
    bookmark_url: str | None = None,
    bookmark_payload: WebBookmarkPayload | None = None,
    media_url: str | None = None,
    media_title: str | None = None,
    media_seconds: float | None = None,
    media_updated_at: int | None = None,
) -> None:
    _ensure_web_progress_row(addon_dir, profile, card_id)
    assignments: list[str] = []
    values: list[object] = []
    if url is not None:
        assignments.append("url = ?")
        values.append(str(url or "").strip())
    if scroll_ratio is not None:
        assignments.append("scroll_ratio = ?")
        values.append(_normalize_scroll_ratio(scroll_ratio))
    if bookmark_url is not None:
        assignments.append("bookmark_url = ?")
        values.append(str(bookmark_url or "").strip())
    if bookmark_payload is not None:
        assignments.append("bookmark_payload = ?")
        values.append(json.dumps(bookmark_payload, ensure_ascii=False))
    if media_url is not None:
        assignments.append("media_url = ?")
        values.append(_normalize_media_url(media_url))
    if media_title is not None:
        assignments.append("media_title = ?")
        values.append(_normalize_media_title(media_title))
    if media_seconds is not None:
        assignments.append("media_seconds = ?")
        values.append(_normalize_media_seconds(media_seconds))
    if media_updated_at is not None:
        assignments.append("media_updated_at = ?")
        values.append(_normalize_media_updated_at(media_updated_at))
    if not assignments:
        return
    values.append(card_id)
    conn = get_connection(addon_dir, profile)
    conn.execute(
        f"UPDATE web_progress SET {', '.join(assignments)} WHERE card_id = ?",
        tuple(values),
    )
    conn.commit()


def get_web_url(addon_dir: str, profile: str, card_id: int) -> str:
    """Return the last visited URL for this card, or '' if never saved."""
    return str(get_web_progress(addon_dir, profile, card_id).get("url") or "")


def set_web_url(addon_dir: str, profile: str, card_id: int, url: str) -> None:
    _update_web_progress_columns(addon_dir, profile, card_id, url=url)


def set_web_scroll_position(
    addon_dir: str,
    profile: str,
    card_id: int,
    url: str,
    scroll_ratio: float,
) -> None:
    _update_web_progress_columns(
        addon_dir,
        profile,
        card_id,
        url=url,
        scroll_ratio=scroll_ratio,
    )


def set_web_bookmark(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    url: str,
    bookmark_payload: WebBookmarkPayload | None,
) -> None:
    normalized = _normalize_bookmark_payload(bookmark_payload)
    if normalized:
        _update_web_progress_columns(
            addon_dir,
            profile,
            card_id,
            url=url,
            bookmark_url=url,
            bookmark_payload=normalized,
        )
        return
    _update_web_progress_columns(
        addon_dir,
        profile,
        card_id,
        url=url,
        bookmark_url="",
        bookmark_payload={},
    )


def set_web_media_progress(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    url: str,
    media_seconds: float,
    media_url: str = "",
    media_title: str = "",
    media_updated_at: int | None = None,
) -> None:
    normalized_seconds = _normalize_media_seconds(media_seconds)
    if normalized_seconds <= 0:
        return
    if media_updated_at is None:
        media_updated_at = int(time.time())
    _update_web_progress_columns(
        addon_dir,
        profile,
        card_id,
        url=url,
        media_url=media_url,
        media_title=media_title,
        media_seconds=normalized_seconds,
        media_updated_at=media_updated_at,
    )


def build_web_media_resume_target(
    page_url: str,
    media_url: str,
    media_seconds: float,
) -> str:
    seconds = max(0, int(_normalize_media_seconds(media_seconds)))
    if seconds <= 0:
        return ""

    try:
        from .video_manager import build_remote_video_watch_url as _build_remote_video_watch_url
    except ImportError:
        from video_manager import build_remote_video_watch_url as _build_remote_video_watch_url

    candidates = []
    page = str(page_url or "").strip()
    media = _normalize_media_url(media_url)
    if page:
        candidates.append(page)
    if media and media not in candidates:
        candidates.append(media)

    for candidate in candidates:
        try:
            resume_url = _build_remote_video_watch_url(candidate, start_sec=seconds)
        except Exception:
            resume_url = None
        if resume_url:
            return str(resume_url).strip()
    return ""


def build_external_web_url(
    url: str,
    *,
    card_id: int | None = None,
    track_with_extension: bool = False,
) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""

    try:
        cid = int(card_id) if card_id is not None else 0
    except Exception:
        cid = 0

    try:
        parsed = urlparse(raw)
        query_items = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k not in {TRACK_CARD_ID_PARAM, TRACK_WEB_FLAG_PARAM}
        ]
        if cid > 0:
            query_items.append((TRACK_CARD_ID_PARAM, str(cid)))
        if track_with_extension and cid > 0:
            query_items.append((TRACK_WEB_FLAG_PARAM, "1"))
        return urlunparse(parsed._replace(query=urlencode(query_items, doseq=True)))
    except Exception:
        if cid <= 0:
            return raw
        sep = "&" if "?" in raw else "?"
        out = f"{raw}{sep}{TRACK_CARD_ID_PARAM}={cid}"
        if track_with_extension:
            out += f"&{TRACK_WEB_FLAG_PARAM}=1"
        return out


def ensure_web_note_type(col) -> None:
    """Create the Incremento Web note type, or sync its template if it already exists."""
    models = col.models
    m = models.by_name(WEB_NOTE_TYPE)
    if m is None:
        m = models.new(WEB_NOTE_TYPE)
        for field_name in ("Title", "URL"):
            fld = models.new_field(field_name)
            models.add_field(m, fld)
        ensure_incremento_metadata_fields(models, m)
        tmpl = models.new_template("Card 1")
        tmpl["qfmt"] = CARD_TEMPLATE_FRONT
        tmpl["afmt"] = CARD_TEMPLATE_BACK
        models.add_template(m, tmpl)
        models.add(m)
    else:
        tmpl = m["tmpls"][0]
        changed = False
        if ensure_incremento_metadata_fields(models, m):
            changed = True
        if tmpl["qfmt"] != CARD_TEMPLATE_FRONT or tmpl["afmt"] != CARD_TEMPLATE_BACK:
            tmpl["qfmt"] = CARD_TEMPLATE_FRONT
            tmpl["afmt"] = CARD_TEMPLATE_BACK
            changed = True
        if changed:
            models.update_dict(m)


def add_web_card(
    col,
    url: str,
    title: str,
    deck_name: str = "Topics",
    tags: list[str] | None = None,
) -> int:
    """Create an Incremento Web note, return the card id."""
    ensure_web_note_type(col)
    deck = col.decks.by_name(deck_name)
    if deck is None:
        deck_id = col.decks.add_normal_deck_with_name(deck_name).id
    else:
        deck_id = deck["id"]
    model = col.models.by_name(WEB_NOTE_TYPE)

    def _build_note(stored_title: str):
        note = col.new_note(model)
        note["Title"] = stored_title
        note["URL"] = url
        apply_incremento_metadata(
            note,
            build_incremento_metadata(
                source_type="Web",
                source_title=title,
                source_link=url,
            ),
        )
        for tag in ["Incremento"] + [t for t in (tags or []) if t != "Incremento"]:
            if not tag:
                continue
            if hasattr(note, "add_tag"):
                note.add_tag(tag)
            elif hasattr(note, "tags"):
                note.tags.append(tag)
        note.note_type()["did"] = deck_id
        return note

    for attempt in range(25):
        stored_title = _stored_web_title(title, attempt)
        note = _build_note(stored_title)
        added = col.add_note(note, deck_id)
        if not added:
            continue
        cards = col.find_cards(f"nid:{note.id}")
        if cards:
            return cards[0]
    raise RuntimeError("Failed to add web card. Anki rejected the note.")
