# Incremento performance audit

Date: 25 October 2026. Baseline commit: `6125c2ca3f4e21cdd52a861c765d3916bb838d28`. The working tree was clean at the start.

The largest opportunities are repeated whole-library work on the UI thread, quadratic storage/model algorithms, and duplicate persistence. Optimize those before small Python syntax changes or adding more threads. This handoff contains 24 prioritized findings: 10 P1, 12 P2 and 2 P3. This audit added only the report and supporting audit artifacts; it changed no shipped implementation or user runtime data.

Concurrent About-credit, documentation and localization edits were observed and preserved. Their source diff does not change the identified performance mechanisms. [The concurrent-change record](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/concurrent_changes.json>) lists the observed files; the inventory retains initial and completion hashes. Source line anchors and extension bundle sizes were rechecked against the completion snapshot.

Completion update, 26 October 2026: all 24 numbered findings have implementations and regression coverage. The completion pass starts from `6a371c732fc6c7d65bb4468fdb5853a2926ec097`, after the first performance batch. The completion results below supersede the original backlog and first-batch handoff. Original measurements, line anchors and inventories remain historical evidence.

## Completion results — all 24 findings

Every numbered finding is addressed. This means the audited mechanism has been removed or bounded with explicit lifecycle/resource controls; it does not mean every possible performance cost has disappeared. Native Anki scheduling, Answer Card Undo/Redo, profile isolation, import journals, SQLite durability and optional-FTS fallbacks remain covered. The audit's unmeasured profiling watchlist remains a watchlist, not a claim of another reproduced defect.

The table reports synthetic component measurements on macOS arm64, Python 3.14.5 / SQLite 3.53.2 and Node 25.6.0. Ordinary timings are medians of three runs. Cold EPUB lookup, native import, Qt construction and browser observer measurements identify their smaller sample sizes in the raw artifacts. Warm caches are explicitly identified. None of these ratios is a whole-application speed claim. Supported-Python CI on 3.12/3.13 is still a separate environment.

| ID | Implemented improvement | Before → after on the same workload |
| --- | --- | --- |
| F01 | Debounced background session counts, one classifier/pool snapshot, batched PDF targets | 10,000 cards / 20 tag rows: **1,125.1 → 59.5 ms**; 504 → 24 SQL reads; 42 → 1 classifier resolutions |
| F02 | Active-EPUB metadata snapshot and validated reverse section map | Cold last-section lookup in a 10 MB / 200-section book: **1,356.5 → 8.2 ms**; 201 → 1 JSON reads. Warm: 0 reads |
| F03 | Combined statistics totals and tag-attribution persistence | First batch: **97.0 → 55.8 ms** with 512 populated tags; 4 → 2 durable saves per review cycle |
| F04 | Background, generation-scoped PDF source index and question/answer payload reuse | 20 lookups / 4,000 PDFs: **59.7 → 11.1 ms including index construction**; warm lookups add 0.004 ms; 80,000 per-note loads avoided |
| F05 | Stable indexed FTS identities for replacement/deletion | First batch: 4,000-page replacement **814.0 → 126.5 ms**. Fresh insertion still has the documented 70 ms tradeoff |
| F06 | Iterative validation plus structural-change-only tree writes | First batch deep validation: 275.6 → 11.1 ms. Completion 4,000-node unchanged save: **10.81 → 5.54 ms**, 4,000 → 0 updated rows; leaf move updates 1 row |
| F07 | Cancellable, paged, read-only database inspection; compact Unicode offsets | 1,000 positions in 312,000 characters: **152.1 → 11.7 ms**. Each inspection page bounds cards, rows, text and elapsed work |
| F08 | PDF copy, cover, native fallback and indexing in the collection worker; prepared empty text retained | 200-page native import: longest sampled UI event-pump gap **63.1 → 13.8 ms**; UI pumps 0 → 14. One sample; not an import-throughput claim |
| F09 | One private bookmark accumulator, iterative deep traversal, folder ranges and selection prefix counts | First batch: 5,000 opaque IDs 2,065 → 3.7 ms. 1,000 counts over 10,000 bookmarks: **373.2 → 0.076 ms warm**; separate range construction 1.03 ms, selection-prefix setup excluded |
| F10 | Debounced/hidden-aware markdown preview and one ordered background save queue | Twenty edits of 105,000 characters: markdown parse work **142.1 → 6.9 ms**, 20 → 1 parses; hidden preview: 0 parses |
| F11 | Local Undo/Redo membership checks instead of repeated global history differences | First batch Python transition: **310.5 → 3.0 ms** at 4,000 cards. Newly measured real SQLite boundary: 2.74 ms / 12 queries for 10,000 revlog IDs |
| F12 | Compiled queries, streaming candidate batches, bounded top-result ranking, async current-document search | Same 1,200 ranked results / 12,000 pages: **129.1 → 104.1 ms**; peak Python allocation **7.18 → 0.61 MB**, 91.5% less |
| F13 | Section-scoped EPUB highlight reads and position-only progress updates | 20,000 saved highlights / 100 in current section: **23.75 → 0.103 ms**; 20,000 → 100 materialized rows |
| F14 | Shared exact-duplicate groups, lazy peer expansion, separate fuzzy edges | 800 same-origin documents: **61.1 → 13.6 ms**; 639,200 → 1,600 stored references; Python peak 37.6 → 5.87 MB |
| F15 | Batched branch/media projections and supplemental writes; background previews and native mutation operations | Shift 4,000 priorities: **341.8 → 16.0 ms**; 4,000 → 1 commits, 4,000 → 5 priority reads |
| F16 | Disconnect the Find observer around owned writes; idempotent marks; preserve PDF.js text changes | 1,000 spans plus one external update over 10 frames: **10 → 2 render callbacks**, **89.1 → 5.2 ms** highlight work; one headless-browser sample |
| F17 | Per-page cancellation plus time/page/output budgets and bounded/reaped external extractor | Cancel after page 2 of 1,000: **48.4 → 2.93 ms** return time; 1,000 → 2 loaded pages, documents closed in both cases |
| F18 | Bounded Qt construction, deferred bookmark folders, 100-row imports and 50-row PDF highlights | React SSR: closed 10,000-leaf folder **92.6 → 0.246 ms**; import rows **413.1 → 4.89 ms**. Qt 5,000 rows: 1 → 126 callbacks; see timing caveat below |
| F19 | Visible/prefetched thumbnails, debounced filters and 24 MiB derived-image LRU | Initial viewport / 2,000 covers: **918.0 → 4.11 ms** native decode work; 2,000 → 9 images; raster accounting 409.6 → 1.84 MB |
| F20 | Split non-React core, UI and lazy custom-language validation chunks | Static content-script graph **1,001,053 → 192,642 bytes**, 80.8% smaller; background 986,486 → 177,928; offscreen 950,623 → 142,059 |
| F21 | One media sample for both heartbeat protocols, live video collection and hidden-poll suspension | 1,000 visible ticks: **2.86 → 2.24 ms**, 2,000 → 0 warm DOM queries; same 2,000 protocol messages. Hidden periodic ticks emit 0; playback events still flush |
| F22 | One SuperMemo parent map and one batch of supplemental topic schedules | 256-topic native import: **119.7 → 97.6 ms**; 36,992 → 4,352 element-ID reads; 256 → 1 topic commits; journal durability retained |
| F23 | Defer six optional dialog modules; initialize SQLite outside the registry lock | **21.7 ms** isolated optional import group deferred to first use. Under a controlled 100 ms initializer stall, unrelated cached lookup **110.1 → 0.002 ms**; first schema open 6.98 → 6.69 ms |
| F24 | One normalized config/classifier snapshot per reviewer event | 100 events with 20 populated presets: **261.9 → 96.1 ms**, 300 → 100 config reads |

The Qt construction budget is cooperative: at most 40 rows per callback and a 5 ms elapsed-work target, checked between rows. In the recorded sample its worst callback fell from 28.8 to 22.1 ms, while total construction rose from 28.8 to 55.7 ms because it yields to the event loop. A single Qt allocation, garbage collection or paint/layout can exceed the target. The implementation does not promise a hard frame-time limit. React numbers measure server rendering of production JSX, not a browser DOM commit. Thumbnail byte counts are conservative cache accounting, not process RSS.

Search retains its previous candidate ordering/caps and exact phrase/prefix/repeated-term/Unicode ranking, including the LIKE fallback. Excerpt FTS was evaluated and not added: adopting token-only matching would change the existing substring candidate semantics, and new mirrors add write/migration costs. Streaming, cancellation, a request text/time budget and bounded result retention remove the audited amplification without that behavior change. Large requests fail explicitly on budgets rather than silently dropping candidates.

PDF extraction cancellation is cooperative between native page calls; it cannot interrupt a single non-cooperative native call. External `pdftotext` has a kill/reap boundary and output/time checks. QWebEngine webpage rendering stays UI-owned and asynchronous; managed copying, covers, Qt PDF fallback and text indexing run outside the UI thread. Writing close/card-switch/backup restoration waits for ordered saves and preserves the live editor on failure; profile teardown flushes the captured profile. No delayed-save policy was introduced for review statistics or import journals.

Knowledge-tree `updated_at` now means the last structural change to that row's parent, kind or sibling order. An unchanged save preserves the timestamp; changed rows update together transactionally. This deliberate timestamp meaning is documented in the architecture and protected by rollback/no-op tests.

The checkout also contains concurrent profile-startup preparation, diagnostics/localization and PDF focus-toolbar changes. They were preserved and tested with this working tree; they are not claimed as performance implementations from this pass. No real `user_files/` content was read or modified. Benchmarks and native/browser tests use disposable profiles and fixtures.

### Evidence, reproduction and hands-on checks

