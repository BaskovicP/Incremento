# Incremento Agent Notes

Compact repo guide for coding agents. Keep this file high-signal and current.

## Repo Shape

- `__init__.py`: addon entry point, hook registration, settings save/load, reviewer patches, bridge startup.
- `backend/`: card creation, browser bridge/API logic, persistence helpers, scheduler/config logic.
- `frontend/`: Qt dialogs/docks plus React source for the PDF viewer.
- `chrome_extensions/incremento_companion/`: Chrome extension for imports, browser capture, bookmark import, and video time sync.
- `web/`: shipped web assets exported by Anki.
- `tests/`: Python regression suite.
- `user_files/`: runtime data only. All user data is per-profile.

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

Functions that must receive `profile` after `addon_dir` include:

- `db.get_connection(addon_dir, profile)`
- DB helpers such as `get_*`, `set_*`, `export_*`, `search_*`, `replace_*`
- `statistics.load_stats(addon_dir, profile)` and related helpers
- `priority_manager.set_priority(addon_dir, profile, card_id, priority)`
- media path helpers such as `video_manager.local_video_abspath(addon_dir, profile, relpath)`

`video_dock.py` and `web_dock.py` each maintain a per-profile Qt WebEngine profile singleton. Reset them on profile switch before migration and `set_active_profile()`.

## Hard Boundaries

- Do not put shipped code or assets inside `user_files/`.
- Keep all runtime/user content per-profile.
- Shipped HTML/JS/CSS belongs under `web/`.
- Any helper that returns a path under `user_files/` must go through `backend/paths.py`.

## PDF Viewer

- Main Python loader: `frontend/pdf_dock.py`
- Main React code: `frontend/src/`
- Build output must land in `web/dist/pdf_viewer.js`

If you change PDF viewer React source:

```bash
npm --prefix frontend run build
```

Imported PDFs are stored under `user_files/<profile>/pdfs/` and referenced by `PDF_Filename`. Do not confuse user PDFs with shipped viewer assets.

## Browser Bridge

- Local bridge: `backend/browser_bridge.py`
- Main endpoint: `http://127.0.0.1:8766/incremento/add-content`
- Browser-capture metadata endpoint: `http://127.0.0.1:8766/incremento/browser-capture-meta`

The bridge currently supports:

- single-item import payloads
- batch `items` payloads
- direct PDF bytes via `pdfBase64`
- generic browser-capture note creation
- writing imports in `selection` and `webpage_markdown` modes
- tracked web-card media progress updates for external browser playback

Current browser-capture rules:

- field mappings now include `titleField`, `selectedTextField`, `urlField`, and `snapshotField`
- if `titleField` targets the note type's first field, the backend writes a unique snapshot label
- duplicate first-field failures raise an explicit error instead of silently relying on Anki rejection
- stored browser-capture image filenames are sanitized and capped before the UUID suffix

The bridge refreshes Anki UI after successful imports.

## Chrome Extension

- Folder: `chrome_extensions/incremento_companion/`
- Source: `chrome_extensions/incremento_companion/src/`
- Built runtime bundles: `chrome_extensions/incremento_companion/dist/`

Popup actions currently include:

- `Add as PDF`
- `Add as Video`
- `Add as Webpage`
- `Add Selection to Markdown`
- `Add Page to Markdown`
- browser-capture triggers for text and snapshot capture

Current extension-specific behavior to keep in mind:

- snapshot capture no longer dims the page with a gray overlay
- popup writing imports auto-generate a unique title only when the user leaves the default page title unchanged
- auto-generated writing titles use a microsecond-resolution timestamp suffix
- markdown preferred filenames are kept short and slug-based; do not feed the full generated note title back into the filename
- tracked web-card playback can come from iframe players; content/background reinjection must preserve `allFrames: true`
- web-card resume handoff for original-page resume is passed through a URL fragment marker, not server-visible query params
- content scripts sanitize temporary Incremento tracking/resume markers back out of the visible URL after load
- bookmark importer runtime files also come from `dist/`

If you change extension source:

```bash
npm --prefix frontend run build:extension
```

Useful focused extension checks:

```bash
npm --prefix chrome_extensions/incremento_companion test
node --check chrome_extensions/incremento_companion/dist/background.js
node --check chrome_extensions/incremento_companion/dist/content.js
node --check chrome_extensions/incremento_companion/dist/offscreen.js
node --check chrome_extensions/incremento_companion/dist/popup.js
node --check chrome_extensions/incremento_companion/dist/bookmarks.js
```

