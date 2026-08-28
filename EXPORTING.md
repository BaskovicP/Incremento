# Exporting and Restoring Incremento

Use **Tools -> Export Full Backup** to create a single ZIP for moving Incremento to a new computer.

## What the backup contains

The ZIP now includes:

- `anki/all_decks.apkg` - all cards from the currently open Anki profile, with scheduling and referenced Anki media
- `user_files/<ProfileName>/` - the Incremento runtime folder for the currently open Anki profile, including:
  - `incremento.db`
  - `pdfs/`
  - `videos/`
  - `writing/`
  - `web_profile/`
  - `video_profile/`
- `config.json` - Incremento add-on config
- `data/*.json` - human-readable exports of priorities, PDF progress, highlights, and stats
- `manifest.json` - summary metadata
- `restore.txt` - quick restore steps

Transient runtime lock files are skipped.

Before export, Incremento checks the active profile database with SQLite's integrity check and creates its database copy through SQLite's backup API. The completed ZIP is reopened for validation and only then atomically replaces the selected destination, so an interrupted export does not replace an existing good backup with a partial archive.

## Fresh-install restore

1. Install Anki on the new computer.
2. Install the Incremento add-on.
3. Open Anki and import `anki/all_decks.apkg`.
4. Close Anki.
5. Copy the exported `user_files/<ProfileName>/` folder into the add-on's `user_files/` folder. Keep any other profile folders already present.
6. If needed, open **Tools -> Add-ons -> Incremento -> Config** and paste in `config.json`.
7. Start Anki and verify your PDFs, videos, writing notes, highlights, and reading progress.

Common add-on paths:

| Platform | Incremento add-on path |
|---|---|
| macOS | `~/Library/Application Support/Anki2/addons21/incremento/` |
| Windows | `%APPDATA%\\Anki2\\addons21\\incremento\\` |
| Linux | `~/.local/share/Anki2/addons21/incremento/` |

## Notes

- The Anki package is generated from the currently open profile.
- The APKG and `user_files/<ProfileName>/` snapshot both cover the profile that was open when the backup started.
- The runtime folder is exported as a full profile snapshot so local PDFs, EPUBs, downloaded videos, writing files, and browser session data can be restored together.
- The export is read-only. It does not delete or modify existing data.
- If the active Anki profile changes while export is running, Incremento aborts instead of combining two profiles.