Current per-finding status, test mapping and source hashes are recorded in [completion results](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/completion_results.json>). Raw measurements are [metadata/tree](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/completion_measurements.json>), [CPU/SQLite](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/completion_cpu_measurements.json>), [native Qt/Anki](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/completion_native_measurements.json>), [extension](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/completion_extension_measurements.json>) and [Find observer](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/completion_browser_measurements.json>). First-batch raw results remain below.

Run from the repository root. These commands create and delete synthetic fixtures, including the 4,000-node tree; they do not alter your Anki collection. The native program uses an offscreen Qt application. The browser program requires the already-installed optional webpage browser component and uses an offline headless page; it never installs software or touches an existing browser tab.

```bash
.venv/bin/python performance_audit/2026-10-25/completion_benchmarks.py --output /tmp/incremento-completion-metadata.json
.venv/bin/python performance_audit/2026-10-25/completion_cpu_benchmarks.py --output /tmp/incremento-completion-cpu.json
QT_QPA_PLATFORM=offscreen .venv/bin/python performance_audit/2026-10-25/completion_native_benchmarks.py --output /tmp/incremento-completion-native.json
node performance_audit/2026-10-25/completion_extension_benchmarks.mjs /tmp/incremento-completion-extension.json
.venv/bin/python performance_audit/2026-10-25/completion_browser_benchmarks.py --output /tmp/incremento-completion-browser.json
```

For visual checks, use a disposable Anki profile and your own test documents. These steps demonstrate the changed interaction; use the commands above for comparable before/after numbers.

| Findings | Steps and expected result |
| --- | --- |
| F01 | Open Start Incremental Learning, add tag rows, and type rapidly in a Topic/Item filter. Counts update after a brief pause; switch Basic/Advanced and confirm the same counts. Close/reopen or switch profiles before a result returns; old results must not appear |
| F02/F13 | Open a long EPUB, jump to a late section, then scroll repeatedly. Find/highlights follow the current section; ordinary scroll updates do not rebuild a whole-book highlight list. Add/delete a highlight and verify its count refreshes |
| F03/F24 | Review tagged Topic and Item cards. Check statistics totals/time and the reviewer badge/buttons. Save changed Settings and review again; the next event must use the new setting |
| F04 | Review extracted cards linked to a PDF source. Flip question/answer repeatedly, then edit the source title/cover and review again. The cover is reused within a card and refreshes after source changes |
| F05/F17 | Use Reindex PDF text on a test library. Reindex an already indexed document; cancel during another long PDF. Previously committed text remains available after cancellation. Use the FTS tradeoff program below to compare first insertion and replacement |
| F06/F15 | Build a nested Knowledge Tree, save without editing, then move one leaf. Open branch study, subset review, priority tools and postpone preview. Results/selection stay correct while reads run in the background. Check native Undo after a postpone change |
| F07 | In Browser select test cards and open Incremento Database Entries. Use page navigation to reach later results; search for repeated text and step through matches. Very long values show an ellipsis. Close during loading; no stale result should reopen the dialog |
| F08 | Import a multi-page PDF through Companion; also import a webpage as PDF. Anki can continue processing UI events while copy/cover/index work runs. Verify a text-free PDF creates its card without a second extraction and that searchable PDFs appear in Search ALL |
| F09/F18 | Open Companion bookmark import with a large folder. Leave the folder closed, then expand it and use Previous/Next page. Selected totals cover the entire folder; import rows page by 100 and all selected entries remain included. In a PDF with many highlights, page through the 50-row list |
| F10 | Open a long writing card, type a burst with preview visible, then hide the preview and type again. Reopen the same card and verify live text/cursor/word progress. Switch cards or close and reopen after saving; text and backup behavior remain intact |
| F11 | Review several Topic/custom-schedule cards, Undo, Redo, then Undo and make another native edit that clears Redo. Check the same intervals and one-time-rule restoration; the benchmark supplies the large-history fixture |
| F12/F16 | Type a common phrase in PDF/EPUB Find and Current Document Search, then change it rapidly. Only the newest results should display. Navigate/rerender a PDF page while Find is active; markings settle without repeating their own redraws |
| F14/F19 | Open Document Bookshelf with many covers and same-origin copies. Filter duplicates, inspect peers, resize, and scroll to the middle/end. All visible tiles gain covers; offscreen tiles are deferred and duplicates retain direct-match semantics |
| F20/F21 | Reload the unpacked Companion extension and open a new synthetic video page. Progress remains correct for the largest active player, including a dynamically inserted/replaced player; hide the tab and verify final position/playback events still persist. Static graph bytes are measured by the extension program |
| F22 | Import a small SuperMemo fixture in a test profile, then reimport it. Verify parent titles/tree placement, topic schedules, cloze/media metadata and idempotency. The native benchmark creates the 256-topic scaling fixture automatically |
| F23 | Start a disposable profile, then open Statistics, Bookshelf, Search ALL and database inspection for the first time and again. Optional imports move to first use. The database benchmark separately measures cold/warm initialization and lock contention; it does not claim an end-to-end Anki startup percentage |

### Completion verification

The final performance-only source passed **4075 Python tests** with 61 warnings, **249 reader tests** and **236 Companion tests**, through the complete release gate. The shared checkout, including preserved concurrent edits, separately passed **4,090 Python tests**. Translation checks, compilation, Ruff, configured mypy, ESLint and all four mutation guards passed; seven deterministic repair cases passed, npm audit found zero vulnerabilities and pip reported no broken requirements. Both generated targets reproduced byte for byte. Every file in the performance-only add-on matches the staged source; runtime data, local metadata and development files are excluded.

The complete release gate, rebuilt-asset reproducibility, dependency audit, deterministic repair checks and final package hash are recorded in [completion checks](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/completion_checks.json>). This section refers to the final completion run; verification further below belongs to the historical audit/first batch.

## Scope and confidence

Every one of the 760 tracked files is accounted for in the inventory. The pass covered 721 ordinary text files, 12 generated/vendor JavaScript artifacts and 27 binary artifacts. It parsed 466 Python files and 172 authored JavaScript/MJS/JSX files without syntax errors. The authored code/web scope excluding tests contains 322 files and 143,974 lines, including development tooling.

Coverage combines whole-repository mechanical scanning with targeted caller/callee review. It is not a claim that every source line was manually inspected or that every workflow was profiled. Generated/minified code was inventoried and relevant static imports checked; owning source remains authoritative. Binary catalogs, icons and fixtures received inventory rather than runtime interpretation. Untracked dependencies, live profiles and `user_files/` were excluded.

Measured findings use synthetic fixtures and original production functions, with medians of three samples (five for the statistics/EPUB measurements). Some pure functions were compiled from their original AST definitions to omit Anki/Qt imports. The Undo experiment fakes its SQL boundary. Python measurements used Python 3.14.5, SQLite 3.53.2 and macOS arm64; JavaScript used Node 25.6.0. Recheck results on supported Anki Python 3.12/3.13 and Qt WebEngine before using them as product latency targets. These measurements are not end-to-end application speedups.

| Repository area | Tracked files |
| --- | ---: |
| .github | 3 |
| (root) | 19 |
| backend | 103 |
| chrome_extensions | 122 |
| frontend | 187 |
| locales | 46 |
| scripts | 13 |
| tests | 259 |
| web | 8 |

P1 means address early because the mechanism blocks a common interaction or shows substantial scaling cost. P2 means a workload-dependent improvement with a clear mechanism. P3 means profile first; the benefit is not established as material. Source-confirmed findings establish the work performed, while their actual user-visible delay remains workload-dependent.

## Reproduced costs

| Workload | Result | Interpretation |
| --- | --- | --- |
| Save 4,000 tree nodes | 273.804 ms chain; 11.167 ms star | Repeated ancestor validation dominates deep structure |
| Replace existing PDF index | 69.585 ms at 1,000 pages; 825.158 ms at 4,000 | FTS trigger deletion scans scale poorly |
| Free-study time and answer statistics | Four atomic writes; 3.675 to 99.331 ms across tag fixtures | Duplicate whole-document persistence grows with populated groups |
| Database result offset conversion | 46.537 ms at 2,000 matches; 629.371 ms at 8,000 | Repeated prefix encoding is quadratic when text and matches grow |
| Build 5,000 bookmarks | 2,061.890 ms opaque IDs; 6.499 ms numeric IDs | Object copying depends strongly on key shape and engine optimizations |
| Clear Redo after Undo with 4,000 tracked cards | 310.529 ms, excluding SQL | Repeated global set differences |
| Read 4,000 priorities | 139.593 ms helper loop; 1.300 ms bounded batches | Per-call path/connection work adds to per-row SQL |
| Search common PDF terms in 12,000 pages | 158.881 ms at limit 120; 505.815 ms at limit 1,200 | Outer oversampling magnifies full-text reranking |
| Exact-origin duplicates in 800 shelf entries | 639,200 stored peer references; 70.421 ms | Quadratic result representation |
| Parse 10 MB EPUB metadata | 6.766 ms per load | A section path loop repeats this load |

The raw samples, fixture sizes, query plans and source hashes are in [Python measurements](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/measurements.json>) and [bookmark measurements](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/bookmark_measurements.json>).

## Prioritized implementation backlog

