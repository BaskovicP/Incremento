# Incremento Architecture

This document defines Incremento's persistence boundaries, dependency direction, and recovery model. It is the durable reference for changes that span Anki, SQLite, profile files, Qt, or the browser companion.

## System boundaries

Incremento is an Anki add-on, not a second flashcard database. Anki remains authoritative for:

- notes, cards, note types, decks, tags, and media
- card queue state, due dates, FSRS state, revlog, and Undo/Redo
- the currently open profile and collection-operation lifecycle

Incremento adds four stores around that canonical collection:

| Store | Scope | Owns |
|---|---|---|
| `user_files/<Profile>/incremento.db` | Per Anki profile | Reader position, priorities, topic/custom schedule state, knowledge tree, search indexes, import journal, and other add-on metadata |
| `user_files/<Profile>/custom_learn_stats.json` | Per Anki profile | Canonical normalized daily/lifetime count and time aggregates |
| `user_files/<Profile>/...` content folders | Per Anki profile | Managed PDFs, EPUBs/extracted EPUBs, videos, writing files, browser profiles, and diagnostics |
| Anki add-on config | Add-on installation | Validated settings and scheduler presets; older keys are migrated by `backend/config_service.py` |

The companion extension also keeps browser-only preferences and linked-tab state in extension storage. It does not replace an Incremento or Anki store.

## Dependency direction

The intended direction is:

```text
Qt dialogs/docks and addon composition (__init__.py)
                    ↓
application workflows and Anki operation adapters
                    ↓
domain rules, repositories, content managers
                    ↓
profile paths, SQLite, JSON, managed files
```

- `__init__.py` composes hooks, menu actions, reviewer patches, and profile lifecycle callbacks.
- `frontend/` owns Qt widgets and UI-only state. Long collection work uses `QueryOp`/`CollectionOp`; file extraction uses Anki's background task runner.
- `backend/` owns scheduling rules, persistence, imports, search, and bridge normalization. Backend modules should not import frontend dialogs. `frontend/session_launcher.py` is the current session UI adapter.
- `backend/anki_compat.py` is the single boundary for private reviewer/V3 queue APIs. Missing capabilities must disable the affected optional feature without changing cards.
- `backend/paths.py` is pure and is the only place that constructs paths below `user_files/`.

Some older backend modules still call `aqt.mw` directly. New code should accept an explicit collection/profile and move Qt interaction to a frontend or root adapter. This is a staged seam, not permission to add new backend-to-frontend imports.

## Profile and thread lifecycle

The active Anki profile is captured at the start of every background operation and passed through to storage helpers. A callback must discard UI results if the active profile changed while it was running.

`backend/db_connection.py` owns one SQLite connection per live worker thread and profile. Connections use WAL, `synchronous=NORMAL`, and a bounded busy timeout. They are never shared concurrently between Anki task threads. A profile transition closes the UI thread's matching handle; an already-running worker may finish with its own handle, which is closed when that worker next changes profile or at shutdown. The hook must never close a connection underneath another live thread.

Anki collection reads and mutations follow Anki's operation model:

- `QueryOp` for serialized collection reads that may be expensive
- `CollectionOp` for normal collection mutations and larger filtered-deck construction; the bounded initial Incremento session build uses a serialized no-progress mutation plus `on_op_finished` to avoid a macOS native-modal activation race
- the operation-provided `col`, never a late lookup of `mw.col`, inside the worker
- Qt and reviewer transitions only in the success callback after Anki finishes the operation

## SQLite schema lifecycle

`backend/db_schema.py` owns the migration ledger. `schema_migrations` and `PRAGMA user_version` advance in the same transaction as each schema change. Failed migrations roll back the schema, ledger row, and version together.

`backend/db.py` currently contains the legacy baseline plus ordered post-ledger migrations. New schema changes must:

1. add one monotonic migration with a stable name;
2. remain idempotent when practical;
3. avoid destructive data rewrites without an explicit backup path;
4. add a migration and rollback regression;
5. update diagnostics/schema expectations and this document if ownership changes.

`backend/db.py` remains a large compatibility repository. New bounded read models should live in focused modules such as `search_repository.py`; existing call sites can be extracted incrementally without a flag-day rewrite.

## Cross-store imports and recovery

Creating PDF, EPUB, writing, managed local-file, or downloaded/local-video content crosses Anki, SQLite, and profile files. These workflows use `backend/operation_journal.py`:

1. create a pending journal row and stable SQLite content ID;
2. journal each profile-relative path before creating it;
3. create the managed file and Anki note/card using the existing provenance fields;
4. bind the card/note identity;
5. atomically register `content_items` and mark the journal committed.

