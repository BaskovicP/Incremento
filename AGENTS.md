# Incremento Agent Notes

Compact repo guide for coding agents. Keep this file high-signal and current.

## Repo Shape

- `__init__.py`: addon entry point, hook registration, settings save/load, reviewer patches, bridge startup.
- `backend/`: scheduling, persistence, import logic, profile-aware path helpers, browser bridge.
- `frontend/`: Qt dialogs/docks plus React source for the PDF viewer.
- `chrome_extensions/incremento_companion/`: Chrome extension for imports, browser capture, bookmark import, and playback sync.
- `web/`: shipped web assets exported by Anki.
- `tests/`: Python regression suite.
- `user_files/`: runtime data only. All user data is per-profile.

Important newer hotspots:

- `backend/knowledge_tree.py`, `backend/knowledge_tree_postpone.py`, `frontend/knowledge_tree_dialog.py`: the knowledge-tree workspace, branch study, branch priority tools, postpone flow, and subset review.
- `backend/session.py`, `backend/scheduler_config.py`, `frontend/learn_dialog.py`: Incremento session construction, active-session auto-refill, and the scheduler dialog controls for card states and pending-window behavior.
- `backend/session_selection.py`, `backend/scheduler.py`, `backend/topic_scheduler.py`: session candidate filtering, tag-aware selection, refill preview behavior, and reader-card scheduler integration.
- `frontend/settings_dialog.py`, `config.json`, `__init__.py`: config-backed settings tabs, persisted defaults, and save/load wiring for extraction, review, topics, writing, shortcuts, and advanced tools.
- `backend/note_metadata.py`: shared Incremento provenance fields and helpers. New note-creation paths should use this instead of appending source/parent text into content fields.
- `frontend/add_card_dock.py`, `backend/reviewer_extract.py`, `frontend/extract_batch_dialog.py`: transfer-to-note flows, topic/item tag toggles, batch Q/A extraction, and reviewer-side extract plumbing.
- `frontend/pdf_dock.py`, `frontend/epub_dock.py`, `frontend/current_document_search_dialog.py`, `frontend/src/PdfViewer.jsx`: PDF and EPUB reader UX, in-document find, current-document search results, per-card scroll restore, and highlight-driven actions.
- `frontend/pdf_highlight_bulk_dialog.py`, `backend/notebook_citations.py`, `frontend/notebook_citation_import_dialog.py`: PDF highlight card creation, bulk highlight workflows, and Kindle notebook citation import into highlights.
- `backend/video_manager.py`, `frontend/video_dock.py`: video import, deferred local download, subtitle management, and local dual-caption playback.
- `backend/media_review.py`, `frontend/media_review_dialog.py`, `frontend/pdf_dock.py`, `frontend/epub_dock.py`, `frontend/video_dock.py`: media-linked card discovery, Topic/Item and scope filtering, position-aware Review All ordering/preview, filtered review launch, and reader-position restore.
- `backend/answer_schedule.py`, `backend/custom_schedule.py`, `frontend/custom_schedule_dialog.py`: shared atomic post-answer interval overrides, browser-side custom scheduling rules, and their dialog/workflow.
- `frontend/reviewer_priority_badge.py`: reviewer overlay that shows priority, topic A-factor, saved browser time, and active custom schedule at a glance.
- `frontend/writing_dock.py`: markdown writing dock with per-card editor state, word-progress counters, and configurable word-count mode.
- `backend/statistics.py`, `frontend/stats_dialog.py`, `frontend/timer_widget.py`, `backend/review_time_tracker.py`: normalized count/time statistics, review-time attribution, and logical-day focus timer activity.
- `frontend/database_entries_dialog.py`: database-backed reader entry inspection surfaced from the learning dialog.
- `frontend/browser_quick_tags.py`, `frontend/tag_colors.py`, `backend/reviewer_tags.py`, `backend/db.py`: Browser quick-tag sets, stable per-tag color chips, recent-set inference, and profile-scoped tag-set history.
- `chrome_extensions/incremento_companion/src/`: browser snapshot quick-create, context-menu sync, and extension-side capture model behavior. Keep built `dist/` output aligned with source changes.

## Read The Local Guide

- If you work in `backend/`, read `backend/AGENTS.md`.
- If you work in `frontend/`, read `frontend/AGENTS.md`.
- If you work in `chrome_extensions/incremento_companion/`, read `chrome_extensions/incremento_companion/AGENTS.md`.
- If you work in `tests/`, read `tests/AGENTS.md`.