| ID | Priority | Improvement | Evidence |
| --- | --- | --- | --- |
| F01 | P1 | Move session dialog counts and PDF targets off the UI thread | Source confirmed |
| F02 | P1 | Reuse EPUB metadata and a reverse section path map | Source confirmed and helper measured |
| F03 | P1 | Combine statistics updates within each review event | Measured production helpers |
| F04 | P1 | Stop scanning the PDF library for each reviewer source cover | Source confirmed |
| F05 | P1 | Address FTS maintenance scans during document replacement | Measured SQL and query plan |
| F06 | P1 | Make knowledge tree validation linear and persist only changed rows | Measured production storage API |
| F07 | P1 | Bound database inspection and avoid quadratic text highlighting | Measured pure helper and source confirmed |
| F08 | P1 | Keep empty PDF preparation from falling back to UI extraction | Source confirmed |
| F09 | P1 | Build the bookmark index in one pass | Measured JavaScript source model |
| F10 | P1 | Debounce full writing preview and serialize saves outside typing handlers | Source confirmed |
| F11 | P2 | Remove repeated global set differences in Undo tracking | Measured Python logic with SQL boundary fake |
| F12 | P2 | Reduce search candidate amplification and repeated tokenization | Measured query helpers and source confirmed |
| F13 | P2 | Make EPUB progress events update only position-dependent state | Source confirmed |
| F14 | P2 | Avoid materializing every peer in large duplicate groups | Measured pure source logic |
| F15 | P2 | Batch remaining branch and linked-media inspection paths | Source confirmed and shared helper measured |
| F16 | P2 | Prevent PDF Find highlighting from observing its own writes | High confidence source risk requiring browser validation |
| F17 | P2 | Add cancellation and resource budgets inside PDF extraction | Source confirmed |
| F18 | P2 | Bound Qt and React item creation after background reads | Source confirmed |
| F19 | P2 | Load bookshelf thumbnails for visible tiles with a byte budget | Source confirmed |
| F20 | P2 | Split extension runtime chunks by actual consumers | Measured artifact sizes and static import graph |
| F21 | P2 | Share media detection across heartbeat paths | Source confirmed |
| F22 | P2 | Index SuperMemo parents once and batch supplemental schedule writes | Source confirmed |
| F23 | P3 | Profile eager imports and first database use before changing startup | Profiling hypothesis |
| F24 | P3 | Reuse normalized config within each reviewer event | Measured normalization and source confirmed |

## Finding details

### F01 Move session dialog counts and PDF targets off the UI thread

**P1 — Source confirmed.** Open Start Incremental Learning, edit Topic or Item filters, or change eligible card states in a large collection.

_refresh_counts and _refresh_tag_count synchronously call helpers that find, sort and classify full candidate lists. Each real tag row clears the classification cache. textChanged signals run these scans immediately. The dialog constructor also calls _refresh_pdf_limit_targets, which loads a Card, Note and saved page for every PDF. The separate available-mix preview already uses background operations; it does not protect these count/target paths.

**Evidence and cost.** Cost grows with candidate cards and configured tag rows; the PDF target path adds per-document backend and SQLite calls. No live dialog latency was measured.

**Implementation direction.** Use a debounced, coalesced QueryOp request carrying the profile, collection, filters and one classifier. Reuse classification metadata within that request and load PDF titles/progress in batches. Show a loading state and discard closed, superseded or profile-switched results. Reuse LatestQuery where appropriate.

**Acceptance.** Typing a burst dispatches at most the active request and one newest pending request; UI signal handlers do no collection scan. Preserve Anki tag/subtag semantics, Basic/Advanced synchronization, branch scope and exact counts.

**Sources.** [frontend/learn_dialog.py:3578](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/learn_dialog.py:3578>), [frontend/learn_dialog.py:3553](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/learn_dialog.py:3553>), [frontend/learn_dialog.py:2984](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/learn_dialog.py:2984>), [backend/cards.py:254](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/cards.py:254>), [frontend/latest_query.py:17](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/latest_query.py:17>).

**Regression coverage.** `tests/test_learn_dialog.py`, `tests/test_learn_dialog_qt.py`, `tests/test_cards.py`, `tests/test_session_setup_model.py`, `tests/test_latest_query.py`.

### F02 Reuse EPUB metadata and a reverse section path map

**P1 — Source confirmed and helper measured.** Navigate or scroll a long EPUB, follow a local section link, or receive a WebEngine URL change.

_current_metadata reparses metadata.json through load_epub_metadata. That JSON includes every section body. _section_index_from_path loops over sections and calls get_epub_section_path for each candidate; that helper reparses the same JSON again. Looking up a late section therefore repeats a whole-book read/parse roughly once per preceding section. Progress/title updates also call _current_sections.

**Evidence and cost.** The original load_epub_metadata helper took a median 6.766 ms for a synthetic 10,007,930-byte, 200-section metadata file. A last-section path lookup can request about 201 parses. That multiplicative cost is established by the caller; an end-to-end lookup time is not claimed.

**Implementation direction.** Keep a bounded snapshot for the active document, keyed by captured profile, filename, metadata identity and sanitizer version. Build a validated path-to-section map once. Clear it on replacement, sanitization changes, document/profile switch and close. Preserve containment checks; never cache arbitrary path acceptance.

**Acceptance.** Resolving any section performs a constant number of metadata reads per document generation. Progress-only events reuse the snapshot. Cover stale replacement, malformed metadata, traversal and profile-switch cases.

**Sources.** [frontend/epub_dock.py:5588](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/epub_dock.py:5588>), [frontend/epub_dock.py:5884](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/epub_dock.py:5884>), [backend/epub_manager.py:727](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/epub_manager.py:727>), [backend/epub_manager.py:931](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/epub_manager.py:931>).

**Regression coverage.** `tests/test_epub_dock.py`, `tests/test_epub_security_integration.py`, `tests/test_epub_manager.py`, `tests/test_reader_links.py`.

### F03 Combine statistics updates within each review event

**P1 — Measured production helpers.** Reveal an answer and grade a card during ordinary free study, especially with many populated tag statistics.

Review-time attribution calls record_time_only and then record_tag_breakdown; answer attribution calls record and then record_tag_breakdown. Each independently loads, normalizes and rewrites the entire canonical JSON, fsyncs it, replaces it and mirrors aggregates/history to SQLite. StatsManager construction also reloads the file. These hooks run synchronously.

**Evidence and cost.** A synthetic time-plus-answer cycle performed four atomic file writes. Medians were 3.675 ms with one populated tag per group, 26.515 ms with 128, and 99.331 ms with 512. This includes two callbacks, not a single measured UI pause. The largest fixture was 79,024 bytes.

**Implementation direction.** Add one locked mutation per logical event that updates its legacy aggregate and joint tag breakdown together. Combine the two time writes at answer reveal and the two count writes at grading, retaining the separate event semantics. Avoid redundant normalization inside the same trusted transaction. Keep the canonical file and recovery mirror contract.

**Acceptance.** One durable canonical write per event, at most two for this complete free-study cycle; exact count/time/tag totals survive restart, concurrent mutations, malformed-file fallback and a failed mirror. Do not trade correctness for a delayed lossy flush.

**Sources.** [backend/review_time_tracker.py:142](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/review_time_tracker.py:142>), [backend/review_time_tracker.py:228](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/review_time_tracker.py:228>), [backend/statistics.py:811](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/statistics.py:811>), [backend/statistics.py:675](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/statistics.py:675>).

**Regression coverage.** `tests/test_statistics.py`, `tests/test_session.py`, `tests/test_stats_progress.py`, `tests/test_learning_statistics.py`.

### F04 Stop scanning the PDF library for each reviewer source cover

**P1 — Source confirmed.** Review an extracted card containing an inline PDF reference in a large PDF library.

Both question and answer hooks call _sync_reviewer_source_cover. Its payload resolver calls find_live_pdf_card_by_filename, which enumerates every PDF note and loads notes until an exact filename match is found. A missing or fuzzy match scans the whole library. The question-to-answer transition repeats that lookup for the same source.

**Evidence and cost.** Up to O(D) Note reads per hook for D PDF notes, plus source card/note reads. This is on the reviewer UI path; no live per-card timing was measured.

**Implementation direction.** Resolve a verified source card identity directly when available. Otherwise use a batched, collection-generation-scoped derived filename index with exact-match precedence and the existing unique-fuzzy fallback. Reuse the resolved payload between the two sides of one card and invalidate after relevant note/document changes.

**Acceptance.** For an unchanged source, question/answer rendering makes no full-library scan. Verify missing files, duplicate names, exact precedence, ambiguous fuzzy matches, replacement/deletion, Undo and profile switching.

**Sources.** [__init__.py:3392](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/__init__.py:3392>), [__init__.py:3479](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/__init__.py:3479>), [backend/pdf_manager.py:87](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/pdf_manager.py:87>).

**Regression coverage.** `tests/test_reviewer_source_cover.py`, `tests/test_pdf_manager.py`, `tests/test_note_metadata.py`.

### F05 Address FTS maintenance scans during document replacement

**P1 — Measured SQL and query plan.** Reindex or replace an already indexed PDF, EPUB or OCR document while FTS5 is available.

The FTS tables keep card/page/section identifiers UNINDEXED. Each base-row delete or update trigger deletes matching FTS rows using those columns. SQLite must scan the virtual table for each affected base row. Replacing P pages against N indexed rows can perform work proportional to P times N. A background worker avoids direct UI work but still holds a write transaction and consumes extraction/import capacity.

**Evidence and cost.** Replacing existing 500/1,000/2,000/4,000-page synthetic PDF indexes took 22.909/69.585/244.314/825.158 ms. EXPLAIN QUERY PLAN for the trigger-style delete returned SCAN pdf_text_fts VIRTUAL TABLE INDEX 0. This fixture used very short text, so deletion overhead is visible.

**Implementation direction.** Prototype stable base-row-to-FTS rowid mapping or a compatible external-content design so per-row maintenance addresses rowid directly. Rebuild mirrors in a new monotonic migration and update all insert/delete/update paths together. Preserve fallback without FTS5 and transactional migration rollback.

**Acceptance.** Measure replacement against a growing unrelated corpus as well as a growing document. Eliminate the per-page full virtual-table scan; preserve search results after insert, replace, delete, migration failure and FTS-unavailable startup.

