# Incremento Agent Notes

Compact repo guide for coding agents. Keep this file high-signal and current.

## Repo Shape

- `__init__.py`: addon entry point, hook registration, settings save/load, reviewer patches, bridge startup.
- `backend/`: scheduling, persistence, content managers, profile-aware paths, search, recovery, statistics, and the authenticated browser bridge.
- `frontend/`: Qt dialogs/docks, editor integrations, reviewer overlays, and React source/tests for the PDF viewer.
- `chrome_extensions/incremento_companion/`: Manifest V3 source, tests, static entry pages, and committed runtime bundles for imports, capture, bookmarks, and playback sync.
- `web/`: shipped reader/player assets. `web/dist/pdf_viewer.js` is generated from `frontend/src/`; `web/pdfjs/` is vendored PDF.js runtime code.
- `tests/`: Python unit, integration, real-Anki subprocess, packaging, repair-harness, and selected UI regression coverage.
- `scripts/`: release packaging, guarded repair/eval/smoke tooling, and extension icon generation.
- `.github/workflows/verify.yml`: supported-Python CI, deterministic repair evals, dependency audit, frontend/extension tests, and generated-asset drift checks.
- `pyproject.toml`, `pytest.ini`: Python/tooling metadata and the default pytest coverage policy; focused commands may override `addopts`, but committed CI expectations remain authoritative.
- `.gitignore`: local/runtime/build exclusions. A path being ignored does not make it safe to package or inspect; packaging has its own explicit allowlist.
- `config.json`: shipped defaults only; runtime normalization and persistence belong to `backend/config_service.py`.
- `README.md`, `MANUAL.md`, `ARCHITECTURE.md`, `SECURITY.md`, `EXPORTING.md`: developer overview, user behavior, system boundaries, security policy, and backup/restore contract.
- `LICENSE`: distribution terms; keep it in release artifacts and do not rewrite or remove notices during dependency/vendor updates.
- `plan.drawio.xml`: design artifact only; it is not packaged runtime state.
- `user_files/`: runtime data only. All user data is per-profile.

Important newer hotspots:

- `backend/db_connection.py`, `backend/db_schema.py`, `backend/db.py`: per-thread/profile SQLite lifecycle, atomic schema ledger, legacy repository surface, and ordered migrations.
- `backend/operation_journal.py`, `backend/reconciliation.py`, `backend/migration.py`, `backend/note_metadata.py`: stable content identity, crash-safe cross-store imports, bounded profile-open recovery, explicit full reconciliation, and resumable legacy storage migration.
- `backend/config_service.py`, `config.json`: versioned config normalization and the canonical config read/write boundary.
- `backend/search_indexer.py`, `backend/search_repository.py`, `frontend/search_all.py`: cancellable off-main PDF indexing, optional FTS-backed bounded search, and the Search ALL read model.
- `backend/anki_compat.py`, `frontend/session_launcher.py`, `backend/session.py`: private Anki reviewer compatibility boundary and frontend-owned session launch UI.
- `backend/knowledge_tree.py`, `backend/knowledge_tree_postpone.py`, `frontend/knowledge_tree_dialog.py`: the knowledge-tree workspace, branch study, branch priority tools, postpone flow, and subset review.
- `backend/session.py`, `backend/scheduler_config.py`, `frontend/learn_dialog.py`: Incremento session construction, active-session auto-refill, and the scheduler dialog controls for card states and pending-window behavior.
- `backend/session_selection.py`, `backend/scheduler.py`, `backend/topic_scheduler.py`: session candidate filtering, tag-aware selection, refill preview behavior, and reader-card scheduler integration.
- `frontend/settings_dialog.py`, `config.json`, `__init__.py`: config-backed settings tabs, persisted defaults, and save/load wiring for extraction, review, topics, writing, shortcuts, and advanced tools.
- `backend/note_metadata.py`: shared Incremento provenance fields and helpers. New note-creation paths should use this instead of appending source/parent text into content fields.
- `frontend/add_card_dock.py`, `backend/reviewer_extract.py`, `frontend/extract_batch_dialog.py`: transfer-to-note flows, topic/item tag toggles, batch Q/A extraction, and reviewer-side extract plumbing.
- `frontend/pdf_dock.py`, `frontend/pdf_bookshelf.py`, `frontend/epub_dock.py`, `frontend/current_document_search_dialog.py`, `frontend/src/PdfViewer.jsx`: PDF and EPUB reader UX, the combined cover-based Document Bookshelf, in-document find, current-document search results, per-card scroll restore, and highlight-driven actions.
- `frontend/pdf_highlight_bulk_dialog.py`, `backend/notebook_citations.py`, `frontend/notebook_citation_import_dialog.py`: PDF highlight card creation, bulk highlight workflows, and Kindle notebook citation import into highlights.
- `backend/video_manager.py`, `frontend/video_dock.py`: video import, deferred local download, subtitle management, and local dual-caption playback.
- `backend/media_review.py`, `frontend/media_review_dialog.py`, `frontend/pdf_dock.py`, `frontend/epub_dock.py`, `frontend/video_dock.py`: media-linked card discovery, Topic/Item and scope filtering, position-aware Review All ordering/preview, filtered review launch, and reader-position restore.
- `backend/answer_schedule.py`, `backend/custom_schedule.py`, `frontend/custom_schedule_dialog.py`: shared atomic post-answer interval overrides, browser-side custom scheduling rules, and their dialog/workflow.
- `frontend/reviewer_priority_badge.py`: reviewer overlay that shows priority, topic A-factor, saved browser time, and active custom schedule at a glance.
- `frontend/writing_dock.py`: markdown writing dock with per-card editor state, word-progress counters, and configurable word-count mode.
- `backend/statistics.py`, `frontend/stats_dialog.py`, `frontend/timer_widget.py`, `backend/review_time_tracker.py`: normalized count/time aggregates, transactional daily trend history, unique PDF/EPUB page activity, review-time attribution, and logical-day graphs/focus-timer totals.
- `frontend/database_entries_dialog.py`: database-backed reader entry inspection surfaced from the learning dialog.
- `frontend/browser_quick_tags.py`, `frontend/tag_colors.py`, `backend/reviewer_tags.py`, `backend/db.py`: Browser quick-tag sets, stable per-tag color chips, recent-set inference, and profile-scoped tag-set history.
- `chrome_extensions/incremento_companion/src/`: browser snapshot quick-create, context-menu sync, and extension-side capture model behavior. Keep built `dist/` output aligned with source changes.

