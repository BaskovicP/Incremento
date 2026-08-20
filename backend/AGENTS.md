# Backend Agent Notes

Use this file for work in `backend/`.

## Ownership

- Scheduling, persistence, browser bridge, content managers, statistics, profile-aware file handling, and migration logic live here.
- Knowledge-tree persistence, branch postpone logic, note provenance helpers, and video media/subtitle management also live here.
- Active Incremento session lifecycle also lives here, especially `backend/session.py` and `backend/scheduler_config.py`.

## Config-Backed Behavior

- Many backend modules expose `configured_*` helpers consumed by `frontend/settings_dialog.py` and `__init__.py`.
- If you change config semantics, keep the helper's fallback behavior backward-compatible for missing keys and older config shapes where practical.
- Changes to config-backed behavior usually require aligned updates in `config.json`, `frontend/settings_dialog.py`, `__init__.py`, `tests/test_settings_dialog.py`, and `MANUAL.md`.

## Session Scheduling

- Main files: `backend/session.py`, `backend/session_selection.py`, and `backend/scheduler_config.py`.
- `include_new`, `include_learning`, and `include_due` define which Anki card states are even eligible for a session build or refill. If all three are off, the normal topic/item search must match nothing; document/media pools remain intentionally state-independent.
- `auto_refill_session` means the active filtered deck should stay topped up to `session_card_count` pending cards after review answers shrink Anki's live queue below that threshold.
- Preserve the distinction between the original selected id pool and Anki's current live queue; refill should add only the missing amount and must not duplicate cards already present in the filtered deck.
- If you change refill behavior, keep `frontend/learn_dialog.py` labels/tooltips and the manual wording aligned with the backend semantics.
- The Docs/Other slider is stored as its left-to-right UI position, so backend `pdf_rate` is `1 - pdf_slider / 100`. A stored value of 100 means 0% Docs.
- A scheduler weight of 0 disables that bucket completely; smoothing/epsilon applies only to positive-weight buckets. Forced card types in strict phases must not fall back and consume another type's quota.
- `SessionPicker` caches raw Anki candidate pools and their priority order for the active session, including later auto-refills. A failed deck rebuild must rewind priority cursors without discarding the immutable order. Keep exhaustion retries bounded independently of a 9,999-card request. Large filtered decks use one comma-separated `cid:` search and batch their order updates.

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

## Browser Quick Tag History

- `browser_recent_tag_groups` stores up to nine complete Browser quick-tag sets per profile; it is separate from the reviewer-side single-tag history.
- Use `get_recent_browser_tag_groups()` and `touch_recent_browser_tag_group()` instead of reading or writing the table directly.
- Tag-set identity is case-insensitive and independent of tag order, while the stored display spelling/order is preserved for the picker.
- Reusing a stored set updates its display spelling without changing `used_at`, so its number remains stable. `seed_recent_browser_tag_groups()` fills empty positions below existing sets; a newly introduced tag set may be inserted at the front.
- `backend/reviewer_tags.py` owns tag-set normalization and deduplication, including the first-use conversion of newest-first Anki note-tag rows into recent sets.
- `browser_tag_colors` assigns each normalized tag a unique persistent color index plus an optional `custom_color` per profile. Use `assign_browser_tag_color_indexes()`, `get_browser_tag_custom_colors()`, and `set_browser_tag_custom_color()`; do not derive or overwrite assignments directly from dialog positions. The `topic` reservation may relocate the previous green-slot occupant without creating an index collision.
- `browser_quick_tag_settings` stores the profile's automatic-recent versus user-fixed mode and nine fixed tag-set slots. Use `get_browser_quick_tag_settings()` and `set_browser_quick_tag_settings()`; normalize each slot while preserving its position.

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

## Answer Overrides and Custom Scheduling

- Main files: `backend/answer_schedule.py`, `backend/custom_schedule.py`, and the custom-schedule tables in `backend/db.py`.
- Browser-selected cards can get per-card custom scheduling rules such as `minimum_cadence`, `fixed_repeat`, and `one_time`.
- Default custom-schedule mode and preset parsing are config-backed and surfaced in the `Review` settings tab.
- Calendar-month rules are measured from Anki's logical scheduler date, not the operating-system date, so reviews between midnight and Anki's rollover do not land a day early.
- `format_custom_schedule_rule(None)` must stay empty. Missing rules must not render as the default preset in the reviewer badge.
- Topic answers resolve custom-rule precedence inside `topic_scheduler` before anything is written. `fixed_repeat` and `one_time` replace the A-factor interval; `minimum_cadence` uses the earlier of the two intervals. The separate custom-schedule after-answer hook must skip topic answers.
- Review-time topic and non-topic interval overrides share `answer_schedule.apply_review_interval()`. Capture the latest revlog before answering, require a different positive revlog afterward, update the post-answer card, and merge into the existing Answer Card undo step. Do not call `set_due_date()` from an after-answer hook; it creates a manual revlog and a second undo operation. `apply_rule_now_to_card()` is intentionally still a manual Browser operation. A filtered deck with `resched = false` is Anki Preview: capture that state before answering, show no Incremento topic interval promise, and do not override the card, persist topic/custom review history, or consume a one-time rule.
- Track only revlogs created during the active profile session. Clear pending answers and trackers on profile close/open. Treat a missing revlog as Undo only when Anki exposes a redo action, and accept its reappearance as Redo only after that Undo was observed. When Anki clears the Redo stack without a revlog delta, retire all still-undone candidates so a later sync cannot impersonate Redo.
- One-time-rule consumption is stored transactionally in topic/custom review history. Rules have a monotonic `revision`; `custom_schedule_rule_versions` retains the last revision after the active rule is consumed or cleared and is backfilled from existing history. Undo must restore the exact consumed revision without overwriting a newer user-authored rule, and Redo may consume only that matching revision—even if an identical replacement was created before Undo.

