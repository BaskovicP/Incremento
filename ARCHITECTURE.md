# Incremento Architecture

This document defines Incremento's persistence boundaries, dependency direction, and recovery model. It is the durable reference for changes that span Anki, SQLite, profile files, Qt, or the browser companion.

Embedded website storage is managed by `frontend/browser_profiles.py`: the Web reader keeps its existing per-profile `web_profile/` directory, and the search popup uses a separate `search_profile/` directory only when **Remember website logins** is enabled. Both paths come from `backend/paths.py`. Persistent profiles have unique storage names and profile-local cache paths; pages are owned by their widgets and destroyed before the profile at profile close/application shutdown so Chromium can flush cookies and local storage. The search popup remains bridge-free, with temporary storage by default. Search provider and persistence preferences are normalized through `backend/config_service.py` and applied only after Settings saves successfully.

## System boundaries

Incremento is an Anki add-on, not a second flashcard database. Anki remains authoritative for:

- notes, cards, note types, decks, tags, and media
- card queue state, due dates, FSRS state, revlog, and Undo/Redo
- the currently open profile and collection-operation lifecycle

Topic **Done** uses Anki's native single-card suspension and note tagging without a second completion registry. The `topic_done_tag` setting defaults to `topic/done`; native tag addition preserves existing tags and merges into the suspension's Undo step. One Undo/Redo restores/reapplies both changes, and a failed tag write or merge rolls back the action. Tags are note-scoped and shared by sibling cards, while suspension changes only the selected card. **Revisit in…** uses native Set Due Date and the card's Anki custom-data key `incrv` (the logical scheduler day when automatic reading selection resumes). The metadata update is merged into the same undo step, preserves other custom-data keys, and rolls back through Anki on failure. Reader pools explicitly include cards without this key; only a future marker on a future-due card suppresses their usual due-independent selection. Expiration needs no startup scan or persistence write. This small piece of scheduling metadata lives with the Anki card for sync and Undo/Redo, rather than in Incremento SQLite. The frontend dispatches captured card/profile/tag requests through CollectionOp and rejects stale commands and stale notification Undo requests.

Incremento adds four stores around that canonical collection:

Math recognition uses `backend/math_ocr.py` as an Anki-free process boundary and `backend/latex_ocr_worker.py` as the standalone pix2tex adapter. Only the explicit setup button creates an isolated environment in the OS application cache and installs the pinned pix2tex release plus compatibility constraints. Setup loads the model before publishing its readiness marker. Anki never imports PyTorch/pix2tex. Each bounded recognition subprocess receives one validated PNG through stdin and returns bounded JSON, with dependency output suppressed. A temporary process-output file is polled off the UI thread and removed after each child exits. Only whitelisted stage identifiers and bounded numeric counts enter the dialog through a single-slot mailbox; raw dependency output is never displayed or added to diagnostics. The isolated worker adapts upstream download progress into measured byte counts. The dialog polls that mailbox with its existing lifecycle guard, renders current-stage percentages only when totals are known, and shows elapsed time for unmeasured stages. The worker disables upstream clipboard copying and checkpoint downloads during recognition. Cancellation/timeout terminates and reaps the child. The shared snapshot dialog captures profile/collection/source identity, rejects stale callbacks, and cancels work on retirement. No crop, recognition result, or credential is persisted. Legacy SimpleTex credential files and their export exclusions remain for compatibility, but active settings and recognition no longer read them.

| Store | Scope | Owns |
|---|---|---|
| `user_files/<Profile>/incremento.db` | Per Anki profile | Reader position, bounded Web extraction anchors, priorities, topic/custom schedule state, knowledge tree, search indexes, import journal, daily trend snapshots, unique page-reading history, and other add-on metadata |
| `user_files/<Profile>/custom_learn_stats.json` | Per Anki profile | Canonical normalized daily/lifetime count and time aggregates |
| `user_files/<Profile>/...` content folders | Per Anki profile | Managed PDFs, EPUBs/extracted EPUBs, videos, writing files, browser profiles, checksummed SuperMemo optimization archives, and diagnostics |
| Anki add-on config | Add-on installation | Validated settings and scheduler presets; older keys are migrated by `backend/config_service.py` |

