# Incremento — User Manual

Incremento is an Anki addon for **incremental reading and learning**. It schedules a balanced mix of topic cards (concept notes, articles, PDFs) and item cards (flashcards, Q&A), lets you read and annotate PDFs directly inside Anki, and tracks your study statistics over time.

---

## Table of Contents

1. [Core Concepts](#1-core-concepts)
2. [Starting a Study Session](#2-starting-a-study-session)
3. [Scheduler Settings — Reference](#3-scheduler-settings--reference)
4. [Adding a PDF Card](#4-adding-a-pdf-card)
5. [The PDF Viewer](#5-the-pdf-viewer)
6. [Extracting Text to Cards (Ctrl+1–4)](#6-extracting-text-to-cards-ctrl14)
7. [Highlighting](#7-highlighting)
8. [Cross-References — Linking to a PDF Page](#8-cross-references--linking-to-a-pdf-page)
9. [Searching for PDF Content in the Card Browser](#9-searching-for-pdf-content-in-the-card-browser)
10. [Viewing Statistics](#10-viewing-statistics)
11. [Exporting Your Data (Backup)](#11-exporting-your-data-backup)
12. [Keyboard Shortcuts Reference](#12-keyboard-shortcuts-reference)
13. [Common Workflows](#13-common-workflows)

---

## 1. Core Concepts

### Topics vs Items

Incremento distinguishes two types of cards:

| Type | What it is | Example |
|------|-----------|---------|
| **Topics** | Long-form reading, concept notes, PDFs | A note about neural networks; a PDF chapter |
| **Items** | Fact cards, flashcards, Q&A | "What is the capital of France? → Paris" |

By default, cards in the `Topics` deck are treated as topics, and everything else as items. You can customise this with filters (see §3).

### Incremental Learning

Rather than studying everything at once, Incremento selects a balanced session for you — mixing new topics to read with items to review. The scheduler tracks what you have already studied and ensures you make progress across all areas without over-studying one thing.

### Filtered Deck

When you start a session, Incremento creates a temporary Anki filtered deck called **Incremento Session** containing exactly the cards it selected. After reviewing, cards return to their original decks with normal scheduling intact.

---

## 2. Starting a Study Session

1. Open Anki.
2. Go to **Tools → Start Incremental Learning**.
3. The **Scheduler Settings** dialog opens. Adjust your settings (see §3) or just click **OK** with the defaults.
4. Anki opens the **Incremento Session** filtered deck and the reviewer starts.

> **First time?** The defaults work well: 50 cards per session, 10% topics / 90% items, 99% random mode. Just click OK.

---

## 3. Scheduler Settings — Reference

### Cards Per Session

How many cards to put in the session. Default: **50**.

> **Example:** If you have 200 due items and set this to 30, Incremento picks 30 cards according to your balance settings.

---

### Card Types to Include

Three checkboxes control which card states are eligible:

| Checkbox | Includes |
|----------|---------|
| **New** | Cards you have never studied |
| **Learning** | Cards still in learning steps |
| **Due / Review** | Cards past their review date |

All three are checked by default. Uncheck **New** if you only want to review existing cards, or uncheck **Due / Review** to focus only on new material.

---

### Topics ↔ Items Balance

A slider from 0 to 100 controlling what fraction of your session is topic cards vs item cards.

- Slide **left** → more topics (reading, notes, PDFs)
- Slide **right** → more items (flashcards, Q&A)
- Default: **10% topics / 90% items**

A live count shows how many cards of each type are currently available: `Topics: 12 ready  Items: 84 ready`.

> **Example:** You are reading a long PDF book and want to spend half your session reading and half reviewing vocabulary. Set the slider to 50%.

---

### Priority ↔ Random Balance

Controls how cards are selected within each type:

- **Priority** — picks the most overdue / highest-urgency cards first
- **Random** — picks randomly from all eligible cards

Default: **99% random / 1% priority**. For spaced repetition purists, slide towards priority.

> **Example:** You have an exam tomorrow and want to see your most overdue cards. Set this to 100% priority.

---

### Scheduler Scope

Determines the time window the scheduler uses when balancing topics vs items and tag quotas:

| Scope | Behaviour |
|-------|-----------|
| **This session** | Resets every time you open the dialog. Good for one-off sessions. |
| **Today** | Remembers picks across multiple same-day sessions. Good if you study in short bursts. |
| **All time** | Balances over your entire history. Good for long-term even coverage. |

**Day ends at** (visible when scope is Today) — sets the logical day boundary. If you study past midnight, set this to e.g. `04:00` so late-night sessions still count as "today".

---

### Scheduling Priority Order

Controls the order in which the scheduler enforces its quotas when **Strict enforcement** is on.

Three dropdowns let you put any of the three dimensions first:

- **Tags** — fill tag quotas first (e.g. "give Biology 30% before anything else")
- **Type** — fill the topics/items balance first
- **Mode** — fill the priority/random balance first

Default order: **Tags → Type → Mode**.

**Strict enforcement** (checkbox):
- **Checked (default)** — each quota is filled completely before moving to the next. Hard guarantees.
- **Unchecked** — soft debt-based scheduling; all dimensions are interleaved. More natural-feeling.

> **Example:** You have tags for Biology, Chemistry, and Physics and want strict 30/30/30 coverage. Set scope to Today, add tag quotas of 30% each, and keep strict enforcement on.

---

### Tag Quotas

Add tags to give them a dedicated share of the session.

1. Choose a tag from the dropdown and click **Add**.
2. Use the per-tag slider to set its percentage (e.g. 25%).
3. Use the **🔒 lock** checkbox to fix a tag's percentage so other sliders don't affect it.
4. The **Other cards** label shows the remaining percentage for untagged cards.

**After exhausting tag groups, fill with rest of cards** — if checked, any remaining slots after all tag quotas are filled are topped up with any available card. Uncheck if you want strict tag-only sessions.

> **Example:** You study three subjects. Add `Biology`, `Chemistry`, `Physics` as tag rows, set each to 33%, and lock them all. Every session will be exactly one-third each subject.

---

### Advanced: Filters

- **Topics filter** (default: `deck:Topics`) — Anki search query that defines what counts as a topic card. You can use any valid Anki search like `tag:reading` or `deck:Articles`.
- **Items filter** (default: `-deck:Topics`) — defines item cards. The `-` prefix means "not in Topics deck".

Click **Test** next to either filter to see how many cards currently match it.

> **Example:** You organise topics by tag rather than deck. Set Topics filter to `tag:topic` and Items filter to `-tag:topic`.

---

### Debug Mode

Check **Show debug information** to see the exact list of cards Incremento selected before the session starts. Useful for understanding the scheduler's choices.

---

### Statistics History Buttons

At the bottom of the dialog:

| Button | Effect |
|--------|--------|
| **Delete Today** | Removes today's statistics |
| **Delete Session** | Clears last session's in-memory stats |
| **Delete All Time** | Removes lifetime statistics |
| **Delete All History** | Removes all statistics (irreversible) |
| **Export JSON** | Saves all statistics to a JSON file |

---

## 4. Adding a PDF Card

Any PDF can become a topic card in Anki. Incremento stores the PDF in your Anki media folder and creates a card that shows the PDF in a sidebar dock while you review.

### Steps

1. Go to **Tools → Add PDF to Topics**.
2. Click **Browse** and choose a PDF file.
3. Enter a **Title** (auto-filled from the filename — edit it if you want).
4. Click **OK**. The card is added to your `Topics` deck.

### What gets created

A note with three fields:
- **Title** — the name you entered
- **PDF_Filename** — the media filename (internal)
- **Content** — full extracted text from the PDF (used for search; not shown on the card face)

The card face shows the title and a note saying the PDF is open in the sidebar.

> **Example:** You have a research paper `attention_is_all_you_need.pdf`. Add it via the menu, title it "Transformer Architecture Paper", and it appears in your Topics deck ready for incremental reading.

---

## 5. The PDF Viewer

When you review a PDF card, the **PDF Viewer dock** opens automatically on the right side of Anki's main window. It stays open between cards.

### Controls

```
← Prev   Page 3 / 42   Next →   −  75%  +   🟡🟢🔵🩷   + Add Card   ☐ Highlight when extracting
```

| Control | Action |
|---------|--------|
| **← Prev / Next →** | Navigate pages |
| **Page N / M** | Current page and total pages |
| **− / +** | Zoom out / in (25%–400%) |
| **Colour buttons** | Select highlight colour (yellow, green, blue, pink) |
| **+ Add Card** | Open the Add Card panel |
| **Highlight when extracting** | If checked, auto-highlight text when using Ctrl+1–4 |

### Page & Zoom Memory

Incremento automatically saves your **page number** and **zoom level** for each PDF card. When you return to a card later, the viewer reopens exactly where you left off.

### Text Selection

Click and drag over any text in the PDF to select it. The text layer is fully selectable — you can copy text normally with Cmd/Ctrl+C.

---

## 6. Extracting Text to Cards (Ctrl+1–4)

This is the core workflow for building new cards while reading a PDF.

### How it works

1. While reviewing a PDF card, select text in the PDF viewer.
2. Press **Cmd+1** (Mac) or **Ctrl+1** (Windows/Linux).
3. The **Add Card** panel opens on the left side of Anki.
4. The selected text is pasted into **Field 1** of the new card.
5. A citation link is automatically appended below the text.

Use **Cmd+2 / 3 / 4** to fill Fields 2, 3, 4 respectively.

### The Citation Link

Every extraction appends a clickable link in this format:

```
Page 4. of attention_is_all_you_need
```

Clicking this link while reviewing **any** card opens the PDF viewer at exactly that page. This creates a permanent cross-reference between your new card and its source.

> **Use case:** You create a flashcard "What is multi-head attention?" with the answer extracted from page 4 of the paper. The citation link at the bottom is a clickable reference. Months later, when you review the flashcard and want context, one click takes you back to that exact page.

### Appending vs Overwriting

If a field already has content, the new text is **appended** with a blank line — it never overwrites. This lets you build up a field from multiple extractions.

> **Example:**
> - Press Ctrl+1 on "Attention is a mechanism that..."
> - Press Ctrl+1 again on "Multi-head attention allows..."
> - Field 1 now contains both excerpts separated by a blank line, each with its own citation.

### Auto-Highlight

Check **"Highlight when extracting"** in the viewer controls. Now every time you press Ctrl+1–4, the selected text is also highlighted in the PDF in the currently selected colour. This gives you a visual record of what you have already extracted.

---

## 7. Highlighting

Highlights are saved permanently to each PDF card and reappear every time you open that card.

### Creating a Highlight

1. Select text in the PDF viewer.
2. Press **Option+H** (Mac) or **Alt+H** (Windows/Linux).
3. The text is highlighted in the currently selected colour.

### Choosing a Colour

Click one of the four colour buttons in the controls bar. The active colour has a white border:

- 🟡 **Yellow** — general highlights
- 🟢 **Green** — important concepts
- 🔵 **Blue** — definitions / terms
- 🩷 **Pink** — questions / uncertainties

### Deleting a Highlight

Each highlight has a small **×** button in its top-right corner. Click it to remove the highlight.

### Auto-Highlight on Extract

Enable the **"Highlight when extracting"** checkbox. Now Ctrl+1–4 highlights the selection in the current colour automatically, so your extraction and annotation happen in one step.

> **Use case:** You are reading a chapter on machine learning. You highlight key definitions in blue, important formulas in yellow, and things you don't understand in pink. When you return to the chapter next week, your annotations are all there.

---

## 8. Cross-References — Linking to a PDF Page

### Creating a link

Every time you use Ctrl+1–4 to extract text, a citation link is added automatically:

```
Page 4. of transformer-paper
```

This is an HTML hyperlink stored in the card field.

### Following a link

Click the blue citation text while reviewing **any card** in Anki (not just PDF cards). The PDF dock opens showing the exact page referenced.

**Importantly:** following a link does **not** change the reading position of the original PDF card. If you were on page 10, navigate around via the link, your next review of the PDF card still resumes at page 10.

> **Use case — study notes:**
> You create a "Machine Learning Concepts" note type with a `Source` field. Every time you read a relevant part of a paper, you Ctrl+1 the text and the citation appears in the Source field. Your notes are now hyperlinked back to their original sources.

> **Use case — Cloze cards:**
> You extract a key sentence into a cloze card. The citation at the bottom gives you one-click access to the full context paragraph whenever you want to check your understanding.

---

## 9. Searching for PDF Content in the Card Browser

When you add a PDF card, Incremento extracts all text from the PDF and stores it in a hidden **Content** field. This makes the full text of every PDF searchable in Anki's card browser.

### How to search

1. Open the **Card Browser** (B in Anki).
2. Type your search query. Examples:
   - `attention mechanism` — finds any PDF card containing that phrase
   - `Content:transformer` — explicitly searches the Content field
   - `Content:gradient descent note:"Incremento PDF"` — combined search

> **Use case:** You vaguely remember reading something about "positional encoding" in one of your PDFs but can't remember which one. Search `positional encoding` in the browser and all matching PDF cards appear immediately.

> **Note:** Scanned PDFs (image-only) produce no text and won't be searchable. This only works for PDFs with embedded text layers.

---

## 10. Viewing Statistics

Go to **Tools → Incremento Statistics** to see your study history.

### Scopes

| Radio button | Shows |
|---|---|
| **This Session** | Cards studied in the last session (resets each time you open the scheduler dialog) |
| **Today** | Cards studied today (respects the Day Ends At boundary) |
| **All Time** | Cumulative totals since you started using Incremento |

### Charts

- **Card Types** — Topics vs Items breakdown
- **Selection Mode** — Priority vs Random breakdown
- **Tags** — Per-tag counts sorted from most to least studied

Each bar shows the count and percentage.

> **Use case:** After a month of studying, switch to "All Time" to see whether you are actually covering all three subjects equally. If Chemistry shows 60% and the others 20% each, consider adding tag quotas (see §3) to rebalance.

---

## 11. Exporting Your Data (Backup)

Go to **Tools → Export All Incremento User Data** to create a complete backup ZIP.

### What is included

| File | Contents |
|------|----------|
| `custom_learn_stats.json` | All study statistics (session, daily, lifetime) |
| `pdf_progress.json` | Last-read page and zoom level for every PDF card |
| `pdf_highlights.json` | All highlights (positions, colours, text) |
| `config.json` | All your scheduler settings |
| `pdfs/` folder | Every PDF file referenced in an Incremento PDF note |

### When to use this

- **Moving to a new computer** — export the ZIP, install Anki + Incremento on the new machine, import your Anki collection (via AnkiWeb sync or `.apkg`), then copy the JSON files back into the addon's `user_files/` folder and the PDFs into Anki's media folder.
- **Regular backup** — run this monthly alongside Anki's built-in backup.

### Restoring on a new machine

1. Install Anki and the Incremento addon.
2. Sync your Anki collection via AnkiWeb, or import your `.apkg` file.
3. From the ZIP:
   - Copy `*.json` files → `[Anki profile folder]/addons21/incremento/user_files/`
   - Copy `pdfs/*.pdf` → `[Anki profile folder]/collection.media/`
4. Restart Anki. All progress, highlights, and settings are restored.

---

## 12. Keyboard Shortcuts Reference

| Shortcut | Where | Action |
|----------|-------|--------|
| **Cmd+1** / **Ctrl+1** | PDF Viewer | Extract selection → fill Field 1 of new card |
| **Cmd+2** / **Ctrl+2** | PDF Viewer | Extract selection → fill Field 2 |
| **Cmd+3** / **Ctrl+3** | PDF Viewer | Extract selection → fill Field 3 |
| **Cmd+4** / **Ctrl+4** | PDF Viewer | Extract selection → fill Field 4 |
| **Option+H** / **Alt+H** | PDF Viewer | Highlight current text selection |

---

## 13. Common Workflows

### Workflow A: Incremental Reading + Flashcard Creation

**Goal:** Read a PDF book chapter by chapter while creating flashcards from key content.

1. **Add PDF to Topics** via Tools menu.
2. Start a session with 20% topics / 80% items.
3. When the PDF card comes up, read through the pages using Next →.
4. Select an important sentence, press **Cmd+1** to extract it to a new flashcard.
5. The citation link is automatically added — you can click back to the source anytime.
6. Check **"Highlight when extracting"** to mark everything you have already processed.
7. Next session, Incremento resumes the PDF at exactly the page you left off.

---

### Workflow B: Multi-Subject Balanced Study

**Goal:** Study Biology, Chemistry, and Physics equally every day.

1. Tag your cards with `Biology`, `Chemistry`, `Physics`.
2. Open scheduler settings, add all three tags as tag quotas with 33% each.
3. Lock all three (🔒) so they are always equal.
4. Set scope to **Today** so Incremento remembers the balance across sessions.
5. Every session has equal coverage of all three subjects.

---

### Workflow C: Research Paper Annotation

**Goal:** Read academic PDFs, annotate them, and create a linked knowledge base.

1. Add each paper as a PDF card.
2. While reading, highlight key claims in **yellow**, definitions in **blue**, and uncertainties in **pink**.
3. Use **Cmd+1** to extract important quotes into new cards. Citation links connect each card back to its source page.
4. When reviewing a derived card and wanting context, click the citation link — PDF opens at the exact page.
5. Search across all papers in the card browser using keywords.

---

### Workflow D: Exam Preparation

**Goal:** Review the most overdue material intensively.

1. Set **Priority ↔ Random** to 100% Priority.
2. Set **Scheduler scope** to All Time (so lifetime counts drive the scheduler).
3. Include only **Due / Review** cards (uncheck New and Learning).
4. Start session — you see only cards that are most overdue.

---

### Workflow E: New Course Onboarding

**Goal:** Work through all new material in a new subject without reviewing old material.

1. Tag all new course cards with `Neuroscience2025`.
2. Add a tag quota for `Neuroscience2025` at 80%.
3. Include only **New** cards.
4. Set session to 30 cards.
5. Each session works through new content until the tag is exhausted, then fills remaining slots with other cards.

---

*For questions or issues, visit the Incremento GitHub page or the Anki add-ons forum.*