## Topic Scheduling

- Topic `More / Same / Less` choices affect the immediate next interval as well as future A-factor growth. Starting from the normal `precise_interval × A-factor` result, `More` subtracts the configured `topic_more_adjustment_percent`, `Same` uses 100%, and `Less` adds `topic_less_adjustment_percent`; `More` and `Less` apply the same multiplier to the persistent A-factor. Both percentages default to 10% and are normalized to 0–100%.
- Topic choices are frequency preferences, not Anki memory grades. The pre-answer hook must retain `more` / `same` / `less` and submit Anki `Good` (ease 3) for all three in every card state. The post-answer hook consumes that choice for A-factor scheduling and records it in `topic_review_history`. Do not map topic choices back to Hard or Easy.
- Apply the final interval by updating the post-answer card directly and merging the update into Anki's Answer Card undo step. Do not use `set_due_date()` here: it adds a manual revlog and a second undo operation. Each history row stores exact before/after topic state. Undo/Redo must compare the live topic state with the transition side it expects before writing, so a newer manual/bulk edit made between or after answers wins instead of being overwritten.
- An unseen topic card starts from its positive pre-answer `card.ivl`; only genuinely new/learning cards fall back to one day. Clamp schedules to the lower of `topic_maximum_interval_days` and the card's deck-preset `rev.maxIvl`.
- Keep the duration labels, persisted precise interval, rounded Anki due date, and `card.ivl` synchronized when changing this behavior. Item `Fail / Pass` semantics are separate.

## Statistics and Document Types

- Main files: `backend/statistics.py`, `backend/db.py`, `backend/cards.py`, and `backend/review_time_tracker.py`.
- `StatsManager` owns transient `session` counts plus persisted `daily` and `lifetime` counts. Count blocks are always `{"type": {}, "tags": {}, "mode": {}}`.
- Review time is tracked separately as seconds. Time blocks are always `{"type": {}, "tags": {}}`; persisted scopes are `time.daily.seconds` and `time.lifetime`.
- `custom_learn_stats.json` is the canonical file-backed store. `load_stats()`, `save_stats()`, and `export_stats_json()` normalize bad values and internal keys before returning data.
- The DB `stats` table remains a backward-compatible fallback/export path. If the stats file exists, `export_stats_json()` should prefer the file and return the normalized shape.
- Use `StatsManager.record_time_only()` for reader or dock time that must not increment card counts. Runtime review-time mirrors should keep the same concrete type/tag attribution.
- `get_document_card_type()` returns concrete document types: `pdf` for `Incremento PDF`, `epub` for `Incremento EPUB`, and `None` otherwise. Do not collapse EPUB cards into PDF stats or scheduling results.

## Card and Media Rules

- Default target deck for bridge and extension imports is usually `Topics`.
- Card creators recreate the deck if it is missing.
- PDF, video, webpage, and writing imports use visible duplicate-title suffixes such as `Title [2]`; do not reintroduce zero-width duplicate markers.
- UUID-backed saved filenames keep a short sanitized stem first, then the UUID.
- The current stem cap is `80` characters across writing, PDF, EPUB, video, and browser-capture media helpers.
- Some `.pdf` URLs return HTML challenge pages to Python; extension-side PDF fetch is the correct fallback there.
- Local-file cards can either reference the original absolute path or store a managed copy under the active profile. Preserve that distinction when changing relink or storage behavior.

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
.venv/bin/python -m pytest -o addopts= tests/test_session.py tests/test_session_selection.py tests/test_learn_dialog.py -q
.venv/bin/python -m pytest -o addopts= tests/test_settings_dialog.py tests/test_custom_schedule.py -q
.venv/bin/python -m pytest -o addopts= tests/test_note_metadata.py -q
.venv/bin/python -m pytest -o addopts= tests/test_custom_schedule.py tests/test_db.py -q
```
