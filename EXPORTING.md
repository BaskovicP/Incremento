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
│   ├── incremento.db           ← all user data in one SQLite file (for direct restore)
│   ├── priorities.json         ← card priorities          (human-readable copy)
│   ├── pdf_progress.json       ← reading positions/zoom   (human-readable copy)
│   ├── highlights.json         ← PDF text highlights      (human-readable copy)
│   └── stats.json              ← review statistics        (human-readable copy)
└── pdfs/
    ├── book1.pdf
    └── ...                     ← every PDF file referenced by an Incremento card
```

`incremento.db` is the authoritative source. The four JSON files are human-readable
copies of the same data — useful for inspection or importing into other tools, but
not required for restore.

---

## What incremento.db contains

| Table | Contents |
|---|---|
| `priorities` | Priority value (0–100) per card ID |
| `pdf_progress` | Current page and zoom level per card ID |
| `pdf_highlights` | All highlighted passages, colours and positions |
| `stats` | Daily and lifetime review statistics |

---

## How to export

1. Open Anki.
2. Go to **Tools → Export All Incremento User Data**.
3. Choose a save location. The default filename includes today's date.
4. Click **Save**. A summary dialog confirms what was exported.

The export is read-only — it never modifies any data.

---

## Restoring on a new computer

### Step 1 — Install Anki and the Incremento addon

Install the same version of Anki, then install Incremento via
**Tools → Add-ons → Get Add-ons**.

### Step 2 — Copy your Anki collection

Export your collection from the old machine (**File → Export → Anki Collection
Package (.colpkg)**) and import it on the new machine. This restores all your cards,
including the Incremento PDF note type.

### Step 3 — Copy the PDF files

From the ZIP, copy everything inside `pdfs/` into Anki's media folder on the new machine:

| Platform | Anki media folder |
|---|---|
| macOS | `~/Library/Application Support/Anki2/<profile>/collection.media/` |
| Windows | `%APPDATA%\Anki2\<profile>\collection.media\` |
| Linux | `~/.local/share/Anki2/<profile>/collection.media/` |

Replace `<profile>` with your Anki profile name (usually `User 1`).

### Step 4 — Restore incremento.db

Find the Incremento addon folder on the new machine:

| Platform | Path |
|---|---|
| macOS | `~/Library/Application Support/Anki2/addons21/incremento/` |
| Windows | `%APPDATA%\Anki2\addons21\incremento\` |
| Linux | `~/.local/share/Anki2/addons21/incremento/` |

Inside it, create a `user_files/` folder if it does not exist. Then copy
`data/incremento.db` from the ZIP into that `user_files/` folder.

That single file restores everything: reading positions, highlights, priorities,
and statistics.

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

## Partial restores

Each table inside `incremento.db` is independent. If you only want to restore
priorities without touching statistics, you can import just the priorities rows
using any SQLite tool:

```sql
-- Run on the new machine's incremento.db:
ATTACH '/path/to/exported/incremento.db' AS src;
INSERT OR REPLACE INTO priorities SELECT * FROM src.priorities;
DETACH src;
```

---

## Inspecting the data manually

### Via the JSON copies in the ZIP

All four `.json` files in `data/` are plain text and can be opened in any editor.

**priorities.json**
```json
{
  "1234567890123": 12.5,
  "1234567890124": 50.0
}
```
Keys are card IDs. Values are priorities on a 0–100 scale where **0 = highest
importance** and **100 = lowest importance**. Default is 50.0.

**pdf_progress.json**
```json
{
  "1234567890123": {"page": 14, "zoom": 1.25}
}
```

**highlights.json**
```json
{
  "1234567890123": [
    {"id": "abc123", "page": 5, "color": "yellow",
     "text": "selected text", "rects": [{"x":10,"y":20,"w":100,"h":15}]}
  ]
}
```

**stats.json**
```json
{
  "daily":    {"date": "2026-03-22", "counts": {"type": {}, "tags": {}, "mode": {}}},
  "lifetime": {"type": {}, "tags": {}, "mode": {}}
}
```

### Via SQLite directly

Open `incremento.db` with [DB Browser for SQLite](https://sqlitebrowser.org) or
the command line:

```sh
sqlite3 incremento.db ".tables"
sqlite3 incremento.db "SELECT card_id, priority FROM priorities ORDER BY priority;"
sqlite3 incremento.db "SELECT card_id, page, zoom FROM pdf_progress;"
```

---

## Scheduling regular backups

Run **Tools → Export All Incremento User Data** before any major Anki session,
before upgrading Anki, or before upgrading the addon. There is no automatic export.
