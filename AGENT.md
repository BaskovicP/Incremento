# Incremento Agent Notes

Compact repo guide for coding agents. Keep this file high-signal and current.

## Repo Shape

- `__init__.py`: addon entry point, hook registration, menu actions, web exports.
- `backend/`: card creation, bridge/API logic, persistence helpers, scheduler/config logic.
- `frontend/`: Qt dialogs/docks plus React source for the PDF viewer.
- `chrome_extensions/incremento_video_time_clipboard/`: Chrome extension for page import, bookmark import, and video time capture.
- `web/`: shipped web assets served by Anki web exports.
  - `web/pdf_dock.html`
  - `web/pdfjs/*`
  - `web/dist/pdf_viewer.js`
- `user_files/`: user data and runtime state only.

## Hard Boundaries

- Do not put shipped code/assets back into `user_files/`.
- `user_files/` is for:
  - imported PDFs in `user_files/pdfs/`
  - writing files in `user_files/writing/`
  - local videos in `user_files/videos/`
  - DB/stats files
  - runtime browser profiles like `user_files/web_profile/` and `user_files/video_profile/`
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
- Imported user PDFs are stored in `user_files/pdfs/` and referenced by `PDF_Filename`.
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

- Folder: `chrome_extensions/incremento_video_time_clipboard/`
- Popup can import current page as:
  - `pdf`
  - `video`
  - `webpage`
  - `writing`
- Bookmark importer lives in:
  - `bookmarks.html`
  - `bookmarks.js`
  - `bookmarks.css`
- PDF bookmark/current-page import may fetch PDF bytes in-browser (`pdf_fetch.js`) and send `pdfBase64` to bypass sites that return bot/captcha HTML to Python.

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

## Tests / Checks

Use the interpreter available in the environment unless told otherwise.

```bash
python3 -m pytest tests/test_browser_bridge.py tests/test_pdf_manager.py
```

Useful JS syntax checks:

```bash
node --check chrome_extensions/incremento_video_time_clipboard/popup.js
node --check chrome_extensions/incremento_video_time_clipboard/bookmarks.js
node --check chrome_extensions/incremento_video_time_clipboard/pdf_fetch.js
```

## Editing Guidance

- Prefer small, isolated fixes.
- Avoid touching user content under `user_files/` unless the task is explicitly about user data migration or cleanup.
- When moving shipped assets, update both source references and generated/runtime references.
- If you change PDF viewer source, rebuild before finishing.
