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

### Install from AnkiWeb (recommended)

Incremento is available from [AnkiWeb Add-ons](https://ankiweb.net/shared/info/1013949798).

1. In Anki, open **Tools → Add-ons → Get Add-ons…**.
2. Enter the add-on code **`1013949798`**.
3. Restart Anki after installation.

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

### Main actions

| Menu item | What it does |
|---|---|
| **Start Incremental Learning** | Build a new Incremento session |
| **Settings** | Configure extraction, review, topic, writing, shortcut, and advanced options |
| **About** | Show a summary of addon capabilities |
| **Add Content → Add PDF** | Import a PDF as a topic card |
| **Add Content → Add EPUB** | Import one or more EPUBs as topic cards |
| **Add Content → Webpage to PDF** | Render a webpage into a PDF card |
| **Add Content → Add Video** | Add a YouTube, Vimeo, or local video card |
| **Add Content → Add to Markdown** | Create a writing card backed by a markdown file |
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
| **Export Full Backup** | Create a backup ZIP |

### Utils submenu

| Menu item | What it does |
|---|---|
| **Check Dependencies...** | Check/install optional PDF tools |
| **Reindex PDF Text (Existing Cards)** | Rebuild searchable PDF text index |
| **Import Notebook Citations to PDF Highlights…** | Import supported notebook citations as PDF highlights |
| **OCR Image Text (Existing Cards)…** | Extract searchable text from image-based cards |
| **Reindex OCR Search Cache (From Hidden Field)** | Rebuild cached OCR search text |
| **Clean Non-Active Profile Data...** | Remove orphaned data not tied to live cards |
| **Clean Up Orphaned PDF Files...** | Delete unreferenced PDF files |
| **Clean Up Orphaned Video Files...** | Delete unreferenced video files |
| **Clean Up Stale Progress / Search Index / OCR Rows…** | Remove stale runtime rows for deleted cards |

---

## 3. Starting a Study Session

1. Open Anki.
2. Choose **Incremento → Start Incremental Learning**.
3. Adjust the scheduler settings or accept the defaults.
4. Incremento builds the **Incremento Session** filtered deck and opens the reviewer.

If you leave before finishing, Anki keeps the unfinished cards in **Incremento Session** so you can open that deck and continue later. Completed cards return to their original decks automatically. Incremento leaves this live queue untouched while exiting, so returning to the deck list does not trigger another potentially slow deck rebuild.

The session dialog also supports:

- named presets that you can save, load, rename, and delete
- optional live preview before starting
- branch-scoped study when launched from the knowledge tree

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

Controls what share of the session goes to topics versus normal review cards.

- Move left for more topics
- Move right for more items

Incremento also shows the current number of ready topic and item cards.

The 0% and 100% endpoints are exact: a bucket set to 0% is disabled and is not reintroduced by scheduler smoothing.

### Docs <-> Other balance

Controls how often PDF and EPUB reading cards are woven into normal scheduling.

- Move left for more Docs
- Move fully right for 0% Docs

Document cards are eligible regardless of New/Learning/Due state. Separate content-type priorities can still reserve a hard document quota in strict mode.

### Priority <-> Random balance

Controls how cards are selected within each bucket.

- **Priority** favors more urgent cards
- **Random** samples more freely from eligible cards

### Scheduler scope

The balancing memory can apply to:

- **This session**
- **Today**
- **All time**

If you use **Today**, the **Day ends at** setting lets you define a late-night cutoff like `04:00`.

### Scheduling priority order

With **Strict enforcement** enabled, Incremento fills quotas in the order you choose:

- **Tags**
- **Type**
- **Mode**

This is useful when you need exact tag coverage or strict topic/item ratios.

### Tag quotas

You can allocate part of each session to specific tags:

1. Add one or more tags.
2. Set each tag percentage.
3. Lock any tag whose share should stay fixed.
4. Use **After exhausting tag groups, fill with rest of cards** if you want leftover slots topped up automatically.

By default, document and media picks also respect active tag rows. For example, if your session only has `data` and `statistics` tag quotas, PDF, EPUB, video, and webpage picks must match those tags instead of falling back to unrelated content.

### Filters

These are standard Anki search filters:

- **Topics filter**: what counts as a topic card
- **Items filter**: what counts as an item card

Both fields are blank by default. Incremento first classifies cards with its configured topic note types/tags, item tags, and Topics deck behavior; an optional filter here narrows the corresponding classified pool further.

Use the **Test** buttons to see how many cards currently match.

### Advanced session options

Open **Advanced** in the session dialog for a few session-behavior controls:

- **Present cards in scheduler order**: shows cards in the exact order selected by the scheduler instead of randomizing them.
- **Auto-refill session deck to keep this many unreviewed cards**: keeps the active **Incremento Session** deck topped up to your **Cards per session** count of not-yet-answered cards as you study. Learning repeats stay in the filtered deck, so the visible Anki queue can temporarily exceed this number.
- **Allow document/media picks outside selected tags**: restores the older fallback behavior where a PDF, EPUB, video, or webpage tag miss can be filled from any card of that content type. Leave this off when tag quotas should be strict.

### Debug mode

**Show debug information** displays the exact selected cards before the session starts.

### Statistics history buttons

The dialog also has buttons to delete session, daily, and lifetime statistics or export them as JSON.

---

## 5. Adding Content Cards

Incremento now supports several kinds of topic material.

### Add PDF

Use **Incremento → Add Content → Add PDF** to import a PDF file into Incremento.

This creates an **Incremento PDF** note and copies the PDF into `user_files/<ProfileName>/pdfs/`.

### Add EPUB

Use **Incremento → Add Content → Add EPUB** to import one or more EPUB books.

Incremento stores the source EPUB under `user_files/<ProfileName>/epubs/` and extracts readable section data under `user_files/<ProfileName>/epub_extracted/` for the reader and search features.

### Webpage to PDF

Use **Incremento → Add Content → Webpage to PDF** when you want a normal PDF-style reading workflow for an online article.

Incremento loads the page in a hidden browser view, renders it to PDF, and imports the result as a PDF card.

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

### Add to Markdown

Use **Incremento → Add Content → Add to Markdown** to create an **Incremento Writing** note backed by a markdown file under `user_files/<ProfileName>/writing/`.

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

If you install the optional companion extension in Chrome/Brave, it can send the current page to Incremento as:

- a PDF
- a video
- a web page card
- a writing card

It can also sync watched YouTube/Vimeo time back into Incremento video cards.

---

## 6. PDF and EPUB Cards

PDF cards remain the most feature-rich workflow in Incremento.

### What a PDF card stores

Each PDF note includes:

- **Title**
- **PDF_Filename**
- **Content** for searchable extracted PDF text

### PDF viewer basics

When a PDF card is reviewed, the PDF dock opens on the right.

Main controls include:

- previous / next page
- zoom out / zoom in
- highlight color selection
- **Add Card**
- **Highlight when extracting**
- **Mark this PDF as finished reading**

Incremento remembers:

- current page
- zoom level
- finished/read state used by the scheduler

### Extracting text to cards

1. Select text in the PDF viewer.
2. Press `Cmd+1..4` on macOS or `Ctrl+1..4` on Windows/Linux.
3. The selected text is inserted into the matching field in the Add Card dock.
4. Incremento appends a clickable citation link to the PDF page.

If the target field already contains text, the new excerpt is appended rather than replacing the old content.

PDF highlights can also be turned into cards from the **Highlights** panel. Incremento prefills the configured Add Card field, includes a citation that points back to the exact highlight when possible, and switches to **Preview Card** after that highlight already has a linked note.

### Highlights

You can highlight text in the current color with:

- `Option+H` on macOS
- `Alt+H` on Windows/Linux

Highlights are saved per PDF and reappear whenever you reopen the card.

### Cross-references

Citations added from PDF extraction link back to the exact PDF page. Highlight-created cards also try to reopen and scroll to the exact cited highlight before falling back to page/excerpt matching.

### Searchable PDF text

Incremento stores searchable PDF content in two ways:

- the note's `Content` field for normal Anki browser search
- a page-level PDF text index used by **Search ALL**

If old cards are missing page-level search results, run **Incremento → Utils → Reindex PDF Text (Existing Cards)**.

### EPUB cards and reader

EPUB cards use a dedicated reader dock instead of the PDF viewer.

Current EPUB features include:

- saved reading position and reopen-at-last-section behavior
- bookmarks within the book
- highlights and highlight notes
- per-book daily reading limits
- optional prompts to review due extracted cards near the current reading point
- searchable extracted section text used by **Search ALL**

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

- current time display
- seek bar
- **Add Card at this point**
- **Open in Browser**

For local playback, extra controls appear:

- play / pause
- skip back 10s
- skip forward 10s
- playback speed
- volume

### Creating cards from videos

Use **Add Card at this point** to create a new card tied to the current video moment. This is useful for note-taking and timestamp-based review prompts.

### Browser sync

If you use the companion browser extension, watched YouTube/Vimeo time can be pushed back into Incremento video cards automatically.

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
- persistent cookies/session storage under `user_files/<ProfileName>/web_profile/`

This works well for long-form websites, documentation, and pages that you want to revisit in-place inside Anki.

Selected text from the web dock can be transferred into the Add Card dock.

When a bookmark is saved, Incremento reopens that web card at the bookmarked point and highlights it. If no bookmark is saved, the web card can restore the last scroll position when the browser-card scroll setting is enabled.

If a page does not behave properly inside Anki's built-in web view, use **Open in Window** to open the current page externally. When **Track via Chrome extension** is checked, the companion extension keeps syncing the same web card to the latest page visited in that browser tab.

In **Incremento → Settings → Review**, you can also choose whether web-card media should try to resume in the original page first and whether browser-card scroll should be remembered by default.

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

### Local file cards

Local file cards open a small dock that shows the linked file name, path, storage mode, and note text.

From the dock you can:

- reveal the file in Finder/Explorer
- open it in the default native app
- relink the card if the original file moved

Managed-copy local files live under `user_files/<ProfileName>/files/`. Referenced local files keep pointing at the original path outside Incremento.

---

## 9. Search and Navigation Tools

### Search ALL

Choose **Incremento → Search ALL** or use its shortcut.

It searches across:

- PDF highlights and sources
- EPUB highlights and sources
- PDF file content
- EPUB file content
- cards

Search results include a preview panel. PDF hits can open directly to the matching page, and card hits can open in the Anki Browser.

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

---

## 10. Statistics and Focus Timer

### Statistics

Open **Statistics** to view study history.

Scopes:

- **This Session**
- **Today**
- **All Time**

Current statistics include both count-based and time-based views:

- card types
- selection mode
- tags
- review time by card type
- review time by tag

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

---

## 11. Priorities, Extraction, and the Add Card Dock

### Per-card priority

Press `Alt+P` to open the priority dialog for the current review card.

Priority scale:

- `0` = highest importance
- `50` = default
- `100` = lowest importance

For topic cards, the dialog can also expose **A-Factor**, which adjusts the topic's interval behavior.

### Extract Card from the current reviewer card

Press `Alt+X` to open the **Extract Card** dialog.

This is separate from PDF field-filling. It lets you:

- take the currently selected reviewer text
- choose any note type
- choose any deck
- create a new note directly

Settings can control:

- the default extract note type
- fallback extract priority
- how strongly source priority influences new extracts
- whether extracts start as topics
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

The settings dialog also lets you choose the tags applied by the dock's **Topic** and **Item** buttons.

---

## 12. Export and Restore Notes

Use **Export Full Backup** to create a single ZIP for migration to a new computer.

The backup includes:

- `anki/all_decks.apkg` for the currently open Anki profile
- the full `user_files/` tree, including all per-profile runtime folders
- `config.json`
- `manifest.json`
- JSON copies of priorities, PDF progress, highlights, and stats
- `restore.txt` with the restore order

For full restore guidance, see `EXPORTING.md`.

---

## 13. Settings, Utilities, and Dependencies

### Settings dialog

Choose **Incremento → Settings** to open six tabs:

- **Extraction**: default extract note type, extract priority behavior, PDF highlight card target field, topic/tag defaults, and saved provenance link types
- **Review**: priority direction, post-answer prompt behavior, browser/PDF/web reviewer defaults, item skip, focus-timer auto-start, and custom scheduling presets
- **Topics**: which card types/tags count as topics, the default topic A-factor, More/Less strength, the maximum topic interval, Add Card topic/item tags, whether Incremento auto-creates the `Topics` deck, which profiles that applies to, and the red Postpone button behavior
- **Writing**: editor defaults, automatic backup intervals, progress visibility, default progress scope, and word-count mode
- **Shortcuts**: assign or clear shortcuts for Incremento actions
- **Advanced**: open the guarded profile database inspector

The advanced database editor creates a timestamped checkpoint first and starts read-only until you explicitly unlock writes.

Topic cards use **More / Same / Less** instead of flashcard grading. All three choices submit a neutral **Good** answer to Anki, so selecting a desired topic frequency never records an artificial FSRS Hard or Easy rating. Incremento retains the original choice in its per-profile `topic_review_history` and independently applies the topic schedule. The normal next interval is the previous precise topic interval multiplied by its A-factor. When a card has no Incremento topic history yet, its existing positive Anki interval is used as that starting interval; genuinely new cards start at one day. In the Topics settings, **More adjustment** and **Less adjustment** independently control how strongly those buttons change both the immediate interval and persistent A-factor. With the 10% defaults, **More** schedules 90% and multiplies the A-factor by 0.9, **Same** schedules the normal interval, and **Less** schedules 110% and multiplies the A-factor by 1.1. The duration shown below each button is the interval that will be applied immediately. **Maximum topic interval** provides a hard cap, while Anki's deck-preset maximum interval remains an additional cap; the lower value wins.

If a topic card also has a custom schedule, Incremento resolves one final interval before saving anything: **Repeat exactly** and **One-time set due** replace the topic interval, while **Minimum cadence** pulls it closer only when the topic interval would be later. A one-time rule is consumed in the same database transaction. The card update is merged into Anki's single **Answer Card** undo step, and Undo/Redo also restores or reapplies the Incremento topic state and consumed one-time rule. Newer manual topic edits and newer custom-rule versions take priority during reconciliation, including an identically configured rule that you deliberately saved again. This avoids extra manual review-history rows.

The same single-step behavior applies to custom schedules on non-topic cards during review: Incremento attaches the interval override to the answer instead of creating a separate **Set Due Date** operation. A one-time rule returns when that answer is undone and is consumed again on Redo. Calendar-month rules use Anki's logical scheduler day, so reviewing after midnight but before Anki's configured rollover does not shift the due date one day early. In a filtered deck with rescheduling disabled (Anki Preview), Incremento leaves the original schedule and custom rule unchanged and records no topic/custom scheduling transition. The Browser dialog's **Apply now** command remains an explicit manual scheduling action and therefore has its own normal Anki undo entry.

Incremento does not rewrite Anki's answer revlog with unsupported SQL. Card Info therefore keeps the interval Anki originally calculated for the real Good/Hard/Easy answer, while the card's current due date and interval contain the applied override. Incremento records the requested and applied topic/custom interval in its own per-profile review history for accurate reconciliation.

Because topic interaction is a frequency preference rather than a recall test, consider assigning topic decks their own Anki deck-options preset. This keeps topic review history out of the FSRS parameter set used by ordinary item cards.

### Dependency setup

On first run, Incremento can show a dependency setup dialog.

Optional tools:

- **PyMuPDF** for stronger PDF rendering and text extraction
- **Tesseract OCR** for scanned/image-only PDFs

PyMuPDF can be installed automatically from inside Anki. Tesseract must be installed at the system level.

### Reindex PDF text

Use this if:

- Search ALL does not find text in older PDFs
- you rebuilt or replaced PDF files
- you added cards before page-level indexing existed

### Cleanup tools

The cleanup utilities help remove:

- files no current card references
- saved progress rows for deleted cards
- data tied to non-active profiles

These are maintenance tools, not normal daily workflow tools.

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
| `Cmd+F` / `Ctrl+F` | Open current-document search results for the active PDF or EPUB |
| `Ctrl+Alt+S` | Open Search ALL |
| `Ctrl+Alt+P` | Quick Open Content |
| `Ctrl+Alt+Left` | PDF viewer previous page |
| `Ctrl+Alt+Right` | PDF viewer next page |
| `Ctrl+Alt+-` | PDF viewer zoom out |
| `Ctrl+Alt+=` | PDF viewer zoom in |
| `Ctrl+Alt+M` | Mark current PDF as finished reading |

Many menu actions have no default shortcut but can still be assigned here, including Start Incremental Learning, Add PDF, Add EPUB, Add Video, Add to Markdown, Web Page, Add Local File, Statistics, Settings, Export, and knowledge-tree actions.

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

---

## 15. Common Workflows

### Workflow A: Classic incremental reading from PDFs

1. Add a PDF with **Incremento → Add Content → Add PDF**.
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
3. Pause at key moments and use **Add Card at this point**.
4. Resume later from the saved timestamp.

### Workflow D: Incremental web reading

1. Add a site or document as **Web Page**.
2. Browse it inside the web dock while reviewing.
3. Select useful text and transfer it into the Add Card dock.
4. Return later to the last visited URL, not just the original home page.

### Workflow E: Writing-first study

1. Create a writing card with **Incremento → Add Content → Add to Markdown**.
2. Draft notes in markdown while reviewing the card.
3. Let Incremento autosave continuously.
4. Select passages from your writing and turn them into review cards.

### Workflow F: Balanced multi-subject study

1. Tag cards by subject.
2. Add tag quotas in the scheduler.
3. Use **Today** scope to preserve balance across multiple sessions.
4. Check **Statistics** to verify both counts and time are balanced.