## Per-Profile Data Isolation

All runtime data lives under `user_files/<ProfileName>/`, not flat in `user_files/`.

```text
user_files/
└── MyProfile/
    ├── incremento.db
    ├── custom_learn_stats.json
    ├── pdfs/
    ├── epubs/
    ├── epub_extracted/
    ├── videos/
    ├── writing/
    ├── video_profile/
    └── web_profile/
```

Key modules:

- `backend/paths.py`: central path construction. Keep it pure; do not import Anki here.
- `backend/migration.py`: idempotent migration from legacy flat `user_files/` to `user_files/<profile>/`.

Preferred profile import pattern in backend modules:

```python
try:
    from .paths import get_active_profile as _active_profile
except ImportError:
    from paths import get_active_profile as _active_profile
```

Frontend modules that already import `_paths` should use `_paths.get_active_profile()`.

## Hard Boundaries

- Do not put shipped code or assets inside `user_files/`.
- Keep all runtime and user content per-profile.
- Shipped HTML, JS, and CSS belong under `web/`.
- Any helper that returns a path under `user_files/` must go through `backend/paths.py`.
- When adding functions that read or write under `user_files/`, thread `profile` from the call site instead of reaching for global state deep inside helper stacks.

## Cross-Cutting Rules

- Preserve profile-aware error paths so users can locate files under `user_files/<profile>/...`.
- Avoid touching `user_files/` unless the task is explicitly about migration or cleanup.
- When moving shipped assets, update both source references and generated or runtime references.
- If you change PDF viewer React source or extension source, rebuild before finishing.
- Keep provenance in dedicated `Incremento_*` note fields. Do not reintroduce inline `Source:` / parent blocks into the main content field for new notes.
- Reader search and find features span both Python docks and the shipped PDF viewer bundle. Keep `frontend/pdf_dock.py`, `frontend/epub_dock.py`, `frontend/current_document_search_dialog.py`, `frontend/src/PdfViewer.jsx`, and `web/dist/pdf_viewer.js` aligned when changing document search UX.
- PDF highlight workflows now include single-highlight actions, bulk card creation, and Kindle citation import. Preserve highlight metadata, selection context, and per-profile document references across those paths.
- Session refill must preserve the distinction between the original selected id pool and Anki's live filtered-deck queue. Refill only the missing pending amount and do not duplicate cards already present.
- Session auto-refill uses `session_card_count` as a live pending-window size after the deck starts. Keep the frontend label, scheduler config, backend refill behavior, and docs aligned when changing this flow.
- When changing config-backed settings, keep `config.json`, `frontend/settings_dialog.py`, `__init__.py`, `tests/test_settings_dialog.py`, and `MANUAL.md` aligned.
- Knowledge-tree nodes are card-backed. One tree node maps to one `card_id`, with at most one parent and any number of children.
- If a knowledge-tree action is exposed in multiple places such as toolbar, inspector, and context menu, keep those entry points aligned.
- Add-card extraction flows are shared between the persistent Add dialog, reviewer extraction, browser capture imports, and batch dialogs. Keep tag-toggle state, duplicate handling, and metadata/provenance behavior consistent across those entry points.
- Writing-card editor state is per card and persisted in SQLite. Writing progress counters are also per card; `session` means the current open session for that writing card.
- Custom-schedule badges in the reviewer should appear only when a real rule exists for that card; missing rules must not fall back to the default preset text.
- Topic More/Same/Less are frequency choices and must all submit Anki Good. Resolve any custom schedule before one final topic write, update the post-answer card without `set_due_date()`, merge into Anki's Answer Card undo step, and reconcile topic state plus consumed one-time rules on Undo/Redo. Unseen topic cards seed from their positive Anki interval, and the lower of Incremento's topic maximum and the deck-preset maximum is the effective cap.
- Every review-time interval override, including non-topic custom schedules, must use `backend/answer_schedule.py` and merge into the existing Answer Card undo step. Capture the pre-answer revlog id, require a genuinely new answer revlog, keep tracking profile-scoped, and never infer Undo from arbitrary deleted history. Non-rescheduling filtered decks are Preview and must retain Anki's original schedule without Incremento history or one-time-rule consumption. Browser-side **Apply now** remains a separate manual scheduling operation. Keep custom-rule revisions monotonic through consumption and clearing via `custom_schedule_rule_versions`; never derive a recreated rule's revision only from the currently active row.
- `custom_learn_stats.json` stores normalized count scopes (`daily.counts`, `lifetime`) plus review-time scopes (`time.daily.seconds`, `time.lifetime`). Keep DB stats behavior as compatibility/fallback, not a second shape.
- EPUB is a concrete document and stat type. Preserve `pdf` and `epub` separately in scheduling, statistics, timer summaries, and UI labels instead of folding EPUB into PDF.
- Browser snapshot quick-create and context-menu behavior live partly in the Chrome extension source and partly in generated `dist/` files. If you touch the extension, update the built artifacts before finishing.
- Privacy-safe support diagnostics live in `backend/diagnostics.py` and are exported through **Incremento → Export Support Bundle…**. Event names and fields must remain explicitly schema-whitelisted. Never add card/note content, raw IDs, deck/tag/profile names, user/media filenames, local paths, URLs, raw database rows, exception messages/tracebacks, or absolute activity timestamps. `record()` must remain a bounded, non-blocking enqueue; filesystem writes belong to the worker, dropped/write-failure counters belong in the bundle, and export must use the non-collection task executor and revalidate persisted events rather than copying logs verbatim. Keep session, topic-scheduler, and custom-scheduler callback registration in `__init__.py`; scheduling result events must describe the committed final interval and original topic choice, and the generic answer event must consume that in-memory final interval without adding a collection query.
- PDF, EPUB, and video Review All combines legacy source rows, canonical parent metadata, saved reader links, recent video children, and knowledge-tree descendants. Keep Topic/Item, direct/nested, entire/up-to-current, due-only, limit, media-position ordering, live exclusion preview, background re-resolution/deck creation, and post-review reader restoration aligned across all three docks. These are rescheduling filtered decks: every answer remains a real Anki review.
- Browser quick tags are a two-step flow: `Cmd+T` / `Ctrl+T`, then `1`–`9`, applies one complete tag set to every distinct selected note. Keep the nine stable numbered positions in a standard row-major 3×3 grid (`1/2/3` top, `4/5/6` middle, `7/8/9` bottom), first-use inference from recently modified tagged notes, profile-scoped `browser_recent_tag_groups` history, and Browser Notes-menu action aligned. Reusing an existing set must not reorder it; only a newest set that introduces a previously unseen tag may enter at the front.
- Quick-tag colors are case-insensitive, persistent, and collision-free within a profile. `topic` reserves the green major-color slot by default; users may override visible tag colors through the dialog's Settings button. The same tag must retain its accessible chip color across tag sets and sessions, while two different tags must not share a color. Keep the `browser_tag_colors` registry (including `custom_color` migration), allocator, settings dialog, and centralized palette in `frontend/tag_colors.py` aligned.
- Quick-tag Settings also supports profile-scoped fixed mode. When `Use my fixed tag sets` is enabled, the nine user-defined `browser_quick_tag_settings` slots replace recent-set inference completely and never reorder; keep fixed-set editing, color assignment for newly typed tags, validation, persistence, and immediate dialog reload aligned.

