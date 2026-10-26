"""Pure Search ALL presentation/read pipeline; safe to execute on a QueryOp worker."""
from __future__ import annotations

from concurrent.futures import CancelledError
from dataclasses import dataclass, replace
from html import escape
import re
import sqlite3
from time import monotonic
from urllib.parse import quote

try:
    from ..backend.i18n import t
    from ..backend.db import (
    CompiledSearch,get_connection, search_note_ocr_index, search_epub_text_index,
                             search_pdf_text_index, search_text_match_score, split_search_terms)
    from ..backend.search_repository import SearchCollection, search_excerpt_rows
    from ..backend.pdf_search import reconcile_pdf_search_indexes
except ImportError:
    from backend.i18n import t
    from db import (
    CompiledSearch,get_connection, search_note_ocr_index, search_epub_text_index,
                    search_pdf_text_index, search_text_match_score, split_search_terms)
    from search_repository import SearchCollection, search_excerpt_rows
    from pdf_search import reconcile_pdf_search_indexes

_MIN_SEARCH_CHARS = 3
_MAX_CATEGORY_RESULTS = 120
_LIVE_RESULT_OVERSAMPLE_FACTOR = 10
_MAX_CARD_SEARCH_CANDIDATES = 1000


@dataclass(frozen=True)
class SearchResults:
    html: str
    highlight_previews: dict[str, str]
    pdf_needs_index: bool = False
    pdf_reindex_documents: tuple = ()


def _document_result_url(
    media: str,
    card_id: int,
    position: int,
    query: str,
    *,
    highlight_key: str = "",
) -> str:
    normalized_media = str(media or "").strip().lower()
    if normalized_media not in {"pdf", "epub"}:
        raise ValueError("Unsupported document preview type.")
    suffix = f"&highlight={quote(str(highlight_key))}" if highlight_key else ""
    return (
        f"inc://{normalized_media}/{int(card_id)}/{int(position)}"
        f"?q={quote(str(query or ''))}{suffix}"
    )


def _highlight_result_url(
    previews: dict[str, str],
    *,
    media: str,
    card_id: int,
    position: int,
    query: str,
    text: str,
) -> str:
    preview_index = len(previews)
    preview_key = f"h{preview_index}"
    while preview_key in previews:
        preview_index += 1
        preview_key = f"h{preview_index}"
    previews[preview_key] = str(text or "")
    return _document_result_url(
        media,
        card_id,
        position,
        query,
        highlight_key=preview_key,
    )


