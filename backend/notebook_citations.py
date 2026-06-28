from __future__ import annotations

import hashlib
import html
import os
import re
import unicodedata
from html.parser import HTMLParser

try:
    from .pdf_highlights import add_highlight, load_highlights
    from .pdf_manager import pdf_storage_abspath
except ImportError:
    from pdf_highlights import add_highlight, load_highlights  # type: ignore
    from pdf_manager import pdf_storage_abspath  # type: ignore


_SUPPORTED_HIGHLIGHT_COLORS = {
    "yellow",
    "pink",
    "green",
    "blue",
    "aqua",
    "orange",
    "red",
    "purple",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")
_PAGE_RE = re.compile(r"\bPage\s+(\d+)\b", re.IGNORECASE)
_LOCATION_RE = re.compile(r"\bLocation\s+(\d+)\b", re.IGNORECASE)


class _NotebookHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.tokens: list[tuple[str, str]] = []
        self._capture_kind: str | None = None
        self._depth = 0
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name: value or "" for name, value in attrs}
        classes = set((attr_map.get("class") or "").split())
        capture_kind = None
        if "sectionHeading" in classes:
            capture_kind = "section"
        elif "noteHeading" in classes:
            capture_kind = "heading"
        elif "noteText" in classes:
            capture_kind = "text"
        if capture_kind and self._capture_kind is None:
            self._capture_kind = capture_kind
            self._depth = 1
            self._buffer = []
            return
        if self._capture_kind is not None:
            if tag in {"br", "hr"}:
                self._buffer.append("\n")
                return
            self._depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, _tag: str) -> None:
        if self._capture_kind is None:
            return
        self._depth -= 1
        if self._depth > 0:
            return
        text = _clean_html_text("".join(self._buffer))
        if text:
            self.tokens.append((self._capture_kind, text))
        self._capture_kind = None
        self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._capture_kind is not None:
            self._buffer.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._capture_kind is not None:
            self._buffer.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._capture_kind is not None:
            self._buffer.append(f"&#{name};")


def _clean_html_text(text: str) -> str:
    cleaned = html.unescape(str(text or ""))
    cleaned = cleaned.replace("\xa0", " ")
    cleaned = _WHITESPACE_RE.sub(" ", cleaned)
    return cleaned.strip()


def _normalize_match_text(text: str) -> str:
    cleaned = unicodedata.normalize("NFKC", str(text or ""))
    cleaned = cleaned.replace("\u2018", "'").replace("\u2019", "'")
    cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"')
    cleaned = cleaned.replace("\u2013", "-").replace("\u2014", "-")
    cleaned = cleaned.casefold()
    return cleaned


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(_normalize_match_text(text))


def _normalize_color(color: str | None) -> str:
    raw = _clean_html_text(color or "").casefold()
    return raw if raw in _SUPPORTED_HIGHLIGHT_COLORS else "yellow"


def _parse_heading(raw_heading: str) -> dict[str, object]:
    heading = _clean_html_text(raw_heading)
    lower = heading.casefold()
    kind = "highlight" if lower.startswith("highlight") else "note"

    color = ""
    color_match = re.search(r"highlight\s*\(([^)]+)\)", heading, re.IGNORECASE)
    if color_match:
        color = _clean_html_text(color_match.group(1))

    page_match = _PAGE_RE.search(heading)
    location_match = _LOCATION_RE.search(heading)
    return {
        "kind": kind,
        "color": color.casefold(),
        "page": int(page_match.group(1)) if page_match else None,
        "location": int(location_match.group(1)) if location_match else None,
    }


def parse_notebook_html(html_text: str) -> list[dict[str, object]]:
    parser = _NotebookHtmlParser()
    parser.feed(str(html_text or ""))
    parser.close()

    current_section = ""
    pending_heading: dict[str, object] | None = None
    entries: list[dict[str, object]] = []
    ordinal = 0

    for token_kind, token_text in parser.tokens:
        if token_kind == "section":
            current_section = token_text
            continue
        if token_kind == "heading":
            pending_heading = _parse_heading(token_text)
            continue
        if token_kind != "text" or pending_heading is None:
            continue
        ordinal += 1
        entries.append(
            {
                "section": current_section,
                "kind": pending_heading["kind"],
                "color": pending_heading["color"],
                "page": pending_heading["page"],
                "location": pending_heading["location"],
                "text": _clean_html_text(token_text),
                "ordinal": ordinal,
            }
        )
        pending_heading = None
    return entries