## Tests / Checks

Use `.venv/bin/python`.

Full suite:

```bash
.venv/bin/python -m pytest tests/ -q
```

Useful focused suites:

```bash
.venv/bin/python -m pytest -o addopts= tests/test_knowledge_tree.py tests/test_db.py tests/test_session_selection.py -q
.venv/bin/python -m pytest -o addopts= tests/test_session.py tests/test_learn_dialog.py tests/test_session_selection.py -q
.venv/bin/python -m pytest -o addopts= tests/test_settings_dialog.py tests/test_learn_dialog.py -q
.venv/bin/python -m pytest -o addopts= tests/test_pdf_dock.py tests/test_epub_dock.py tests/test_current_document_search_dialog.py -q
.venv/bin/python -m pytest -o addopts= tests/test_add_card_dock.py tests/test_extract_batch_dialog.py tests/test_reviewer_extract.py -q
.venv/bin/python -m pytest -o addopts= tests/test_note_metadata.py tests/test_browser_bridge.py tests/test_pdf_manager.py tests/test_video_web.py -q
.venv/bin/python -m pytest -o addopts= tests/test_reviewer_priority_badge.py tests/test_custom_schedule.py -q
.venv/bin/python -m pytest -o addopts= tests/test_db.py tests/test_writing_dock.py -q
.venv/bin/python -m pytest -o addopts= tests/test_reviewer_tags.py tests/test_tag_colors.py tests/test_db.py -q
```

If the local environment lacks `pytest-cov` but `pytest.ini` expects it, use:

```bash
.venv/bin/python -m pytest -o addopts= tests/test_add_card_dock.py -q
```
