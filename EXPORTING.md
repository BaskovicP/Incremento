# Exporting and Restoring Incremento Data

This guide explains how to back up all your Incremento data and restore it on a new
computer (or after reinstalling Anki).

---

## What gets exported

Running **Tools → Export All Incremento User Data** creates a ZIP archive with this layout:

```
incremento_export_YYYY-MM-DD.zip
├── manifest.json               ← export metadata (date, counts, file descriptions)
├── config.json                 ← all scheduler and session settings
├── data/
│   ├── custom_learn_stats.json ← session, daily and lifetime review statistics
│   ├── pdf_progress.json       ← reading position and zoom level for every PDF card
│   ├── pdf_highlights.json     ← all highlighted passages and their colours
│   ├── priorities.db           ← card priorities (SQLite, for direct restore)
│   └── priorities.json         ← card priorities (human-readable JSON copy)
└── pdfs/
    ├── book1.pdf
    └── ...                     ← every PDF file referenced by an Incremento card
```

> **Note:** `priorities.db` and `priorities.json` contain the same data.
> The `.db` file is for fast direct restore; the `.json` is for manual inspection
> or importing into other tools.

---

## How to export

1. Open Anki.
2. Go to **Tools → Export All Incremento User Data**.
3. Choose a save location. The default filename includes today's date.
4. Click **Save**. A summary dialog confirms what was exported.

The export is safe to run at any time — it is read-only and does not modify any data.

---

## Restoring on a new computer

### Step 1 — Install Anki and the Incremento addon

Install the same version of Anki and then install Incremento via
**Tools → Add-ons → Get Add-ons**.

### Step 2 — Copy your Anki collection

Export your Anki collection from the old machine (**File → Export → Anki Collection
Package (.colpkg)**) and import it on the new machine. This restores all your cards,
including the Incremento PDF note type and card structure.

### Step 3 — Copy the PDF files

From the ZIP, copy everything inside the `pdfs/` folder into Anki's media folder on
the new machine:

| Platform | Anki media folder |
|---|---|
| macOS | `~/Library/Application Support/Anki2/<profile>/collection.media/` |
| Windows | `%APPDATA%\Anki2\<profile>\collection.media\` |
| Linux | `~/.local/share/Anki2/<profile>/collection.media/` |

Replace `<profile>` with your Anki profile name (usually `User 1`).

### Step 4 — Restore the data files

Find the Incremento addon folder on the new machine:

| Platform | Path |
|---|---|
| macOS | `~/Library/Application Support/Anki2/addons21/incremento/` |
| Windows | `%APPDATA%\Anki2\addons21\incremento\` |
| Linux | `~/.local/share/Anki2/addons21/incremento/` |

Inside it, create a `user_files/` folder if it does not exist. Then copy these files
from the ZIP's `data/` folder into `user_files/`:

| File | What it restores |
|---|---|
| `custom_learn_stats.json` | Review statistics (session, daily, lifetime) |
| `pdf_progress.json` | Reading position and zoom for every PDF card |
| `pdf_highlights.json` | All highlights |
| `priorities.db` | Card priorities (recommended — used directly by the addon) |

You do **not** need to copy `priorities.json` unless you want a human-readable
reference. If `priorities.db` is present, it takes precedence.

### Step 5 — Restore scheduler settings

From the ZIP root, open `config.json` in a text editor.
In Anki on the new machine: **Tools → Add-ons → Incremento → Config**, paste the
contents, and click **OK**.

Alternatively, just configure the settings manually via
**Tools → Start Incremental Learning** — the config is small and easy to recreate.

### Step 6 — Verify

1. Start Anki and open a PDF card. Confirm it loads at the correct page.
2. Go to **Tools → Start Incremental Learning** and check that statistics look correct.
3. Open a card and press `Option+P` to confirm priorities were restored.

---

## Inspecting the data manually

All data files except `priorities.db` are plain JSON and can be opened in any text
editor.

### priorities.json

```json
{
  "1234567890123": 12.5,
  "1234567890124": 50.0,
  "1234567890125": 87.32
}
```

Keys are card IDs (integers stored as strings). Values are priorities on a 0–100
scale where **0 = highest importance** and **100 = lowest importance**. The default
is 50.0.

### priorities.db (SQLite)

Open with any SQLite browser (e.g. [DB Browser for SQLite](https://sqlitebrowser.org)):

```sql
SELECT card_id, priority FROM priorities ORDER BY priority;
```

Or from the command line:
```sh
sqlite3 priorities.db "SELECT card_id, priority FROM priorities ORDER BY priority;"
```

### custom_learn_stats.json

```json
{
  "daily":    {"date": "2026-03-22", "counts": {"type": {}, "tags": {}, "mode": {}}},
  "lifetime": {"type": {}, "tags": {}, "mode": {}}
}
```

`type` tracks topics vs items, `mode` tracks priority vs random picks, `tags` tracks
per-tag counts.

---

## Partial restores

You can restore any subset of files independently — the addon reads each file only
when it needs it. For example, restoring only `priorities.db` will recover priorities
without touching statistics or highlights.

---

## Scheduling regular backups

The export is a single menu action, so it is easy to run before any major Anki
session. There is no automatic scheduled export — run it manually whenever you want
a checkpoint, especially before upgrading Anki or the addon.
