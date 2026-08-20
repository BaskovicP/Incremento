# Frontend Agent Notes

Use this file for work in `frontend/`.

## Ownership

- Qt dialogs and docks live here, along with the React PDF viewer source in `frontend/src/`.
- The main knowledge-tree workspace, subset review window, branch postpone dialog, and reviewer priority badge also live here.
- The Start Incremental Learning dialog in `frontend/learn_dialog.py` also lives here, including session-size, card-state, and active-session auto-refill controls.
- The main settings surface lives in `frontend/settings_dialog.py`, but persistence wiring still goes through `__init__.py`.

## PDF Viewer

- Main Python loader: `frontend/pdf_dock.py`.
- Main React code: `frontend/src/`.
- Build output must land in `web/dist/pdf_viewer.js`.
- Imported PDFs are stored under `user_files/<profile>/pdfs/` and referenced by `PDF_Filename`. Do not confuse user PDFs with shipped viewer assets.
- `frontend/vite.config.js` controls where the shipped PDF viewer bundle is written. Keep it aligned with `web/pdf_dock.html`.

If you change PDF viewer React source:

```bash
npm --prefix frontend run build
```

## Add Card and Note Editors

- Main file: `frontend/add_card_dock.py`.
- The dock embeds Anki's Add dialog persistently and injects transfer buttons for recent selections.
- Register `T` and `I` toolbar buttons in both Add Card and edit-note editors.
- `T` toggles config-driven topic tags.
- `I` toggles config-driven item tags.
- Tag button state must refresh on editor init, note load, and `editor_did_update_tags`.
- Edit-note toggles must refresh the visible tag widget immediately and may need a scheduled `editor.loadNote()` so the tag row visibly updates.
- Relevant config keys: `add_card_topic_tags`, `add_card_item_tags`, `extract_notetype`, `extract_source_links`.
- Generic note editors and field pickers should hide dedicated Incremento provenance fields. Reuse backend `visible_field_names()` behavior rather than duplicating a separate blocklist.

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
- Reader docks can steal keyboard focus while their question-shown hooks open or raise. Keep the final deferred `reviewer_did_show_question` focus recovery in `frontend/reviewer_focus.py` so Anki's Space, `1`–`4`, and editor shortcuts continue on every card. Never reclaim focus from a modal, popup, or separate active Anki window.

## Session Builder UI

- Main file: `frontend/learn_dialog.py`.
- The dialog supports named presets, optional live preview, and branch-scoped study launches from the knowledge tree.
- The **Card types** checkboxes control whether `New`, `Learning`, and `Due / Review` cards are eligible for session selection at all.
- **Cards per session** and backend normalization share the inclusive 1–9,999 range. The Docs/Other slider stores 100 at its fully-right 0%-Docs endpoint; keep its UI direction and backend conversion aligned.
- The **Advanced** checkbox `Auto-refill session deck to keep this many pending cards` uses **Cards per session** as a live pending-window target after the session starts.
- PDF, EPUB, video, and web reading cards have additional scheduler flows layered on top of Anki state; when changing eligibility wording, verify the tooltip text still matches actual selection behavior.
- Keep the checkbox label, tooltip, saved profile key `auto_refill_session`, and backend semantics in `backend/session.py` consistent. If the behavior changes, update `MANUAL.md` and session-related tests too.

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

## Frontend Checks

- Useful focused suite:

```bash
.venv/bin/python -m pytest -o addopts= tests/test_add_card_dock.py -q
.venv/bin/python -m pytest -o addopts= tests/test_settings_dialog.py tests/test_learn_dialog.py -q
.venv/bin/python -m pytest -o addopts= tests/test_knowledge_tree.py tests/test_reviewer_priority_badge.py -q
.venv/bin/python -m pytest -o addopts= tests/test_video_web.py -q
.venv/bin/python -m pytest -o addopts= tests/test_writing_dock.py tests/test_reviewer_priority_badge.py -q
```
