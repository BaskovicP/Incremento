# Frontend Agent Notes

Use this file for work in `frontend/`.

## Ownership

- Qt dialogs and docks live here, along with the React PDF viewer source in `frontend/src/`.
- The main knowledge-tree workspace, subset review window, branch postpone dialog, and reviewer priority badge also live here.

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
- Settings UI lives in `frontend/settings_dialog.py`. Save and load wiring lives in `__init__.py`.
- Generic note editors and field pickers should hide dedicated Incremento provenance fields. Reuse backend `visible_field_names()` behavior rather than duplicating a separate blocklist.

## Writing Dock

- Main file: `frontend/writing_dock.py`.
- The dock remembers per-card cursor, scroll, zoom, wrap mode, focus mode, current-line highlight, and marker line.
- The bottom bar also shows per-card writing progress. Scope options are `Today`, `Session`, and `All-time`.
- `Session` means the current open session for that writing card, not the whole Anki run.
- Word counting mode is configurable from the `Writing` settings tab. `Word-like` is only an approximation of Microsoft Word behavior, not a byte-for-byte clone.

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
- Topic cards use `More / Same / Less`.
- Topic cards can optionally show the red Postpone button.
- Item cards can optionally use `Fail / Pass`.
- Topic review button styling is patched after `_showEaseButtons()`.
- Current topic styling keeps yellow unchanged and uses more muted red and blue tones.
- If you change reviewer button behavior, verify both scheduling logic and injected web styling.
- Reviewer glance metadata lives in `frontend/reviewer_priority_badge.py`. The badge shows priority for all cards and topic A-factor, saved browser time, and custom schedule when available. If you change priority or topic review flows, keep the reviewer badge refresh path in sync.
- Custom schedule text must only render when a real schedule exists for the current card; stale default text is a regression.

## Frontend Checks

- Useful focused suite:

```bash
.venv/bin/python -m pytest -o addopts= tests/test_add_card_dock.py -q
.venv/bin/python -m pytest -o addopts= tests/test_knowledge_tree.py tests/test_reviewer_priority_badge.py -q
.venv/bin/python -m pytest -o addopts= tests/test_video_web.py -q
.venv/bin/python -m pytest -o addopts= tests/test_writing_dock.py tests/test_reviewer_priority_badge.py -q
```