The companion extension also keeps browser-only preferences and linked-tab state in extension storage. It does not replace an Incremento or Anki store. Ordinary-page access is gesture-scoped with `activeTab`; persistent required hosts are provider/loopback only. Users may separately opt into optional HTTP(S) access for cross-navigation link saving and Web tracking; the service worker dynamically registers or removes the content loader with that permission. Its bounded PDF stream and capture budgets reduce browser-process exposure before the authenticated bridge performs independent validation.

Custom UI language packs are profile files under `user_files/<Profile>/language_packs/`, routed through `backend/paths.py` and bounded/validated by `backend/language_packs.py`. They contain UI text only, never executable catalogs or Anki content. Settings stages an import in memory and saves the pack together with the config choice on acceptance, restoring the previous pack if saving fails. The config preference uses `custom:<locale>`; profile-open resolves that frozen startup preference against only the opened profile's pack, and missing packs fall back to English. Profile-close clears the custom snapshot, and existing root menu actions are relabeled without recreating shortcuts. PDF startup receives a validated snapshot that is cleared for the next document/profile when absent. The companion independently stores its pack registry and preference in one local storage write. Both apps share a generated English CSV schema and bundled editable snapshots; see `TRANSLATING.md` for their contract.

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

Migration 13 adds `browser_website_tags`, the companion popup's opt-in tag preferences keyed by exact normalized hostname. The per-profile database stores only explicitly remembered hostnames and bounded tag lists, never page paths, queries, fragments, or a visit history. Disabling a website deletes its row. The authenticated `/incremento/website-tags` endpoint reads or replaces only that website's set and binds writes to the Anki profile/session that supplied the popup's initial preference. Requests and the total number of remembered websites are bounded. Anki remains authoritative for tags on actual notes; these rows are import-form defaults only. Support diagnostics expose table shape and row count, never hostnames or tags. Ordinary profile backups include the preferences.

Migration 14 adds `document_links`, profile-scoped PDF reference associations (source card/kind/page and a bounded passage label; target document/page/scroll). Migration 15 indexes target endpoints for bounded reverse page-link lookups. PDF page connections appear at both endpoints using the same stored association. `backend/document_links.py` captures canonical content identities when present and follows their card rebinding, while legacy associations retain card identity. The visible page-link bridge re-resolves each connection and both live documents under read-only collection access before a jump; profile, reader generation, and page-request checks retire stale buttons. Deleting a target leaves a repairable association. SQLite owns these supplemental relationships; Anki owns the document cards and note fields. Support diagnostics expose only the allow-listed table's shape/count, never reference rows or passage labels.

Migration 18 adds bounded, bidirectional `epub_connections` with canonical endpoint identities, section indices, text offsets, scroll fallbacks, and a bounded excerpt. Either endpoint can remove the same row. It also adds `epub_progress.appearance_mode`; appearance writes never replace navigation or read markers. `backend/epub_reference.py` resolves only existing managed files and currently sanitized, contained chapter paths under a captured profile, without extracting or repairing files. `frontend/epub_reference_workspace.py` owns separate WebEngine profiles, nonces, position state, and asynchronous lifetimes for references and destination pickers. It reuses the main EPUB script in ApplicationWorld with explicit book metadata, never the main reader’s progress handler. Profile close invalidates pending requests and destroys these panes. Reference extraction passes its explicit card and section through Add Card’s captured options; note creation records that source before the legacy main-reader attachment hook. PDF and EPUB share `PdfFocusMode` with one active owner per Anki window.

Migration 16 adds nullable `source_y` and `target_y` physical-page fractions to these associations. Legacy links retain their existing scroll semantics. The destination dialog shares the reference reader's restricted WebEngine setup but owns its state and lifetime independently of both reading panes; one pending chooser is retained. Confirmation revalidates the live document, physical page count, profile/source lifetime, and reading limit before a location reaches the link writer. Cancelling only disposes the preview. Primary-reader annotation refreshes retain the transient displayed page, zoom, and location instead of replacing a linked passage with saved reading progress.

`backend/pdf_reader_state.py` owns each supplemental reader's transient page, zoom, scroll, nonce and lifetime. `frontend/pdf_reference_workspace.py` resolves live PDF identities via a captured-profile QueryOp, contains paths within that profile's PDF directory, and supplies a separate restricted WebEngine profile/page/interceptor per view. The reference app in `frontend/src/ReferencePdfViewer.jsx` and `referencePdfReader.mjs` mounts independently of the primary reader; it never dispatches primary-reader progress or scheduling commands. One floating preview and one pinned reference bound WebEngine resource use. Pinning reparents the same view without reloading. Source-aware extraction passes the reference card explicitly to Add Card instead of consulting the primary dock's globals. Profile close invalidates all pending references and link dialogs. The existing primary reader remains the compatibility adapter for normal study and its progress/timer hooks.

