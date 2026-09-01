# Frontend Agent Notes

Use this file for work in `frontend/`.

## Ownership

- Qt dialogs and docks live here, along with the React PDF viewer source in `frontend/src/`.
- The main knowledge-tree workspace, subset review window, branch postpone dialog, and reviewer priority badge also live here.
- The Start Incremental Learning dialog in `frontend/learn_dialog.py` also lives here, including session-size, card-state, and active-session auto-refill controls.
- The main settings surface lives in `frontend/settings_dialog.py`, but persistence wiring still goes through `__init__.py`.

## Frontend Module Map

- Document readers: `pdf_dock.py`, `pdf_dialog.py`, `pdf_quick_jump.py`, `pdf_bookshelf.py`, `epub_dock.py`, `epub_dialog.py`, `current_document_search_dialog.py`, `reader_links.py`, `bookmark_comment_dialog.py`, and `highlight_note_dialog.py`.
- Highlight/citation flows: `pdf_highlight_bulk_dialog.py` and `notebook_citation_import_dialog.py`.
- Other content docks and import dialogs: `local_file_dock.py`, `video_dock.py`, `web_dock.py`, `writing_dock.py`, `add_local_file_dialog.py`, `add_video_dialog.py`, `add_web_dialog.py`, `add_writing_dialog.py`, and `webpage_dialog.py`.
- Add/edit/reviewer integrations: `add_card_dock.py`, `extract_card_dialog.py`, `extract_batch_dialog.py`, `reviewer_extract_button.py`, `reviewer_focus.py`, `reviewer_shortcuts.py`, `reviewer_source_cover.py`, `reviewer_priority_badge.py`, and `reviewer_tag_dialog.py`.
- Browser/editor tools: `browser_priority_toolbar.py`, `browser_quick_tags.py`, `priority_dialog.py`, `quick_tag_shortcuts.py`, `tag_colors.py`, `tag_edit.py`, and `image_rotation.py`.
- Learning and scheduling dialogs: `learn_dialog.py`, `session_setup_model.py`, `session_launcher.py`, `custom_schedule_dialog.py`, `media_review_dialog.py`, and the four `knowledge_tree*_dialog.py` modules.
- Navigation and guidance: `command_palette.py`, `onboarding_dialog.py`, `reader_shell.py`, and `shortcut_conflicts.py`.
- Search, statistics, activity, and maintenance: `search_all.py`, `stats_dialog.py`, `activity_center.py`, `timer_widget.py`, `database_entries_dialog.py`, `sqlite_editor_dialog.py`, `settings_dialog.py`, and `note_type_update_dialog.py`.
- Platform/browser helpers: `file_shell.py`; keep command construction centralized here rather than scattering platform-specific shell calls.
- PDF viewer source: `src/main.jsx`, `src/PdfViewer.jsx`, `src/HighlightLayer.jsx`, `src/usePdfRender.js`, `src/pdfLinks.mjs`, `src/pdfLinkHistory.mjs`, and `src/pdfAnchorLocation.mjs`. Their focused Node tests live under `frontend/tests/`.
- PDF viewer pure tests: `tests/pdfLinks.test.mjs`, `tests/pdfLinkHistory.test.mjs`, and `tests/pdfAnchorLocation.test.mjs`; keep each beside the source contract it protects.
- Web toolchain: `package.json` declares React/Vite scripts and dependencies, `package-lock.json` pins them, `vite.config.js` builds the PDF viewer, and `vite.extension.config.js` builds the companion extension. Dependency or lockfile changes require `npm audit --audit-level=high` and both relevant tests/builds.

## Qt, Operations, and Lifecycle

- Never do document extraction, library scans, downloads, large collection queries, or filtered-deck builds on Qt's main thread. Use Anki's operation/task APIs appropriate to collection ownership.
- A worker captures the profile and immutable request values at launch, uses the operation-provided collection where applicable, and returns plain data. Create and mutate Qt objects only in the UI callback.
- Reject a result if the profile, current card, dialog generation, or request token no longer matches. Closing a dock/dialog or switching profile must make pending callbacks harmless.
- Use `QueryOp` for read-only collection work and the specifically documented no-progress initial session mutation. Use `CollectionOp` for ordinary collection mutations so Anki serializes changes and emits its normal operation hooks.
- Parent transient dialogs to the owning Anki window, make teardown idempotent, and avoid modal prompts from reviewer question/answer hooks. On macOS, a hidden native modal can strand input behind a raised dock.
- Signals, hooks, shortcuts, and monkey patches may be installed more than once during reloads; registration must be idempotent and disconnection must not remove another component's handler.
- `frontend/file_shell.py` opens/reveals validated local targets using argument lists. Never interpolate a user path into a shell command string.