Before an Anki card exists, failure removes only paths explicitly created by that operation. Once a card exists, recovery preserves user content rather than guessing. On the next profile open, `backend/reconciliation.py` can rebind an interrupted import through an optional legacy `Incremento_Content_ID` or the exact existing provenance source link, remove rows whose Anki owner is definitely gone, and repair unambiguous knowledge-tree links. New installations do not add `Incremento_Content_ID` to Anki note types; the canonical identity lives in SQLite.

## Anki note-type updates

`backend/note_type_updates.py` inspects existing Incremento card formats without mutating the collection. Startup never creates unused note types and never silently changes existing fields or templates. When an update is actually pending, `frontend/note_type_update_dialog.py` explains the one-way-sync consequence and requires explicit confirmation. The user can defer, run a normal sync first, or apply the approved update and then enter Anki's native full-sync flow. Existing optional fields are tolerated and never removed automatically.

Reconciliation deliberately does not delete arbitrary untracked files. Cleanup of ambiguous legacy files remains an explicit user maintenance action.

Legacy flat `user_files/` migration is resumable and non-overwriting. `backend/migration.py` merges only missing descendants and records conflicts in `.incremento_profile_migration.json` for the active profile.

## Scheduling boundary

Anki owns the answer and its revlog. Incremento may adjust the resulting interval only through `backend/answer_schedule.py`, attached to the existing **Answer Card** undo step.

- Item Pass is Anki Good; item Fail is Again.
- Topic More/Same/Less all submit Anki Good because they express desired frequency, not recall quality.
- Topic A-factor and custom-schedule rules resolve one final post-answer interval.
- Preview filtered decks (`resched = false`) are never overridden and consume no one-time rule.
- No after-answer workflow may write unsupported revlog SQL or use `set_due_date()` to manufacture a second review/undo entry.

Scheduling changes require lifecycle tests for real answer, revlog ownership, Undo, Redo, filtered-deck Preview, and profile reset.

## Search architecture

Searchable PDF/EPUB/OCR text is stored in ordinary SQLite tables with optional FTS5 mirrors and triggers. If Anki's SQLite build lacks FTS5, bounded plain-table fallback remains available.

`backend/search_indexer.py` extracts PDF text off the Qt thread, stores file mtime/size/status, backs off repeated failures, reports progress, and checks cancellation between files. `backend/search_repository.py` exposes bounded rows to `frontend/search_all.py`; UI code should not add raw Incremento SQL. Search-while-typing is debounced, card candidates are bounded, and PDF document discovery runs as a `QueryOp` before the collection-free extraction task starts.

Manual **Reindex PDF Text** is also background, cancellable, profile-captured, and forced. A large library must never be synchronously extracted from a Search ALL keypress.

## Configuration and statistics

All shipped Python reads/writes add-on configuration through `backend/config_service.py`. The service versions the shape, normalizes risky values, preserves unknown forward-compatible keys, and keeps the legacy `profiles` scheduler-preset alias synchronized with `scheduler_presets`.

`custom_learn_stats.json` is the statistics source of truth. `backend/statistics.py` performs profile-locked atomic read/modify/write operations and mirrors the normalized shape to SQLite only as compatibility/fallback. Do not create a second competing aggregate shape.

## Browser bridge security

The companion talks to `127.0.0.1:8766` using bridge protocol 2:

1. a Chrome/Brave extension origin performs a handshake;
2. the bridge binds that origin for the Anki run and returns an ephemeral token;
3. every data request supplies the token and protocol headers;
4. the bridge enforces exact origin, request-size, path, and concurrent-handler limits.

Tokens reset when the bridge/profile stops. The extension retries one handshake after a `401`. Only loopback clients are trusted; Incremento exposes no remote listener. Source and generated `dist/` extension files must remain aligned.

## Backup and diagnostics

**Export Full Backup** is private and current-profile scoped. Its APKG and `user_files/<Profile>/` snapshot refer to the profile captured when export starts. SQLite is copied through the backup API after `PRAGMA integrity_check`; the ZIP is validated and atomically replaces the destination only after completion. Other profile folders are not included or deleted.

**Export Support Bundle** is a separate privacy-safe diagnostic artifact. Its event schema is allowlisted and excludes card/note content, raw IDs, profile/deck/tag names, URLs, paths, user filenames, database rows, exception text, and precise activity timestamps.

## Release gates

Supported packaged baseline is Anki 24.11 or newer. Optional private-API features fail closed when a newer Anki changes the reviewer contract.

The release command is:

```bash
.venv/bin/python scripts/package_addon.py --release --clean-staging
```

It compiles Python, runs the full Python suite, rebuilds the PDF viewer and companion extension, runs extension tests, validates required archive entries, and rejects runtime data, path traversal, caches, and bytecode. CI repeats the Python suite on supported Python versions and verifies generated extension assets are committed.

Runtime dependency installation is always explicit. PyMuPDF is bounded to `>=1.24,<2`; yt-dlp is never silently installed into Anki's Python environment.