**Sources.** [backend/db.py:407](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/db.py:407>), [backend/db.py:448](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/db.py:448>), [backend/db.py:463](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/db.py:463>), [backend/db.py:478](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/db.py:478>), [backend/search_indexer.py:52](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/search_indexer.py:52>).

**Regression coverage.** `tests/test_db.py`, `tests/test_db_schema.py`, `tests/test_search_indexer.py`, `tests/test_search_repository.py`, `tests/test_pdf_search_safety.py`.

### F06 Make knowledge tree validation linear and persist only changed rows

**P1 — Measured production storage API.** Save, move, insert or remove nodes in a large or deeply nested knowledge tree.

set_knowledge_tree_structure walks each node to the root with a new seen set, repeating shared ancestor work. It then upserts every surviving row, including unchanged nodes. Several structure helpers rebuild and save the whole tree for one change; repeated per-node operations multiply the cost.

**Evidence and cost.** A 4,000-node chain took 273.804 ms per save versus 11.167 ms for a star of the same size. Chain saves at 1,000/2,000/4,000 nodes took 19.880/75.832/273.804 ms. These are storage-API measurements; they do not imply that the current recursive UI can display a 4,000-level chain.

**Implementation direction.** Validate the complete parent graph once using iterative visitation states or memoized completed chains. Compute changed/deleted rows and affected sibling ordering, then write only those rows in one transaction. Batch multi-node operations at their owning boundary. Preserve created_at and meaningful updated_at semantics.

**Acceptance.** Cycle, missing-parent and duplicate rejection remain identical and atomic. Validation approaches O(N+E); changing one branch does not rewrite unrelated rows. Exercise wide, balanced and deep synthetic trees plus rollback.

**Sources.** [backend/db.py:4861](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/db.py:4861>), [backend/db.py:4896](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/db.py:4896>), [backend/knowledge_tree.py:204](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/knowledge_tree.py:204>), [frontend/knowledge_tree_dialog.py:1849](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/knowledge_tree_dialog.py:1849>).

**Regression coverage.** `tests/test_db.py`, `tests/test_knowledge_tree.py`, `tests/test_knowledge_tree_mind_map.py`.

### F07 Bound database inspection and avoid quadratic text highlighting

**P1 — Measured pure helper and source confirmed.** Open Incremento Database Entries for a large Browser selection, then search common text in a large result.

The action synchronously discovers tables, queries each matching card-reference column and fetches every returned value. _format_browser_database_entries scans the entire entries list again for each selected card. Each search keystroke builds a case-fold offset map for the entire text and creates selections for every match. text_index_to_qt_position repeatedly slices and UTF-16-encodes the whole prefix for both ends of each match; next/previous navigation rebuilds all selections too.

**Evidence and cost.** Offset conversion alone took 46.537 ms for 128,000 characters/2,000 matches, 165.883 ms for 256,000/4,000, and 629.371 ms for 512,000/8,000. This excludes case folding, SQL, formatting and Qt selection creation.

**Implementation direction.** Move discovery/lookup/formatting into a captured-profile cancellable read operation, with explicit selection, row and byte budgets and paging. Group entries by card once. Precompute UTF-16 offsets once or use a stable Qt-native search strategy, debounce queries and update only the active selection on navigation.

**Acceptance.** No uncapped table/materialization work in the action handler; formatting is O(entries + selected cards), and offset preparation is O(text + matches). Keep Unicode expansions, emoji/surrogate pairs and overlapping-match behavior correct; display truncation/paging explicitly.

**Sources.** [backend/db.py:241](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/db.py:241>), [__init__.py:2018](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/__init__.py:2018>), [__init__.py:2105](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/__init__.py:2105>), [frontend/database_entries_dialog.py:82](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/database_entries_dialog.py:82>), [frontend/database_entries_dialog.py:175](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/database_entries_dialog.py:175>).

**Regression coverage.** `tests/test_database_entries_dialog.py`, `tests/test_db.py`.

### F08 Keep empty PDF preparation from falling back to UI extraction

**P1 — Source confirmed.** Import a scanned or otherwise textless PDF from Companion, or create a PDF from an opened webpage.

_prepare_pdf_item_off_main records precomputed text only when the extracted list is truthy. extract_pdf_pages_text can return an empty list for a valid scan. The main-thread add_pdf_card path sees the missing value and runs extraction again, including Qt and a possible external pdftotext invocation. Webpage-created PDFs skip this preparation route and also reach extraction during main-thread creation. File copy, cover rendering and text-index insertion remain in that synchronous creation phase.

**Evidence and cost.** The source establishes duplicate extraction after a successful empty preparation and library/file-size-dependent work on the UI thread. No scan duration was measured.

**Implementation direction.** Represent preparation completion independently from whether text exists; carry an explicit empty list. Prepare text for rendered webpages before final collection creation. Move managed-file preparation and indexing work to the appropriate captured-profile workers/operations, with journaled paths and a minimal serialized Anki mutation phase.

**Acceptance.** A prepared empty PDF never invokes an extractor again in the UI phase. Cover direct PDF bytes, downloaded PDF, webpage render and preparation failure, with profile changes and crash-safe rollback. Preserve bridge authorization checks at collection access.

**Sources.** [backend/browser_bridge.py:824](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/browser_bridge.py:824>), [backend/browser_bridge.py:852](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/browser_bridge.py:852>), [backend/browser_bridge.py:1290](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/browser_bridge.py:1290>), [backend/pdf_manager.py:1275](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/pdf_manager.py:1275>), [backend/pdf_manager.py:835](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/pdf_manager.py:835>).

**Regression coverage.** `tests/test_browser_bridge.py`, `tests/test_pdf_manager.py`, `tests/test_operation_journal.py`, `tests/test_webpage_pdf_integration.py`.

### F09 Build the bookmark index in one pass

**P1 — Measured JavaScript source model.** Open Companion bookmark import with a large bookmark collection, particularly IDs that are opaque strings.

registerBookmark creates a new object with every previous item via object spread for every bookmark. buildBookmarkItems repeats this throughout the recursive walk. That is quadratic copying for general string keys. Folder rendering also recollects descendants, and closed details elements still mount their child tree; these are additional UI costs outside the model benchmark.

**Evidence and cost.** For 1,000/2,500/5,000 opaque IDs, buildBookmarkItems took 41.777/428.280/2,061.890 ms. Numeric-string IDs took 1.204/2.762/6.499 ms on the same Node/V8 runtime. The numeric optimization does not make the algorithm safe for other ID shapes; the fixture is illustrative, not a measurement of Firefox itself.

**Implementation direction.** Populate a fresh private accumulator once during initial tree construction, preserving the public immutability contract for a supplied input map. Build node/subtree indexes once per tree and mount expanded branches or a visible window. Keep immutable targeted updates for React state after construction.

**Acceptance.** Initial construction approaches O(B) for numeric and opaque IDs; input maps and nodes remain unchanged, duplicate handling/folder paths stay identical, and folder selection remains stable. Measure browser rendering separately.

**Sources.** [chrome_extensions/incremento_companion/src/bookmarks/bookmarkModel.js:59](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/chrome_extensions/incremento_companion/src/bookmarks/bookmarkModel.js:59>), [chrome_extensions/incremento_companion/src/bookmarks/bookmarkModel.js:82](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/chrome_extensions/incremento_companion/src/bookmarks/bookmarkModel.js:82>), [chrome_extensions/incremento_companion/src/bookmarks/components/BookmarkTree.jsx:47](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/chrome_extensions/incremento_companion/src/bookmarks/components/BookmarkTree.jsx:47>).

**Regression coverage.** `chrome_extensions/incremento_companion/tests/bookmarkModel.test.js`.

**Coordination.** Extension source changes require build:extension and the matching generated bundles.

### F10 Debounce full writing preview and serialize saves outside typing handlers

**P1 — Source confirmed.** Type in a long writing card or keep a large Markdown document open with preview hidden.

_on_editor_text_changed rebuilds the complete preview with setMarkdown and separately reads/counts the complete document on every change. Hiding the preview does not skip this work. A 180 ms autosave timer then reads/writes the whole document, checks backups, recounts words and writes supplemental state. A separate 220 ms state timer can repeat progress writes; flush also saves progress twice.

**Evidence and cost.** O(document length) preview/word processing per keystroke plus synchronous save/backup work on pauses. The existing autosave timer does not debounce the immediate preview conversion. No live typing latency was measured.

**Implementation direction.** Keep caret/status updates immediate, debounce preview and word-count snapshots, and skip preview parsing while hidden. Capture immutable text/profile/card generations for an ordered background save queue; retain a safe close/profile-switch flush and visible failure handling. Persist unchanged editor state only when dirty.

**Acceptance.** A burst of edits causes one newest preview/count task and ordered durable replacements; hidden preview causes no Markdown rebuild. Preserve unsaved text, per-card word baselines, backup tiers, session counters and profile isolation under slow/failing saves.

**Sources.** [frontend/writing_dock.py:880](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/writing_dock.py:880>), [frontend/writing_dock.py:300](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/writing_dock.py:300>), [frontend/writing_dock.py:574](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/writing_dock.py:574>), [frontend/writing_dock.py:597](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/writing_dock.py:597>), [backend/writing_manager.py:258](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/writing_manager.py:258>).

**Regression coverage.** `tests/test_writing_dock.py`, `tests/test_writing_manager.py`, `tests/test_writing_workspace_qt.py`.

### F11 Remove repeated global set differences in Undo tracking

**P2 — Measured Python logic with SQL boundary fake.** After many topic/custom-schedule answers in one profile session, Undo an answer and then perform an operation that clears Redo.

ReviewRevlogTracker.transitions computes set(existing) minus each card snapshot inside the restored_undone comprehension. The condition runs when an undone candidate exists and can_redo is false. With one tracked answer per card, it repeatedly copies almost the whole global set, yielding O(cards times tracked revlogs). Normal transition checks also query all tracked session revlogs.

