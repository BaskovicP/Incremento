# Frontend Agent Notes

Use this file for work in `frontend/`.

## Ownership

- Qt dialogs and docks live here, along with the React PDF viewer source in `frontend/src/`.

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

## Web and Video Docks

- Main files: `frontend/web_dock.py` and `frontend/video_dock.py`.
- `video_dock.py` and `web_dock.py` each maintain a per-profile Qt WebEngine profile singleton.
- Reset those singletons on profile switch before migration and `set_active_profile()`.
- The web dock toolbar is split into two rows to keep controls usable.
- The dock has both `Open in Window` and `Open in Window (Home)`.
- `Home` keeps navigation inside the dock; `Open in Window (Home)` opens the card's stored homepage externally.
- Show `Resume mm:ss` only when resume state exists for the current web card.
- Original-page resume should not depend on the live `Track via Chrome extension` checkbox being enabled at click time.

## Reviewer Behavior

- Reviewer patching is centralized in `__init__.py`, but frontend-visible button styling and behavior changes must stay aligned with it.
- Topic cards use `More / Same / Less`.
- Topic cards can optionally show the red Postpone button.
- Item cards can optionally use `Fail / Pass`.
- Topic review button styling is patched after `_showEaseButtons()`.
- Current topic styling keeps yellow unchanged and uses more muted red and blue tones.
- If you change reviewer button behavior, verify both scheduling logic and injected web styling.

## Frontend Checks

- Useful focused suite:

```bash
.venv/bin/python -m pytest -o addopts= tests/test_add_card_dock.py -q
```