Migration 10 adds `reader_custom_colors`, a bounded, ordered sixteen-slot palette
shared by the PDF and EPUB annotation pickers within each profile. The shared Qt
dialog restores these swatches on open and commits all slots atomically on close,
including Cancel, without changing the selected annotation color on Cancel.
On first use, an existing Qt palette seeds the profile's swatches. Qt's global
palette is restored after the picker closes so other profiles and unrelated color
dialogs do not inherit edits. The profile database, not Qt preferences, owns
subsequent reader swatches and includes them in ordinary Incremento backups.

PDF annotation interchange is owned by `backend/pdf_annotations.py`. Migration 9
adds native annotation metadata to `pdf_highlights` and a per-card
`pdf_annotation_sync` table containing stable per-page PDF names, the last merged
annotation baseline, a page-content fingerprint, and an explicitly linked
original path. Incremento's SQLite annotations and the managed/linked PDFs are
reconciled in both directions. Neither store alone overrides concurrent edits.
Original paths and comment baselines are private user metadata.

Captured-profile workers stage and validate PDF files beside their destinations,
check for intervening file changes, save the previous versions to profile-local
backup slots, and atomically replace each PDF before committing the SQLite
baseline. Stable PDF annotation names make retries after partial writes
idempotent. SQLite edits made during file I/O are retained and trigger another
pass. A private per-document catalog stamp identifies the last shared baseline;
missing annotations in an older/unstamped snapshot are preserved rather than
interpreted as deletions. No user comment text is stored in that stamp.
Local PDF loading uses `backend/pdf_byte_ranges.py` and the instance-owned
`frontend/pdf_range_bridge.py`. Each captured source authorizes one managed PDF
or that card's exact derived reader copy under the captured profile. The existing
nonce/card bridge carries an additional per-load token and bounded 256 KiB reads
through the collection-free task executor, with two client requests and at most
four server jobs in flight per reader. JavaScript supplies offsets, never a path.
File identity is rechecked around every read; stale profile/document replies are
dropped. PDF.js receives reassembled requested ranges with streaming and automatic
whole-file prefetch disabled. No network listener or CSP expansion is involved.
The visible page renders first; cancellable idle display renders on tiny temporary
canvases prepare the moving ±5 page window within a 64 MiB estimated page-resource
budget. The current page is always retained, even if it alone exceeds the budget;
idle decoding stops before exhausting the remaining headroom. Hidden readers
release neighboring pages. PDF.js image resizing also has an explicit 32 MiB
canvas-area limit. `pdfPageResources.mjs` shares ownership between foreground
renders, the page window and footnote previews, so disposing a preview cannot
clean a page in use by the reader. Preview caches have a separate 32 MiB estimated
budget and four-entry ceiling. Text and decoded page resources are released
together; selection and font metadata share one streamed extraction, reused on
zoom. Annotation indexes and normalized geometry are reused until edits arrive,
and note tooltips subscribe independently of the reader.

`frontend/pdf_annotation_sync.py` coalesces automatic saves after 400 ms of quiet;
explicit sync bypasses that wait. `backend/pdf_annotation_process.py` serializes
native annotation jobs in a separate compatible Python interpreter through the
private `pdf_annotation_worker.py` entry point. The child imports no Anki or Qt,
uses the installed PyMuPDF package, checks cooperative cancellation and lowers its
CPU priority where supported. The parent bounds processing and result size,
validates returned paths and fixed error codes, and owns exact temporary outputs
so abnormal exits can clean them safely. A bounded in-memory, profile-scoped cache
reuses page-content digests only after matching the full PDF byte hash; every
file-change check and commit validation remains active. Queue reset retires the
cache generation so an old worker cannot repopulate it. Native work never falls
back to Anki's interpreter. `backend/pdf_reading_priority.py` remains available
for legacy in-process checkpoint users.