**Evidence and cost.** The original tracker logic took 18.310/77.482/310.529 ms for 1,000/2,000/4,000 tracked cards in the Redo-clearing case. The benchmark fakes only the revlog lookup; SQL and UI costs are excluded.

**Implementation direction.** Test only the relevant intersection of a card's linked IDs and the undone set when identifying restored candidates, or otherwise precompute differences once. Investigate reducing ordinary full-session polling only with a verified native Undo lifecycle signal. Do not arbitrarily evict history that Anki can still undo.

**Acceptance.** Preserve exact transitions for genuine Undo/Redo, forget/delete, sync, cleared Redo, manual topic edits, recreated rule revisions and profile resets. The specific Redo-clearing computation scales approximately linearly.

**Sources.** [backend/answer_schedule.py:208](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/answer_schedule.py:208>), [backend/answer_schedule.py:229](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/answer_schedule.py:229>), [__init__.py:7760](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/__init__.py:7760>).

**Regression coverage.** `tests/test_topic_scheduler.py`, `tests/test_custom_schedule.py`, `tests/test_topic_scheduler_anki_integration.py`.

### F12 Reduce search candidate amplification and repeated tokenization

**P2 — Measured query helpers and source confirmed.** Search common terms across a large document/highlight library, or type in current-document Find.

Search ALL oversamples requested results by 10 to remove stale/unavailable owners; the DB layer then multiplies the limit by 25. A 120-result PDF category can therefore request 30,000 full-text candidates. Each candidate reparses the query and tokenizes its full text before Python sorting. Highlight/source excerpt search always uses a leading-wildcard lower LIKE scan. Current PDF/EPUB Find and the current-document results dialog call search synchronously on text changes.

**Evidence and cost.** With 12,000 pages of about 1,380 characters, the PDF helper took 158.881 ms for limit 120 and 505.815 ms for limit 1,200, which is the outer oversampling request. The excerpt query plan scanned the card/page index. A LIMIT bounds returned rows, not scanned rows or transferred text bytes.

**Implementation direction.** Compile query terms once per request, reduce redundant text work and use incremental candidate batches with cancellation and explicit work/byte budgets. Evaluate proper text indexes for excerpts with the required fallback. Move current-document searches to debounced latest-request workers. Preserve ranking, prefix, phrase and Unicode semantics rather than just lowering caps.

**Acceptance.** Profile common/rare/no-hit terms and stale-owner cases; preserve result order and coverage. New typing must not wait behind obsolete ranking work. Avoid uncapped full-text materialization before cancellation checks.

**Sources.** [frontend/search_all_results.py:125](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/search_all_results.py:125>), [backend/db.py:3672](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/db.py:3672>), [backend/db.py:3463](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/db.py:3463>), [backend/search_repository.py:131](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/search_repository.py:131>), [frontend/current_document_search_dialog.py:109](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/current_document_search_dialog.py:109>), [frontend/pdf_dock.py:2616](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/pdf_dock.py:2616>), [frontend/epub_dock.py:4868](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/epub_dock.py:4868>).

**Regression coverage.** `tests/test_search_repository.py`, `tests/test_search_all_results.py`, `tests/test_current_document_search_dialog.py`, `tests/test_pdf_dock.py`, `tests/test_epub_dock.py`.

### F13 Make EPUB progress events update only position-dependent state

**P2 — Source confirmed.** Scroll or turn pages in an EPUB containing many saved highlights and source cards.

_record_progress saves state, recomputes daily limits, updates the toolbar and rebuilds the sources panel. _current_section_highlights loads highlights for the whole book and filters in Python; _on_load_finished repeats the same pattern. Counts, bookmarks and HTML panel rendering are refreshed even when only the scroll ratio changed, including when the sources panel is hidden.

**Evidence and cost.** O(all book highlights) reads/allocation per progress update, plus SQL aggregates and HTML reconstruction. The bridge has a 140 ms debounce, which reduces frequency but does not reduce each update's work.

**Implementation direction.** Query highlights for the active section using the existing card/section index. Cache section counts and panel data per document generation; invalidate on highlight/source/bookmark mutations. Separate position persistence from section-change and visible-panel updates.

**Acceptance.** A same-section scroll does not reload all highlights or rebuild hidden panels. Preserve daily-limit enforcement, unique-page counts, bookmark state and live updates shared with reference panes.

**Sources.** [frontend/epub_dock.py:5837](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/epub_dock.py:5837>), [frontend/epub_dock.py:5288](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/epub_dock.py:5288>), [frontend/epub_dock.py:5770](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/epub_dock.py:5770>), [backend/epub_highlights.py:11](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/epub_highlights.py:11>).

**Regression coverage.** `tests/test_epub_dock.py`, `tests/test_epub_highlights.py`, `tests/test_reader_controls_qt.py`, `tests/test_reader_links.py`.

**Coordination.** Coordinate with F02 so metadata and panel caches share correct invalidation.

### F14 Avoid materializing every peer in large duplicate groups

**P2 — Measured pure source logic.** Open the Document Bookshelf with many imported copies sharing the same normalized source filename.

_bookshelf_duplicate_matches caps title/feature buckets but not exact_origins. For an origin group of D entries it enumerates every pair, stores reciprocal sets, then builds a full peer tuple for every entry. Subsequent duplicate-entry/group consumers reuse this expanded graph rather than a compact group representation.

**Evidence and cost.** 200/400/800 same-origin documents produced 39,800/159,600/639,200 stored peer references and took 6.435/21.373/70.421 ms. Memory growth is established by reference counts; peak RSS was not measured.

**Implementation direction.** Represent exact-equivalence groups compactly and resolve selected peers lazily. Keep fuzzy edges separate because fuzzy similarity is not transitive; connected components alone cannot replace direct-match semantics. Reuse one computed match model within each shelf snapshot.

**Acceptance.** Exact duplicate storage approaches O(D) per equivalence group while direct fuzzy matches and delete-confirmation attachment counts remain correct. Include groups above existing bucket caps and titles with conflicting numeric parts.

**Sources.** [frontend/pdf_bookshelf.py:555](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/pdf_bookshelf.py:555>), [frontend/pdf_bookshelf.py:617](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/pdf_bookshelf.py:617>), [frontend/pdf_bookshelf.py:725](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/pdf_bookshelf.py:725>).

**Regression coverage.** `tests/test_pdf_bookshelf.py`.

### F15 Batch remaining branch and linked-media inspection paths

**P2 — Source confirmed and shared helper measured.** Open branch subset review, simulate/apply branch postponement, change branch priorities, or inspect a large media Review All selection.

Subset review and postponement still synchronously load per-card metadata, priorities and topic state. build_branch_study_scope enriches the entire tree before selecting one subtree. subtree_node_infos uses list.pop(0), which repeatedly shifts a wide pending queue. Media review is already background-owned, but its full inspection still creates a Card per candidate and a Note per distinct note. Several bulk priority consumers call individual persistence helpers. The main tree snapshot already demonstrates a batched read model.

**Evidence and cost.** 4,000 get_priority helper reads took 139.593 ms versus 6.780 ms using repeated queries on an already-resolved connection, or 1.300 ms for five batches of at most 900 IDs. These helper results illustrate batching overhead; they are not timings for the complete dialogs.

**Implementation direction.** Extend operation-owned batch projections to the remaining consumers, limit branch study reads to required structure/metadata, and reuse one classifier and adjacency map. Use deque for breadth-first traversal. Put synchronous read previews in QueryOp and ordinary mutations in CollectionOp. Batch supplemental writes transactionally, preserving per-card errors and native Undo semantics.

**Acceptance.** Backend calls and SQL statements grow by bounded batches rather than per displayed field/card. Keep media attachment provenance, nested positions, due/exclusion previews, ordering, Preview mode and conflicting filtered-deck behavior identical.

**Sources.** [backend/knowledge_tree.py:1768](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/knowledge_tree.py:1768>), [backend/knowledge_tree.py:1857](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/knowledge_tree.py:1857>), [backend/knowledge_tree.py:1567](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/knowledge_tree.py:1567>), [backend/knowledge_tree.py:1544](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/knowledge_tree.py:1544>), [backend/knowledge_tree_postpone.py:503](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/knowledge_tree_postpone.py:503>), [frontend/knowledge_tree_postpone_dialog.py:802](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/knowledge_tree_postpone_dialog.py:802>), [frontend/knowledge_tree_subset_dialog.py:280](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/knowledge_tree_subset_dialog.py:280>), [backend/media_review.py:625](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/media_review.py:625>).

**Regression coverage.** `tests/test_knowledge_tree.py`, `tests/test_knowledge_tree_postpone.py`, `tests/test_media_review.py`, `tests/test_media_review_dialog.py`, `tests/test_priority_manager.py`.

### F16 Prevent PDF Find highlighting from observing its own writes

**P2 — High confidence source risk requiring browser validation.** Keep a nonempty PDF Find query active while the observed text layer receives a child/text mutation after observation begins.

The Find effect observes childList, subtree and characterData. Its callback schedules applySearchHitStyles, which rewrites span textContent or innerHTML and therefore creates the same kinds of mutations. One external text mutation can start successive self-scheduled passes. The initial highlighting pass happens before observation, and effect cleanup/renderInfo changes can stop the cycle, so sustained idle CPU is conditional rather than established for every search.

**Evidence and cost.** Potential repeated whole-page DOM rewriting on animation frames. No native WebEngine or real-browser reproduction was completed in this environment; the browser tool blocked local-file navigation. This finding must be reproduced before claiming an observed idle CPU defect.

**Implementation direction.** Observe text-layer lifecycle once, or disconnect/suppress the observer around owned writes and reconnect afterward. Make highlighting idempotent and modify only changed spans. Do not mutate PDF.js selection structure gratuitously.

