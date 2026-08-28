# Incremento

Incremento is a modern Anki add-on for incremental learning from mixed content. It brings a SuperMemo-style long-form learning workflow into Anki, combining PDFs, EPUBs, videos, web pages, writing notes, and local files with normal flashcards so you can study, extract, and review in one place.

Incremento supports Anki 24.11 and newer. Optional features that depend on Anki's private reviewer API check compatibility at runtime and fail closed without rescheduling cards when the API is unavailable.

## What It Does

- Builds filtered study sessions with configurable card states, topic/item and document mixes, tags, priorities, ordering, and optional auto-refill
- Opens PDF, EPUB, video, web, writing, and local-file material in persistent reviewer docks that remember progress
- Provides a searchable PDF-and-EPUB Document Bookshelf on `Option+Shift+P` / `Alt+Shift+P`, with a format selector and visual one-click opening
- Reviews cards attached to the current PDF, EPUB, or video with Topic/Item, direct/nested, media-range, due-state, ordering, and count controls, then restores the source position
- Creates cards from selections and highlights while preserving source metadata and links
- Provides topic A-factor scheduling, per-card custom schedules, postpone tools, and Anki-compatible Undo/Redo behavior
- Includes document search, colored Browser quick tags, a card-backed knowledge tree, statistics, and a focus timer
- Exports a privacy-safe support bundle with redacted settings, recent typed events, version data, and code fingerprints for easier bug reports
- Keeps runtime content and databases isolated per Anki profile
- Includes a browser bridge and companion Chrome/Brave extension for capture, import, and playback synchronization

## Install

### Install from AnkiWeb (recommended)

Incremento is available from [AnkiWeb Add-ons](https://ankiweb.net/shared/info/1013949798).

1. In Anki, open **Tools → Add-ons → Get Add-ons…**.
2. Enter the code **`1013949798`**.
3. Restart Anki after installation.

### Install from source

For development or manual installation:

1. Clone or copy this repo into your Anki add-ons folder as `incremento`.
2. Make sure the final path ends with `addons21/incremento`.
3. Restart Anki.

The repository intentionally does not ship `meta.json`; Anki creates and manages that local installation metadata.

Common add-on paths:

| Platform | Add-on path |
|---|---|
| macOS | `~/Library/Application Support/Anki2/addons21/incremento/` |
| Windows | `%APPDATA%\Anki2\addons21\incremento\` |
| Linux | `~/.local/share/Anki2/addons21/incremento/` |

## Optional Dependencies

Core functionality works without extra system setup, but some PDF features improve when these are available:

- `PyMuPDF >=1.24,<2`: PDF rendering and text extraction
- `Tesseract`: OCR for image-only PDFs
- `yt-dlp`: optional local YouTube/Vimeo downloads

Incremento can guide first-run setup from inside Anki. PyMuPDF installation is an explicit user action and yt-dlp is never silently installed into Anki's Python environment. Platform-specific details are implemented in [backend/deps.py](backend/deps.py).

## Quick Start

After installing and restarting Anki:

1. Open **Incremento → Start Incremental Learning** to build a study session.
2. Use **Incremento → Add Content → Add PDF** to add a PDF-backed topic card.
3. Use **Incremento → Export Full Backup** to create a migration/backup ZIP.
4. If something goes wrong, use **Incremento → Export Support Bundle…** to create a diagnostic ZIP that is safe to attach to a bug report.

For a full walkthrough, see [MANUAL.md](MANUAL.md).

The support bundle is separate from **Export Full Backup**. It never contains card/note text, raw card or note IDs, deck/tag/profile names, media, user or media filenames, local filesystem paths, URLs, database rows, exception messages, or precise activity timestamps. Private and free-text configuration values are replaced with redaction markers. Fixed shipped-code filenames may appear beside their hashes so the developer can identify the installed build.

## Companion Extension

The optional Chrome/Brave extension lives in `chrome_extensions/incremento_companion/`. It can send PDFs, videos, web pages, and writing notes into Incremento, and it can capture watched video time.

Extension details and install steps:

- [chrome_extensions/incremento_companion/README.md](chrome_extensions/incremento_companion/README.md)

## Main Components

- `backend/`: scheduling, persistence, import logic, browser bridge, and content managers
- `frontend/`: Qt dialogs/docks plus React source for the PDF viewer
- `web/`: shipped web assets used inside Anki
- `chrome_extensions/incremento_companion/`: companion Chrome extension
- `tests/`: Python test suite

## Documentation

- User manual: [MANUAL.md](MANUAL.md)
- Export and restore guide: [EXPORTING.md](EXPORTING.md)
- Persistence and software architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
- Internal agent/developer notes: [AGENTS.md](AGENTS.md) with nested area-specific guides under `backend/`, `frontend/`, `chrome_extensions/incremento_companion/`, and `tests/`

## Development

Python tests:

```bash
.venv/bin/python -m pytest tests/ -v
```

Frontend build:

```bash
cd frontend
npm run build
```

The frontend build writes the shipped PDF viewer bundle to `web/dist/pdf_viewer.js`.

Chrome extension UI build:

```bash
cd frontend
npm run build:extension
```

This writes the React-based extension UI bundles into `chrome_extensions/incremento_companion/dist/`.

Chrome extension tests:

```bash
cd frontend
npm run test:extension
```

## Release Packaging

Build a clean installable `.ankiaddon` package with:

```bash
python3 scripts/package_addon.py
```

Useful variants:

```bash
# Rebuild the frontend bundle first
python3 scripts/package_addon.py --build-frontend

# Run tests before packaging
python3 scripts/package_addon.py --run-tests

# Run every release gate, rebuild generated assets, and remove staging
.venv/bin/python scripts/package_addon.py --release --clean-staging

# Include local meta.json for a manual/private package
python3 scripts/package_addon.py --include-meta
```

The script writes the `.ankiaddon` into `dist/` and stages the exact packaged folder next to it for inspection unless `--clean-staging` is used. Runtime `user_files/`, tests, caches, bytecode, and local installation metadata are excluded; the archive is reopened and validated before success is reported.

## Repository Hygiene

- `meta.json` is ignored because it is local Anki installation metadata
- `user_files/` is ignored because it contains local runtime data, imported media, and user databases
- Generated viewer assets in `web/` are intentionally tracked because they are shipped with the add-on
