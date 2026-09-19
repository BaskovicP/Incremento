# Changelog

This changelog covers work completed after **16 September 2026, 09:44
(Europe/Zagreb)**.

## 19 September 2026 — Turn more of what you read into learning

This release removes friction from the path between finding useful material and
turning it into cards. DjVu books are easier to size and convert, batches of
questions can be shaped before they reach Anki, PDF snapshots remember where
they belong, and Companion now makes every import visibly accountable from the
first click to the created card.

### Six ways this release feels better

- **Import DjVu without guessing the PDF size.** Every DjVu file now has its own
  compression choice, an automatic sample drawn from across the book, a page
  preview, and an estimated output-size range. Choose sharp layered black text
  over a compact colour background, conventional compact or balanced colour,
  small grayscale, black and white, or archival lossless output. Incremento
  warns about extreme expansion and safely falls back when a document cannot
  use layered compression.

- **Create a whole Q/A set in one focused pass.** The `Q/A` button is available
  in Anki's normal Add window and Incremento's Add Card dock. Paste alternating
  question/answer lines or multiline `Q:` / `A:` blocks, preview the proposed
  cards, edit or remove rows, map the two destination fields, and set priority,
  Topic/Item/Other classification, and tags per card. Apply shared values to the
  whole batch, then fine-tune individual cards before creating anything.

- **Let PDF snapshots remember their destination.** A new **Always use the
  field I choose** option remembers the selected field for that note type. The
  next snapshot can go straight where it belongs; if the note type or field has
  changed, Incremento asks again instead of guessing. The behavior can be
  disabled at any time under **Settings → Extraction**.

- **Copy and extract PDF text more faithfully.** Selection now follows exact
  character boundaries through PDF.js wrappers, preserves spaces and narrow
  letters, joins ordinary line wraps, keeps real paragraph breaks, and handles
  small OCR baseline differences without jagged highlight bands. Converted
  DjVu text also keeps its original page coordinates, reading order, and
  selectable Unicode symbols more reliably.

- **Know what Companion is doing.** Imports now show the visible stages of the
  operation: reading the tab, preparing the destination, and waiting for Anki
  to create the card. Success and failure receive a single accessible border
  signal. Failures identify the stage and offer **Copy error details** with a
  privacy-safe diagnostic report that excludes page content, URLs, tokens, and
  card data.

- **Keep reading instead of managing browser edge cases.** Companion loads Anki
  metadata independently from page inspection, shares bridge reconnect work
  across tabs, retries brief read-only contention, and serializes optional
  AnkiConnect video updates. Main-content Markdown capture prefers the page's
  semantic article, strips navigation and inactive elements before applying
  limits, and avoids serializing a large DOM for actions that do not need it.

### Reader and review polish

- The video reader now has a compact primary bar with **Extract**, **Bookmark**,
  and a live bookmark count. Back, browser opening, local download, captions,
  and Review All remain close at hand in a clean overflow menu.
- Manual resume time and local playback controls are clearer, while the toolbar
  uses readable theme-aware colours in night mode.
- Batch extraction preserves active source metadata and knowledge-tree lineage,
  while a standalone batch stays independent from another open extraction.
- Topic and Item classification stays exclusive, and batch tags accept spaces,
  commas, or semicolons without creating duplicates.

### Backups that cooperate with cloud-sync folders

- Automatic backups now reuse the oldest owned archive at the same path once
  the chosen retention count is full, including compatible timestamp-named
  backups created by earlier versions.
- When the filesystem permits, automatic ZIPs are built and validated outside
  the selected sync folder, then atomically moved into place. Google Drive,
  Dropbox, and similar tools see the completed slot instead of uploading a
  temporary work file as a second cloud item.
- Manual exports keep their existing destination-local staging behavior, and
  unrelated files, manual archives, other profiles, and symlinks remain outside
  automatic rotation.

### Safer, steadier local integration

- Companion's local bridge now uses an origin-preserving bodyless POST
  handshake and the same transport for read-only metadata calls.
- Concurrent stale requests share one authorization refresh. Safe reads may
  retry short connection failures or busy responses, while an ambiguous write
  is never repeated and cannot silently create a duplicate card.
- Page capture requests only the data required by the selected action and
  reports bounded scope and size information when content exceeds a safety
  limit.
- Newly added PDF snapshot settings are normalized, bounded, and represented in
  privacy-safe support diagnostics without exposing note-type or field names.

### Language, documentation, and the road ahead

- English, Croatian, and Simplified Chinese catalogs and generated browser
  bundles cover the new workflows.
- The manual now documents every DjVu compression mode, batch Q/A creation,
  remembered snapshot fields, Companion progress and diagnostics, video toolbar
  changes, and the revised automatic-backup lifecycle.
- Two Croatian design documents capture research and a proposed UX for using
  authenticated Chrome sessions in a future browser-led study flow. They are
  explicitly research and product direction, not behavior enabled by this
  release.

### Release confidence

The release package passed the complete build and validation gate: translation
and generated-asset checks, Python compilation, Ruff, mypy, ESLint, four targeted
mutation checks, **2,585 Python tests**, **85 PDF-viewer tests**, **133 Companion
tests**, both production builds, and final `.ankiaddon` archive validation.