**Acceptance.** In a real DOM regression, append text with Find active, settle rendering, and assert highlight work becomes idle with no further input. Verify match/no-match queries, progressive text, page switches, copy/selection and current-document context.

**Sources.** [frontend/src/PdfViewer.jsx:297](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/src/PdfViewer.jsx:297>), [frontend/src/PdfViewer.jsx:327](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/src/PdfViewer.jsx:327>), [frontend/src/PdfViewer.jsx:962](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/src/PdfViewer.jsx:962>), [frontend/src/usePdfRender.js:108](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/src/usePdfRender.js:108>).

**Regression coverage.** `frontend/tests/pdfSelection.test.mjs`, `tests/test_pdf_controls_browser.py`, `tests/test_pdf_dock.py`.

**Coordination.** Add a real DOM lifecycle regression, then rebuild web/dist/pdf_viewer.js after a source change.

### F17 Add cancellation and resource budgets inside PDF extraction

**P2 — Source confirmed.** Cancel indexing while a very large/damaged PDF is being extracted, or close/switch profile during that extraction.

index_pdf_documents checks cancellation between files. extract_pdf_pages_text builds a list for every page in one call and its pdftotext fallback captures all output without a timeout. Superseded work can therefore occupy a worker for the rest of a large file; stale publication guards prevent wrong writes but do not reclaim extraction time or peak memory.

**Evidence and cost.** O(all page text) materialization with no within-file cancellation deadline in this extractor. The call can outlive the visible operation by a document-dependent amount; no large-file timing or RSS was measured.

**Implementation direction.** Introduce cooperative checks between pages, a bounded extraction result/stream strategy, and explicit subprocess time/output budgets with termination cleanup. Consider a dedicated process for non-cooperative native work, using the existing annotation-process lifecycle as a reference, without assuming arbitrary thread parallelism is safe.

**Acceptance.** Cancellation stops before the next page/chunk when cooperative; timed-out children are reaped. Preserve ready/empty/error/backoff states, atomic index publication and generation guards. Never publish a partial page set as a complete index.

**Sources.** [backend/search_indexer.py:52](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/search_indexer.py:52>), [backend/pdf_manager.py:835](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/pdf_manager.py:835>), [backend/pdf_manager.py:882](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/pdf_manager.py:882>), [backend/pdf_annotation_process.py:81](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/pdf_annotation_process.py:81>).

**Regression coverage.** `tests/test_search_indexer.py`, `tests/test_pdf_manager.py`, `tests/test_pdf_search_safety.py`.

### F18 Bound Qt and React item creation after background reads

**P2 — Source confirmed.** Load a large knowledge tree, subset table or PDF highlight panel after its data is ready.

The main knowledge-tree data query is already asynchronous, but _apply_snapshot clears and creates every QTreeWidgetItem in one UI callback. Subset review populates all table rows/cells. The PDF all-highlights panel maps every matching highlight to buttons. Efficient worker reads do not bound these final UI construction costs.

**Evidence and cost.** O(all displayed items) widget/DOM construction and retained memory in a single refresh. Live frame time and peak memory remain unmeasured.

**Implementation direction.** Measure callback/commit time separately from query time. Use a model/view or paged/windowed representation for large collections, or bounded generation-aware construction batches. Preserve selection, expanded state, stable row order, accessibility and immediate cancellation of obsolete builds.

**Acceptance.** A background result cannot monopolize one UI callback for the entire large collection. Compare 1,000/10,000/50,000 synthetic nodes/items while testing selection restoration and stale results. Keep the existing batched tree snapshot instead of reintroducing per-card reads.

**Sources.** [frontend/knowledge_tree_dialog.py:1943](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/knowledge_tree_dialog.py:1943>), [frontend/knowledge_tree_subset_dialog.py:319](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/knowledge_tree_subset_dialog.py:319>), [frontend/src/PdfViewer.jsx:3209](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/src/PdfViewer.jsx:3209>).

**Regression coverage.** `tests/test_knowledge_tree.py`, `tests/test_knowledge_tree_mind_map.py`, `tests/test_accessibility_ux.py`, `frontend/tests/pdfHighlights.test.mjs`.

### F19 Load bookshelf thumbnails for visible tiles with a byte budget

**P2 — Source confirmed.** Open or repeatedly filter a bookshelf containing thousands of documents.

_refresh rebuilds matching tiles in batches of 40 and queues every uncached visible-result entry, including far offscreen tiles. _load_next_thumbnail decodes/renders serially and _thumbnail_cache retains QIcons without a byte/item budget for the dialog lifetime. Every keystroke restarts filter/population generations. The background render call also omits uses_collection=False, which should be checked against the installed task API before changing it.

**Evidence and cost.** For a 160 by 220 RGBA preview, raw pixels alone are about 140,800 bytes; 5,000 such previews would be about 671 MiB before Qt/container overhead. This is an illustrative size calculation, not a measured RSS value or guaranteed retained representation.

**Implementation direction.** Prioritize viewport tiles with a small prefetch margin and an LRU byte budget; debounce filtering and reuse stable items where practical. Keep bounded parallel decoding only after measuring file/CPU pressure, and mark collection-free image work explicitly where supported.

**Acceptance.** The number of decoded/retained previews stays bounded as library size grows; fast scrolling preserves tile identity and never applies stale images. Retain stored covers, PDF-only missing-cover fallback, captions, tag filters and per-profile behavior.

**Sources.** [frontend/pdf_bookshelf.py:1641](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/pdf_bookshelf.py:1641>), [frontend/pdf_bookshelf.py:1928](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/pdf_bookshelf.py:1928>), [frontend/pdf_bookshelf.py:2007](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/pdf_bookshelf.py:2007>).

**Regression coverage.** `tests/test_pdf_bookshelf.py`.

### F20 Split extension runtime chunks by actual consumers

**P2 — Measured artifact sizes and static import graph.** Inject a content script, wake the background worker, or create the clipboard offscreen page.

The Vite manualChunks rule puts every shared module, including React hooks and the full language-pack validation catalog, into extension-shared. The shared chunk statically imports extension-vendor. Consequently even the small content and offscreen entries pull the React vendor chunk. Built-in translation-pack export is already dynamically imported and should remain so.

**Evidence and cost.** The content entry has 1,000,932 bytes of static JS dependencies, the background entry 986,365 bytes, and the 393-byte offscreen entry reaches 950,502 bytes. These are uncompressed committed file totals at the completion snapshot, not network transfer, decoded heap or startup time. Dynamically imported built-in export packs are excluded.

**Implementation direction.** Separate non-React bridge/browser/i18n core from UI hooks and settings/export validation. Investigate loading custom-pack validation only when needed while preserving validation before use. Remove forced all-shared cohabitation and inspect static entry graphs after a reproducible build.

**Acceptance.** Content/background/offscreen paths without React UI no longer statically import React solely through the shared chunk. Cold language initialization, custom packs, Firefox adaptation, permissions and bridge behavior remain unchanged. Verify generated source/output alignment.

**Sources.** [frontend/vite.extension.config.js:26](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/frontend/vite.extension.config.js:26>), [chrome_extensions/incremento_companion/src/shared/i18n.js:6](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/chrome_extensions/incremento_companion/src/shared/i18n.js:6>), [chrome_extensions/incremento_companion/src/shared/languagePacks.js:1](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/chrome_extensions/incremento_companion/src/shared/languagePacks.js:1>), [chrome_extensions/incremento_companion/src/shared/languagePacks.js:242](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/chrome_extensions/incremento_companion/src/shared/languagePacks.js:242>).

**Regression coverage.** `chrome_extensions/incremento_companion/tests/languagePacks.test.js`, `chrome_extensions/incremento_companion/tests/i18n.test.js`, `chrome_extensions/incremento_companion/tests/bridge.test.js`.

**Coordination.** Run the extension tests and build:extension; do not edit committed bundles by hand.

### F21 Share media detection across heartbeat paths

**P2 — Source confirmed.** Keep many pages or provider frames with Companion content scripts alive, especially pages containing multiple video elements.

The one-second interval calls sendHeartbeat and sendWebMediaHeartbeat separately; both call currentTrackedMedia, which queries and sorts video elements. timeupdate/play/pause events repeat the same pair. Dedupe happens after media detection. A separate 750 ms interval polls the URL. visibilitychange flushes state but does not suspend ordinary polling.

**Evidence and cost.** Repeated DOM queries/sorts per sample and per frame, including nonproductive polls. No browser CPU measurement was completed, and background timer throttling can change actual frequency.

**Implementation direction.** Capture media context once per tick/event and pass it to both protocol payload builders. Track the active video via bounded lifecycle discovery, prefer a linear maximum selection over sorting, and reduce idle polling while retaining navigation/reinjection detection. Flush final progress on hide/pagehide before suspending.

**Acceptance.** One media discovery per sampling event, bounded pending requests and correct resume/watch progress across nested frames, SPA navigation, pauses/seeks and service-worker restarts. Avoid raising bridge/storage update frequency.

**Sources.** [chrome_extensions/incremento_companion/src/content/main.js:2243](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/chrome_extensions/incremento_companion/src/content/main.js:2243>), [chrome_extensions/incremento_companion/src/content/main.js:2492](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/chrome_extensions/incremento_companion/src/content/main.js:2492>), [chrome_extensions/incremento_companion/src/content/main.js:2533](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/chrome_extensions/incremento_companion/src/content/main.js:2533>), [chrome_extensions/incremento_companion/src/content/main.js:2580](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/chrome_extensions/incremento_companion/src/content/main.js:2580>).

**Regression coverage.** `chrome_extensions/incremento_companion/tests/bridge.test.js`, `tests/test_video_watch_meter.py`, `tests/test_video_web.py`.

### F22 Index SuperMemo parents once and batch supplemental schedule writes