def parse_notebook_file(path: str) -> list[dict[str, object]]:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return parse_notebook_html(handle.read())


def summarize_notebook_entries(entries: list[dict[str, object]]) -> dict[str, object]:
    colors: dict[str, int] = {}
    counts = {
        "highlights": 0,
        "notes": 0,
        "page_entries": 0,
        "location_only_entries": 0,
        "colors": colors,
    }
    for entry in entries:
        kind = str(entry.get("kind") or "")
        if kind == "highlight":
            counts["highlights"] += 1
            color = _normalize_color(str(entry.get("color") or ""))
            colors[color] = colors.get(color, 0) + 1
        elif kind == "note":
            counts["notes"] += 1
        if entry.get("page") is not None:
            counts["page_entries"] += 1
        elif entry.get("location") is not None:
            counts["location_only_entries"] += 1
    return counts


def _entry_debug_summary(entry: dict[str, object]) -> dict[str, object]:
    return {
        "ordinal": int(entry.get("ordinal") or 0),
        "section": str(entry.get("section") or ""),
        "page": int(entry.get("page") or 0) or None,
        "location": int(entry.get("location") or 0) or None,
        "text": str(entry.get("text") or ""),
    }


def _page_candidates(parsed_page: int | None, page_count: int) -> list[int]:
    if page_count <= 0:
        return []
    if parsed_page is None or parsed_page <= 0 or parsed_page > page_count:
        return list(range(page_count))
    exact = parsed_page - 1
    ordered = [exact]
    for delta in (1, 2):
        for candidate in (exact - delta, exact + delta):
            if 0 <= candidate < page_count and candidate not in ordered:
                ordered.append(candidate)
    for page_index in range(page_count):
        if page_index not in ordered:
            ordered.append(page_index)
    return ordered


def _build_page_word_data(page, page_index: int) -> dict[str, object]:
    raw_words = list(page.get_text("words", sort=True) or [])
    token_entries: list[dict[str, object]] = []
    for word_index, word in enumerate(raw_words):
        word_text = str(word[4] or "")
        for token in _tokenize(word_text):
            token_entries.append(
                {
                    "token": token,
                    "word_index": word_index,
                    "page_index": page_index,
                }
            )
    return {"raw_words": raw_words, "token_entries": token_entries}


def _find_token_matches(token_entries: list[dict[str, object]], text: str) -> list[dict[str, object]]:
    tokens = _tokenize(text)
    if not tokens:
        return []
    haystack = [str(entry.get("token") or "") for entry in token_entries]
    results: list[dict[str, object]] = []
    limit = len(haystack) - len(tokens) + 1
    for start in range(max(0, limit)):
        if haystack[start : start + len(tokens)] != tokens:
            continue
        matched_entries = token_entries[start : start + len(tokens)]
        word_refs: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        for entry in matched_entries:
            page_index = int(entry.get("page_index") or 0)
            word_index = int(entry.get("word_index") or 0)
            ref = (page_index, word_index)
            if ref in seen:
                continue
            seen.add(ref)
            word_refs.append(ref)
        results.append(
            {
                "token_start": start,
                "token_end": start + len(tokens),
                "word_refs": word_refs,
            }
        )
    return results


def _find_page_matches(page_data: dict[str, object], text: str) -> list[dict[str, object]]:
    token_entries = list(page_data.get("token_entries") or [])
    return _find_token_matches(token_entries, text)


def _find_cross_page_matches(
    start_page_data: dict[str, object],
    next_page_data: dict[str, object],
    text: str,
) -> list[dict[str, object]]:
    combined = list(start_page_data.get("token_entries") or []) + list(next_page_data.get("token_entries") or [])
    start_page_index = int((combined[0].get("page_index") if combined else 0) or 0)
    results = []
    for match in _find_token_matches(combined, text):
        pages = {page_index for page_index, _word_index in list(match.get("word_refs") or [])}
        if len(pages) < 2 or start_page_index not in pages:
            continue
        results.append(match)
    return results


def _rects_for_match(raw_words: list[tuple], word_indexes: list[int]) -> list[dict[str, float]]:
    rects: list[dict[str, float]] = []
    current = None
    current_key = None
    for word_index in word_indexes:
        x0, y0, x1, y1, _text, block_no, line_no, _word_no = raw_words[word_index]
        key = (block_no, line_no)
        if current is None or key != current_key:
            current = {
                "x": round(float(x0), 3),
                "y": round(float(y0), 3),
                "w": round(float(x1 - x0), 3),
                "h": round(float(y1 - y0), 3),
            }
            rects.append(current)
            current_key = key
            continue
        current["w"] = round(float(x1) - float(current["x"]), 3)
        current["h"] = round(max(float(current["h"]), float(y1) - float(current["y"])), 3)
    return rects


