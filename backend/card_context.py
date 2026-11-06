"""Bounded, read-only context for the source card of an extract."""
from html import unescape
import re

try:
    from .annotation_notes import sanitize_note_html
    from .db import get_knowledge_tree_node
    from .note_metadata import INCREMENTO_PARENT_CARD_ID_FIELD, INCREMENTO_PARENT_FIELD, visible_field_names
except ImportError:
    from annotation_notes import sanitize_note_html
    from db import get_knowledge_tree_node
    from note_metadata import INCREMENTO_PARENT_CARD_ID_FIELD, INCREMENTO_PARENT_FIELD, visible_field_names


def _field(note, name):
    try:
        return str(note[name] or '')
    except (KeyError, TypeError):
        return ''


def _card_id(value):
    raw = str(value or '').strip()
    if raw.isascii() and raw.isdigit() and len(raw) <= 16 and 0 < int(raw) <= 2**53 - 1:
        return int(raw)
    return None


def _title(value):
    return ' '.join(unescape(re.sub(r'<[^>]*>', ' ', value[:4000])).split())[:240]


def load_parent_context(addon_dir, profile, collection, card_id):
    """Prefer the saved extraction origin; tree membership supplies older links.

    No ancestry/library scan, note-type update, or collection mutation is needed.
    Return only inert presentation data, never a live Anki note to a UI callback.
    """
    note = collection.get_card(card_id).note()
    parent_id = _card_id(_field(note, INCREMENTO_PARENT_CARD_ID_FIELD))
    if parent_id is None:
        row = get_knowledge_tree_node(addon_dir, profile, card_id)
        parent_id = _card_id(row['parent_card_id']) if row else None
    if parent_id is None or parent_id == card_id:
        return None
    result = dict(card_id=parent_id, title=_title(_field(note, INCREMENTO_PARENT_FIELD)),
                  available=False, fields=[])
    try:
        parent = collection.get_card(parent_id).note()
    except Exception:
        # Anki uses different missing-card exceptions across supported releases.
        return result
    remaining = 250_000
    for name in visible_field_names(list(parent.keys())[:80]):
        raw = _field(parent, name)[:min(65_536, remaining)]
        if not raw.strip():
            continue
        try:
            text, markup = sanitize_note_html(raw)
        except ValueError:
            # Excessive nesting cannot prevent the other fields from opening.
            continue
        if text or markup:
            markup = markup[:remaining]
            result['fields'].append((name[:120], markup))
            remaining -= len(markup)
        if remaining <= 0:
            break
    title_raw = _field(parent, 'Title') or next(iter(parent.fields), '')
    try:
        title_text, _markup = sanitize_note_html(str(title_raw)[:4000])
    except ValueError:
        title_text = ''
    result.update(title=' '.join(title_text.split())[:240] or result['title'], available=True)
    return result