**P2 — Source confirmed.** Import a large SuperMemo collection.

Inside the note-creation loop, parent_title uses next over ordered to locate each element's parent, repeating up to the full collection for each element. Topic schedule state is then saved through set_topic_schedule once per topic, with a commit in each call. This adds avoidable Python scans and small transactions to already expensive native note/media/history work.

**Evidence and cost.** Worst-case O(imported elements times ordered elements) parent lookup and one supplemental schedule commit per topic. End-to-end SuperMemo import time was not measured.

**Implementation direction.** Build an element-ID lookup once and reuse it for parent metadata. Batch topic-state rows in the existing controlled supplemental transaction boundary where failure recovery allows. Keep ImportOperation journal/bind/commit durability boundaries intact; do not bulk-disable journaling to improve a benchmark.

**Acceptance.** Parent resolution is O(1) per created element, and supplemental topic writes use bounded transactions. Preserve cloze mapping, rich sources, native revlog restoration, idempotent reimport, media rollback and archived optimization data.

**Sources.** [backend/supermemo_import.py:599](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/supermemo_import.py:599>), [backend/supermemo_import.py:667](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/supermemo_import.py:667>), [backend/supermemo_import.py:755](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/supermemo_import.py:755>), [backend/db.py:3924](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/db.py:3924>).

**Regression coverage.** `tests/test_supermemo_format.py`, `tests/test_supermemo_import_anki_integration.py`.

**Coordination.** F06 also affects the final knowledge-tree persistence phase.

### F23 Profile eager imports and first database use before changing startup

**P3 — Profiling hypothesis.** Cold-start Anki or open a profile whose Incremento database needs migration.

__init__.py has 89 direct relative import statements, including substantial reader/dialog modules before any of those features are opened. It also performs profile activation/migration synchronously. A thread's first get_connection can initialize schema while the connection manager's global lock is held; a slow initialization can delay other callers asking for cached handles. Routine pending-import recovery itself already has a bounded read-only preflight.

**Evidence and cost.** Import fanout and lock scope are source facts. Their contribution to startup time has not been measured, so this is lower priority than reproduced work. Deferred imports can merely move cost to first use.

**Implementation direction.** Capture cold/warm import self/cumulative time, profile-open stages and first-DB-use time in a disposable synthetic environment. Lazy-load optional dialogs only when the measurement supports it; register hooks idempotently and initialize language before visible strings. Separate safe connection fast paths from potentially waiting initialization without sharing connections across threads.

**Acceptance.** Compare cold startup, warm profile open and first feature opening together. Preserve profile/WebEngine reset order, bounded recovery, consent-gated note-type updates, migrations and concurrent initialization correctness.

**Sources.** [__init__.py:42](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/__init__.py:42>), [__init__.py:3033](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/__init__.py:3033>), [backend/db_connection.py:56](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/db_connection.py:56>), [backend/operation_journal.py:300](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/operation_journal.py:300>).

**Regression coverage.** `tests/test_db.py`, `tests/test_db_schema.py`, `tests/test_migration.py`, `tests/test_note_type_updates.py`.

### F24 Reuse normalized config within each reviewer event

**P3 — Measured normalization and source confirmed.** Render reviewer badges/buttons or compute a topic answer when many scheduler presets or profile preferences exist.

load_addon_config deep-copies and normalizes the entire config, including every preset and its legacy alias. Many configured helpers independently call it. The priority badge loads config, calls topic classification more than once, and later calls a priority-direction helper without passing the already loaded config. Similar repeated access occurs in topic scheduling.

**Evidence and cost.** Fifty normalizations took 1.640/4.609/14.199 ms with 1/25/100 presets. Even the largest case is a fraction of a millisecond per call; this is a secondary optimization, not a demonstrated major pause.

**Implementation direction.** Resolve one event-local normalized snapshot and classifier, passing them through configured helpers. Consider a versioned read cache only inside config_service with explicit invalidation for every save and supported external edits. Do not maintain independent consumer caches that can disagree with Settings.

**Acceptance.** Bound normalization/classification calls per event and preserve unknown keys, preset aliases, concurrent reader preferences, settings changes and profile switching. Rebenchmark before adding broader cache complexity.

**Sources.** [backend/config_service.py:350](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/config_service.py:350>), [backend/config_service.py:452](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/config_service.py:452>), [__init__.py:3309](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/__init__.py:3309>), [backend/topic_scheduler.py:791](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/backend/topic_scheduler.py:791>).

**Regression coverage.** `tests/test_config_service.py`, `tests/test_config_properties.py`, `tests/test_reviewer_priority_badge.py`, `tests/test_settings_dialog.py`.

## Existing optimizations to preserve

Several seemingly expensive features already have important protections. Treat these as constraints on changes, rather than proposing the same work again:

- Session candidate pools retain their priority/random orders and cursors across refill, batch real-Anki classification and filtered-deck ordering, and bound exhaustion. Preserve the special no-progress initial QueryOp mutation and deferred reviewer advance. The remaining session-dialog counts are F01.
- Search ALL uses debouncing, LatestQuery, background QueryOp data reads and collection-free background extraction, with profile/generation guards. F12 concerns the remaining candidate/Find costs; it does not claim Search ALL extracts a library on the UI thread.
- The main knowledge-tree snapshot batches card/note metadata and caches visible note text per snapshot. F15 concerns older branch consumers and F18 the final widget construction.
- PDF rendering bounds backing canvas pixels, coalesces/cancels render requests, reuses page text, warms a moving page window with a 64 MiB estimate budget, and releases unused page resources. Do not replace these with unbounded whole-document pre-rendering.
- Annotation synchronization uses captured-profile coalescing, a debounce, bounded passes and a subprocess boundary. Profile-open import recovery checks pending journal identities rather than scanning all cards/indexes.
- Bridge requests, browser PDF reads, captures, diagnostics and activity history already have size/concurrency or queue budgets. Bounded size does not eliminate copying or CPU cost, but removing limits is not an optimization.
- Document statistics already batch collection reads and paginate the native library table. PDF metadata-title lookups have a signature-keyed LRU. Built-in language-pack export is already lazy. Keep these behaviors.

## Additional profiling watchlist

These are areas to measure after the prioritized work; the audit does not establish an additional high-priority defect:

- Near-limit PDF capture retains chunk buffers, a contiguous byte array, a Blob/base64 result, serialized JSON and backend decode buffers at different stages. Measure peak RSS and transfer CPU before designing a new protocol. Preserve the 48 MiB cap, signatures, final-URL policy and authenticated bridge.
- Page capture clones and serializes the DOM before checking the final HTML length. A very large source page can therefore spend time before rejection. Consider preflight node/time budgets without silently truncating content or weakening sanitization.
- Document-completion statistics read PDF page counts or EPUB metadata throughout the library in a worker. Measure collection-queue occupancy and repeated loads when the Statistics dialog refreshes; use signature-based derived caches only if the repeated I/O is material.
- Annotation sync digests, backup compression, OCR, video transcoding and EPUB sanitization are inherently heavy explicit operations. Profile cancellation, memory and contention with readers before adding concurrency. This pass did not measure representative real documents or media.
- The PDF viewer build is configured without minification. Measure first reader load/parse and compare a reproducible production build before changing debuggability or build settings. The committed viewer is 667,498 bytes; this alone does not establish a startup delay.

## Implementation sequence and safety constraints

A practical sequence is to remove the most avoidable work first, then improve broader architecture:

1. Reproduce F08 with a prepared empty PDF, F09 with opaque bookmark IDs, and F11 with cleared Redo. These have narrow mechanisms and can be corrected with focused contracts and scaling checks.
2. Address F01, F02, F03, F04 and F10 for the interaction paths users encounter repeatedly. Separate query, formatting, UI construction and persistence timing so a worker change does not hide remaining UI work.
3. Implement F05 and F06 with schema/rollback coverage and production-equivalent synthetic datasets. Then revisit search/index/import timings, because several later paths depend on those storage costs.
4. Apply F12 through F22 according to measured usage and library shape. Reproduce the conditional F16 DOM lifecycle in an environment that can run browser tests before accepting an idle-CPU claim.
5. Profile F23/F24 and the watchlist after larger costs are removed. Do not start with generic caching, more threads, Python loop syntax changes, or disabling durability.

For every implementation, keep Anki authoritative for scheduling, notes/cards and Undo/Redo; use the operation-provided collection; capture profile/request generations; and reject stale callbacks. Read root and subdirectory AGENTS.md plus tests/AGENTS.md before code changes. Write a meaningful failing regression first. New DB structures/triggers need a monotonic migration and rollback coverage. Preserve import journaling, source provenance, note-type consent, reader links/limits and optional FTS fallback. Never disable fsync, WAL safety or validation to produce a better benchmark. Rebuild viewer/extension bundles from their owning source when those sources change.

Use operation counts, cache invalidation and result equivalence as deterministic regression assertions. Keep noisy wall-clock thresholds in dedicated performance checks. For product profiling, collect warm/cold p50/p95 durations over enough repetitions, GUI long-task/frame time, peak memory, SQL/query counts, bytes materialized and worker/collection queue wait. Suggested interaction goals such as under 16 ms for small UI callbacks or no avoidable pauses over 50 ms are proposed engineering targets, not measured guarantees.

## Validation performed

- Both synthetic benchmark programs completed with fixture/result assertions. Raw samples and source hashes are saved alongside the report. All runtime fixtures were temporary; no live profile was inspected.
- Selected Python suites: **517 passed, 10 failed in 13.40 seconds**. All ten failures are browser integration cases in tests/test_epub_dock.py that failed to launch the optional Chromium process under the execution permissions. macOS sandbox-parameter initialization failed before the browser assertions. They are not evidence of a performance regression. The exact selection and failure families are in [check results](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/checks.json>).
- Frontend Node tests: **247 passed**. Extension Node tests: **228 passed**.
- The added benchmark script passed the repository Ruff rules and the JavaScript benchmark passed Node syntax checking. Local document links and evidence symbols were validated.
- The full Python suite, live-Anki profiling, release packaging and source rebuilds were not run by this audit. The audit changed no shipped source; concurrent changes belong to their separate owner.
- A hidden synthetic browser probe could not run because browser policy rejected local-file navigation. Its temporary tab was closed; no real-browser result is claimed for F16.