## Read The Local Guide

- If you work in `backend/`, read `backend/AGENTS.md`.
- If you work in `frontend/`, read `frontend/AGENTS.md`.
- If you work in `chrome_extensions/incremento_companion/`, read `chrome_extensions/incremento_companion/AGENTS.md`.
- If you work in `scripts/`, read `scripts/AGENTS.md`.
- If you work in `web/` or change a generated/shipped browser asset, read `web/AGENTS.md` plus the frontend or extension guide that owns its source.
- Before changing behavior, fixing a bug, or creating, changing, or reviewing tests, read `tests/AGENTS.md` and apply its 20 Test-Authoring Rules. Do this before editing implementation code so the TDD loop can start with a meaningful failing test.

## Sources of Truth

- `__init__.py` is the composition root. It may register hooks, menus, reviewer patches, profile lifecycle callbacks, and frontend/backend adapters; reusable rules and persistence do not belong there.
- Anki owns cards, notes, decks, tags, scheduling, revlog, sync, and Undo/Redo. Incremento SQLite owns only supplemental state described in `ARCHITECTURE.md`.
- `backend/paths.py` owns every path below `user_files/<profile>/`; `backend/db_schema.py` plus ordered migrations in `backend/db.py` own SQLite shape.
- `backend/config_service.py` owns shipped Python config normalization. `config.json` supplies defaults, `frontend/settings_dialog.py` owns widgets, and `__init__.py` wires accepted values.
- `backend/note_type_updates.py` owns note-type specifications and consent-gated updates. Startup inspection is read-only.
- `frontend/src/` owns the PDF viewer; `web/dist/pdf_viewer.js` is committed generated output. `frontend/vite.extension.config.js` maps extension entry points under `chrome_extensions/incremento_companion/src/` to committed `dist/` bundles.
- Root/static extension HTML and CSS are hand-maintained. Do not hand-edit generated bundles to create source changes, and do not edit vendored `web/pdfjs/*.min.js` except as an intentional dependency upgrade.
- `scripts/package_addon.py` defines the release allowlist/exclusions and generated Anki manifest. Local `meta.json`, the repository-level release `dist/`, caches, tests, `AGENTS.md`, development manifests, and all `user_files/` are not normal package inputs; committed web/extension runtime bundles are included only through their explicit package paths.

