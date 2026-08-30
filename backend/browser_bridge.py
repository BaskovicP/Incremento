import json
import hmac
import os
import re
import secrets
import tempfile
import threading
import time
import uuid
from base64 import b64decode
from datetime import datetime
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request

try:
    from .content_safety import (
        external_plain_text,
        external_plain_text_to_anki_html,
        external_plain_text_to_markdown,
        normalize_external_http_url,
    )
    from .network_safety import copy_response_limited, open_public_http
    from .webpage_markdown import convert_webpage_html_to_markdown
    from .note_metadata import (
        apply_incremento_metadata,
        build_incremento_metadata,
        ensure_incremento_metadata_fields,
        visible_field_names,
    )
except ImportError:
    from content_safety import (  # type: ignore
        external_plain_text,
        external_plain_text_to_anki_html,
        external_plain_text_to_markdown,
        normalize_external_http_url,
    )
    from network_safety import copy_response_limited, open_public_http  # type: ignore
    from webpage_markdown import convert_webpage_html_to_markdown
    from note_metadata import (  # type: ignore
        apply_incremento_metadata,
        build_incremento_metadata,
        ensure_incremento_metadata_fields,
        visible_field_names,
    )


BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8766
BRIDGE_PATH = "/incremento/add-content"
BROWSER_CAPTURE_META_PATH = "/incremento/browser-capture-meta"
WEB_TRACK_PATH = "/incremento/update-web-card"
WEB_TRACK_MEDIA_PATH = "/incremento/update-web-card-media"
BROWSER_MEDIA_REF_PATH = "/incremento/browser-media-ref"
BRIDGE_HANDSHAKE_PATH = "/incremento/handshake"
BRIDGE_PROTOCOL_VERSION = 2
_ALLOWED_ORIGIN_PREFIX = "chrome-extension://"
_EXTENSION_ORIGIN_RE = re.compile(r"^chrome-extension://[a-p]{32}$")
_MAX_REQUEST_BYTES = 64 * 1024 * 1024
_MAX_ACTIVE_REQUESTS = 8
_REQUEST_SOCKET_TIMEOUT_SECONDS = 15.0
_MAX_HTML_CHARS = 2_000_000
_MAX_MARKDOWN_CHARS = 2_000_000
_MAX_SELECTED_TEXT_CHARS = 200_000
_MAX_TITLE_CHARS = 1_000
_MAX_NAME_CHARS = 200
_MAX_TAGS = 100
_MAX_TAG_CHARS = 200
_MAX_BATCH_ITEMS = 100
_MAX_PDF_UPLOAD_BYTES = 48 * 1024 * 1024
_MAX_REMOTE_PDF_BYTES = 256 * 1024 * 1024
_MAX_BROWSER_CAPTURE_SNAPSHOTS = 12
_MAX_BROWSER_CAPTURE_IMAGE_BYTES = 8_000_000
_MAX_MEDIA_FILENAME_STEM = 80
_PREPARED_PDF_PATH_KEY = "_prepared_pdf_path"
_PREPARED_PDF_PAGE_TEXTS_KEY = "_prepared_pdf_page_texts"
_PREPARED_WRITING_MARKDOWN_KEY = "_prepared_writing_markdown"

_server: ThreadingHTTPServer | None = None
_server_thread: threading.Thread | None = None
_server_lock = threading.Lock()
_bridge_identity_lock = threading.Lock()
_request_slots = threading.BoundedSemaphore(_MAX_ACTIVE_REQUESTS)


