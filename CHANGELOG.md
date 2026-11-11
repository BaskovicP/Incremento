# Changelog

Changes after **16 September 2026, 09:44 (Europe/Zagreb)**.

## 11 November 2026 — 2026.11.11

Changes since tag **v2026.11.01.1**.

- Set one Incremento priority for a Browser selection through **Incremento → Set Priority…**. Cards mode changes only the selected cards; Notes mode includes every card belonging to the selected notes. The background batch saves atomically and refreshes the Browser without changing Anki schedules or topic A-factors.
- Right-click one or more PDFs or EPUBs in either Document Bookshelf view to **Set Priority…**. Saving updates visible priorities and priority sorting while preserving selection and unsaved details. The bookshelf also gains **Last added** sorting.
- Read the current review card's original parent in a read-only sidebar without changing the card or answer side. **Settings → Review → Reviewer Controls → Show parent context icon** controls the icon and applies immediately. Automatic study navigation and priority badges stay limited to cards using Incremento.
- Keep up to 32 writing drafts in one tabbed pane, with per-draft text, Undo/Redo, reading position, appearance, bookmarks, and word progress. Use the compact formatting toolbar, export the current draft as Markdown or standalone HTML, and optionally open a selected passage in Google Translate. Saved workspaces retain the writing tabs and their order.
- Connect exact passages in PDFs and EPUBs, briefly reveal matching source or destination text, and return with **Jump Back**. Send selected reader or reviewer text to Writing with a source link, and reopen the writing excerpt from the source-side indicator. Existing page and section links remain usable.
- Track non-linear reading with separate **Viewed** and **Marked read** figures in readers and the Document Bookshelf. Mark or unmark PDF pages and ranges or EPUB passages and sections; repeated visits count once, and explicit marks combine with existing **Read to here** progress in Statistics.
- Save webpages from Anki or Companion as an **HTML snapshot — website appearance** or an editable **Reading copy — reflowable Markdown**. Preview HTML captures, remove unwanted elements with **Zap elements**, and undo or restore removals before saving. Read the result offline with EPUB tools and export standalone HTML, Markdown, or TXT. Later captures create separate documents.
- Keep grouped workspace tabs active for newly opened readers, references, writing, and searches. Find, pin, rename, resize, color, and group tabs; collapse groups without closing their readers. Reopen recently closed panes and restore each profile's last tab session automatically or manually, including browsing addresses and reader positions.
- Preview internal PDF links and footnotes on hover, including when link navigation is disabled. Keep text inside noted highlights selectable, avoid duplicate annotation rendering after synchronization, and refresh overlay-only edits without reloading the document. Fix PDF annotation synchronization and edited Markdown document saves on Windows.
- Stage full backups on the selected destination's filesystem, including external drives, while preserving previous backups on failure. Improve visible progress, event processing, restore recovery, and database-connection handling during backup and restore.
- Refresh English, Croatian, and Simplified Chinese interface text, improve translated-control layouts, rebuild the reader and Companion assets, and update vulnerable Anki and minimatch development dependencies.

Restart Anki after updating. Reload or reinstall Companion from the updated add-on and refresh pages using its capture features. Reading coverage, document associations, writing backlinks, offline documents, and workspace sessions are profile-local; use Incremento backups to preserve data that Anki Sync alone does not transfer. Existing read-to-here markers are retained. Offline snapshots preserve captured content and available resources with scripts and interactive website behavior disabled. The minimum supported Anki version remains 24.11.

