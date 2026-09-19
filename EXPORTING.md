# Exporting and Restoring Incremento

Use **Incremento -> Export Full Backup -> Export Now…** to create a single ZIP for moving Incremento to a new computer. The same chooser offers **Automatic Backups…**.

## What the backup contains

The ZIP now includes:

- `anki/all_decks.apkg` - all cards from the currently open Anki profile, with scheduling and referenced Anki media
- `user_files/<ProfileName>/` - the Incremento runtime folder for the currently open Anki profile, including:
  - `incremento.db`
  - `pdfs/`
  - `epubs/` (including managed Markdown learning documents)
  - `markdown_backups/` (one previous edited version per Markdown document)
  - `videos/`
  - `writing/`
  - `web_profile/`
  - `video_profile/`
- `config.json` - Incremento add-on config
- `data/*.json` - human-readable exports of priorities, PDF progress, highlights, and stats
- `manifest.json` - summary metadata
- `restore.txt` - quick restore steps

Transient runtime lock files are skipped.

Before export, Incremento checks the active profile database with SQLite's integrity check and creates its database copy through SQLite's backup API. The completed ZIP is reopened for validation before it atomically replaces the selected destination. Automatic exports build their temporary ZIP outside the selected folder when the filesystem permits, so desktop sync services see only the validated final slot instead of uploading a temporary `.incremento-backup-*.zip` as an additional cloud file.

## Automatic backups

Open **Incremento -> Export Full Backup -> Automatic Backups…** (or **Configure Automatic Full Backups…**) for the active Anki profile. Choose an existing destination folder, enable backups, and select on-profile-open, on-profile-close, and/or an interval (1–720 hours while Anki remains open; 0 disables the interval). Choose 1–20 rolling automatic versions (5 by default). Incremento creates slot files only until that count is reached; afterward, each new validated backup atomically replaces the oldest automatic ZIP at the same path. With five selected, the sixth backup replaces the first. Existing timestamp-named automatic ZIPs count toward the selected limit and are reused, so upgrading does not create a second set of slots. The on-open backup begins shortly after the profile is ready. Timed backups are checked while Anki is open and do not run while Anki is closed. The export runs off the UI thread and shows a progress window; collection operations may queue until its read finishes. A close-triggered full backup holds the collection open until the backup attempt finishes, so Anki shutdown or profile switching waits for success or failure. A previously running backup also completes before the profile unloads. A failed close backup is flagged when that profile next opens. Manual exports and other profiles' archives are never rotated. If the chosen folder becomes unavailable, Incremento reports an error and does not fall back to a different location.

To upload through Google Drive, Dropbox, or another sync app, choose a folder already synced by that app. Incremento keeps the temporary automatic archive outside that folder when possible and exposes only the final fixed slot to the sync app. Incremento does not authenticate to a cloud provider or confirm remote delivery. Temporary `.incremento-backup-*.zip` items uploaded by an older version may require one cleanup in the provider's web interface because they may already have disappeared from the local sync folder. Because the archives contain private cards and media, review the cloud account's security and keep an independent copy when needed.

## Restore a full backup

1. Install Anki and Incremento, then open the Anki profile you want to restore into. You can create a fresh profile first to keep an existing collection untouched.
2. Choose **Incremento -> Restore Full Backup…**. The file picker starts in this profile’s configured automatic-backup folder when it is available; you can browse to any full Incremento ZIP elsewhere.
3. Wait for the pre-check. Incremento reads both ZIP layers, checks every member’s CRC, rejects unsafe or duplicate paths and media names, verifies both SQLite databases, checks the embedded collection structure and orphan cards, opens a disposable copy with the installed Anki version, and compares file/card counts and database version with the manifest. It warns if a PDF or EPUB card references a cover image missing from the package. A damaged or unsupported archive is rejected before the current profile is changed.
4. Review the backup profile name and file counts. Confirm only if this is the backup you intend to restore. The current profile’s collection, Anki media folder, and Incremento profile folder will be replaced, including newer changes. If the source profile name differs, the runtime snapshot is placed under the current profile name.
5. Incremento creates an Anki safety backup, turns off automatic collection sync and periodic media sync, closes the profile, replaces the files, and reopens it. A failed replacement or reopen triggers rollback and restores the previous sync preferences; if rollback itself fails, Incremento keeps the prior files in its restore staging folders and reports their locations. Verify cards, media, PDFs, EPUBs, videos, writing notes, highlights, and reading progress before re-enabling sync.

The backup’s add-on configuration is restored through Incremento’s normal config writer. Existing automatic-backup folder settings are retained, so restoring a ZIP from another computer does not redirect scheduled backups to an old path. The pre-check catches structural and integrity problems; it cannot prove that every card’s content or external reference is correct. Keep the original ZIP until you have inspected the restored profile.

New full backups explicitly include PDF and EPUB cover images referenced by Incremento's plain filename fields. Older ZIPs may lack these covers even when their cards and source documents are intact; the restore warning counts the missing images. The reviewer shows a compact title-only source panel when a cover cannot load. A missing PDF cover can be regenerated from the document in the PDF reader.

The pre-check does not contact AnkiWeb or compare the backup with the server. A restore replaces the open **local** profile, including cards that may have been added since the backup. If you then perform an ordinary sync, newer server changes or deletions may be merged with the restored cards. If the restored collection must become the authoritative copy, force a one-way **Upload** on the first manual sync; **Download** replaces the restored local collection. Anki media sync is separate and always merges files, even during a one-way card sync. A different AnkiWeb account remains linked to the current profile; restoring this ZIP does not change its login. To inspect both collections without replacing the current one, restore into a fresh unsynced Anki profile first.

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