## Card Creation and Filename Rules

- Default target deck for bridge/extension imports is usually `Topics`.
- Card creators recreate the deck if it is missing.
- PDF, video, webpage, and writing imports now use visible duplicate-title suffixes such as `Title [2]`; do not reintroduce zero-width duplicate markers.
- UUID-backed saved filenames should keep a short sanitized stem first, then append the UUID.
- The current stem cap is `80` characters across writing, PDF, EPUB, video, and browser-capture media helpers.

## Web Dock and Web Cards

Main files:

- `frontend/web_dock.py`
- `backend/web_manager.py`

Current behavior:

- the dock toolbar is split into two rows to keep the control bar usable
- the dock has both `Open in Window` and `Open in Window (Home)`
- `Home` keeps navigation inside the dock; `Open in Window (Home)` opens the card's stored homepage externally
- tracked `Incremento Web` cards persist the latest embedded-media resume state per card
- the dock shows a `Resume mm:ss` button only when resume state exists for the current web card
- if `prefer_web_card_resume_in_original_page` is enabled, `Resume` reopens the original page and asks the extension to seek there
- otherwise `Resume` prefers a direct resumable media URL when one can be built
- original-page resume should not depend on the live `Track via Chrome extension` checkbox being enabled in the dock at click time
- avoid putting resume metadata in the server-facing query string; use the fragment-based Incremento marker instead

Relevant config key:

- `prefer_web_card_resume_in_original_page`

## Add Card and Note Editors

Main file: `frontend/add_card_dock.py`

Current behavior:

- embeds Anki's Add dialog in a persistent dock
- injects transfer buttons for recent selections
- registers `T` and `I` toolbar buttons in both Add Card and edit-note editors
- `T` toggles config-driven topic tags
- `I` toggles config-driven item tags
- tag button state refreshes on editor init, note load, and `editor_did_update_tags`
- edit-note toggles must refresh the visible tag widget immediately and may need a scheduled `editor.loadNote()` to make the tag row visibly update

Relevant config keys:

- `add_card_topic_tags`
- `add_card_item_tags`
- `extract_notetype`
- `extract_source_links`

Settings UI lives in `frontend/settings_dialog.py`. Save/load wiring lives in `__init__.py`.

## Reviewer Behavior

Reviewer patching is centralized in `__init__.py`.

Current notable behavior:

- topic cards use `More / Same / Less`
- topic cards can optionally show the red Postpone button
- item cards can optionally use `Fail / Pass`
- topic review button styling is patched after `_showEaseButtons()`
- current topic styling keeps yellow unchanged and uses more muted red/blue tones

If you change reviewer button behavior, verify both scheduling logic and the injected web styling.

## Useful Current Gotchas

- Some `.pdf` URLs return HTML challenge pages to Python; extension-side PDF fetch is the correct fallback there.
- If you change browser-import behavior, verify both bridge normalization/tests and extension JS/runtime output.
- `frontend/vite.config.js` controls where the shipped PDF viewer bundle is written. Keep it aligned with `web/pdf_dock.html`.
- Error messages referencing saved user files should include the profile-aware path shape so users can locate the file.

## Tests / Checks

Use `.venv/bin/python`.

Full suite:

```bash
.venv/bin/python -m pytest tests/ -q
```

If the local environment lacks `pytest-cov` but `pytest.ini` expects it, use:

```bash
.venv/bin/python -m pytest -o addopts= tests/test_add_card_dock.py -q
```

Useful focused suites for recent hotspots:

```bash
.venv/bin/python -m pytest -o addopts= tests/test_add_card_dock.py -q
.venv/bin/python -m pytest -o addopts= tests/test_browser_bridge.py tests/test_pdf_manager.py tests/test_video_web.py -q
```

`tests/conftest.py` sets the active profile to `TestProfile`, so test DB/path helpers use `user_files/TestProfile/`.

## Editing Guidance

- Prefer small, isolated fixes.
- Avoid touching `user_files/` unless the task is explicitly about migration or cleanup.
- When moving shipped assets, update both source references and generated/runtime references.
- If you change PDF viewer or extension source, rebuild before finishing.
- When adding functions that read/write under `user_files/`, thread `profile` from the call site instead of reaching for global state deep inside helper stacks.