[Full comparison](https://github.com/BaskovicP/Incremento/compare/v2026.11.01.1...v2026.11.11)

## 4 November 2026 — 2026.11.04

Changes since tag **v2026.11.03**.

- Link PDF and EPUB passages to the exact explanation in another document. Connections retain the source and destination text, briefly reveal the matching passage, and support returning with **Jump Back**. Older page and section links remain usable.
- Track non-linear reading with separate **Viewed** and **Marked read** figures in readers and the Document Bookshelf. Mark or unmark individual PDF pages, page ranges, EPUB passages, or sections. Repeated visits count once, and explicit reading marks combine with the existing **Read to here** marker in Statistics.
- Send selected PDF, EPUB, or reviewer text to Writing with a link back to its source. Source-side indicators reopen the corresponding writing excerpt, and temporary passage reveals make both directions easier to follow. Writing insertion retains native Undo/Redo.
- Save webpages for offline reading from Anki or Companion. Choose a previewable **HTML snapshot — website appearance** or an editable **Reading copy — reflowable Markdown**. Read these documents with the existing EPUB tools and export them as standalone HTML, Markdown, or TXT. Capturing a later version creates a separate document.
- Keep grouped workspace tabs active when opening more readers, references, writing, and searches. Rename, close, resize, and color tabs; save their appearance with workspaces. Grouped web searches retain separate results tabs and share their own profile-scoped browsing session.
- Preview internal PDF links and footnotes on hover with a resizable preview, including while link navigation is disabled. Text inside noted highlights stays selectable. Overlay-only annotation edits update without reloading the main or beside reader, while changes requiring new PDF appearances still refresh the display copy.
- Preserve passage references through resource inspection and unlink/restore flows, retain reader positions across reference navigation, and keep the new state isolated by Anki profile. Refresh English, Croatian, and Simplified Chinese interface catalogs and rebuild the shipped reader and Companion assets.

Restart Anki after updating. Reload or reinstall Companion from the updated add-on and refresh pages using its capture features. Viewed coverage begins with this update; existing read-to-here markers are retained. Reading coverage, document associations, writing backlinks, and offline documents are profile-local and travel through Incremento backups rather than Anki Sync alone. Offline snapshots preserve captured content and available resources; scripts and interactive website behavior are disabled. The minimum supported Anki version remains 24.11.

[Full comparison](https://github.com/BaskovicP/Incremento/compare/v2026.11.03...v2026.11.04)

## 3 November 2026 — 2026.11.03

Changes since tag **v2026.11.01.1**.

- Keep up to 32 writing drafts in one tabbed pane beside PDF/EPUB readers. Reorder and close tabs, create or open drafts from the tab menu, and restore their order and selected draft with saved workspaces. Each tab retains its text, Undo/Redo history, reading position, appearance, bookmarks, and word-progress state; failed saves keep the draft open.
- Use a compact, theme-aware writing toolbar with paragraph and heading styles, formatting, links, images, tables, and keyboard shortcuts. Preview adapts to narrow panes, and Markdown or standalone HTML export includes the current draft even before autosave completes. An explicit translation action opens a reviewed passage in Google Translate through the selected Companion browser.
- Open the current review card's original parent in a read-only sidebar using the compact Parent icon. Parent context follows the saved extraction origin or Knowledge Tree parent while preserving the current card and question/answer side; stale commands and profile changes clear the preview.
- Limit automatic study navigation and the floating priority badge to cards using Incremento, preserving ordinary Anki card layouts. Explicit resource linking remains available from the card menu.
- Add **Last added** sorting to the Document Bookshelf, with newest or oldest documents first.
- Prevent duplicate PDF text-mark rendering after annotation synchronization and note edits. Saved highlights, underlines, squiggles, dashed/dotted underlines, and strikeouts remain editable, and small PDF coordinate differences no longer create spurious annotation conflicts.
- Stage full-backup profile copies, Anki packages, database snapshots, and ZIPs on the selected destination's filesystem, including external drives and MCP exports. Keep previous backups intact on failure and document temporary-space requirements and interrupted-export cleanup.
- Share PDF/EPUB import controls, remove obsolete helper paths, refresh English, Croatian, and Simplified Chinese UI catalogs, and rebuild shipped browser assets. Correct the parent-context test import for the full-suite import mode.

Restart Anki after updating. Writing tabs are cleared on profile changes; save a workspace to reopen them later. Translation sends only the passage explicitly opened in Google Translate and requires an internet connection.

[Full comparison](https://github.com/BaskovicP/Incremento/compare/v2026.11.01.1...v2026.11.03)

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