## PDF Viewer

- Main Python loader: `frontend/pdf_dock.py`.
- Main React code: `frontend/src/`.
- Build output must land in `web/dist/pdf_viewer.js`.
- Imported PDFs are stored under `user_files/<profile>/pdfs/` and referenced by `PDF_Filename`. Do not confuse user PDFs with shipped viewer assets.
- `frontend/pdf_bookshelf.py` owns the PDF/EPUB Document Bookshelf. Its default shortcut is `Option+Shift+P` on macOS (`Alt+Shift+P` elsewhere); it includes suspended document cards, filters between All/PDF/EPUB and by title plus exact case-insensitive Anki tags with explicit OR/AND semantics, and offers contains-matching autocomplete plus a browse-all tag picker ranked by document frequency. Completion must replace only the active tag token so multi-tag queries remain intact. The shelf reserves an explicit wrapping caption area with a bold theme-aware title below every cover, loads stored PDF first-page and EPUB cover media progressively, and renders only missing PDF previews in the background without persisting them. Open through the shared `_open_pdf_card()` / `_open_epub_card()` paths; keep PDF-only preserve-history and both-format open-card-to-study behavior aligned with Quick Open Content.
- The PDF Review group exposes both due-nearby review and Review All. Review All opens the shared Topic/Item, scope, state, limit, and order picker, reviews linked cards in a dedicated filtered deck, then restores the PDF page/zoom/read state.
- PDF is the reference reader for primary action order and terminology. Apply `reader_shell.py` metadata after constructing PDF, EPUB, video, and web buttons; preserve Back, Search, Extract, Bookmark, Review All order where the layout supports it, and disable unsupported actions with an explicit reason. EPUB's Qt controls live below the document and consume `reader_toolbar_clone_spec("epub")` plus `reader_toolbar_action_text("epub")`: keep the exact four PDF groups (Navigation, Reading, Annotation & capture, Review & cards), literal PDF text/symbol icons, nested action order, all eight highlight colors, unlabelled progress meter, progress/limit state, page jump, count labels, customization dialog, and compact bar synchronized with the PDF reference. Expanded controls use the PDF's two deliberate rows—Navigation+Reading, then Annotation+Review—and each labelled subgroup remains horizontal; responsive wrapping occurs only between whole outer groups and every wrapped line stays centered. Keep Find centered inside the controls and place every retained legacy widget under a hidden parent; an unlaid dock child can cover native Close/Float controls. Scope outer-frame and progress-meter styles by object name so they cannot leak borders/backgrounds onto descendant labels or segments. EPUB Zoom maps to text scale and stable read progress maps to sections.
- Clickable links in both readers default off to preserve text selection. PDF link annotations render as opt-in hit targets; internal destinations use limit-aware page navigation and external targets cross the nonce/current-card bridge. Both PDF and EPUB place Jump Back directly beside Links, record a bounded stack of exact internal-link source locations, restore the latest page/section plus scroll ratio, and clear stale history when a different document starts. EPUB anchors cross the same kind of trusted bridge, resolve only to known sections within the active extraction root, and use Qt only for validated HTTP(S) external links. Both readers preserve WebEngine's standard context menu and append **Copy Link to This Place** only for a validated current-card document point. Clipboard anchors carry card-ready HTML, a plain-text fallback, and a validated private MIME marker; the editor hook must rebuild only that allow-listed anchor shape and paste it as trusted internal rich HTML because Anki's external sanitizer removes `onclick`. PDF anchors restore page/scroll without replacing saved reading progress, while EPUB anchors restore section/text offset with a bounded scroll fallback. Keep legacy link commands readable and never let either web view navigate remotely.
- `frontend/vite.config.js` controls where the shipped PDF viewer bundle is written. Keep it aligned with `web/pdf_dock.html`.
- `frontend/src/main.jsx` is the React entry point, `frontend/src/PdfViewer.jsx` owns the reader bridge/state, `frontend/src/HighlightLayer.jsx` owns highlight rendering/interactions, and `frontend/src/usePdfRender.js` owns the PDF.js render lifecycle. Keep pure anchor/link/history rules in the `.mjs` modules so Node tests can exercise them without a browser.

