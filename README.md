# Incremento

Incremento is a modern Anki add-on for incremental learning from mixed content. It brings a SuperMemo-style long-form learning workflow into Anki, combining PDFs, EPUBs, videos, web pages, writing notes, and local files with normal flashcards so you can study, extract, and review in one place.

## What It Does

- Builds filtered Anki study sessions with configurable topic/item balance
- Supports PDF-based topic cards with an in-app viewer, highlights, and extraction into new cards
- Supports video, web page, and writing cards
- Tracks reading progress, priorities, highlights, and study statistics
- Includes a browser bridge and Chrome extension for importing content from the web

## Install

This repository is set up for source installation, not direct AnkiWeb distribution. The repo intentionally does not ship `meta.json`, because that file contains the private add-on package ID.

1. Clone or copy this repo into your Anki add-ons folder as `incremento`.
2. Make sure the final path ends with `addons21/incremento`.
3. Restart Anki.

Common add-on paths:

| Platform | Add-on path |
|---|---|
| macOS | `~/Library/Application Support/Anki2/addons21/incremento/` |
| Windows | `%APPDATA%\Anki2\addons21\incremento\` |
| Linux | `~/.local/share/Anki2/addons21/incremento/` |

## Optional Dependencies

Core functionality works without extra system setup, but some PDF features improve when these are available:

- `PyMuPDF`: PDF rendering and text extraction
- `Tesseract`: OCR for image-only PDFs

Incremento can guide first-run setup from inside Anki. Platform-specific details are implemented in [backend/deps.py](backend/deps.py).

## Quick Start

After installing and restarting Anki:

1. Open **Tools → Start Incremental Learning** to build a study session.
2. Use **Tools → Add PDF to Topics** to add a PDF-backed topic card.
3. Use **Tools → Export Full Backup** to create a migration/backup ZIP.

For a full walkthrough, see [MANUAL.md](MANUAL.md).

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

Build a clean addon ZIP with:

```bash
python3 scripts/package_addon.py
```

Useful variants:

```bash
# Rebuild the frontend bundle first
python3 scripts/package_addon.py --build-frontend

# Run tests before packaging
python3 scripts/package_addon.py --run-tests

# Include local meta.json for a manual/private package
python3 scripts/package_addon.py --include-meta
```

The script writes a publishable ZIP into `dist/`, stages the exact packaged folder next to it for inspection, and creates the initial `user_files/` directory structure expected on first run.

## Repository Hygiene

- `meta.json` is ignored because it contains the private Anki add-on package ID
- `user_files/` is ignored because it contains local runtime data, imported media, and user databases
- Generated viewer assets in `web/` are intentionally tracked because they are shipped with the add-on