The derived `pdf_annotations/<card_id>/reader.pdf` omits native highlights
and Incremento snapshot frames so the interactive viewer paints them once; other
annotation appearances stay native. These paths belong to `backend/paths.py` and
are included with the profile tree in full backups. Unlinked original PDFs are
never scanned or inferred. The dock displays the latest derived copy, or the
managed PDF as a safe fallback, before starting background interchange. Moving
to another PDF cancels obsolete work, lock-queue time is separate from the
bounded processing budget, and unchanged baselines reuse the validated derived
copy. Protected or changed-content documents fail closed.
Sync results also identify a replaced derived reader file, independently of
native annotation changes. Main and supplemental readers then reopen fresh byte
sources while preserving each pane's own position, so later range requests never
use a token for the replaced file. Unchanged reader copies retain their caches.

`backend/db_schema.py` owns the migration ledger. `schema_migrations` and `PRAGMA user_version` advance in the same transaction as each schema change. Failed migrations roll back the schema, ledger row, and version together.

PDF reading state is profile-scoped in `pdf_progress`. Alongside page, zoom, scroll, and read-marker state, its validated `appearance_mode` stores the explicit Original, Dark, or Night choice for each PDF card. The config-backed PDF appearance policy supplies the default or temporarily forces one mode globally; forcing does not overwrite per-document state.

`backend/db.py` currently contains the legacy baseline plus ordered post-ledger migrations. New schema changes must:

1. add one monotonic migration with a stable name;
2. remain idempotent when practical;
3. avoid destructive data rewrites without an explicit backup path;
4. add a migration and rollback regression;
5. update diagnostics/schema expectations and this document if ownership changes.

`backend/db.py` remains a large compatibility repository. New bounded read models should live in focused modules such as `search_repository.py`; existing call sites can be extracted incrementally without a flag-day rewrite.

Web extraction markers are supplemental state, not card content. An anchor is staged before the Add Card field callback so the amber marker cannot be lost by a delayed adapter; the profile-scoped extraction draft and a bounded Web-dock runtime copy retain the same validated record until the transfer is rejected, discarded, or finalized. Only the Incremento Add Card note that owns that draft may finalize it. After Anki has successfully created the note, `web_card_sources` stores the text quote/DOM anchor or snapshot region/element anchor under the captured Web card and exact normalized HTTP(S) URL, and the runtime copy is released so the marker repaints green. The private bridge is installed once after navigation and resolves anchors to bounded document-space rectangles without inserting extraction elements, styles, or mutation observers into the remote page. A pointer-transparent native Qt layer above `QWebEngineView` paints amber/green markers and follows Qt's scroll, resize, and content-size signals; generation, profile, card, page, URL, anchor-ID, state, kind, coordinate, and count checks reject stale or forged callbacks. The Anki note remains authoritative. Invalid, ambiguous, oversized, stale-profile, or stale-card anchors fail closed without blocking text or snapshot transfer or note creation.

## Cross-store imports and recovery

`backend/markdown_manager.py` converts bounded UTF-8 Markdown into a temporary offline EPUB, preserving the original Markdown bytes and only contained regular raster-image files. Python-Markdown is supplied by Anki. Rendered content uses an inert tag/attribute allowlist; remote resources, active HTML, CSS, symlinks, and escaping image paths cannot enter the study copy. Major headings become EPUB sections and document-local anchors are rewritten to those sections. `frontend/markdown_document_dialog.py` prepares the copy through the non-collection executor, rejects stale/closed-profile callbacks, and performs the journaled import through a serialized `CollectionOp`. The existing EPUB manager owns storage, canonical `content_items.kind = epub`, note type, index, scheduling, progress, and reader state. Dedicated provenance stores `Incremento_Source_Type = Markdown`; no new SQLite schema or writing state is introduced. The exact original source remains inside the EPUB as `source.md`, and user-owned source files are never modified.

The Markdown batch importer snapshots per-file options before background conversion and serialized imports. Its Qt previews sanitize text and deny all resource loading. `frontend/markdown_edit_dialog.py` edits the managed `source.md`, not the original external file. The backend validates the exact canonical card/storage owner, bounds source/embedded assets, rejects symlinks and stale archive revisions, validates a new reader cache before replacement, and replaces the archive/cache/search index with exception rollback. An in-process lock serializes Markdown saves; Anki state and supplemental annotations/positions are untouched. `source_assets.json` retains original image-reference mappings without reopening external files. One previous archive per document is retained under the path-owned, profile-scoped `markdown_backups/` directory; file edits are not Anki Undo operations.