If you change PDF viewer React source:

```bash
npm --prefix frontend run build
```

Also run the source-level tests before accepting the generated bundle:

```bash
npm --prefix frontend test
```

## Import Dialogs and Content Docks

- `add_local_file_dialog.py`, `add_video_dialog.py`, `add_web_dialog.py`, and `add_writing_dialog.py` collect and validate user choices; backend managers own file/network side effects. Dialog acceptance must not leave a half-created note when a later step fails.
- `webpage_dialog.py` owns webpage-to-card choices, including snapshot/Markdown behavior. Treat the live page and extension payload as untrusted and pass raw provenance to backend metadata helpers rather than constructing inline source blocks.
- `local_file_dock.py` must preserve whether the card references an intentional original absolute path or a managed profile copy. Resolve managed copies through backend containment helpers, allow reference-mode paths to remain external by design, disable open/reveal for missing files, and route both actions through `file_shell.py`.
- `video_dock.py`, `web_dock.py`, and document docks own profile-scoped WebEngine state. Never share cookies/cache/profile instances across Anki profiles, and reset singleton references before a profile migration/open completes.
- `add_writing_dialog.py` and `writing_dock.py` operate on backend-owned atomic Markdown storage. UI autosave/error handling must never report success until the durable replace completes.

## Reader Links, Search, and Annotations

- `reader_links.py` is a security boundary, not just clipboard formatting. It validates the private Incremento marker and canonical document location, emits a narrowly allow-listed rich anchor plus plain fallback, and forces trusted rich paste only for that verified shape. Reject arbitrary clipboard HTML, scripts, stale-card markers, and non-document commands.
- `pdf_quick_jump.py` owns page-jump parsing/history UI; `current_document_search_dialog.py` owns bounded results for the open document. Keep page/section positions type-correct and never interpret user search text as bridge code.
- `bookmark_comment_dialog.py` enforces the backend comment limit and returns plain text. `highlight_note_dialog.py` edits supplemental highlight notes without changing the selected document range.
- `pdf_highlight_bulk_dialog.py` and `notebook_citation_import_dialog.py` preview before creating cards. Preserve per-row selection, source positions, active profile/document identity, rollback-safe import behavior, and dedicated provenance fields.
- WebEngine request interceptors and navigation handlers must fail closed. Reader content may use validated internal/local targets and normalized uncredentialed HTTP(S) external links only through the opt-in system-browser path; it must never navigate the reader view to remote content.

## Add Card and Note Editors

- Main file: `frontend/add_card_dock.py`.
- The dock embeds Anki's Add dialog persistently and injects transfer buttons for recent selections.
- When Anki closes the embedded Add dialog after a confirmed discard, retire the parent dock too and clear the abandoned extract options, provenance context, selection snapshot, and editor reference. A later extract must build a fresh dialog instead of leaving or reusing an empty shell.
- Register `T` and `I` toolbar buttons in both Add Card and edit-note editors.
- `T` toggles config-driven topic tags.
- `I` toggles config-driven item tags.
- Add-mode editors expose a `P` button and compact number field for standalone-note priority. The value is note-local, defaults to `50`, and is applied to every card generated by the new note. JS bridge handling must prefer the originating editor context when native and docked Add windows coexist; pending extraction priority remains separate.
- Existing-card editors expose a `P` button in both Browser and Edit Current contexts. Edit Current must resolve only the active reviewer card whose note matches the editor note and fail closed on stale or mismatched state.
- `Cmd/Ctrl+1..4` extraction refreshes only Incremento-owned automatic source/topic tags. Preserve unrelated and pre-existing user tags, carry automatic-tag ownership when Anki copies tags into the next blank note or across an Add note-type change, and release T/I classification tags from automatic ownership when the user explicitly toggles them.
- Tag button state must refresh on editor init, note load, and `editor_did_update_tags`.
- Edit-note toggles must refresh the visible tag widget immediately and may need a scheduled `editor.loadNote()` so the tag row visibly updates.
- Relevant config keys: `add_card_topic_tags`, `add_card_item_tags`, `extract_notetype`, `extract_source_links`.
- Generic note editors and field pickers should hide dedicated Incremento provenance fields. Reuse backend `visible_field_names()` behavior rather than duplicating a separate blocklist.
- `extract_card_dialog.py` owns single-card extraction choices; `extract_batch_dialog.py` owns multi-row Q/A creation. Keep duplicate handling, tag ownership, source metadata, field visibility, and note-type changes consistent with the persistent dock and reviewer extraction path.
- `reviewer_extract_button.py` and `reviewer_shortcuts.py` are thin UI adapters. Shared extraction behavior belongs in backend/frontend extraction helpers so toolbar and keyboard entry points cannot drift.

