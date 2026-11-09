# Shared-folder reader sync: design note

Status: proposal for review, before any code (issue #16).
Scope: the desktop reader MVP drawn in `shared-folder-sync-c1.svg`.

## 1. Contract

- **Snapshots** initialize and recover shared reader state.
- **Everyday changes** come from logical comparison. Saved state is exported as normalized records and compared with a persisted baseline, and changed records become immutable revisions. No feature gains sync hooks: features keep saving to their current stores.
- **The exchange** is a dedicated folder synced by any provider. Incremento never signs in to a cloud service and never opens SQLite inside that folder.
- **Anki stays canonical** for cards, notes, decks, scheduling, revlog, sync and Undo/Redo. The exchange carries only Incremento-owned supplemental state, and never a value that AnkiWeb already carries (§7).
- **Out of scope until their contracts are agreed:**
  - topic scheduling (the scheduling reference stays a separate experiment);
  - writing;
  - knowledge-tree merging;
  - presets and configuration;
  - statistics.

  Android is outside this plan.
- **Incoming data is not applied automatically** until the scenarios in §9 pass.

## 2. What syncs and what stays local

Classified against schema version 24 (`master` at `e6e0f0c`). A test will fail when a new table or column is not classified, so later migrations can't silently enter or leave the exchange.

**MVP: synced as records**

| Family | Tables | Record key | Synced fields |
|---|---|---|---|
| `priority` | `priorities` | card ref | `priority` |
| `reader_bookmark` | `reader_bookmarks` | `id` (UUID) | card ref, `reader_type`, `label`, `comment_text`, `location_json` |
| `reading_position` | `pdf_progress`, `epub_progress`, `video_progress`, `web_progress` | card ref + reader | positions and read markers (`page`, `scroll_ratio`, `read_page`, `read_anchor_json`, `section_index`, `read_section_index`, `is_finished`, `position`, `url`, media position) |
| `annotation` | `pdf_highlights`, `epub_highlights` | card ref + `id` | all columns except the device-local PDF interchange state |
| `document` | `content_items` + the managed PDF/EPUB file | `content_id` | a content version: the file blob plus its interchange baseline (§6.1) |

**Stays local (never exported)**
- **Machinery:** `schema_migrations`, `import_journal`, `reconciliation_runs`, `pdf_annotation_sync` (per-device `document_id`, `source_path`, baseline).
- **Derived, rebuildable:** `document_index_state`, `*_text_index`, `*_fts*`, `note_ocr_index`.
- **History and statistics:** `reading_page_history`, `video_watch_history`, `topic_review_history`, `custom_schedule_review_history`, `stats`, `stats_daily_history`.
- **Per-day usage:** `pdf_daily_limit_usage`, `epub_daily_limit_usage`.
- **Browser and UI memory:** `browser_*`, `reviewer_recent_tags`.
- **Device display preferences:** PDF `zoom`, EPUB `font_scale`, `appearance_mode`.
- **Files and secrets:** linked-original absolute paths, credentials, browser profiles, `.dependencies/`, `db_checkpoints/`, diagnostics.

**Later (each needs its own contract)**
- `topic_schedule`, `topic_postpones`, `item_postpones`, `custom_schedule_rules`/`_rule_versions`.
- `knowledge_tree_nodes`, `knowledge_tree_postpone_presets`.
- `writing_progress`, `writing_word_stats`.
- `document_links`, `epub_connections`, `recording_links`, `*_card_sources`.
- `*_daily_limits`, `*_due_review_prompts`.
- `document_library_*`, `statistics_goals`, `reader_custom_colors`.
- Videos and other large local media.

Open question for review: should zoom, font scale and appearance follow the reader across devices, or stay per screen? The proposal keeps them local.

## 3. Identities

| Identity | Meaning |
|---|---|
| `library_id` | One shared library; a UUID created when sync is first enabled |
| `device_id` | One install × profile; a UUID |
| `device_epoch` | Raised on restore or re-setup, so sequence numbers are never reused (§8) |
| card ref | `card_id`, `note_id`, note GUID, and `uploaded_usn` (§7) |

Profile names, filenames and file hashes are never used as identities. Joining an existing library checks a sample of the library's card refs against the local collection, and refuses a folder that belongs to a different collection.

## 4. Records and revisions

A **family adapter** owns one family. It is pure, with no Qt, and receives the profile and connection explicitly:

```python
scan(conn)            -> iterator of (key, value)   # complete, or raises
read(conn, key)       -> value | None
write(conn, key, v)   # never commits; runs inside the caller's transaction
delete(conn, key)     # never commits
```

**Normalization:**
- canonical JSON (sorted keys, fixed float precision per field);
- allowlisted fields only;
- incidental timestamps and caches excluded.

A failed or partial scan raises. It never yields an empty set, and deletions are inferred only from a completed scan of that family.

**Revision:**

```
id        sha256 of the canonical encoding of the fields below
library, family, key
parents   revision ids ([] for a first value)
device, epoch, seq
value | tombstone
deps      { card: card ref, blobs: [sha256] }
format    sync-format version (separate from the schema version)
```

Order comes from ancestry, never from timestamps:
- An incoming revision that descends from the local head fast-forwards.
- One that the local head already descends from is ignored.
- Anything else is concurrent and goes to the family's merge policy (§5).

A resolution is a new revision whose parents are both heads, so competing history is kept.

**Local tables (one new migration):**

| Table | Purpose |
|---|---|
| `sync_meta` | library, device, epoch, format |
| `sync_baseline(family, key, revision_id, value_hash)` | "this value has been captured locally" |
| `sync_revisions` | known revisions and their parents |
| `sync_outbox` | captured, not yet published |
| `sync_inbox(revision_id, status, reason)` | `received` (validated, not yet applied), `pending_parent`, `pending_blob`, `pending_anki`, `applied`, `conflict`, `obsolete`, `rejected` |
| `sync_receipts(peer, epoch, max_seq)` | confirmed application of another device's revisions |
| `sync_conflicts` | open conflicts shown to the user |
| `sync_peers` | each peer's announced AnkiWeb state (usn, scm) |
| `sync_seen_packs` | packs already accepted or rejected, so each is read once |

They live in `incremento.db`, so capture and apply commit together with the data they describe.

## 5. Merge policies

| Family | Concurrent edits |
|---|---|
| `priority` | Conflict, unless the values are equal |
| `reading_position` | Conflict by default. Proposed option: resolve to the further read position, a semantic rule rather than a timestamp |
| `reader_bookmark` | Adds never conflict; edits to the same `id` conflict; edit vs delete keeps the edit and flags it |
| `annotation` | Reuse `pdf_annotations._merge` semantics: concurrent notes on the same passage are joined, and other divergence keeps both rows (`conflict-…` ids) |
| `document` | Concurrent content versions are both kept. No PDF merging |

**Equal values merge deterministically.** When concurrent heads hold the same value, every device computes the same merge revision from them: it uses the reserved device `~merge`, its id is a content hash, and it is never published. This is why a merge can't set off another round of merges between devices. Different values open a conflict that keeps the local value; its resolution is an ordinary published revision whose parents are all the heads.

Records of cards deleted in Anki are not tombstoned. Each device's own reconciliation removes them after AnkiWeb deletes the card. Removing a pack from the folder never deletes user content.

## 6. Capture, publication, apply

1. **Scan** in one read transaction (a consistent snapshot), hashing each record.
2. **Capture**, in a short `BEGIN IMMEDIATE` transaction, re-reading only the changed keys:
   - insert the revisions;
   - insert the outbox rows;
   - update the baseline.

   It all commits together. A crash before the scan leaves the change discoverable by the next scan. A crash after it leaves a pending outbox.
3. **Publish** from the outbox:
   - The pack is deterministic, so a retry produces the same file name.
   - It's written to a temporary name, renamed, then re-read and its hash verified.
   - Only then is the outbox row marked published.
4. **Fetch:** list the peers' packs and verify each pack's bytes against the hash in its name. A mismatch means "not arrived yet", not an error. Parsing is bounded and each family has a schema. Blobs are addressed only by hash, so no path from a package is ever used.
5. **Apply** each revision whose dependencies are present. In one `BEGIN IMMEDIATE` transaction:
   1. Read the live value. If it differs from the baseline, there is an unscanned local edit: capture it first, which makes the incoming revision concurrent.
   2. Fast-forward, ignore, or merge or record a conflict, using the family's `write`/`delete`.
   3. Set the baseline to the result, record the inbox outcome, and update the receipt.

   The baseline then equals the live value, so the next scan doesn't publish the received change back.
   - Files are downloaded and staged before the transaction, and checked again at commit.
   - Helpers that commit internally are not used on this path; adapters provide transaction-capable writes.

### 6.1 Documents (investigation of requirement 8)

Findings from `backend/pdf_annotations.py`:
- `_content_digest` hashes page content, images, forms and fonts, and deliberately excludes annotations. A PDF therefore has a content identity that annotation edits don't change.
- Interchange is already a three-way merge of `pdf_annotation_sync.baseline_json`, the SQLite rows and the native annotations of the managed PDF and any linked original:
  - A catalog stamp (`sha256(baseline_json)` under the per-device `document_id`) tells a PDF that reflects the baseline from a stale one.
  - The PDF is written and backed up first. SQLite then commits after re-checking that no row changed during file I/O (`retry_needed`).

Proposal:
- **Content versions and annotations travel separately.** A document version is the managed file blob together with its `content_digest`, `document_id` and `baseline_json`. Annotations travel as records.
  - The receiving device adopts the version by writing its own `pdf_annotation_sync` row from those values, with an empty `source_path` (linked originals are local).
  - Delivered annotation records then reach its PDF through the existing interchange, exactly as local edits do.
  - Edits made in an external PDF tool enter SQLite through the same interchange and are captured as records.
- **The PDF is re-shipped only when its content changes** (for example a replaced document). In that rare case concurrent versions are kept rather than merged.
- **Hazard this avoids.** Shipping a managed PDF *without* its baseline would let the receiver's first interchange see annotations deleted elsewhere as new, and resurrect them across all devices. The baseline and the matching stamp prevent that. A scenario in §9 covers it.
- **Crash safety** stays with the interchange's existing stamps and ordering. Applying an annotation record is a SQLite-only transaction. An interchange running at the same time already reports `retry_needed` instead of overwriting.
- **EPUB** files are immutable after import (`epub_extracted/` is derived), so an EPUB version is just its blob. Highlights are records.

This needs a prototype test with real PyMuPDF before it is relied on. It is the first thing to check after the foundations.

## 7. AnkiWeb and the exchange

The two channels deliver independently. Findings from Anki's sync code (`rslib/src/sync/collection/{start,chunks,finish}.rs`):
- Locally changed cards, notes and revlog rows carry `usn = -1`.
- On upload they receive the server usn of that sync. Afterwards the collection's usn is that server usn + 1.
- If both sides changed a card, the copy with the newer modification time wins (`add_or_update_card_if_newer`). Revlog rows from both sides are kept.
- A full upload or download fires `collection_will_temporarily_close` and reopens the collection with `after_full_sync=True` (`qt/aqt/sync.py`).

Verified against AnkiWeb with two collections (Anki 25.09):
- A card added locally has usn −1.
- After a normal sync it carries the server usn, and the collection's usn is that value + 1.
- Later full uploads continued the numbering (7 → 8) rather than restarting it. Only the first upload to a fresh account started at 0.
- Schema changes and full syncs change the collection's `scm`, so the rules below compare usns only within one `scm`.

Rules:
1. **One owner per fact.** The exchange never carries due dates, intervals, tags, suspension, `customData` (`incrv`), filtered-deck membership or revlog.
2. **Card refs:**
   - A revision whose card or GUID is absent is `pending_anki`. It is re-checked after every AnkiWeb sync and on profile open.
   - It never enters `recover_interrupted_imports` or reconciliation cleanup. Staged files stay outside the managed folders, and reconciliation skips anything referenced by a pending inbox row.
3. **Late or deleted:**
   - Each revision records the card's `uploaded_usn`, or `null` if the card had not been uploaded yet.
   - Each device publishes the server usn of its last completed AnkiWeb sync.
   - If the receiver's collection usn is greater than `uploaded_usn` and the card is still absent, the card was deleted: the revision becomes `obsolete` and is neither applied nor tombstoned.
   - Usns are compared only when the revision's collection `scm` equals the receiver's (and the sender's announced one). Across a schema change or full sync the revision keeps waiting instead, so a numbering that does not line up can never declare a card deleted.
   - If `uploaded_usn` is `null`, the receiver waits until the sender's published usn shows the upload happened.
4. **Full sync:**
   - After a reopen with `after_full_sync=True`, an idempotent re-anchor pass re-checks every card ref.
   - Records whose card vanished become `orphaned_by_full_sync`: kept for 30 days, never published as deletions, never cleaned up by reconciliation.
   - The pass needs no knowledge of the direction; after an upload it finds nothing.
5. **Order on desktop:**
   - **Profile open:** AnkiWeb sync, then fetch and apply, then retry `pending_anki`, then start services.
   - **During an AnkiWeb sync:** applying is paused.
   - **After every AnkiWeb sync:** publish the usn and retry pending revisions.
   - **Profile close:** capture and publish, then Anki's closing sync.
6. **For the later scheduling work: the revlog anchor.** A topic answer already stores its answer's revlog id. A revision of the topic state (A-factor and intervals) names that row as its *anchor*: `{revlog_id, ease, revlog_ivl}`. It uses none of the `customData` budget. I checked it against Anki 25.09, with single collections and with two collections synced through AnkiWeb (the single-collection facts will be pinned by a regression test, so a future Anki that changes them fails loudly):

   | Situation | What Anki does | What the anchor rules do |
   |---|---|---|
   | Undo | removes the answer's revlog row and reverts the card; Redo restores the **same** row id | the state's anchor is gone, so the state is an *orphan*; upstream's reconcile-on-Undo already reverts it locally |
   | Undo after an AnkiWeb sync | impossible: the undo stack is cleared by the sync | an anchored answer can only vanish *before* it syncs; a revision published in between waits on the receiver for a row that never comes |
   | Manual reschedule (Set Due Date) | adds its own row with `ease 0`, `type 4`; changes the card's due date (and interval with `!`) | no effect: only `ease > 0` rows are answers, exactly as on a single device |
   | A review from another client (AnkiDroid, plain Anki) | adds a later answer row | the local state is *stale* (Anki has a later answer), so the next topic answer must not trust it |
   | Both devices answer offline | AnkiWeb keeps both rows and the card with the newer modification, which is the later answer | the revision anchored at the latest answer that has arrived wins, on both devices, deterministically |
   | The topic's interval override | the revlog row keeps Anki's own interval; only the card holds the override | the card's interval cannot be used to verify the anchor; the anchor deliberately does not depend on it |

   The receiving rules:
   - **Applying.** A revision whose anchor row is absent waits (`pending_anki`). A row with that id but a different ease or interval is a mismatch (not the sender's answer) and is rejected.
   - **Using.** Before a topic answer, the local state is *fresh* if its anchor is the card's latest answer, *stale* if Anki has a later answer, and an *orphan* if its own answer is gone. A stale state falls back to Anki's interval for that answer, as designed earlier, and the new answer's revision supersedes it.
   - **Concurrent revisions** for one card resolve to the one anchored at the latest answer, without asking the user. The other stays in history.

   Corrections to what I wrote earlier: the rule does not need the card's own interval or due date, and a flag change did not bump the card's modification time in my run, so a flag change does not make an earlier answer win. A manual reschedule does bump it (it is what Anki kept in my concurrent test), but it never changes which *answer* is current.

   The rules are small pure functions with tests; they come with the topic-scheduling stage, which is not part of the reader-sync PRs. Not yet verified: wiring them into the engine's apply step, in particular that a revision made after an Undo supersedes the stuck one it descends from (by ancestry, as for any revision whose ancestor is still pending).

## 8. Exchange folder, setup, restore, retention

```
<folder>/IncrementoSync/v1/<library_id>/
  library.json
  devices/<device_id>/{device.json, lease.json, receipts.json}
  devices/<device_id>/packs/<epoch>-<seq>-<sha256>.pack
  blobs/<aa>/<sha256>
  snapshots/<device_id>/<id>/          allowlisted setup/recovery snapshots
```

- **Single writer per directory.** Only device X writes under `devices/X/`. Blobs are content-addressed, so concurrent writers produce identical bytes. Providers therefore have no reason to create conflicted copies.
- **The lease** only warns; it can't enforce exclusive ownership between offline devices.
- **Setup:**
  - The first device creates the library and a snapshot made through the same allowlist as §2. It is not a clone of the runtime database.
  - A joining device checks collection identity (§3): it samples up to 50 card references from the library's verified packs. A card present with another note GUID means another collection; no sampled card present means the collection hasn't synced with AnkiWeb yet. Either refuses the join with an explanation. It then captures its existing data as parentless revisions. Identical values merge silently; different values become conflicts. Its work is never discarded.
- **Restore and copied profiles** (Full Backup, Automatic Backups, or a database copied to another computer):
  - A small binding file in `user_files/<profile>/sync/`, which backups leave out, records which device identity this installation owns. A database that doesn't match it came from a backup or another computer, so the profile adopts a new device identity in the same library. Old sequence numbers are never reused, and two computers never share an identity.
  - Revisions captured under the old identity but never published are re-issued under the new one, with their children, baseline and conflicts following.
  - The old identity becomes an ordinary peer. Its later published work is received back and fast-forwards from the restored baseline, so a restore can't rewind shared history or let old packs overwrite newer work.
- **Progress announcement.** `device.json` is written after the packs. It states what the device has published (`published: {epoch, last_seq}`) and which of its packs it has deleted (`retired: {epoch, through}`).
- **Snapshots** (`devices/<id>/snapshots/`). Now and then each device writes its view of the whole library:
  - the current head revisions of every record (its baseline plus open conflict heads);
  - its receipts (the highest sequence it has integrated from each device, its own included).

  A snapshot is split into hash-named parts, and its manifest is written last, so a partly uploaded snapshot is never used. A device keeps only its latest snapshot.
- **Retention.** A device deletes its own packs only up to the lowest sequence that every listed device's *latest snapshot* records for it. Any one complete latest snapshot, plus the packs still present, therefore holds the full current state.
  - A device without a snapshot blocks retention.
  - Unseen devices become "inactive" after 90 days and stop blocking retention only after the user confirms.
- **Catching up after retention.** A device that lacks history some peer has retired (its receipt for that peer is below the peer's `retired.through`) loads a complete latest snapshot that covers the retired ranges, then reads the remaining packs.
- **Truncated parents.** A waiting revision may name a parent that only existed in a retired pack. When every peer's packs are present without gaps from `retired.through` to `published.last_seq`, a parent that is still unknown can no longer arrive. The revision is released, and ancestry treats it as concurrent with the current heads, which is what it is.
- **Blobs.** Blobs named by no remaining pack and no latest snapshot are swept by any device after a 30-day grace period. Sweeping is idempotent and deletes only content-addressed copies, never a user's file.

## 9. Demonstrations before automatic apply

Two disposable profiles syncing to one disposable AnkiWeb account and one local folder. Each scenario becomes an automated test plus a manual run on two real computers.

| # | Scenario | Expected |
|---|---|---|
| 1 | `updated_at`, JSON order, or a cache changes | no revision |
| 2 | A family's table fails mid-scan | no revision, no tombstone |
| 3 | Crash before capture, during capture, after capture, and during publication | edit rediscovered or pending; nothing lost or duplicated |
| 4 | Offline priority edits on both devices to different cards | both applied |
| 5 | The same card's priority changed on both devices | one conflict; resolution is a merge revision; history kept |
| 6 | Packs delivered reversed, twice, truncated, before their blobs, before their parents | pending, then applied once |
| 7 | Local edit not yet scanned when a remote change arrives | conflict, not an overwrite |
| 8 | Crash during apply | all or nothing; nothing re-published |
| 9 | Pack removed from the folder | nothing deleted |
| 10 | Revision before AnkiWeb delivers the card; interrupted-import recovery runs meanwhile | kept, applied after the AnkiWeb sync |
| 11 | Card deleted on one device | revision `obsolete` after the receiver's sync passes `uploaded_usn` |
| 12 | Forced full sync | re-anchor pass; nothing deleted |
| 13 | Profile switch mid-sync | stale callbacks dropped |
| 14 | Malformed packs: oversized, path traversal, unknown family or format | rejected and reported |
| 15 | Annotation deleted on A after the document was shipped; B adopts the document | the annotation stays deleted |
| 16 | Same PDF annotated on both devices; crash between the PDF write and the SQLite commit | both annotations kept; no duplicates |
| 17 | Old backup restored on one device | newer work elsewhere survives |
| 18 | Second computer joins with existing work | nothing discarded; differences become conflicts |

A developer script, `scripts/sync_e2e.py`, which comes with the code PRs, runs these scenarios against real AnkiWeb, with two Anki collections and a shared folder. Device B can run in the same process or in a second Python, for example Linux under WSL. It needs a disposable account, because the first sync replaces the account's collection:

```bash
INC_E2E_USER=... INC_E2E_PASS=... python scripts/sync_e2e.py two-devices --workdir /tmp/inc-e2e --overwrite-ankiweb
```

On 2026-11-06 (Anki 25.09.2): 15/15 checks with two collections on Windows, and 9/9 with device B on Linux under WSL. The runs cover a card's data arriving before the card, a card deleted before the other device synced, a conflict and its resolution, an annotated PDF, a reading position with a bookmark, and full syncs.

## 10. Staged PRs

1. This note.
2. Sync tables and identities: one migration with a rollback test. No behavior.
3. Family adapter contract and `priority`: scanner and crash-safe capture to an outbox. Covers scenarios 1–3, plus the classification test.
4. Folder exchange: packs, blobs, bounded validation, and a **dry-run** inbox that records what it would do. Covers 6, 9 and 14.
5. Apply and conflicts for `priority`, plus the two-profile harness. Covers 4, 5, 7, 8 and 13.
6. AnkiWeb coordination. Covers 10–12.
7. Bookmarks and reading positions.
8. Document versions and annotations (§6.1). Covers 15 and 16.
9. Setup, join, restore, retention, and a status line ("Synced · 2 waiting for AnkiWeb · 1 conflict"). Covers 17 and 18.

Each PR keeps the feature off by default until PR 5 passes on two real computers.

## 11. Questions for review

1. Reading position: conflict, or "further read wins"?
2. Zoom, font scale and appearance: local, as proposed, or synced?
3. Is §6.1 (content versions plus annotation records, with the interchange baseline travelling with the version) acceptable in place of whole-document units?
4. Should the session filtered deck be emptied before the closing AnkiWeb sync, so other devices don't receive cards held in it?
5. Default retention periods (30 days for orphans, 90 for inactive devices)?