Creating PDF, EPUB, writing, managed local-file, or downloaded/local-video content crosses Anki, SQLite, and profile files. These workflows use `backend/operation_journal.py`:

1. create a pending journal row and stable SQLite content ID;
2. journal each profile-relative path before creating it;
3. create the managed file and Anki note/card using the existing provenance fields;
4. bind the card/note identity;
5. atomically register `content_items` and mark the journal committed.

Before an Anki card exists, failure removes only paths explicitly created by that operation. Once a card exists, recovery preserves user content rather than guessing. On the next profile open, `backend/reconciliation.py` can rebind an interrupted import through an optional legacy `Incremento_Content_ID` or the exact existing provenance source link, remove rows whose Anki owner is definitely gone, and repair unambiguous knowledge-tree links. New installations do not add `Incremento_Content_ID` to Anki note types; the canonical identity lives in SQLite.

Audio imports use the same content identity journal but deliberately store the selected file in Anki's `collection.media`, not under `user_files/`. A unique Anki media name and a canonical `[sound:...]` note-field reference make normal Anki media sync authoritative for desktop and mobile availability. Failure before note creation moves the newly added media file to Anki's trash. The minimal card-template player stores resume position in that client's WebView `localStorage`; this state is per device, is not Incremento SQLite data, and does not synchronize through AnkiWeb.

Native SuperMemo import is split across `backend/supermemo_format.py` and `backend/supermemo_import.py`. The first is a bounded, read-only parser for matched KNO/folder pairs and securely extracted ZIPs; it rejects unknown fixed-record layouts, traversal, symlinks, oversized entries, count mismatches, and invalid references. It resolves the one-based Text/Image registry usage chains, self-sized component descriptors, native title and reference records, numbered HTML files, and registered image files without executing collection content. The second creates dedicated Incremento-owned standard and cloze note types and maps only into Anki-owned card/note/schedule/revlog/media fields plus existing Incremento priorities, topic schedules, knowledge-tree nodes, import journal, provenance fields, and content identity. Deleted elements are excluded and surviving descendants are reparented to the nearest importable ancestor. Rich HTML is sanitized while retaining passive formatting, and supported raster images are signature-validated, copied once into Anki media under collection-scoped names, and referenced from every using card. A single SuperMemo `[...]` omission with a non-empty answer maps losslessly to one Anki `c1` deletion; ambiguous multi-omission or answerless items remain normal Q/A notes. SuperMemo A-factor, forgetting-index, compact collection fingerprint, and element identity use Anki card custom data within Anki's key and size restrictions; no SuperMemo-specific SQLite metadata table exists. Opaque SM8 and SM17/SM20 optimization files are copied losslessly to the profile path returned by `backend/paths.py` and covered by a checksum manifest, but are never used to schedule. Direct historical revlog restoration makes the explicitly confirmed bulk import non-undoable; future reviews are exclusively Anki-scheduled. Reimport identity is the compact collection fingerprint plus element number in card custom data, with the older internal provenance-link form retained as a compatibility fallback.

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

PDF results require both a live Anki document and an available managed file. `backend/pdf_search.py` prunes only derived PDF text after confirming that its Anki card is gone; a missing file alone never authorizes deletion. `frontend/pdf_search_lifecycle.py` captures exact PDF IDs before note deletion and reconciles them through the serialized collection queue after deletion or Undo/Redo. Explicit Search ALL also audits older indexed owners in the background; profile open performs no index scan. A `deleted` marker in `document_index_state` lets Search ALL rebuild restored documents on demand without modifying Anki's undo stack. Generation guards prevent retired extraction jobs from republishing text after deletion or profile closure. Highlights, annotations, source links, extracted notes, and files are outside this cleanup.

## Configuration and statistics

All shipped Python reads/writes add-on configuration through `backend/config_service.py`. The service versions the shape, normalizes risky values, preserves unknown forward-compatible keys, and keeps the legacy `profiles` scheduler-preset alias synchronized with `scheduler_presets`.