## Change Routing

| Change | Keep aligned |
|---|---|
| Config-backed behavior | `config.json`, `backend/config_service.py`, consumer helper, `frontend/settings_dialog.py`, `__init__.py`, `tests/test_settings_dialog.py`, `MANUAL.md` |
| SQLite schema/state | `backend/db_schema.py`, ordered migration/repository code in `backend/db.py`, rollback tests, diagnostics/schema expectations, `ARCHITECTURE.md` when ownership changes |
| Imported content or note type | content manager, `ImportOperation`, provenance helpers, note-type inspection/consent UI, path-containment and rollback tests |
| PDF viewer behavior | Python dock/bridge, relevant `frontend/src/` module, Node tests, `web/dist/pdf_viewer.js`, Python regressions, manual wording |
| Extension behavior | `chrome_extensions/incremento_companion/src/`, matching model/runtime tests, extension `manifest.json` only if permissions/entry points change, regenerated extension `dist/`, extension README when user-facing |
| Reviewer scheduling | pre-answer choice, `backend/answer_schedule.py`, post-answer state/history, Undo/Redo reconciliation, reviewer UI/badge, real-Anki lifecycle tests |
| Profile/background workflow | captured profile, operation-provided collection, stale-callback guard, per-profile paths/DB, cancellation and profile-switch tests |
| Packaging/release | `scripts/package_addon.py`, `tests/test_package_addon.py`, README release commands, CI generated-asset expectations |
| Repair automation | `scripts/repair_pipeline.py` and adapters, `SECURITY.md`, repair tests/eval corpus; never relax protected paths or human-review-only output implicitly |
| User-visible behavior | `MANUAL.md` and, where installation/development or extension behavior changes, the relevant README |

## Known Hardening Work

- The companion manifest has broad host/API permissions, browser-side PDF fetch currently buffers without a local limit and trusts a `.pdf` suffix too much, and full-page/screenshot capture can allocate data before the backend body limit rejects it. See the extension guide; do not describe these as already fixed.
- Browser **Incremento Database Entries** inspection is read-only but currently performs a synchronous, uncapped selected-card/table scan. Keep it an explicit maintenance action until it gains budgets, background execution, cancellation, and stale-profile handling.
- A few older backend adapters still access `aqt.mw` directly. Treat them as staged compatibility seams; new work should pass profile/collection explicitly and keep Qt interaction in root/frontend adapters.

## Per-Profile Data Isolation

All runtime data lives under `user_files/<ProfileName>/`, not flat in `user_files/`.

