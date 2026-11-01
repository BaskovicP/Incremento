# Incremento Shared Folder Sync C1 Plan

Status: Proposed implementation plan for an opt-in desktop reader sync feature.

Use a user-selected cloud-synced folder to exchange immutable Incremento records and managed document versions. Keep each computer's live SQLite database local. Detect changes by comparing a normalized view of saved records with a persisted synchronization baseline. Use snapshots to initialize another computer and recover shared state; publish only changed records for everyday synchronization.

The initial release supports two desktop computers using the same Anki collection. Both may remain open and work offline. Independent changes combine automatically; competing changes to the same record remain available for resolution. Delivery depends on the user's cloud client. Android, hosted services, and general Incremento state synchronization are separate work.

## C1 system context

This follows the [C4 system context model](https://c4model.com/diagrams/system-context): people, Incremento, and the external systems it depends on. Local databases and individual sync modules are implementation details below C1.

![C4 Level 1 context for Incremento shared folder sync](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/docs/architecture/shared-folder-sync-c1.png>)

The [editable SVG](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/docs/architecture/shared-folder-sync-c1.svg>) contains the same baseline system context. Logical comparison is an internal Incremento responsibility, not another external system. The scheduling reference experiment below adds no production relationship to this diagram.

Incremento does not sign in to a cloud provider. The provider's desktop client handles transport. AnkiWeb remains responsible for Anki data; the two channels can finish at different times. A completed Anki sync is not proof that an Incremento package has arrived. See [Anki synchronization](https://docs.ankiweb.net/manual/syncing).

## Initial scope

Snapshots and everyday records use the same explicit allowlist. A setup snapshot must not quietly clone excluded state.

| Shared object | Revision boundary and behavior |
| --- | --- |
| Priority | One value per verified Anki card. Unrelated cards combine automatically; competing values for one card require resolution. Pairing verifies that both installations interpret priority direction consistently. |
| Reader bookmark | One bookmark ID, including its label, comment and location. Independent additions survive. Preserve IDs and existing normalization rules. |
| Reading position | One position per device and document version. Preserve each device's position and offer continuation from the other device. Never infer progress by taking the maximum page number or jump an active reader automatically. |
| Managed PDF or EPUB state | One coherent document record containing document identity, managed file hash, associated annotation state and required portable metadata. Bookmarks and reading positions remain separate records. |

For this release, record-level synchronization does not mean merging individual annotations inside one document. Concurrent annotation edits to the same document preserve two document revisions. Different documents, bookmarks and priorities continue synchronizing independently.

Writing, knowledge-tree changes, scheduler presets, statistics, video downloads and supplemental topic/custom scheduling state remain local in this release. The UI and manual must identify this as **Desktop Reader Sync**, with the supported data listed before pairing. Users must not infer that A-factors or custom scheduling rules follow them between computers. Scheduling requires a separate cross-store contract before advertising full Incremento sync.

Recovery journals, pending imports, extraction drafts, browser profiles, machine paths, credentials, diagnostics, caches and private MCP histories never enter the exchange. Existing Full Backup remains the separate tool for recovering a complete profile.

## Architectural decisions

1. **Retain local storage and existing readers.** Add synchronization metadata and thin domain adapters around current persistence helpers. Do not relocate the live profile folder or place its database, WAL or SHM files in cloud storage.
2. **Use portable identity.** Bind an Anki profile to a library UUID; allocate a fresh device UUID for each installation. Reuse stable content/bookmark IDs where available. Keep exact Anki card/note bindings as references. Profile names, filenames and matching hashes do not establish identity.
3. **Publish immutable revisions.** A record carries its library, type, object ID, revision ID, parent revision IDs, bounded complete payload or deletion marker, and required file hashes. Timestamps are descriptive. A resolved conflict references all heads it resolves.
4. **Detect edits by logical state comparison.** Existing features continue saving through their owning persistence helpers. A background scan compares complete normalized records with a persisted baseline. It durably queues detected revisions and advances only their captured baseline values in the same SQLite transaction. Individual UI, import and MCP writers do not need to emit sync events.
5. **Treat the folder as eventually delivered storage.** Unique names prevent competing writers from overwriting a shared current-state file. Directory listings, publication order and local atomic rename do not prove remote completeness.
6. **Apply through domain adapters.** Validate incoming data, stage resources, recheck live record fingerprints and unsaved editor state, then commit. Persist the corresponding baseline and inbox state with database effects so remote application does not echo back as a local change. Derived caches and reader copies do not create revisions.

## Logical state comparison

The baseline is Incremento's last captured or applied value for each shared object, together with its revision heads. It is not a claim that another computer has received that value. Pending publication and peer confirmation remain separate state.

1. **Read a coherent saved view.** Export the allowlisted records from a consistent SQLite read view, using existing normalization rules and stable IDs. Canonicalize ordering and values so internal timestamps, JSON key order and caches do not produce changes. Managed document records additionally require the coherent file/annotation capture described below.
2. **Compare against the baseline.** Detect new, changed and deliberately removed records. Infer removal only from a successful, complete scan of the authoritative record set. A missing file, missing Anki owner, failed query or partial scan is a pending/error condition, never an empty collection or automatic tombstone.
3. **Commit detected revisions.** Immediately before queueing each change, recheck both the baseline heads and the live record fingerprint. If either changed during the scan, retry the comparison. Save the revision, immutable publication payload and captured baseline together. A later local edit will differ from that baseline and be found on the next scan.
4. **Protect local work on receive.** Check the live record against its baseline inside the application commit boundary. Capture an unscanned local edit before integrating a remote branch. Stage incoming files without advancing the baseline; recheck after staging and retry or preserve a conflict if local work intervened.
5. **Avoid feedback loops.** Apply remote database state, its baseline and inbox outcome together. Document file adoption uses a recoverable local operation to finish the same logical transition. A restart either completes that transition or leaves the previous version usable; it does not announce an unfinished transition as applied.

Scans run after profile setup, periodically while open and on **Sync now**. A crash before a scan leaves the saved data for the next scan to discover. A crash after a queue commit leaves a durable pending package. This preserves the application's saved-state durability without wiring every save path into an event log.

This is state synchronization: intermediate keystrokes or changes that return to the same saved value between scans are not an action history. Review events, statistics counters and one-time rule consumption remain outside this mechanism. Slow scans stay off the UI thread and must be bounded; failed scans do not advance the baseline.

## Exchange layout

All exchange files live outside the add-on and runtime profile directories. Local queues, inbox state and device identity use profile-aware paths owned by the existing path service.

```text
chosen_folder/
  incremento-sync/
    <library-id>/
      library.json
      snapshots/<snapshot-id>.zip
      changes/<package-id>.json
      blobs/<sha256>
      receipts/<device-id>/<receipt-id>.json
```

`library.json` is an immutable initial descriptor containing the library identity and format contract. Change packages can batch small revisions, but each record remains independently identifiable. Blobs are immutable byte sequences named by hash. Receipts acknowledge specific packages after durable processing and distinguish applied records from pending dependencies or conflicts.

There is no authoritative mutable `latest` file, global timestamp cursor, or distributed lease. Presence warnings may follow later; correctness must work when both computers were offline.

The publisher stages and validates a package before exposing its final name. It copies required blobs before publishing references, while the receiver still tolerates the opposite arrival order. Ignore temporary files and deduplicate by validated identity and content. A provider-created conflicted copy with different bytes is quarantined rather than guessed into the protocol.

## Setup and recovery snapshots

The first computer explicitly initializes a library after a verified backup. Run logical comparison first so saved shared state has corresponding revisions. Capture the allowlisted records, their current revision heads and required ancestry anchors, then bundle the referenced document files into an immutable setup snapshot. Recheck the captured records and document fingerprints; a concurrent change must cause a retry or a clearly pending capture, not a snapshot whose contents disagree with its declared revisions.

Reuse the existing SQLite backup helper to obtain a consistent database view before exporting those records. Serialize shared records with the same encoding and validators used for ordinary change packages. Do not distribute or install an unrestricted runtime database. SQLite's [backup API](https://www.sqlite.org/backup.html) guarantees a database copy; coordinating that view with document files remains Incremento's responsibility.

A snapshot manifest contains the library and snapshot IDs, sync-format version, producer version, source database schema version, included revision identities, file hashes and sizes. A joining computer validates the archive and its declared contents before importing approved records into its own database. It then processes available change packages, including any not represented by the snapshot. Never skip packages because their filenames or timestamps appear older than the snapshot.

Setup behavior is explicit:

- The second computer first obtains the corresponding Anki collection through normal Anki sync. Only exact referenced identities are checked; setup does not add fields to note types.
- If it already has relevant Incremento work, preserve that work and stage it for comparison. Missing shared ancestry produces a reconciliation choice, never an automatic overwrite or filename-based match.
- A missing card or document dependency keeps the incoming record pending. Arrival before AnkiWeb is not evidence that the record should be deleted.
- Device identity, local queues, receipts and recovery journals are never cloned from the first computer.

For recovery, a replacement computer can import a retained snapshot and replay available revisions. Restoring an earlier object's contents in an active library creates a new revision after reading current known heads. It must not reset the library's history or erase pending edits. A complete Anki/profile restore remains a separate maintenance flow and requires library revalidation before sync resumes.

## Everyday synchronization

1. Let existing features save normally. At the next scan, compare their saved state with the baseline and queue the changed records. Frequent position updates naturally coalesce between scans. An unstable document remains pending until a coherent file/annotation state can be captured.
2. Publish immutable record packages and required blobs in the background. A failed publication remains queued; repeating it is harmless.
3. Discover available packages on profile open, on **Sync now**, and periodically while the profile is open. Watcher events are optional hints. Use bounded background scans and a durable inbox, not a high-water timestamp that could skip delayed files.
4. Validate library, format, size, identities, parents and resources. Missing parents or resources remain pending and are retried. Unsupported future formats pause that library's exchange while preserving local work.
5. Compare revision ancestry and apply through the existing owning service. Recheck local changes made during download before committing. Store inbox processing state with the corresponding database effects; use recoverable staging for filesystem effects.
6. Send an explicit receipt describing processing outcomes. Close-time publication is best effort; persisted queues continue on the next launch. Anki does not have to close for ordinary sync.

Transport disappearance is not a user deletion. A deletion is an explicit versioned record. Automatic shared-file deletion, history compaction and pruning are outside the initial release; retain revisions and referenced resources. Show storage growth and a configurable warning threshold. This trades storage for straightforward recovery during the pilot.

## Conflicts and document safety

| Incoming change | Action |
| --- | --- |
| A descendant of the current record, with no pending local edit | Apply after dependency checks. |
| An already processed revision or an ancestor | Do not reapply or roll back. |
| Independent objects | Apply both. |
| Equivalent content on parallel revisions | Retain ancestry without asking the user; the next edit references all equivalent heads. |
| Different content on parallel revisions | Retain both branches and show one object-level conflict. Keep the current local display until resolution. |
| Concurrent edit and deletion | Preserve both intents for resolution. |
| Missing ancestry, file or Anki owner | Wait and explain the pending dependency. |

Resolving a conflict publishes a new revision referencing the competing heads; choosing one version does not destroy the other history. For a document conflict, provide two recoverable document versions, not an entire-profile choice.

While a conflict is unresolved, an ordinary local edit extends the displayed branch; baseline comparison must not implicitly accept or discard the other branch. Referencing all competing heads requires explicit resolution, except for the equivalent-content case above.

PDF capture must bind the exact managed bytes, annotation rows and portable baseline metadata to one verified content fingerprint. It waits for pending saves and existing annotation interchange to finish, validates the captured state again, and retries if work changed during capture. File modification times may schedule a recheck but do not establish content identity or revision order. EPUB capture follows the corresponding file/highlight consistency rule. Incomplete imports are not published.

Keep current native PDF interchange; do not introduce an annotation-overlay redesign or general PDF merge in this project. Transport never copies another computer's original-file path or directly writes its linked original. The local annotation adapter must preserve local link configuration and verify baseline handling before allowing existing interchange to run after remote adoption. If this cannot be demonstrated safely, document interchange blocks release rather than being silently bypassed.

Incoming document adoption stages and verifies the new file, retains the previous version and uses a recoverable commit with its annotation state. Defer adoption while a local editor is dirty or a document writer is active; do not replace underneath it. Another record may continue syncing. Reader caches are regenerated locally.

## Minimal implementation boundaries

| Existing boundary | Required change |
| --- | --- |
| [Database and schema](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/db_schema.py>) | Add ordered migrations for normalized baseline values/fingerprints, revision heads/history, durable publication/inbox state and conflicts. Queue captured revisions and their baselines atomically. Keep schema rollback tests. |
| [Priorities](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/priority_manager.py>), [bookmarks](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/reader_bookmarks.py>) and existing reader persistence | Add normalized export and guarded apply adapters. Inventory all durable fields and saving behavior, including UI, batch, MCP and imports, to prove the exported view includes their results. Avoid per-writer event hooks. |
| [Snapshot helper](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/export_bundle.py>) and [PDF interchange](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/pdf_annotations.py>) | Reuse validated database copying, document validation and staging. Add allowlisted snapshot export and coherent document capture/adoption. Leave local import journals outside the wire format. |
| [Paths](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/paths.py>), [configuration](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/config_service.py>) and profile lifecycle | Persist per-profile pairing and local queues, capture profile/generation for workers, reject stale callbacks and cancel on profile switches. Scope settings explicitly; do not overwrite installation-wide presets. |
| Settings and reader UI | Add opt-in setup, **Sync now**, object conflict resolution and factual status. Expose pending work through the existing Activity Center. |

Keep revision rules testable without Anki or Qt. Add only the folder transport, local persistence and domain adapters needed by this scope. Shared input is untrusted: validate bounded JSON/archives, contained paths, no symlinks, hashes and existing content constraints; never execute transported SQL or code.

Status distinguishes **Saved locally**, **Published to sync folder**, **Waiting for files or Anki data**, **Conflict**, and **Confirmed applied on the other computer**. A local folder write is not cloud delivery. A receipt that records a pending dependency cannot produce the final confirmation. No status claims that excluded scheduling or workspace data is shared.

## Delivery plan

| Change | Deliverable | Exit condition |
| --- | --- | --- |
| 1 | Normalized record exports, baseline comparison, ancestry/conflict rules, durable-state inventory and a deterministic delayed-folder simulator. Prototype coherent PDF capture/adoption early. | Semantic changes are detected without changing every writer; normalization creates no false edits; reordered, duplicate and missing delivery preserve all revisions. The PDF adapter demonstrates safe baseline handling. |
| 2 | Atomic revision/baseline queue commits, guarded remote application, allowlisted snapshots and library pairing. | Crashes before or after scans preserve saved state; remote application creates no echo; setup imports only supported state and retains existing secondary-device work. |
| 3 | Folder publication/replay for priorities, bookmarks and positions, plus receipts and dependency waiting. | Two temporary desktop profiles combine independent work while open and recover after offline use. |
| 4 | Managed document groups, safe adoption, conflict resolution, recovery UX and a real two-computer pilot. | Interrupted and competing document edits remain recoverable; linked originals and local journals cannot be deleted or overwritten by remote recovery. |

Implement changes with the repository's test-first workflow and temporary profiles. Update architecture, manual and export documentation when the feature is implemented. Sync stays opt-in during the pilot. Do not advertise provider compatibility until the filesystem tests and a real two-computer run cover the claimed configuration.

## Release evidence

The release must demonstrate these observable outcomes:

1. A crash after a local save but before a scan rediscovers the saved change. A crash after a queue commit, publication, file replacement or inbox commit resumes without losing captured work or duplicating effects.
2. Desktop annotation changes and laptop priority/bookmark changes all survive; same-document competing changes retain both versions.
3. Packages and blobs arriving repeatedly or in any order eventually apply once their dependencies arrive. Missing or corrupt data never replaces the last usable state.
4. A concurrent local edit during remote staging becomes a branch or waits; it is never overwritten by the download.
5. A deleted cloud package is not interpreted as a user deletion. An explicit edit/delete conflict preserves the edit.
6. A setup/recovery snapshot plus delayed revisions reconstructs the supported state without importing another device's queues, tokens, histories or pending journals.
7. Missing Anki cards remain pending across a completed native sync; their absence cannot trigger import cleanup. Exact identities are rechecked before application.
8. Profile switches and shutdown cannot redirect queued work into another profile. Unsupported formats and hostile paths fail without changing user state.
9. Dirty open readers and existing native PDF interchange retain all comments, geometry and local link configuration across remote adoption and recovery.
10. Independent offline edits converge on the same revision sets and conflict status. Conflict resolution converges after its revision is delivered.
11. A local edit after a scan but before queueing or remote application is detected by the final fingerprint/baseline check and is never marked as already captured or overwritten.
12. A remote apply followed by another scan emits no duplicate revision. JSON ordering, incidental timestamps and cache changes emit no false revision.
13. Failed or incomplete exports, missing files, unsupported records and a corrupt baseline cannot produce mass deletion or reset the synchronization history.

## Separate scheduling reference experiment

Investigate a short reference stored on the Anki card, with the larger supplemental state carried as an immutable shared-folder payload. This is an isolated experiment, not an extension of the reader MVP allowlist or a prerequisite for its release. Use disposable profiles and a separate experimental library.

The proposed sequence is:

1. Prepare and durably retain a uniquely identified supplemental state payload before installing its reference on the card. Include the Anki identity, relevant review identity and expected final scheduling context so an unrelated later card operation can be detected.
2. Update the final Anki schedule and the short state reference in the same supported card update, merged into the existing Answer Card undo step. Preserve unrelated custom-data keys. A failure must restore both the schedule and the reference through the owned Anki operation.
3. Publish the immutable payload through the shared folder. Repeated publication uses the same identity and contents.
4. After native Anki sync, read the reference from the actual current card. Load that exact payload and validate its identity and scheduling context before using it. A missing payload, absent reference or changed context leaves the dependent topic operation pending or explicitly unsupported; it must not silently reuse stale local state.

Anki's [card sync representation](https://github.com/ankitects/anki/blob/main/rslib/src/sync/collection/chunks.rs) includes scheduling fields and card data in one record. The experiment tests whether that can bind the selected schedule to its supplemental state across the two delivery channels. It does not change Anki's rules for choosing between concurrent card updates.

Anki currently limits all serialized card custom data to [100 bytes](https://github.com/ankitects/anki/blob/main/rslib/src/storage/card/data.rs). Prove the reference fits alongside existing revisit, SuperMemo and third-party data; never evict their keys or silently omit the reference. No new note-type fields are required by this experiment.

Exit evidence must cover crash points before/after the card update and payload publication, Undo/Redo, concurrent reviews, one-time rule consumption, manual rescheduling, restore/downgrade behavior and ordinary reviews made by clients without this experiment. An unchanged old reference after such a review must be detected as stale. Only a separate scheduling decision may promote the experiment to supported sync.

## Separate follow-up work

Topic/custom scheduling synchronization requires proof that supplemental state matches the actual Anki schedule, including Undo/Redo and one-time-rule consumption. It is not a generic merge of the topic table. Writing, knowledge-tree invariants, presets and statistics each need their own record contract before joining the allowlist.

Android and other mobile clients are separate projects. This plan introduces no AnkiDroid fork, Python embedding, mobile UI or mobile cloud-folder integration. The desktop format can be documented for future clients without committing this release to them.
