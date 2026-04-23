# Backend Agent Notes

Use this file for work in `backend/`.

## Ownership

- Scheduling, persistence, browser bridge, content managers, profile-aware file handling, and migration logic live here.
- Knowledge-tree persistence, branch postpone logic, note provenance helpers, and video media/subtitle management also live here.

## Profile and Path Rules

- Functions that touch profile data must receive `profile` after `addon_dir`.
- Examples: `db.get_connection(addon_dir, profile)`, DB helpers such as `get_*` and `set_*`, `statistics.load_stats(addon_dir, profile)`, `priority_manager.set_priority(addon_dir, profile, card_id, priority)`, and media path helpers such as `video_manager.local_video_abspath(addon_dir, profile, relpath)`.
- Keep `backend/paths.py` pure. Do not import Anki there.
- Use the preferred import pattern for `_active_profile` from `paths.py`.
- Keep `backend/migration.py` idempotent. It owns migration from legacy flat `user_files/` into per-profile layout.

## Note Metadata

- Shared provenance lives in `backend/note_metadata.py`.
- Canonical fields are:
  - `Incremento_Source_Type`
  - `Incremento_Source_Title`
  - `Incremento_Source_Link`
  - `Incremento_Source_Author`
  - `Incremento_Imported_At`
  - `Incremento_Parent`
  - `Incremento_Parent_Card_ID`
- New note-creation paths should call `ensure_incremento_metadata_fields()` and `apply_incremento_metadata()` instead of appending source or parent text into content fields.
- If a frontend field picker or editor should hide those fields, use `visible_field_names()` rather than duplicating field-name filtering logic.

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
- Browser-capture provenance now belongs in Incremento metadata fields. Do not reintroduce URL or source blocks into mapped content fields when the backend can write metadata separately.

## Knowledge Tree

- Main files: `backend/knowledge_tree.py`, `backend/knowledge_tree_postpone.py`, and the related tables in `backend/db.py`.
- Tree rows are card-backed, not note-backed:
  - one node = one `card_id`
  - one parent max
  - many children allowed
- Use `load_knowledge_tree_nodes()` when the caller needs enriched rows with card metadata. Use raw DB rows only when working on structure persistence.
- Branch-scoped study, subset review, and postpone features all work by resolving subtree card ids from the selected root.
- Child creation and other tree-driven note creation should preserve provenance through `build_incremento_metadata(...)`.
- If you change subtree behavior, cover both selection helpers and the caller that consumes them.

## Custom Scheduling

- Main files: `backend/custom_schedule.py` and the `custom_schedule_rules` table in `backend/db.py`.
- Browser-selected cards can get per-card custom scheduling rules such as `minimum_cadence`, `fixed_repeat`, and `one_time`.
- `format_custom_schedule_rule(None)` must stay empty. Missing rules must not render as the default preset in the reviewer badge.
- Topic cards may still keep their topic scheduler state; `fixed_repeat` also updates the stored topic interval so UI and due date stay aligned.

## Card and Media Rules

- Default target deck for bridge and extension imports is usually `Topics`.
- Card creators recreate the deck if it is missing.
- PDF, video, webpage, and writing imports use visible duplicate-title suffixes such as `Title [2]`; do not reintroduce zero-width duplicate markers.
- UUID-backed saved filenames keep a short sanitized stem first, then the UUID.
- The current stem cap is `80` characters across writing, PDF, EPUB, video, and browser-capture media helpers.
- Some `.pdf` URLs return HTML challenge pages to Python; extension-side PDF fetch is the correct fallback there.

## Writing Cards

- Writing editor state lives in `writing_progress`; writing word baselines/totals live in `writing_word_stats`.
- Writing stats are per card, not global. Daily stats are baseline-based; session stats are runtime-only and reset when the card is reopened.
- Keep logical-date handling local/profile-safe when changing writing stats. Do not derive progress from file history snapshots.

## Video Cards

- Main backend file: `backend/video_manager.py`.
- `ensure_video_note_type()` now owns both local-video and subtitle fields. Reuse it instead of adding video fields ad hoc.
- Use `get_video_note_media()` and `update_video_note_media()` for note-field reads and writes rather than poking subtitle fields by hand.
- Managed subtitle files live under the profile `videos/` area beside local video assets.
- Deferred local download should reuse the existing download/compression pipeline; do not create a second downloader path.
- Dual-caption playback is currently a local-playback feature. Backend subtitle acquisition should not assume remote providers can host the overlay reliably.

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
.venv/bin/python -m pytest -o addopts= tests/test_knowledge_tree.py tests/test_knowledge_tree_postpone.py tests/test_db.py tests/test_session_selection.py -q
.venv/bin/python -m pytest -o addopts= tests/test_note_metadata.py -q
.venv/bin/python -m pytest -o addopts= tests/test_custom_schedule.py tests/test_db.py -q
```