```text
user_files/
└── MyProfile/
    ├── incremento.db
    ├── db_checkpoints/
    ├── custom_learn_stats.json
    ├── pdfs/
    ├── epubs/
    ├── epub_extracted/
    ├── videos/
    ├── writing/
    ├── writing_backups/
    ├── files/
    ├── diagnostics/
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
- Treat Anki's collection as canonical for cards, notes, decks, scheduling, revlog, and Undo/Redo. SQLite stores only Incremento-owned supplemental state.
- Repair automation produces review artifacts outside the repository. It must never apply, commit, push, publish, deploy, or merge a candidate automatically.
- Never commit or package local `meta.json`, caches, dependency trees, temporary databases/WAL files, generated repair artifacts, or anything below `user_files/`.

## Cross-Cutting Rules

- Preserve profile-aware error paths so users can locate files under `user_files/<profile>/...`.
- All shipped Python config reads/writes go through `backend/config_service.py`; preserve unknown forward-compatible keys and the legacy scheduler-preset alias.
- New SQLite schema changes require a monotonic `backend/db_schema.py` migration and rollback regression. Do not add startup-time unversioned DDL.
- External-content creation must use `ImportOperation` and journal profile-relative paths before creating them. Stable content identity is canonical in Incremento SQLite; `Incremento_Content_ID` is optional legacy metadata and must never be auto-added to an Anki note type. Recovery may use the existing provenance source link. Never delete untracked files during automatic reconciliation.
- Profile-open recovery must inspect only pending import-journal rows and their exact card/provenance identities. Never enumerate the full Anki collection or scan large Incremento index/history tables from a profile-open hook; full stale-row reconciliation is an explicit maintenance operation because it serializes with session CollectionOps.
- Existing Anki note types must never be changed automatically at startup or from a background import. Detect changes through `backend/note_type_updates.py`, explain the full-sync consequence in `frontend/note_type_update_dialog.py`, and require explicit user consent before applying them.
- Background work captures the profile at launch, passes it through storage helpers, and drops UI callbacks after a profile switch.
- Private reviewer/V3 APIs belong in `backend/anki_compat.py`. An unavailable capability must fail closed without modifying the selected cards.
- Avoid touching `user_files/` unless the task is explicitly about migration or cleanup.
- When moving shipped assets, update both source references and generated or runtime references.
- If you change PDF viewer React source or extension source, rebuild before finishing.
- Keep provenance in dedicated `Incremento_*` note fields. Do not reintroduce inline `Source:` / parent blocks into the main content field for new notes.
- Reader search and find features span both Python docks and the shipped PDF viewer bundle. Keep `frontend/pdf_dock.py`, `frontend/epub_dock.py`, `frontend/current_document_search_dialog.py`, `frontend/src/PdfViewer.jsx`, and `web/dist/pdf_viewer.js` aligned when changing document search UX.
- PDF and EPUB reader links are explicitly opt-in and default off. Internal links stay inside the current document; external links must pass the shared uncredentialed HTTP(S)-only validator and open in the system browser, never inside either web view. Keep PDF annotation hit targets, the EPUB sanitizer/version, nonce-and-current-card bridge checks, local extraction-root containment, reading limits, and toolbar state aligned.
- The Document Bookshelf opens both PDF and EPUB cards. Keep its `Option+Shift+P` / `Alt+Shift+P` default and legacy shortcut migration, menu/settings labels, All/PDF/EPUB and title filters, exact case-insensitive tag OR/AND filtering, frequency-ranked contains autocomplete, active-token-only completion, PDF first-page and EPUB cover metadata, suspended-card visibility, PDF-only background fallback rendering, direct type-correct reader path, and reading-position restoration aligned.
- PDF highlight workflows now include single-highlight actions, bulk card creation, and Kindle citation import. Preserve highlight metadata, selection context, and per-profile document references across those paths.
- Session refill must preserve the distinction between the original selected id pool and Anki's live filtered-deck queue. Refill only the missing pending amount and do not duplicate cards already present.
- Keep session selection read-only and non-modal through `QueryOp`. The bounded initial session-deck mutation also uses the serialized no-progress `QueryOp` path plus `on_op_finished`, because even a millisecond `CollectionOp` creates an application-modal progress window that can strand macOS input during reviewer activation. Larger refill and explicit-review mutations remain `CollectionOp` operations.
- Session auto-refill uses `session_card_count` as a live pending-window size after the deck starts. Keep the frontend label, scheduler config, backend refill behavior, and docs aligned when changing this flow.
- When changing config-backed settings, keep `config.json`, `frontend/settings_dialog.py`, `__init__.py`, `tests/test_settings_dialog.py`, and `MANUAL.md` aligned.
- Knowledge-tree nodes are card-backed. One tree node maps to one `card_id`, with at most one parent and any number of children.
- If a knowledge-tree action is exposed in multiple places such as toolbar, inspector, and context menu, keep those entry points aligned.
- Add-card extraction flows are shared between the persistent Add dialog, reviewer extraction, browser capture imports, and batch dialogs. Keep tag-toggle state, duplicate handling, and metadata/provenance behavior consistent across those entry points.
- Discarding an embedded Add Card draft must remove the now-closed AddCards child and its parent dock together, clear transient extract/provenance state, and let the next extract rebuild cleanly; never leave a blank dock shell or stale source context.
- Add-card extract tags have provenance: every `Cmd/Ctrl+1..4` transfer replaces only Incremento-owned source/topic tags with the current source's set. Carry that ownership across Anki's sticky-tag new-note and note-type transitions, preserve pre-existing/manual tags, and clear stale extract context when no current source card exists.
- Standalone notes created in either Anki's Add window or Incremento's Add Card dock expose a per-note priority control. Route editor bridge messages through their originating editor context, and apply the chosen priority to every card generated by the new note without overriding extraction priority.
- Writing-card editor state is per card and persisted in SQLite. Writing progress counters are also per card; `session` means the current open session for that writing card.
- Custom-schedule badges in the reviewer should appear only when a real rule exists for that card; missing rules must not fall back to the default preset text.
- Topic More/Same/Less are frequency choices and must all submit Anki Good. Resolve any custom schedule before one final topic write, update the post-answer card without `set_due_date()`, merge into Anki's Answer Card undo step, and reconcile topic state plus consumed one-time rules on Undo/Redo. Unseen topic cards seed from their positive Anki interval, and the lower of Incremento's topic maximum and the deck-preset maximum is the effective cap.
- Every review-time interval override, including non-topic custom schedules, must use `backend/answer_schedule.py` and merge into the existing Answer Card undo step. Capture the pre-answer revlog id, require a genuinely new answer revlog, keep tracking profile-scoped, and never infer Undo from arbitrary deleted history. Non-rescheduling filtered decks are Preview and must retain Anki's original schedule without Incremento history or one-time-rule consumption. Browser-side **Apply now** remains a separate manual scheduling operation. Keep custom-rule revisions monotonic through consumption and clearing via `custom_schedule_rule_versions`; never derive a recreated rule's revision only from the currently active row.
- `custom_learn_stats.json` stores normalized count scopes (`daily.counts`, `lifetime`) plus review-time scopes (`time.daily.seconds`, `time.lifetime`). Keep DB stats behavior as compatibility/fallback, not a second shape.
- EPUB is a concrete document and stat type. Preserve `pdf` and `epub` separately in scheduling, statistics, timer summaries, and UI labels instead of folding EPUB into PDF.
- Browser snapshot quick-create and context-menu behavior live partly in the Chrome extension source and partly in generated `dist/` files. If you touch the extension, update the built artifacts before finishing.
- Port `8766` uses bridge protocol 2: exact extension-origin binding, ephemeral handshake token, protocol/token headers, and request-size/concurrency limits. Extension bridge calls must use `chrome_extensions/incremento_companion/src/shared/bridgeAuth.js`.
- Privacy-safe support diagnostics live in `backend/diagnostics.py` and are exported through **Incremento → Export Support Bundle…**. Event names and fields must remain explicitly schema-whitelisted. Never add card/note content, raw IDs, deck/tag/profile names, user/media filenames, local paths, URLs, raw database rows, exception messages/tracebacks, or absolute activity timestamps. `record()` must remain a bounded, non-blocking enqueue; filesystem writes belong to the worker, dropped/write-failure counters belong in the bundle, and export must use the non-collection task executor and revalidate persisted events rather than copying logs verbatim. Keep session, topic-scheduler, and custom-scheduler callback registration in `__init__.py`; scheduling result events must describe the committed final interval and original topic choice, and the generic answer event must consume that in-memory final interval without adding a collection query.
- PDF, EPUB, and video Review All combines legacy source rows, canonical parent metadata, saved reader links, recent video children, and knowledge-tree descendants. Traverse from both the media card and every direct attachment, because an attached card may be a standalone knowledge-tree root; its children are nested links and inherit its media position. Keep Topic/Item, direct/nested, entire/up-to-current, due-only, limit, media-position ordering, live exclusion preview, background re-resolution/deck creation, and post-review reader restoration aligned across all three docks. These are rescheduling filtered decks: every answer remains a real Anki review. The dangerous include-other-filtered-decks choice is one-shot and defaults off; using it must leave an active reviewer first, empty each conflicting filtered deck through Anki's supported whole-deck API, return every card in those decks home, retain their deck definitions, and then build the requested Review All deck.
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
.venv/bin/python -m pytest -o addopts= tests/test_pdf_bookshelf.py tests/test_reader_links.py -q
```

Non-Python and release checks:

```bash
.venv/bin/python -m compileall -q __init__.py backend frontend scripts
npm --prefix frontend test
npm --prefix chrome_extensions/incremento_companion test
npm --prefix frontend run build
npm --prefix frontend run build:extension
.venv/bin/python scripts/llm_repair_eval.py tests/repair_cases --deterministic-only --json
.venv/bin/python scripts/package_addon.py --release --clean-staging
```

Run only checks required by the change during development, but release work must use the complete packaging gate. After either build, inspect `git diff` and commit the generated asset with its source change.

If the local environment lacks `pytest-cov` but `pytest.ini` expects it, use:

```bash
.venv/bin/python -m pytest -o addopts= tests/test_add_card_dock.py -q
```