## Browser and Editor Utilities

- `browser_priority_toolbar.py` and `priority_dialog.py` route priority changes through `backend/priority_manager.py`; refresh the Browser after a successful collection operation and fail closed for stale selections.
- `tag_edit.py` centralizes safe note-tag mutations used by UI actions. Preserve Anki tag normalization and update each distinct selected note once.
- `reviewer_tag_dialog.py` is the reviewer-side tag chooser; it is separate from Browser quick-tag sets and must not write Browser history tables accidentally.
- `reviewer_source_cover.py` renders source media/cover context without making stored filenames or HTML trusted. Keep missing-media fallbacks and current-card checks.
- `image_rotation.py` rotates only selected local Anki media, writes a new media artifact, updates the originating editor, and leaves unsupported/remote references unchanged. Treat orientation and format errors as recoverable UI failures.

## Browser Quick Tags

- `frontend/browser_quick_tags.py` owns the Browser-local `Cmd+T` / `Ctrl+T` action and numbered recent-tag-set picker.
- The picker is intentionally a two-step workflow: open it, then press `1`–`9`, the matching `A`–`I` alternative, or click the corresponding row to apply the entire displayed tag set to every distinct selected note. Slot mappings are `1/A` through `9/I` and come from the pure `frontend/quick_tag_shortcuts.py` helper.
- Lay out the nine choices as a standard row-major 3×3 block: `1/2/3` across the top row, `4/5/6` across the middle, and `7/8/9` across the bottom.
- Each tag is rendered as an individual color chip inside its numbered row. Color identity is persistent and case-insensitive; reuse `frontend/tag_colors.py` plus the profile `browser_tag_colors` registry so the same tag never changes color and two different tags never share a color. `topic` is green automatically. The quick-tag dialog's Settings button opens `BrowserTagColorSettingsDialog`, where visible tag colors can be customized or restored to Automatic without permitting a duplicate effective color.
- `BrowserTagColorSettingsDialog` also owns `Use my fixed tag sets`. It exposes nine row-major slots, accepts one or more space/comma/semicolon-separated tags per slot, requires contiguous unique non-empty sets from slot 1, and reloads the picker after saving. Fixed mode bypasses recent-tag inference entirely.
- Keep chip text readable in both light and dark Anki themes, and preserve each numbered/lettered row as one accessible click target even though it contains multiple chip labels.
- Exact recent-set order is profile-scoped in `browser_recent_tag_groups`; collection-note inference supplies the initial nine choices before any quick-tag history exists. Number positions are muscle-memory stable: selecting an existing set does not promote it, and only the newest inferred set introducing a previously unseen tag may enter at the front.

## Writing Dock

- Main file: `frontend/writing_dock.py`.
- The dock remembers per-card cursor, scroll, zoom, wrap mode, focus mode, current-line highlight, and marker line.
- The bottom bar also shows per-card writing progress. Scope options are `Today`, `Session`, and `All-time`.
- `Session` means the current open session for that writing card, not the whole Anki run.
- Word counting mode is configurable from the `Writing` settings tab. `Word-like` is only an approximation of Microsoft Word behavior, not a byte-for-byte clone.

## Statistics and Timer UI