class _BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Bound connection threads before request headers or bodies are parsed."""

    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = _MAX_ACTIVE_REQUESTS

    def __init__(self, *args, **kwargs):
        self._connection_slots = threading.BoundedSemaphore(_MAX_ACTIVE_REQUESTS)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address) -> None:
        if not self._connection_slots.acquire(blocking=False):
            try:
                request.close()
            except OSError:
                pass
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._connection_slots.release()
            raise

    def process_request_thread(self, request, client_address) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connection_slots.release()
_addon_dir: str = ""
_bridge_token: str = ""
_allowed_extension_origin: str = ""


def _collapse_ws(value) -> str:
    return " ".join(str(value or "").split()).strip()


def _bounded_collapsed(value, *, max_chars: int) -> str:
    return _collapse_ws(external_plain_text(value, max_chars=max_chars))[:max_chars]


def normalize_http_url(raw_url) -> str:
    return normalize_external_http_url(raw_url)


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
    part_path = f"{dest_path}.{uuid.uuid4().hex}.part"
    try:
        with open_public_http(req, timeout=max(1.0, float(timeout_sec))) as resp:
            content_type = str(resp.headers.get("Content-Type") or "").lower()
            with open(part_path, "xb") as handle:
                size, sniff_raw = copy_response_limited(
                    resp,
                    handle,
                    max_bytes=_MAX_REMOTE_PDF_BYTES,
                )

        if size <= 0:
            raise RuntimeError("Failed to download PDF: empty response.")
        sniff = sniff_raw.lstrip()
        looks_like_html = (
            sniff[:256].lower().startswith(b"<!doctype html")
            or sniff[:256].lower().startswith(b"<html")
        )
        looks_like_pdf = (
            "pdf" in content_type
            or b"%PDF-" in sniff
            or (url_looks_like_pdf(url) and size > 1024 and not looks_like_html)
        )
        if not looks_like_pdf:
            raise RuntimeError("URL did not return a PDF file.")
        os.replace(part_path, dest_path)
    except (URLError, HTTPError, TimeoutError, ValueError, RuntimeError) as exc:
        try:
            os.remove(part_path)
        except OSError:
            pass
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(f"Failed to download PDF: {exc}") from exc
    except Exception as exc:
        try:
            os.remove(part_path)
        except OSError:
            pass
        raise RuntimeError("Failed to download PDF.") from exc


def build_writing_markdown(
    title: str,
    url: str,
    selected_text: str = "",
    page_markdown: str = "",
) -> str:
    clean_title = external_plain_text_to_markdown(
        _collapse_ws(title) or "Untitled",
        max_chars=_MAX_TITLE_CHARS,
    )
    normalize_http_url(url)
    clean_selection = external_plain_text_to_markdown(
        selected_text,
        max_chars=_MAX_SELECTED_TEXT_CHARS,
    ).strip()
    clean_page_markdown = str(page_markdown or "").strip()

    lines = [
        f"# {clean_title}",
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
        clean = _bounded_collapsed(tag, max_chars=_MAX_TAG_CHARS)
        if clean and clean not in tags:
            tags.append(clean)
        if len(tags) > _MAX_TAGS:
            raise ValueError(f"Too many tags. Maximum is {_MAX_TAGS}.")
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


def _normalize_parent_card_id(raw_parent_card_id) -> int | None:
    if raw_parent_card_id in (None, ""):
        return None
    try:
        parent_card_id = int(raw_parent_card_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("parentCardId must be a positive integer.") from exc
    if parent_card_id <= 0:
        raise ValueError("parentCardId must be a positive integer.")
    return parent_card_id


def _normalize_browser_capture_field_name(raw_name) -> str:
    return _bounded_collapsed(raw_name, max_chars=_MAX_NAME_CHARS)


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
        filename = _bounded_collapsed(
            raw_snapshot.get("filename", ""), max_chars=255
        ) or f"browser-capture-{idx + 1}.png"
        base64_data = str(raw_snapshot.get("base64", "") or "").strip()
        if not base64_data:
            raise ValueError("Each snapshot must include base64 image data.")
        if len(base64_data) > ((_MAX_BROWSER_CAPTURE_IMAGE_BYTES * 4) // 3) + 8:
            raise ValueError("Snapshot image is too large.")
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

    note_type_name = _bounded_collapsed(
        payload.get("noteTypeName", ""), max_chars=_MAX_NAME_CHARS
    )
    if not note_type_name:
        raise ValueError("noteTypeName is required.")

    return {
        "type": "browser_capture",
        "url": normalize_http_url(payload.get("url", "")),
        "title": _bounded_collapsed(
            payload.get("title", ""), max_chars=_MAX_TITLE_CHARS
        )
        or "Untitled",
        "deck_name": _bounded_collapsed(
            payload.get("deckName", ""), max_chars=_MAX_NAME_CHARS
        )
        or "Default",
        "note_type_name": note_type_name,
        "tags": _normalize_tags(payload.get("tags")),
        "priority": _normalize_priority(payload.get("priority")),
        "parent_card_id": _normalize_parent_card_id(payload.get("parentCardId")),
        "selected_text": external_plain_text(
            payload.get("selectedText", ""), max_chars=_MAX_SELECTED_TEXT_CHARS
        ).strip(),
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
    title = _bounded_collapsed(
        payload.get("title", ""), max_chars=_MAX_TITLE_CHARS
    ) or url
    deck_name = _bounded_collapsed(
        payload.get("deckName", ""), max_chars=_MAX_NAME_CHARS
    ) or "Topics"
    selected_text = external_plain_text(
        payload.get("selectedText", ""), max_chars=_MAX_SELECTED_TEXT_CHARS
    ).strip()
    html = str(payload.get("html", "") or "")
    if len(html) > _MAX_HTML_CHARS:
        raise ValueError("HTML payload is too large.")
    markdown = str(payload.get("markdown", "") or "")
    if len(markdown) > _MAX_MARKDOWN_CHARS:
        raise ValueError("Markdown payload is too large.")
    preferred_filename = _bounded_collapsed(
        payload.get("preferredFilename", ""), max_chars=255
    )
    raw_writing_mode = _collapse_ws(payload.get("writingMode", "")).lower()
    if raw_writing_mode not in {"", "selection", "webpage_markdown"}:
        raise ValueError("writingMode must be 'selection' or 'webpage_markdown'.")
    raw_page_content_scope = _collapse_ws(payload.get("pageContentScope", "")).lower()
    if raw_page_content_scope not in {"", "main", "full"}:
        raise ValueError("pageContentScope must be 'main' or 'full'.")
    pdf_base64 = str(payload.get("pdfBase64", "") or "").strip()
    if len(pdf_base64) > ((_MAX_PDF_UPLOAD_BYTES * 4) // 3) + 8:
        raise ValueError("PDF payload is too large.")
    pdf_filename = _bounded_collapsed(payload.get("pdfFilename", ""), max_chars=255)
    raw_media_url = str(payload.get("mediaUrl", "") or "").strip()
    media_url = ""
    if raw_media_url:
        try:
            media_url = normalize_http_url(raw_media_url)
        except ValueError:
            media_url = ""
    media_title = _bounded_collapsed(
        payload.get("mediaTitle", ""), max_chars=_MAX_TITLE_CHARS
    )
    raw_media_seconds = payload.get("mediaSeconds", None)
    if raw_media_seconds in (None, ""):
        media_seconds = 0.0
    else:
        try:
            media_seconds = round(float(raw_media_seconds or 0.0), 1)
        except Exception as exc:
            raise ValueError("mediaSeconds must be a non-negative number.") from exc
        if media_seconds < 0:
            raise ValueError("mediaSeconds must be a non-negative number.")

    return {
        "kind": kind,
        "url": url,
        "title": title,
        "deck_name": deck_name,
        "tags": _normalize_tags(payload.get("tags")),
        "priority": _normalize_priority(payload.get("priority")),
        "parent_card_id": _normalize_parent_card_id(payload.get("parentCardId")),
        "selected_text": selected_text,
        "html": html,
        "markdown": markdown,
        "preferred_filename": preferred_filename,
        "writing_mode": raw_writing_mode or "selection",
        "page_content_scope": raw_page_content_scope or "main",
        "pdf_base64": pdf_base64,
        "pdf_filename": pdf_filename,
        "media_url": media_url,
        "media_title": media_title,
        "media_seconds": media_seconds,
    }


def normalize_add_content_batch_payload(payload) -> list[dict]:
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Items must be a non-empty array.")
    if len(raw_items) > _MAX_BATCH_ITEMS:
        raise ValueError(f"Too many items. Maximum is {_MAX_BATCH_ITEMS}.")

    normalized = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise ValueError("Each item must be a JSON object.")
        merged = dict(raw_item)
        if "deckName" not in merged and "deckName" in payload:
            merged["deckName"] = payload.get("deckName")
        if "parentCardId" not in merged and "parentCardId" in payload:
            merged["parentCardId"] = payload.get("parentCardId")
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


def normalize_browser_media_ref_payload(payload) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")

    try:
        card_id = int(payload.get("cardId") or 0)
    except Exception as exc:
        raise ValueError("cardId must be a positive integer.") from exc
    if card_id <= 0:
        raise ValueError("cardId must be a positive integer.")

    page_url = normalize_http_url(payload.get("pageUrl", payload.get("url", "")))

    raw_media_url = str(payload.get("mediaUrl", "") or "").strip()
    media_url = ""
    if raw_media_url:
        try:
            media_url = normalize_http_url(raw_media_url)
        except ValueError:
            media_url = ""

    media_title = _collapse_ws(payload.get("mediaTitle", payload.get("title", "")))
    try:
        seconds = float(payload.get("seconds") or 0.0)
    except Exception as exc:
        raise ValueError("seconds must be a non-negative number.") from exc
    if seconds < 0:
        raise ValueError("seconds must be a non-negative number.")

    return {
        "card_id": card_id,
        "page_url": page_url,
        "media_url": media_url,
        "media_title": media_title,
        "seconds": round(seconds, 1),
    }


def normalize_browser_media_ref_query(payload) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Query must be a mapping.")
    raw_card_id = payload.get("cardId")
    if isinstance(raw_card_id, list):
        raw_card_id = raw_card_id[0] if raw_card_id else 0
    try:
        card_id = int(raw_card_id or 0)
    except Exception as exc:
        raise ValueError("cardId must be a positive integer.") from exc
    if card_id <= 0:
        raise ValueError("cardId must be a positive integer.")
    return {"card_id": card_id}


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
        # TODO: New code should use CollectionOp() instead.
        mw.reset()
    except Exception:
        pass

    try:
        if getattr(mw, "deckBrowser", None):
            mw.deckBrowser.refresh()
    except Exception:
        pass


def _make_temp_pdf_path() -> str:
    fd, temp_path = tempfile.mkstemp(prefix="incremento-webpage-", suffix=".pdf")
    os.close(fd)
    return temp_path


def _looks_like_normalized_add_content_request(payload) -> bool:
    if not isinstance(payload, dict):
        return False
    if "batch" not in payload or "browser_capture" not in payload:
        return False
    items = payload.get("items")
    if not isinstance(items, list):
        return False
    return all(isinstance(item, dict) for item in items)


def _extract_pdf_pages_text_off_main(pdf_path: str) -> list[str]:
    try:
        from .pdf_manager import extract_pdf_pages_text
    except ImportError:
        from pdf_manager import extract_pdf_pages_text  # type: ignore

    try:
        return extract_pdf_pages_text(pdf_path, allow_qt=False)
    except Exception:
        return []


def _prepare_pdf_item_off_main(normalized: dict) -> None:
    if normalized.get("kind") != "pdf":
        return
    if normalized.get(_PREPARED_PDF_PATH_KEY):
        return
    if not normalized.get("pdf_base64") and not url_looks_like_pdf(normalized.get("url", "")):
        return

    temp_pdf_path = _make_temp_pdf_path()
    try:
        if normalized.get("pdf_base64"):
            try:
                pdf_bytes = b64decode(str(normalized.get("pdf_base64") or ""), validate=True)
            except Exception as exc:
                raise ValueError(f"Invalid PDF payload: {exc}") from exc
            if not pdf_bytes:
                raise ValueError("Invalid PDF payload: empty file.")
            if len(pdf_bytes) > _MAX_PDF_UPLOAD_BYTES:
                raise ValueError("PDF payload is too large.")
            with open(temp_pdf_path, "wb") as handle:
                handle.write(pdf_bytes)
        else:
            download_pdf_from_url(str(normalized.get("url") or ""), temp_pdf_path)

        normalized[_PREPARED_PDF_PATH_KEY] = temp_pdf_path
        page_texts = _extract_pdf_pages_text_off_main(temp_pdf_path)
        if page_texts:
            normalized[_PREPARED_PDF_PAGE_TEXTS_KEY] = page_texts
    except Exception:
        try:
            os.remove(temp_pdf_path)
        except OSError:
            pass
        raise


def _prepare_writing_item_off_main(normalized: dict) -> None:
    if normalized.get("kind") != "writing":
        return
    if str(normalized.get("markdown") or "").strip():
        return
    if normalized.get("writing_mode") != "webpage_markdown":
        return

    page_result = convert_webpage_html_to_markdown(
        str(normalized.get("url") or ""),
        str(normalized.get("html") or ""),
        title=str(normalized.get("title") or ""),
        content_scope=str(normalized.get("page_content_scope") or "main"),
    )
    title = _collapse_ws(page_result.get("title", "")) or str(normalized.get("title") or "")
    normalized["title"] = title
    normalized["markdown"] = build_writing_markdown(
        title,
        str(normalized.get("url") or ""),
        page_markdown=page_result.get("markdown", ""),
    )
    normalized[_PREPARED_WRITING_MARKDOWN_KEY] = True


def prepare_add_content_request_off_main(payload_or_request) -> dict:
    request = (
        payload_or_request
        if _looks_like_normalized_add_content_request(payload_or_request)
        else normalize_add_content_request(payload_or_request)
    )
    prepared = {
        "batch": bool(request["batch"]),
        "browser_capture": bool(request["browser_capture"]),
        "items": [dict(item) for item in request["items"]],
    }
    if prepared["browser_capture"]:
        return prepared

    try:
        for normalized in prepared["items"]:
            _prepare_writing_item_off_main(normalized)
            _prepare_pdf_item_off_main(normalized)
    except Exception:
        cleanup_prepared_add_content_request(prepared)
        raise
    return prepared


def cleanup_prepared_add_content_request(request: dict | None) -> None:
    if not isinstance(request, dict):
        return
    for item in request.get("items") or []:
        if not isinstance(item, dict):
            continue
        temp_pdf_path = str(item.pop(_PREPARED_PDF_PATH_KEY, "") or "")
        if not temp_pdf_path:
            continue
        try:
            os.remove(temp_pdf_path)
        except OSError:
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
            fields = visible_field_names(fields)
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
    return external_plain_text_to_anki_html(text)


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


def _parent_card_title_on_main(parent_card_id: int | None) -> str:
    if parent_card_id is None:
        return ""
    try:
        from aqt import mw

        card = mw.col.get_card(int(parent_card_id))
        note = card.note()
        fields = list(getattr(note, "fields", []) or [])
        if fields:
            return _collapse_ws(fields[0])
    except Exception:
        return ""
    return ""


def _source_metadata_for_extension_card(
    *,
    source_type: str,
    source_title: str,
    source_link: str,
    parent_card_id: int | None = None,
) -> dict[str, str]:
    return build_incremento_metadata(
        source_type=source_type,
        source_title=source_title,
        source_link=source_link,
        parent=_parent_card_title_on_main(parent_card_id),
        parent_card_id=parent_card_id,
    )


def _sync_parent_child_knowledge_tree_on_main(
    *,
    parent_card_id: int | None,
    child_card_id: int,
    node_kind: str = "item",
) -> dict:
    if parent_card_id is None:
        return {}
    try:
        parent_card_id = int(parent_card_id)
        child_card_id = int(child_card_id)
    except Exception:
        return {}
    if parent_card_id <= 0 or child_card_id <= 0 or parent_card_id == child_card_id:
        return {}

    try:
        from .knowledge_tree import ensure_extract_lineage_cards_in_tree
        from .paths import get_active_profile as _active_profile
    except ImportError:
        from knowledge_tree import ensure_extract_lineage_cards_in_tree  # type: ignore
        from paths import get_active_profile as _active_profile  # type: ignore

    return ensure_extract_lineage_cards_in_tree(
        _addon_dir,
        _active_profile(),
        source_card_id=parent_card_id,
        created_card_ids=[child_card_id],
        created_node_kind=node_kind,
    )


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
    ensure_incremento_metadata_fields(mw.col.models, model, save=True)

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
        field_html[field_name] = _append_browser_capture_html(
            field_html.get(field_name, ""),
            _plain_text_to_html(normalized["url"]),
        )

    if mappings["snapshot_field"]:
        field_name = mappings["snapshot_field"]
        snapshot_html = ""
        for idx, snapshot in enumerate(normalized["snapshots"], start=1):
            media_filename = _store_browser_capture_snapshot(mw.col, snapshot, normalized["title"], idx)
            snapshot_html = _append_browser_capture_html(snapshot_html, f'<img src="{escape(media_filename, quote=True)}">')
        field_html[field_name] = _append_browser_capture_html(field_html.get(field_name, ""), snapshot_html)

    if not any(value for value in field_html.values()):
        raise ValueError(
            "Nothing to insert. Choose at least one title, selected text, or snapshot destination field."
        )

    for field_name, value in field_html.items():
        note[field_name] = value

    parent_card_id = normalized.get("parent_card_id")
    apply_incremento_metadata(
        note,
        _source_metadata_for_extension_card(
            source_type="Browser Capture",
            source_title=normalized["title"],
            source_link=normalized["url"],
            parent_card_id=parent_card_id,
        ),
    )

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
    knowledge_tree_result = _sync_parent_child_knowledge_tree_on_main(
        parent_card_id=parent_card_id,
        child_card_id=int(card_id),
        node_kind="item",
    )
    return {
        "ok": True,
        "type": "browser_capture",
        "cardId": int(card_id),
        "noteId": int(note.id),
        "noteTypeName": note_type_name,
        "deckName": deck_name,
        "title": normalized["title"],
        "knowledgeTree": knowledge_tree_result,
    }


def _add_content_item_on_main(normalized: dict) -> dict:
    from aqt import mw

    from .pdf_manager import add_pdf_card
    from .priority_manager import set_priority
    from .paths import get_active_profile as _active_profile
    from .video_manager import add_video_card, is_supported_video_url, resolve_video_url_for_embed
    from .web_manager import add_web_card, set_web_media_progress
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
    media_url = normalized.get("media_url", "")
    media_title = normalized.get("media_title", "")
    media_seconds = float(normalized.get("media_seconds") or 0.0)
    parent_card_id = normalized.get("parent_card_id")

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
            metadata=_source_metadata_for_extension_card(
                source_type="Video",
                source_title=title,
                source_link=video_url,
                parent_card_id=parent_card_id,
            ),
        )
    elif kind == "webpage":
        card_id = add_web_card(
            mw.col,
            url=url,
            title=title,
            deck_name=deck_name,
            tags=tags,
            metadata=_source_metadata_for_extension_card(
                source_type="Web",
                source_title=title,
                source_link=url,
                parent_card_id=parent_card_id,
            ),
        )
        if media_seconds > 0:
            set_web_media_progress(
                _addon_dir,
                _active_profile(),
                int(card_id),
                url=url,
                media_url=media_url,
                media_title=media_title,
                media_seconds=media_seconds,
            )
    elif kind == "writing":
        initial_markdown = str(markdown or "").strip()
        if initial_markdown and not normalized.get(_PREPARED_WRITING_MARKDOWN_KEY):
            initial_markdown = external_plain_text_to_markdown(
                initial_markdown,
                max_chars=_MAX_MARKDOWN_CHARS,
            )
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
            metadata=_source_metadata_for_extension_card(
                source_type="Web",
                source_title=title,
                source_link=url,
                parent_card_id=parent_card_id,
            ),
        )
    else:
        prepared_pdf_path = str(normalized.get(_PREPARED_PDF_PATH_KEY) or "")
        temp_pdf_path = prepared_pdf_path or _make_temp_pdf_path()
        cleanup_temp_pdf = not bool(prepared_pdf_path)
        try:
            if prepared_pdf_path:
                if not os.path.exists(prepared_pdf_path):
                    raise RuntimeError("Prepared PDF file was not found.")
            elif pdf_base64:
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
                metadata=_source_metadata_for_extension_card(
                    source_type="PDF",
                    source_title=title,
                    source_link=url,
                    parent_card_id=parent_card_id,
                ),
                precomputed_page_texts=normalized.get(_PREPARED_PDF_PAGE_TEXTS_KEY),
            )
        finally:
            if cleanup_temp_pdf:
                try:
                    os.remove(temp_pdf_path)
                except OSError:
                    pass

    set_priority(_addon_dir, _active_profile(), int(card_id), priority)
    knowledge_tree_result = _sync_parent_child_knowledge_tree_on_main(
        parent_card_id=parent_card_id,
        child_card_id=int(card_id),
        node_kind="item",
    )

    return {
        "ok": True,
        "kind": kind,
        "cardId": int(card_id),
        "title": title,
        "deckName": deck_name,
        "knowledgeTree": knowledge_tree_result,
    }


def _add_content_request_on_main(request: dict) -> dict:
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


def _add_content_on_main(payload: dict) -> dict:
    request = (
        payload
        if _looks_like_normalized_add_content_request(payload)
        else normalize_add_content_request(payload)
    )
    return _add_content_request_on_main(request)


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
    try:
        from .. import _sync_reviewer_priority_badge

        _sync_reviewer_priority_badge()
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


def _save_browser_media_ref_on_main(payload: dict) -> dict:
    from aqt import mw

    try:
        from .db import set_card_browser_media_ref
        from .paths import get_active_profile as _active_profile
        from .web_manager import WEB_NOTE_TYPE, set_web_media_progress
    except ImportError:
        from db import set_card_browser_media_ref  # type: ignore
        from paths import get_active_profile as _active_profile  # type: ignore
        from web_manager import WEB_NOTE_TYPE, set_web_media_progress  # type: ignore

    normalized = normalize_browser_media_ref_payload(payload)
    card_id = int(normalized["card_id"])

    try:
        card = mw.col.get_card(card_id)
    except Exception as exc:
        raise ValueError(f"Could not load card {card_id}.") from exc
    if card is None:
        raise ValueError(f"Card {card_id} was not found.")

    is_web_card = False
    try:
        note = mw.col.get_note(card.nid)
        model = mw.col.models.get(note.mid)
        is_web_card = bool(model is not None and model.get("name") == WEB_NOTE_TYPE)
    except Exception:
        is_web_card = False

    updated_at = int(time.time())
    if is_web_card:
        set_web_media_progress(
            _addon_dir,
            _active_profile(),
            card_id,
            url=normalized["page_url"],
            media_url=normalized["media_url"],
            media_title=normalized["media_title"],
            media_seconds=normalized["seconds"],
            media_updated_at=updated_at,
        )
        try:
            from ..frontend.web_dock import sync_external_web_media_state

            sync_external_web_media_state(
                card_id,
                normalized["page_url"],
                normalized["media_url"],
                normalized["media_title"],
                normalized["seconds"],
            )
        except Exception:
            pass
    else:
        set_card_browser_media_ref(
            _addon_dir,
            _active_profile(),
            card_id,
            page_url=normalized["page_url"],
            media_url=normalized["media_url"],
            media_title=normalized["media_title"],
            media_seconds=normalized["seconds"],
            updated_at=updated_at,
        )

    try:
        from .. import _sync_reviewer_priority_badge

        _sync_reviewer_priority_badge()
    except Exception:
        pass

    try:
        from .video_manager import fmt_time
    except ImportError:
        from video_manager import fmt_time  # type: ignore
        time_text = fmt_time(float(normalized["seconds"]))
    except Exception:
        time_text = str(normalized["seconds"])
    else:
        time_text = fmt_time(float(normalized["seconds"]))

    return {
        "ok": True,
        "cardId": card_id,
        "pageUrl": normalized["page_url"],
        "mediaUrl": normalized["media_url"],
        "mediaTitle": normalized["media_title"],
        "seconds": normalized["seconds"],
        "timeText": time_text,
        "updatedAt": updated_at,
        "hasReference": True,
    }


def _load_browser_media_ref_on_main(card_id: int) -> dict:
    try:
        from .db import get_card_browser_media_ref
        from .paths import get_active_profile as _active_profile
        from .web_manager import WEB_NOTE_TYPE, get_web_progress
    except ImportError:
        from db import get_card_browser_media_ref  # type: ignore
        from paths import get_active_profile as _active_profile  # type: ignore
        from web_manager import WEB_NOTE_TYPE, get_web_progress  # type: ignore

    is_web_card = False
    try:
        from aqt import mw

        card = mw.col.get_card(int(card_id))
        note = mw.col.get_note(card.nid)
        model = mw.col.models.get(note.mid)
        is_web_card = bool(model is not None and model.get("name") == WEB_NOTE_TYPE)
    except Exception:
        is_web_card = False

    if is_web_card:
        progress = get_web_progress(_addon_dir, _active_profile(), int(card_id))
        ref = {
            "page_url": progress.get("url", ""),
            "media_url": progress.get("media_url", ""),
            "media_title": progress.get("media_title", ""),
            "media_seconds": progress.get("media_seconds", 0.0),
            "updated_at": progress.get("media_updated_at", 0),
        }
    else:
        ref = get_card_browser_media_ref(_addon_dir, _active_profile(), int(card_id))
    seconds = float(ref.get("media_seconds") or 0.0)
    has_reference = bool(ref.get("updated_at"))
    try:
        from .video_manager import fmt_time
    except ImportError:
        from video_manager import fmt_time  # type: ignore
        time_text = fmt_time(seconds) if has_reference else ""
    except Exception:
        time_text = str(seconds) if has_reference else ""
    else:
        time_text = fmt_time(seconds) if has_reference else ""

    return {
        "ok": True,
        "cardId": int(card_id),
        "pageUrl": str(ref.get("page_url") or ""),
        "mediaUrl": str(ref.get("media_url") or ""),
        "mediaTitle": str(ref.get("media_title") or ""),
        "seconds": seconds,
        "timeText": time_text,
        "updatedAt": int(ref.get("updated_at") or 0),
        "hasReference": has_reference,
    }


class _IncrementoBridgeHandler(BaseHTTPRequestHandler):
    server_version = "IncrementoBrowserBridge/2.0"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(_REQUEST_SOCKET_TIMEOUT_SECONDS)

    def log_message(self, format, *args):
        return

    def _request_origin_allowed(self, *, allow_unbound: bool = False) -> bool:
        origin = str(self.headers.get("Origin") or "")
        if not origin:
            return False
        if not _EXTENSION_ORIGIN_RE.fullmatch(origin):
            return False
        with _bridge_identity_lock:
            if _allowed_extension_origin:
                return hmac.compare_digest(origin, _allowed_extension_origin)
        return bool(allow_unbound)

    def _bind_handshake_origin(self) -> bool:
        global _allowed_extension_origin
        origin = str(self.headers.get("Origin") or "")
        if not origin:
            return False
        if not _EXTENSION_ORIGIN_RE.fullmatch(origin):
            return False
        with _bridge_identity_lock:
            if not _allowed_extension_origin:
                _allowed_extension_origin = origin
            return hmac.compare_digest(origin, _allowed_extension_origin)

    def _request_authenticated(self) -> bool:
        token = str(self.headers.get("X-Incremento-Token") or "")
        protocol = str(self.headers.get("X-Incremento-Protocol") or "")
        with _bridge_identity_lock:
            expected = _bridge_token
        return (
            bool(expected)
            and protocol == str(BRIDGE_PROTOCOL_VERSION)
            and hmac.compare_digest(token, expected)
        )

    def _send_cors_headers(self) -> None:
        origin = str(self.headers.get("Origin") or "")
        if _EXTENSION_ORIGIN_RE.fullmatch(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, X-Incremento-Token, X-Incremento-Protocol",
        )

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            self.close_connection = True

    def do_OPTIONS(self) -> None:
        request_path = urlsplit(self.path).path
        if request_path not in {
            BRIDGE_PATH,
            BRIDGE_HANDSHAKE_PATH,
            BROWSER_CAPTURE_META_PATH,
            WEB_TRACK_PATH,
            WEB_TRACK_MEDIA_PATH,
            BROWSER_MEDIA_REF_PATH,
        }:
            self.send_error(404)
            return
        if not self._request_origin_allowed(allow_unbound=True):
            self.send_error(403)
            return
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        if not _request_slots.acquire(blocking=False):
            self._send_json(503, {"ok": False, "error": "Bridge is busy."})
            return
        try:
            self._do_GET()
        finally:
            _request_slots.release()

    def _do_GET(self) -> None:
        parsed = urlsplit(self.path)
        request_path = parsed.path
        if request_path == BRIDGE_HANDSHAKE_PATH:
            if not self._request_origin_allowed(allow_unbound=True) or not self._bind_handshake_origin():
                self._send_json(403, {"ok": False, "error": "Origin not allowed."})
                return
            with _bridge_identity_lock:
                token = _bridge_token
            self._send_json(
                200,
                {
                    "ok": True,
                    "protocol": BRIDGE_PROTOCOL_VERSION,
                    "token": token,
                },
            )
            return
        if request_path not in {BROWSER_CAPTURE_META_PATH, BROWSER_MEDIA_REF_PATH}:
            self._send_json(404, {"ok": False, "error": "Unknown path."})
            return
        if not self._request_origin_allowed():
            if self._request_origin_allowed(allow_unbound=True):
                self._send_json(401, {"ok": False, "error": "Bridge authorization required."})
            else:
                self._send_json(403, {"ok": False, "error": "Origin not allowed."})
            return
        if not self._request_authenticated():
            self._send_json(401, {"ok": False, "error": "Bridge authorization required."})
            return

        try:
            if request_path == BROWSER_CAPTURE_META_PATH:
                result = _run_on_main_and_wait(_browser_capture_meta_on_main)
            else:
                query = normalize_browser_media_ref_query(parse_qs(parsed.query, keep_blank_values=True))
                result = _run_on_main_and_wait(
                    lambda: _load_browser_media_ref_on_main(int(query["card_id"]))
                )
        except ValueError as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
            return
        except Exception:
            self._send_json(500, {"ok": False, "error": "Bridge operation failed."})
            return

        self._send_json(200, result)

    def do_POST(self) -> None:
        if not _request_slots.acquire(blocking=False):
            self._send_json(503, {"ok": False, "error": "Bridge is busy."})
            return
        try:
            self._do_POST()
        finally:
            _request_slots.release()

    def _do_POST(self) -> None:
        request_path = urlsplit(self.path).path
        if request_path not in {BRIDGE_PATH, WEB_TRACK_PATH, WEB_TRACK_MEDIA_PATH, BROWSER_MEDIA_REF_PATH}:
            self._send_json(404, {"ok": False, "error": "Unknown path."})
            return
        if not self._request_origin_allowed():
            if self._request_origin_allowed(allow_unbound=True):
                self._send_json(401, {"ok": False, "error": "Bridge authorization required."})
            else:
                self._send_json(403, {"ok": False, "error": "Origin not allowed."})
            return
        if not self._request_authenticated():
            self._send_json(401, {"ok": False, "error": "Bridge authorization required."})
            return

        if str(self.headers.get("Transfer-Encoding") or "").strip():
            self.close_connection = True
            self._send_json(400, {"ok": False, "error": "Transfer-Encoding is not supported."})
            return

        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            self._send_json(400, {"ok": False, "error": "Invalid Content-Length."})
            return
        if length < 0 or length > _MAX_REQUEST_BYTES:
            self.close_connection = True
            self._send_json(413, {"ok": False, "error": "Request is too large."})
            return
        try:
            raw = self.rfile.read(length)
        except (OSError, TimeoutError):
            self.close_connection = True
            self._send_json(408, {"ok": False, "error": "Request body timed out."})
            return
        if len(raw) != length:
            self.close_connection = True
            self._send_json(400, {"ok": False, "error": "Incomplete request body."})
            return

        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            self._send_json(400, {"ok": False, "error": "Invalid JSON."})
            return

        try:
            if request_path == BRIDGE_PATH:
                prepared_request = prepare_add_content_request_off_main(payload)
                try:
                    result = _run_on_main_and_wait(
                        lambda: _add_content_request_on_main(prepared_request)
                    )
                finally:
                    cleanup_prepared_add_content_request(prepared_request)
            elif request_path == WEB_TRACK_MEDIA_PATH:
                result = _run_on_main_and_wait(lambda: _update_web_card_media_on_main(payload))
            elif request_path == WEB_TRACK_PATH:
                result = _run_on_main_and_wait(lambda: _update_web_card_on_main(payload))
            else:
                result = _run_on_main_and_wait(lambda: _save_browser_media_ref_on_main(payload))
        except ValueError as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
            return
        except Exception:
            self._send_json(500, {"ok": False, "error": "Bridge operation failed."})
            return

        self._send_json(200, result)


def start_browser_bridge(addon_dir: str) -> None:
    global _server, _server_thread, _addon_dir, _bridge_token, _allowed_extension_origin

    with _server_lock:
        _addon_dir = addon_dir
        if _server is not None and _server_thread is not None and _server_thread.is_alive():
            return
        with _bridge_identity_lock:
            _bridge_token = secrets.token_urlsafe(32)
            _allowed_extension_origin = ""
        try:
            server = _BoundedThreadingHTTPServer(
                (BRIDGE_HOST, BRIDGE_PORT),
                _IncrementoBridgeHandler,
            )
        except OSError as exc:
            with _bridge_identity_lock:
                _bridge_token = ""
                _allowed_extension_origin = ""
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
    global _server, _server_thread, _bridge_token, _allowed_extension_origin

    with _server_lock:
        server = _server
        thread = _server_thread
        _server = None
        _server_thread = None

    with _bridge_identity_lock:
        _bridge_token = ""
        _allowed_extension_origin = ""

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
