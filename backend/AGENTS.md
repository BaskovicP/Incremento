# Backend Agent Notes

Use this file for work in `backend/`.

## Ownership

- Scheduling, persistence, browser bridge, content managers, profile-aware file handling, and migration logic live here.

## Profile and Path Rules

- Functions that touch profile data must receive `profile` after `addon_dir`.
- Examples: `db.get_connection(addon_dir, profile)`, DB helpers such as `get_*` and `set_*`, `statistics.load_stats(addon_dir, profile)`, `priority_manager.set_priority(addon_dir, profile, card_id, priority)`, and media path helpers such as `video_manager.local_video_abspath(addon_dir, profile, relpath)`.
- Keep `backend/paths.py` pure. Do not import Anki there.
- Use the preferred import pattern for `_active_profile` from `paths.py`.
- Keep `backend/migration.py` idempotent. It owns migration from legacy flat `user_files/` into per-profile layout.

## Browser Bridge

- Main file: `backend/browser_bridge.py`.
- Main endpoint: `http://127.0.0.1:8766/incremento/add-content`.
- Browser-capture metadata endpoint: `http://127.0.0.1:8766/incremento/browser-capture-meta`.
- The bridge supports single-item imports, batch `items`, direct PDF bytes via `pdfBase64`, generic browser-capture note creation, writing imports in `selection` and `webpage_markdown` modes, and tracked web-card media progress updates.
- Field mappings include `titleField`, `selectedTextField`, `urlField`, and `snapshotField`.
- If `titleField` targets the note type's first field, write a unique snapshot label.
- Duplicate first-field failures must raise an explicit error instead of relying on Anki rejection.
- Stored browser-capture image filenames must stay sanitized and capped before the UUID suffix.
- Refresh the Anki UI after successful imports.

## Card and Media Rules

- Default target deck for bridge and extension imports is usually `Topics`.
- Card creators recreate the deck if it is missing.
- PDF, video, webpage, and writing imports use visible duplicate-title suffixes such as `Title [2]`; do not reintroduce zero-width duplicate markers.
- UUID-backed saved filenames keep a short sanitized stem first, then the UUID.
- The current stem cap is `80` characters across writing, PDF, EPUB, video, and browser-capture media helpers.
- Some `.pdf` URLs return HTML challenge pages to Python; extension-side PDF fetch is the correct fallback there.

## Web Cards

- Main backend file: `backend/web_manager.py`.
- Tracked `Incremento Web` cards persist the latest embedded-media resume state per card.
- If `prefer_web_card_resume_in_original_page` is enabled, resume should reopen the original page and ask the extension to seek there.
- Otherwise, resume should prefer a direct resumable media URL when one can be built.
- Avoid putting resume metadata in the server-facing query string; use the fragment-based Incremento marker instead.

## Backend Checks

- If you change browser import behavior, verify both bridge normalization tests and the extension runtime behavior.
- Useful focused suite:

```bash
.venv/bin/python -m pytest -o addopts= tests/test_browser_bridge.py tests/test_pdf_manager.py tests/test_video_web.py -q
```