class SearchResultsBuilder:
    def __init__(self, addon_dir, profile, col, query_filters, *, cancel=None, progress=None):
        self._addon_dir, self._profile = addon_dir, profile
        self._filters = frozenset(query_filters)
        self._metadata = SearchCollection(col, cancel=cancel)
        self._progress = progress
        self._last_progress = 0.0
        self._last_total = 0
        self._highlight_previews: dict[str, str] = {}
        self._pdf_needs_index = False

    def _publish(self, parts, total):
        self._metadata.check_cancelled()
        now = monotonic()
        if (self._progress is not None and total > self._last_total
                and (self._last_total == 0 or now - self._last_progress >= 0.1)):
            self._last_progress, self._last_total = now, total
            # Each callback owns its map: later categories cannot change hover targets.
            self._progress(SearchResults("".join(parts) + "</div>", dict(self._highlight_previews)))

    def _filter_current_profile_rows(self, rows, *, note_id_index=None, limit=None, pdf=False):
        self._metadata.check_cancelled()
        if pdf:
            self._metadata.load_document_titles(row[0] for row in rows)
            rows = [row for row in rows if self._metadata.pdf_card_available(
                int(row[0]), self._addon_dir, self._profile)]
        if "current_profile" not in self._filters:
            output = rows[:limit] if limit is not None else rows
        else:
            self._metadata.load_cards(row[0] for row in rows)
            if note_id_index is not None:
                self._metadata.load_notes(row[note_id_index] for row in rows)
            output = []
            for row in rows:
                if self._metadata.cards.get(int(row[0])) is None:
                    continue
                if note_id_index is not None and self._metadata.notes.get(int(row[note_id_index])) is None:
                    continue
                output.append(row)
                if limit is not None and len(output) >= limit:
                    break
        self._metadata.load_document_titles(row[0] for row in output)
        return output

    def _search_limit(self, limit, *, pdf=False):
        return limit * _LIVE_RESULT_OVERSAMPLE_FACTOR if pdf or "current_profile" in self._filters else limit

    def _search_excerpt_hits(self, kind, query, *, source_rows=False, limit=_MAX_CATEGORY_RESULTS):
        self._metadata.check_cancelled()
        rows = search_excerpt_rows(self._addon_dir, self._profile, kind, query, limit=self._search_limit(limit, pdf=kind.startswith("pdf_")))
        return self._filter_current_profile_rows(
            rows, note_id_index=3 if source_rows else None, limit=limit, pdf=kind.startswith("pdf_"),
        )

    def _pdf_title(self, card_id):
        title = self._metadata.document_title(card_id)
        return title if title is not None else t("search_all_pdf_card", card_id=card_id)

    def _epub_title(self, card_id):
        title = self._metadata.document_title(card_id)
        return title if title is not None else t("search_all_epub_card", card_id=card_id)

    def _search_pdf_file_hits(self, query, limit=_MAX_CATEGORY_RESULTS):
        self._metadata.check_cancelled()
        rows = search_pdf_text_index(self._addon_dir, self._profile, query, limit=self._search_limit(limit, pdf=True))
        rows = self._filter_current_profile_rows(rows, limit=limit, pdf=True)
        self._pdf_needs_index = not rows
        return [(cid, page, self._snippet(text or "", query, max_len=180)) for cid, page, text in rows]

    def _search_epub_file_hits(self, query, limit=_MAX_CATEGORY_RESULTS):
        self._metadata.check_cancelled()
        rows = search_epub_text_index(self._addon_dir, self._profile, query, limit=self._search_limit(limit))
        rows = self._filter_current_profile_rows(rows, limit=limit)
        return [(cid, section, title, self._snippet(text or title or "", query, max_len=180))
                for cid, section, title, text in rows]

    def _search_ocr_hits(self, query, limit):
        self._metadata.check_cancelled()
        rows = search_note_ocr_index(self._addon_dir, self._profile, query, limit=limit)
        self._metadata.load_cards(row[1] for row in rows)
        if "current_profile" in self._filters:
            rows = [row for row in rows if self._metadata.cards.get(int(row[1])) is not None]
        self._metadata.load_notes(row[0] for row in rows)
        rows = [row for row in rows if (
            self._metadata.notes.get(row[0]) is None
            or self._metadata.notes[row[0]].pdf_filename is None
            or self._metadata.pdf_available(self._metadata.notes[row[0]], self._addon_dir, self._profile)
        )]
        return rows[:_MAX_CATEGORY_RESULTS]

    def _safe_find_notes(self, query):
        self._metadata.check_cancelled()
        try:
            ids = self._metadata.col.find_notes(query)
        except Exception:
            self._metadata.check_cancelled()
            escaped = query.replace('"', r'\"')
            ids = self._metadata.col.find_notes(f'"{escaped}"')
        ids = ids[:_MAX_CARD_SEARCH_CANDIDATES]
        self._metadata.load_notes(ids)
        return ids

    @staticmethod
    def _snippet(text: str, q: str, max_len: int = 120) -> str:
        if not text:
            return ""
        plain = " ".join(text.split())
        if not q:
            return plain[:max_len]
        i = plain.lower().find(q.lower())
        if i < 0:
            for tok in split_search_terms(q):
                match = re.search(rf"(?i)\b{re.escape(tok)}\w*", plain)
                if match is not None:
                    i = match.start()
                    break
        if i < 0:
            return plain[:max_len]
        start = max(0, i - max_len // 3)
        end = min(len(plain), start + max_len)
        s = plain[start:end]
        if start > 0:
            s = "..." + s
        if end < len(plain):
            s = s + "..."
        return s


    def run(self, query: str) -> SearchResults:
        self._metadata.check_cancelled()
        q = CompiledSearch((query or "").strip(), cancel=self._metadata.cancel)
        if len(q) < _MIN_SEARCH_CHARS:
            return SearchResults("", {}, False)

        html = ["<div style='font-family:sans-serif'>"]
        total = 0

        def _score_text(text: str):
            self._metadata.check_cancelled()
            return search_text_match_score(text or "", q)

        # PDF highlights (go directly to page)
        for kind, enabled, heading in (
            ("pdf_highlights", "pdf_highlights" in self._filters, t("search_all_pdf_highlights")),
            ("pdf_annotations", "annotations" in self._filters, t("search_all_annotations") + " (PDF)"),
        ):
            if not enabled:
                continue
            rows = self._search_excerpt_hits(
                kind,
                q,
            )

            if rows:
                html.append(f"<h3>{escape(heading)}</h3>")
                by_file: dict = {}
                for cid, page, text in rows:
                    by_file.setdefault(cid, []).append((page, text))
                for cid, pages in by_file.items():
                    title = escape(self._pdf_title(cid))
                    html.append(f"<div style='margin:6px 0 2px'><b>{title}</b></div><ul style='margin:0 0 6px 16px'>")
                    for page, text in pages:
                        snippet = escape(self._snippet(text or "", q))
                        result_url = escape(
                            _highlight_result_url(
                                self._highlight_previews,
                                media="pdf",
                                card_id=cid,
                                position=page,
                                query=q,
                                text=text or "",
                            ),
                            quote=True,
                        )
                        html.append(
                            f"<li><a href='{result_url}'>{escape(t('search_all_page', page=page))}</a>"
                            f" — <span style='color:#888'>{snippet}</span></li>"
                        )
                        total += 1
                    html.append("</ul>")

        self._publish(html, total)

        # Cards created from PDF pages (go to page)
        if "pdf_sources" in self._filters:
            rows = self._search_excerpt_hits(
                "pdf_sources",
                q,
                source_rows=True,
            )

            if rows:
                html.append(f"<h3>{escape(t('search_all_pdf_sources'))}</h3>")
                by_file: dict = {}
                for cid, page, excerpt, _note_id in rows:
                    by_file.setdefault(cid, []).append((page, excerpt))
                for cid, pages in by_file.items():
                    title = escape(self._pdf_title(cid))
                    html.append(f"<div style='margin:6px 0 2px'><b>{title}</b></div><ul style='margin:0 0 6px 16px'>")
                    for page, excerpt in pages:
                        snippet = escape(self._snippet(excerpt or "", q))
                        html.append(
                            f"<li><a href='inc://pdf/{cid}/{int(page)}?q={quote(q)}'>{escape(t('search_all_page', page=page))}</a>"
                            f" — <span style='color:#888'>{snippet}</span></li>"
                        )
                        total += 1
                    html.append("</ul>")

        self._publish(html, total)

        for kind, enabled, heading in (
            ("epub_highlights", "epub_highlights" in self._filters, t("search_all_epub_highlights")),
            ("epub_annotations", "annotations" in self._filters, t("search_all_annotations") + " (EPUB)"),
        ):
            if not enabled:
                continue
            rows = self._search_excerpt_hits(
                kind,
                q,
            )

            if rows:
                html.append(f"<h3>{escape(heading)}</h3>")
                by_file: dict = {}
                for cid, section_index, text in rows:
                    by_file.setdefault(cid, []).append((section_index, text))
                for cid, entries in by_file.items():
                    title = escape(self._epub_title(cid))
                    html.append(f"<div style='margin:6px 0 2px'><b>{title}</b></div><ul style='margin:0 0 6px 16px'>")
                    for section_index, text in entries:
                        snippet = escape(self._snippet(text or "", q))
                        result_url = escape(
                            _highlight_result_url(
                                self._highlight_previews,
                                media="epub",
                                card_id=cid,
                                position=section_index,
                                query=q,
                                text=text or "",
                            ),
                            quote=True,
                        )
                        html.append(
                            f"<li><a href='{result_url}'>{escape(t('search_all_section', section=section_index + 1))}</a>"
                            f" — <span style='color:#888'>{snippet}</span></li>"
                        )
                        total += 1
                    html.append("</ul>")

        self._publish(html, total)

        if "epub_sources" in self._filters:
            rows = self._search_excerpt_hits(
                "epub_sources",
                q,
                source_rows=True,
            )

            if rows:
                html.append(f"<h3>{escape(t('search_all_epub_sources'))}</h3>")
                by_file: dict = {}
                for cid, section_index, excerpt, _note_id in rows:
                    by_file.setdefault(cid, []).append((section_index, excerpt))
                for cid, entries in by_file.items():
                    title = escape(self._epub_title(cid))
                    html.append(f"<div style='margin:6px 0 2px'><b>{title}</b></div><ul style='margin:0 0 6px 16px'>")
                    for section_index, excerpt in entries:
                        snippet = escape(self._snippet(excerpt or "", q))
                        html.append(
                            f"<li><a href='inc://epub/{cid}/{int(section_index)}?q={quote(q)}'>{escape(t('search_all_section', section=section_index + 1))}</a>"
                            f" — <span style='color:#888'>{snippet}</span></li>"
                        )
                        total += 1
                    html.append("</ul>")

        self._publish(html, total)

        # Actual PDF file text (page-level)
        if "pdf_content" in self._filters:
            pdf_page_hits = self._search_pdf_file_hits(q, limit=_MAX_CATEGORY_RESULTS)
            if pdf_page_hits:
                html.append(f"<h3>{escape(t('search_all_pdf_file_content'))}</h3>")
                by_file: dict = {}
                for cid, page, snippet_text in pdf_page_hits:
                    by_file.setdefault(cid, []).append((page, snippet_text))
                for cid, pages in by_file.items():
                    title = escape(self._pdf_title(cid))
                    html.append(f"<div style='margin:6px 0 2px'><b>{title}</b></div><ul style='margin:0 0 6px 16px'>")
                    for page, snippet_text in pages:
                        snippet = escape(snippet_text)
                        html.append(
                            f"<li><a href='inc://pdf/{cid}/{int(page)}?q={quote(q)}'>{escape(t('search_all_page', page=page))}</a>"
                            f" — <span style='color:#888'>{snippet}</span></li>"
                        )
                        total += 1
                    html.append("</ul>")

        self._publish(html, total)

        if "epub_content" in self._filters:
            epub_section_hits = self._search_epub_file_hits(
                q,
                limit=_MAX_CATEGORY_RESULTS,
            )
            if epub_section_hits:
                html.append(f"<h3>{escape(t('search_all_epub_file_content'))}</h3>")
                by_file: dict = {}
                for cid, section_index, title, snippet_text in epub_section_hits:
                    by_file.setdefault(cid, []).append((section_index, title, snippet_text))
                for cid, entries in by_file.items():
                    title = escape(self._epub_title(cid))
                    html.append(f"<div style='margin:6px 0 2px'><b>{title}</b></div><ul style='margin:0 0 6px 16px'>")
                    for section_index, section_title, snippet_text in entries:
                        snippet = escape(snippet_text)
                        section_label = escape(section_title or t("search_all_section", section=section_index + 1))
                        html.append(
                            f"<li><a href='inc://epub/{cid}/{int(section_index)}?q={quote(q)}'>{section_label}</a>"
                            f" — <span style='color:#888'>{snippet}</span></li>"
                        )
                        total += 1
                    html.append("</ul>")

        self._publish(html, total)

        if "image_ocr" in self._filters:
            search_limit = (
                _MAX_CATEGORY_RESULTS * _LIVE_RESULT_OVERSAMPLE_FACTOR
                if "current_profile" in self._filters
                else _MAX_CATEGORY_RESULTS
            )
            ocr_hits = self._search_ocr_hits(q, search_limit)
            if "current_profile" in self._filters:
                ocr_hits = [
                    row for row in ocr_hits if self._metadata.cards.get(int(row[1])) is not None
                ]
            if ocr_hits:
                html.append(f"<h3>{escape(t('search_all_image_ocr'))}</h3><ul>")
                for note_id, card_id, image_name, text in ocr_hits[
                    :_MAX_CATEGORY_RESULTS
                ]:
                    try:
                        note = self._metadata.notes[note_id]
                        model_name = escape(note.model_name or t("search_all_note"))
                    except Exception:
                        model_name = t("search_all_note")
                    snippet = escape(self._snippet(text or "", q, max_len=180))
                    image_label = escape(image_name or t("search_all_ocr_text"))
                    html.append(
                        f"<li><a href='inc://card/{note_id}'>{model_name} — {escape(t('search_all_note_number', note_id=note_id))}</a>"
                        f"<br><span style='color:#888'>{image_label}: {snippet}</span></li>"
                    )
                    total += 1
                html.append("</ul>")

        self._publish(html, total)

        # All cards/notes (open in Browser)
        if "cards" in self._filters:
            note_ids = self._safe_find_notes(q)[:_MAX_CARD_SEARCH_CANDIDATES]
            if note_ids:
                ranked_notes: list[tuple[tuple[int, int, int, int], int, object, str]] = []
                for nid in note_ids:
                    try:
                        note = self._metadata.notes[nid]
                        if note is not None and note.pdf_filename is not None and not self._metadata.pdf_available(
                            note, self._addon_dir, self._profile,
                        ):
                            continue
                        model_name = note.model_name or t("search_all_note")
                        text = " ".join(note.fields or [])
                        score = _score_text(text)
                        if score is None:
                            continue
                        ranked_notes.append((score, int(nid), note, model_name))
                    except CancelledError:
                        raise
                    except Exception:
                        continue
                ranked_notes.sort(key=lambda item: (item[0], item[1]))
                html.append(f"<h3>{escape(t('search_all_cards'))}</h3><ul>")
                for _, nid, note, model_name in ranked_notes[:160]:
                    text = " ".join((note.fields or [])[:2])
                    snippet = escape(self._snippet(text, q))
                    html.append(
                        f"<li><a href='inc://card/{nid}'>{escape(model_name)} — {escape(t('search_all_note_number', note_id=nid))}</a>"
                        f"<br><span style='color:#888'>{snippet}</span></li>"
                    )
                    total += 1
                html.append("</ul>")

        self._publish(html, total)

        if total == 0:
            html.append(f"<div style='color:#888;padding:8px'>{escape(t('search_all_no_matches'))}</div>")
        html.append("</div>")
        self._metadata.check_cancelled()
        return SearchResults("".join(html), dict(self._highlight_previews), self._pdf_needs_index)



def run_search(addon_dir, profile, col, query, filters, *, cancel=None, progress=None, check_pdf_cache=False) -> SearchResults:
    builder = SearchResultsBuilder(addon_dir, profile, col, filters, cancel=cancel, progress=progress)
    builder._metadata.check_cancelled()
    # This thread-scoped connection is exclusively used by this serialized read.
    # Interrupt long SQLite scans; Anki queries and ranking stop at the next checkpoint.
    conn = get_connection(addon_dir, profile)
    if cancel is not None:
        conn.set_progress_handler(lambda: int(cancel.is_set()), 1000)
    try:
        restored = reconcile_pdf_search_indexes(
            addon_dir, profile, col, cancel=cancel,
        ) if check_pdf_cache else []
        return replace(builder.run(query), pdf_reindex_documents=tuple(restored))
    except sqlite3.OperationalError:
        builder._metadata.check_cancelled()
        raise
    finally:
        if cancel is not None:
            conn.set_progress_handler(None, 0)
