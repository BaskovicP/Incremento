# Incremento - User Manual

Incremento is an Anki add-on for incremental learning from mixed content. It combines long-form material such as PDFs, EPUBs, videos, webpages, writing notes, and local files with normal flashcards, then builds balanced study sessions inside Anki.

---

## Table of Contents

0. [Installation](#installation)
1. [Core Concepts](#1-core-concepts)
2. [Incremento Menu Overview](#2-incremento-menu-overview)
3. [Starting a Study Session](#3-starting-a-study-session)
4. [Scheduler Settings](#4-scheduler-settings)
5. [Adding Content Cards](#5-adding-content-cards)
6. [PDF and EPUB Cards](#6-pdf-and-epub-cards)
7. [Video Cards](#7-video-cards)
   - [Audio Cards](#7a-audio-cards)
8. [Web, Writing, and Local File Cards](#8-web-writing-and-local-file-cards)
9. [Search and Navigation Tools](#9-search-and-navigation-tools)
10. [Statistics and Focus Timer](#10-statistics-and-focus-timer)
11. [Priorities, Extraction, and the Add Card Dock](#11-priorities-extraction-and-the-add-card-dock)
12. [Export and Restore Notes](#12-export-and-restore-notes)
13. [Settings, Utilities, and Dependencies](#13-settings-utilities-and-dependencies)
14. [Keyboard Shortcuts](#14-keyboard-shortcuts)
15. [Common Workflows](#15-common-workflows)

---

## Installation

Incremento supports Anki 24.11 and newer. When a newer Anki release changes an optional private reviewer API, Incremento disables only the affected direct-review feature and leaves card scheduling unchanged.

### Install from AnkiWeb (recommended)

Incremento is available from [AnkiWeb Add-ons](https://ankiweb.net/shared/info/1013949798).

1. In Anki, open **Tools → Add-ons → Get Add-ons…**.
2. Enter the add-on code **`1013949798`**.
3. Restart Anki after installation.

After an installation or update, Incremento may need to prepare local files and
upgrade its search indexes. A **Preparing Incremento** window shows the current
stage, an animated progress indicator, and elapsed time. Large libraries may
take a few minutes; keep Anki open until preparation finishes. This local work
runs in the background while the window remains responsive, and Anki continues
after it completes. Ordinary launches skip this window when the profile is
already up to date. Preparation does not start an AnkiWeb sync; Anki's existing
sync preferences still apply. Support bundles include the time spent preparing
files and upgrading the database to help diagnose unusually slow openings.

### Install from source

For development or manual installation, clone or copy the repository into Anki's `addons21` folder as `incremento`, then restart Anki.

| Platform | Source installation path |
|---|---|
| macOS | `~/Library/Application Support/Anki2/addons21/incremento/` |
| Windows | `%APPDATA%\Anki2\addons21\incremento\` |
| Linux | `~/.local/share/Anki2/addons21/incremento/` |

The source repository does not ship `meta.json`; Anki creates and manages that local installation metadata.

---

## 1. Core Concepts

### Topics vs Items

Incremento works with two broad card groups:

| Type | What it means | Examples |
|---|---|---|
| **Topics** | Long-form material you work through gradually | PDFs, videos, webpages, writing notes, article notes |
| **Items** | Normal fact/review cards | Basic, cloze, Q&A, vocabulary |

Incremento classifies a card as a topic when it is in the `Topics` deck, matches one of the configured topic tags, or belongs to an enabled topic content type such as PDF/EPUB, video, or writing. Configured item tags take precedence. The optional scheduler Topic and Item filters narrow these classified pools; they do not replace the classifier. Incremento can also auto-create the `Topics` deck for selected profiles from the settings dialog.

### Incremental learning

Instead of reviewing one deck in isolation, Incremento builds a temporary filtered deck called **Incremento Session**. It mixes topics and items according to your settings, keeps track of what you studied, and lets you continue long-form material where you left off.

### Persistent side docks

When you review Incremento cards, the source opens in a dock:

- PDF cards open the PDF viewer
- EPUB cards open the EPUB reader
- Video cards open the video dock
- Web cards open the web browser dock
- Writing cards open the markdown editor dock
- Local-file cards open a file-management dock

These docks persist across reviews and save progress automatically.

### Profile-isolated data

Runtime data is stored separately for every Anki profile under `user_files/<ProfileName>/`. This includes the profile's `incremento.db`, statistics, PDFs, EPUBs, videos, writing files, managed local files, and browser/video session data. Switching Anki profiles therefore switches Incremento's content and database context as well.

---

## 2. Incremento Menu Overview

Incremento adds its own top-level **Incremento** menu to Anki's menu bar.
**Command Palette…** and **Activity Center…** appear directly below **Start Incremental Learning** in the first menu section.

### Main actions

| Menu item | What it does |
|---|---|
| **Start Incremental Learning** | Build a new Incremento session |
| **Command Palette…** | Search and launch Incremento actions; unavailable actions explain why they cannot run |
| **Activity Center…** | Inspect active/recent background indexing and download work, with Cancel or Retry where supported |
| **Getting Started…** | Reopen the first-run reading/extraction/session/backup guide |
| **Settings** | Configure extraction, review, topic, writing, shortcut, and advanced options |
| **About** | Show a summary of addon capabilities and contributor credits |
| **Utils → Import SuperMemo Collection…** | Import a native SuperMemo 17/18/20 collection from its KNO file or ZIP |
| **Add Content → Add PDF / DjVu** | Import a PDF or DjVu as a topic card |
| **Add Content → Add EPUB** | Import one or more EPUBs as topic cards |
| **Add Content → Add Markdown Document…** | Batch-import rendered Markdown learning documents with preview |
| **Edit Current Markdown Document…** | Edit the open Markdown study copy with source and preview |
| **Add Content → Webpage to PDF** | Render a webpage into a PDF card |
| **Add Content → Add Audio** | Import a mobile-compatible audio topic card |
| **Add Content → Add Video** | Add a YouTube, Vimeo, or local video card |
| **Add Content → Add Markdown Writing…** | Create a writing card backed by a markdown file |
| **Add Content → Web Page** | Create a browsable web page card |
| **Add Content → Add Local File** | Create a card that opens or tracks a local file |
| **Download Current Video Locally** | Download the active remote video into the current profile |
| **Configure Current Video Captions…** | Manage target/reference captions for the active video |
| **Open Knowledge tree** | Open the card-backed knowledge-tree workspace |
| **Reveal Current Card In Knowledge Tree** | Select the current reviewer card in the tree |
| **Go To Parent In Knowledge Tree** | Move from the current tree card to its parent |
| **Show Focus Timer** | Show or hide the timer toolbar |
| **Statistics** | Open study statistics |
| **Quick Open Content** | Fuzzy-search and open PDF, EPUB, or writing cards |
| **Find In Current Document** | Open a small results dialog for the currently open PDF or EPUB, with a Search ALL handoff |
| **Search ALL** | Search PDF/EPUB highlights, sources, content, and cards |
| **Export Support Bundle…** | Create a privacy-safe diagnostic ZIP for a bug report |
| **Export Full Backup** | Create a backup ZIP |

### Utils submenu

| Menu item | What it does |
|---|---|
| **Check Dependencies...** | Check/install optional PDF and video tools, including FFmpeg |
| **Reindex PDF Text (Existing Cards)** | Rebuild searchable PDF text index |
| **Build PDF Snapshot Previews on Cards…** | Render or replace a highlighted, mobile-visible PDF screenshot for every PDF citation |
| **Import Notebook Citations to PDF Highlights…** | Import supported notebook citations as PDF highlights |
| **OCR Image Text (Existing Cards)…** | Extract searchable text from image-based cards |
| **Reindex OCR Search Cache (From Hidden Field)** | Rebuild cached OCR search text |
| **Clean Up Unused Data & Images…** | Review and clean unused PDF/video files, image attachments that Anki reports as unused, and stale progress/search/OCR records with one confirmation |

---

## 3. Starting a Study Session

1. Open Anki.
2. Choose **Incremento → Start Incremental Learning**.
3. Adjust the scheduler settings or accept the defaults.
4. Incremento builds the **Incremento Session** filtered deck and opens the reviewer.

If you leave before finishing, Anki keeps the unfinished cards in **Incremento Session** so you can open that deck and continue later. Completed cards return to their original decks automatically. Incremento leaves this live queue untouched while exiting, so returning to the deck list does not trigger another potentially slow deck rebuild.

The session dialog also supports:

- a **Basic** view for the preset, card count, Topic/Item mix, Documents within Topics, summary, and preview
- an **Advanced** view for every scheduler quota, filter, card-state, ordering, and diagnostic control
- named presets that you can save, load, rename, and delete
- optional live preview before starting
- branch-scoped study when launched from the knowledge tree

When a named preset is selected, clicking **OK** saves the current scheduler setup back into that preset before starting the session. You do not need to click **Save** separately. **Current Settings** continues to save only the shared dialog state.

Basic and Advanced edit the same setup. Switching views does not reset anything, and Incremento remembers the last view you used. New users also receive a short versioned first-run guide; use **Incremento → Getting Started…** to reopen it at any time.

Good first-run defaults:

- 50 cards
- 90% topics / 10% items
- 99% random / 1% priority
- 0% Docs in the soft document mix
- all card states enabled

---

## 4. Scheduler Settings

### Cards per session

Controls how many cards Incremento puts into the session.

The accepted range is **1–9,999 cards**. Large catch-up sessions use the same scheduling rules; Incremento stops searching once eligible pools are exhausted instead of continuing to retry up to the requested total.

If you later enable **Auto-refill session deck to keep this many unreviewed cards** in **Advanced**, this same number becomes the live not-yet-answered card target. Incremento preserves learning repeats in the filtered deck, so Anki's visible queue can temporarily be larger than this count.

### Card states to include

You can include any combination of:

- **New**
- **Learning**
- **Due / Review**

To let never-seen cards enter Incremento sessions at all, keep **New** enabled here. If **New** is off, auto-refill can still top up the session, but it will only pull from the other enabled card states.

If all three boxes are off, no ordinary topic/item card is eligible. Incremento document and media cards remain state-independent, as indicated in the dialog.

### Topics <-> Items balance

Controls what share of the whole session goes to Topics versus Items. Topics include document-reading cards; the next slider divides only the Topic portion.

- Move left for more topics
- Move right for more items

Incremento also shows the current number of ready topic and item cards.

The 0% and 100% endpoints are exact: a bucket set to 0% is disabled and is not reintroduced by scheduler smoothing or empty-pool fallback. For example, an Items-only preview with no matching Items reports fewer scheduled cards instead of substituting Topics.

### Documents within Topics (%)

Controls what percentage of the Topic portion targets PDF and EPUB reading cards. It does not reduce the Item allocation. The remaining Topics are non-document Topics.

- Move left for more documents within Topics
- Move fully right for 0% document Topics in normal mixing
- Move fully left to target only documents within Topics

For example, 100 cards with 60% Topics / 40% Items and 10% Documents within Topics targets **6 Documents + 54 other Topics + 40 Items**. It is not 10 documents out of the whole session. Integer estimates split Topics/Items first, then divide the Topic allocation; actual soft scheduling depends on available cards and the balancing scope.

At 100% Items, the document control is disabled and displays 0%; its saved preference is retained for when Topics are enabled again. PDFs and EPUBs explicitly classified as Items remain eligible as Items and do not consume the document-Topic target. Regular flashcards extracted from a document are not automatically document-reading cards.

The estimate table separates Documents (Topics), Other Topics, and Items. It runs the actual session selection in the background, using the current tags, card states, filters, quotas, and branch scope. If only 20 cards can be selected for a 500-card target, the count shows **20 / 500** and the table totals 20. While recalculating, the table clears instead of displaying the requested target as available cards.

Documents plus Other Topics form the Topic total. Percentages inside each table column describe tag shares, not Topic/Item percentages. The first Total row shows the selected count for each content column and the whole session. The expected-mix percentages still describe your configured preferences.

The table, **Live card preview**, and session startup share one selected list, including random choices. Opening Live card preview loads the details for that list without drawing new cards. **Refresh** replaces the shared selection and updates both views. Starting with an up-to-date result reuses its exact cards and scheduling metadata. Changing session settings clears both views until the new selection is ready.

Suspended and buried cards, and cards already in a different filtered deck, are excluded from this selection because Anki cannot admit them to the session deck. Unfinished cards in the same session deck remain eligible.

The optional **Require an up-to-date preview before starting** checkbox blocks startup until the current selection is available. If it is off and startup occurs before the background preview finishes, Incremento selects cards during startup. An already displayed current selection is reused in either mode.

Document Topics are eligible regardless of New/Learning/Due state and respect Topic classification, Topic filters, and active tag constraints. Separate Advanced content-type priorities can still reserve document places independently before the normal mix; these explicit overrides can change the final allocation, including in an Items-only setup.

Saved setups from the previous whole-session document mix are converted once, including named presets and the legacy preset alias. The conversion preserves the old expected three-way mix as closely as whole-percent sliders allow: for example, the old 66% Docs / 100% Items setup becomes 66% Topics / 34% Items with 100% Documents within Topics. Unknown settings and locks are retained; documents no longer share the main slider balancing pool. Small rounding differences and explicit classification overrides can affect the resulting counts.

### Priority <-> Random balance

Controls how cards are selected within each bucket.

- **Priority** favors more urgent cards
- **Random** samples more freely from eligible cards

### Scheduler scope

The balancing memory can apply to:

- **This session**
- **Today**
- **All time**

For **Today**, the shared **Day ends at** setting in **Incremento → Settings → Review → Statistics** defines a late-night cutoff like `04:00`. It also controls Incremento's daily statistics, tag charts, and focus-timer day. Click **OK** in Settings to save it without starting a session. Existing saved cutoff times are retained; switching session presets does not change the cutoff.

### Scheduling priority order

With **Strict enforcement** enabled, Incremento fills quotas in the order you choose:

- **Tags**
- **Type**
- **Mode**

Each phase tries to reach a rounded card-count target using the available slots. For example, 20% of 10 cards gives the Tags phase a target of 2 cards. Earlier phases, overlapping tags, and available cards affect the final mix; this is not an unconditional percentage guarantee.

### Tag quotas

You can allocate part of each session to specific tags:

1. Type a tag name in the editable picker or choose it from the dropdown, then click **Add…**. Suggestions match any part of an existing tag name, ignoring case. Repeat to add more tags.
2. Set each tag percentage.
3. Lock any tag whose share should stay fixed, or use **Lock all tags** to lock every current tag row at once. When all rows are locked, the same button becomes **Unlock all tags**.
4. Use **After exhausting tag groups, fill with rest of cards** if you want leftover slots topped up automatically.

The always-present **Other** row excludes every active selected tag, including its subtags. For example, with `spiritual` selected, neither `spiritual` nor `spiritual::prayer` can enter through Other. Cards may still have unrelated tags; they do not need to be untagged. This applies to topics, items, documents, media, leftover-slot filling, and auto-refill. When no specific tags have been added, Other is necessarily 100% and its slider is disabled. Adding a tag restores the normal editable balance.

With auto-refill, quota counts continue across the same session; they do not reset for each refill or each ten-card pending window. Strict tag targets use cards selected in that session. Soft mode adjusts selection probabilities using the chosen statistics scope, so **Today** can compensate for earlier reviews that day. Neither mode promises exactly 2 matching cards in every visible window of 10.

By default, document and media picks also respect active tag rows. For example, if your session only has `data` and `statistics` tag quotas, PDF, EPUB, video, and webpage picks must match those tags instead of falling back to unrelated content.

### Filters

These are standard Anki search filters:

- **Topics filter**: what counts as a topic card
- **Items filter**: what counts as an item card

Both fields are blank by default. Incremento first classifies cards with its configured topic note types/tags, item tags, and Topics deck behavior; an optional filter here narrows the corresponding classified pool further.

Use the **Test** buttons to see how many cards currently match.

### Advanced session options

Open **Advanced** in the session dialog for a few session-behavior controls:

- **PDF Daily Reading Limit**: select a PDF and set its daily page cap and enforcement mode. This panel is inside the collapsible Advanced section.
- **Present cards in scheduler order**: shows cards in the exact order selected by the scheduler instead of randomizing them.
- **Auto-refill session deck to keep this many unreviewed cards**: keeps the active **Incremento Session** deck topped up to your **Cards per session** count of not-yet-answered cards as you study. Learning repeats stay in the filtered deck, so the visible Anki queue can temporarily exceed this number.
- **Allow document/media picks outside selected tags**: restores the older fallback behavior where a PDF, EPUB, video, or webpage tag miss can be filled from any card of that content type. Leave this off when tag quotas should be strict.

### Debug mode

**Show debug information** displays the exact selected cards before the session starts.

### Statistics history buttons

The dialog also has buttons to delete session, daily, and lifetime statistics or export them as JSON. Export includes the recorded daily reading/study timeline as well as the existing aggregates.

---

## 5. Adding Content Cards

Incremento now supports several kinds of topic material.

### Import SuperMemo Collection

Use **Incremento → Utils → Import SuperMemo Collection…** and select either a ZIP containing one matched `.Kno`/collection-folder pair or the `.Kno` file beside its collection folder. Incremento validates and previews the import before changing Anki. Native structure versions 20–22 (used by supported SuperMemo 17/18/20 collections) are accepted; incomplete, ambiguous, unsafe, or unknown layouts are rejected rather than guessed.

The import creates **Incremento SuperMemo** notes in the deck you choose. Items with one SuperMemo `[...]` omission and a separate answer become genuine **Incremento SuperMemo Cloze** notes: the answer replaces the marker as Anki `{{c1::answer}}` text. Other items remain normal Q/A cards. Formatted text comes from SuperMemo's native HTML files, so paragraphs, emphasis, lists, tables, links, colors, and safe inline styling are retained. Registered local GIF, JPEG, PNG, WebP, and BMP images are copied into Anki media with stable collection-scoped names and displayed responsively on every linked card; shared images are copied once. Active markup such as scripts, event handlers, embedded objects, forms, and unsafe URLs is removed rather than executed.

The importer maps topics/concepts to Topic cards, the knowledge tree to Incremento's existing knowledge tree, and SuperMemo's priority queue to Incremento priority values. Deleted elements are skipped, with surviving descendants attached to the nearest surviving ancestor. Memorized cards retain their current interval, due date, repetition count, and lapse count. A-factors and forgetting indexes are retained in Anki card state; topic A-factors also seed Incremento's existing topic schedule. SuperMemo repetition history is restored to Anki's revlog: grades 1–5 become Anki answer grades, while topic and initial-memorization records become manual history entries so they do not invent scheduler answers. Native reference titles, safe HTTP(S) links, and source names populate Incremento's existing provenance fields. Anki's scheduler is authoritative for all future reviews.

SM8 and SM17/SM20 optimization records are preserved byte-for-byte with sizes and SHA-256 checksums under `user_files/<ProfileName>/supermemo_imports/<collection-fingerprint>/optimization/`. They are archival input only and are not applied to Anki's scheduler. No new Incremento database tables are created for SuperMemo metadata.

The importer deliberately excludes SuperMemo aggregate statistics/workload/outstanding queues, task scheduling and task elements, component window geometry, templates, scripts, OLE objects, and executable components. Text questions, answers, topic text, safe HTML formatting, registered images, hierarchy, references, and scheduling/history data are imported; unsupported active or layout-only components are never executed. Importing the same collection fingerprint again skips cards identified by their compact SuperMemo identity in Anki card custom data; older imports using the internal SuperMemo provenance link remain recognized.

Because historical revlog rows must be restored directly, this bulk import is not an Anki Undo operation. Make an Anki profile backup before confirming the preflight. Parsing and ZIP extraction run outside the collection thread; the collection change is serialized and is cancelled if the active profile changes.

### Add PDF / DjVu

Use **Incremento → Add Content → Add PDF / DjVu** to import one or more PDF or DjVu files into Incremento. DjVu documents are converted to PDFs while preserving existing selectable text; see the DjVu import guidance below. When Tesseract is available, **OCR all possible** selects every document that can use OCR—including documents whose text check finishes after you click it—and **Don't OCR anything** clears every OCR choice. Documents with usable text or without the required OCR tools remain unchanged.

This creates an **Incremento PDF** note and copies the PDF into `user_files/<ProfileName>/pdfs/`.

### Add EPUB

Use **Incremento → Add Content → Add EPUB** to import one or more EPUB books.

Incremento stores the source EPUB under `user_files/<ProfileName>/epubs/` and extracts readable section data under `user_files/<ProfileName>/epub_extracted/` for the reader and search features.

### Add Markdown Document

Use **Incremento → Add Content → Add Markdown Document…** to import UTF-8 `.md` or `.markdown` files as rendered learning documents. The split dialog provides **Add files…**, **Add folder…**, a filename filter, import checkboxes, per-file tags and priority, and a rendered preview on the right. **Select all / Deselect all** affects only visible rows; checked hidden rows still import. Global tags are combined with each file's tags. Titles use each filename by default; uncheck **Use file name as title** to supply a shared title. Choose the destination deck, then **Add**. A batch accepts up to 1,000 files; folder discovery scans at most 50,000 entries. Preview is text-only and does not load images or activate links. This is separate from **Add Markdown Writing**, which creates an incremental-writing card.

Markdown is rendered into a managed EPUB study copy, so it uses the existing document reader rather than the writing editor. It supports headings, emphasis, lists, tables, fenced code blocks, and footnotes. Level-1 and level-2 headings start reader sections; a file without headings becomes one section. Highlights, selection-to-card extraction, bookmarks, in-document search, Search ALL, reading markers/progress, reading limits, and Review All use the same EPUB/PDF-style workflow. Open the document from **Document Bookshelf → All documents / EPUBs**, Quick Open Content, or its study card. Its note type, scheduling, and statistics are EPUB-backed; provenance identifies the source as Markdown.

The original file is never edited. Its exact Markdown bytes and supported local PNG/JPEG/GIF/WebP images are included in the managed EPUB under `user_files/<ProfileName>/epubs/`; the reader/search cache lives under `epub_extracted/`. Changes to the original after import do not update the study copy. Images must be regular files inside the Markdown file's folder (including subfolders), not symlinks or escaping paths. Missing/unsupported/remote images show their alt text. Scripts, active HTML, user CSS, and remote resources are removed; external HTTP(S) links remain opt-in through **Links On** and open in the system browser. Limits are 2 MiB of Markdown, 8 MiB per image, 128 images / 48 MiB total, and 2,000 reader sections.

To edit the open study document, use the reader's **Edit Markdown…** button or **Incremento → Edit Current Markdown Document…**. Edit the source alongside its live, text-only preview and choose **Save document**. Saving updates the same document and its search index, then refreshes the reader. It does not change the Anki note, scheduling, tags, priority, or extracted cards. Embedded images are retained even if the original image files are gone; new local or remote image files are not loaded from the editor. One previous managed EPUB version is kept at `user_files/<ProfileName>/markdown_backups/<document-filename>.epub`; a later successful save replaces that backup. Highlights, bookmarks, reading progress and saved reader links remain, but editing headings or text may move their positions. A concurrent document change rejects the save; reopen the editor to load the latest version. Closing with unsaved changes asks before discarding them.

The import runs in the background and captures the current Anki profile. **Settings → Shortcuts → Add Markdown Document** can assign a key; there is no default shortcut. The command is also available in the Command Palette.

### Webpage to PDF

Use **Incremento → Add Content → Webpage to PDF** when you want a normal PDF-style reading workflow for an online article.

After a successful import, the confirmation offers **Open PDF** to open the newly imported card in Incremento's PDF reader immediately. Choose **Close** to keep working without opening it. The confirmation does not block Anki.

Choose **Website appearance** to preserve the site's screen layout, or **Clean article** for consistent typography and margins with navigation, comments, and sharing controls removed. Both retain article images, tables, and ordinary clickable links. **Include a list of link destinations** adds a deduplicated appendix of up to 500 external destinations; it does not download the linked pages. In the PDF reader, enable **Links** to follow them.

With **Website appearance**, enable **Preview and remove elements before saving** in this dialog. After capture, an offline preview lets you keep the article and loaded comments while removing unwanted navigation, banners, or sidebars. Hover to see the removal target, then click to hide it; **Shift-click** targets its parent container. **Undo removal** restores the last element and **Reset** restores everything. Turn **Zap elements** off to select text, then choose **Save PDF** when ready. These edits affect only this import. The preview keeps page scripts and network access disabled; it cannot load more comments or expand interactive controls. Cancel or switch profiles to abandon the import. Editing time is separate from the capture timeout.

**Load content added by JavaScript** uses a disposable Chromium browser through Playwright. It waits for initial background requests, expands HTML details sections, scrolls a bounded distance to trigger lazy loading, and waits for images and fonts before printing. The browser component is enabled after **Set up browser component…**, an explicit download into Incremento's local dependency folder. It requires a compatible Python interpreter and supported Chromium system libraries; setup never modifies Anki's Python environment. It is already selected on later opens when the component is available. Dynamic captures have a 90-second limit. Closing the dialog or switching profiles cancels the capture. Login-only content, embedded frames, POST-based data requests, and interactive controls may not appear in a static PDF.

Without dynamic content, Incremento fetches the public HTTP(S) page together with its styles, fonts, and images in the background, verifies HTTPS certificates and redirects, and prints a guarded offline snapshot with scripts and embedded frames disabled. Downloads have time, count, and size limits. An unavailable optional image or font does not discard the article.

For streamed React pages such as LessWrong, completed server-rendered article and comment fragments are placed into their document positions before sanitizing. This prevents the hidden streaming containers from producing a blank PDF without executing the site's scripts. Choose **Website appearance** to retain comments supplied in the page response.

If the site returns HTTP 403/429 or a recognized CAPTCHA/login page, **Import** automatically opens a verification handoff in your selected Companion browser. Choose Chrome (the default) or Firefox in **Incremento → Settings → Review → Reviewer Controls → Companion browser** and load the corresponding Companion extension. The first time you use a site, Companion asks for permission to capture that site (including the archive aliases for archive.is). After that one-time setup, finish the CAPTCHA and wait: Companion detects the readable page, sends its rendered HTML back to the waiting import, and Anki saves the PDF, returns to the foreground, and shows the same **Open PDF** confirmation. There is no capture shortcut, Print dialog, saved-file picker, or second import confirmation. The original dialog's title, tags, layout, link appendix, and source URL are retained. Closing the browser tab reports failure; cancelling the Anki dialog or switching profiles prevents a late import. The request expires after ten minutes. Unrecognized challenges or redirects to a different article may need the manual alternatives below.

You can also start directly in the browser: finish verification, then press **Option+Shift+P** on macOS (**Alt+Shift+P** elsewhere), or choose **Capture opened page as PDF** in Companion. The popup lets you edit title, deck, tags, and priority; the shortcut uses the page title and standard import defaults. This browser-first route uses Companion's layout/link preferences. Both routes include JavaScript content already loaded in the tab, without transferring cookies or requiring the separate browser component. The captured document does not require Anki to resolve or download its source address again. Each optional image, stylesheet, or font download still passes the public-network checks; blocked or unavailable resources are omitted while the article text is retained. Resources requiring sign-in may also be missing.

Without Companion, choose **Open in browser**, complete verification, and use **Print → Save as PDF**, then **Use browser-saved PDF…** here. This keeps this dialog's title, tags, and source URL and imports a separate study copy without changing your saved original. Select a regular PDF of at most 48 MiB; its layout comes from the browser's print settings. Incremento does not solve CAPTCHAs automatically; rate-limited sites must allow browser access before capture.

**Website print layout (Wikipedia PDF)** uses the site's print styling. For Wikipedia article URLs without a link appendix, it first requests Wikipedia's official PDF service, preserving the clean article layout, images, tables, and citations. If that service is unavailable, it uses the selected browser or offline renderer. Restart Anki after updating the add-on, then import a page again to regenerate an existing PDF.

In the Chrome/Brave Companion popup, **Settings → Webpage to PDF** provides the same three layouts, JavaScript loading, and link-destination appendix. Click **Save** to apply them to **Add as PDF** and its keyboard shortcut; **Cancel** discards edits. The extension keeps these defaults separately in the browser profile. JavaScript loading requires the browser component set up through the Anki dialog above and reloads the public page without Chrome cookies. Existing PDF files are imported unchanged. Reload the extension after updating Incremento.

This is useful when you want:

- page-based reading progress
- PDF highlighting
- PDF extraction shortcuts
- a stable offline snapshot of the article

### Add Video

Use **Incremento → Add Content → Add Video** for:

- YouTube URLs
- Vimeo URLs
- local video files

For remote videos, you can keep them as streaming links or download/compress a local copy into `user_files/<ProfileName>/videos/`.

For local files, Incremento can either:

- keep original quality
- encode H.264 high quality
- encode H.264 smaller size

### Add Audio

Use **Incremento → Add Content → Add Audio** to choose an MP3, M4A, AAC, or WAV file. Incremento copies it into Anki media, creates an **Incremento Audio** topic card in the `Topics` deck, and uses the filename as its title. The individual file must stay within AnkiWeb's 100 MB media-file limit; MP3 is the most portable and space-efficient choice.

The player is part of the card template, so it works in desktop Anki, AnkiMobile, and AnkiDroid without an Incremento mobile add-on. It restores the last playback position stored by that Anki client. This position is local to each device and does not synchronize through AnkiWeb. Finishing the audio clears the saved position so the next playback starts from the beginning.

### Add Markdown Writing

Use **Incremento → Add Content → Add Markdown Writing…** to create an **Incremento Writing** note backed by a markdown file under `user_files/<ProfileName>/writing/`.

You can provide:

- title
- optional filename
- tags
- deck
- initial markdown

### Web Page

Use **Incremento → Add Content → Web Page** to create a browsable **Incremento Web** card.

Unlike **Webpage to PDF**, this keeps the content as a live webpage inside the dock instead of converting it into a PDF.

### Add Local File

Use **Incremento → Add Content → Add Local File** to make a card for any local document or asset that you want to open from review.

You can either:

- keep a reference to the original file path
- import a managed copy into Incremento's profile data

### Browser extension import

**Incremento → Settings → Review → Reviewer Controls → Companion browser** offers **Chrome** (default) and **Firefox**. Save with **OK**. This selects both the companion allowed to connect and the browser used for web-card pages and homepages, video/resume links, PDF/EPUB external links, and webpage verification. Switching invalidates the previous companion connection; choose Chrome again to return to the existing setup. No cards or media are migrated. For webpage verification, the selected browser supplies the verified page and Incremento’s internal renderer makes the PDF. If the selected browser is unavailable, the action reports an error; it does not silently open another browser.

Firefox 140+ support is a local development preview. Select **Firefox** and click **Set up browser extension… → Export Firefox extension…** to save a loadable `.xpi` file without build tools. Open `about:debugging#/runtime/this-firefox` in Firefox, click **Load Temporary Add-on**, and select that file. Close the setup guide and save Settings with **OK**. Keep the file: temporary add-ons must be loaded again after Firefox exits. Export a new file after updating Incremento. Nothing is published automatically. See the [Companion installation guide](chrome_extensions/incremento_companion/README.md#firefox-local-preview) for details and the optional developer command.

For Chrome, the same setup button shows installation instructions and a **Show Chrome extension folder** action. Browser settings are saved only when you accept Settings; opening a guide or exporting a file does not change the selected browser.

In Firefox, assign shortcuts through **Add-ons and themes → Extensions → gear menu → Manage Extension Shortcuts** and keep Firefox focused. Companion's shortcut-settings button opens instructions. The Chrome scope instructions below apply only to Chrome. Settings, site permissions, and bookmarks remain separate in each browser.

If you install the optional companion extension in your selected browser, it can send the current page to Incremento as:

- a PDF
- a video
- a web page card
- a writing card

It can also sync watched YouTube/Vimeo time back into Incremento video cards.

For one-click link import, enable **Enable right-click link action** in the Companion popup, choose the **Right-click destination deck**, and save the quick-link settings. Right-click a link and choose **Add link to Incremento**. Every card created by this action receives the `topic` tag and goes to the selected deck. Supported YouTube and Vimeo links automatically create Incremento Video cards, while other HTTP(S) links create Incremento Web cards. The clicked link is imported without opening it first, and supported video timestamps are preserved.

The popup and the full text/snapshot capture form load existing tags from the active Anki profile. Focus the tag field or type any part of a tag to open suggestions, then click one or use the arrow keys with Enter/Tab. Completion replaces only the tag currently being typed, so other space- or comma-separated tags remain intact; new tags are still accepted.

In the popup, enable **Remember tags for this website** below Tags to restore that set whenever you reopen the popup on the same website. It saves the current tags immediately and updates them automatically as you edit; wait for **Saving website tags…** to disappear before closing. The match uses the exact hostname across all pages, HTTP/HTTPS, and ports; subdomains have separate sets. Disable the checkbox to forget that website while retaining the current input. The option defaults off and stores remembered hostnames and tags in the active Anki profile's `incremento.db`, so they are included in normal backups and kept separate between profiles. Anki must be open. If loading or saving fails, use the visible **Retry** action. Each profile can remember up to 1,000 websites, with up to 100 tags of 200 characters each per website.

Text and snapshot capture also start with the remembered website tags, including snapshot **Extract now**. These replace older capture-tag defaults; remembering an empty set leaves the Tags field blank. Note type, deck, priority, and field mappings retain their saved choices. Starting capture from the popup waits for the current website-tag save to finish.

The capture form initially focuses **Create note**. With saved field mappings, select text, press **Option+X** on macOS (**Alt+X** elsewhere), then **Enter** to create the note. Enter also submits from ordinary form inputs. In the selected-text editor, Enter keeps adding newlines; with tag suggestions open, it accepts the selected tag first. Holding Enter or pressing it while a note is being created cannot submit the same capture twice. Existing field/content validation still applies.

Text capture waits briefly for extension startup; note creation is never automatically resent after a connection failure. If Companion reports a disconnected extension, reload **Incremento Companion** in **Chrome → Extensions**, then reload the webpage before trying again. These steps also replace old background/page code after an unpacked extension update. If **Option/Alt+X** does nothing, check its **Text capture** assignment and **In Chrome** scope in **Chrome → Extensions → Keyboard shortcuts**.

For snapshot regions, use Chrome's registered **Snapshot capture** shortcut: **Option+Shift+X** on macOS, **Alt+Shift+X** elsewhere, unless you changed it in **Chrome → Extensions → Keyboard shortcuts**. Set its **Scope** to **In Chrome**. **Global** shortcuts do not grant Chrome's temporary screenshot permission, even when used inside Chrome; Companion shows the scope instructions instead of starting an unauthorized capture. A page-only key handler cannot grant that permission either, so the older **Option+Command+X** combination shows the registered shortcut or assignment instructions. You can also click the Companion toolbar icon on the page and choose **Trigger snapshot capture**. Keep the original tab active while drawing; a tab switch cancels that region capture. Broad all-sites access is not required.

Both text and snapshot capture shortcuts default to **In Chrome** on a new installation. Chrome retains any scope you previously changed; extensions cannot change that saved setting automatically. Existing **Global** assignments need a one-time change in Chrome's shortcut settings. If another extension already uses the suggested keys, Chrome may leave the shortcut unassigned; the Companion popup shows its assignment and provides **Open shortcut settings**.

Shortcut and snapshot-permission warnings also include **Open shortcut settings**, which opens Chrome's shortcut settings in a new tab. The warning stays visible until you open settings or choose **Dismiss warning**. If Chrome cannot open settings, the warning shows an error and lets you retry.

The **Source URL field** inserts a clickable page-title link. **Link to the original passage** defaults on and retains the original selection when you edit the excerpt; switch it off for a normal page link. Passage navigation depends on browser support and unchanged page text, with the source page as fallback. Older browser captures with source metadata also gain a clickable source during review without modifying their templates. Captures keep safe paragraphs, lists, emphasis, and code formatting, remove page clutter, and use cleaned plain text after you edit the excerpt.

Use **Page title**, **Selected text**, deck, tags, and mappings to adjust a capture, then choose **Preview** to inspect each field and its clickable source before saving. Preview is read-only; the selected Anki template determines the final layout, and first-field title mappings get a unique label on creation. Capturing the same passage again offers **Open existing note** or **Create another**. Duplicate checks stay within the current profile and ignore deleted cards and whitespace/formatting differences. Older captures can be recognized when they retain source metadata. No note-type fields are added automatically; map the source URL to a visible field when metadata fields are absent. Switching Anki profiles invalidates an open capture form; reopen it before saving.

You can keep multiple Chrome/Brave tabs open. Companion coordinates bridge reconnects, uses an origin-preserving local handshake for deck/tag metadata, keeps that loading independent from inspection of the current page, and serializes optional AnkiConnect video-time updates so one problematic or busy tab does not blank the popup metadata for the others.

If you switch Anki profiles or the selected Companion browser while a request is waiting, that request fails instead of accessing the new profile. Reopen the extension popup in the intended profile and try again. Requests that time out before their queued Anki action starts are cancelled and cannot create cards later.

Text and snapshot capture use the same authenticated, origin-preserving metadata requests as the popup. If an older Companion build reports **This Companion copy is not authorized** only when starting capture, update and reload the extension, refresh the page, and retry. If the popup also reports that error, restart Anki so the intended Companion copy can reconnect.

When you choose an import action such as **Add as Video**, the popup shows each stage: reading the current tab, preparing the card and destination, and waiting for Incremento/Anki to create it. The final message confirms the created card or names the stage where the operation stopped, along with the underlying error when available. The whole popup border appears once—green after confirmed creation or red after failure—stays steady briefly, then fades out once, without taking focus or blocking another click; reduced-motion mode uses a steady brief border. A failed import also shows a selectable diagnostic report and **Copy error details**. The report contains the extension version, action, stage, reason, stable error code, and applicable scope/size counters. **Anki detail** shows the specific rejection returned by Anki, alongside the HTTP status and Anki's validation, content-preparation, or card-creation stage when available. PDF failures also show the selected layout, JavaScript-loading option, and link-appendix option. The report does not attach the page, import payload, card data, or connection credentials. If conversion detects a CAPTCHA or login page, complete it in the original browser tab and choose **Capture opened page as PDF**. Failed imports are not automatically resent.

**Add Page to Markdown** reads only the selected content scope. **Main content** prefers the page's semantic article/main region and removes scripts, styles, embedded frames, hidden elements, and navigation chrome before enforcing the capture limit. Video, Webpage, and selection-only actions read page metadata without serializing the full HTML, so a large background DOM does not block those actions. **Entire page** intentionally remains subject to the full safety limit after non-content nodes are removed.

---

## 6. PDF and EPUB Cards

PDF cards remain the most feature-rich workflow in Incremento.

### Importing DjVu documents

Choose **Incremento → Add Content → Add PDF / DjVu** and select `.djvu` or
`.djv` files, or a folder containing PDFs and DjVu documents. Titles, tags,
priority and the import checkboxes work the same for both formats.

Incremento converts DjVu documents in the background into managed PDFs, keeping
the existing text layer and its positions. The resulting card uses the PDF
reader, Document Bookshelf, search, highlighting and extraction tools. The
original DjVu file is left untouched. Cancel stops conversion and pending imports; documents
already imported remain available.

Select a DjVu row to choose **PDF compression for this DjVu** in the preview
panel. Each file has its own choice, retained while the import dialog is open:

| Choice | Image quality |
| --- | --- |
| **Layered compact — black foreground** | Keeps a sharp full-resolution black text/line-art mask over a compressed 120 dpi colour background. Foreground colours become black. If a document has no usable DjVu layers, Incremento safely falls back to Compact colour. |
| **Compact colour** | 200 dpi colour with JPEG compression; a smaller conventional PDF when the layered mode is not suitable. |
| **Balanced colour** | 300 dpi colour with JPEG compression; fine details may soften. |
| **Small grayscale** | 200 dpi grayscale with JPEG compression; removes colour and may soften small symbols. |
| **Black and white** | Original-resolution black-and-white rendering; colour and shading can disappear. Image-only pages may remain grayscale. |
| **Archival lossless (very large)** | Original resolution and colours with lossless image compression. This can expand a small DjVu into a PDF hundreds of megabytes in size. |

Selecting a DjVu row automatically samples up to eight pages spread through the
book, including the first and last pages. Unless you already chose a mode for that
file, Incremento then selects the smallest estimate among Layered compact,
Compact colour and Balanced colour. You can override that choice. Switch modes to
compare the estimated PDF size range, percentage change against an archival
lossless PDF, and the sample-page preview. **Estimate sizes** retries the estimate
when needed. The source DjVu size is shown separately: a compressed PDF can still
be larger than the DjVu. Incremento displays an extra warning when the estimate is
at least ten times the source size or reaches 250 MiB. Use the preview page
selector to inspect interior text and diagrams as well as the cover.
Estimates use the same conversion settings as import and include existing OCR
text. They are approximate, can show an increase, and may change if new OCR runs.
Short documents of eight pages or fewer are measured in full. Estimation runs
offline in the background, can be cancelled, and creates no cards or managed
files. Choosing another file or closing the dialog cancels pending estimation;
failure to estimate does not prevent importing with the chosen setting.

Every compression choice preserves existing selectable text and its page
coordinates. Layered compact keeps text and line art sharp while compressing the
photographic background separately, but turns foreground colours black. Check
small mathematical symbols, faint lines, and shaded or coloured diagrams before
choosing the smaller modes. This control applies to new DjVu imports; existing
PDFs are not rewritten.

DjVu import requires **PyMuPDF** and **DjVuLibre** (`ddjvu` and `djvutxt`).
Check **Incremento → Utils → Check Dependencies…** for installation guidance.
On macOS, install DjVuLibre with `brew install djvulibre`; on Debian/Ubuntu,
use `sudo apt install djvulibre-bin`. On Windows, install DjVuLibre and add its
tool directory to PATH. Restart Anki after installing dependencies.

Existing DjVu text is reused without running OCR again. OCR words may extend
outside their enclosing line or paragraph boxes as long as they remain inside
the page; their original positions are preserved. Symbols missing from the
primary font use bundled fallback fonts without downloading anything.
**Use OCR** is optional
and runs only when the whole document has no usable text layer and Tesseract is
available. Use **OCR all possible** or **Don't OCR anything** to set every eligible
PDF and DjVu row at once. Without OCR, image-only documents can still be read,
but their text cannot be selected. DjVu outlines and hyperlinks are not transferred. Indirect
multi-file documents must first be bundled into one DjVu file. Invalid or
unsupported text layers fail visibly instead of silently losing their text.
Conversion limits are 256 MiB input, 1 GiB output, 5,000 pages, 8 MiB of text per
page and five minutes per DjVuLibre command.

### What a PDF card stores

Each PDF note includes:

- **Title**
- **PDF_Filename**
- **Content** for searchable extracted PDF text

### PDF viewer basics

When a PDF card is reviewed, the PDF dock opens on the right.

The Windows PDF-loading regression in version `2026.10.25.224930` can show
**Could not load this PDF** for valid PDFs. After installing the fix, restart
Anki and reopen existing PDF cards; re-importing the files is unnecessary.

Large PDFs load the bytes needed for the current view first. Nearby pages are
prepared gradually while you pause, up to five pages in either direction.
Image-heavy pages use a smaller cache to limit memory; hidden readers release
their neighboring pages. Text selection and formatting share extracted page text,
and zooming reuses it. Footnote previews release their page resources when evicted
or closed with the reader.

Annotation edits appear immediately. Saving those edits into the PDF waits briefly
for rapid changes to settle, then runs in a separate process so native PDF work
does not hold up Anki's interface. **Sync now** starts immediately.
Unchanged files reuse verified page-content fingerprints while still checking for
external file changes. The worker uses the compatible Python interpreter and
PyMuPDF installation described under **Dependencies**; missing dependencies are
reported without installing anything automatically.

Click **PDF focus** in the PDF's bottom toolbar to hide the left Anki pane—including the deck list on the Decks screen—and give the PDF the full available width. Focus also hides Anki's top navigation bar (Decks, Add, Browse, Stats, Sync), restoring its previous visibility when focus ends. The toggle stays available in both the expanded and minimized toolbar, with no extra row above the document. It works from Decks, the deck overview, and during review, including PDFs opened from the Document Bookshelf or as references. The button stays pressed while enabled. Anki's answer controls remain below the reader during review. Click it again to restore the previous docked or floating layout without reopening the PDF or losing your place. The choice is saved immediately and remembered after restarting Anki; you can also change it under **Settings → Review → PDF focus**. Switching to a regular flashcard, leaving review, or closing the reader automatically restores the Anki pane without clearing your preference, so focus resumes the next time you open a PDF.

Press `Option+Shift+P` on macOS (`Alt+Shift+P` on Windows/Linux), or choose **Incremento → Document Bookshelf**, to open a searchable visual shelf of imported PDFs and EPUBs. Use **Show** inside the dialog to switch between **All documents**, **PDFs**, and **EPUBs**. **Possible duplicates only** compares document titles and reconstructed original filenames within the same document type, plus the standard embedded `Title` metadata between PDFs. PDF metadata is read and cached in the background, so opening the shelf does not wait for every PDF; hover a PDF tile to see the discovered metadata title. Generic metadata such as `Untitled` is ignored. The matcher combines case-insensitive word matching, lower weight for words that occur in many shelf entries, and three-character groups (trigrams) that tolerate punctuation, word-form, and small spelling differences. Numeric parts such as years or volume numbers must match. Treat the results as candidates rather than guaranteed byte-for-byte copies. While **Possible duplicates only** is selected, Incremento checks candidate documents for live attached Topic or Item cards in a background collection query. A green check appears over the top-right of a cover when attachments exist; hover it to see the distinct card count. This marker can help identify a copy on which you have already worked, but it does not change the duplicate score or choose which copy to retain. Right-click any tile and choose **Show in Finder** on macOS or **Show in File Explorer** on Windows to select its stored PDF or EPUB file; Linux opens the containing folder. This action is disabled when the stored file is unavailable. The same menu lets you delete that document or, when it belongs to a duplicate group, delete its directly matching candidates while keeping the selected one. Before showing confirmation, Incremento checks the same direct, provenance, legacy-source, and knowledge-tree relationships used by Review All. When live attached cards exist, the confirmation reports their distinct count and explains that the cards remain in Anki while links back to deleted documents may stop working. If that check fails or the active profile changes, nothing is deleted. Confirmed deletion removes the corresponding Anki notes/cards through Anki's undoable collection operation. Managed source files remain so Undo can restore the documents safely.

**PDFs with missing files only** checks the actual PDF files in the current profile in the background and shows documents whose source file is missing or unavailable, including empty or unsafe file references. A saved cover does not count as an available PDF. Title, tag, format, and duplicate filters still apply. Results are cached while the shelf is open; use **Check files again** after restoring or moving files, or reopen the shelf to start a fresh check.

To correct an imported PDF title, right-click its tile and choose **Edit PDF name…**, enter the name, and confirm. This is also available in **Open PDF window…**. The shelf refreshes immediately and title searches use the new name. The change is saved to the Anki note and supports Anki Undo/Redo; the stored PDF filename, reading position, annotations, and links are preserved.

The separate tag field accepts exact Anki tag names separated by spaces, commas, or semicolons. Start typing any part of a tag to see case-insensitive suggestions, or select **Browse tags** to discover tags already used by bookshelf documents; frequently used tags appear first, and choosing one completes only the tag currently being typed. Choose **Any tag (OR)** to include documents carrying at least one requested tag, or **All tags (AND)** to require every requested tag; tag matching ignores uppercase/lowercase and combines with the title and document-type filters. PDF tiles use their stored first-page cover; EPUB tiles use their stored book cover. Every tile has a bold, theme-aware title underneath and opens the appropriate reader with one left-click. Suspended document cards remain visible because the shelf is a document opener rather than a study queue. For older PDFs without a stored cover, Incremento renders a temporary first-page preview in the background. A document whose cover or source is unavailable keeps a placeholder instead of blocking the dialog.

Use **Sort by** to order the shelf by **Title**, **Priority**, **Due cards**, **Reviews done**, **Annotations**, or **Random**. **Reverse order** flips the selected order; **Shuffle again** generates a fresh random order. Random order stays stable while you change title, format, tag, or duplicate filters. Priority follows your configured lower/higher-is-more-important setting, with unset priorities treated as 50. Due cards counts distinct live linked cards currently due in Anki, excluding new, suspended, and buried cards. Reviews done adds Anki's review counters for the document card and its distinct linked cards. Both include nested knowledge-tree attachments. Annotations counts saved highlight/annotation records, including snapshots; a note on a highlight does not count separately. The selected metric appears beneath each title and in its tooltip. Statistics load in the background when first requested and are cached until the shelf closes; reopen it after reviewing or annotating to refresh the counts.

Main controls include:

- previous / next page
- zoom out / zoom in
- **Fit Width** beside the zoom controls fills the reader width and returns to the top of the current page. Scroll vertically to read the rest. It is available in compact and expanded controls, including side PDF readers, and keeps your marked-read progress unchanged. Zoom at 100% follows the reader width when the pane is resized; its height and toolbar size do not shrink the page.
- The Document Bookshelf loads without a modal progress window; duplicate analysis and cover decoding run in the background, and the grid fills progressively. Snapshot MathJax scans prepare PNG images in the background before recognition.
- PDF text clicks reuse the current text-row geometry; scrolling, zooming, or replacing the text layer refreshes it. Entering and leaving Snapshot selection updates only the capture controls, without rebuilding saved highlights. Snapshot dragging updates only the selection frame, and PNG encoding runs asynchronously. A pending snapshot is discarded if its document or page changes.
- **PDF appearance** with **Original**, neutral **Dark**, and warmer low-glare **Night** page modes; each PDF remembers its own choice, and the display filter does not alter the source PDF or snapshots
- highlight color selection
- **Add Card**
- **Open All in Browser** to show the PDF's linked cards in Anki Browser, sorted by creation date with the oldest first
- **Review Due** for due extracted cards near the current reading point
- **Review All** for every available card linked to this PDF
- **Links Off / On** to make PDF links clickable while you want them
- **Jump Back** beside the link toggle to return to the page and reading position from before an internal PDF-link jump
- **Find**, with **Return to p.N** after a search starts so you can go back to the page you were reading before the first result opened
- **Highlight when extracting**
- **Mark this PDF as finished reading**

PDF and EPUB readers start with a compact toolbar: Contents, Search, page navigation and zoom; Read to here, Extract, Bookmark, Annotate, Review All, More and Show controls; then Links, Jump Back, Page links and **Marked read** progress. Page position and marked-read progress remain separate. **Annotate** opens the full color palette, extraction-highlighting option, Snapshot, Highlights and Bookmarks. The arrow beside **Review All** opens the remaining review and card tools. **More** contains appearance, focus, reference-pane controls where available, Customize controls, Exact read marker, Reading Limit and Regenerate Cover. Click the same panel button again to close it. Side PDF readers keep their reading tools and omit review/card-management actions.

**Show controls** arranges the full toolbar into four aligned sections: **Navigation**, **Reading**, **Annotation & capture**, and **Review & cards**. At wide sizes, section names sit in a consistent column beside the tools. In narrow panes, headings move above the wrapping controls, and the toolbar scrolls vertically to keep every action reachable. Search stays beside Contents, and Extract stays beside Snapshot.

**Show controls** and **Minimize controls** are remembered after reopening PDFs and restarting Anki. The main reader and the side reader remember their choices separately for each profile. Until you make a choice, the reader starts with compact controls at every window size. Search, page jumps, and opening a tool panel keep your saved view unchanged. **PDF focus** also remembers whether it was on or off, so PDFs reopen in your last chosen mode. Closing a PDF does not reset that choice.

If you turn pages, zoom, or resize while a PDF page is still drawing, the reader cancels obsolete drawing work and displays your latest request next. Intermediate requests are skipped, and switching documents discards unfinished work from the previous document.

Local PDFs load through small, on-demand file reads. The reader requests the PDF structure and resources needed for the current view, so it can display a page before reading the complete book. After the visible page finishes, the main and side readers prepare up to five pages ahead and five behind, one at a time during idle gaps. Turning a page or zooming pauses that preparation and gives the requested view priority. Pages outside the moving window release their drawing resources. Search and annotation synchronization run as separate background operations.

The reader releases the hidden canvas after each page swap, and each page canvas is limited to eight million pixels. Ordinary views keep the display's pixel density; very large views or high zoom reduce rendering resolution while preserving page size, selection, highlight positions, and snapshot crop coordinates. Zoom still ranges from 25% to 400%. Revisiting a page outside the prepared window redraws it as needed. Complex PDF structure and shared resources can still require data from elsewhere in the file, and PDF.js may retain bytes already read.

The page indicator shows both the printed-page label and the running PDF position when the PDF supplies page-label metadata, for example **Printed 551 · PDF 579 / 1453**. Roman numerals and appendix labels are preserved. The PDF position counts every page, including covers and front matter. When printed labels are unavailable, the indicator shows only **PDF 579 / 1453**; it does not guess from an offset or scan the page image. Click the indicator to jump by **PDF page**. Saved reading positions, highlights, bookmarks, and links continue to use that running PDF number.

Under **Settings → Extraction → PDF citation page numbering**, choose **Printed page label (default)**, **PDF page number**, or **Printed label and PDF page**. This choice applies to ordinary text extraction, single and bulk highlight cards, and **Copy Link to This Place**, including the plain-text clipboard fallback. For printed page **v** at PDF page **7**, the choices show **Page v**, **Page 7**, or **Page v (PDF 7)**. Missing printed labels fall back to the PDF page number. Changing this setting affects new citations; existing card text is kept. Links always reopen the physical PDF page and retain the saved position.

New extraction citations and **Copy Link to This Place** use the PDF card's saved **Title**. For webpages converted to PDF, this is the webpage title saved at import, including any title you entered, rather than the generated `incremento-webpage-…` filename. If the saved title is unavailable, Incremento falls back to a readable filename. Existing extract text is kept.

Reader links are off by default so ordinary text selection is not interrupted. Turn **Links On** when you want to follow them. Links to another page stay inside the current PDF; after following one, **Jump Back** restores the earlier page and scroll position. Repeated internal jumps build a short back history, which is cleared when another PDF opens. `http` and `https` links open in your system browser. Unsupported link types are blocked and PDFs never navigate the embedded reader to a remote site.

Hover over a linked footnote reference or another internal PDF link to immediately open a small preview of its destination. This also works with **Links Off**. Drag the preview's bottom-right corner to resize its width and height within the reader window. Your last resized dimensions are remembered per Anki profile for subsequent footnotes, including after closing the PDF or restarting Anki. Both the main reader and side panes use this saved size. A smaller reader temporarily fits the preview to the available space without replacing your preference. Move into the preview to scroll through the note; press **Escape**, click **×**, or move away to close it. With **Links On**, focusing an internal link with the keyboard also opens its preview. Previews preserve the PDF's formatting and leave your current page, reading progress, and Jump Back history unchanged. Active reading locks also apply to previews. The PDF must contain an internal link; plain printed footnote numbers without link annotations cannot be previewed.

Use **− / +** in the preview to adjust its zoom from **100% to 400%** in 25% steps (default **150%**). The preview stays on the same footnote while zoom changes. Your chosen level is remembered separately for each Anki profile, including after closing the PDF or restarting Anki; the main PDF zoom is independent. You can also change it under **Settings → Review → Footnote preview zoom**.

**Contents** beside page navigation opens a small searchable chapter picker from any PDF page. It is also available in the compact controls and through **Incremento → Contents** or `Ctrl+Alt+T` (configurable as **Document Contents** in **Settings → Shortcuts**). The picker stays closed until requested, shows nested outline entries and your current chapter, and closes after choosing a destination, pressing Escape, or clicking outside it. Chapters use the PDF's embedded outline and its page destinations; remote outline links are excluded. **Jump Back** restores your previous page and scroll position. Contents works with **Links Off**, respects reading limits, and does not advance the **Read to here** marker or mark skipped pages as read.

The small fold button beside the Contents heading switches between **Expand all** and **Collapse all**, including nested chapters and **Saved places**. If any chapters are open, the first click collapses them all; the next click expands everything. The button stays hidden when there is nothing to fold. Search keeps matching destinations visible and temporarily disables folding; clearing search restores your previous folds and position in the list. Press Down from search to browse results with the keyboard, then Enter to open a destination. The popup follows the light or dark theme, with compact icon controls, a clear-search button, and muted page numbers.

The same picker includes **Saved places**, using the document's existing bookmarks. Choose **Save this place…** to name the current page and position; for a PDF without an outline, save its printed contents page as **Contents page**, then add any chapter destinations you need. These places are stored per document and Anki profile. They also appear under **Bookmarks**, where they can be removed. Built-in outlines remain part of the document and are not edited by this action.

To create a reusable return point, right-click the PDF page and choose **Copy Link to This Place**. Paste normally into an Anki card field: it appears as a clickable citation that previews the same PDF page at the clicked vertical position. The citation and its plain-text fallback use the PDF's printed page label when available (for example, **Page v** for physical PDF page 7); without a label, they use the physical PDF page number. The link always navigates by the physical PDF page number. Incremento preserves this rich link even when Anki's **Paste strips formatting** preference is enabled. The ordinary Copy and other standard right-click actions remain available. Visiting this anchor does not replace the PDF's saved reading position. A plain-text title is also placed on the clipboard for apps that do not accept rich HTML.

The **Page links** button lives in the bottom PDF toolbar's **Reading** group and remains available in the compact toolbar. Reference panes also keep it in their bottom toolbar. The button shows the current page's connection count; click it to open a small panel containing saved destinations, **Link this page…**, and **Linked PDFs**. The panel closes after choosing an action, pressing Escape, clicking outside, or changing pages, and reserves no space above the document. Choose **Link this page…** and select another imported PDF. A separate destination preview lets you turn pages, enter a page number, search, zoom, and scroll while your first PDF stays open. Click a spot or select a passage to mark the destination, then click **Link to this spot**. Scrolling without selecting a spot links to the top of the preview's current view. **Cancel** saves nothing. The page picker stays within the document's page count and current reading limit. The saved position identifies a point on the physical PDF page, so links can restore the passage at a different reader size or zoom.

A button such as **Other book — page 42** then jumps to that location in the same pane. Open **Page links** on the destination page to find the return button to the original PDF and page. The **Open beside reading** text button next to a page link opens its destination in the second pane; in narrow windows it wraps below the destination. Existing page-specific PDF associations also gain these buttons. In both main and side PDF readers, the Page links panel opens above the controls and stays visible when the toolbar scrolls. The panel shows only connections for the current page; **Remove** beside each destination removes the connection from either endpoint, including a missing destination, and refreshes both open readers. **Linked PDFs** also lets you change or remove a connection from either endpoint. Changing a link uses the same destination preview. Missing pages and locked destinations do not redirect to a different page. EPUB uses the same **Page links** control for stable section and passage connections; see the EPUB reader section below.

You can also use **Link PDF…** in the PDF reader's right-click menu. Select text first to keep a short passage label with the link. The Document Bookshelf picker lets you filter by title and tags without opening the target; enter its physical PDF page number, or keep page 1 for a whole-document reference. **Linked PDFs** lists saved references and their management actions. Anki review cards expose the same actions in their right-click menu, and stored web cards have a **Linked PDFs** button with **Link PDF…** inside the list. Associations live in the current profile's Incremento database and are included in profile backups; Anki Sync alone does not transfer them. The original PDF or webpage is not rewritten.

Choose **Preview PDF** to browse a reference in a separate, resizable window. Page navigation, Jump Back, zoom, text selection, and **Find next in PDF** belong to that window. **Copy Link to This Place** copies its current location. **Extract** sends selected plain text to the first Add Card field; `Cmd/Ctrl+1…4` targets the corresponding field and preserves the reference PDF's own source metadata, tags, and priority. Reference browsing does not change the main reader's position, saved study progress, daily page counts, or scheduling. Existing page locks apply. **Open in main reader** explicitly switches to the referenced document.

Choose **Open beside reading** in a preview to pin the same view beside the current reader without losing its page or scroll position. The divider is resizable. To compare two PDFs, open the first normally, reopen Document Bookshelf, then right-click the second PDF and choose **Open beside reading**. The Bookshelf closes before the reference opens, and the first PDF stays open. A floating main reader docks back into Anki so both PDFs share the divider. You can also use **Incremento → Open beside reading** to choose a second PDF. Two views may show different pages of the same PDF. The side pane uses the same **Navigation**, **Reading**, and **Annotation & capture** tools as the main PDF reader, including Contents, search, appearance, links, read markers, highlights, highlight notes, colors, bookmarks, and snapshots. Review and card-management controls are omitted. Highlights, notes, bookmarks, and explicit read markers are shared with the original document and refresh in its open panes; each pane keeps its own page, zoom, and scroll position. Simply browsing beside the main reader does not replace its saved reading position. Find opens its search field even when controls are minimized or the Reading group is hidden. Clearing the query keeps Find open for the next search. Choosing a result in the full search window keeps the complete result list available for Previous/Next. Highlights and Bookmarks lists stay above the toolbar in short windows. Right-click a passage for **Copy Link to This Place**; copied citations use that PDF’s own printed page labels and the configured citation numbering. One floating preview and one pinned reference are retained at a time; opening another replaces the corresponding reference view. Closing or switching profiles retires all reference views and pending requests. **Change linked PDF…** repairs a missing or outdated target while retaining its source association; **Remove link** removes only that association. Copying and extracting wait for the displayed page to finish rendering and recheck that its source document is still available. Legacy PDF commands remain readable. Linking from an ordinary browser tab through Companion is not part of this workflow.

To copy a clean embedded picture, right-click it and choose **Copy Embedded Image**. The action becomes available after a background check. Paste into an Anki field or another image-capable app to get the bitmap at its embedded pixel dimensions, including transparency, without page text, highlights, or Dark/Night display filters. Zoom does not affect the copied image. The action stays disabled when there is no bitmap under the pointer; hover over it for the reason. Vector drawings, figures assembled from several separate objects, and regions of scanned pages can still be captured with **Snapshot**. On a scanned page, the embedded picture may be the entire page. Copying requires PyMuPDF, available through **Incremento → Utils → Check Dependencies…**. Images above 16 million pixels, pages with more than 32 million embedded pixels or 2,048 image placements, PDFs above 512 MiB, and encoded images above 32 MiB are not copied.

During review, newer extracted PDF text keeps the card template's normal color and retains source bold and italics when the PDF exposes that font information. A visible **Source page preview** control appears beneath the text and citation. Press it to reveal a cropped image of the real PDF page with the source passage highlighted yellow; press it again to hide the image. For a selection spanning multiple rows, the crop covers the entire selection plus five PDF text rows before its first row and five after its last by default; change both sides together under **Settings → Extraction → PDF context rows before and after**. Matching tolerates PDF line wrapping, typographic punctuation, compatibility ligatures, and small OCR differences. Older citations without a saved screenshot retain the indexed-text hover fallback until you run the Utils action. Disable that legacy page-link popup under **Settings → Extraction → Show PDF context when hovering page links**.

New PDF text and highlight extractions store the cropped screenshot in Anki media and add a closed **Source page preview** control below the citation in Add Card and during desktop and mobile review. The image and saved card HTML sync normally. If the screenshot cannot be created or saved, the same control shows surrounding indexed PDF text when the extracted passage can be matched; this saved text also syncs normally. Previously saved hover or always-visible previews also gain the control during desktop review without rewriting notes; rerun the Utils action to save that layout to the cards for mobile sync. If neither the screenshot nor matching indexed text is available, Incremento keeps the ordinary citation instead of attaching unrelated context.

In Add Card and note editors, click the empty line below **Source page preview** to keep writing. The preview button stays clickable and is protected from text editing, so Enter creates normal text paragraphs. Older preview controls receive the same protection when opened in an editor. Preview clicks expand or collapse the content inside the card, including when an edited citation accidentally surrounds the preview. Click the citation itself to open the PDF reader. Existing previews receive this click protection during desktop review without changing saved notes.

Incremento remembers:

- current page
- zoom level
- finished/read state used by the scheduler

### Extracting text to cards

1. Select text in the PDF viewer.
2. Press `Cmd+1..4` on macOS or `Ctrl+1..4` on Windows/Linux.
3. The selected text is inserted into the matching field in the Add Card dock and the note is immediately tagged as a Topic. Paragraph breaks and PDF bold/italic emphasis remain visible when available.
4. Incremento appends a clickable citation link to the PDF page.

If the target field already contains text, the new excerpt is appended rather than replacing the old content.

PDF highlights can also be turned into cards from the **Highlights** panel. Incremento prefills the configured Add Card field, includes a citation that points back to the exact highlight when possible, and switches to **Preview Card** after that highlight already has a linked note.

### Reviewing all cards attached to media

While a PDF, EPUB, or video card is open, press **Review All** to open the attached-card review picker. Incremento recognizes older PDF/EPUB extraction records, current parent-card metadata, saved reader links, recent video extracts, and nested descendants below either the media card or any directly attached knowledge-tree root.

The picker lets you choose:

- **Topics and items**, **Topics only**, or **Items only**. This uses the same Topic/Item classifier as the normal Incremento reviewer, including configured topic note types/tags, item-tag overrides, and Topics-deck behavior.
- **Direct and nested cards** or **Direct attachments only**.
- **Include cards already in another filtered deck** when you explicitly want to transfer matching cards out of an existing filtered review.
- The **entire media** or only cards **up to the current position**. Media position means PDF page, EPUB section, or video timestamp. A nested card inherits the nearest known ancestor position; a card with no known position is excluded from the up-to-current range and reported in the preview.
- **All available cards** or only due review and ready learning/relearning cards. The due-only choice does not include new or future cards.
- A maximum number of cards, applied after filtering and ordering. Leave it at **All** for no limit.

Available review orders are:

- attached/source order
- media position, from the beginning toward the end
- creation date, oldest or newest first
- due and learning cards first
- shortest or longest current interval first
- random

Incremento first scans the links in the background, then shows a live **Ready** list and a separate **Excluded** list. Every excluded card has one primary reason, such as suspended, buried, already filtered, nested, beyond the current position, unknown position, not due, wrong Topic/Item type, or past the chosen limit. The preview names conflicting filtered decks and shows how many whole decks/cards would be affected before you opt in. The source card itself is never included.

After you confirm, Incremento resolves the links again and builds the temporary filtered deck in a background collection operation. Rechecking prevents stale preview data from scheduling a card that changed while the dialog was open. The selected order is preserved. Cards already in another filtered deck remain there unless you explicitly enable **Include cards already in another filtered deck**.

Anki cannot remove only selected cards from a filtered deck through its supported filtered-deck operation. When that option is enabled, Incremento first leaves any active reviewer, empties every conflicting filtered deck, and returns all cards from those decks to their original decks. It then moves only the matching selected cards into the PDF, EPUB, or video Review All deck. This does not delete cards, review history, scheduling data, or the old filtered-deck definitions, but it ends those decks' current review queues; rebuild the old filtered decks if you want to use them again. The picker shows a warning and requires this one-time opt-in every time it opens.

By default, these are real Anki reviews, including cards that were not yet due, so each answer updates that card's schedule normally. For topic cards, **Same** preserves the A-factor but still grows the interval and calculates a new due date from the day of the answer, even when the card is reviewed early.

To revisit cards without moving their next scheduled review, enable **Reminder without schedule changes** under **Scheduling**. Use **All available** under **Card state** to include cards that are not yet due, then press **Preview … Cards**. This uses Anki Preview: answers preserve the original due dates, intervals, topic A-factors and precise topic intervals, and custom schedule rules, including unconsumed one-time rules. New and learning cards also retain their original scheduling state. Anki may record the activity as a filtered-deck preview; Incremento does not record a topic/custom scheduling transition. Topic **More / Same / Less** buttons do not change frequency in this mode.

The reminder option starts off and is remembered separately for each profile and media type during the current Anki run. Clear it to resume normal scheduling; reusing the same Review All deck switches it back to rescheduling. In either mode, when the linked-card review ends, Incremento reopens the PDF, EPUB, or video at its saved reading or playback position.

### Highlights

You can highlight text in your saved default color (initially yellow) with:

- `Cmd+H` or `Option+H` on macOS
- `Ctrl+H` or `Alt+H` on Windows/Linux

Highlights are saved per PDF and reappear whenever you reopen the card.
Both PDF and EPUB support six text-mark styles: **Highlight**, **Underline**,
**Squiggly**, **Dashed**, **Dotted**, and **Strikethrough**. Open **Annotate**,
choose **Style** and a color, select your text, then click **Mark selection**.
The chosen style stays selected while that reader is open. The highlight
shortcut uses that style and your saved default color; quick swatches apply
the chosen style with their color. Existing highlights retain their appearance.
Click a PDF mark to change its style or color in the small palette. In EPUB,
click a mark and choose **Style** to open the same choices. Each style has a
label and a visual sample. Changing a mark keeps its text, note, position, and
linked cards. Dashed and dotted marks retain their appearance when synced to PDF.
Use **Add note** or **Edit note** on a PDF or EPUB highlight to open the note editor. Its toolbar supports **bold**, *italic*, underline, strikethrough, bulleted and numbered lists, hyperlinks, clear formatting, and undo/redo. Select text before applying formatting or adding a link; without a selection, the link URL is inserted as text. Use `Cmd/Ctrl+B`, `Cmd/Ctrl+I`, `Cmd/Ctrl+U`, and `Cmd/Ctrl+K` for the common actions. Enter an empty URL to remove a selected link. **Save** saves and closes the annotation editor; **Cancel** keeps the previous version. The editor is a separate, non-modal window: you can scroll, navigate PDF pages or EPUB sections, select text, and copy from the reader while the draft stays open. Its source passage remains fixed. Reopening the same annotation brings its existing draft forward instead of opening a second competing editor. Saving checks the original document, profile, collection session, and annotation; a changed or deleted annotation cannot be overwritten by an older draft. If the source context changes or saving fails, an inline message explains the problem and the draft stays open so you can copy it or retry. Return to the original document before saving, or copy the draft and reopen the annotation if the reader/profile session was replaced. Closing a draft does not save it automatically. Formatting appears in the PDF highlight list and hover preview, EPUB highlight list, and Search ALL annotation preview. Open note hyperlinks from the reader's highlight list; Search ALL previews and hover previews display them without navigation. Search ALL searches the visible note text. Existing plain-text notes remain literal text. PDF annotation sync exports readable plain text and keeps Incremento's formatting locally; editing the note text in another PDF application replaces its previous local formatting.

Paste a copied bitmap, screenshot, or copied local image file into that editor with `Cmd/Ctrl+V`, then add a short description beside or below it. A copied local image is imported as a bitmap; its `file://` path is never inserted into the note. Images are automatically reduced to at most 960 pixels on the longest edge and compressed to at most 80 KiB each, with clipboard metadata removed. Click an image to show a blue outline and visible resize handles. Drag the bottom-right corner to keep its current proportions; drag the right or bottom edge handle to stretch its width or height independently. Hold **Shift** to switch between proportional and free resizing. You can also focus a handle with **Tab** and use the arrow keys. **Escape** cancels an unfinished drag, and one **Undo** reverses a completed drag. **Image width**, the stored size, and **Remove image** remain available below the editor. Width-field changes preserve the current proportions. Resizing affects the display dimensions without recompressing the image, and stretched dimensions survive saving/reopening and reader previews. New images start at a compact size so their handles are reachable. Clear formatting retains images.

**Image placement** offers four layouts. New pasted images default to **Own line (recommended)**: an initially centered image with normal text paragraphs above and below, a useful choice for a landmark and a short description. For an own-line image, **Align image → Left / Center / Right** changes its horizontal position without wrapping the caption beside it. These controls appear only for Own line, support Undo/Redo, and keep the chosen alignment when saving, reopening, resizing, or using Write above/below. **Inline with text** places a small image inside a sentence. **Wrap text (image left)** and **Wrap text (image right)** put the image on that side with the note text flowing beside it, useful for longer descriptions or small diagrams. **Write above** and **Write below** put the image on its own line and move the typing cursor to the chosen side; existing descriptions and formatting remain intact. You can also click in any paragraph and type normally. Right-aligned images expose their resize handles on the free left edge. Placement changes support Undo/Redo, survive reopening, and appear in PDF/EPUB lists and Search ALL previews. Wrapping stays within the current annotation. For narrow panes or detailed pictures, Own line keeps the caption easier to read. The editor explains when an image leaves too little space for a readable text column. PDF previews temporarily stack wrapped images in narrow panels and restore wrapping when widened, without changing the saved choice. Existing notes keep their previous inline placement until changed. Notes may contain images without text, but a short caption makes visual mnemonics easier to understand and find through search. Up to four images fit within the existing total note-size limit. Images stay embedded in the profile's annotation data, without separate files in Anki's media pool or remote-image requests, and are included in Incremento backups. **Remove image**, followed by **Save**, removes those embedded bytes; **Cancel** keeps the previously saved image. They appear in reader lists and PDF hover previews, and alongside matching captions in Search ALL. PDF annotation sync exports the description as plain text; embedded images remain local to Incremento, like rich formatting.

Use **Default color** at the start of the **Annotate** palette to change
the default while reading, or choose it under **Settings → Extraction**. Its swatch
shows the saved color. The default is shared by PDF and EPUB readers in the current
profile and survives Anki restarts. Choosing a quick color, using **More colors…**,
or recoloring an existing annotation does not change it. Changing the default does
not annotate selected text or recolor saved highlights.
Hover over a saved PDF highlight to reveal its color, note, resize, and delete icons together. The icons stay visible as you move onto them and hide when you move away; keyboard focus on any icon reveals the whole group too. Only actions available for that annotation appear, and the delete-button visibility setting still applies. Click the little colored circle to open the full color picker directly, just as in EPUB. Choose a color and confirm with **OK** to recolor only that annotation; its text, note, linked cards, and your saved shortcut default stay intact. Clicking the highlighted text itself opens a small palette with eight quick colors and **More colors…**. Press **Escape**, click elsewhere, or scroll to dismiss that palette. Both controls work in the main reader and the side reading pane, including when delete buttons are hidden; snapshots keep their dedicated blue outline. You can also open **Highlights** and use **Choose annotation color**.
As soon as you select text, the blue selection shows a line-and-dot handle at
each endpoint. Drag either handle before creating the highlight to adjust its
start or end; copy, extraction, and highlight actions use the adjusted text. The
temporary handles disappear when you save the highlight or click elsewhere. To
resize a saved text highlight, click its highlighted text (or its
horizontal-arrow action) to show the endpoints again; finishing the drag or
clicking elsewhere hides them.
All six text-mark styles can be resized. Snapshot regions, shapes, and PDF
comment icons retain their own geometry.
Use the eight quick swatches or **More colors…** for a larger palette and a custom
HTML color such as `#123ABC`. Click **OK** to apply the color to selected text.
The highlight shortcut continues to use the saved default. Custom
colors used on highlights are saved in the database and preserved when synced to
PDFs. **Add to Custom Colors** stores up to 16 palette swatches in their original
slots. They are saved when the picker closes (including **Cancel**), survive Anki
restarts, and are shared between PDF and EPUB readers within the current profile.
The palette is included in Incremento database backups; **Cancel** still leaves
the current annotation color unchanged.

The blue text-selection preview and saved text highlights join word spaces,
including wider spaces in justified text, between PDF text fragments on the
same line. Small OCR baseline differences stay within one highlight band.
Copying and extracting text preserve word spaces, narrow letters, punctuation,
and the exact selected start and end characters, including in converted DjVu
documents. Overlapping boxes render once for even color; separate lines and
wide column gutters remain clear. Hovering a highlight
with a saved note shows one note popup beside the pointer.
All annotation action icons stay hidden until you hover over the highlight or
its controls, or focus an icon with the keyboard, keeping them out of screenshots when idle.
For clean PDF screenshots, open **Highlights** and choose **Hide highlight
controls**. The panel closes and the on-page delete buttons, note popups, and
resize handles disappear; saved highlights and their colors stay visible.
This choice stays active while you navigate pages in the current reader.
Open **Highlights → Show highlight controls** to edit annotations again.
To keep highlights visible without their on-page delete X, uncheck **Settings → Extraction → Show delete X on PDF highlights**. The Highlights panel still offers Delete, and note and resize controls remain available. The setting applies immediately and is remembered after restarting Anki.

With PyMuPDF 1.26 or newer installed, opening a PDF or editing its annotations
syncs highlights and notes into the managed PDF as standard, editable PDF
annotations. The reader opens immediately from its latest display copy while
this interchange continues in the background; switching to another PDF cancels
obsolete work for the previous document. Existing PDF highlights, underlines,
squiggles, strikeouts, sticky notes, free-text boxes, rectangles, and circles
also appear in Incremento's Highlights panel. Their comments can be edited
there. Other annotation types remain in the PDF with their native appearance.

To share changes with a PDF outside Incremento, open **Highlights → PDF annotation
sync… → Link original PDF…** and select the matching document once. Incremento
then syncs both files on open and annotation edits. Use **Sync and open in another
PDF reader** to open the linked original (or the managed PDF when unlinked).
**Show in Finder** on macOS or **Show in File Explorer** on Windows selects that
file in its folder without syncing. On other systems, **Show containing folder**
opens the folder.
After editing in another reader, save there and reopen the Incremento PDF or
choose **Sync now**. Files are not watched continuously. **Unlink original PDF**
stops writing the external file. Annotation sync accepts PDFs up to 512 MiB and
20,000 pages, retains up to 32 MiB of serialized annotation metadata, and allows
up to 10 minutes of processing per attempt. If a PDF exceeds a bounded limit, the
automatic attempt is not repeated again during the current profile session;
**Sync now** or linking the original explicitly retries it. Reopening or
switching the Anki profile also resets this temporary suppression.

Concurrent comments on the same passage are combined; conflicting positions
are retained as separate annotations. Incremento preserves newer annotations
absent from an older PDF snapshot. Readers that
remove Incremento's sync stamp cannot propagate deletions; remove those
annotations in Incremento instead. Before replacing a changed PDF, Incremento
keeps its previous version under `user_files/<Profile>/pdf_annotations/<card_id>/`
as `managed-backup.pdf` or `source-backup.pdf`; each slot holds one previous
version. `reader.pdf` is a derived display copy that avoids painting highlights
twice. Original-file links and sync history are profile-specific. PDFs marked as
digitally signed, requiring a password, restricting annotation changes, exceeding
the sync limits, or containing changed page content stop sync with a specific
explanation; Incremento's saved annotations remain available. A digital signature
is certificate-based evidence of who signed the document and whether it changed
after signing; rewriting it during sync could invalidate that signature. An empty,
unsigned signature field alone does not block sync. Saving annotations inside
Incremento is separate from syncing them into the PDF file.
Legacy citation highlights without page rectangles stay in Incremento only.

### Card → documents → recordings

**Settings → Review → Use study workspace during review** controls this presentation and defaults to on. Turn it off for Anki’s normal card layout, without the resource tabs or linked-resource summary. Saving Settings applies the choice immediately and returns an open study visit to the same card and question/answer side. Saved links are retained; **Study resources** in the card’s right-click menu still opens them explicitly. Turning the workspace back on restores its review navigation without answering or re-rendering the card. Normal-card mode also skips automatic resource availability queries.

The study view keeps the current review card and its question/answer state in place. **Card**, **PDFs**, and **Videos** provide one view per media type, with inline file counts. **Documents** replaces PDFs when EPUBs are linked; **Audio** replaces Videos when all linked recordings are audio. Counts describe distinct available files, so several passages from one PDF still count as one document. Empty or unavailable views remain reachable for linking and repair. Availability is checked in the background; **Checking…**, **Could not check**, and **Retry** distinguish a pending or failed check from an empty list.

Use **+ Link resources…** from the card or either media view. The link sheet opens inside the same workspace and names the current card, even while a PDF is open. Check imported PDFs, videos, or audio recordings; each checked file reveals its own PDF page or start time, optional end time, and label directly underneath. **Links you’re creating** shows the current card and the exact links in the unsaved draft. Its list updates immediately as you edit; **Remove** only unchecks that draft resource. Select a link or use **Preview** to inspect its PDF page or paused recording segment in the same sheet. PDF pages load in the background and respect the document's accessible-page limit. **Choose exact spot in PDF…**, or clicking the page preview, opens the precise destination picker. Recording previews start at the entered time and stop at the optional end; **Use current position** copies the current PDF location or that recording preview's timestamp. Invalid page numbers and time ranges appear beside the fields and disable saving. The preview sits beside the library in a wide window and below it in a narrow one, with scrolling for longer drafts.

**Import files…** offers the normal PDF, video, and audio import flows, plus Refresh after an asynchronous import finishes. The library shows the 500 most recent imported resources; search appears for longer lists. Choose up to 32 resources per save. **Link N resources** validates every destination and saves the entire mixed batch atomically; a failure retains the draft and saves none of that batch. **Cancel** returns to the same card or reader. Previewing never writes card content, associations, reading progress, or playback resume positions. The card's current question or answer remains unchanged.

The compact resource picker shows the selected title and its page or timestamp on separate lines. Click it to expand the linked files in place; each row shows its title, saved location, optional label, and a checkmark for the selection. **+ Link resources…** and **Manage links…** are inside that list. One resource opens directly; several resources open the first available choice on the initial visit and retain the selected resource on later visits. Multiple passages or segments from one file are supported: add another link with a different destination. Switching resources retains their separate reading or playback positions and pauses playback when switching away. Long bibliographic filenames are shortened for display; their original titles remain in tooltips. Right-click the picker for focus controls and **Other resources**, which opens the advanced resource drawer. Explicit passage visits retain the split layout. The document and recording panels can be resized when both are visible; their proportions are remembered per profile, separately for wide and narrow windows.

**Manage links…**, also available in the quiet footer, lists card resources including unavailable destinations. Click a direct link's title to change its file, location, or label. Choose another imported file to repair a missing target. Each direct link has its own **Unlink** button, which removes only the association and keeps the original files. **Undo unlink** restores the association, including unavailable targets. Links inherited from card content or document passages are identified and edited at their original source.

**Focus textbook** or **Focus video** expands that view to full screen, hiding the other panels, card summary, and surrounding Anki docks. A compact navigation bar keeps **Card**, **Documents**, **Videos**, and **Exit focus (Esc)** within reach. Press **Esc** or **Exit focus** to restore the previous window state and panel sizes. Selecting a different view restores that view’s saved layout. Focusing the textbook from beside a playing video pauses the video and keeps its timestamp. Entering or leaving focus on the current view preserves the live reader and playback state. Textbook and Video remember focus independently in the current profile. Closing the workspace, returning to Card, or switching views keeps that preference, so the next visit restores focus after the content loads. Pressing **Esc** or **Exit focus** saves your choice to use the split layout next time. Automatic resizing and closing never overwrite your preferred panel proportions; saving Settings also preserves the latest layout choices.

Switching views keeps the live card, page/scroll/zoom, and playback position. Playback pauses whenever you switch away. Automatic advance and the reviewer’s grading shortcuts are suspended while the embedded textbook or video is open. **Card** restores the original question or answer and keep the study visit ready. The card's text, media, typed input, and controls remain live inside the centered panel. Revealing the answer on that same card preserves the visit. Advancing to another card or changing profiles ends it. Outside card review, or while another focused reader already owns Anki's content area, resources use a separate window with the same panel layout. A visit opened outside card review disables Card with an explanation. Empty Documents and Videos views explain how to add the missing link.

Use the **PDFs** or **Videos** tab on the question or answer side to open its resources. **Study resources** is also available from the card's right-click menu. The textbook opens at its saved PDF page or EPUB section; a video opens paused at its saved timestamp. The current card is summarized above the two-line picker, with no repeated title toolbar. Each compact tab shows its selected media; returning to PDFs keeps the same reader and position. The player uses compact controls; loading, unavailable-file, and segment-finished messages remain visible. The original card and its current side stay in place.

To set up a connection, open the relevant textbook passage and choose **Page links → Link recording…**, or right-click the passage and choose **Link recording…**. Selecting text first keeps a short excerpt with the association. Choose an imported local video or audio recording, preview it, enter a label and start time, and optionally enter an end time. Times accept seconds, `m:ss`, or `h:mm:ss`; **Use current position** copies the preview's timestamp. **Save link** connects the passage to the original recording without cutting or duplicating a clip. You can also link a recording directly to a review card. Use **+ Link resources…** to attach recordings directly to a card, independently of any document. **Link PDF…** remains available in the expanded resource drawer.

The recording picker shows the 500 most recent imported video/audio notes and searches within that list. Use **Import video…** or **Import audio…** to run the normal import flow, then press **Refresh** after the import finishes. Choose a downloaded local copy for video playback; a web URL alone is not playable in this reference player. Audio uses the original file in Anki's collection media. Playback depends on the codecs available in Anki's Qt media runtime.

When you open a linked recording, it starts **paused** at the saved timestamp beside the textbook. Press **Play** to begin. If an end time was saved, playback pauses there and offers **Replay segment** or **Continue recording**. **Back to passage** pauses playback and returns focus to the same live textbook view, preserving its page, scroll position, and zoom. If that pane was closed, it reopens at the last page or section and scroll position. **Return to card** restores the original question or answer without grading it and keeps the reader and player ready for another visit. The visit does not change the recording's normal resume position or the textbook's normal reading position. Explicit reader actions such as adding a highlight or marking a passage read retain their usual behavior.

Use **Edit link…** to change the recording, label, or timestamps; use **Remove link** to remove only the association. Missing or moved files stay visible as unavailable so you can repair the link. Existing document reading limits still apply. Links are saved in the current profile's Incremento database and included in Incremento profile backups; **Anki Sync alone does not transfer these associations**.

### Cross-references

Citations added from PDF extraction link back to the exact PDF page. Highlight-created cards also try to reopen and scroll to the exact cited highlight before falling back to page/excerpt matching.

### Searchable PDF text

Incremento stores searchable PDF content in two ways:

- the note's `Content` field for normal Anki browser search
- a page-level PDF text index used by **Search ALL**

If old cards are missing page-level search results, run **Incremento → Utils → Reindex PDF Text (Existing Cards)**.

### EPUB cards and reader

EPUB cards use a dedicated reader dock that clones the PDF reader toolbar. The same four customizable groups stay below the document: **Navigation** (Navigate + Zoom), **Reading** (read-to-here, exact marker, Links, Jump Back, range, and progress), **Annotation & capture** (the same eight quick highlight colors and **More colors…** palette with hex entry, extraction highlighting, Snapshot, Highlights, Bookmark, and Bookmarks), and **Review & cards** (Review Due, Review All, Reading Limit, Regenerate Cover, browser/card actions, and Finished Reading). EPUB maps PDF zoom to reflowable text scale and stable read progress to EPUB sections. The page-location button supports direct page jumps, current-section cards appear as **Page cards**, and an enabled daily reading limit appears in the toolbar. **Annotate**, the arrow beside **Review All**, and **More** open tools on demand in the compact view. **Show controls** exposes all four groups; **Minimize controls** returns to the compact view. The choice is saved for each profile, independently of PDF, and restored when the reader reopens or Anki restarts. Opening Search or a tool panel does not change the saved choice. **Customize controls** chooses the groups shown in expanded mode; all features remain accessible in compact mode. Marked-read progress refers to sections, shown as **Sections 1–N**, independently of the current reflowed page.

You can narrow the EPUB dock with all controls showing. The expanded toolbar automatically wraps its sections and buttons to fit, including the Find row. When the controls need more height, scroll within the toolbar to reach them while the document keeps its reading area. **Customize controls** and **Minimize controls** remain optional ways to reduce the toolbar.

**EPUB focus** fills Anki’s available width, hides Anki’s top navigation bar, and keeps review answer controls visible. Toggle it in either toolbar or under **Settings → Review**. The preference is saved; moving to an ordinary card restores Anki’s card area and the navigation bar’s previous visibility. PDF and EPUB focus share the same layout controller, so switching document types cannot leave two focused readers behind. In either reader, Anki’s background refreshes keep the deck list and main card area hidden until focus ends. **Original / Dark / Night** appearance is remembered separately for each EPUB without changing its contents or reading position.

Use **EPUB reference…** to choose another book from the Document Bookshelf and read it alongside the main book. Drag the divider to resize the panes. Each reference has its own section, scroll position, text scale, Find, Links, and Jump Back controls. A floating **Preview EPUB** can be opened from Page links. One pinned reference and one floating preview are retained. Navigation in either reference leaves the main book’s saved position unchanged. Highlights and their notes/colors are shared for the same book; explicit bookmarks and read markers belong to that book. **Extract** and Cmd/Ctrl+1–4 use the reference book as the source, including its section, tags, priority, and provenance.

**Page links → Link a passage…** captures the selected passage, or the nearest visible text when nothing is selected. Choose an EPUB, browse to the destination, select its passage if desired, and press **Use this passage**. Links store section and text offsets with a scroll fallback, so changing text size or pane width does not turn a connection into an unrelated page number. The connection appears under **Page links** at both endpoints. Use **Open in main reader**, **Preview EPUB**, or **Open beside reading** to follow it; open Page links at the destination to return. **Remove link** works from either end, including when the other book is missing. Reading limits still apply. These are EPUB-to-EPUB connections; PDF page connections retain their separate PDF workflow.

Current EPUB features include:

- saved reading position and reopen-at-last-section behavior
- bookmarks within the book
- an opt-in **Links Off / On** control for section, footnote, and web links
- **Jump Back** immediately beside the link toggle, with bounded internal-link history and exact source-section/scroll restoration
- highlights and highlight notes, with draggable start/end handles on both live text selections and saved highlights
- per-book daily reading limits
- optional prompts to review due extracted cards near the current reading point
- **Review All** with the shared Topic/Item, scope, state, limit, and order picker
- searchable extracted section text used by **Search ALL**

Click a saved EPUB highlight to open its action menu. The color dot changes its color using the shared palette, including custom hex colors; its note, text range, identity, and linked cards are retained. The other icons edit its note, resize it, or delete it. All four actions remain visible while the menu is open. Cmd+H on macOS or Ctrl+H on Windows/Linux highlights the current selection in the saved default color. Use **Default color** in the **Annotate** palette to change it while reading; one-off colors leave that default unchanged.

Selections spanning paragraphs or styled text keep the original text layout and remain one highlight. Its note, resize handles, and Delete action apply to the entire selection.

Drag a selection or saved-highlight pin by its dot to adjust that endpoint. Picking up a pin keeps the selection in place; dragging across lines moves only the endpoint you grabbed.

EPUB links are also off by default. With **Links On**, links to a section or anchor navigate inside the same book and validated `http`/`https` links open in your selected Companion browser. After an internal jump, **Jump Back** returns to the exact source section and reading position; repeated jumps create a bounded back stack that is cleared when another EPUB opens. Remote resources still cannot load inside the EPUB reader, and unsupported or escaping local paths are blocked.

EPUB also has **Contents** in both full and compact controls, with the same shortcut, search, saved places, automatic closing, and **Jump Back** behavior as PDF. It reads EPUB 3 navigation or EPUB 2 NCX chapter hierarchies, including subsection anchors, in the background. Books without either list fall back to their reading-order section titles. Contents navigation leaves the separate read-to-here marker unchanged; jumping ahead does not mark intervening sections as read.

Right-click the EPUB text and choose **Copy Link to This Place** to copy a card-ready anchor for the current section and nearest text position. Pasting it into an Anki field creates a link that reopens that exact reading area; a bounded scroll position is retained as a fallback if the text point cannot be resolved. The action is available independently of **Links On**, and the standard context-menu actions remain intact.

Selected-text web search uses the same small Google/DuckDuckGo window as PDF. Snapshot offers the same local MathJax/LaTeX recognition workflow. Search ALL already searches EPUB annotation notes separately from highlighted text, runs progressively in the background, and supports cancellation. Document Bookshelf and Knowledge Tree loading are shared background workflows. Linked-card Browser lists use oldest-note-first ordering, and Contents has the same first-click Collapse all behavior. Native PDF annotation interchange, PDF page rasterization, and embedded-PDF-image extraction remain PDF-specific; EPUB renders reflowable HTML and keeps its annotations in Incremento.

EPUBs are treated as a distinct document type throughout Incremento. They appear separately from PDFs in quick open, statistics, and focus-timer summaries.

---

## 7. Video Cards

Video cards use the **Incremento Video** note type and open in the video dock.

### Supported sources

- YouTube
- Vimeo
- local video files

### Remembered progress

Incremento saves the last watched position for each video card and resumes from there later.

### Video dock tools

The dock includes:

- a compact current-time and manual resume-time control
- a primary **Extract** action for adding a card at the current timestamp
- **Create Mobile Clip…** for trimming a local or remote video range into synced Anki media
- **Bookmark** plus a live bookmark count that opens the saved return points
- an overflow menu for **Back** (10 seconds), **Open in Browser**, **Download Local Copy…**, **Captions…**, and **Review All**; the shared **Search** action stays visible but disabled because video cards do not have text search

**Review All** opens the linked-card picker with Topic/Item, timestamp range,
nested scope, due-state, limit, and ordering controls.

For local playback, extra controls appear:

- play / pause
- skip back 10s
- skip forward 10s
- seek bar
- playback speed
- volume

### Creating cards from videos

Use **Add Card at this point** to create a new card tied to the current video moment. This is useful for note-taking and timestamp-based review prompts.

To make part of a video playable on mobile, click **Create Mobile Clip…**, enter the exact start and end (for example, `07:55` and `08:33`), and confirm. When a local copy exists, Incremento trims it directly. For YouTube or Vimeo without a local copy, Incremento downloads only the selected range instead of the complete source video. It then creates a bounded H.264/AAC MP4, copies it into normal Anki media, and adds a playable video plus the source timestamp to the Add Card draft. Finish the prompt/answer in that draft and add the note normally. After Anki media sync completes, the embedded clip is available in desktop Anki, AnkiMobile, and AnkiDroid without the Incremento add-on on the mobile device.

Clips are limited to 10 minutes and must remain below Anki's 100 MB per-media-file limit. A full local source video, when present, remains under `user_files/<ProfileName>/videos/` and does not sync; only the generated clip is stored in Anki media. Discarding the Add Card draft moves its staged Incremento clip to Anki's media trash. Creating local clips requires FFmpeg; clipping a remote YouTube or Vimeo source also requires yt-dlp. Install FFmpeg explicitly through **Incremento → Utils → Check Dependencies…** when Homebrew (macOS) or winget (Windows) is available. Linux users receive the appropriate package-manager commands. Incremento never installs FFmpeg without that button click.

### Browser sync

If you use the companion browser extension, watched YouTube/Vimeo time can be pushed back into Incremento video cards automatically.

---

## 7A. Audio Cards

Audio cards use the **Incremento Audio** note type and play directly inside the card. Import them through **Incremento → Add Content → Add Audio**. The audio itself is ordinary Anki media and therefore follows normal Anki media sync to desktop, AnkiMobile, and AnkiDroid.

The card remembers its listening position independently on each device. Opening the same card again on that device resumes near the saved second; reaching the end resets it. Clearing the app's web storage, reinstalling the app, or moving to another device starts from that device's own position.

The first version intentionally has no separate desktop dock, timestamp extraction, bookmarks, or cross-device position sync.

---

## 8. Web, Writing, and Local File Cards

### Web cards

Web cards open a persistent browser dock with:

- the card's home URL
- a **Home** button
- a **Bookmark** button for saving one highlighted return point
- an **Open in Window** fallback
- a **Track via Chrome extension** checkbox for that external window flow
- saved last visited URL
- optional remembered scroll position for browser cards
- persistent cookies and website local storage under `user_files/<ProfileName>/web_profile/`

This works well for long-form websites, documentation, and pages that you want to revisit in-place inside Anki.

The Web reader saves its browser storage when you close the Anki profile or exit Anki. Its website logins are separate from the search popup and your external browser. Websites can expire or revoke sessions, and some sign-in providers require **Open in Window**. An interrupted shutdown can still lose recent browser changes.

Selected text and snapshot regions from the web dock can be transferred into the Add Card dock. After a transfer succeeds, Incremento leaves an amber dotted text marker or amber dashed snapshot outline on the page so you can see what is still part of the unsaved Add Card draft. Saving the note changes that marker to green; reopening the same tracked Web card and exact URL restores its saved markers. Restoring an extraction draft restores its pending markers, while discarding the draft removes them. Markers are drawn by a pointer-transparent native reader layer above the website: they do not insert elements or styles into the page, intercept clicks, or alter its text.

Incremento stores both the selected quote and bounded surrounding/DOM context, so markers can usually survive modest page-layout changes without altering the webpage text. Restoration fails closed when repeated text cannot be identified uniquely. Text selected inside a cross-origin embedded frame, selections larger than the marker limit, or content that a site has replaced may still transfer to the Add Card dock without leaving a persistent marker.

When a bookmark is saved, Incremento reopens that web card at the bookmarked point and highlights it. If no bookmark is saved, the web card can restore the last scroll position when the browser-card scroll setting is enabled.

If a page does not behave properly inside Anki's built-in web view, use **Open in Window** to open the current page externally. When **Track via Chrome extension** is checked, the companion extension keeps syncing the same web card to the latest page visited in that browser tab.

In **Incremento → Settings → Review**, you can choose a default PDF appearance. With **Always force this appearance for every PDF** off, a PDF's remembered choice wins and the default is used for PDFs without one. With it on, every PDF opens in the selected Original/light, Dark, or Night appearance; the per-PDF choices remain saved and become active again when forcing is turned off. The same tab also controls whether web-card media should try to resume in the original page first and whether browser-card scroll should be remembered by default.

### Writing cards

Writing cards open a markdown editor and live preview side by side.

Features:

- autosave while typing
- markdown file stored in `user_files/<ProfileName>/writing/`
- live rendered preview
- **Open Folder** button
- text selection transfer into the Add Card dock

Writing settings let you define default wrap mode, focus mode, preview visibility, current-line highlighting, bookmark restore, automatic backups, the default progress scope, and the word-count mode.

If a writing card does not yet have a file path, Incremento generates one automatically the first time the card is opened.

### Multiple PDF windows and dragging

Choose **Incremento → Workspace → Open PDF window…**, then select a PDF. Repeat to open more PDFs, or right-click a PDF in **Document Bookshelf** and choose **Open in new window**. You can open different PDFs or several views of the same PDF. Each window keeps its own page and scroll position; highlights, notes, bookmarks, and explicit read markers are shared. These additional readers keep the reading tools without changing the main review card. Up to **eight additional PDF readers** can stay open, including temporary preview panes; close one when the limit is reached. Opening a new window never silently closes an existing independent window.

Resize a floating reader by dragging any **edge or corner**; the pointer changes to show the resize direction. The bottom-right corner also has a resize grip. This lets you widen or shorten the PDF window while keeping it at your preferred size. **Escape** cancels an in-progress resize. Docked panes resize with Anki's separators.

Drag an Incremento pane by its **title bar**. A blue placement outline appears when a drop is available:

- At a screen edge, release to use that half of the screen. Corners use a quarter.
- Near the edge of a docked pane, release to split beside, above, or below it inside Anki.
- Near an Anki window edge, release to dock there. At other positions the window stays floating.

**Escape** cancels the drag and restores its starting layout. **Workspace → Restore previous layout** reverses a completed move. Screen snapping uses the screen under the pointer and respects its available area and the pane's minimum size. Dragging a PDF preview makes it an independent window, so later previews cannot replace it. Double-click a title bar or use its float/dock button to detach or dock a pane; use the close button to close it. Text selection inside the reader continues to work normally. Focus mode keeps its reader in Anki's central area; turn off focus mode or use the Workspace positioning commands to move that main reader.

### Writing beside a document and arranging windows

While a PDF or EPUB is open, choose **Incremento → Workspace → Write beside document…**. Search for a writing card and choose **Open beside**. **New writing…** opens the existing writing-card creation dialog; after creating the card, select it in the list. Loading the list happens in the background. The picker shows up to 2,000 writing cards, including suspended cards; Quick Open Content remains available for larger libraries.

The writing pane opens beside the reader with **Keep open while studying** enabled. If the PDF or EPUB is in focus mode, it stays in Anki’s central reading area while writing takes the right side. It keeps the chosen writing card visible when you review other cards or leave review. Uncheck this option to resume following writing cards in the reviewer; closing the writing pane also turns it off. Only one writing card is open at a time. Opening another writing card explicitly switches the editor. Autosave, backups, per-card cursor position, and word progress continue to work. Reopening an already open writing card, including a hidden pane, preserves its live text and session word baseline.

Use **Incremento → Workspace** to organize the open Incremento panes:

- **Side by side**, **Stack vertically**, and **Grid** dock the open panes inside Anki. Grid uses two columns. Drag the dividers to adjust their proportions.
- **Position window → [pane title]** floats that pane into a left/right/top/bottom half, a corner quarter, or the available screen area. It uses the pane's current screen (Anki's screen when docked) and leaves room for system bars. Positions too small for the pane's controls are rejected.
- **Restore previous layout** reverses the last layout or positioning action, including reader focus mode. Closed panes stay closed. The layout history lasts only for the current profile session.
- **Save workspace…** saves the current arrangement under a name. **Open saved workspace → [name]** reopens its documents and writing cards, restores zoom, reader controls and focus mode, and puts the panes back in their docked or floating positions and sizes. PDF and EPUB readers resume the document’s latest saved reading position. Readers that are already open keep their current page and scroll position. This also applies to workspaces saved before this behavior was added; reading further never requires saving the layout again. Additional readers keep their independent positions while open; after closing, they resume the document’s latest saved position. Writing keeps its existing content and restores its preview, wrapping and text scale. Saved workspaces survive restarting Anki and belong to the current Anki profile. Up to 20 named workspaces can be saved; saving an existing name asks before replacing it. **Delete saved workspace → [name]** removes only that saved arrangement.

Workspace snapshots reference existing cards and files; they do not make a second copy of document or writing content. Missing or deleted documents are skipped with a notice. Existing extra panes remain open, including unsaved Add Card content. Loading a workspace does not start a review session or change card schedules. If a saved floating window belonged to a disconnected screen, it is brought back onto an available screen.

These commands arrange Incremento's readers, reference panes, writing, Add Card, and local-file panes. Other applications are unaffected. Arranging a reader in focus mode temporarily returns it to its dock; restoring the layout restores focus mode. Documents and writing remain loaded while panes move. In narrow writing panes, scroll the tools row horizontally to reach every action; turn off **Preview** for more editing space. Switching Anki profiles closes the writing workspace and clears pending callbacks.


### Local file cards

Local file cards open a small dock that shows the linked file name, path, storage mode, and note text.

From the dock you can:

- reveal the file in Finder/Explorer
- open it in the default native app
- relink the card if the original file moved

Managed-copy local files live under `user_files/<ProfileName>/files/`. Referenced local files keep pointing at the original path outside Incremento.

---

## 9. Search and Navigation Tools

### Search selected text with Google or DuckDuckGo

Select text in an Anki card or editor, a PDF/EPUB reader, a web/video reader, or the Writing editor/preview. Right-click and choose **Search Google** or **Search DuckDuckGo** to see results in a small, resizable window while keeping your reader open. Choose the provider in **Incremento → Settings → Review → Search engine for selected text**; Google is the default. Standard Copy and reader context-menu actions remain available. The search uses up to the first 1,000 characters of the selection and sends them to the selected provider only when you choose the action.

You can edit the query on the results page to search again. Use **Back** to return from a result, **Open in Browser** to continue in your selected Companion browser, or **Close** (Escape) to return to studying. If a search or website login cannot load in the popup, use **Open in Browser**. Changing providers does not guarantee that CAPTCHA challenges disappear.

**Remember website logins**, in the same Settings tab, applies only to this search popup and defaults off. With it off, closing the popup discards its temporary cookies and website storage. With it on, cookies (including session cookies) and website local storage are saved under `user_files/<ProfileName>/search_profile/` across popup closes and Anki restarts. Each Anki profile has separate storage, also separate from the main Web reader and your external browser. A website may still expire its own login or require an external browser.

Saving a change to **Remember website logins** closes the current popup so the next search uses the chosen storage mode. Turning it off does not erase earlier saved logins; they remain unused until you enable it again. Cancelling Settings leaves the existing search preferences and popup unchanged.

### AI connections (MCP)

Open **Incremento → AI connections…**, enable local MCP, and click **Apply connection settings**. **Allow reversible MCP changes** is a separate opt-in; both preferences default off and are also in Settings → Advanced. The endpoint restarts with Anki when enabled. Close the profile or disable the connection to revoke access. Reconnect the AI client after changing permissions so its tool list refreshes.

- **Codex tab:** use **Copy setup prompt** and paste the complete prompt into Codex or an assistant with local computer access. The prompt includes the MCP configuration and asks the assistant to apply it to the user configuration, preserve unrelated settings, and verify the connection. It respects `CODEX_HOME` and otherwise uses `~/.codex/config.toml`. HTTP connects directly and needs no separate runtime.
- **Claude Code tab:** use **Copy setup prompt** and paste it into Claude Code or an assistant with local computer access. The prompt includes the registration command and asks the assistant to run it in private user scope, preserve other servers, and verify the connection.
- **Claude Desktop tab:** choose **Save Claude Desktop connector…**, select a new `.mcpb` filename, and install it through Settings → Extensions → Advanced settings → Install Extension. Use **Copy token** and paste it when prompted. The bundle uses Claude Desktop's bundled Node runtime and contains no token or user data; it can be shared with other users, who supply their own tokens.

Each tab contains only its client's instructions. The Codex and Claude Code copy buttons include the entire setup prompt, instructions, and connection details. The Claude Desktop copy button copies its token. A chat without local computer access cannot apply local configuration; the copied prompt tells that assistant to explain the limitation rather than claim success. If a reconnect is still required, the assistant reports that remaining step.

Keep Anki open on the paired profile. Other profiles have different tokens; requests cannot switch into them. This version targets local clients, not Claude's cloud connectors or AnkiMobile/AnkiDroid. Text returned by tools enters the client and its AI provider's context. Keep credentials out of shared files.

| Tool | Behavior |
|---|---|
| `get_context` | Return profile/context, permissions, and coverage limitations; call first |
| `search` | Page through cards, books, indexed PDF/EPUB text, or highlights/annotation notes; plain-text words use AND; optional `anki_query` uses Anki Browser syntax and `topic_only` uses configured Topic/Item rules |
| `read_notes` | Read exact notes and their tag/content revisions |
| `read_document` | Read bounded PDF pages or EPUB sections with continuation cursors; positions are one-based for both formats |
| `get_lists` | Page through lists or one list's canonical book IDs |
| `create_list`, `rename_list`, `delete_list` | Manage lists; deleting a list retains books and acquisition notes |
| `update_list_members` | Add/remove up to 100 books atomically, preserving other lists and acquisition notes; supply book IDs and live card IDs from search |
| `update_tags` | Add/remove literal tags on up to 100 distinct notes in one native Anki Undo operation; requires revisions from `read_notes` |
| `update_note_fields` | Replace selected existing fields with safely rendered plain text using a fresh content revision; protects provenance/media identity and requires a stable normal/cloze card layout |
| `get_cards` | Inspect exact card identities, native schedules, deck, flag and suspension, with revision guards for card changes |
| `get_note_types`, `get_decks` | Discover native types and decks with pagination; inspect a type's existing fields and bounded template/CSS text without executing templates or changing schemas |
| `create_cards` | Create up to 20 standalone notes from plain-text fields in an existing normal/cloze type and deck; Anki generates fresh template cards, with optional tags/priority; defaults to the dedicated MCP Q/A type |
| `clone_cards` | Clone distinct notes behind up to 20 selected cards, with fresh scheduling and optional target deck, added tags and priority; selected siblings produce one copied note with all templates; media references are shared without moving/deleting originals |
| `move_cards` | Move selected cards to an existing normal deck while preserving sibling cards, schedules and review history; requires fresh card revisions |
| `set_card_flags` | Set or clear native color flags (0–7), preserving internal flag bits and scheduling; requires fresh card revisions |
| `suspend_cards`, `unsuspend_cards` | Suspend/unsuspend exact cards through Anki with fresh revisions; unsuspend leaves buried/active cards untouched |
| `read_ocr` | Read saved hidden image OCR text (or indexed text when the field is empty/missing), with continuation cursors, index details and a revision; does not run OCR or add fields |
| `search_ocr` | Search existing image OCR indexes with word AND matching and pagination; reports bounded existing-index coverage |
| `update_ocr_text` | Correct combined OCR text plus the search index using a fresh OCR revision; requires an existing OCR field and retains the previous per-image index for undo; preserves images and note types |
| `preview_field_replacements` | Preview literal case-sensitive replacements on up to 50 selected notes; inspect exact before/after text, then use `apply_plan` for one reversible batch; rewritten fields become safely rendered plain text |
| `find_duplicate_notes` | Compare one named field on up to 100 exact selected notes; group case/whitespace/HTML-insensitive duplicates within each note type; does not delete or claim collection-wide completeness |
| `get_review_history` | Page through native review history for exact cards; timestamps are Unix milliseconds, negative intervals are seconds, positive intervals are days, and ease 0 identifies manual scheduling |
| `get_priorities`, `set_priorities` | Read or atomically set priorities on up to 100 live cards; reports the configured priority direction |
| `get_book_details`, `update_book_details` | Read/edit acquisition reason and source, preserving list memberships; edits require a fresh revision |
| `get_bookmarks`, `add_bookmark`, `update_bookmark_comment`, `delete_bookmark` | Manage bookmarks on PDF, EPUB, video, web, and writing cards without changing reading progress |
| `get_highlights`, `update_highlight`, `delete_highlight` | Read existing PDF/EPUB highlights, edit annotation notes/color/style, or delete one highlight using a fresh revision; preserves linked Anki cards |
| `get_knowledge_tree`, `update_knowledge_tree` | Read the tree, add live cards, move nodes, or remove nodes with child reparenting; edits require a fresh structure revision and never delete Anki cards |
| `get_statistics`, `set_daily_goals` | Read study totals and up to 90 days of history; edit card/page/minute goals without changing study history |
| `get_custom_schedules`, `set_custom_schedule`, `clear_custom_schedule` | Manage saved rules for future answers using revisions; does not apply schedules immediately |
| `get_capabilities`, `list_actions` | Discover supported data areas and registered native menu/shortcut actions, including their availability; does not trigger UI actions |
| `get_undo_history`, `undo_change` | Find and reverse retained MCP data changes across profile closes and Anki restarts; each reversal returns a reference for redo |
| `read_source`, `search_sources` | Read/search saved writing, all EPUB sections, PDF pages, saved webpage study copies, and available local subtitle tracks; bounded text with continuation cursors, no automatic transcription or fetching during reads |
| `update_writing` | Replace a managed writing card's Markdown using its fresh source revision; requires its native writing editor to be closed |
| `preview_changes`, `get_plan`, `apply_plan` | Save/review/apply up to 50 concrete actions as one reversible batch; rechecks every affected before-state and compensates failed steps |
| `list_tags`, `preview_tag_changes` | Discover tags and propose exact renames/merges on up to 50 affected notes; apply only through the saved plan, preserving unmapped subtags |
| `get_resource_links`, `update_resource_links` | Read/add/remove direct links to imported PDF pages and local video/audio segments; uses the native resource validator and fresh revisions; files and citations stay intact |
| `preview_session` | Run the real saved scheduler selection with optional query/count overrides, returning selected cards and selection metadata without building a filtered deck or changing schedules |
| `create_source_cards` | Create up to 20 supplied Q/A drafts with dedicated source provenance, PDF/EPUB positions or recording timestamps, and the existing target deck; the assistant supplies the draft text |
| `import_documents` | Import up to 5 local PDFs/EPUBs or public webpages into managed copies, with optional tags/list; originals stay untouched; at most 2 webpage fetches per call |
| `get_ocr_capabilities`, `run_image_ocr`, `run_pdf_ocr` | Detect installed capabilities; run local image OCR or selected PDF-page OCR without installing engines; retain previous text/index/source fingerprints for undo and preserve original files |
| `update_note_html`, `get_media_references`, `attach_media` | Sanitize rich HTML while retaining basic formatting, equations, HTTP(S) links and local media; inspect references; copy selected local images/audio/video to unique Anki filenames with field revision checks and reversible attachment changes |
| `create_deck`, `rename_deck`, `preview_deck_merge` | Create missing normal-deck ancestors, rename/move hierarchies through full `::` paths, and preview complete branch merges; preserve exact native deck/card IDs |
| `change_card_schedule` | Explicit due-day, ease, bury/unbury and reset-to-new controls using card revisions; preserves previous review history and checkpoints all affected sibling cards; does not answer cards |
| `preview_note_type_conversion` | Review mappings from target fields to source fields on one existing text type, including an explicit optional cloze wrap; shows the full-sync consequence before application |
| `preview_note_type_edit` | Review field additions/removals/renames/order, templates and CSS for an existing custom text type; returns native-rendered sanitized HTML/CSS from a disposable collection; all affected notes/cards are checkpointed |
| `preview_note_removal`, `preview_duplicate_merge` | Preview note deletion or suspension-plus-tag archiving, or an explicit duplicate survivor and merged fields; deleted identities, reviews and supplemental rows remain recoverable; media originals remain intact |
| `apply_advanced_plan` | Apply exactly one reviewed advanced proposal with fresh state guards and one durable undo reference; schema/type changes require `acknowledge_full_sync=true` after user review |
| `build_semantic_index`, `get_semantic_status`, `search_meaning` | Build/resume an offline corpus-trained latent-semantic index over note/OCR/source passages; inspect coverage; retrieve related wording with source evidence, optional client-supplied concepts, and stale-source exclusion |
| `find_library_duplicates` | Page through whole-collection first-field exact duplicate groups, normalized with SQLite lower/trim, and bounded near-duplicate candidates across decks; never merges automatically |
| `audit_library` | Read-only checks for missing media/sources, empty visible fields, broken parent/resource links and changed OCR source images; old OCR without fingerprints is reported as unverified |
| `get_smart_lists`, `manage_smart_list`, `preview_smart_list_refresh` | Save/review/delete named Anki-query rules on existing book lists, then preview and explicitly apply membership refreshes; rules and membership changes each retain durable undo |
| `recover_change` | Inspect an interrupted write/reversal and its fresh state revision before explicitly retaining the current state as the undo conflict guard |


For example, ask “Read relevant passages and put my books about decision-making into a list,” “Find Topic cards involving memory and add the tag cognitive-science,” or “Set those cards' priority to 20, then undo that change.” The client classifies retrieved evidence and calls the corresponding data tools. Incremento does not call a separate AI service; meaning search uses a local corpus-trained latent-semantic index.

Generic menu/shortcut triggering is discovery-only. Dedicated reviewed workflows use `list_operation_types` → `preview_operation(action, parameters)` → `apply_advanced_plan(plan_id)`. Discovery returns each action's exact parameter schema. The 97 MCP tools include these 16 areas:

| Area | Reviewed actions |
|---|---|
| Sessions | Start with the native scheduler selection, resume a saved deck, end review; launch keeps native answer tracking/refill |
| Reviewer | Inspect active card/side, reveal question/answer, submit native ratings or Topic More/Same/Less |
| Filtered review | Build/rebuild/empty filtered decks and launch PDF/EPUB/video Review All, including Reminder mode |
| Incremento settings | Read/change public settings, save/delete session presets, edit nine fixed quick-tag sets and collision-checked tag colors |
| Decks and FSRS | Read/change a shared deck preset, enable FSRS, optimize installed native FSRS parameters without rescheduling |
| Readers/player | Read/change saved PDF/EPUB/video/web position/range; control an open local Qt video's play/pause/seek/speed/volume |
| Annotation/capture | Create/resize PDF or EPUB highlights, add PDF snapshot images to fields, import Kindle notebook citations |
| Imports | Writing, Markdown, audio, local video/provider links, live web, local file copy/reference, DjVu, SuperMemo KNO/ZIP, APKG, two-column CSV |
| Video/captions | Download supported provider media, transcode local media, attach bounded clips, import/download target/reference captions |
| Source files | Relink PDF/local-file cards and synchronize PDF annotations, retaining affected managed/original bytes |
| Image occlusion | Read/create/edit native rectangle/ellipse masks and groups; preserve generated card identities on undo |
| Note types | Create/clone/rename or remove unused custom types, with full-sync acknowledgement; managed Incremento types remain protected |
| Export/backup | Export selected cards as APKG/CSV, create/restore native-compatible full ZIP backups, change automatic backup policy, export privacy-safe support ZIPs |
| Maintenance | Rebuild selected PDF/OCR indexes, run integrity repair, quarantine explicitly selected unused files while protecting notes/templates/drafts |
| Timer/jobs | Control the native focus timer and inspect tasks; queue, retry and reverse MCP-owned jobs |
| Administration | Inspect profile/add-on/sync status; refuse sync, profile switching and add-on install/removal under strict undo |

For slow operations, use `start_operation_job(plan_id)` and poll `get_background_tasks`. Downloads/transcodes/clips/caption downloads prepare private bounded assets outside the collection queue, then recheck their target notes and take a fresh checkpoint before publication. Intervening unrelated edits remain outside the job's undo. Queued jobs can be cancelled; running engines finish before their retained result can be reversed. Other native tasks are inspection-only. An interrupted mutation requires `recover_change` inspection before reuse. Jobs requiring schema acknowledgement must be applied directly. Native session startup uses the existing serialized operation without a modal progress window.

Native workflow checkpoints use Anki collection-package export/import rather than collection SQL writes, so actual review history and generated card IDs restore across restarts. These broader checkpoints reject intervening collection/supplemental edits; harmless deck/model navigation is allowed. Before a collection-package restoration, leave the reviewer and close writing editors. A configured sync account must have automatic collection/media sync off for a full restore. The MCP never initiates sync. UI controls require the live Anki adapter; restore may require reopening the relevant timer/player context. Playback restoration restores the saved control state, not elapsed wall-clock time.

These workflows deliberately refuse oversized recovery scopes: at most 10,000 notes, 50,000 cards, 100,000 review rows, 500 note types, 32 MiB note content/48 MiB native checkpoint metadata; supplemental snapshots allow 100,000 rows per table/48 MiB total. Affected files allow 128 MiB each, 512 files/512 MiB total. Sessions and filtered review admit at most 500 cards; candidate queries allow 5,000. APKG preflight runs against an isolated collection copy and caps 400 ZIP entries/256 MiB expanded bytes. CSV imports accept 1–100 `Front,Back` rows without a header. SuperMemo imports accept at most 100 elements and bounded local files. Optional FFmpeg, yt-dlp, DjVu, PDF and OCR engines must already be available; the MCP does not install them. Copies/redo use retained bytes, preserving originals. Full backup restore keeps the current MCP token, permissions, history and recovery assets.

Existing note types are never silently changed: a missing compatible type may be created by an explicit import/card-creation action, while an incompatible existing managed format requires the normal consent-gated update. Note-type lifecycle actions and APKG imports require explicit full-sync acknowledgement. Source-backed drafts use the dedicated normal `Incremento MCP Q/A` type with hidden provenance fields. Managed reader note types, including audio, allow title edits through `update_note_fields`; use the dedicated workflow for other fields or new document copies. Standalone creation/cloning supports existing text types and the dedicated Q/A type; it preserves managed media identities and refuses conflicting template deck overrides. Normal notes need every template card present before editing. Ordinary text/rich edits must preserve the complete existing cloze-number/card set. Use the separately reviewed conversion/schema workflow when changing generated card layouts. Card moves, flags and suspension operate on normal decks; return filtered cards home first. Tag edits use tag-only APIs and preserve unmapped subtags.

For example, ask: “Clone these cards into my Practice deck with fresh schedules,” “Show and correct the OCR on these image notes,” or “Preview replacing this term in the Back field of these notes, then apply the approved batch.” Creation and cloning copy notes, so a reversed/cloze note generates its normal sibling cards. Cloning does not copy reviews, FSRS state or source-specific Incremento scheduling rules. Use `get_cards` revisions before cloning or changing card state. OCR access uses saved local data, never downloads images or installs Tesseract; correction requires the hidden `Incremento_OCR_Text` field to exist already. Native image OCR setup remains explicit. Combined OCR correction replaces per-image rows with corrected combined text; MCP undo restores the previous image-level rows exactly.

The original `search` tools inspect at most 200 candidates per call and existing text indexes, with a 1,000,000-character passage budget. `search_sources` scans at most 20 saved positions per call, including later EPUB sections and available target/reference subtitle tracks; follow its cursor even when a page has no matches. Writing and subtitle files are limited to 2 MiB, EPUB archives to 2,000 entries/48 MiB expanded, and PDF fallback extraction to 128 MiB and 1,000,000 characters per page. `read_source` uses one-based document/track positions and text cursors; `next_position` identifies another section/page/track. Missing or oversized sources prevent complete-coverage claims. Reads never fetch webpage links, install speech recognition, move readers, count pages, or change schedules. Native indexing remains available; local PDF text extraction requires the already optional PyMuPDF dependency.

The advanced tools keep the same client installation. `run_image_ocr` needs an already installed Tesseract executable; `run_pdf_ocr` additionally needs the existing optional PyMuPDF dependency. Capability checks never install software. Image OCR accepts at most two local raster images/16 million pixels each per request; PDF OCR accepts at most three selected pages from a PDF up to 128 MiB. Each OCR process is limited to eight seconds and 1 MiB of output. Recognition finishes before text writes begin. A note without the hidden OCR field uses its saved search index without an implicit schema change. PDF OCR retains selected-page text and file fingerprints in `mcp_ocr_sources.json`; the ordinary PDF indexer preserves matching OCR overrides, including during forced indexing, and discards overrides when the PDF bytes change.

Rich HTML removes scripts, event handlers, remote media and active CSS. Attachments accept selected local raster/audio/video files up to 32 MiB, copy them under unique Anki media names and retain private recovery bytes; replacement preserves the old media file. Undo refuses to remove a copy that another note subsequently references. Template previews return native-rendered HTML/CSS without running JavaScript or opening a window. Existing `Incremento ...` note types retain their native consent-gated format-update path. Custom text-type conversion and schema changes require a concrete preview and an explicit full-sync acknowledgement. Undo restores local fields, templates, card identities and reviews; **Anki can still require a full sync after a schema change is undone**. Schema changes may clear Anki's in-memory Undo stack, so use MCP undo for the complete operation. No tool starts AnkiWeb sync. Reset-to-new affects Anki scheduling and retains past reviews plus Incremento's separately saved rules/topic metadata; due changes avoid adding manual revlog entries so the prior history can be restored exactly.

Native recovery operations are bounded to 100 notes/500 card identities, 5,000 review rows per note and 4 MiB of snapshot metadata, with native recovery packages up to 48 MiB. Larger changes must be divided into reviewed batches. Deletion removes every card belonging to the selected notes; archives suspend those cards and add `incremento::archived`. Duplicate merge preserves the chosen survivor's scheduling; removed notes/reviews remain in recovery packages and are not combined into a synthetic FSRS history. Deck merges include complete source branches and refuse the Default deck, filtered decks and destinations inside the source branch.

Meaning search uses latent semantic indexing learned from your saved corpus, blended with literal evidence; it is not a pretrained world-knowledge model. Optional related concepts supplied by the AI client can expand a query. Build/resume processes at most 60 chunks of 4,000 characters per call, up to 2,000 passages/12 MiB per profile. Follow continuation cursors; after restarting, call build without an old cursor to resume saved progress. Each build batch is reversible, and stale cursors after undo are rejected. Search returns only indexed evidence and excludes changed notes/source passages; coverage and unavailable-source counts remain explicit. Unindexed, oversized or unavailable material prevents a whole-library completeness claim. Exact duplicate grouping uses the native HTML-stripped first field with SQLite lower/trim; near matches use bounded prefix/token candidates and do not prove that other duplicates are absent. Health audits inspect a page of notes, at most 100 cards per note and 200 reported issues, with explicit truncation and unverified-OCR counts.

Smart lists are profile-local named rules in `mcp_smart_lists.json`. Saving a rule does not alter membership or start background jobs. Refresh resolves the full bounded Anki query, previews additions/removals and rechecks both rule and candidate revisions before application. It refuses queries over 5,000 cards/500 books rather than treating a partial scan as an empty result. Other lists and acquisition notes are preserved. Refresh undo restores the membership snapshot even if time-based query matches change later. The semantic index, OCR source registry and smart-list rules are private profile files with atomic writes and retained compressed before-states under `mcp_undo_files/state/`. These files and native recovery packages belong to private full backups, not connector bundles, support diagnostics or releases.

Operations after `get_context` require its current `context_id`. Writes require a unique `request_id`; retry with that ID and identical action arguments. The server keeps its bounded reply cache, while completed write outcomes also live in the private durable history so a reconnect/restart cannot duplicate a creation or applied plan. Reused IDs with different arguments are rejected. A timeout may leave an already-running operation committed: inspect current state and `get_undo_history` before trying another write. Queued cancelled work cannot execute later. An interrupted write/reversal retains a pending record: inspect it through `recover_change`, review the shown before/current states, then confirm the fresh `state_revision`. Recovery does not silently overwrite uncertain intervening edits.

Every MCP data change returns an `undo_id` (`null` for a no-op). Ask the assistant to undo it or call `undo_change`; the reply returns a single-use inverse reference for redo. `get_undo_history` lists dated references (timestamps are UTC) in durable action order and labels them `undo`, `redo`, or `pending`; supply an `undo_id` to inspect that action and bounded before/after previews; successive Undo requests should select the newest remaining `undo`. Reversals compare exact affected user data, refuse intervening edits, and preserve monotonically increasing scheduling-rule versions. Ordinary Anki Sync transport counters and derived modification timestamps do not create a false conflict when semantic content/schedules are unchanged. Tag/text/card-state edits also use native Anki Undo. OCR corrections use MCP undo for the complete field-plus-index change. For a batch, import, resource change, or writing edit, use MCP undo to restore the complete operation, including supplemental rows/files.

OCR reads inspect at most 200 saved image rows/2 MiB per note, and return at most 16,000 text characters per chunk plus bounded image details. OCR search scans at most 200 index rows per request and the first 16,001 characters per row; follow cursors even for empty result pages. Native card inspections bound note content to 512 KiB. Standalone authoring accepts at most 20 notes per request and 20 templates/cloze numbers per note; cloze numbers range from 1 to 500. No note-type/deck schema edits or scheduling resets are implicit.

Private history survives profile close and Anki restart in `user_files/<profile>/mcp_history.json`, written atomically with restrictive permissions. Retained native `.apkg` recovery copies and quarantined managed imports live under `mcp_undo_files/`. Creation undo refuses edited/reviewed/referenced cards, uses Anki APIs for note/card removal and identity-preserving restoration, and reverses new unused note types too. Import undo moves only its exact tracked managed copies into retained undo storage; original files and later unrelated files are never removed, and redo does not refetch websites or reread originals. History is capped at 1,000 active references/16 MiB of metadata/snapshots; oversized changes or full history refuse new mutations without evicting retained reversals. Binary recovery assets are retained with their references. Applied preview drafts may be pruned while their reversal snapshots remain; at most 100 unapplied proposals are retained. Full profile backups include this private history/assets; release packages, connector bundles, and support diagnostics exclude them. Undo cannot reverse external AI-provider processing of retrieved text, and supplemental records/history do not use Anki Sync.

If setup fails, check local port 8767. A wrong token or another profile is rejected. The persistent private token lives under the profile's `mcp_token` file and is excluded from backups; restored or new profiles must be paired again. Browser Companion port 8766 and its authentication remain separate.

### Search ALL

Choose **Incremento → Search ALL** or use its shortcut.

It searches across:

- PDF highlights and sources
- EPUB highlights and sources
- **Annotations**: your notes attached to PDF and EPUB highlights, independently of the highlight filters
- PDF file content
- EPUB file content
- cards

Search results include a preview panel. Hovering a PDF or EPUB highlight previews the saved highlighted passage. Annotation results show your note above the page or section text, mark its source passage within that text in the original highlight color, and automatically scroll to the marked passage. This works even when the search words appear only in your note, and tolerates PDF line wrapping, hyphenation, and ligatures. If indexed context is missing or the source cannot be matched, the preview shows the saved source passage in its highlight color. The preview header identifies the document and page or section. Source and file-content hits preview the indexed page or section for context. Enable **Annotations** to find words such as `failure mode` in your notes even with both highlight checkboxes off. PDF hits can open directly to the matching page, and card hits can open in the Anki Browser.

Changing a result-type checkbox applies immediately, including when **Search while typing** is off. **Existing Anki Items Only** hides indexed results whose linked document card or source note has been deleted; searches always remain scoped to the active Anki profile.

PDF results are always hidden when their Anki document has been deleted or its PDF file is missing, including under **Cards**, even with **Existing Anki Items Only** off. A missing or moved file alone does not delete saved data. Confirmed Anki deletions remove only the derived PDF text index; Search ALL also clears older stale entries in the background. Highlights, annotations, extracted cards, source links, and PDF files are preserved. Anki **Undo** restores the document; with **PDF file content** enabled, Search ALL rebuilds its searchable text in the background. **Redo** hides it and clears the text cache again.

The complete search runs in the background, including result validation, note retrieval, and ranking. Completed result sections appear while the remaining categories are searched. **Cancel** stops the current search; results already shown may be incomplete. Typing a new query replaces obsolete work, and results from an earlier query, closed dialog, or previous profile are discarded. The search keeps only the newest pending request, so rapid typing does not build a queue of old searches.

PDF text extraction never scans the whole library on Anki's UI thread. Search-while-typing waits briefly for you to pause, bounds card candidates, and discovers PDF documents through Anki's background query queue. If searchable text is missing, Search ALL starts a profile-scoped background index, shows progress, and lets you cancel after the current PDF. File modification time, size, and index status are remembered so unchanged PDFs are skipped and repeatedly failing files are not retried on every keypress. The first search after upgrading may refresh an older unsigned PDF index once so it cannot silently reuse text from a replaced file. EPUB and OCR text use the same bounded SQLite/FTS search layer; systems without SQLite FTS5 fall back to bounded ordinary-table search.

### Quick Open Content

Choose **Incremento → Quick Open Content** to fuzzy-search document and writing cards by title.

It shows:

- title
- type
- priority

Modes currently include:

- Docs: PDFs and EPUBs
- Writing: markdown writing cards

It also supports fast actions inside the dialog:

- `Ctrl+F` -> open first in priority queue
- `Ctrl+R` -> open a random visible note
- `Ctrl+L` -> reopen the last opened note for the current mode

### Knowledge Tree

Choose **Incremento → Open Knowledge tree** to work in a card-backed topic tree.

The knowledge tree lets you:

- inspect parent/child relationships between cards
- create or attach extracted cards under a selected node
- launch branch-scoped study sessions
- postpone, reprioritize, or subset-review a whole subtree

The tree browser has a compact **Study**, **Add**, **Mind Map**, search, and **Refresh** toolbar. **Workspace** and **Search** share one tabbed area above the tree. A breadcrumb shows the selected node's path, and the Priority column pairs each number with a green, amber, or red urgency bar. The selected-card pane shows its type, priority, full visible note text, card ID, and available source or citation. Use **Inspect** to open it in Anki Browser, or **More** for the same actions available by right-clicking a tree node. The urgency colors follow the configured priority direction.

The tree loads in the background and shares one snapshot with its search panel, so searching does not reload every card. The snapshot refreshes after tree edits and Anki collection changes, when the workspace regains focus, or when you choose **Refresh**. Selection and expanded branches are preserved across refreshes. Closing the workspace or switching profiles discards pending loads. Cards that no longer exist are hidden, and their surviving children are shown under the nearest surviving parent; loading the view does not delete saved tree records.

Click **Mind Map** to generate a read-only visual map from the current knowledge tree. The map follows the main Tony Buzan-style conventions: one central idea, radiant hierarchy, curved connected branches, a distinct color for each main branch, concise branch labels, symbols, and progressively lighter visual weight at deeper levels. Choose **Whole tree** or **Selected branch** and optionally show card priorities. Scroll normally, Shift-scroll horizontally, drag empty space to pan, or Cmd/Ctrl-scroll to zoom around the pointer; **Fit**, **100%**, and the zoom controls provide precise alternatives. Click a node to select it, use the arrow keys to move, press Space or `/` to fold or unfold its branch, and press Enter or double-click to return to that card in the tree. Fold badges show the number of hidden descendants, while **Collapse All** and **Expand All** control the full map. **Find** highlights matching titles and reveals folded ancestors, **Focus Branch** isolates the selected branch, hovering shows the full unshortened title, and **Export PNG…** saves the current map. When the tree has multiple roots, the map creates a synthetic **Knowledge Tree** center; a single root or focused branch becomes the center directly. You can also right-click a node and choose **View Branch as Mind Map** to open that subtree immediately. Tree editing remains in the normal workspace.

---

## 10. Statistics and Focus Timer

### Statistics

Open **Incremento → Statistics** for a progress overview: large **Pages read**,
**Study time**, and **Cards studied** totals, PDF/EPUB counts, a reading streak,
and comparisons with the previous equivalent period. Daily goals stay visible
above the overview. The dialog opens on **Today**.

Two graphs appear immediately: **Daily activity** and **Progress adds up**.
Choose **Pages**, **Study time**, or **Cards** to change both graphs together.
Pages use separate PDF and EPUB colors. The first graph includes a dashed line
for the current daily goal; the second shows the running total within the graph's
date range. Quiet days remain visible. Reading days, active days, and average
pages per calendar day help show your pace without excluding days off.

Today shows the last seven days of graphs. The 7 Days and 30 Days scopes graph
their selected periods; Year groups its daily records into seven-day totals,
including a partial last group, and omits the daily goal line. All Time keeps
lifetime totals above clearly labelled graphs for the last 30 days. Click either
graph, or focus it and use Left/Right, Home, or End, to inspect exact dates,
PDF/EPUB pages, study time, card counts, and the accumulated total.

The reading streak counts consecutive recorded days with PDF or EPUB reading;
if you have not read today yet, yesterday's streak stays visible. Cumulative
pages sum daily page observations, so rereading a page on another day counts
again. A study-time-only day does not imply any pages or answered cards.
**Refresh** reloads the statistics without reopening the window. Changing goals
updates the graph marker immediately.

Switch to **Documents** to see every PDF and EPUB in a searchable list, with
**Pages read**, **Pages left**, **Total pages**, and a completion bar. Use the
All formats / PDF / EPUB filter to narrow the list. The list shows 50 documents
at a time, and search covers the entire library. These are all-time completion
figures, independent of the Overview date range.

Completion uses the readers' saved **Mark read to here** progress, rather than
adding daily page visits. For PDFs, the denominator is the actual file's page
count, including blank pages. A missing or unreadable file shows an unknown
total and percentage. Update the marker in the reader, then click **Refresh**
in Statistics to reload it.

EPUB rows are labelled **est.**: reflowable books have no universal screen-page
count. Statistics uses a stable reference of 1,500 cached text characters per
page, rounded up within each section (at least one page per section). Counts
can differ from the reader's window-dependent pagination. The saved section
marker determines the read range; a saved text marker narrows it to reference
pages before that location, and **Finished** sets it to 100%. A default first
section with no text marker counts as unread. Missing cached metadata shows an
unknown total; opening the EPUB in its reader can make that metadata available.
Loading this view does not extract books or change reading progress.

Switch to **Learning cards** for both the current **New → Learning → Review**
breakdown and daily answer/recall graphs. **Relearning** appears separately.
The stage bars show each stage's share of memory cards across all decks,
including suspended and buried cards in their existing stages; their counts
appear below the bars. Topic and reader cards are excluded. Review is ongoing
spaced practice, not permanent completion. Stage counts always describe the
current collection, while the trend selector chooses the last 7 or 30 days.

The two learning graphs show recalled/failed answer attempts and daily recall
rate side by side. Use the day selector for exact figures with the keyboard,
or hover over the rate graph. The period comparison is weighted by answer
attempts. Repeats count, so this is an answer-level recall rate, not Anki's
first-review-per-card-per-day **True Retention** metric. Quiet days are gaps in
the rate graph. **Refresh** reloads both the history and current stages; Anki's
Undo/Redo remains authoritative.

Below the overview, **Topics by tag** and **Items by tag** pie charts show each
chart's total reviewed-card count below the title.
Percentages appear inside the slices, rounded to one decimal place when needed;
slice size and each legend entry use the reviewed-card count.
The charts use the shared **Day ends at** cutoff in **Settings → Review → Statistics** (default `04:00`, local time), and include reviews outside Incremento sessions. Anki's native **Studied … today** summary uses Anki's own day boundary.
Topic/Item classification tags are omitted from the
legend so the chart uses the first meaningful content tag; cards without one
appear as **Untagged**. Incremento also removes the separate Session Timer
summary from this screen because its “minutes in session” includes time while
Anki is simply open.

The dialog opens on **Today** by default; the same tag split is available in
**All Time**. Today also shows **Pages read**, the sum of unique PDF and EPUB
pages visited during the current logical day.

The **Reading & video** panel appears in Today, 7 Days, 30 Days, Year, and All
Time. It shows total pages read, separate PDF and EPUB page counts, distinct
videos played in Incremento, and video watch time. The page totals count each
document page once per logical day. Video watch time starts with this update:
it counts observed playback, excluding pauses and seeks. It cannot be
reconstructed from old resume positions, and playback in an external browser
is not included.

**Statistics → Today** shows **Today’s learning results**: total answer attempts,
**Again / Fail**, **Recalled**, and the recall
rate. **Recalled** means Hard, Good, or Easy; the recall rate is those answers
divided by all counted answer attempts. The table separates Learning, Review,
and Relearning using the stage recorded when each answer was given.

Repeated attempts count separately: three Again clicks on one card mean three
failed attempts and one card with Again. The panel also shows unique cards and
unique cards with Again. Results come from Anki's review history, include study
outside Incremento sessions, follow native Undo/Redo, and use the shared **Day
ends at** cutoff. Current Topic/Item classification rules exclude topic frequency
choices from recall results. Preview practice and manual schedule changes are
also excluded. Normal rescheduling filtered-deck reviews are included.

Choose **7 Days** or **30 Days** for the same failed/recalled totals across that
period, including today. A stacked daily graph shows **Recalled** in green and
**Again / Fail** in orange. A second graph shows the daily recall rate on a fixed
0–100% scale; days without answers leave a gap. Hover over the rate graph for a
day's attempts, failures, recalled answers, and percentage.

The panel compares the selected period's recall rate with the preceding 7 or
30 days and reports the change in percentage points. Period rates use total
recalled answers divided by total answer attempts, so quiet days do not outweigh
busy days. If either period has no answers, it reports that instead of inventing
a comparison. Past results are backfilled from Anki's review history using the
same daily cutoff and exclusions as Today.

Scopes:

- **This Session**
- **Today**
- **7 Days**
- **30 Days**
- **Year**
- **All Time**

Free study in Anki is included: Incremento measures from question display to
answer display and records the answer separately. It does not use the time Anki
has merely been left open on the deck browser.

Current statistics include both count-based and time-based views:

- card types
- selection mode
- tags
- review time by card type
- review time by tag

The 7- and 30-day views add daily stacked graphs for:

- Topics, Items, and other reviewed card types
- unique PDF and EPUB pages read
- study/review time

They also show total cards, total pages, study time, active days, the current activity streak, and active-day averages. A page is counted once per document and logical day even if you revisit it or restart Anki. The shared **Day ends at** setting used by scheduling determines when a new statistics day begins.

Use **Edit goals…** to choose only the daily measures that support your study:
cards, pages, or minutes. Each goal has an explicit on/off choice instead of using
zero as a hidden off state. When recent activity is available, Incremento suggests
a realistic starting target from the median of positive activity days in the last
30 days; unusually large sessions therefore do not set the pace. Suggestions are
optional and never change a goal until selected and saved. The main Statistics
window shows progress only for enabled goals. Goal progress is based on the same
logical day as scheduling.

The 7-day, 30-day, and Year scopes compare their totals with the preceding
equivalent period and include an activity heatmap. Change the heatmap metric
between all activity, cards, pages, and minutes; selecting a day shows its Topics,
Items, other cards, PDF pages, EPUB pages, and study time. **Export History CSV…**
exports up to the latest year of this normalized daily history.

EPUB stays separate from PDF in these views.

### Focus timer

Enable **Show Focus Timer** to keep the toolbar visible at the top of Anki.

Features:

- presets from 5 to 60 minutes
- start / pause / resume
- reset
- end-of-session summary

In **Incremento → Settings → Review**, you can also make the focus timer auto-start for selected card types and optional tag filters, and choose whether it plays a beep when the timer ends.

The summary shows:

- cards reviewed
- unique PDF pages read
- unique EPUB pages read
- number of PDFs touched during that timer session

The cumulative **Today so far** line also uses the persisted unique-page history, so reading performed before starting the focus timer remains visible.

---

## 11. Priorities, Extraction, and the Add Card Dock

### Per-card priority

Press `Alt+P` to open the priority dialog for the current review card. The same
action is available as a visible `P` toolbar button in Anki's **Edit Current**
window. The Browser editor also shows `P` for the selected card.

Priority scale:

- `0` = highest importance with the default priority direction
- `50` = default
- `100` = lowest importance with the default priority direction

You can reverse that interpretation under **Incremento → Settings → Review → Priority direction**.
In the same Review tab, **Show reviewer priority badge on** has separate **Topic cards**
and **Item and other cards** checkboxes. Both are on by default. These control
the whole floating reviewer badge (priority and any available A-factor, saved
browser time, or custom schedule), not the priority value or scheduling itself.
Topic classification follows your Topics settings; every non-topic card uses
the Item and other option. Turning a type off also hides the badge immediately
when that type is currently on screen.

### Priority while creating a card from scratch

Both Anki's normal **Add** window and Incremento's persistent **Add Card** dock expose a `P` toolbar button for a new standalone note. Click it, choose a value from `0` to `100`, and then add the note normally. A compact **Card priority** number field above the editor fields shows the same value for quick entry.

The chosen priority is saved for every card generated by that note. This matters for note types with multiple card templates. Each newly loaded blank note starts at the neutral priority of `50`; media and reviewer extraction flows continue to use their separate **Extract Priority** control.

For topic cards, the dialog can also expose **A-Factor**, which adjusts the topic's interval behavior.

### Batch Q/A cards

Both Anki's normal **Add** window and Incremento's persistent **Add Card** dock expose a `Q/A` toolbar button. It opens a batch editor for creating many cards against the note type and deck selected in the originating Add window.

Paste either alternating non-empty lines—question, answer, question, answer—or labeled `Q:` / `A:` blocks. Labeled blocks may contain multiline questions and answers. Click **Preview Cards** to see every proposed card before anything is created. You can edit questions and answers, delete unwanted rows, map question and answer text to any two visible note fields, and set each row's priority, Topic/Item/Other classification, and tags.

The **Apply to all cards** controls copy one priority, classification, and tag set to every preview row; afterward, individual rows can still be adjusted. Tags may be separated with spaces, commas, or semicolons. Click **Extract Cards** only after the preview is ready. When the batch starts from an active Incremento extraction, its existing source metadata and lineage are retained; a standalone batch remains independent of any extraction open in another Add window.

### Extract Card from the current reviewer card

Click **Extract** or press `Alt+X` to open the persistent **Add Card** dock with empty content fields. Opening Extract never copies the source card or selected text into Front automatically. The current source URL and provenance fill immediately in existing source fields. Use the field transfer buttons or `Cmd/Ctrl+1..4` when you want to insert selected text.

Reviewer extraction stays active while you use the dock. Each **Add** attaches the new card to the reviewer topic currently open when you press **Add**. Whenever the current topic changes—through **More**, **Same**, **Less**, **Done**, postponing, or other navigation—the open extract clears the previous draft content and immediately fills the new topic's source and provenance fields, updates its parent, copied source tags, and initial extract priority. Front stays empty until you type or transfer text. Existing `Source`, `Sources`, `URL`, `Source URL`, `Source_URL`, and `sourceUrl` fields are recognized. **Sources** retains the original clickable titles, multiple references, and HTML formatting. Note types are not changed by this refresh. If the new topic has no source, the old source is cleared. Refreshing the same topic keeps your edits. An in-progress save keeps the topic and text captured at the Add click, then the next draft adopts the current topic's source.

With no active reviewer card, Add creates a standalone note instead of reusing the previous topic. An explicit extraction from a PDF, EPUB, webpage, writing card, or video switches to that source's extraction workflow. Discarding or closing the embedded Add dialog ends reviewer extraction. Restoring a reviewer draft resumes attachment to the current reviewer card.

Reviewer extraction lets you:

- explicitly transfer selected reviewer text into the chosen field
- choose any note type
- choose any deck
- create a new note directly

Settings can control:

- the default extract note type
- fallback extract priority
- how strongly source priority influences new extracts
- the default extraction tag: **Item** (default), **Topic**, or **None**, under **Settings → Extraction → Default extraction tag**; Item and Topic use the configured `I`/`T` tag sets
- whether source tags are copied
- whether extraction also creates a highlight
- which Add Card field PDF highlight cards should prefill
- which provenance links are stored in dedicated Incremento metadata fields

### Add Card dock

The Add Card dock is a persistent docked version of Anki's Add dialog.

It is used by:

- PDF extraction shortcuts
- selected text transfers from web pages
- selected text transfers from writing cards
- timestamp-based video note creation

When text is selected in a supported source, transfer buttons appear next to Add Card fields so you can insert the selection directly.

After drawing a PDF snapshot, the field picker includes **Always use the field I choose**. Check it before choosing a field to remember that field for the current note type. Later PDF snapshots using that note type are inserted there automatically; if the field or note type is no longer available, Incremento safely shows the picker again. Turn off **Automatically use remembered PDF snapshot fields** under **Settings → Extraction** to ask every time again.

MathJax recognition uses **LaTeX-OCR (pix2tex)** locally in a separate process. No recognition account, API key, or per-scan quota is needed. In a PDF, EPUB, or web reader, click **Snapshot**, select a rectangle closely around the formula, then click **Scan for MathJax…** in the snapshot preview.

On first use, click **Set up / repair local LaTeX-OCR**. Setup creates an isolated Python environment and downloads pix2tex, PyTorch, and the model. Allow several minutes and several GB of free disk space. It uses an installed Python 3.10–3.12; Python 3.11 is recommended. If Python is missing, install it from [python.org](https://www.python.org/downloads/), restart Anki, and retry. On Windows, enable the Python installer's PATH option. Setup does not change Anki's Python environment and never uploads the snapshot. Closing the scanner cancels the active process; setup can be retried after an interrupted download.

Setup displays the current step (1–4), software download counts, and elapsed time. Formula-model and image-preparation-model downloads show measured percentages and downloaded/total MB. Installation and model loading show an animated bar while no reliable percentage is available. Formula recognition also shows its current stage and elapsed time. The progress bar disappears when the operation finishes, fails, or is cancelled.

When setup reports ready, click **Scan for MathJax**. Check and edit the recognized LaTeX, then use the existing inline MathJax, display MathJax, or plain LaTeX Copy buttons. The clipboard changes only when Copy is clicked. Recognition works offline after setup; each scan starts a local worker, so loading the model adds a delay. Closing the scanner or switching profile/source cancels its worker and discards stale results. If model files are missing or recognition cannot start, run **Set up / repair** again.

Dependencies and models are shared on this computer under `~/Library/Caches/Incremento/latex-ocr-v1` on macOS, `%LOCALAPPDATA%/Incremento/latex-ocr-v1` on Windows, and `~/.cache/Incremento/latex-ocr-v1` on Linux. Crops travel through the worker's input pipe and are not saved. These dependencies are excluded from profile backups and are installed again on another computer. Old SimpleTex credential files are no longer used and remain excluded from exports.

When recognition succeeds, **MathJax found** appears with editable LaTeX. Check and correct the formula, then choose **Copy inline MathJax**, **Copy display MathJax**, or **Copy LaTeX**. Close the snapshot dialogs (Cancel leaves the image uninserted) and paste into any Anki field. MathJax copies already include Anki's inline `\(…\)` or display `\[…\]` delimiters; plain LaTeX copies omit them. Chemistry commands such as `\ce{…}` are preserved for Anki's built-in mhchem support, but unsupported chemistry drawing packages may need manual rewriting. Recognition quality depends on the crop, so always check the result. If remembered PDF fields bypass the preview, turn off **Automatically use remembered PDF snapshot fields** to access the scanner. Scans accept PNG crops up to 8 MiB and 16 million pixels and run in the background; closing the scanner or changing document/profile discards pending results. This action is available in Incremento's three readers, not Companion browser capture.

An **Extract composer** strip keeps the current source, priority, Topic/Item choice, tree-link choice, and batch action together. Non-empty extraction drafts autosave after edits under the active Anki profile. If Anki or the dock closes before the note is added, the next Add Card dock offers **Restore** or **Discard**. A successful add or explicit discard clears that saved draft.

If you close an unfinished extract and confirm **Discard**, the Add Card dock closes with it and clears that draft's source context. The next extraction opens a fresh Add Card dock.

Each `Cmd/Ctrl+1..4` transfer refreshes Incremento-managed tags against the current source. When you move from one PDF or other source to another, source/topic tags that Incremento added and that no longer apply are removed, shared tags remain, and unrelated pre-existing tags are preserved. This cleanup also follows Anki's tags into the next blank Add note, because Anki normally carries tags forward after a note is added.

The settings dialog also lets you choose the tags applied by the dock's **Topic** and **Item** buttons.

---

## 12. Support Bundles, Export, and Restore

### Privacy-safe support bundle

If Incremento behaves unexpectedly, choose **Incremento → Export Support Bundle…** and attach the resulting ZIP to the issue report. Incremento automatically keeps a small per-profile diagnostic history after this version is installed; events from older versions cannot be reconstructed.

The support bundle contains:

- sanitized Incremento configuration: booleans, numbers, safe modes/enums, and shortcuts remain visible, while names, labels, tags, filters, paths, URLs, hashes, and other free text become redaction markers
- recent UI state transitions, Anki operation categories, numeric card queue/type/final-interval states, answer ratings, Incremento session build phases/refill outcomes/exit events, media Review All lifecycle plus normalized picker choices/counts, and privacy-safe topic/custom-schedule results or failure stages
- Anki, Python, add-on, operating-system family, architecture, and enabled-add-on counts
- safe current-session counts/flags, diagnostic-writer health and dropped-event counters, known Incremento database table row/column counts plus a schema fingerprint, and hashes of a fixed list of shipped code files

It does **not** contain card or note text, raw card/note IDs, deck/tag/profile names, media, user or media filenames, local filesystem paths, URLs, browser history, database rows, exception messages/tracebacks, or precise activity timestamps. Fixed shipped-code filenames are included only beside their hashes so an installed build can be identified. Error events retain only the exception class, such as `OperationalError`. Event timing is elapsed time within an Anki run.

Diagnostic logs are stored under the active profile's `user_files/<ProfileName>/diagnostics/` directory. They are capped at three 1 MB files, and an export includes at most the latest 5,000 validated events. Reviewer and scheduler hooks only enqueue typed events into a bounded 2,048-event memory queue; a background writer performs filesystem work, and a full queue drops events instead of delaying review. The bundle includes those dropped-event and writer-health counters. The exporter parses and revalidates every event instead of copying the raw log files, and it runs outside Anki's serialized collection-task queue so it can still capture diagnostics when a collection operation is stalled.

### Full backup and restore

Use **Export Full Backup** to create a single ZIP for the currently open Anki profile. Use **Incremento → Restore Full Backup…** to restore one into the open profile. The restore picker starts in that profile’s configured automatic-backup folder if it is available, but accepts a full backup ZIP from any folder.

The backup includes:

- `anki/all_decks.apkg` for the currently open Anki profile
- `user_files/<ProfileName>/`, containing the Incremento runtime data for the currently open profile
- `config.json`
- `manifest.json`
- JSON copies of priorities, PDF progress, highlights, and stats
- `restore.txt` with the restore order

Before replacement, the restore flow validates the outer ZIP and embedded Anki package, checks their contents for corruption and unsafe paths, checks both SQLite databases and key collection relationships, and compares counts and schema metadata with the manifest. It displays the source profile and counts for review, including a warning if PDF/EPUB cover images are missing from an older package. New backups include these cover files explicitly. On confirmation, it creates an Anki safety backup, replaces the current profile’s collection, Anki media, and Incremento runtime files, then reopens the profile. An error during replacement or reopening triggers rollback; if rollback fails, the prior files remain in restore staging folders and their locations are reported. Automatic collection and periodic media sync stay off until you re-enable them after checking the restored profile. The pre-check does not compare with AnkiWeb; an ordinary later sync may merge remote changes or deletions, while one-way **Upload** makes the restored cards authoritative and **Download** replaces them. Media sync always merges separately. See `EXPORTING.md` for the steps and limits of this pre-check.

The full backup is private and intentionally contains your cards, media, database, paths, and raw configuration. Do not attach a full backup to a public issue; use **Export Support Bundle…** instead.

The APKG and `user_files/<ProfileName>/` snapshot always refer to the same active profile. Restoring this archive does not require deleting other existing Incremento profile folders.

Incremento copies the database through a dedicated read-only connection using SQLite's backup API and checks both the source and the completed copy. This avoids false search-index errors from a reused background connection; a failed integrity check still stops the export and preserves the previous backup. It writes and validates a temporary ZIP before atomically replacing the selected destination. Automatic exports keep that work file outside the selected folder when the filesystem permits, so cloud-sync software sees only the completed slot. If the active profile changes during export, the operation stops rather than mixing data from two profiles.

Choose **Incremento → Export Full Backup → Automatic Backups…** (or the separate **Configure Automatic Full Backups…** menu item) to select a folder, enable backups for the current Anki profile, and choose **when the profile opens**, **when it closes**, and/or an interval in hours while Anki stays open (0 turns the interval off). **Export Now…** keeps the one-time save flow. Choose how many automatic versions to keep, from 1 to 20 (5 by default). Incremento creates slot files until that count is reached; after that, each successful, validated backup atomically replaces the oldest automatic ZIP at the same path. For example, with five selected, the sixth backup replaces the first. Older timestamp-named automatic ZIPs count toward the limit and are reused instead of creating a second set of slot files. The first timed backup runs when due; reopening with the on-open option selected creates a new backup. Automatic backups run in the background with a progress window that explains why Anki is temporarily unavailable and shows the current stage. Progress and failures also appear in Activity Center. Collection operations may briefly queue behind the export. If close backup is selected, Anki waits for the backup attempt to finish before unloading the profile, so shutdown or profile switching may take longer. An existing backup also finishes before the profile unloads. A failed close backup is flagged when that profile next opens. Each new ZIP is verified before an existing automatic ZIP is replaced or excess automatic ZIPs for that profile are rotated; manual exports and other profiles' backups are untouched. A missing or inaccessible destination produces a notification rather than switching to another folder.

A folder synced by the Google Drive desktop app (or another cloud-sync app) can be selected. Incremento builds automatic backups outside that folder when possible, validates them, and then exposes only the final fixed slot to the sync service. Incremento itself does not sign in to a cloud service or verify that the ZIP finished uploading. Temporary `.incremento-backup-*.zip` items uploaded by an older version may need to be removed once in the cloud provider's web interface because they can remain remotely after disappearing from the local folder. These full backups include private cards, media and configuration: protect the sync account and destination accordingly. Keep an additional backup outside the sync service if you need protection against cloud-side deletion or account loss.

---

## 13. Settings, Utilities, and Dependencies

### Settings dialog

Choose **Incremento → Settings** to open seven tabs:

- **Language**: choose Automatic (follow Anki), English, Hrvatski, or 简体中文

- **Extraction**: local LaTeX-OCR setup guidance for MathJax recognition, default extract note type, extract priority behavior, PDF highlight card target field, PDF citation page numbering (printed labels, PDF numbers, or both), remembered PDF snapshot-field reuse, topic/tag defaults, and saved provenance link types
- **Review**: priority direction, per-type reviewer badge visibility, post-answer prompt behavior, browser/PDF/web reviewer defaults, item skip, focus-timer auto-start, and custom scheduling presets
- **Topics**: which card types/tags count as topics, the Done tag, the default topic A-factor, More/Less strength, the maximum topic interval, Add Card topic/item tags, whether Incremento auto-creates the `Topics` deck, which profiles that applies to, and the red Postpone button behavior
- **Writing**: editor defaults, automatic backup intervals, progress visibility, default progress scope, and word-count mode
- **Shortcuts**: assign or clear shortcuts for Incremento actions
- **Advanced**: open the guarded profile database inspector

The **Language** tab saves your choice with **OK**; **Cancel** discards it. Restart Anki yourself to apply a new language. Existing readers, reviews, and unsaved drafts keep their current interface language until then. Reopening Settings shows the saved choice. The setting applies to the add-on in this Anki installation; it does not change Anki's own language.

To create or edit a translation, use **Export template…** or **Export selected language…** in this tab. Open the CSV in Excel, Google Sheets or LibreOffice, edit only the `translation` column (including the language code and native name in the metadata rows), save as CSV UTF-8, then use **Import translations…**. Import previews the language and translated-entry count; **OK** saves it, **Cancel** discards it. Blank entries use English. Re-importing the same locale replaces that custom pack, so export the existing language before making corrections. The same CSV includes the add-on, PDF reader and Chrome extension and can be imported in both apps. See [TRANSLATING.md](TRANSLATING.md) for the complete spreadsheet walkthrough, placeholder/plural rules and troubleshooting.

Imported Anki language packs belong to the active profile, under its `language_packs/` directory. If the saved language choice points to a pack absent from another profile, that profile uses English; import the CSV there separately to use it. Selecting a built-in language restores its shipped translation. Pack import never replaces a built-in catalog or translates user content.

Incremento's **More → Review buttons** submenu, reviewer overlays, preview details, bookmark controls and generated reader labels follow this choice too. Native Anki actions beside them, such as **Replay Own Voice** and **Auto Advance**, follow Anki's own language preference. Settings guidance wraps into a full-width row so longer translations remain readable.

The Chrome companion has its own **Settings → Language** choice. **Save** applies it immediately to the extension, including open bookmark/import views, without clearing their current work. **Cancel** or closing the settings view without saving leaves the old choice. Its choice is stored for the Chrome profile and works offline, even when Anki is closed. Browser-owned extension names and shortcut descriptions follow Chrome's language; the extension's own pages and menus follow its setting.

**Automatic** follows the host language when supported and otherwise uses English. Chinese currently means Simplified Chinese (`zh-Hans`); Traditional Chinese is a separate translation. Language names always remain English, Hrvatski, and 简体中文 so that you can recover from an accidental choice. Missing translations use English. Tags, note-type/field names, saved custom preset names, document titles, and card content are not translated. New built-in schedule presets have translated display labels while their stored values remain stable.

The advanced database editor creates a timestamped checkpoint first and starts read-only until you explicitly unlock writes.

Topic review also has a secondary **✓ Done** button, available on both the question and answer side and as **Mark Topic as Done** in the reviewer's More menu. Use it when you have finished extracting what you need from a topic. Done suspends only the current Anki card and adds `topic/done` to its note. Choose a different tag under **Incremento → Settings → Topics → Done tag**; enter one tag without spaces, or leave it empty to use `topic/done`. The setting applies to future Done actions. Existing tags are preserved, and an already-present tag is not duplicated.

Anki tags belong to notes, so the Done tag is visible on every card generated from that note. Only the selected card is suspended; sibling cards, extracted cards, and child topics retain their schedules. The original content, source links, and knowledge-tree position remain intact, and no answer grade is recorded. The non-modal **Topic marked as done** notification offers **Undo**, and Anki's **Edit → Undo** also works: one undo restores the suspension and previous tags together, and Redo reapplies both. A tag that was already present before Done survives Undo. Later, the Browser's **Toggle Suspend** reactivates the card and keeps its tags; remove the Done tag separately if desired.

Reviewer controls share consistent height, rounded corners, typography, and flat styling in light and dark themes. **Postpone / Skip** retain a muted red accent, and a short divider separates **Done** from the preceding review control.

While reviewing, open **More → Review buttons** to show or hide the **Done**, **Postpone**, and **Extract** buttons independently, or use **Show review button group** to collapse or restore the group. The bar updates immediately without resetting the current card, and the choices persist across sessions. You can assign **Toggle Reviewer Buttons** a key in **Incremento → Settings → Shortcuts**; it starts without a default shortcut. The group toggle preserves each individual button choice; restore the group before changing those choices in More. The same visibility options are under **Incremento → Settings → Review → Reviewer Controls**. All three are shown by default; Done appears only on topic cards, Postpone only on eligible topic questions when topic postponement is enabled, and Extract appears on both sides. Hiding a button changes only the bar: Done remains in More, and you can turn any button back on from that submenu.

For a temporary break, use the reviewer's **More → Revisit in… → 3 months / 6 months / 12 months**, or **Choose date…**. This is a one-time manual change to the next due date, with its own Undo step. It does not answer the card, replace its custom scheduling rule, or change the topic's A-factor. Future answers use the existing topic/custom scheduling rules. The existing **Postpone** action remains the short, timed/session pause.

Revisit also keeps PDF, EPUB, video, and web topics out of automatic reading-session selection until the chosen date. Ordinary media cards remain eligible regardless of their due dates. You can still deliberately open deferred content or include it in an explicit **Review All → All available** review. To bring a deferred card back early, set its due date to today in the Browser; Undo restores both the old date and automatic-selection behavior.

Topic cards use **More / Same / Less** instead of flashcard grading. All three choices submit a neutral **Good** answer to Anki, so selecting a desired topic frequency never records an artificial FSRS Hard or Easy rating. Incremento retains the original choice in its per-profile `topic_review_history` and independently applies the topic schedule. The normal next interval is the previous precise topic interval multiplied by its A-factor. When a card has no Incremento topic history yet, its existing positive Anki interval is used as that starting interval; genuinely new cards start at one day. In the Topics settings, **More adjustment** and **Less adjustment** independently control how strongly those buttons change both the immediate interval and persistent A-factor. With the 10% defaults, **More** schedules 90% and multiplies the A-factor by 0.9, **Same** schedules the normal interval, and **Less** schedules 110% and multiplies the A-factor by 1.1. The duration shown below each button is the interval that will be applied immediately. **Maximum topic interval** is the sole cap for this algorithm. The topic schedule works in every normal and rescheduling filtered deck independently of the home deck's learning steps and maximum interval.

Item cards use Anki's native scheduler; **Fail / Pass** records **Again / Good**. To let FSRS calculate every item interval, including learning and relearning, enable FSRS in Anki and leave **Learning steps** and **Relearning steps** empty in every deck-options preset used by items. A fixed sequence such as `1d 1d 1d 1d` takes precedence while a card is learning, even with FSRS enabled. Filtered decks normally use the home preset; remove any filtered-deck learning-step override too. Keep these fields empty when creating new presets. Retention targets and trained FSRS parameters remain native Anki settings. Cards explicitly tagged as items retain item scheduling even when their home deck is named `Topics`.

If a topic card also has a custom schedule, Incremento resolves one final interval before saving anything: **Repeat exactly** and **One-time set due** replace the topic interval, while **Minimum cadence** pulls it closer only when the topic interval would be later. A one-time rule is consumed in the same database transaction. The card update is merged into Anki's single **Answer Card** undo step, and Undo/Redo also restores or reapplies the Incremento topic state and consumed one-time rule. Newer manual topic edits and newer custom-rule versions take priority during reconciliation, including an identically configured rule that you deliberately saved again. This avoids extra manual review-history rows.

The same single-step behavior applies to custom schedules on non-topic cards during review: Incremento attaches the interval override to the answer instead of creating a separate **Set Due Date** operation. A one-time rule returns when that answer is undone and is consumed again on Redo. Calendar-month rules use Anki's logical scheduler day, so reviewing after midnight but before Anki's configured rollover does not shift the due date one day early. In a filtered deck with rescheduling disabled (Anki Preview), Incremento leaves the original schedule and custom rule unchanged and records no topic/custom scheduling transition. The Browser dialog's **Apply now** command remains an explicit manual scheduling action and therefore has its own normal Anki undo entry.

Incremento does not rewrite Anki's answer revlog with unsupported SQL. Card Info therefore keeps the interval Anki originally calculated for the real Good/Hard/Easy answer, while the card's current due date and interval contain the applied override. Incremento records the requested and applied topic/custom interval in its own per-profile review history for accurate reconciliation.

Topics do not require a special deck or deck-options preset. Use the configured topic tags or enabled topic note types to identify them in any deck; the legacy `Topics` deck remains a fallback for untagged cards, and explicit item tags take precedence. Because topic interaction is a frequency preference rather than a recall test, a separate preset is still an optional way to isolate topic history during FSRS parameter optimization. It does not control Incremento's topic intervals. Reminder mode with rescheduling disabled continues to preserve both item and topic schedules.

### Card-format updates and AnkiWeb sync

Incremento does not silently update existing Anki note-type fields or card templates at startup. It first inspects the existing Incremento PDF, EPUB, audio, video, web, writing, and local-file note types without saving anything. If an update is needed, an **Incremento Card Format Update** dialog lists the affected note types and explicitly states that the collection has not yet been changed.

The dialog offers:

- **Later**: closes the dialog without changing the collection
- **Sync Before Updating**: leaves the collection untouched and opens Anki's normal sync, so you can first synchronize this device and your other devices
- **Apply Update**: enabled only after you confirm that this device contains the collection you intend to keep

After an approved note-type update, Incremento explains the required direction and opens Anki's native sync. If Anki requests a one-way sync, choose **Upload to AnkiWeb** on the device where you applied the update, then choose **Download** on the other devices. If another device has unsynchronized work, choose **Later** instead and resolve that work before applying the update.

You can reopen the same workflow manually with **Incremento → Utils → Card Format Updates…**. Creating a previously unused Incremento content type remains lazy: Incremento does not create all possible note types merely because Anki started.

`Incremento_Content_ID` from an earlier development build is tolerated as an optional hidden field, but Incremento neither adds nor removes it automatically. New installations keep this internal identity in the per-profile SQLite journal, so this implementation detail does not force an Anki full sync.

### Learning leech tags

Under **Incremento → Settings → Review → Learning leeches**, enable **Tag difficult learning cards**, choose an **Again threshold** (1–9,999; default 5), and set the **Tag** (default `learning_leech`). The feature is off until enabled.

Each card counts its own cumulative **Again** answers during initial learning, including its first answer as a new card and learning on later days. Good/Hard answers do not reset the count. Review lapses, relearning, and non-rescheduling filtered-deck Preview answers do not count. Existing learning history is included when the next learning Again is answered; saving settings does not scan or tag the collection retroactively.

At the threshold, Incremento adds the tag to the card's Anki note, so sibling cards share the visible tag but do not pool their failure counts. The card is not suspended and its schedule is unchanged. Counts survive restarting Anki because they use Anki's review history. Undo/Redo restores the answer and its newly added tag together; pre-existing tags remain untouched. The tag stays after graduation until you remove it manually. Find marked notes in the Browser with `tag:learning_leech` (or your chosen tag).

### Dependency setup

On first run, Incremento can show a dependency setup dialog.

Optional tools:

- **PyMuPDF `>=1.26,<2`** for PDF rendering, text extraction, and annotation sync
- **Tesseract OCR** for scanned/image-only PDFs
- **yt-dlp** for optional local YouTube/Vimeo downloads
- **FFmpeg** for video compression, local re-encoding, and mobile clips

The PyMuPDF install button uses a real Python interpreter matching Anki's Python
version and CPU architecture, verifies that the downloaded native package works,
and installs it in Incremento's `.dependencies/` folder. Restart Anki to activate
it. This folder is local to the installation and is excluded from add-on releases
and profile backups. If no compatible interpreter with pip is available, the
setup dialog provides the required Python version and a manual install command.

The PyMuPDF button performs an explicit, version-bounded installation after you choose it. The FFmpeg row recognizes standard system and Homebrew locations even when Anki's GUI `PATH` is limited. On macOS with Homebrew or Windows with winget, its install button runs the fixed system-package command in the background and verifies the resulting executable; Linux keeps the privileged package-manager step manual. Incremento never installs FFmpeg without an explicit click and never silently installs yt-dlp into Anki's Python environment. Tesseract remains a guided system-level installation.

### Reindex PDF text

Use this if:

- Search ALL does not find text in older PDFs
- you rebuilt or replaced PDF files
- you added cards before page-level indexing existed

Reindexing runs in the background, records progress per PDF, and can be cancelled. The manual command forces a fresh index even when the stored file signature has not changed.

### Build PDF snapshot previews on cards

Use **Incremento → Utils → Build PDF Snapshot Previews on Cards…** after changing the context-row setting or upgrading older extracted cards. The action finds notes containing Incremento PDF citations, opens the cited local page, locates the exact extracted passage, renders the configured rows before and after, highlights the passage yellow, and stores the resulting image in Anki media. It places a closed screenshot-preview control below the citation on desktop and mobile without overriding the card template's text color or weight. Rerunning it also removes the former blue styling and hover behavior from existing preview triggers. Saved highlight coordinates are preferred when available; otherwise Incremento matches the citation excerpt against the PDF's words. Unmatched passages are left unchanged and reported as skipped. Identical images reuse content-addressed media names. The work is profile-scoped, creates one Undo step for note changes, and syncs both the card HTML and media to mobile devices.

### Clean up unused images and data

Extracting a PDF passage adds its generated screenshot to Anki media before the card is saved. Discarding the card can therefore leave an unused image; ordinary image attachments can also become unused after card edits or deletions. After closing Add Cards, choose **Incremento → Utils → Clean Up Unused Data & Images…**. One preview and confirmation covers every image attachment that Anki reports as unused, orphaned PDF and video files, and stale progress, search-index, and OCR records. Images named in a saved extraction draft are protected. Incremento checks Anki's references and the draft again immediately before moving only the approved images to Anki's media trash; images used by saved notes remain untouched. You can restore media from that trash until you empty it to reclaim disk space.

### Cleanup tools

The unified cleanup action helps remove:

- files no current card references
- saved progress rows for deleted cards
- data tied to non-active profiles

This is a maintenance action, not a normal daily workflow step.

---

## 14. Keyboard Shortcuts

Incremento's configurable shortcuts can be changed in **Incremento → Settings → Shortcuts**. Leave a shortcut field empty if you want to disable that action entirely. The Browser quick-tag shortcut is fixed to `Cmd+T` / `Ctrl+T`.

### Default shortcuts

| Shortcut | Action |
|---|---|
| `Cmd+1..4` / `Ctrl+1..4` | PDF extraction into Add Card fields 1-4 |
| `Option+H` / `Alt+H` | Highlight selected PDF text |
| `Alt+P` | Set priority for current card |
| `Alt+X` | Open Extract Card dialog |
| `Cmd+T` / `Ctrl+T` | In the Browser, open nine quick tag sets for the selected notes |
| `Ctrl+K` | Open the Incremento Command Palette |
| `Cmd+F` / `Ctrl+F` | Open current-document search results for the active PDF or EPUB |
| `Ctrl+Alt+S` | Open Search ALL |
| `Ctrl+Alt+P` | Quick Open Content |
| `Option+Shift+P` / `Alt+Shift+P` | Open the visual Document Bookshelf for PDFs and EPUBs |
| `Ctrl+Alt+Left` | PDF viewer previous page |
| `Ctrl+Alt+Right` | PDF viewer next page |
| `Ctrl+Alt+-` | PDF viewer zoom out |
| `Ctrl+Alt+=` | PDF viewer zoom in |
| `Ctrl+Alt+M` | Mark current PDF as finished reading |

Many menu actions have no default shortcut but can still be assigned here, including Start Incremental Learning, Add PDF / DjVu, Add EPUB, Add Markdown Document, Edit Current Markdown Document, Add Video, Add Markdown Writing, Web Page, Add Local File, Statistics, Settings, Export, and knowledge-tree actions.

**Toggle Reviewer Buttons** also has no default key. Assign one here to collapse or restore Done, Postpone, and Extract together while reviewing; the saved individual choices return when the group is shown again.

The shortcut editor rejects duplicate non-empty Incremento shortcuts and identifies both conflicting actions. **Activity Center** has no default shortcut but can be assigned here.

### Command Palette

Press `Ctrl+K` or choose **Incremento → Command Palette…**, type part of an action name, and press Return. Matching also considers categories, keywords, and configured shortcuts. Commands that are unavailable in the current Anki view remain visible and explain why instead of silently doing nothing.

### Browser quick tags

Select one or more rows in the Browser and press `Cmd+T` on macOS or `Ctrl+T` on Windows/Linux. The picker shows up to nine distinct tag sets in a standard 3×3 block (`1/2/3` top, `4/5/6` middle, `7/8/9` bottom), so one choice can apply combinations such as `spiritual + topic`. Every slot accepts either its number or matching letter (`1/A`, `2/B`, through `9/I`), or you can click it, to apply every tag in the set immediately to every selected note. Existing sets keep their number when reused; the order changes only when the newest tagged note introduces a tag not represented in the current list. Every tag receives a persistent color chip unique within the profile, `topic` is green by default, and the same tag keeps its color across tag sets and future sessions. Use the dialog's **Settings…** button to choose a custom color for any visible tag or restore its automatic color; duplicate effective colors are rejected. If multiple selected cards belong to the same note, that note is updated only once.

In **Settings…**, enable **Use my fixed tag sets instead of recent tag sets** to define the numbered slots yourself. Each slot may contain one or several tags separated by spaces, commas, or semicolons. Fill slots consecutively from 1; fixed mode replaces automatic recent-tag discovery and never reorders the slots. Tags introduced in fixed slots are added to the same color editor, so their colors can be chosen before using the picker.

### Quick Open Content dialog shortcuts

Inside the quick-open dialog:

| Shortcut | Action |
|---|---|
| `Ctrl+F` | Open first in priority queue |
| `Ctrl+R` | Open a random visible note |
| `Ctrl+L` | Open the last opened note for the current mode |

### Document Bookshelf

The bookshelf has three panes: your lists on the left, books in the middle, and the selected book's details on the right. Drag the divider to the right of **Lists** to widen the list pane for longer names. Use **+** to create lists such as Maths, Physics, or Psychology. Choose **Edit lists** in a book's details to select any number of lists, then **Save changes**. A book can belong to several lists without duplicating its document. Right-click a list to rename or delete it; deleting a list keeps its books, saved reasons, and sources. **All books**, **Not in a list**, and **No saved reason** help you organise existing imports.

To group several documents at once, **Cmd-click** on macOS (**Ctrl-click** on Windows/Linux) to select individual documents, **Shift-click** for a range, or **Cmd/Ctrl+A** to select all documents shown. Choose **Add selected to list…** above the books, or right-click the selection and choose the same action, then pick a list. Grouping runs in the background and keeps the documents' other lists, reasons, and sources. Your selection remains highlighted while the documents match the current filters. Unsaved notes remain drafts until you save them; select one document to edit its notes or open its reader. Bulk grouping works in both bookshelf views for PDFs, EPUBs, and webpages saved as PDFs.

For one book, **Edit lists** opens a larger, resizable picker. Search the categories on the left and tick as many as you need; results update as you type. Click **Search** or press **Enter** in the search field to run the search without confirming your choices. The **Selected lists** pane on the right keeps all your choices visible even when the search hides them. Select entries in that pane and choose **Remove selected** to remove memberships. **New list…** creates and selects another category. Choose **OK** to update the draft, then **Save changes** in the bookshelf or finish the import; **Cancel** keeps the previous memberships. The book's compact summary shows up to three list names plus a count; reopen the picker to review every membership. This picker is shared by the bookshelf and PDF, EPUB, and webpage-to-PDF imports.

Record **Why I saved this book** and **Where I found it (optional)** in the details pane. The source can be a person, website, ChatGPT conversation, or plain-text link. These notes belong to the document, so cards using the same stored file share them. Search matches titles, reasons, and sources, and works together with the format, list, and tag filters. Switch between **Covers** and **Reason-first list** to browse visually or read the saved reasons. Unsaved edits stay available while you select other books; closing or opening a reader asks whether to save, discard, or cancel when edits remain.

**+ Add PDF** and **+ Add EPUB** open the normal import dialogs and refresh the shelf afterwards. In either import dialog, select a file to enter its optional lists, reason, and source. Each file keeps its own draft when you switch selections, including in batch and folder imports. Imported details are committed with the import and recovered after an interrupted import. Lists and notes stay in the current profile's Incremento database and backups; they are separate from Anki tags and do not alter note types.

**Webpage to PDF** includes the same **Edit lists**, reason, and source controls. Group articles by theme in one or more existing lists, or create a list before importing. These details stay with the resulting PDF, including when verification in your Companion browser or **Use browser-saved PDF…** is needed. You can edit them later in the Document Bookshelf.

The **Sort by**, **Reverse order**, and **Shuffle again** controls are always visible above the books, without opening **More filters**. Sorting offers title, priority, due linked-card count, completed-review count, annotation count, and random order. Use **Reverse order** for the opposite direction or **Shuffle again** to browse a fresh random arrangement. Filtering preserves the current random arrangement. Counts load on demand in the background; the selected count appears on each tile. Reopening the shelf refreshes these counts.

In **Covers**, each cover keeps its full aspect ratio. Titles, list labels, saved reasons, and sort counts appear in a separate caption area beneath the image, with a clear gap.

The Document Bookshelf is optimized for visual recognition across PDFs and EPUBs. Choose **All documents**, **PDFs**, or **EPUBs**, type in the search box to filter titles, and use the tag autocomplete or **Browse tags** with **OR/AND** matching to narrow the shelf without remembering exact spelling. **Possible duplicates only** can be combined with those filters and uses cached rare-word plus trigram similarity across document titles, original filenames, and embedded PDF metadata titles. The profile-captured metadata scan runs off the UI thread and ignores generic titles. Duplicate mode also caches per-document attachment counts and overlays a green top-right check on covers with live Topic or Item attachments; the hover text gives the count. The badge is informational and does not affect matching. Right-click any book and choose **Show in Finder** (macOS), **Show in File Explorer** (Windows), or **Show containing folder** (Linux) to locate its stored PDF or EPUB file. The action is disabled if the file is unavailable. The same menu lets you delete a candidate or keep it and delete its directly matching candidates. A separate background collection query recounts distinct live attached cards before confirmation; attached cards are not deleted, and the warning explains that their document links may stop working. A failed or stale attachment check cancels deletion. The confirmation also explains that the document's Anki note/card is deleted while the managed source stays available for Undo. Single-click a cover to select it and edit its details. Double-click, press Return with the book list focused, or choose **Open book** to read it. Opening a PDF restores its saved page, zoom, and appearance state unless Settings force another appearance; opening an EPUB restores its saved section and scroll position. Thumbnails load progressively, and missing PDF previews render one at a time, so opening a large library does not synchronously render every document. **Don't change cards attached to PDF reading history** is enabled only for a selected PDF. **Open the card also to study** works for either format and starts the selected document card after opening its reader. If an older profile customized the former PDF Bookshelf shortcut, Incremento carries that shortcut into Document Bookshelf automatically. If `Option/Alt+Shift+P` was also assigned to Quick Open Content, the Bookshelf keeps that key; Quick Open Content remains available from the Incremento menu and can be given a different shortcut in Settings.

---

## 15. Common Workflows

### Workflow A: Classic incremental reading from PDFs

1. Add a PDF with **Incremento → Add Content → Add PDF / DjVu**.
2. Start a session with some topic share.
3. Read in the PDF dock.
4. Use `Ctrl/Cmd+1..4` to extract key text into new cards.
5. Use highlights to mark processed passages.
6. Resume later exactly where you left off.

### Workflow B: Turn articles into durable reading material

1. Open an online article.
2. Use **Incremento → Add Content → Webpage to PDF**.
3. Review it like a normal PDF card.
4. Highlight and extract passages as you read.

### Workflow C: Learn from videos

1. Add a YouTube, Vimeo, or local video with **Add Video**.
2. Review the video card.
3. Pause at key moments and use **Add Card at this point** for a timestamp link, or **Create Mobile Clip…** for a trimmed segment that syncs through Anki media.
4. Finish and add the extracted card, then let Anki sync its media for mobile playback.
5. Resume the source video later from its saved timestamp.

### Workflow D: Incremental web reading

1. Add a site or document as **Web Page**.
2. Browse it inside the web dock while reviewing.
3. Select useful text and transfer it into the Add Card dock.
4. Return later to the last visited URL, not just the original home page.

### Workflow E: Writing-first study

1. Create a writing card with **Incremento → Add Content → Add Markdown Writing…**.
2. Draft notes in markdown while reviewing the card.
3. Let Incremento autosave continuously.
4. Select passages from your writing and turn them into review cards.

### Workflow F: Balanced multi-subject study

1. Tag cards by subject.
2. Add tag quotas in the scheduler.
3. Use **Today** scope to preserve balance across multiple sessions.
4. Check **Statistics** to verify both counts and time are balanced.


## 16. Large libraries and responsive tools

Session counts and PDF-target lists update in the background after a brief typing pause. PDF/EPUB Find and Current Document Search show the newest query; closing a dialog or changing profiles discards old results. Searches have text and time budgets: if a request exceeds a budget, narrow the query and try again. Cancellation preserves already committed document indexes.

**Incremento Database Entries** is read-only and loads one page at a time. Use **Previous** and **Next** to reach the rest of a large selection. A page contains at most 500 selected cards, 2,000 matching database rows and 2 MiB of displayed data; very long individual values are shortened to 4,096 characters with an ellipsis. Closing the dialog cancels loading. Search and match navigation apply to the displayed page.

Document Bookshelf loads covers for the visible rows and a small nearby margin. Scroll to load later covers; offscreen covers may be released and loaded again. PDF highlight lists display 50 entries per page, with Previous/Next controls. Highlight selection and actions remain available on later pages.

The writing preview updates after a short pause and does no markdown parsing while hidden. Autosaves run in order in the background; closing, switching writing cards or restoring a backup waits for the latest save. If a save fails, the editor keeps its live text and reports the failure rather than claiming it was saved. Cursor/scroll progress and the chosen word-count mode are preserved.

Companion bookmark folders mount their children when expanded. Long folder and import lists display 100 entries per page. Folder selection totals include every descendant, including later pages, and importing includes all selected entries. Use Previous/Next to reach the remaining entries.