def _notebook_hash(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha1(handle.read()).hexdigest()


def _highlight_signature(entry: dict[str, object]) -> str:
    page = int(entry.get("page") or 0)
    location = int(entry.get("location") or 0)
    text = " ".join(_tokenize(str(entry.get("text") or "")))
    section = _normalize_match_text(str(entry.get("section") or ""))
    return f"{section}|{page}|{location}|{text}"


def _highlight_id(signature: str, occurrence: int, card_id: int, match_index: int) -> str:
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:16]
    return f"notebook-{digest}-{int(occurrence)}-{int(card_id)}-{int(match_index)}"


def _merge_note(existing: str, incoming: str) -> str:
    current = str(existing or "").strip()
    extra = str(incoming or "").strip()
    if not extra:
        return current
    if not current:
        return extra
    if current == extra or extra in current.split("\n\n"):
        return current
    return f"{current}\n\n{extra}"


def import_notebook_citations(
    addon_dir: str,
    profile: str,
    notebook_path: str,
    selected_cards: list[dict[str, object]],
    *,
    entries: list[dict[str, object]] | None = None,
    fitz_module=None,
) -> dict[str, object]:
    try:
        fitz = fitz_module if fitz_module is not None else __import__("fitz")
    except Exception as exc:
        raise RuntimeError("PyMuPDF is required to import notebook citations.") from exc

    parsed_entries = list(entries) if entries is not None else parse_notebook_file(notebook_path)
    notebook_hash = _notebook_hash(notebook_path)
    highlight_entries = [entry for entry in parsed_entries if entry.get("kind") == "highlight"]
    note_entries = [entry for entry in parsed_entries if entry.get("kind") == "note"]
    seen_signatures: dict[str, int] = {}
    highlight_identity_by_ordinal: dict[int, tuple[str, int]] = {}
    for entry in highlight_entries:
        signature = _highlight_signature(entry)
        occurrence = seen_signatures.get(signature, 0)
        seen_signatures[signature] = occurrence + 1
        highlight_identity_by_ordinal[int(entry.get("ordinal") or 0)] = (signature, occurrence)

    report = {
        "notebook_path": notebook_path,
        "notebook_hash": notebook_hash,
        "entry_counts": summarize_notebook_entries(parsed_entries),
        "pdfs": [],
    }

    for selected in list(selected_cards or []):
        try:
            card_id = int(selected.get("card_id") or 0)
        except Exception:
            card_id = 0
        if card_id <= 0:
            continue
        stored_filename = str(selected.get("stored_filename") or "").strip()
        pdf_path = pdf_storage_abspath(stored_filename)
        pdf_report = {
            "card_id": card_id,
            "title": str(selected.get("title") or f"Card {card_id}"),
            "stored_filename": stored_filename,
            "created": 0,
            "updated": 0,
            "notes_attached": 0,
            "unmatched_highlights": 0,
            "unattached_notes": 0,
            "unmatched_highlight_entries": [],
            "unattached_note_entries": [],
            "read_error": "",
            "no_searchable_text": False,
        }
        report["pdfs"].append(pdf_report)

        if not pdf_path or not os.path.exists(pdf_path):
            pdf_report["read_error"] = "Stored PDF file is missing."
            pdf_report["unmatched_highlights"] = len(highlight_entries)
            pdf_report["unattached_notes"] = len(note_entries)
            pdf_report["unmatched_highlight_entries"] = [
                _entry_debug_summary(entry) for entry in highlight_entries
            ]
            pdf_report["unattached_note_entries"] = [
                _entry_debug_summary(entry) for entry in note_entries
            ]
            continue

        try:
            doc = fitz.open(pdf_path)
        except Exception as exc:
            pdf_report["read_error"] = str(exc)
            pdf_report["unmatched_highlights"] = len(highlight_entries)
            pdf_report["unattached_notes"] = len(note_entries)
            pdf_report["unmatched_highlight_entries"] = [
                _entry_debug_summary(entry) for entry in highlight_entries
            ]
            pdf_report["unattached_note_entries"] = [
                _entry_debug_summary(entry) for entry in note_entries
            ]
            continue

        try:
            existing_rows = load_highlights(addon_dir, profile, card_id)
            existing_by_id = {
                str(row.get("id") or ""): dict(row)
                for row in existing_rows
            }
            page_cache: dict[int, dict[str, object]] = {}
            imported_targets: list[dict[str, object]] = []
            any_searchable_text = False

            def _page_data(page_index: int) -> dict[str, object]:
                nonlocal any_searchable_text
                cached = page_cache.get(page_index)
                if cached is not None:
                    return cached
                data = _build_page_word_data(doc.load_page(page_index), page_index)
                if data["token_entries"]:
                    any_searchable_text = True
                page_cache[page_index] = data
                return data

            for entry in highlight_entries:
                parsed_page = entry.get("page")
                candidates = _page_candidates(
                    int(parsed_page) if parsed_page is not None else None,
                    len(doc),
                )
                matched = None
                for page_index in candidates:
                    page_matches = _find_page_matches(_page_data(page_index), str(entry.get("text") or ""))
                    if not page_matches:
                        if page_index + 1 < len(doc):
                            cross_matches = _find_cross_page_matches(
                                _page_data(page_index),
                                _page_data(page_index + 1),
                                str(entry.get("text") or ""),
                            )
                            if cross_matches:
                                matched = (page_index, cross_matches[0], cross_matches, True)
                                break
                        continue
                    matched = (page_index, page_matches[0], page_matches, False)
                    break
                if matched is None:
                    pdf_report["unmatched_highlights"] += 1
                    pdf_report["unmatched_highlight_entries"].append(_entry_debug_summary(entry))
                    continue
                page_index, chosen_match, page_matches, _cross_page = matched
                page_data = _page_data(page_index)
                raw_words = list(page_data.get("raw_words") or [])
                word_indexes = [
                    word_index
                    for ref_page_index, word_index in list(chosen_match.get("word_refs") or [])
                    if int(ref_page_index) == page_index
                ]
                rects = _rects_for_match(raw_words, word_indexes)
                signature, occurrence = highlight_identity_by_ordinal.get(
                    int(entry.get("ordinal") or 0),
                    (_highlight_signature(entry), 0),
                )
                highlight_id = _highlight_id(
                    signature,
                    occurrence,
                    card_id,
                    page_matches.index(chosen_match),
                )
                highlight = {
                    "id": highlight_id,
                    "page": page_index + 1,
                    "color": _normalize_color(str(entry.get("color") or "")),
                    "text": str(entry.get("text") or ""),
                    "note": str(existing_by_id.get(highlight_id, {}).get("note") or ""),
                    "rects": rects,
                }
                add_highlight(addon_dir, profile, card_id, highlight)
                if highlight_id in existing_by_id:
                    pdf_report["updated"] += 1
                else:
                    pdf_report["created"] += 1
                existing_by_id[highlight_id] = highlight
                imported_targets.append(
                    {
                        "highlight_id": highlight_id,
                        "source_page": entry.get("page"),
                        "ordinal": int(entry.get("ordinal") or 0),
                    }
                )

            for entry in note_entries:
                parsed_page = entry.get("page")
                if parsed_page is None:
                    pdf_report["unattached_notes"] += 1
                    pdf_report["unattached_note_entries"].append(_entry_debug_summary(entry))
                    continue
                same_page = [
                    target
                    for target in imported_targets
                    if target.get("source_page") == parsed_page
                ]
                if not same_page:
                    pdf_report["unattached_notes"] += 1
                    pdf_report["unattached_note_entries"].append(_entry_debug_summary(entry))
                    continue
                same_page.sort(
                    key=lambda target: (
                        abs(int(target.get("ordinal") or 0) - int(entry.get("ordinal") or 0)),
                        int(target.get("ordinal") or 0),
                    )
                )
                target = same_page[0]
                highlight_id = str(target.get("highlight_id") or "")
                highlight = dict(existing_by_id.get(highlight_id) or {})
                if not highlight:
                    pdf_report["unattached_notes"] += 1
                    pdf_report["unattached_note_entries"].append(_entry_debug_summary(entry))
                    continue
                merged_note = _merge_note(str(highlight.get("note") or ""), str(entry.get("text") or ""))
                if merged_note == str(highlight.get("note") or ""):
                    pdf_report["notes_attached"] += 1
                    continue
                highlight["note"] = merged_note
                add_highlight(addon_dir, profile, card_id, highlight)
                existing_by_id[highlight_id] = highlight
                pdf_report["notes_attached"] += 1

            if not any_searchable_text:
                pdf_report["no_searchable_text"] = True
        finally:
            try:
                doc.close()
            except Exception:
                pass

    return report