## Reproduction and AI handoff

Run these commands from the repository root. The benchmark programs create and clean synthetic data under TemporaryDirectory and do not start Anki, use a real profile, install packages or make network requests:

```bash
.venv/bin/python performance_audit/2026-10-25/benchmark.py --output /tmp/incremento-performance-repeat.json
node performance_audit/2026-10-25/benchmark_bookmarks.mjs --output /tmp/incremento-bookmarks-repeat.json
```

Read [the structured backlog](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/findings.json>) for stable finding IDs, symbols, verified line anchors, proposed acceptance criteria and affected test files. Read [the complete file inventory](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/file_inventory.json>) for per-file coverage/disposition and original SHA-256 hashes. Re-resolve symbols and compare hashes before implementing against a later revision; line numbers describe this baseline only.

> Implement one selected finding from this audit at a time. First confirm that the cited mechanism still exists, reproduce it with synthetic or explicitly authorized data, and read the applicable agent/test guides. Write the failing behavioral/scaling regression, make the smallest safe change, and run the affected checks. Preserve the acceptance constraints and all profile, Anki ownership, Undo, security and durability contracts. Report before/after measurements with the same fixture and distinguish a local benchmark gain from end-to-end user latency. Do not treat an unmeasured hypothesis as an observed production bottleneck.

## First-batch implementation results (historical)

The first batch on 25 October 2026 removes repeated extraction, object copying, ancestor traversal, whole-index deletion scans and duplicate statistics saves. It also reduces Undo tracking work. These changes address six measured mechanisms; the broader UI work in the original backlog remains open.

| Finding | Applied change | Status |
| --- | --- | --- |
| F03 | Free-study time and answer events persist totals and joint tag attribution together | Implemented; four durable saves per review cycle become two |
| F05 | Migration 19 adds indexed, stable FTS lookup identities for PDF, EPUB and OCR | Implemented, with the fresh-indexing tradeoff below |
| F06 | Iterative validation reuses completed parent paths | Validation complete; writes still preserve existing whole-structure timestamp behavior |
| F08 | Completed empty background PDF extraction is passed to note creation | Direct bytes/download paths complete; webpage rendering, cover preparation and Qt-only fallback work remain |
| F09 | Bookmark construction lazily clones caller state once and fills one private map | Model complete; folder subtree indexing and deferred DOM mounting remain |
| F11 | Redo-clear detection checks local linked IDs without copying global history per card | Implemented |

### Benchmark comparisons

The following are local synthetic component measurements. They exclude live-Anki UI latency. Python comparisons use the same fixture sizes and median-of-three sampling, with five samples for statistics; bookmark comparisons use Node and three samples. The Undo SQL boundary is a fake. PDF preparation uses real PyMuPDF/Poppler extraction and the production manager's prepared-text decision, with Qt extraction represented by an empty boundary fake. PDF note creation, file storage and cover rendering are excluded.

| Workload | Before | After | Change |
| --- | ---: | ---: | --- |
| Save a 4,000-node chain | 275.577 ms | 11.108 ms | 24.8× faster |
| Replace an existing 4,000-page PDF index | 814.010 ms | 126.463 ms | 6.4× faster |
| Build 5,000 opaque bookmark IDs | 2,065.372 ms | 3.709 ms | 557× faster |
| Clear Redo with 4,000 tracked cards | 310.515 ms | 2.959 ms | 105× faster, excluding SQL |
| Free-study time and answer, 512 populated tags per group | 97.005 ms and 4 saves | 55.818 ms and 2 saves | 42% less time |
| Prepare and consume empty text for a 500-page PDF | 65.749 ms and 2 extraction passes | 31.623 ms and 1 extraction pass | 52% less time in this fixture |

Wide-tree saves remain approximately unchanged: 10.866 to 10.267 ms for a 4,000-node star. Parent validation has deterministic work-budget coverage for chains, balanced trees and stars, in both insertion orders. This avoids turning wall-clock timing into a flaky unit-test threshold.

Text-index deletion no longer grows with unrelated text. Deleting a 50-page document took 0.276, 8.331 and 25.719 ms with 0, 2,000 and 8,000 unrelated pages under schema 18. Schema 19 took 0.145, 0.164 and 0.184 ms respectively. Source/FTS counts are checked after each timed deletion.

**FTS tradeoff:** maintaining the extra lookup identity increases fresh insertion work. For 4,000 short synthetic pages, first insertion increased from 45.926 to 115.464 ms, about 70 ms extra; allocated database pages increased from 1,089,536 to 1,224,704 bytes. The one-time upgrade of that populated fixture took 10.716 ms. Large real text indexes require their own migration timing and disk budget. The change keeps ordinary source tables authoritative, preserves their column layout, and removes the repeated full-mirror scans that previously made replacement and deletion scale poorly.

Raw samples, query plans and measured source hashes are saved in [before measurements](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/implementation_before.json>), [after measurements](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/implementation_after.json>), [bookmark before](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/bookmarks_before.json>), [bookmark after](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/bookmarks_after.json>), [PDF comparison](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/pdf_preparation_comparison.json>) and [FTS tradeoffs](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/fts_tradeoffs.json>).

### Behavior and recovery coverage

Statistics comparisons assert identical persisted totals, joint attribution, daily history and SQLite mirrors between separate legacy updates and the combined API. The file still uses the profile lock, fsync and atomic replacement. Failed replacement leaves both persisted contributions unchanged, and retry succeeds. Incremento-owned sessions keep their existing aggregate owner and separate attribution call; PDF and EPUB retain their concrete types.

Migration tests cover existing populated mirrors with unrelated rowids, repeat initialization, key edits, multiple OCR images on one note/card, replacement/ignored insertion, deletion, transaction rollback, `VACUUM`, absence of FTS and migration interruption. A single-row deletion must finish within a fixed SQLite work budget despite 2,000 unrelated rows. Lookup identities are independent of the ordinary tables' implicit rowids.

The empty-PDF fix distinguishes a completed empty result from unavailable extraction backends. Qt fallback remains available when no background backend can read the PDF. Tests cover browser bytes, downloads, repeated preparation and consumption of an empty precomputed list. Existing import-journal and reconciliation tests remain green. Bookmark tests preserve frozen caller maps and nodes, edits to existing items, duplicate precedence, paths and unusual computed keys. Undo tests retain the original lifecycle coverage and add a deterministic global-history iteration budget for both final Redo and cleared Redo.

### Verification

- Focused implementation Python run: **861 passed in 6.23 seconds**, including database/search, statistics/session, tree, browser/PDF/video imports, journal/reconciliation, schema compatibility and real-Anki scheduling lifecycle tests.
- Earlier restricted Python run: **3,970 passed, 37 failed, 25 warnings in 150.87 seconds**. The failures occurred before the intended browser/GUI behavior checks: 19 Chromium-launch failures, 16 Qt/macOS process-startup aborts and 2 denied local socket binds. That run preceded the final FTS insertion refinement. All of these permission-related failures were resolved in the full release run below. No tests were skipped or relaxed.
- Extension tests: **230 passed**. Frontend/extension ESLint, Ruff, configured mypy and Python compilation passed.
- The extension was rebuilt from source, all five entry bundles passed syntax checks, and a second build reproduced all eight output files byte for byte. The existing large-chunk warning remains relevant to F20.
- The benchmark environment remains Python 3.14.5, SQLite 3.53.2, Node 25.6.0 and macOS arm64. Supported Anki Python 3.12/3.13 and live UI timings still require their respective environments.

Exact commands and failure families are in [implementation checks](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/implementation_checks.json>). [Implementation results JSON](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/implementation_results.json>) supplies current statuses, component measurements and source hashes for the next implementation pass.

Release verification on 25 October 2026 completed the full `package_addon.py --release --clean-staging` gate with the required headless browser and temporary local-socket permissions: **4,012 Python tests passed** in 191.79 seconds, with 62 warnings; **247 viewer tests and 230 extension tests passed**. Translation checks, both builds, compilation, Ruff, configured mypy, ESLint, all four mutation guards and seven deterministic repair cases passed. Dependency audit reported zero vulnerabilities, and `pip check` found no broken requirements. Archive validation confirmed the shipped files match the source and exclude runtime user data and local `meta.json`. The existing contributor-credit and translation changes are included with their rebuilt assets. [Release checks](</Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento/performance_audit/2026-10-25/release_checks.json>) records the artifact hash and complete gate results.

### First-batch handoff (superseded by completion results)

Continue with F01 session-dialog queries, F02 EPUB metadata reuse, F04 reviewer source-cover lookup, F07 bounded database inspection and F10 writing preview/save scheduling. Complete F06's change-only persistence only after specifying timestamp behavior. Finish F08's webpage/cover preparation with a working browser/Qt integration environment, and treat F09 folder mounting as a separate rendering workload. Keep the fresh-indexing overhead visible when tuning F05 further.

The original `findings.json` and inventory describe the audit baseline; use `implementation_results.json` for applied status and resolve current symbols before editing. Reproduce the extra comparisons with:

```bash
.venv/bin/python performance_audit/2026-10-25/benchmark_pdf_preparation.py --output /tmp/incremento-pdf-preparation.json
.venv/bin/python performance_audit/2026-10-25/benchmark_fts_tradeoffs.py --output /tmp/incremento-fts-tradeoffs.json
```
