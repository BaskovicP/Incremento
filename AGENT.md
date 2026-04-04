# Incremento Agent Notes

Compact repo guide for coding agents. Keep this file high-signal and current.

## Repo Shape

- `__init__.py`: addon entry point, hook registration, menu actions, web exports.
- `backend/`: card creation, bridge/API logic, persistence helpers, scheduler/config logic.
- `frontend/`: Qt dialogs/docks plus React source for the PDF viewer.
- `chrome_extensions/incremento_companion/`: Chrome extension for page import, bookmark import, and video time capture.
- `web/`: shipped web assets served by Anki web exports.
  - `web/pdf_dock.html`
  - `web/pdfjs/*`
  - `web/dist/pdf_viewer.js`
- `user_files/`: user data and runtime state only. **Data is per-profile** — see below.

## Per-Profile Data Isolation

All user data lives under `user_files/<ProfileName>/`, not flat in `user_files/`.

```
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

### Key modules

- **`backend/paths.py`** — central path construction. Pure functions, no Anki imports.
  - `set_active_profile(name)` / `get_active_profile()` — module-level registry; set once in `profile_did_open`, read everywhere else.
  - `get_user_files_dir(addon_dir, profile)`, `get_db_path(...)`, `get_pdf_dir(...)`, etc.
- **`backend/migration.py`** — idempotent migration from legacy flat `user_files/` layout to `user_files/<profile>/`. Called on every `profile_did_open`.

### `_active_profile()` import pattern

Any backend module that needs the current profile name imports like this:

```python
try:
    from .paths import get_active_profile as _active_profile
except ImportError:
    from paths import get_active_profile as _active_profile
```

Frontend modules that already have `_paths` imported use `_paths.get_active_profile()`.

### Functions that require `profile` as the second argument

All of these must receive a `profile` string after `addon_dir`:

- `db.get_connection(addon_dir, profile)`
- All DB helpers: `get_topic_schedule`, `set_topic_schedule`, `export_*_json`, `add_*_card_source`, `get_*_card_sources`, `replace_*_text_index`, `search_*_text_index`, etc.
- `statistics.load_stats(addon_dir, profile)`, `save_stats(...)`, `delete_*_stats(...)`
- `statistics.StatsManager(addon_dir, profile, day_end_time=...)`
- `priority_manager.set_priority(addon_dir, profile, card_id, priority)`
- `video_manager.local_video_abspath(addon_dir, profile, relpath)`

### Qt WebEngine profile singletons

`video_dock.py` and `web_dock.py` create Qt WebEngine profiles stored in `user_files/<profile>/video_profile/` and `user_files/<profile>/web_profile/`. These are singletons that must be reset on profile switch.

- `frontend/video_dock.reset_for_profile_switch()` — sets `_video_profile = None`, hides/destroys dock
- `frontend/web_dock.reset_for_profile_switch()` — sets `_runtime.profile = None`, hides/destroys dock
- Both are called from `_on_profile_did_open()` in `__init__.py` **before** `set_active_profile` and migration.

## Hard Boundaries

- Do not put shipped code/assets back into `user_files/`.
- `user_files/` is for user data only, and all of it is per-profile (see above).
- Shipped HTML/JS/CSS assets belong under `web/`.

## Web Assets

- `__init__.py` exports `web/.*` via `mw.addonManager.setWebExports(__name__, r"web/.*")`.
- PDF.js worker URL is `/_addons/incremento/web/pdfjs/pdf.worker.min.js`.
- If you change `frontend/src/*` for the PDF viewer, rebuild it:

```bash
cd frontend
npm run build
```

- The build output must land in `web/dist/pdf_viewer.js`.

## PDF Viewer

- Main Python loader: `frontend/pdf_dock.py`.
- Main React hook: `frontend/src/usePdfRender.js`.
- Imported user PDFs are stored in `user_files/<profile>/pdfs/` and referenced by `PDF_Filename`.
- Do not confuse viewer assets with imported PDFs.

## Browser Bridge

- Local bridge lives in `backend/browser_bridge.py`.
- Endpoint: `http://127.0.0.1:8766/incremento/add-content`
- Supports:
  - single-item import payloads
  - batch `items` payloads
  - direct PDF bytes via `pdfBase64`
- The bridge refreshes Anki UI after successful imports; extension-driven imports should recreate and refresh `Topics` immediately.

## Chrome Extension

- Folder: `chrome_extensions/incremento_companion/`
- React source lives in:
  - `chrome_extensions/incremento_companion/src/`
- Built extension bundles are written to:
  - `chrome_extensions/incremento_companion/dist/`
- Popup can import current page as:
  - `pdf`
  - `video`
  - `webpage`
  - `writing`
- Bookmark importer lives in:
  - `bookmarks.html`
  - `bookmarks.css`
- Runtime scripts referenced by manifest/HTML now come from `dist/`:
  - `dist/background.js`
  - `dist/content.js`
  - `dist/offscreen.js`
  - `dist/popup.js`
  - `dist/bookmarks.js`
- PDF bookmark/current-page import is implemented in the shared source module:
  - `src/shared/pdfFetch.js`
- If you change extension React source, rebuild it:

```bash
cd frontend
npm run build:extension
```

## Deck/Card Creation Rules

- Default target deck is `Topics`.
- Card creators recreate the deck if it is missing:
  - `backend/pdf_manager.py`
  - `backend/video_manager.py`
  - `backend/web_manager.py`
  - `backend/writing_manager.py`

## Useful Current Gotchas

- Some `.pdf` URLs do not return PDFs to Python. They may return HTML challenge pages instead. For those, extension-side PDF fetch is the correct path.
- If you change browser-import behavior, verify both:
  - bridge normalization/tests
  - extension JS syntax
- `frontend/vite.config.js` controls where the shipped PDF viewer bundle is written. Keep it aligned with `web/pdf_dock.html`.
- Any path helper that returns something under `user_files/` must go through `backend/paths.py` — never hardcode `user_files/pdfs/` or similar.
- Any error message referencing a user file path should include the profile name (e.g. `user_files/<profile>/pdfs/`) so the user can find the actual file.

## Tests / Checks

Use `.venv/bin/python` (Python 3.14).

```bash
.venv/bin/python -m pytest tests/ -q
```

Currently ~463 tests pass. 3 pre-existing failures unrelated to profile work:
- `test_add_card_dock` (×2)
- `test_epub_manager::test_extracts_metadata_and_sections`

`tests/conftest.py` calls `_paths.set_active_profile("TestProfile")` so all test DB/path helpers use `user_files/TestProfile/` as their root.

Useful JS syntax checks:

```bash
node --check chrome_extensions/incremento_companion/dist/background.js
node --check chrome_extensions/incremento_companion/dist/content.js
node --check chrome_extensions/incremento_companion/dist/offscreen.js
node --check chrome_extensions/incremento_companion/dist/popup.js
node --check chrome_extensions/incremento_companion/dist/bookmarks.js
```

Extension unit tests:

```bash
npm --prefix chrome_extensions/incremento_companion test
```

## Editing Guidance

- Prefer small, isolated fixes.
- Avoid touching user content under `user_files/` unless the task is explicitly about user data migration or cleanup.
- When moving shipped assets, update both source references and generated/runtime references.
- If you change PDF viewer source, rebuild before finishing.
- When adding any function that reads/writes under `user_files/`, always thread the `profile` argument through from the call site rather than calling `get_active_profile()` deep inside — or use `get_active_profile()` at the outermost call site only.
