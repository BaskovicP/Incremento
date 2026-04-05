import json
import os
import tempfile
import threading
import uuid
from base64 import b64decode
from datetime import datetime
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

try:
    from .webpage_markdown import convert_webpage_html_to_markdown
except ImportError:
    from webpage_markdown import convert_webpage_html_to_markdown


BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8766
BRIDGE_PATH = "/incremento/add-content"
BROWSER_CAPTURE_META_PATH = "/incremento/browser-capture-meta"
WEB_TRACK_PATH = "/incremento/update-web-card"
WEB_TRACK_MEDIA_PATH = "/incremento/update-web-card-media"
_ALLOWED_ORIGIN_PREFIX = "chrome-extension://"
_MAX_HTML_CHARS = 2_000_000
_MAX_MARKDOWN_CHARS = 2_000_000
_MAX_BROWSER_CAPTURE_SNAPSHOTS = 12
_MAX_BROWSER_CAPTURE_IMAGE_BYTES = 8_000_000
_MAX_MEDIA_FILENAME_STEM = 80

_server: ThreadingHTTPServer | None = None
_server_thread: threading.Thread | None = None
_server_lock = threading.Lock()
_addon_dir: str = ""


def _collapse_ws(value) -> str:
    return " ".join(str(value or "").split()).strip()


def normalize_http_url(raw_url) -> str:
    raw = str(raw_url or "").strip()
    if not raw:
        raise ValueError("Missing URL.")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must start with http:// or https://")
    return raw


def url_looks_like_pdf(raw_url: str) -> bool:
    try:
        parsed = urlsplit(str(raw_url or "").strip())
    except Exception:
        return False
    path = str(parsed.path or "").lower()
    return path.endswith(".pdf")


def download_pdf_from_url(url: str, dest_path: str, timeout_sec: float = 20.0) -> None:
    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urlopen(req, timeout=max(1.0, float(timeout_sec))) as resp:
            content_type = str(resp.headers.get("Content-Type") or "").lower()
            payload = resp.read()
    except (URLError, HTTPError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f"Failed to download PDF: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Failed to download PDF: {exc}") from exc

    if not payload:
        raise RuntimeError("Failed to download PDF: empty response.")

    sniff = payload[:4096].lstrip()
    looks_like_html = (
        sniff[:256].lower().startswith(b"<!doctype html")
        or sniff[:256].lower().startswith(b"<html")
    )
    looks_like_pdf = (
        "pdf" in content_type
        or b"%PDF-" in sniff
        or (url_looks_like_pdf(url) and len(payload) > 1024 and not looks_like_html)
    )
    if not looks_like_pdf:
        raise RuntimeError("URL did not return a PDF file.")

    with open(dest_path, "wb") as handle:
        handle.write(payload)


