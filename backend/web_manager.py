try:
    from .db import get_connection
except ImportError:
    from db import get_connection
import json
from typing import Literal, TypedDict
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_INVISIBLE_DUPLICATE_MARK = "\u200b"

WEB_NOTE_TYPE = "Incremento Web"
TRACK_CARD_ID_PARAM = "inc_card_id"
TRACK_WEB_FLAG_PARAM = "inc_track_web"
_DEFAULT_REMEMBER_BROWSER_CARD_SCROLL = True

CARD_TEMPLATE_FRONT = """
<div style="text-align:center; padding:60px 20px; font-family:sans-serif; color:#888;">
  <div style="font-size:1.3em; margin-bottom:10px; color:#ccc;">{{Title}}</div>
  <div style="font-size:0.85em;">Web page open in sidebar</div>
</div>
{{URL}}
""".strip()

CARD_TEMPLATE_BACK = "{{Title}}"


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


def _default_web_progress() -> WebProgressState:
    return {
        "url": "",
        "scroll_ratio": 0.0,
        "bookmark_url": "",
        "bookmark_payload": {},
    }


def _normalize_scroll_ratio(value) -> float:
    try:
        ratio = float(value or 0.0)
    except Exception:
        ratio = 0.0
    return max(0.0, min(ratio, 1.0))


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


def get_web_progress(addon_dir: str, card_id: int) -> WebProgressState:
    row = get_connection(addon_dir).execute(
        "SELECT url, scroll_ratio, bookmark_url, bookmark_payload "
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


def _ensure_web_progress_row(addon_dir: str, card_id: int) -> None:
    conn = get_connection(addon_dir)
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
    card_id: int,
    *,
    url: str | None = None,
    scroll_ratio: float | None = None,
    bookmark_url: str | None = None,
    bookmark_payload: WebBookmarkPayload | None = None,
) -> None:
    _ensure_web_progress_row(addon_dir, card_id)
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
    if not assignments:
        return
    values.append(card_id)
    conn = get_connection(addon_dir)
    conn.execute(
        f"UPDATE web_progress SET {', '.join(assignments)} WHERE card_id = ?",
        tuple(values),
    )
    conn.commit()


def get_web_url(addon_dir: str, card_id: int) -> str:
    """Return the last visited URL for this card, or '' if never saved."""
    return str(get_web_progress(addon_dir, card_id).get("url") or "")


def set_web_url(addon_dir: str, card_id: int, url: str) -> None:
    _update_web_progress_columns(addon_dir, card_id, url=url)


def set_web_scroll_position(
    addon_dir: str,
    card_id: int,
    url: str,
    scroll_ratio: float,
) -> None:
    _update_web_progress_columns(
        addon_dir,
        card_id,
        url=url,
        scroll_ratio=scroll_ratio,
    )


def set_web_bookmark(
    addon_dir: str,
    card_id: int,
    *,
    url: str,
    bookmark_payload: WebBookmarkPayload | None,
) -> None:
    normalized = _normalize_bookmark_payload(bookmark_payload)
    if normalized:
        _update_web_progress_columns(
            addon_dir,
            card_id,
            url=url,
            bookmark_url=url,
            bookmark_payload=normalized,
        )
        return
    _update_web_progress_columns(
        addon_dir,
        card_id,
        url=url,
        bookmark_url="",
        bookmark_payload={},
    )


def build_external_web_url(
    url: str,
    *,
    card_id: int | None = None,
    track_with_extension: bool = False,
) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""

    if not track_with_extension:
        return raw

    try:
        cid = int(card_id) if card_id is not None else 0
    except Exception:
        cid = 0
    if cid <= 0:
        return raw

    try:
        parsed = urlparse(raw)
        query_items = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k not in {TRACK_CARD_ID_PARAM, TRACK_WEB_FLAG_PARAM}
        ]
        query_items.append((TRACK_CARD_ID_PARAM, str(cid)))
        query_items.append((TRACK_WEB_FLAG_PARAM, "1"))
        return urlunparse(parsed._replace(query=urlencode(query_items, doseq=True)))
    except Exception:
        sep = "&" if "?" in raw else "?"
        return f"{raw}{sep}{TRACK_CARD_ID_PARAM}={cid}&{TRACK_WEB_FLAG_PARAM}=1"


def ensure_web_note_type(col) -> None:
    """Create the Incremento Web note type, or sync its template if it already exists."""
    models = col.models
    m = models.by_name(WEB_NOTE_TYPE)
    if m is None:
        m = models.new(WEB_NOTE_TYPE)
        for field_name in ("Title", "URL"):
            fld = models.new_field(field_name)
            models.add_field(m, fld)
        tmpl = models.new_template("Card 1")
        tmpl["qfmt"] = CARD_TEMPLATE_FRONT
        tmpl["afmt"] = CARD_TEMPLATE_BACK
        models.add_template(m, tmpl)
        models.add(m)
    else:
        tmpl = m["tmpls"][0]
        if tmpl["qfmt"] != CARD_TEMPLATE_FRONT or tmpl["afmt"] != CARD_TEMPLATE_BACK:
            tmpl["qfmt"] = CARD_TEMPLATE_FRONT
            tmpl["afmt"] = CARD_TEMPLATE_BACK
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
    raise RuntimeError("Failed to add web card. Anki rejected the note.")
