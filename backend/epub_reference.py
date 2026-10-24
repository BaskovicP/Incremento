"""Read-only reference snapshots: no extraction, import, or reading-progress writes."""
import json
from pathlib import Path

try:
    from .paths import get_epub_dir, get_epub_extract_root
    from .epub_manager import _EPUB_SANITIZER_VERSION, _MAX_EPUB_METADATA_BYTES
    from .epub_connections import normalize_location
except ImportError:
    from paths import get_epub_dir, get_epub_extract_root
    from epub_manager import _EPUB_SANITIZER_VERSION, _MAX_EPUB_METADATA_BYTES
    from epub_connections import normalize_location


def resolve_epub_reference(addon_dir, profile, collection, card_id):
    if type(card_id) is not int or not 1 <= card_id <= 2**53 - 1:
        raise ValueError('Invalid EPUB card')
    try:
        note = collection.get_note(collection.get_card(card_id).nid)
    except Exception as error:
        raise ValueError('EPUB card unavailable') from error
    try:
        filename = str(note['EPUB_Filename'] or '').strip()
        title = str(note['Title'] or '').strip()
        root = get_epub_dir(addon_dir, profile).resolve()
        raw = filename.replace('\\', '/')
        if raw.startswith('user_files/') and '/epubs/' in raw:
            raw = raw.split('/epubs/', 1)[1]
        elif raw.startswith('epubs/'):
            raw = raw[6:]
        file = (root / raw).resolve()
        if not raw or not file.is_relative_to(root) or not file.is_file():
            raise ValueError('Managed EPUB unavailable')
        extracted_root = get_epub_extract_root(addon_dir, profile).resolve()
        extracted = (extracted_root / Path(filename).name).resolve()
        if not extracted.is_relative_to(extracted_root) or extracted == extracted_root:
            raise ValueError('Unsafe EPUB extraction directory')
        metadata = extracted / 'metadata.json'
        if metadata.is_symlink() or metadata.stat().st_size > _MAX_EPUB_METADATA_BYTES:
            raise ValueError('Unsafe EPUB metadata')
        with metadata.open(encoding='utf-8') as stream:
            data = json.load(stream)
        if data.get('sanitizer_version') != _EPUB_SANITIZER_VERSION:
            raise ValueError('Open the EPUB normally to update its sanitized copy')
        sections = data.get('sections')
        if not isinstance(sections, list) or not 1 <= len(sections) <= 100_000:
            raise ValueError('EPUB sections unavailable')
        paths = []
        for section in sections:
            href = section['href']
            if not isinstance(href, str) or not href or ':' in href or '\\' in href:
                raise ValueError('Unsafe EPUB section')
            path = (extracted / href).resolve()
            if not path.is_relative_to(extracted) or not path.is_file():
                raise ValueError('EPUB section unavailable')
            paths.append(str(path))
        return dict(card_id=card_id, filename=filename, title=title or file.stem,
                    root=str(extracted), paths=paths, sections=sections)
    except (OSError, KeyError, TypeError, AttributeError, json.JSONDecodeError) as error:
        raise ValueError('EPUB reference unavailable') from error


def validate_location(snapshot, location):
    location = normalize_location(location)
    if location['card_id'] != snapshot['card_id'] or location['section'] >= len(snapshot['sections']):
        raise ValueError('EPUB passage unavailable')
    return location


def location_allowed(location, status, *, page_index=None):
    """Reflowed page enforcement remains active in references and pickers."""
    maximum = status.get('allowed_max_page', status.get('allowed_max_section'))
    return not (status.get('enabled') and status.get('enforcement_mode') in ('soft_lock', 'hard_stop')
                and not status.get('override_enabled') and maximum is not None
                and (location['section'] if page_index is None else page_index) > maximum)