def build_writing_markdown(
    title: str,
    url: str,
    selected_text: str = "",
    page_markdown: str = "",
) -> str:
    clean_title = _collapse_ws(title) or "Untitled"
    clean_url = normalize_http_url(url)
    clean_selection = str(selected_text or "").strip()
    clean_page_markdown = str(page_markdown or "").strip()

    lines = [
        f"# {clean_title}",
        "",
        f"Source: {clean_url}",
        "",
    ]
    if clean_page_markdown:
        lines.extend([
            clean_page_markdown,
            "",
        ])
    if clean_selection:
        lines.extend([
            "## Selected text",
            "",
            clean_selection,
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def _normalize_tags(raw_tags) -> list[str]:
    tags = []
    if raw_tags is None:
        return tags
    if isinstance(raw_tags, str):
        candidates = raw_tags.replace(",", " ").split()
    elif isinstance(raw_tags, (list, tuple)):
        candidates = raw_tags
    else:
        raise ValueError("Tags must be a list or string.")
    for tag in candidates:
        clean = _collapse_ws(tag)
        if clean and clean not in tags:
            tags.append(clean)
    return tags


def _normalize_priority(raw_priority) -> float:
    if raw_priority is None or raw_priority == "":
        return 50.0
    try:
        priority = round(float(raw_priority), 4)
    except (TypeError, ValueError) as exc:
        raise ValueError("Priority must be a decimal number between 0.0000 and 100.0000.") from exc
    if not (0.0 <= priority <= 100.0):
        raise ValueError("Priority must be between 0.0000 and 100.0000.")
    return priority


def _normalize_browser_capture_field_name(raw_name) -> str:
    return _collapse_ws(raw_name)


def _normalize_browser_capture_field_mappings(raw_mappings) -> dict[str, str]:
    if raw_mappings is None:
        raw_mappings = {}
    if not isinstance(raw_mappings, dict):
        raise ValueError("fieldMappings must be a JSON object.")
    return {
        "title_field": _normalize_browser_capture_field_name(raw_mappings.get("titleField")),
        "selected_text_field": _normalize_browser_capture_field_name(raw_mappings.get("selectedTextField")),
        "url_field": _normalize_browser_capture_field_name(raw_mappings.get("urlField")),
        "snapshot_field": _normalize_browser_capture_field_name(raw_mappings.get("snapshotField")),
    }


def _normalize_browser_capture_snapshots(raw_snapshots) -> list[dict]:
    if raw_snapshots is None:
        return []
    if not isinstance(raw_snapshots, list):
        raise ValueError("snapshots must be an array.")
    if len(raw_snapshots) > _MAX_BROWSER_CAPTURE_SNAPSHOTS:
        raise ValueError(f"Too many snapshots. Maximum is {_MAX_BROWSER_CAPTURE_SNAPSHOTS}.")

    normalized = []
    for idx, raw_snapshot in enumerate(raw_snapshots):
        if not isinstance(raw_snapshot, dict):
            raise ValueError("Each snapshot must be a JSON object.")
        mime_type = _collapse_ws(raw_snapshot.get("mimeType", "")).lower() or "image/png"
        if mime_type != "image/png":
            raise ValueError("Only PNG snapshots are supported.")
        filename = _collapse_ws(raw_snapshot.get("filename", "")) or f"browser-capture-{idx + 1}.png"
        base64_data = str(raw_snapshot.get("base64", "") or "").strip()
        if not base64_data:
            raise ValueError("Each snapshot must include base64 image data.")
        try:
            raw_bytes = b64decode(base64_data, validate=True)
        except Exception as exc:
            raise ValueError(f"Invalid snapshot payload: {exc}") from exc
        if not raw_bytes:
            raise ValueError("Snapshot payload cannot be empty.")
        if len(raw_bytes) > _MAX_BROWSER_CAPTURE_IMAGE_BYTES:
            raise ValueError("Snapshot image is too large.")
        normalized.append(
            {
                "mime_type": mime_type,
                "filename": filename,
                "base64": base64_data,
                "bytes": raw_bytes,
            }
        )
    return normalized


def normalize_browser_capture_payload(payload) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")

    note_type_name = _collapse_ws(payload.get("noteTypeName", ""))
    if not note_type_name:
        raise ValueError("noteTypeName is required.")

    return {
        "type": "browser_capture",
        "url": normalize_http_url(payload.get("url", "")),
        "title": _collapse_ws(payload.get("title", "")) or "Untitled",
        "deck_name": _collapse_ws(payload.get("deckName", "")) or "Default",
        "note_type_name": note_type_name,
        "tags": _normalize_tags(payload.get("tags")),
        "priority": _normalize_priority(payload.get("priority")),
        "selected_text": str(payload.get("selectedText", "") or "").strip(),
        "field_mappings": _normalize_browser_capture_field_mappings(payload.get("fieldMappings")),
        "snapshots": _normalize_browser_capture_snapshots(payload.get("snapshots")),
    }


def normalize_add_content_payload(payload) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")

    raw_kind = _collapse_ws(payload.get("kind", "")).casefold()
    kind_aliases = {
        "pdf": "pdf",
        "video": "video",
        "youtube": "video",
        "web": "webpage",
        "webpage": "webpage",
        "writing": "writing",
    }
    kind = kind_aliases.get(raw_kind)
    if not kind:
        raise ValueError("Kind must be one of: pdf, video, webpage, writing.")

    url = normalize_http_url(payload.get("url", ""))
    title = _collapse_ws(payload.get("title", "")) or url
    deck_name = _collapse_ws(payload.get("deckName", "")) or "Topics"
    selected_text = str(payload.get("selectedText", "") or "").strip()
    html = str(payload.get("html", "") or "")
    if len(html) > _MAX_HTML_CHARS:
        html = ""
    markdown = str(payload.get("markdown", "") or "")
    if len(markdown) > _MAX_MARKDOWN_CHARS:
        raise ValueError("Markdown payload is too large.")
    preferred_filename = _collapse_ws(payload.get("preferredFilename", ""))
    raw_writing_mode = _collapse_ws(payload.get("writingMode", "")).lower()
    if raw_writing_mode not in {"", "selection", "webpage_markdown"}:
        raise ValueError("writingMode must be 'selection' or 'webpage_markdown'.")
    raw_page_content_scope = _collapse_ws(payload.get("pageContentScope", "")).lower()
    if raw_page_content_scope not in {"", "main", "full"}:
        raise ValueError("pageContentScope must be 'main' or 'full'.")
    pdf_base64 = str(payload.get("pdfBase64", "") or "").strip()
    pdf_filename = _collapse_ws(payload.get("pdfFilename", ""))

    return {
        "kind": kind,
        "url": url,
        "title": title,
        "deck_name": deck_name,
        "tags": _normalize_tags(payload.get("tags")),
        "priority": _normalize_priority(payload.get("priority")),
        "selected_text": selected_text,
        "html": html,
        "markdown": markdown,
        "preferred_filename": preferred_filename,
        "writing_mode": raw_writing_mode or "selection",
        "page_content_scope": raw_page_content_scope or "main",
        "pdf_base64": pdf_base64,
        "pdf_filename": pdf_filename,
    }


def normalize_add_content_batch_payload(payload) -> list[dict]:
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Items must be a non-empty array.")

    normalized = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise ValueError("Each item must be a JSON object.")
        merged = dict(raw_item)
        if "deckName" not in merged and "deckName" in payload:
            merged["deckName"] = payload.get("deckName")
        normalized.append(normalize_add_content_payload(merged))
    return normalized


def normalize_add_content_request(payload) -> dict:
    if isinstance(payload, dict) and str(payload.get("type") or "").strip().lower() == "browser_capture":
        return {"batch": False, "browser_capture": True, "items": [normalize_browser_capture_payload(payload)]}
    if isinstance(payload, dict) and payload.get("items") is not None:
        items = normalize_add_content_batch_payload(payload)
        return {"batch": True, "browser_capture": False, "items": items}
    return {"batch": False, "browser_capture": False, "items": [normalize_add_content_payload(payload)]}


def normalize_update_web_card_payload(payload) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")

    try:
        card_id = int(payload.get("cardId") or 0)
    except Exception as exc:
        raise ValueError("cardId must be a positive integer.") from exc
    if card_id <= 0:
        raise ValueError("cardId must be a positive integer.")

    url = normalize_http_url(payload.get("url", ""))
    title = _collapse_ws(payload.get("title", ""))
    return {
        "card_id": card_id,
        "url": url,
        "title": title,
    }


def normalize_update_web_card_media_payload(payload) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")

    try:
        card_id = int(payload.get("cardId") or 0)
    except Exception as exc:
        raise ValueError("cardId must be a positive integer.") from exc
    if card_id <= 0:
        raise ValueError("cardId must be a positive integer.")

    url = normalize_http_url(payload.get("url", ""))

    raw_media_url = str(payload.get("mediaUrl", "") or "").strip()
    media_url = ""
    if raw_media_url:
        try:
            media_url = normalize_http_url(raw_media_url)
        except ValueError:
            media_url = ""

    media_title = _collapse_ws(payload.get("mediaTitle", ""))
    try:
        seconds = float(payload.get("seconds") or 0.0)
    except Exception as exc:
        raise ValueError("seconds must be a positive number.") from exc
    if seconds <= 0:
        raise ValueError("seconds must be a positive number.")

    return {
        "card_id": card_id,
        "url": url,
        "media_url": media_url,
        "media_title": media_title,
        "seconds": round(seconds, 1),
    }


def _run_on_main_and_wait(fn, timeout_sec: float = 180.0):
    from aqt import mw

    done = threading.Event()
    box: dict[str, object] = {}

    def _wrapped() -> None:
        try:
            box["result"] = fn()
        except Exception as exc:
            box["error"] = exc
        finally:
            done.set()

    mw.taskman.run_on_main(_wrapped)
    if not done.wait(timeout=timeout_sec):
        raise TimeoutError("Incremento browser bridge timed out.")
    if "error" in box:
        raise box["error"]
    return box.get("result")


def _refresh_anki_after_import() -> None:
    from aqt import mw

    try:
        mw.col.reset()
    except Exception:
        pass

    try:
        mw.reset()
    except Exception:
        pass

    try:
        if getattr(mw, "deckBrowser", None):
            mw.deckBrowser.refresh()
    except Exception:
        pass


def _browser_capture_meta_on_main() -> dict:
    from aqt import mw

    note_types = []
    try:
        for model in mw.col.models.all():
            if not isinstance(model, dict):
                continue
            fields = []
            for field in model.get("flds") or []:
                if isinstance(field, dict):
                    name = _collapse_ws(field.get("name", ""))
                    if name:
                        fields.append(name)
            note_name = _collapse_ws(model.get("name", ""))
            if note_name and fields:
                note_types.append({"name": note_name, "fields": fields})
    except Exception:
        note_types = []

    deck_names = []
    try:
        deck_names = sorted(
            {
                _collapse_ws(deck.name)
                for deck in mw.col.decks.all_names_and_ids()
                if _collapse_ws(getattr(deck, "name", ""))
            }
        )
    except Exception:
        deck_names = []

    return {
        "ok": True,
        "noteTypes": sorted(note_types, key=lambda item: item["name"].casefold()),
        "deckNames": deck_names,
    }


def _append_browser_capture_html(existing: str, chunk: str) -> str:
    left = str(existing or "").strip()
    right = str(chunk or "").strip()
    if not right:
        return left
    if not left:
        return right
    return f"{left}<br><br>{right}"


def _plain_text_to_html(text: str) -> str:
    safe = escape(str(text or ""))
    return safe.replace("\n", "<br>")


def _browser_capture_source_html(url: str) -> str:
    safe_url = escape(url, quote=True)
    return f'Source: <a href="{safe_url}">{safe_url}</a>'


def _browser_capture_unique_label_suffix() -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"


def _browser_capture_note_title(title: str, url: str, *, unique: bool) -> str:
    base_title = _collapse_ws(title) or _collapse_ws(url) or "Untitled"
    if not unique:
        return base_title
    return f"{base_title} [snapshot {_browser_capture_unique_label_suffix()}]"


def _sanitize_media_filename(raw_name: str, fallback_stem: str) -> str:
    stem, ext = os.path.splitext(os.path.basename(str(raw_name or "").strip()))
    stem = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in stem).strip(".-_")
    if not stem:
        stem = fallback_stem
    stem = stem[:_MAX_MEDIA_FILENAME_STEM].strip(".-_") or "browser-capture"
    ext = ".png"
    return f"{stem}-{uuid.uuid4().hex}{ext}"


def _store_browser_capture_snapshot(col, snapshot: dict, title: str, index: int) -> str:
    fd, temp_path = tempfile.mkstemp(prefix="incremento-browser-capture-", suffix=".png")
    os.close(fd)
    try:
        with open(temp_path, "wb") as handle:
            handle.write(snapshot["bytes"])
        filename = _sanitize_media_filename(
            snapshot.get("filename", ""),
            fallback_stem=f"{_collapse_ws(title).replace(' ', '-') or 'browser-capture'}-{index}",
        )
        stored_path = temp_path
        desired_path = os.path.join(os.path.dirname(temp_path), filename)
        if desired_path != temp_path:
            try:
                os.replace(temp_path, desired_path)
                stored_path = desired_path
            except OSError:
                stored_path = temp_path
        return col.media.add_file(stored_path)
    finally:
        for path in {temp_path, locals().get("desired_path", "")}:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass


def _create_browser_capture_note_on_main(normalized: dict) -> dict:
    from aqt import mw

    try:
        from .priority_manager import set_priority
        from .paths import get_active_profile as _active_profile
    except ImportError:
        from priority_manager import set_priority  # type: ignore
        from paths import get_active_profile as _active_profile  # type: ignore

    note_type_name = normalized["note_type_name"]
    model = mw.col.models.by_name(note_type_name)
    if model is None:
        raise ValueError(f"Note type '{note_type_name}' was not found.")

    field_names = [str(field.get("name") or "") for field in model.get("flds") or [] if str(field.get("name") or "").strip()]
    if not field_names:
        raise ValueError(f"Note type '{note_type_name}' has no writable fields.")

    deck_name = normalized["deck_name"]
    deck = mw.col.decks.by_name(deck_name)
    if deck is None:
        deck_id = mw.col.decks.add_normal_deck_with_name(deck_name).id
    else:
        deck_id = deck["id"]

    mappings = normalized["field_mappings"]
    for mapping_name, field_name in mappings.items():
        if field_name and field_name not in field_names:
            raise ValueError(f"Field '{field_name}' was not found in note type '{note_type_name}'.")

    note = mw.col.new_note(model)
    field_html: dict[str, str] = {}

    selected_text = normalized["selected_text"]
    first_field_name = field_names[0]
    title_field = mappings["title_field"]

    if title_field:
        capture_title = _browser_capture_note_title(
            normalized["title"],
            normalized["url"],
            unique=title_field == first_field_name,
        )
        field_html[title_field] = _append_browser_capture_html(
            field_html.get(title_field, ""),
            _plain_text_to_html(capture_title),
        )

    if selected_text and mappings["selected_text_field"]:
        field_name = mappings["selected_text_field"]
        field_html[field_name] = _append_browser_capture_html(field_html.get(field_name, ""), _plain_text_to_html(selected_text))

    if mappings["url_field"]:
        field_name = mappings["url_field"]
        field_html[field_name] = _append_browser_capture_html(field_html.get(field_name, ""), _browser_capture_source_html(normalized["url"]))

    if mappings["snapshot_field"]:
        field_name = mappings["snapshot_field"]
        snapshot_html = ""
        for idx, snapshot in enumerate(normalized["snapshots"], start=1):
            media_filename = _store_browser_capture_snapshot(mw.col, snapshot, normalized["title"], idx)
            snapshot_html = _append_browser_capture_html(snapshot_html, f'<img src="{escape(media_filename, quote=True)}">')
        field_html[field_name] = _append_browser_capture_html(field_html.get(field_name, ""), snapshot_html)

    if not any(value for value in field_html.values()):
        raise ValueError("Nothing to insert. Choose at least one mapped destination field.")

    for field_name, value in field_html.items():
        note[field_name] = value

    for tag in ["Incremento"] + [t for t in normalized["tags"] if t != "Incremento"]:
        if not tag:
            continue
        if hasattr(note, "add_tag"):
            note.add_tag(tag)
        elif hasattr(note, "tags"):
            note.tags.append(tag)

    note.note_type()["did"] = deck_id
    added = mw.col.add_note(note, deck_id)
    if not added:
        try:
            first_field_value = _collapse_ws(note[first_field_name])
        except Exception:
            first_field_value = ""
        if not first_field_value:
            raise ValueError(f"Could not create note. The first field '{first_field_name}' is empty.")
        raise ValueError(
            f"Could not create note. The first field '{first_field_name}' duplicates an existing note: {first_field_value}"
        )
    try:
        card_id = mw.col.find_cards(f"nid:{note.id}")[0]
    except Exception as exc:
        raise RuntimeError("Created note but could not resolve its card id.") from exc
    set_priority(_addon_dir, _active_profile(), int(card_id), normalized["priority"])
    return {
        "ok": True,
        "type": "browser_capture",
        "cardId": int(card_id),
        "noteId": int(note.id),
        "noteTypeName": note_type_name,
        "deckName": deck_name,
        "title": normalized["title"],
    }


def _add_content_item_on_main(normalized: dict) -> dict:
    from aqt import mw

    from .pdf_manager import add_pdf_card
    from .priority_manager import set_priority
    from .paths import get_active_profile as _active_profile
    from .video_manager import add_video_card, is_supported_video_url, resolve_video_url_for_embed
    from .web_manager import add_web_card
    from .writing_manager import add_writing_card
    from ..frontend.webpage_dialog import render_webpage_to_pdf

    kind = normalized["kind"]
    url = normalized["url"]
    title = normalized["title"]
    deck_name = normalized["deck_name"]
    tags = normalized["tags"]
    priority = normalized["priority"]
    selected_text = normalized["selected_text"]
    html = normalized["html"]
    markdown = normalized["markdown"]
    preferred_filename = normalized["preferred_filename"]
    writing_mode = normalized["writing_mode"]
    page_content_scope = normalized["page_content_scope"]
    pdf_base64 = normalized["pdf_base64"]

    if kind == "video":
        video_url = resolve_video_url_for_embed(url)
        if not is_supported_video_url(video_url):
            raise ValueError("Video URL must be a supported YouTube or Vimeo page.")
        card_id = add_video_card(
            mw.col,
            youtube_url=video_url,
            title=title,
            deck_name=deck_name,
            tags=tags,
        )
    elif kind == "webpage":
        card_id = add_web_card(
            mw.col,
            url=url,
            title=title,
            deck_name=deck_name,
            tags=tags,
        )
    elif kind == "writing":
        initial_markdown = str(markdown or "").strip()
        if not initial_markdown and writing_mode == "webpage_markdown":
            page_result = convert_webpage_html_to_markdown(
                url,
                html,
                title=title,
                content_scope=page_content_scope,
            )
            title = _collapse_ws(page_result.get("title", "")) or title
            initial_markdown = build_writing_markdown(
                title,
                url,
                page_markdown=page_result.get("markdown", ""),
            )
        if not initial_markdown:
            initial_markdown = build_writing_markdown(title, url, selected_text)
        card_id = add_writing_card(
            _addon_dir,
            mw.col,
            title=title,
            deck_name=deck_name,
            tags=tags,
            initial_markdown=initial_markdown,
            preferred_filename=preferred_filename,
        )
    else:
        fd, temp_pdf_path = tempfile.mkstemp(prefix="incremento-webpage-", suffix=".pdf")
        os.close(fd)
        try:
            if pdf_base64:
                try:
                    pdf_bytes = b64decode(pdf_base64, validate=True)
                except Exception as exc:
                    raise ValueError(f"Invalid PDF payload: {exc}") from exc
                if not pdf_bytes:
                    raise ValueError("Invalid PDF payload: empty file.")
                with open(temp_pdf_path, "wb") as handle:
                    handle.write(pdf_bytes)
            elif url_looks_like_pdf(url):
                download_pdf_from_url(url, temp_pdf_path)
            else:
                render_webpage_to_pdf(
                    temp_pdf_path,
                    url=url,
                    html=html,
                )
            card_id = add_pdf_card(
                _addon_dir,
                mw.col,
                temp_pdf_path,
                title,
                deck_name=deck_name,
                tags=tags,
            )
        finally:
            try:
                os.remove(temp_pdf_path)
            except OSError:
                pass

    set_priority(_addon_dir, _active_profile(), int(card_id), priority)

    return {
        "ok": True,
        "kind": kind,
        "cardId": int(card_id),
        "title": title,
        "deckName": deck_name,
    }


def _add_content_on_main(payload: dict) -> dict:
    request = normalize_add_content_request(payload)
    if request.get("browser_capture"):
        result = _create_browser_capture_note_on_main(request["items"][0])
        _refresh_anki_after_import()
        return result

    batch = bool(request["batch"])
    results = []
    any_success = False

    for normalized in request["items"]:
        try:
            item_result = _add_content_item_on_main(normalized)
            results.append(item_result)
            any_success = True
        except Exception as exc:
            if not batch:
                raise
            results.append(
                {
                    "ok": False,
                    "kind": normalized["kind"],
                    "title": normalized["title"],
                    "deckName": normalized["deck_name"],
                    "error": str(exc),
                }
            )

    if any_success:
        _refresh_anki_after_import()

    if not batch:
        return results[0]

    imported_count = sum(1 for item in results if item.get("ok"))
    failed_count = len(results) - imported_count
    return {
        "ok": True,
        "results": results,
        "importedCount": imported_count,
        "failedCount": failed_count,
    }


def _update_web_card_on_main(payload: dict) -> dict:
    from aqt import mw

    from .web_manager import WEB_NOTE_TYPE, set_web_url
    from .paths import get_active_profile as _active_profile

    normalized = normalize_update_web_card_payload(payload)
    card_id = int(normalized["card_id"])
    url = normalized["url"]

    try:
        card = mw.col.get_card(card_id)
    except Exception as exc:
        raise ValueError(f"Could not load card {card_id}.") from exc
    if card is None:
        raise ValueError(f"Card {card_id} was not found.")

    try:
        note = mw.col.get_note(card.nid)
        model = mw.col.models.get(note.mid)
    except Exception as exc:
        raise ValueError(f"Could not inspect card {card_id}.") from exc
    if model is None or model.get("name") != WEB_NOTE_TYPE:
        raise ValueError(f"Card {card_id} is not an Incremento Web card.")

    set_web_url(_addon_dir, _active_profile(), card_id, url)
    try:
        from ..frontend.web_dock import sync_external_web_url

        sync_external_web_url(card_id, url)
    except Exception:
        pass
    return {
        "ok": True,
        "cardId": card_id,
        "url": url,
        "title": normalized["title"],
    }


def _update_web_card_media_on_main(payload: dict) -> dict:
    from aqt import mw

    from .web_manager import WEB_NOTE_TYPE, set_web_media_progress
    from .paths import get_active_profile as _active_profile

    normalized = normalize_update_web_card_media_payload(payload)
    card_id = int(normalized["card_id"])

    try:
        card = mw.col.get_card(card_id)
    except Exception as exc:
        raise ValueError(f"Could not load card {card_id}.") from exc
    if card is None:
        raise ValueError(f"Card {card_id} was not found.")

    try:
        note = mw.col.get_note(card.nid)
        model = mw.col.models.get(note.mid)
    except Exception as exc:
        raise ValueError(f"Could not inspect card {card_id}.") from exc
    if model is None or model.get("name") != WEB_NOTE_TYPE:
        raise ValueError(f"Card {card_id} is not an Incremento Web card.")

    set_web_media_progress(
        _addon_dir,
        _active_profile(),
        card_id,
        url=normalized["url"],
        media_url=normalized["media_url"],
        media_title=normalized["media_title"],
        media_seconds=normalized["seconds"],
    )
    try:
        from ..frontend.web_dock import sync_external_web_media_state

        sync_external_web_media_state(
            card_id,
            normalized["url"],
            normalized["media_url"],
            normalized["media_title"],
            normalized["seconds"],
        )
    except Exception:
        pass
    return {
        "ok": True,
        "cardId": card_id,
        "url": normalized["url"],
        "mediaUrl": normalized["media_url"],
        "mediaTitle": normalized["media_title"],
        "seconds": normalized["seconds"],
    }


class _IncrementoBridgeHandler(BaseHTTPRequestHandler):
    server_version = "IncrementoBrowserBridge/1.0"

    def log_message(self, format, *args):
        return

    def _request_origin_allowed(self) -> bool:
        origin = str(self.headers.get("Origin") or "")
        return not origin or origin.startswith(_ALLOWED_ORIGIN_PREFIX)

    def _send_cors_headers(self) -> None:
        origin = str(self.headers.get("Origin") or "")
        if origin.startswith(_ALLOWED_ORIGIN_PREFIX):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        if self.path not in {BRIDGE_PATH, BROWSER_CAPTURE_META_PATH, WEB_TRACK_PATH, WEB_TRACK_MEDIA_PATH}:
            self.send_error(404)
            return
        if not self._request_origin_allowed():
            self.send_error(403)
            return
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path != BROWSER_CAPTURE_META_PATH:
            self._send_json(404, {"ok": False, "error": "Unknown path."})
            return
        if not self._request_origin_allowed():
            self._send_json(403, {"ok": False, "error": "Origin not allowed."})
            return

        try:
            result = _run_on_main_and_wait(_browser_capture_meta_on_main)
        except Exception as exc:
            self._send_json(500, {"ok": False, "error": str(exc)})
            return

        self._send_json(200, result)

    def do_POST(self) -> None:
        if self.path not in {BRIDGE_PATH, WEB_TRACK_PATH, WEB_TRACK_MEDIA_PATH}:
            self._send_json(404, {"ok": False, "error": "Unknown path."})
            return
        if not self._request_origin_allowed():
            self._send_json(403, {"ok": False, "error": "Origin not allowed."})
            return

        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0
        raw = self.rfile.read(max(0, length))

        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            self._send_json(400, {"ok": False, "error": "Invalid JSON."})
            return

        try:
            if self.path == BRIDGE_PATH:
                result = _run_on_main_and_wait(lambda: _add_content_on_main(payload))
            elif self.path == WEB_TRACK_MEDIA_PATH:
                result = _run_on_main_and_wait(lambda: _update_web_card_media_on_main(payload))
            else:
                result = _run_on_main_and_wait(lambda: _update_web_card_on_main(payload))
        except Exception as exc:
            self._send_json(500, {"ok": False, "error": str(exc)})
            return

        self._send_json(200, result)


def start_browser_bridge(addon_dir: str) -> None:
    global _server, _server_thread, _addon_dir

    with _server_lock:
        _addon_dir = addon_dir
        if _server is not None and _server_thread is not None and _server_thread.is_alive():
            return
        try:
            server = ThreadingHTTPServer((BRIDGE_HOST, BRIDGE_PORT), _IncrementoBridgeHandler)
        except OSError as exc:
            print(f"[Incremento] Browser bridge failed to start on {BRIDGE_HOST}:{BRIDGE_PORT}: {exc}")
            return
        server.daemon_threads = True
        _server = server
        _server_thread = threading.Thread(
            target=server.serve_forever,
            name="IncrementoBrowserBridge",
            daemon=True,
        )
        _server_thread.start()


def stop_browser_bridge(*_args, **_kwargs) -> None:
    global _server, _server_thread

    with _server_lock:
        server = _server
        thread = _server_thread
        _server = None
        _server_thread = None

    if server is not None:
        try:
            server.shutdown()
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass
    if thread is not None and thread.is_alive():
        thread.join(timeout=1.0)
