"""Visual bookshelf for opening Incremento PDF and EPUB documents by cover."""

from __future__ import annotations

import html
import math
import os
import re
import threading
import unicodedata
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, replace
from functools import lru_cache
from itertools import combinations
from pathlib import Path

from aqt import mw
from aqt.qt import (
    QAbstractItemView,
    QCheckBox,
    QColor,
    QComboBox,
    QCompleter,
    QDialog,
    QEvent,
    QHBoxLayout,
    QIcon,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPalette,
    QPainter,
    QPen,
    QPixmap,
    QPushButton,
    QSize,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTimer,
    QVBoxLayout,
    Qt,
    qconnect,
)
from aqt.utils import askUser, tooltip
from PyQt6.QtPdf import QPdfDocument
try:
    from ..backend.i18n import t, tn
except ImportError:
    from backend.i18n import t, tn

try:
    from ..backend.paths import get_active_profile as _active_profile
except ImportError:
    from paths import get_active_profile as _active_profile

try:
    from ..backend.pdf_manager import (
        PDF_COVER_FIELD,
        PDF_NOTE_TYPE,
        pdf_storage_abspath,
    )
    from ..backend.epub_manager import (
        EPUB_COVER_FIELD,
        EPUB_FILE_FIELD,
        EPUB_NOTE_TYPE,
    )
    from ..backend.media_review import (
        linked_media_attachment_card_ids,
    )
    from ..backend.priority_manager import get_all_priorities
except ImportError:
    from pdf_manager import PDF_COVER_FIELD, PDF_NOTE_TYPE, pdf_storage_abspath  # type: ignore
    from epub_manager import EPUB_COVER_FIELD, EPUB_FILE_FIELD, EPUB_NOTE_TYPE  # type: ignore
    from media_review import (  # type: ignore
        linked_media_attachment_card_ids,
    )
    from priority_manager import get_all_priorities  # type: ignore


_PREVIEW_WIDTH = 160
_PREVIEW_HEIGHT = 220
_TILE_WIDTH = 196
_TILE_HEIGHT = 350
_KIND_ALL = "ALL"
_KIND_PDF = "PDF"
_KIND_EPUB = "EPUB"
_TAG_MODE_OR = "OR"
_TAG_MODE_AND = "AND"
_MAX_TAG_FILTER_CHARS = 4_096
_MAX_TAG_FILTER_TERMS = 64
_MAX_TAG_SUGGESTIONS = 10_000
_MANAGED_FILENAME_UUID_RE = re.compile(r"-[0-9a-f]{32}$", re.IGNORECASE)
_VISIBLE_DUPLICATE_SUFFIX_RE = re.compile(r"\s+\[\d+\]\s*$")
_DUPLICATE_NOISE_TOKENS = frozenset(
    {
        "a",
        "an",
        "and",
        "book",
        "copy",
        "document",
        "edition",
        "epub",
        "for",
        "in",
        "of",
        "on",
        "pdf",
        "scan",
        "the",
        "to",
    }
)
_MAX_DUPLICATE_FEATURE_BUCKET = 64
_MAX_EXACT_TITLE_BUCKET = 128
_MAX_PDF_METADATA_TITLE_CHARS = 2_048
_ATTACHMENT_BADGE_ROLE = int(Qt.ItemDataRole.UserRole) + 1
_GENERIC_PDF_METADATA_TITLES = frozenset(
    {
        "document",
        "pdf",
        "scan",
        "unknown",
        "untitled",
    }
)


@dataclass(frozen=True)
class _BookshelfEntry:
    title: str
    card_id: int
    kind: str
    cover_filename: str = ""
    source_filename: str = ""
    priority: float | None = None
    tags: tuple[str, ...] = ()
    note_id: int = 0
    metadata_title: str = ""


@dataclass(frozen=True)
class _DuplicateFingerprint:
    kind: str
    title: str
    origin: str
    metadata_title: str
    title_tokens: frozenset[str]
    origin_tokens: frozenset[str]
    metadata_tokens: frozenset[str]
    title_trigrams: frozenset[str]
    origin_trigrams: frozenset[str]
    metadata_trigrams: frozenset[str]
    title_numbers: frozenset[str]
    origin_numbers: frozenset[str]
    metadata_numbers: frozenset[str]


def _bookshelf_theme_colors(background_lightness: int) -> tuple[str, str]:
    """Return readable caption and secondary text colors for the active theme."""
    if int(background_lightness) < 128:
        return "#f4f4f5", "#b8bcc4"
    return "#202124", "#5f6368"


def _note_text(note, field_name: str) -> str:
    try:
        return str(note[field_name] or "").strip()
    except Exception:
        return ""


def _note_tags(note) -> tuple[str, ...]:
    """Return bounded, display-ready note tags without case-folding their labels."""
    try:
        raw_tags = getattr(note, "tags", ()) or ()
    except Exception:
        return ()
    if isinstance(raw_tags, str):
        raw_tags = raw_tags.split()
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw_tag in raw_tags:
        tag = str(raw_tag or "").strip()
        key = tag.casefold()
        if not tag or len(tag) > 512 or key in seen:
            continue
        cleaned.append(tag)
        seen.add(key)
        if len(cleaned) >= 512:
            break
    return tuple(cleaned)


def _parse_bookshelf_tag_query(raw_query: object) -> tuple[str, ...]:
    """Parse a bounded, case-insensitive list of exact Anki tag names."""
    candidate = str(raw_query or "")[:_MAX_TAG_FILTER_CHARS]
    terms: list[str] = []
    seen: set[str] = set()
    for raw_term in re.split(r"[\s,;]+", candidate):
        term = raw_term.strip().casefold()
        if not term or len(term) > 512 or term in seen:
            continue
        terms.append(term)
        seen.add(term)
        if len(terms) >= _MAX_TAG_FILTER_TERMS:
            break
    return tuple(terms)


def _is_bookshelf_tag_delimiter(character: str) -> bool:
    return character in ",;" or character.isspace()


def _bookshelf_tag_token_bounds(query: str, cursor_position: int) -> tuple[int, int]:
    raw_query = str(query or "")
    try:
        cursor = max(0, min(len(raw_query), int(cursor_position)))
    except (TypeError, ValueError):
        cursor = len(raw_query)

    start = cursor
    while start > 0 and not _is_bookshelf_tag_delimiter(raw_query[start - 1]):
        start -= 1

    end = cursor
    while end < len(raw_query) and not _is_bookshelf_tag_delimiter(raw_query[end]):
        end += 1
    return start, end


def _complete_bookshelf_tag_query(
    query: object,
    completion: object,
    cursor_position: int,
) -> tuple[str, int]:
    """Replace only the tag token at the cursor with a selected suggestion."""
    raw_query = str(query or "")
    try:
        cursor = max(0, min(len(raw_query), int(cursor_position)))
    except (TypeError, ValueError):
        cursor = len(raw_query)
    tag = str(completion or "").strip()
    if (
        not tag
        or len(tag) > 512
        or any(_is_bookshelf_tag_delimiter(character) for character in tag)
    ):
        return raw_query, cursor

    start, end = _bookshelf_tag_token_bounds(raw_query, cursor)
    completed_query = f"{raw_query[:start]}{tag}{raw_query[end:]}"
    return completed_query, start + len(tag)


def _bookshelf_tag_suggestions(
    entries: list[_BookshelfEntry],
) -> tuple[str, ...]:
    """Return relevant tags ranked by document frequency, then by name."""
    labels: dict[str, str] = {}
    counts: dict[str, int] = {}
    for entry in entries:
        seen_on_entry: set[str] = set()
        for raw_tag in entry.tags:
            tag = str(raw_tag or "").strip()
            key = tag.casefold()
            if (
                not tag
                or len(tag) > 512
                or key in seen_on_entry
                or any(_is_bookshelf_tag_delimiter(character) for character in tag)
            ):
                continue
            seen_on_entry.add(key)
            if key not in labels:
                if len(labels) >= _MAX_TAG_SUGGESTIONS:
                    continue
                labels[key] = tag
                counts[key] = 0
            counts[key] += 1

    ranked_keys = sorted(
        labels,
        key=lambda key: (-counts[key], labels[key].casefold(), labels[key]),
    )
    return tuple(labels[key] for key in ranked_keys)