- Main files: `frontend/stats_dialog.py` and `frontend/timer_widget.py`.
- `StatsDialog` consumes normalized backend stats only. Keep summary cards, count charts, and review-time charts tolerant of missing or dirty data.
- Card-type display order and colors should keep EPUB distinct from PDF. Current labels include `PDFs` for `pdf` and `EPUBs` for `epub`.
- Tags beginning with `__` are synthetic/internal and must stay hidden from stats UI tag charts and summary choices.
- Review-time charts use `time.*.seconds` data and duration formatting. Keep counts and time separate so time-only reader tracking does not imply an answered card.
- The `7 Days` and `30 Days` scopes consume only `load_daily_history()` and display separate stacked daily series for Topics/Items/Other, PDF/EPUB pages, and study minutes. Keep summary totals, active days, streak, zero days, and active-day averages aligned with those series.
- The focus timer tracks answered cards plus unique PDF and EPUB pages even when the timer is not currently running. Starting a timer must not clear already collected activity.
- Timer completion resets only the per-report counters. The “Today so far” line comes from cumulative daily activity and resets on the scheduler logical date from `day_end_time`.

## Knowledge Tree Workspace

- Main files:
  - `frontend/knowledge_tree_dialog.py`
  - `frontend/knowledge_tree_priority_dialog.py`
  - `frontend/knowledge_tree_postpone_dialog.py`
  - `frontend/knowledge_tree_subset_dialog.py`
- The tree dialog is a split workspace: toolbar + tree + selected-node inspector.
- When you add or rename a selected-node action, keep toolbar, inspector, and context menu surfaces aligned unless the action is intentionally contextual.
- The tree can reopen against the current reviewer card via `select_card_id`; preserve that focus behavior when refactoring the dialog lifecycle.
- Branch operations such as study, priority, postpone, and subset review are subtree-scoped by default. The selected node itself is part of that subtree unless the UI says otherwise.

## Web and Video Docks

- Main files: `frontend/web_dock.py` and `frontend/video_dock.py`.
- `video_dock.py` and `web_dock.py` each maintain a per-profile Qt WebEngine profile singleton.
- Reset those singletons on profile switch before migration and `set_active_profile()`.
- The web dock toolbar is split into two rows to keep controls usable.
- The dock has both `Open in Window` and `Open in Window (Home)`.
- `Home` keeps navigation inside the dock; `Open in Window (Home)` opens the card's stored homepage externally.
- Show `Resume mm:ss` only when resume state exists for the current web card.
- Original-page resume should not depend on the live `Track via Chrome extension` checkbox being enabled at click time.
- `video_dock.py` now also owns deferred `Download Local Copy…`, caption management, and target/reference caption toggles.
- Dual captions currently render through the local HTML player wrapper, not provider-native remote playback. If remote playback cannot support a caption flow, guide the user toward local download instead of faking parity.
- The video dock's Review All action uses `frontend/media_review_dialog.py`, passes the current playback timestamp plus recent child positions, preserves playback and captions, and restores the source video after the linked-card review ends. Recent child ids/positions are transient and must be cleared by `reset_for_profile_switch()`.
- Keep per-profile `QWebEngineProfile` singletons reset-safe on profile switches for both web and video docks.

## Reviewer Behavior

- Reviewer patching is centralized in `__init__.py`, but frontend-visible button styling and behavior changes must stay aligned with it.
- Topic cards use `More / Same / Less`. They are Incremento frequency preferences, so all three submit Anki `Good` while Incremento separately retains the original choice. Never map `More` to Hard or `Less` to Easy. All three affect the interval being scheduled immediately. The Topics settings expose separate percentage strengths for `More` and `Less` (10% defaults), a maximum topic interval, and guidance to use a dedicated deck-options preset for FSRS isolation. The effective cap is the lower of that setting and Anki's deck-preset maximum.
- Topic cards can optionally show the red Postpone button.
- Item cards can optionally use `Fail / Pass`. Its semantics are fixed across new, learning/relearning, and review states: `Fail` always submits Anki `Again` (ease 1), while `Pass` always submits Anki `Good` (ease 3). Topic-card buttons and A-factor scheduling are separate.
- Topic review button styling is patched after `_showEaseButtons()`.
- Current topic styling keeps yellow unchanged and uses more muted red and blue tones.
- If you change reviewer button behavior, verify both scheduling logic and injected web styling.
- Reviewer glance metadata lives in `frontend/reviewer_priority_badge.py`. The badge shows priority for all cards and topic A-factor, saved browser time, and custom schedule when available. If you change priority or topic review flows, keep the reviewer badge refresh path in sync.
- Custom schedule text must only render when a real schedule exists for the current card; stale default text is a regression.
- Reader docks can steal keyboard focus while reviewer hooks open or raise them. Keep the final bounded, deferred focus recovery registered for both `reviewer_did_show_question` and `reviewer_did_show_answer` in `frontend/reviewer_focus.py` so Anki's Space, `1`–`4`, and editor shortcuts continue on every card. Never reclaim focus from a modal, popup, or separate active Anki window.
- PDF/EPUB question-shown hooks must open their reader with `offer_due_review_prompt=False`. Never start a modal due-card prompt during reviewer activation; on macOS it can hide behind the raised dock and leave the main window unable to accept clicks. The explicit Review Due / Review All controls remain the reviewer-safe entry points.

