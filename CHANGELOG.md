# Changelog

Changes after **16 September 2026, 09:44 (Europe/Zagreb)**.

## 23 October 2026 — PDF references and side-by-side reading

Changes since the 23 October overnight rebuild requested as **00:05 (Europe/Zagreb)**. The retained package is stamped **00:02:37** (`2026.10.23.000237`); all 239 packaged source files match commit `c81c996`.

- Read two PDFs side by side with a resizable divider, or browse a reference in a separate preview window. Each reader keeps its own page, zoom, search, and return history. Browsing a reference preserves the main document's saved reading progress.
- Link a PDF page to a specific page or passage in another imported PDF. The destination preview supports page browsing, search, zoom, scrolling, and selecting a spot before saving. Open the destination's Page links panel to jump back to the source.
- Open linked PDFs from PDF pages, stored web cards, and Anki card menus. References support preview, opening beside the current reader, changing the destination, and removing the association.
- Page links now lives in the existing bottom Reading toolbar and compact controls. Its connection count opens a dismissible panel, and **Open beside reading** is a visible text button. Controls and link rows adapt to narrow windows, and the reader reserves the toolbar's actual height so the last part of the page remains accessible.
- Recognize formula snapshots from PDF, EPUB, and web readers with local LaTeX-OCR (pix2tex). Review and edit the result, then copy inline MathJax, display MathJax, or plain LaTeX. Setup and recognition show progress and support cancellation; recognition works offline after setup and does not require an account or upload the crop.
- Recolor saved PDF highlights without losing their text, notes, or linked cards, including when delete buttons are hidden. Highlight shortcuts also accept Cmd+H on macOS and Ctrl+H on Windows/Linux alongside Option/Alt+H.
- Search personal PDF and EPUB highlight notes through the independent **Annotations** filter in Search ALL. Annotation previews show the saved note, while highlight previews show the highlighted passage.
- Preserve a linked passage when annotations refresh, retain the reference document's source details during extraction, and reject stale reader operations after closing a document or switching profiles. Updated English, Croatian, and Simplified Chinese interface text and rebuilt reader and Companion assets are included.
- Updated compatible build-tool dependencies and stabilized the real WebEngine editor tests for macOS offscreen execution. The dependency audit reports no known vulnerabilities.

Restart Anki after updating. Optional local formula recognition requires an installed Python 3.10–3.12 and a one-time software/model download through **Snapshot → Scan for MathJax… → Set up / repair local LaTeX-OCR**. Saved PDF associations are included in Incremento profile backups; Anki Sync alone does not transfer them. Page-to-page associations currently support PDFs.

## 18 October 2026 — 2026.10.18

Changes since the 12 October 2026 release.

- Redesigned Statistics with reading streaks, daily goals, activity and cumulative graphs, and period comparisons.
- Added searchable PDF/EPUB completion figures and a Learning cards view with current card stages, failed/recalled answer attempts, and 7- or 30-day recall trends. EPUB page totals are estimates.
- Added video watch-time statistics for playback inside Incremento, excluding pauses and seeks. Tracking starts with this update.
- Session estimates, Live card preview, and startup now share the same actual selection, including random choices. Counts reflect available cards, and tag suggestions match any part of a name.
- Companion can remember tags per website and Anki profile. Text capture supports Enter to create a note, formatted selections, clickable source links, a field preview, and duplicate detection. Capture authorization and snapshot shortcut guidance are improved.
- Capture an opened browser page as a PDF, save PDF layout defaults in Companion, and resume supported blocked-page imports after completing browser verification.
- Choose printed labels, physical PDF page numbers, or both in citations. Source page previews expand on desktop and mobile, available bold/italic formatting is retained, and highlight controls can be hidden for clean screenshots.
- One cleanup action handles unused Incremento files, PDF screenshots, and stale records. Bookshelf documents can be revealed in Finder or File Explorer, and full backups avoid false integrity failures from reused database connections.

After updating, restart Anki, reload Companion, and refresh pages where you use its capture features. Existing Global capture shortcuts may need their scope changed to In Chrome in the browser's extension shortcut settings.

## 19 September 2026

Turn more reading into learning: choose and preview DjVu compression, create editable Q/A batches, remember PDF snapshot fields, and copy PDF text more accurately. Companion now shows import progress and privacy-safe errors, handles multi-tab reconnects better, and captures cleaner Markdown. Video controls are simpler, cloud-synced backup rotation is tidier, and local bridge security is stronger.