def _normalized_bookshelf_duplicate_label(value: object) -> str:
    label = html.unescape(str(value or ""))
    label = re.sub(r"<[^>]*>", " ", label)
    label = unicodedata.normalize("NFKC", label)
    label = label.replace("\u200b", "").strip()
    label = _VISIBLE_DUPLICATE_SUFFIX_RE.sub("", label)
    decomposed = unicodedata.normalize("NFKD", label.casefold())
    label = "".join(
        character
        if character.isalnum()
        else " "
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return " ".join(label.split())


def _bookshelf_origin_label(entry: _BookshelfEntry) -> str:
    raw_source = str(entry.source_filename or "").strip().replace("\\", "/")
    source_name = raw_source.rsplit("/", 1)[-1]
    source_stem = os.path.splitext(source_name)[0]
    source_stem = _MANAGED_FILENAME_UUID_RE.sub("", source_stem)
    return _normalized_bookshelf_duplicate_label(source_stem)


def _bookshelf_metadata_title_label(entry: _BookshelfEntry) -> str:
    if str(entry.kind or "").strip().upper() != _KIND_PDF:
        return ""
    label = _normalized_bookshelf_duplicate_label(entry.metadata_title)
    return "" if label in _GENERIC_PDF_METADATA_TITLES else label


def _clean_pdf_metadata_title(value: object) -> str:
    raw = str(value or "")[:_MAX_PDF_METADATA_TITLE_CHARS]
    printable = "".join(
        character if character.isprintable() else " "
        for character in raw
    )
    return " ".join(printable.split())


def _read_pdf_metadata_title(pdf_path: str) -> str:
    """Read the standard PDF Title property without exposing parser failures."""
    if not pdf_path or not os.path.isfile(pdf_path):
        return ""
    document = QPdfDocument(None)
    try:
        document.load(pdf_path)
        title_field = QPdfDocument.MetaDataField.Title
        return _clean_pdf_metadata_title(document.metaData(title_field))
    except Exception:
        return ""
    finally:
        document.close()


@lru_cache(maxsize=4_096)
def _cached_pdf_metadata_title_for_signature(
    pdf_path: str,
    modified_ns: int,
    size: int,
) -> str:
    del modified_ns, size
    return _read_pdf_metadata_title(pdf_path)


def _cached_pdf_metadata_title(pdf_path: str) -> str:
    try:
        stat = os.stat(pdf_path)
    except OSError:
        return ""
    return _cached_pdf_metadata_title_for_signature(
        pdf_path,
        int(stat.st_mtime_ns),
        int(stat.st_size),
    )


def _load_pdf_metadata_titles(
    entries: list[_BookshelfEntry],
    *,
    profile: str,
    cancelled: threading.Event | None = None,
) -> dict[int, str]:
    """Read PDF metadata titles in a worker for one captured profile."""
    titles: dict[int, str] = {}
    for entry in entries:
        if cancelled is not None and cancelled.is_set():
            break
        if entry.kind != _KIND_PDF or not entry.source_filename:
            continue
        try:
            source_path = pdf_storage_abspath(
                entry.source_filename,
                profile=profile,
            )
        except Exception:
            continue
        if not source_path or not os.path.isfile(source_path):
            continue
        title = _cached_pdf_metadata_title(source_path)
        if title:
            titles[entry.card_id] = title
    return titles


def _duplicate_tokens(label: str) -> frozenset[str]:
    return frozenset(
        token
        for token in str(label or "").split()
        if token and token not in _DUPLICATE_NOISE_TOKENS
    )


def _duplicate_trigrams(tokens: frozenset[str]) -> frozenset[str]:
    trigrams: set[str] = set()
    for token in tokens:
        padded = f"^{token}$"
        if len(padded) < 3:
            trigrams.add(padded)
            continue
        trigrams.update(
            padded[index : index + 3]
            for index in range(len(padded) - 2)
        )
    return frozenset(trigrams)


def _duplicate_fingerprint(entry: _BookshelfEntry) -> _DuplicateFingerprint:
    title = _normalized_bookshelf_duplicate_label(entry.title)
    origin = _bookshelf_origin_label(entry)
    metadata_title = _bookshelf_metadata_title_label(entry)
    title_all_tokens = frozenset(title.split())
    origin_all_tokens = frozenset(origin.split())
    metadata_all_tokens = frozenset(metadata_title.split())
    title_tokens = _duplicate_tokens(title)
    origin_tokens = _duplicate_tokens(origin)
    metadata_tokens = _duplicate_tokens(metadata_title)
    return _DuplicateFingerprint(
        kind=str(entry.kind or "").strip().upper(),
        title=title,
        origin=origin,
        metadata_title=metadata_title,
        title_tokens=title_tokens,
        origin_tokens=origin_tokens,
        metadata_tokens=metadata_tokens,
        title_trigrams=_duplicate_trigrams(title_tokens),
        origin_trigrams=_duplicate_trigrams(origin_tokens),
        metadata_trigrams=_duplicate_trigrams(metadata_tokens),
        title_numbers=frozenset(
            token for token in title_all_tokens if token.isdecimal()
        ),
        origin_numbers=frozenset(
            token for token in origin_all_tokens if token.isdecimal()
        ),
        metadata_numbers=frozenset(
            token for token in metadata_all_tokens if token.isdecimal()
        ),
    )


def _bookshelf_duplicate_key(entry: _BookshelfEntry) -> tuple[str, str] | None:
    """Return the strongest exact key retained for compatibility and tests."""
    label = _bookshelf_origin_label(entry)
    if not label:
        label = _normalized_bookshelf_duplicate_label(entry.title)
    kind = str(entry.kind or "").strip().upper()
    return (kind, label) if kind and label else None


def _duplicate_feature_weights(
    feature_sets: list[frozenset[str]],
) -> dict[str, float]:
    document_count = max(1, len(feature_sets))
    frequencies: Counter[str] = Counter()
    for features in feature_sets:
        frequencies.update(features)
    return {
        feature: 1.0 + math.log((document_count + 1) / (frequency + 1))
        for feature, frequency in frequencies.items()
    }


def _weighted_duplicate_scores(
    left: frozenset[str],
    right: frozenset[str],
    weights: dict[str, float],
) -> tuple[float, float]:
    if not left or not right:
        return 0.0, 0.0
    intersection = left & right
    union = left | right
    intersection_weight = sum(weights.get(feature, 1.0) for feature in intersection)
    union_weight = sum(weights.get(feature, 1.0) for feature in union)
    left_weight = sum(weights.get(feature, 1.0) for feature in left)
    right_weight = sum(weights.get(feature, 1.0) for feature in right)
    jaccard = intersection_weight / union_weight if union_weight else 0.0
    smallest = min(left_weight, right_weight)
    containment = intersection_weight / smallest if smallest else 0.0
    return jaccard, containment


def _duplicate_channel_matches(
    left_label: str,
    right_label: str,
    left_tokens: frozenset[str],
    right_tokens: frozenset[str],
    left_trigrams: frozenset[str],
    right_trigrams: frozenset[str],
    left_numbers: frozenset[str],
    right_numbers: frozenset[str],
    token_weights: dict[str, float],
    trigram_weights: dict[str, float],
    *,
    exact_origin: bool = False,
) -> bool:
    if not left_label or not right_label:
        return False
    if left_numbers != right_numbers and (left_numbers or right_numbers):
        return False
    if left_label == right_label:
        if exact_origin:
            return True
        informative_chars = sum(len(token) for token in left_tokens)
        return len(left_label) >= 8 and informative_chars >= 6
    if min(len(left_label), len(right_label)) < 6:
        return False

    token_jaccard, token_containment = _weighted_duplicate_scores(
        left_tokens,
        right_tokens,
        token_weights,
    )
    trigram_jaccard, _trigram_containment = _weighted_duplicate_scores(
        left_trigrams,
        right_trigrams,
        trigram_weights,
    )
    length_ratio = min(len(left_label), len(right_label)) / max(
        len(left_label), len(right_label)
    )
    return bool(
        (token_jaccard >= 0.72 and trigram_jaccard >= 0.45)
        or (
            token_containment >= 0.88
            and trigram_jaccard >= 0.52
            and length_ratio >= 0.45
        )
        or (
            trigram_jaccard >= 0.78
            and token_containment >= 0.28
            and length_ratio >= 0.60
        )
        or (
            trigram_jaccard >= 0.84
            and len(left_tokens) == len(right_tokens) == 1
            and length_ratio >= 0.75
        )
    )


def _bookshelf_duplicate_matches(
    entries: list[_BookshelfEntry],
) -> dict[int, tuple[_BookshelfEntry, ...]]:
    """Return direct fuzzy matches using rare words and character trigrams."""
    if len(entries) < 2:
        return {}
    fingerprints = [_duplicate_fingerprint(entry) for entry in entries]
    title_token_weights = _duplicate_feature_weights(
        [fingerprint.title_tokens for fingerprint in fingerprints]
    )
    origin_token_weights = _duplicate_feature_weights(
        [fingerprint.origin_tokens for fingerprint in fingerprints]
    )
    metadata_token_weights = _duplicate_feature_weights(
        [fingerprint.metadata_tokens for fingerprint in fingerprints]
    )
    title_trigram_weights = _duplicate_feature_weights(
        [fingerprint.title_trigrams for fingerprint in fingerprints]
    )
    origin_trigram_weights = _duplicate_feature_weights(
        [fingerprint.origin_trigrams for fingerprint in fingerprints]
    )
    metadata_trigram_weights = _duplicate_feature_weights(
        [fingerprint.metadata_trigrams for fingerprint in fingerprints]
    )

    exact_origins: defaultdict[tuple[str, str], list[int]] = defaultdict(list)
    exact_titles: defaultdict[tuple[str, str], list[int]] = defaultdict(list)
    exact_metadata_titles: defaultdict[tuple[str, str], list[int]] = defaultdict(list)
    feature_buckets: defaultdict[tuple[str, str, str], list[int]] = defaultdict(list)
    for index, fingerprint in enumerate(fingerprints):
        if fingerprint.origin:
            exact_origins[fingerprint.kind, fingerprint.origin].append(index)
        if fingerprint.title:
            exact_titles[fingerprint.kind, fingerprint.title].append(index)
        if fingerprint.metadata_title:
            exact_metadata_titles[
                fingerprint.kind,
                fingerprint.metadata_title,
            ].append(index)
        for channel, tokens, trigrams in (
            ("title", fingerprint.title_tokens, fingerprint.title_trigrams),
            ("origin", fingerprint.origin_tokens, fingerprint.origin_trigrams),
            (
                "metadata",
                fingerprint.metadata_tokens,
                fingerprint.metadata_trigrams,
            ),
        ):
            for token in tokens:
                feature_buckets[fingerprint.kind, channel, f"t:{token}"].append(index)
            for trigram in trigrams:
                feature_buckets[fingerprint.kind, channel, f"g:{trigram}"].append(index)

    matches: defaultdict[int, set[int]] = defaultdict(set)

    def link(left_index: int, right_index: int) -> None:
        if left_index == right_index:
            return
        matches[left_index].add(right_index)
        matches[right_index].add(left_index)

    for indexes in exact_origins.values():
        for left_index, right_index in combinations(indexes, 2):
            left = fingerprints[left_index]
            right = fingerprints[right_index]
            if left.origin_numbers == right.origin_numbers:
                link(left_index, right_index)

    for indexes in exact_titles.values():
        if len(indexes) > _MAX_EXACT_TITLE_BUCKET:
            continue
        for left_index, right_index in combinations(indexes, 2):
            left = fingerprints[left_index]
            right = fingerprints[right_index]
            if _duplicate_channel_matches(
                left.title,
                right.title,
                left.title_tokens,
                right.title_tokens,
                left.title_trigrams,
                right.title_trigrams,
                left.title_numbers,
                right.title_numbers,
                title_token_weights,
                title_trigram_weights,
            ):
                link(left_index, right_index)

    for indexes in exact_metadata_titles.values():
        if len(indexes) > _MAX_EXACT_TITLE_BUCKET:
            continue
        for left_index, right_index in combinations(indexes, 2):
            left = fingerprints[left_index]
            right = fingerprints[right_index]
            if _duplicate_channel_matches(
                left.metadata_title,
                right.metadata_title,
                left.metadata_tokens,
                right.metadata_tokens,
                left.metadata_trigrams,
                right.metadata_trigrams,
                left.metadata_numbers,
                right.metadata_numbers,
                metadata_token_weights,
                metadata_trigram_weights,
            ):
                link(left_index, right_index)

    candidate_pairs: set[tuple[int, int]] = set()
    for indexes in feature_buckets.values():
        unique_indexes = sorted(set(indexes))
        if not (1 < len(unique_indexes) <= _MAX_DUPLICATE_FEATURE_BUCKET):
            continue
        candidate_pairs.update(combinations(unique_indexes, 2))

    for left_index, right_index in candidate_pairs:
        if right_index in matches.get(left_index, set()):
            continue
        left = fingerprints[left_index]
        right = fingerprints[right_index]
        if left.kind != right.kind:
            continue
        title_match = _duplicate_channel_matches(
            left.title,
            right.title,
            left.title_tokens,
            right.title_tokens,
            left.title_trigrams,
            right.title_trigrams,
            left.title_numbers,
            right.title_numbers,
            title_token_weights,
            title_trigram_weights,
        )
        origin_match = _duplicate_channel_matches(
            left.origin,
            right.origin,
            left.origin_tokens,
            right.origin_tokens,
            left.origin_trigrams,
            right.origin_trigrams,
            left.origin_numbers,
            right.origin_numbers,
            origin_token_weights,
            origin_trigram_weights,
            exact_origin=True,
        )
        metadata_match = _duplicate_channel_matches(
            left.metadata_title,
            right.metadata_title,
            left.metadata_tokens,
            right.metadata_tokens,
            left.metadata_trigrams,
            right.metadata_trigrams,
            left.metadata_numbers,
            right.metadata_numbers,
            metadata_token_weights,
            metadata_trigram_weights,
        )
        if title_match or origin_match or metadata_match:
            link(left_index, right_index)

    return {
        entries[index].card_id: tuple(entries[match] for match in sorted(indexes))
        for index, indexes in matches.items()
        if indexes
    }


def _bookshelf_duplicate_groups(
    entries: list[_BookshelfEntry],
) -> tuple[tuple[_BookshelfEntry, ...], ...]:
    """Return connected candidate groups in the shelf's stable order."""
    matches = _bookshelf_duplicate_matches(entries)
    entries_by_card = {entry.card_id: entry for entry in entries}
    order = {entry.card_id: index for index, entry in enumerate(entries)}
    visited: set[int] = set()
    groups: list[tuple[_BookshelfEntry, ...]] = []
    for entry in entries:
        if entry.card_id in visited or entry.card_id not in matches:
            continue
        pending = [entry.card_id]
        component: set[int] = set()
        while pending:
            card_id = pending.pop()
            if card_id in component:
                continue
            component.add(card_id)
            pending.extend(
                candidate.card_id for candidate in matches.get(card_id, ())
            )
        visited.update(component)
        group = tuple(
            entries_by_card[card_id]
            for card_id in sorted(component, key=order.__getitem__)
            if card_id in entries_by_card
        )
        if len(group) > 1:
            groups.append(group)
    return tuple(groups)


def _bookshelf_duplicate_entries(
    entries: list[_BookshelfEntry],
) -> list[_BookshelfEntry]:
    matched_card_ids = set(_bookshelf_duplicate_matches(entries))
    return [entry for entry in entries if entry.card_id in matched_card_ids]


def _bookshelf_note_ids(entries: list[_BookshelfEntry]) -> tuple[int, ...]:
    note_ids: list[int] = []
    seen: set[int] = set()
    for entry in entries:
        try:
            note_id = int(entry.note_id)
        except (TypeError, ValueError):
            continue
        if note_id <= 0 or note_id in seen:
            continue
        note_ids.append(note_id)
        seen.add(note_id)
    return tuple(note_ids)


def _bookshelf_attached_card_ids(
    addon_dir: str,
    profile: str,
    entries: list[_BookshelfEntry],
    *,
    col,
) -> tuple[int, ...]:
    """Return distinct live cards linked through canonical attachment data."""
    attached_by_document = _bookshelf_attachment_card_ids_by_document(
        addon_dir,
        profile,
        entries,
        col=col,
    )
    attached = {
        card_id
        for card_ids in attached_by_document.values()
        for card_id in card_ids
    }
    return tuple(sorted(attached))


def _bookshelf_attachment_card_ids_by_document(
    addon_dir: str,
    profile: str,
    entries: list[_BookshelfEntry],
    *,
    col,
) -> dict[int, tuple[int, ...]]:
    attached_by_document: dict[int, tuple[int, ...]] = {}
    for entry in entries:
        if entry.kind not in {_KIND_PDF, _KIND_EPUB} or entry.card_id <= 0:
            continue
        linked_card_ids = linked_media_attachment_card_ids(
            addon_dir,
            profile,
            int(entry.card_id),
            col=col,
            media_kind=entry.kind.casefold(),
            include_tree_descendants=True,
        )
        attached: set[int] = set()
        for raw_card_id in linked_card_ids:
            try:
                card_id = int(raw_card_id)
            except (TypeError, ValueError):
                continue
            if card_id > 0:
                attached.add(card_id)
        attached_by_document[entry.card_id] = tuple(sorted(attached))
    return attached_by_document


def _bookshelf_attachment_counts(
    addon_dir: str,
    profile: str,
    entries: list[_BookshelfEntry],
    *,
    col,
) -> dict[int, int]:
    return {
        card_id: len(card_ids)
        for card_id, card_ids in _bookshelf_attachment_card_ids_by_document(
            addon_dir,
            profile,
            entries,
            col=col,
        ).items()
    }


def _bookshelf_entry_has_attachment_badge(
    entry: _BookshelfEntry,
    *,
    duplicates_only: bool,
    attachment_counts: dict[int, int],
) -> bool:
    return bool(
        duplicates_only
        and int(attachment_counts.get(entry.card_id, 0) or 0) > 0
    )


class _BookshelfItemDelegate(QStyledItemDelegate):
    """Paint attachment status above Qt's cover/selection rendering."""

    def paint(self, painter, option, index) -> None:
        super().paint(painter, option, index)
        try:
            attachment_count = int(index.data(_ATTACHMENT_BADGE_ROLE) or 0)
        except (TypeError, ValueError):
            attachment_count = 0
        if attachment_count <= 0:
            return

        initialized_option = QStyleOptionViewItem(option)
        self.initStyleOption(initialized_option, index)
        widget = initialized_option.widget
        style = widget.style() if widget is not None else None
        icon_rect = (
            style.subElementRect(
                QStyle.SubElement.SE_ItemViewItemDecoration,
                initialized_option,
                widget,
            )
            if style is not None
            else None
        )
        if icon_rect is not None and icon_rect.isValid() and icon_rect.width() >= 36:
            icon_left = icon_rect.left()
            icon_top = icon_rect.top()
            icon_width = icon_rect.width()
            try:
                actual_size = initialized_option.icon.actualSize(icon_rect.size())
                if 36 <= actual_size.width() < icon_rect.width():
                    icon_left += (icon_rect.width() - actual_size.width()) // 2
                    icon_width = actual_size.width()
                if 36 <= actual_size.height() < icon_rect.height():
                    icon_top += (icon_rect.height() - actual_size.height()) // 2
            except (AttributeError, RuntimeError):
                pass
        else:
            icon_width = min(
                _PREVIEW_WIDTH,
                max(36, initialized_option.rect.width()),
            )
            icon_left = initialized_option.rect.left() + max(
                0,
                (initialized_option.rect.width() - icon_width) // 2,
            )
            icon_top = initialized_option.rect.top() + 4

        diameter = 32
        margin = 7
        left = icon_left + icon_width - diameter - margin
        top = icon_top + margin

        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            outline_pen = QPen(QColor("#0b4f25"))
            outline_pen.setWidth(2)
            painter.setPen(outline_pen)
            painter.setBrush(QColor("#188038"))
            painter.drawEllipse(left, top, diameter, diameter)
            check_pen = QPen(QColor("#ffffff"))
            check_pen.setWidth(4)
            check_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            check_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(check_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(left + 8, top + 16, left + 14, top + 22)
            painter.drawLine(left + 14, top + 22, left + 25, top + 10)
        finally:
            painter.restore()


def _bookshelf_delete_confirmation(
    *,
    document_count: int,
    attached_card_count: int,
    keep_one: bool,
) -> str:
    confirmation = (
        tn("reader_bookshelf_delete_others_confirm", document_count)
        if keep_one
        else t("reader_bookshelf_delete_confirm")
    )
    if attached_card_count > 0:
        confirmation += "\n\n" + tn(
            "reader_bookshelf_delete_attached_warning",
            attached_card_count,
        )
    return confirmation


def _without_bookshelf_notes(
    entries: list[_BookshelfEntry],
    note_ids: tuple[int, ...],
) -> list[_BookshelfEntry]:
    deleted = {int(note_id) for note_id in note_ids if int(note_id) > 0}
    return [entry for entry in entries if entry.note_id not in deleted]


def _with_pdf_metadata_titles(
    entries: list[_BookshelfEntry],
    titles: dict[int, str],
) -> list[_BookshelfEntry]:
    return [
        replace(entry, metadata_title=titles[entry.card_id])
        if entry.kind == _KIND_PDF and titles.get(entry.card_id)
        else entry
        for entry in entries
    ]


class _BookshelfTagCompleter(QCompleter):
    """Complete the active tag token without replacing the whole query."""

    def splitPath(self, path: str) -> list[str]:
        query = str(path or "")
        widget = self.widget()
        try:
            cursor = int(widget.cursorPosition())
        except (AttributeError, RuntimeError, TypeError, ValueError):
            cursor = len(query)
        start, _end = _bookshelf_tag_token_bounds(query, cursor)
        return [query[start:cursor]]

    def pathFromIndex(self, index) -> str:
        completion = str(super().pathFromIndex(index) or "")
        widget = self.widget()
        try:
            query = str(widget.text() or "")
            cursor = int(widget.cursorPosition())
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return completion
        completed_query, completed_cursor = _complete_bookshelf_tag_query(
            query,
            completion,
            cursor,
        )

        def restore_cursor() -> None:
            try:
                if widget.text() == completed_query:
                    widget.setCursorPosition(completed_cursor)
            except (AttributeError, RuntimeError):
                return

        QTimer.singleShot(0, restore_cursor)
        return completed_query


def _load_bookshelf_entries(
    addon_dir: str,
    *,
    collection=None,
    profile: str | None = None,
) -> list[_BookshelfEntry]:
    """Return every live PDF/EPUB note, including suspended reading cards."""
    col = collection or mw.col
    try:
        captured_profile = (
            str(profile)
            if profile is not None
            else str(_active_profile() or "")
        )
        all_priorities = get_all_priorities(addon_dir, captured_profile)
    except Exception:
        all_priorities = {}

    entries: list[_BookshelfEntry] = []
    note_specs = (
        (PDF_NOTE_TYPE, _KIND_PDF, PDF_COVER_FIELD, "PDF_Filename"),
        (EPUB_NOTE_TYPE, _KIND_EPUB, EPUB_COVER_FIELD, EPUB_FILE_FIELD),
    )
    for note_type, kind, cover_field, source_field in note_specs:
        try:
            note_ids = col.find_notes(f'note:"{note_type}"')
        except Exception:
            continue
        for note_id in note_ids:
            try:
                note = col.get_note(note_id)
                card_ids = col.find_cards(f"nid:{note_id}")
            except Exception:
                continue
            if not card_ids:
                continue

            try:
                card_id = int(card_ids[0])
            except Exception:
                continue

            title = _note_text(note, "Title")
            if not title:
                fields = getattr(note, "fields", None)
                title = str(fields[0] if fields else note_id).strip()

            entries.append(
                _BookshelfEntry(
                    title=title or str(note_id),
                    card_id=card_id,
                    kind=kind,
                    cover_filename=_note_text(note, cover_field),
                    source_filename=_note_text(note, source_field),
                    priority=all_priorities.get(card_id),
                    tags=_note_tags(note),
                    note_id=int(note_id),
                )
            )

    return sorted(entries, key=lambda entry: (entry.title.casefold(), entry.card_id))


def _load_bookshelf_snapshot(
    addon_dir: str,
    profile: str,
    *,
    collection=None,
) -> tuple[list[_BookshelfEntry], dict[int, int]]:
    """Load shelf entries and title-known duplicate attachment counts together."""
    col = collection or mw.col
    entries = _load_bookshelf_entries(
        addon_dir,
        collection=col,
        profile=profile,
    )
    duplicate_entries = _bookshelf_duplicate_entries(entries)
    if not duplicate_entries:
        return entries, {}
    return (
        entries,
        _bookshelf_attachment_counts(
            addon_dir,
            profile,
            duplicate_entries,
            col=col,
        ),
    )


def _filter_bookshelf_entries(
    entries: list[_BookshelfEntry],
    query: str,
    kind: str = _KIND_ALL,
    *,
    tag_query: str = "",
    tag_mode: str = _TAG_MODE_OR,
    duplicates_only: bool = False,
    duplicate_card_ids: set[int] | None = None,
) -> list[_BookshelfEntry]:
    needle = str(query or "").strip().casefold()
    normalized_kind = str(kind or _KIND_ALL).strip().upper()
    requested_tags = _parse_bookshelf_tag_query(tag_query)
    normalized_tag_mode = (
        _TAG_MODE_AND
        if str(tag_mode or "").strip().upper() == _TAG_MODE_AND
        else _TAG_MODE_OR
    )
    if not duplicates_only:
        active_duplicate_card_ids: set[int] = set()
    elif duplicate_card_ids is None:
        active_duplicate_card_ids = {
            entry.card_id for entry in _bookshelf_duplicate_entries(entries)
        }
    else:
        active_duplicate_card_ids = set(duplicate_card_ids)

    def matches_tags(entry: _BookshelfEntry) -> bool:
        if not requested_tags:
            return True
        entry_tags = {
            str(tag or "").strip().casefold()
            for tag in entry.tags
            if str(tag or "").strip()
        }
        if normalized_tag_mode == _TAG_MODE_AND:
            return all(tag in entry_tags for tag in requested_tags)
        return any(tag in entry_tags for tag in requested_tags)

    return [
        entry
        for entry in entries
        if (normalized_kind == _KIND_ALL or entry.kind == normalized_kind)
        and (not needle or needle in entry.title.casefold())
        and matches_tags(entry)
        and (not duplicates_only or entry.card_id in active_duplicate_card_ids)
    ]


def _bookshelf_count_text(
    all_entries: list[_BookshelfEntry],
    visible_entries: list[_BookshelfEntry],
    kind: str,
) -> str:
    normalized_kind = str(kind or _KIND_ALL).strip().upper()
    eligible = [
        entry
        for entry in all_entries
        if normalized_kind == _KIND_ALL or entry.kind == normalized_kind
    ]
    total = len(eligible)
    visible = len(visible_entries)
    kind_key = {
        _KIND_ALL: "reader_bookshelf_document_count",
        _KIND_PDF: "reader_bookshelf_pdf_count",
        _KIND_EPUB: "reader_bookshelf_epub_count",
    }.get(normalized_kind, "reader_bookshelf_document_count")
    count_label = tn(kind_key, total)
    if not total:
        return t({
            _KIND_ALL: "reader_bookshelf_no_documents",
            _KIND_PDF: "reader_bookshelf_no_pdfs",
            _KIND_EPUB: "reader_bookshelf_no_epubs",
        }.get(normalized_kind, "reader_bookshelf_no_documents"))
    if visible != total:
        return t("reader_bookshelf_showing", visible=visible, total=count_label)
    if normalized_kind == _KIND_ALL:
        pdf_count = sum(entry.kind == _KIND_PDF for entry in eligible)
        epub_count = sum(entry.kind == _KIND_EPUB for entry in eligible)
        return t("reader_bookshelf_all_summary", documents=count_label, pdfs=tn("reader_bookshelf_pdf_count", pdf_count), epubs=tn("reader_bookshelf_epub_count", epub_count))
    return count_label


def _existing_media_preview_path(media_dir: str, cover_filename: str) -> str:
    """Resolve an Anki media preview without allowing it to escape media.dir()."""
    raw = str(cover_filename or "").strip()
    if not raw or not media_dir:
        return ""
    try:
        root = Path(media_dir).resolve()
        candidate = (root / raw).resolve()
        candidate.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return ""
    return str(candidate) if candidate.is_file() else ""


def _render_pdf_first_page(pdf_path: str, render_width: int = _PREVIEW_WIDTH):
    """Render one small first-page image; safe to call in Anki's task worker."""
    if not pdf_path or not os.path.isfile(pdf_path):
        return None
    doc = QPdfDocument(None)
    try:
        doc.load(pdf_path)
        if doc.pageCount() <= 0:
            return None
        page_size = doc.pagePointSize(0)
        page_width = float(page_size.width() or 0)
        page_height = float(page_size.height() or 0)
        render_height = int(render_width * 1.414)
        if page_width > 0 and page_height > 0:
            render_height = max(1, int(render_width * page_height / page_width))
        image = doc.render(0, QSize(render_width, render_height))
        return image if image is not None and not image.isNull() else None
    except Exception:
        return None
    finally:
        doc.close()


class _DocumentBookshelfDialog(QDialog):
    """A searchable, progressively loaded grid of PDF and EPUB covers."""

    def __init__(
        self,
        parent=None,
        *,
        addon_dir: str,
        last_opened_card_id: int | None = None,
        entries: list[_BookshelfEntry] | None = None,
        attachment_counts: dict[int, int] | None = None,
    ):
        super().__init__(parent)
        self._addon_dir = str(addon_dir)
        try:
            self._profile = str(_active_profile() or "")
        except Exception:
            self._profile = ""
        self._entries = (
            list(entries)
            if entries is not None
            else _load_bookshelf_entries(addon_dir)
        )
        self._last_opened_card_id = last_opened_card_id
        self._thumbnail_generation = 0
        self._thumbnail_queue: deque[tuple[QListWidgetItem, _BookshelfEntry]] = deque()
        self._thumbnail_cache: dict[tuple[str, int], QIcon] = {}
        self._duplicate_matches: dict[int, tuple[_BookshelfEntry, ...]] = {}
        self._attachment_counts = {
            int(card_id): max(0, int(count or 0))
            for card_id, count in dict(attachment_counts or {}).items()
            if int(card_id) > 0
        }
        self._attachment_checked_card_ids = set(self._attachment_counts)
        self._attachment_scan_in_progress = False
        self._attachment_scan_generation = 0
        self._delete_check_in_progress = False
        self._pdf_metadata_cancelled = threading.Event()
        self._metadata_scan_pending = any(
            entry.kind == _KIND_PDF and bool(entry.source_filename)
            for entry in self._entries
        )
        try:
            self._media_dir = str(mw.col.media.dir() or "")
        except Exception:
            self._media_dir = ""

        self.setWindowTitle(t("reader_bookshelf_title"))
        self.resize(1080, 760)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel(f"<b>{t('reader_bookshelf_title')}</b>")
        title.setStyleSheet("font-size: 20px;")
        layout.addWidget(title)

        hint = QLabel(t("reader_bookshelf_intro"))
        hint.setWordWrap(True)
        layout.addWidget(hint)

        kind_row = QHBoxLayout()
        kind_row.addWidget(QLabel(t("reader_show_label")))
        self._kind_combo = QComboBox()
        self._kind_combo.addItem(t("reader_bookshelf_all_documents"), _KIND_ALL)
        self._kind_combo.addItem(t("reader_bookshelf_pdfs"), _KIND_PDF)
        self._kind_combo.addItem(t("reader_bookshelf_epubs"), _KIND_EPUB)
        kind_row.addWidget(self._kind_combo)
        self._duplicates_only_cb = QCheckBox(
            t("reader_bookshelf_duplicates_only")
        )
        kind_row.addWidget(self._duplicates_only_cb)
        kind_row.addStretch(1)
        layout.addLayout(kind_row)

        self._search = QLineEdit()
        self._search.setPlaceholderText(t("reader_bookshelf_search_titles"))
        self._search.setClearButtonEnabled(True)
        layout.addWidget(self._search)

        tag_row = QHBoxLayout()
        tag_row.addWidget(QLabel(t("reader_tags_label")))
        self._tag_search = QLineEdit()
        self._tag_search.setPlaceholderText(
            t("reader_bookshelf_filter_tags_placeholder")
        )
        self._tag_search.setClearButtonEnabled(True)
        self._tag_search.setMaxLength(_MAX_TAG_FILTER_CHARS)
        self._tag_search.setToolTip(
            t("reader_bookshelf_filter_tags_hint")
        )
        self._tag_search.setAccessibleName(t("reader_bookshelf_tag_filter_accessible"))
        tag_row.addWidget(self._tag_search, 1)

        tag_suggestions = _bookshelf_tag_suggestions(self._entries)
        self._tag_completer = _BookshelfTagCompleter(
            list(tag_suggestions),
            self._tag_search,
        )
        self._tag_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._tag_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._tag_completer.setCompletionMode(
            QCompleter.CompletionMode.PopupCompletion
        )
        self._tag_completer.setMaxVisibleItems(12)
        self._tag_search.setCompleter(self._tag_completer)

        self._browse_tags_button = QPushButton(t("reader_bookshelf_browse_tags"))
        self._browse_tags_button.setAccessibleName(t("reader_bookshelf_browse_tags_accessible"))
        self._browse_tags_button.setEnabled(bool(tag_suggestions))
        self._browse_tags_button.setToolTip(
            t("reader_bookshelf_browse_tags_hint")
            if tag_suggestions
            else t("reader_bookshelf_no_tags")
        )
        tag_row.addWidget(self._browse_tags_button)

        self._tag_mode_combo = QComboBox()
        self._tag_mode_combo.addItem(t("reader_bookshelf_any_tag"), _TAG_MODE_OR)
        self._tag_mode_combo.addItem(t("reader_bookshelf_all_tags"), _TAG_MODE_AND)
        self._tag_mode_combo.setToolTip(
            t("reader_bookshelf_tag_mode_hint")
        )
        tag_row.addWidget(self._tag_mode_combo)
        layout.addLayout(tag_row)

        self._count_label = QLabel("")
        try:
            background_lightness = self.palette().color(
                QPalette.ColorRole.Window
            ).lightness()
        except Exception:
            background_lightness = 255
        self._caption_color, muted_color = _bookshelf_theme_colors(
            background_lightness
        )
        self._count_label.setStyleSheet(f"color: {muted_color};")
        layout.addWidget(self._count_label)

        self._list = QListWidget()
        self._list.setViewMode(QListView.ViewMode.IconMode)
        self._list.setResizeMode(QListView.ResizeMode.Adjust)
        self._list.setMovement(QListView.Movement.Static)
        self._list.setWrapping(True)
        self._list.setWordWrap(True)
        self._list.setUniformItemSizes(True)
        self._list.setSpacing(8)
        self._list.setIconSize(QSize(_PREVIEW_WIDTH, _PREVIEW_HEIGHT))
        self._list.setGridSize(QSize(_TILE_WIDTH, _TILE_HEIGHT))
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.setStyleSheet(
            "QListWidget::item {"
            f" color: {self._caption_color};"
            " padding: 4px;"
            "}"
            "QListWidget::item:selected {"
            f" color: {self._caption_color};"
            "}"
        )
        self._bookshelf_item_delegate = _BookshelfItemDelegate(self._list)
        self._list.setItemDelegate(self._bookshelf_item_delegate)
        layout.addWidget(self._list, 1)

        self._preserve_history_cb = QCheckBox(
            t("reader_bookshelf_preserve_history")
        )
        self._preserve_history_cb.setChecked(False)
        layout.addWidget(self._preserve_history_cb)

        self._study_card_cb = QCheckBox(t("reader_open_card_to_study"))
        self._study_card_cb.setChecked(False)
        layout.addWidget(self._study_card_cb)

        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel_button = QPushButton(t("reader_cancel"))
        qconnect(cancel_button.clicked, self.reject)
        footer.addWidget(cancel_button)
        layout.addLayout(footer)

        qconnect(self._search.textChanged, self._refresh)
        qconnect(self._kind_combo.currentIndexChanged, self._refresh)
        qconnect(
            self._duplicates_only_cb.stateChanged,
            self._duplicates_filter_changed,
        )
        qconnect(self._tag_search.textChanged, self._refresh)
        qconnect(self._tag_mode_combo.currentIndexChanged, self._refresh)
        qconnect(self._browse_tags_button.clicked, self._show_tag_suggestions)
        qconnect(self._search.returnPressed, self._accept_current)
        qconnect(self._tag_search.returnPressed, self._accept_current)
        qconnect(self._list.itemActivated, self._accept_item)
        qconnect(self._list.currentItemChanged, self._update_option_availability)
        qconnect(self._list.customContextMenuRequested, self._show_context_menu)
        qconnect(
            self.finished,
            lambda *_args: self._pdf_metadata_cancelled.set(),
        )
        self._search.installEventFilter(self)
        self._tag_search.installEventFilter(self)
        self._list.viewport().installEventFilter(self)

        self._update_duplicate_filter_state()
        self._refresh()
        self._search.setFocus()
        self._start_pdf_metadata_scan()

    def eventFilter(self, watched, event):
        if (
            watched is self._list.viewport()
            and event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
        ):
            try:
                position = event.position().toPoint()
            except AttributeError:
                position = event.pos()
            item = self._list.itemAt(position)
            if item is not None:
                self._accept_item(item)
                return True
        if (
            watched in (self._search, self._tag_search)
            and event.type() == QEvent.Type.KeyPress
        ):
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self._list.count():
                self._list.setFocus()
                return True
        return super().eventFilter(watched, event)

    def _update_duplicate_filter_state(self) -> None:
        self._duplicate_matches = _bookshelf_duplicate_matches(self._entries)
        has_duplicates = bool(self._duplicate_matches)
        self._duplicates_only_cb.setEnabled(has_duplicates)
        self._duplicates_only_cb.setToolTip(
            t("reader_bookshelf_duplicates_hint")
            if has_duplicates
            else t(
                "reader_bookshelf_duplicates_scanning_hint"
                if self._metadata_scan_pending
                else "reader_bookshelf_no_duplicates_hint"
            )
        )
        if not has_duplicates and self._duplicates_only_cb.isChecked():
            self._duplicates_only_cb.setChecked(False)

    def _duplicates_filter_changed(self, *_args) -> None:
        self._refresh()
        if self._duplicates_only_cb.isChecked():
            self._start_duplicate_attachment_scan()

    def _start_duplicate_attachment_scan(self) -> None:
        if (
            not self._duplicates_only_cb.isChecked()
            or self._attachment_scan_in_progress
        ):
            return
        candidate_card_ids = set(self._duplicate_matches)
        pending_entries = [
            entry
            for entry in self._entries
            if entry.card_id in candidate_card_ids
            and entry.card_id not in self._attachment_checked_card_ids
        ]
        if not pending_entries:
            return
        captured_profile = self._profile
        self._attachment_scan_in_progress = True
        self._attachment_scan_generation += 1
        generation = self._attachment_scan_generation
        checked_card_ids = {entry.card_id for entry in pending_entries}
        tooltip(t("reader_bookshelf_checking_duplicate_attachments"), parent=self)

        def inspect(col) -> dict[int, int]:
            return _bookshelf_attachment_counts(
                self._addon_dir,
                captured_profile,
                pending_entries,
                col=col,
            )

        def checked(counts: dict[int, int]) -> None:
            if generation != self._attachment_scan_generation:
                return
            self._attachment_scan_in_progress = False
            if self._pdf_metadata_cancelled.is_set():
                return
            try:
                if str(_active_profile() or "") != captured_profile:
                    return
                self._attachment_checked_card_ids.update(checked_card_ids)
                self._attachment_counts.update(
                    {
                        int(card_id): max(0, int(count or 0))
                        for card_id, count in dict(counts or {}).items()
                    }
                )
                if self._duplicates_only_cb.isChecked():
                    self._refresh()
                    self._start_duplicate_attachment_scan()
            except (AttributeError, RuntimeError, TypeError, ValueError):
                return

        def failed(_error: Exception) -> None:
            if generation != self._attachment_scan_generation:
                return
            self._attachment_scan_in_progress = False
            if self._pdf_metadata_cancelled.is_set():
                return
            try:
                tooltip(
                    t("reader_bookshelf_duplicate_attachment_check_failed"),
                    parent=self,
                )
            except RuntimeError:
                return

        from aqt.operations import QueryOp

        try:
            QueryOp(
                parent=self,
                op=inspect,
                success=checked,
            ).failure(failed).run_in_background()
        except Exception:
            failed(RuntimeError("duplicate attachment check could not start"))

    def _start_pdf_metadata_scan(self) -> None:
        if not self._metadata_scan_pending:
            return
        taskman = getattr(mw, "taskman", None)
        if taskman is None or not hasattr(taskman, "run_in_background"):
            self._metadata_scan_pending = False
            self._update_duplicate_filter_state()
            return

        snapshot = list(self._entries)
        captured_profile = self._profile

        def scan() -> dict[int, str]:
            return _load_pdf_metadata_titles(
                snapshot,
                profile=captured_profile,
                cancelled=self._pdf_metadata_cancelled,
            )

        def finished(future) -> None:
            self._metadata_scan_pending = False
            if self._pdf_metadata_cancelled.is_set():
                return
            try:
                if str(_active_profile() or "") != captured_profile:
                    return
                titles = future.result()
                if titles:
                    self._entries = _with_pdf_metadata_titles(
                        self._entries,
                        titles,
                    )
                self._update_duplicate_filter_state()
                self._refresh()
                if self._duplicates_only_cb.isChecked():
                    self._start_duplicate_attachment_scan()
            except (AttributeError, RuntimeError):
                return
            except Exception:
                self._update_duplicate_filter_state()

        taskman.run_in_background(
            scan,
            finished,
            uses_collection=False,
        )

    def _current_kind(self) -> str:
        kind = self._kind_combo.currentData()
        return str(kind or _KIND_ALL).strip().upper()

    def _current_tag_mode(self) -> str:
        mode = self._tag_mode_combo.currentData()
        return (
            _TAG_MODE_AND
            if str(mode or "").strip().upper() == _TAG_MODE_AND
            else _TAG_MODE_OR
        )

    def _show_tag_suggestions(self) -> None:
        self._tag_search.setFocus()
        query = self._tag_search.text()
        cursor = self._tag_search.cursorPosition()
        start, _end = _bookshelf_tag_token_bounds(query, cursor)
        self._tag_completer.setCompletionPrefix(query[start:cursor])
        completion_model = self._tag_completer.completionModel()
        if completion_model.rowCount() <= 0:
            return
        popup = self._tag_completer.popup()
        popup.setCurrentIndex(completion_model.index(0, 0))
        self._tag_completer.complete()

    def _refresh(self, *_args) -> None:
        kind = self._current_kind()
        visible_entries = _filter_bookshelf_entries(
            self._entries,
            self._search.text(),
            kind,
            tag_query=self._tag_search.text(),
            tag_mode=self._current_tag_mode(),
            duplicates_only=self._duplicates_only_cb.isChecked(),
            duplicate_card_ids=set(self._duplicate_matches),
        )
        self._thumbnail_generation += 1
        generation = self._thumbnail_generation
        self._thumbnail_queue.clear()
        self._list.clear()

        placeholder = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        selected_item = None
        for entry in visible_entries:
            item = QListWidgetItem(entry.title)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
            )
            item.setForeground(QColor(self._caption_color))
            title_font = item.font()
            title_font.setBold(True)
            item.setFont(title_font)
            # QListView's icon mode can ignore gridSize() for the item's own
            # paint rectangle, which clips the text directly beneath tall
            # covers. An explicit size hint reserves a real caption area.
            item.setSizeHint(QSize(_TILE_WIDTH, _TILE_HEIGHT))
            priority_text = (
                t("reader_bookshelf_priority_value", value=int(round(entry.priority)))
                if entry.priority is not None
                else t("reader_bookshelf_priority_unset")
            )
            visible_tags = entry.tags[:20]
            tags_text = ", ".join(visible_tags) if visible_tags else t("reader_none")
            if len(entry.tags) > len(visible_tags):
                tags_text += " " + t("reader_bookshelf_more_tags", count=len(entry.tags) - len(visible_tags))
            item_tooltip = t(
                "reader_bookshelf_item_tooltip",
                title=entry.title,
                kind=entry.kind,
                tags=tags_text,
                priority=priority_text,
            )
            if entry.metadata_title:
                item_tooltip += "\n" + t(
                    "reader_bookshelf_pdf_metadata_title",
                    title=entry.metadata_title,
                )
            show_attachment_badge = _bookshelf_entry_has_attachment_badge(
                entry,
                duplicates_only=self._duplicates_only_cb.isChecked(),
                attachment_counts=self._attachment_counts,
            )
            if show_attachment_badge:
                item_tooltip += "\n" + tn(
                    "reader_bookshelf_attached_badge_tooltip",
                    self._attachment_counts.get(entry.card_id, 0),
                )
            item.setData(
                _ATTACHMENT_BADGE_ROLE,
                self._attachment_counts.get(entry.card_id, 0)
                if show_attachment_badge
                else 0,
            )
            item.setToolTip(item_tooltip)
            cache_key = (entry.kind, entry.card_id)
            cached = self._thumbnail_cache.get(cache_key)
            base_icon = cached or placeholder
            item.setIcon(base_icon)
            self._list.addItem(item)
            if cached is None:
                self._thumbnail_queue.append((item, entry))
            if entry.card_id == self._last_opened_card_id:
                selected_item = item

        self._count_label.setText(
            _bookshelf_count_text(self._entries, visible_entries, kind)
        )

        if selected_item is None and self._list.count():
            selected_item = self._list.item(0)
        if selected_item is not None:
            self._list.setCurrentItem(selected_item)
            self._list.scrollToItem(selected_item)
        self._update_option_availability()

        QTimer.singleShot(0, lambda current=generation: self._load_next_thumbnail(current))

    def _duplicates_for_entry(
        self,
        entry: _BookshelfEntry,
    ) -> tuple[_BookshelfEntry, ...]:
        return self._duplicate_matches.get(entry.card_id, ())

    def _show_context_menu(self, position) -> None:
        item = self._list.itemAt(position)
        entry = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if not isinstance(entry, _BookshelfEntry):
            return
        self._list.setCurrentItem(item)

        menu = QMenu(self)
        delete_action = menu.addAction(t("reader_bookshelf_delete_document"))
        qconnect(
            delete_action.triggered,
            lambda _checked=False, target=entry: self._confirm_delete_entries(
                [target]
            ),
        )

        duplicates = tuple(
            candidate
            for candidate in self._duplicates_for_entry(entry)
            if candidate.note_id != entry.note_id
        )
        if duplicates:
            delete_others_action = menu.addAction(
                t("reader_bookshelf_delete_other_duplicates")
            )
            qconnect(
                delete_others_action.triggered,
                lambda _checked=False, targets=duplicates: self._confirm_delete_entries(
                    list(targets),
                    keep_one=True,
                ),
            )

        menu.exec(self._list.viewport().mapToGlobal(position))

    def _confirm_delete_entries(
        self,
        entries: list[_BookshelfEntry],
        *,
        keep_one: bool = False,
    ) -> None:
        if self._delete_check_in_progress:
            tooltip(t("reader_bookshelf_attachment_check_busy"), parent=self)
            return
        note_ids = _bookshelf_note_ids(entries)
        if not note_ids:
            tooltip(t("reader_bookshelf_delete_unavailable"), parent=self)
            return
        captured_profile = self._profile
        self._delete_check_in_progress = True
        tooltip(t("reader_bookshelf_checking_attached_cards"), parent=self)

        def inspect(col) -> tuple[int, ...]:
            return _bookshelf_attached_card_ids(
                self._addon_dir,
                captured_profile,
                entries,
                col=col,
            )

        def checked(attached_card_ids: tuple[int, ...]) -> None:
            self._delete_check_in_progress = False
            if self._pdf_metadata_cancelled.is_set():
                return
            try:
                if str(_active_profile() or "") != captured_profile:
                    tooltip(
                        t("reader_bookshelf_delete_profile_changed"),
                        parent=self,
                    )
                    return
                confirmation = _bookshelf_delete_confirmation(
                    document_count=len(note_ids),
                    attached_card_count=len(attached_card_ids),
                    keep_one=keep_one,
                )
                if not askUser(confirmation, parent=self):
                    return

                from aqt.operations.note import remove_notes

                remove_notes(parent=self, note_ids=note_ids).success(
                    lambda _result, deleted=note_ids: self._after_entries_deleted(
                        deleted
                    )
                ).run_in_background()
            except RuntimeError:
                return

        def failed(_error: Exception) -> None:
            self._delete_check_in_progress = False
            if self._pdf_metadata_cancelled.is_set():
                return
            try:
                tooltip(
                    t("reader_bookshelf_attachment_check_failed"),
                    parent=self,
                )
            except RuntimeError:
                return

        from aqt.operations import QueryOp

        try:
            QueryOp(
                parent=self,
                op=inspect,
                success=checked,
            ).failure(failed).run_in_background()
        except Exception:
            failed(RuntimeError("attachment check could not start"))

    def _after_entries_deleted(self, note_ids: tuple[int, ...]) -> None:
        deleted = set(note_ids)
        deleted_card_ids = {
            entry.card_id for entry in self._entries if entry.note_id in deleted
        }
        self._entries = _without_bookshelf_notes(self._entries, note_ids)
        self._thumbnail_cache = {
            key: icon
            for key, icon in self._thumbnail_cache.items()
            if key[1] not in deleted_card_ids
        }
        self._attachment_checked_card_ids.difference_update(deleted_card_ids)
        for card_id in deleted_card_ids:
            self._attachment_counts.pop(card_id, None)
        try:
            self._update_duplicate_filter_state()
            self._refresh()
            tooltip(
                tn("reader_bookshelf_deleted_count", len(note_ids)),
                parent=self,
            )
        except RuntimeError:
            return

    def _load_next_thumbnail(self, generation: int) -> None:
        if generation != self._thumbnail_generation or not self.isVisible():
            return

        while self._thumbnail_queue:
            item, entry = self._thumbnail_queue.popleft()
            cover_path = _existing_media_preview_path(
                self._media_dir,
                entry.cover_filename,
            )
            if cover_path:
                pixmap = QPixmap(cover_path)
                if not pixmap.isNull():
                    self._set_thumbnail(item, entry, QIcon(pixmap), generation)
                    QTimer.singleShot(
                        0,
                        lambda current=generation: self._load_next_thumbnail(current),
                    )
                    return

            # EPUB imports already persist their extracted cover in Anki media.
            # Only PDFs have a safe, lightweight first-page fallback renderer.
            if entry.kind != _KIND_PDF:
                continue
            try:
                source_path = pdf_storage_abspath(
                    entry.source_filename,
                    profile=self._profile,
                )
            except Exception:
                source_path = ""
            if not source_path or not os.path.isfile(source_path):
                continue

            def render(path=source_path):
                return _render_pdf_first_page(path)

            def finished(future, current_item=item, current_entry=entry, current=generation):
                if current != self._thumbnail_generation or not self.isVisible():
                    return
                try:
                    image = future.result()
                except Exception:
                    image = None
                if image is not None:
                    self._set_thumbnail(
                        current_item,
                        current_entry,
                        QIcon(QPixmap.fromImage(image)),
                        current,
                    )
                QTimer.singleShot(
                    0,
                    lambda active=current: self._load_next_thumbnail(active),
                )

            taskman = getattr(mw, "taskman", None)
            if taskman is not None and hasattr(taskman, "run_in_background"):
                taskman.run_in_background(render, finished)
                return

            image = render()
            if image is not None:
                self._set_thumbnail(item, entry, QIcon(QPixmap.fromImage(image)), generation)

        # No preview is available for remaining placeholder entries.

    def _set_thumbnail(
        self,
        item: QListWidgetItem,
        entry: _BookshelfEntry,
        icon: QIcon,
        generation: int,
    ) -> None:
        if generation != self._thumbnail_generation:
            return
        current_entry = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(current_entry, _BookshelfEntry):
            return
        if (current_entry.kind, current_entry.card_id) != (
            entry.kind,
            entry.card_id,
        ):
            return
        self._thumbnail_cache[(entry.kind, entry.card_id)] = icon
        item.setIcon(icon)

    def _accept_item(self, item: QListWidgetItem) -> None:
        entry = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if isinstance(entry, _BookshelfEntry):
            self._list.setCurrentItem(item)
            self.accept()

    def _accept_current(self) -> None:
        item = self._list.currentItem()
        if item is not None:
            self._accept_item(item)

    def _selected_entry(self) -> _BookshelfEntry | None:
        item = self._list.currentItem()
        entry = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return entry if isinstance(entry, _BookshelfEntry) else None

    def _update_option_availability(self, *_args) -> None:
        entry = self._selected_entry()
        is_pdf = entry is not None and entry.kind == _KIND_PDF
        self._preserve_history_cb.setEnabled(is_pdf)
        self._preserve_history_cb.setToolTip(
            t("reader_bookshelf_preserve_history_hint")
            if is_pdf
            else t("reader_bookshelf_pdf_only_hint")
        )

    @property
    def selected_card_id(self) -> int | None:
        entry = self._selected_entry()
        return int(entry.card_id) if entry is not None else None

    @property
    def selected_card_type(self) -> str:
        entry = self._selected_entry()
        return str(entry.kind) if entry is not None else ""

    @property
    def preserve_history(self) -> bool:
        return bool(
            self.selected_card_type == _KIND_PDF
            and self._preserve_history_cb.isChecked()
        )

    @property
    def open_card_to_study(self) -> bool:
        return bool(self._study_card_cb.isChecked())