## Session Builder UI

- Main file: `frontend/learn_dialog.py`.
- The dialog supports named presets, optional live preview, and branch-scoped study launches from the knowledge tree. A successful **OK** must atomically persist the current dialog state and overwrite the selected named preset; `Current Settings` must not alter named presets. A stale required live preview still blocks both saving and launch.
- The always-present synthetic Other tag row is fixed at 100% and disabled when it is the only tag row. Adding a real tag restores normal slider balancing; removing the final real tag must immediately normalize Other back to 100%.
- The **Card types** checkboxes control whether `New`, `Learning`, and `Due / Review` cards are eligible for session selection at all.
- **Cards per session** and backend normalization share the inclusive 1–9,999 range. The Docs/Other slider stores 100 at its fully-right 0%-Docs endpoint; keep its UI direction and backend conversion aligned.
- The **Advanced** checkbox `Auto-refill session deck to keep this many pending cards` uses **Cards per session** as a live pending-window target after the session starts.
- Starting a session must not synchronously recount/classify cards in `accept()`. Backend session construction and filtered-deck rebuilding run as a background collection operation; an empty result is reported after that operation completes.
- PDF, EPUB, video, and web reading cards have additional scheduler flows layered on top of Anki state; when changing eligibility wording, verify the tooltip text still matches actual selection behavior.
- Basic/Advanced is a presentation switch over one session configuration. Basic edits the same preset, count, Topic/Item slider, and Document/Other slider used by Advanced, and its summary/preview must update immediately in both directions.
- Keep the checkbox label, tooltip, saved profile key `auto_refill_session`, and backend semantics in `backend/session.py` consistent. If the behavior changes, update `MANUAL.md` and session-related tests too.
- PDF, EPUB, and video Review All is separate from the normal session builder. Keep Topic/Item, direct/nested, entire/up-to-current, due-only, limit, position-order, preview, and unavailable-card wording aligned. Run the initial inspection with `QueryOp`, re-resolve and build with `CollectionOp`, and never scan or mutate a potentially large linked-card deck on Qt's main thread. Including cards from other filtered decks must default off, never be remembered, explain that every conflicting deck is emptied, and leave an active reviewer before scheduling the collection mutation.
- `frontend/session_launcher.py` owns the dialog/debug-renderer adapter passed into `backend/session.py`. Do not make the backend import `frontend.learn_dialog` again.

## Search ALL

- `frontend/search_all.py` consumes bounded helpers from `backend/search_repository.py`; do not issue raw Incremento SQLite queries in the dialog.
- Missing PDF text starts `backend/search_indexer.py` through the background task runner. Keep progress, cancel-after-current-file, profile capture, stale-callback guards, persistent retry state, and Activity Center lifecycle intact.
- A query must never synchronously extract an entire PDF library on the Qt thread. Manual forced reindexing follows the same background/cancellable rule.
- Keep Review All diagnostics aligned with that two-operation lifecycle: inspection start/finish/failure, normalized picker enums and numeric limit, filtered-deck counts, and review start/end. Never forward source titles, card IDs, filenames, positions, or exception messages to the diagnostic sink.

## Settings UI

- Main file: `frontend/settings_dialog.py`.
- Tabs are `Extraction`, `Review`, `Topics`, `Writing`, `Shortcuts`, and `Advanced`.
- `frontend/settings_dialog.py` owns widget layout and value normalization; `__init__.py` `openSettingsFunction()` owns loading current config into the dialog and writing accepted values back.
- When adding or renaming a setting, keep these in sync:
  - `config.json` default
  - dialog constructor argument
  - dialog property or parser
  - `openSettingsFunction()` load/save wiring
  - `tests/test_settings_dialog.py`
  - `MANUAL.md`
