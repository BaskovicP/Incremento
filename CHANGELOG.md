# Changelog

This changelog covers work completed after **16 September 2026, 09:44
(Europe/Zagreb)**.

## 19 September 2026 — Turn more of what you read into learning

This release shortens the path from useful material to well-organized cards.
DjVu conversion is easier to control, batch creation is faster, PDF extraction
is more accurate, and Companion makes every import visibly accountable.

### Highlights

- **Import DjVu without guessing the result.** Choose from six PDF compression
  modes, inspect automatic samples and page previews, and see an estimated size
  range. Incremento warns about extreme expansion and safely falls back when
  layered conversion is unavailable while preserving selectable text.

- **Create complete Q/A sets in one pass.** Use the new `Q/A` button in Anki's
  Add window or Incremento's dock. Paste alternating lines or multiline blocks,
  preview and edit every card, map fields, and set priority, classification, and
  tags individually or in bulk. Active extracts retain source lineage.

- **Make PDF extraction more natural.** Snapshots can remember their destination
  field per note type, with a safe fallback and an off switch under **Settings →
  Extraction**. Text selection better preserves exact characters, spacing, line
  wraps, paragraph breaks, and OCR alignment.

- **Know exactly what Companion is doing.** Browser imports show their progress
  from reading the tab to creating the card. Success and failure receive one
  accessible signal. Failures identify the stopped stage and provide copyable,
  privacy-safe diagnostics without page content, URLs, tokens, or card data.

- **Capture pages with less friction.** Companion loads Anki metadata separately,
  shares reconnect work across tabs, and queues AnkiConnect video updates.
  Main-content Markdown capture prefers the semantic article and removes page
  chrome before applying safety limits. Actions that do not need HTML no longer
  serialize the page.

- **Enjoy a cleaner video workflow.** The compact primary bar emphasizes
  **Extract**, **Bookmark**, and the live count. Back, browser opening, downloads,
  captions, and Review All remain in an organized overflow menu.

- **Keep cloud-synced backups tidy.** Automatic backups reuse the oldest archive
  once the retention limit is full, including compatible older backups. When
  possible, Incremento builds and validates the ZIP outside the sync folder,
  then atomically moves it into place so cloud tools avoid temporary duplicates.

### Reliability and polish

The local bridge preserves the extension origin, shares authorization refreshes,
retries only safe operations, and never repeats an ambiguous card-creation
request. English, Croatian, and Simplified Chinese catalogs cover the new
workflows. New research also outlines a future Chrome-authenticated study UX; it
is product direction, not enabled functionality.

### Release confidence

The release passed translation and generated-asset checks, compilation, Ruff,
mypy, ESLint, four mutation checks, **2,585 Python tests**, **85 PDF-viewer
tests**, **133 Companion tests**, production builds, and archive validation.