`custom_learn_stats.json` remains the source of truth for current-day and lifetime count/time aggregates. Its bounded `tag_breakdown` block jointly attributes active review seconds and answered-card counts to one semantic Topic/Item kind and one content tag, which avoids trying to reconstruct the pie-chart split from independent type and tag totals. Normal aggregate updates preserve this block instead of replacing the stats document. Today's card-count pies are also rebuilt from a bounded, grouped Anki revlog query and current card tags when the Statistics dialog renders; this recovers reviews completed before the joint block existed while keeping Anki's review history canonical. `backend/statistics.py` performs profile-locked, fsync-and-replace read/modify/write operations and transactionally mirrors the normalized aggregate shape to SQLite for recovery and compatibility. A corrupt canonical file falls back to the last committed mirror.

SQLite additionally owns the append-across-days trend data that the aggregate file never represented: `stats_daily_history` stores one normalized count/time snapshot per logical scheduler day, and `reading_page_history` stores one constraint-checked row per unique PDF/EPUB card page and logical day. Its composite primary key makes repeated reader progress messages and restarts idempotent. Trend reads are bounded, zero-filled, normalized in the backend, and never issued as raw SQL by the Qt dialog.

`video_watch_history` stores observed playback seconds per video card and logical day. The video reader counts advancing playback in bounded samples, excludes pauses and large seeks, and flushes pending time under the captured profile and date. Statistics aggregates distinct cards and playback seconds by the selected period; a saved resume position is never treated as watched time.

## Browser bridge security

The companion talks to `127.0.0.1:8766` using bridge protocol 2:

1. a companion in the configured browser (Chrome/Chromium by default, or Firefox) performs a bodyless POST handshake, which preserves its browser-supplied origin even when privileged GET requests would omit it;
2. the bridge binds that origin for the Anki run and returns an ephemeral token;
3. every data request supplies the token and protocol headers;
4. the bridge enforces exact origin, request-size, path, and concurrent-handler limits.

Tokens reset when the bridge/profile stops or the configured Companion browser changes. Read-only bridge RPCs also use bodyless POSTs and are explicitly retry-safe; mutating POSTs are never repeated after an ambiguous connection failure. The extension retries one handshake after a `401`. Only loopback clients are trusted; Incremento exposes no remote listener. Source and generated `dist/` extension files must remain aligned.

Browser text capture uses `backend/browser_capture.py` for bounded semantic HTML sanitization, escaped source anchors, text-fragment links, and excerpt fingerprints. The existing authenticated add-content RPC accepts read-only `preview`, normal `create`, and explicitly requested `open_existing` capture actions. Capture metadata supplies a profile/session-bound token so a stale dialog cannot write into another profile. Preview uses inert sandboxed field rendering; it creates no note, deck, media, or provenance fields. Creation uses `ImportOperation` and registers `content_items.kind = browser_capture`, with its URL/excerpt fingerprint in `storage_key`, before optional priority/tree updates. Anki still owns the note/card. Duplicate checks verify bounded live identities and also compare up to 100 older source-matched notes; metadata itself is excluded from excerpt matching. Existing note types are never expanded by capture. Source metadata is used when already available, explicit URL mappings receive clickable anchors, and `frontend/browser_capture_source.py` renders legacy browser provenance during review without changing templates.

`backend/webpage_handoff.py` owns bounded, process-memory CAPTCHA handoffs. `frontend/webpage_dialog.py` creates a profile/generation-bound request after a blocked import, opens an inert loopback landing URL, and polls its result through a Qt timer. Companion observes that landing navigation, resolves its opaque identifier through the authenticated bridge, and opens the backend-selected source. A one-time optional site-access grant enables a read-only, main-frame verification watcher for that tab. The extension's session storage keeps the pending association across MV3 worker restarts. A verified HTML submission is consumed once by the original dialog, rendered offline with its captured options, and imported through the existing `addWebpageFunction`/journaled PDF manager. Only a successful same-profile import activates Anki and shows a non-modal success message. Browser/profile/dialog closure and the ten-minute expiry cannot create a late card. The unauthenticated landing page contains no request details; every handoff data RPC retains protocol-2 authorization.

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

Runtime dependency installation is always explicit. PyMuPDF is bounded to
`>=1.26,<2`. `backend/deps.py` selects a real interpreter matching Anki's Python
version and CPU architecture, installs a wheel in a temporary folder, and checks
its native import before replacing the current installation. Runtime packages
live under `.dependencies/pymupdf/<runtime-tag>/`, outside profile data and release
inputs. The composition root activates that folder before readers use it; it
never launches the Anki executable as Python. yt-dlp is never silently installed
into Anki's Python environment.