- The advanced settings tab opens a guarded database editor. Keep its copy accurate about checkpoint creation and read-only startup.
- Reject duplicate non-empty shortcuts after normalizing platform-equivalent key sequences. The command palette defaults to `Ctrl+K`; Activity Center is assignable but unbound by default.

## Navigation, Onboarding, Activity, and Accessibility

- The command palette lists registered Incremento actions, ranks them deterministically, displays configured shortcuts, and retains unavailable actions with an explanation. Activation must dispatch through the existing QAction callback.
- Onboarding is non-modal and versioned. First-run completion/skip is persisted, while **Getting Started…** always opens the guide manually. Reuse existing action callbacks for Add PDF, session setup, and backup.
- Activity Center polls the bounded backend snapshot without blocking producers. Preserve selection across refreshes, expose Cancel/Retry only when supported, and stop its timer when the dialog closes.
- Custom-painted charts need an accessible name and concise text equivalent. Controls need stable accessible names/descriptions, visible `:focus-visible` treatment, status announcements through polite live regions, and reduced-motion behavior where animation/transition exists.
- Reader toolbar consistency does not mean erasing reader-specific features. Shared primary actions follow PDF terminology; playback, EPUB section navigation, web navigation, highlights, and PDF page/zoom controls remain media-specific.

## Database and Maintenance Dialogs

- `database_entries_dialog.py` is a read-only text/search view of Incremento rows linked to an explicit Browser card selection; it must not become a generic raw-SQL path. The current lookup/format path is synchronous and has no explicit selection/result cap, so do not invoke it automatically or broaden its scope. A hardening change should add card/result budgets and move the DB scan off Qt's main thread with cancellation/stale-profile tests.
- `sqlite_editor_dialog.py` starts read-only, explicitly checkpoints before enabling writes, validates/quotes identifiers, and restricts mutations to the chosen Incremento database. Never accept an arbitrary filesystem database path or concatenate table/column input into SQL.
- Maintenance UI that touches Anki or profile storage must show the exact scope before mutation, run the work off the UI thread when non-trivial, and refresh only after the operation succeeds.

## Card-format updates

- `frontend/note_type_update_dialog.py` explains pending Anki note-type changes before they happen. It must state that the collection is still untouched, offer Later and Sync Before Updating, require an explicit confirmation before Apply, and explain Upload/Download direction after the approved change.
- Startup may detect and prompt, but it must never create or update note types. The manual **Incremento → Utils → Card Format Updates…** action uses the same workflow.

## Frontend Checks

- Useful focused suite:

```bash
.venv/bin/python -m pytest -o addopts= tests/test_add_card_dock.py -q
.venv/bin/python -m pytest -o addopts= tests/test_settings_dialog.py tests/test_learn_dialog.py -q
.venv/bin/python -m pytest -o addopts= tests/test_knowledge_tree.py tests/test_reviewer_priority_badge.py -q
.venv/bin/python -m pytest -o addopts= tests/test_video_web.py -q
.venv/bin/python -m pytest -o addopts= tests/test_writing_dock.py tests/test_reviewer_priority_badge.py -q
.venv/bin/python -m pytest -o addopts= tests/test_pdf_bookshelf.py tests/test_reader_links.py tests/test_pdf_dock.py tests/test_epub_dock.py -q
.venv/bin/python -m pytest -o addopts= tests/test_browser_priority_toolbar.py tests/test_reviewer_extract_button.py tests/test_reviewer_shortcuts.py tests/test_reviewer_source_cover.py tests/test_reviewer_tags.py tests/test_tag_colors.py -q
.venv/bin/python -m pytest -o addopts= tests/test_database_entries_dialog.py tests/test_file_shell.py tests/test_image_rotation.py tests/test_note_type_update_dialog.py tests/test_db.py -q
.venv/bin/python -m pytest -o addopts= tests/test_current_document_search_dialog.py tests/test_pdf_quick_jump.py tests/test_media_review_dialog.py tests/test_webpage_dialog.py -q
npm --prefix frontend test
npm --prefix frontend run build
```

Run `npm --prefix frontend run build:extension` instead when changing `vite.extension.config.js` or extension-owned source. Both generated outputs are committed; inspect their diffs and keep them in the same change as their source.
