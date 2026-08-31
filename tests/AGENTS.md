# Tests Agent Notes

Use this file whenever behavior changes, a bug is fixed, or tests are created,
changed, or reviewed. The root `AGENTS.md` requires agents to read it before
editing implementation code so the test can drive the change.

## 20 Test-Authoring Rules

1. **Define the contract first.** Write down the observable behavior, invariant,
   and principal risk before choosing assertions or changing production code.
2. **Start red.** For every bug fix or behavior change, add the smallest meaningful
   test first and run it to confirm that it fails for the expected reason. If it
   passes before the change, strengthen it or record which existing test already
   proves the regression.
3. **Make the smallest change to reach green.** Implement only enough production
   behavior to satisfy the failing contract; do not hide unrelated refactors in
   the green step.
4. **Refactor only while green.** Improve names, structure, fixtures, and duplication
   after the test passes, rerunning the focused test after each material refactor.
5. **Test stable behavior, not implementation trivia.** Prefer public APIs,
   persisted state, emitted results, and user-visible transitions. Assert internal
   calls only when that interaction is itself a required contract.
6. **Protect existing regressions.** Never delete, skip, loosen, or rewrite a failing
   test merely to make a change pass. Update an expectation only when the intended
   behavior changed, and make that reason explicit in the test or change summary.
7. **Use the lowest sufficient test layer.** Keep most cases fast and unit-level;
   add integration coverage at database, filesystem, Anki, Qt, browser-bridge, and
   generated-asset boundaries, with end-to-end tests reserved for critical flows.
8. **Keep tests deterministic.** Control time, randomness, locale, environment,
   network responses, ordering, and generated identifiers. Never depend on the
   developer's machine, live services, test order, or an unseeded random source.
9. **Isolate every test.** Each test must pass alone and in any order, own and clean
   up its mutable state, use temporary/profile-scoped storage, and never read or
   write real runtime data under `user_files/`.
10. **Mock only true boundaries.** Prefer realistic values and small fakes; mock
    external, slow, privileged, or nondeterministic collaborators rather than the
    behavior under test. Do not over-mock internal call chains until the test only
    verifies the mock setup.
11. **Keep one behavioral reason to fail.** Structure tests as Arrange, Act, Assert;
    multiple assertions are welcome when they jointly prove one outcome, but split
    unrelated scenarios into separate tests.
12. **Name tests as specifications.** A test name should identify the initial
    condition, action, and expected result so failures are understandable without
    opening the implementation.
13. **Cover input partitions and boundaries.** Include normal, empty, missing,
    malformed, duplicate, zero/one, limit, off-by-one, maximum-size, and
    unsupported/future-version cases wherever they are relevant.
14. **Test hostile and unauthorized input.** For every trust boundary, exercise
    injection, traversal, XSS, SSRF, origin/authentication failures, oversized
    input, unsafe redirects, and sensitive-data leakage as applicable; prove the
    system fails closed.
15. **Prove failure safety.** Exercise exceptions, partial writes, retries,
    cancellation, rollback, recovery, and idempotency. Assert both the returned
    error and the absence of corrupt or orphaned side effects.
16. **Exercise lifecycle and concurrency risks.** When code crosses threads,
    profiles, callbacks, processes, or async boundaries, test races, duplicate or
    stale callbacks, profile switches, bounded waits, and teardown without using
    arbitrary sleeps.
17. **Use parameterization and properties deliberately.** Parameterize the same
    contract across meaningful cases with readable IDs; use property/invariant
    tests for broad input spaces, but keep a named regression example for every
    bug that reached a user.
18. **Make assertions precise and mutation-resistant.** Assert exact outputs and
    important side effects, including what must not change. Treat line coverage as
    a diagnostic signal, not success; a good test should fail under a plausible
    broken implementation.
19. **Make failures fast and actionable.** Use focused fixtures, explicit expected
    values, bounded polling instead of sleeps, and messages or assertion diffs that
    reveal the violated contract. Eliminate flaky tests rather than retrying them.
20. **Verify in widening circles.** Run the new test red, then green, then the
    affected focused suite, and finally the full required checks for the scope,
    including builds for generated assets. Report commands, failures, skips, and
    warnings honestly; do not claim completion from an unrun check.

## Test Environment

- Use `.venv/bin/python`.
- `tests/conftest.py` sets the active profile to `TestProfile`, so test DB and path helpers use `user_files/TestProfile/`.
- Prefer focused regression tests for the subsystem you change, then run the full suite when the change is broad enough to justify it.
- Many focused runs need `-o addopts=` because local `pytest.ini` may expect plugins not present in the environment.

## Useful Suites

Full suite:

```bash
.venv/bin/python -m pytest tests/ -q
```

If the local environment lacks `pytest-cov` but `pytest.ini` expects it, use:

```bash
.venv/bin/python -m pytest -o addopts= tests/test_add_card_dock.py -q
```

Focused suites for common hotspots:

```bash
.venv/bin/python -m pytest -o addopts= tests/test_add_card_dock.py -q
.venv/bin/python -m pytest -o addopts= tests/test_browser_bridge.py tests/test_pdf_manager.py tests/test_video_web.py -q
.venv/bin/python -m pytest -o addopts= tests/test_knowledge_tree.py tests/test_knowledge_tree_postpone.py tests/test_db.py tests/test_session_selection.py -q
.venv/bin/python -m pytest -o addopts= tests/test_session.py tests/test_learn_dialog.py tests/test_session_selection.py -q
.venv/bin/python -m pytest -o addopts= tests/test_settings_dialog.py tests/test_learn_dialog.py -q
.venv/bin/python -m pytest -o addopts= tests/test_note_metadata.py tests/test_browser_bridge.py tests/test_pdf_manager.py tests/test_video_web.py -q
.venv/bin/python -m pytest -o addopts= tests/test_reviewer_priority_badge.py tests/test_custom_schedule.py -q
.venv/bin/python -m pytest -o addopts= tests/test_topic_scheduler.py tests/test_topic_scheduler_anki_integration.py tests/test_custom_schedule.py tests/test_db.py -q
.venv/bin/python -m pytest -o addopts= tests/test_db.py tests/test_writing_dock.py -q
.venv/bin/python -m pytest -o addopts= tests/test_statistics.py tests/test_stats_dialog.py tests/test_timer_widget.py tests/test_session.py tests/test_scheduler.py -q
```

## Expectations

- If you change browser import behavior, cover backend normalization and extension-facing behavior.
- If you change profile-aware paths or migration behavior, keep assertions explicitly profile-scoped.
- SQLite lifecycle changes need connection isolation plus schema-ledger success/rollback coverage. Cross-store imports need before-card rollback, after-card preservation, optional content-ID/source-link rebind, and path-containment cases.
- Note-type update regressions must prove inspection is non-mutating, absent unused types are not created at startup, implicit changes to existing types fail closed, consent applies only the displayed changes, and internal content identity never makes `Incremento_Content_ID` a required Anki field.
- Search/index changes need unchanged/error/cancel/force behavior plus bounded repository results; no test may require a Qt-thread library scan.
- Bridge changes require handshake, origin, token/protocol, body-limit, concurrency, and extension retry tests.
- If you change reviewer or dock behavior, prefer regression tests that exercise the user-visible state transition instead of only helper internals.
- Document Bookshelf regressions should cover combined PDF/EPUB loading (including suspended cards), format filtering, loaded note tags, title filtering, exact case-insensitive tag parsing and OR/AND matching, combined title/type/tag filters, first-page/EPUB cover and source metadata, legacy cards without stored covers, dark/light caption contrast, media-path containment, type-correct reader opening, PDF-only preserve-history, both-format open-to-study behavior, and migration of the configurable `Alt+Shift+P` default.
- Reader-link regressions must cover the default-off toggle, trusted current-card bridge messages, PDF annotation rectangles and internal destinations, bounded internal-link back history with page/scroll restoration and per-PDF reset, the preserved native right-click menu plus validated **Copy Link to This Place**, rich-HTML/plain-text/private-marker clipboard payloads, forced rich paste under Anki's format-stripping mode, hostile marker rejection, PDF page/scroll and EPUB section/offset restoration, legacy EPUB command compatibility, stale-card rejection, HTTP(S)-only external normalization, credential/control/scheme rejection, EPUB sanitizer cache versioning, extraction-root containment, known-section/fragment resolution, and regenerated `web/dist/pdf_viewer.js` output.
- Item-card `Fail / Pass` regressions must cover every Anki state: `Fail` remains `Again` (ease 1), and `Pass` becomes `Good` (ease 3), including learning and relearning cards. Keep topic-card behavior separate.
- Topic-button regressions must verify that `More`, `Same`, and `Less` all submit Anki `Good` (ease 3) across new, learning, relearning, review, and rescheduling-filtered-deck states while preserving the original frequency choice for Incremento. Verify configurable immediate scheduling, existing-interval seeding, maximum-interval caps, custom-rule precedence, one-step Anki Undo/Redo reconciliation, exactly one Good revlog, and no manual revlog. Also cover non-rescheduling filtered-deck Preview for both topic and non-topic rules: Anki's original schedule and the rule must remain untouched, with no Incremento review-history row. `tests/test_topic_scheduler_anki_integration.py` runs these lifecycle checks in a clean subprocess because the main test harness mocks Anki modules.
- If you change note creation or import provenance, assert that metadata lands in dedicated `Incremento_*` note fields and not inline in the main content field.
- Standalone Add Cards priority regressions should cover native-versus-dock editor routing, immediate numeric-input synchronization, the neutral `50` default, and applying the chosen value to every card generated by a note without replacing pending extraction priority.
- Existing-card priority-toolbar regressions must cover Browser and Edit Current registration, exact current-card resolution, Browser refresh after save, and fail-closed handling when an Edit Current note does not match the active reviewer card.
- Add-card extraction tag regressions must simulate switching sources after Anki copies tags into the next blank note: stale Incremento-owned tags disappear, shared current-source tags remain, pre-existing manual tags survive, explicitly toggled T/I tags become user-owned, and a missing current source cannot retain prior provenance context.
- If you change knowledge-tree behavior, cover both raw structure helpers and a user-facing consumer such as branch study, postpone, subset review, or branch-summary formatting.
- If you change session selection or refill behavior, cover `tests/test_session_selection.py`, `tests/test_session.py`, `tests/test_session_anki_integration.py`, and any `frontend/learn_dialog.py` save/load wiring affected by `include_new` or `auto_refill_session`. Session-dialog acceptance regressions must prove that **OK** updates the selected named preset and dialog state in one write without changing sibling presets or forward-compatible config keys.
- Session-dialog tag-slider regressions must prove that a lone synthetic Other row is normalized to a disabled 100% control and becomes editable again when a real tag row exists.
- Large-session regressions must exercise a 9,999-card target with scarce/exhausted pools, bounded misses, cached candidate searches, one priority sort or random shuffle per pool across incremental auto-refill transactions, rollback-safe cursor rewinding, bounded live-queue fetches, compact filtered-deck searches, batch topic/item classification, and batch order updates. Startup/refill regressions must also prove that read-only selection and the bounded initial deck build use serialized no-progress `QueryOp` paths, the initial mutation dispatches `on_op_finished`, refill/larger mutations use `CollectionOp`, stale selection results are discarded, post-operation UI waits for native teardown without an unbounded progress-manager wait, session exit performs no filtered-deck collection mutation, and deferred reviewer advancement is cancelled after exit. Endpoint ratios must prove that 0%-weight buckets are never selected.
- Reviewer-dock focus regressions belong in `tests/test_reviewer_focus.py`: recovery is retried for a bounded interval after both question and answer hooks, works for an owned floating dock, and does not displace modal/popup or separate-window focus.
- If you change settings dialog fields, config defaults, or config-backed normalization, cover `tests/test_settings_dialog.py` plus the subsystem-specific helper tests that consume those values.
- If you change video-card behavior, cover both backend media helpers and the frontend-facing flow that consumes them.
- If you change media Review All, cover legacy positioned PDF/EPUB links, exact parent metadata, saved video timestamps, attached cards acting as standalone knowledge-tree roots, nested position inheritance, Topic/Item filtering, direct/nested and entire/up-to-current scope, Anki due-only state, limits, exclusion preview counts, every ordering mode, deterministic preview/build random order, background query plus filtered-deck construction, and PDF/EPUB/video position restoration. The include-other-filtered-decks path also needs one-shot/default-off UI coverage, active-review exit ordering, whole-deck side-effect messaging, unit coverage for unselected cards returning home, and a real-Anki collection integration test.
- If you change writing-card behavior, cover both DB persistence and the dock-side helper/config behavior. Writing stats are per card, and the current-card session resets on reopen.
- If you change custom scheduling or the reviewer badge, add a regression for the “missing rule” case so schedule text does not appear by default. Review-time custom scheduling also needs a real-Anki lifecycle check proving there is one answer revlog, no manual revlog, one Answer Card Undo/Redo step, and correct one-time-rule restoration/consumption.
- Undo reconciliation regressions must cover manual/bulk topic-state edits both between answers and after the answer being undone, rejection of forget/delete as review Undo, verified new-revlog ownership, profile tracker reset, retirement when Anki clears the Redo stack, and preservation of newer custom-rule revisions across Redo even when an identical replacement is created before Undo. Also cover migration/backfill of the persistent revision ledger.
- If you change Browser quick tags, cover complete-set deduplication, case/order-insensitive persisted identity, row-major nine-position layout, paired `1–9` and `A–I` shortcuts, no promotion on reuse, new-tag admission, automatic versus fixed mode, nine fixed-slot persistence/validation, reserved green for `topic`, custom-color persistence/reset, and collision-free effective colors. The focused files include `tests/test_reviewer_tags.py`, `tests/test_quick_tag_shortcuts.py`, `tests/test_tag_colors.py`, and `tests/test_db.py`.
- If you change stats normalization, history, or export behavior, cover `StatsManager`, `custom_learn_stats.json`, `stats_daily_history`, unique PDF/EPUB page deduplication, bounded zero-filled trend reads, migration rollback/constraints, `export_stats_json()`, dirty input cleanup, file-first loading, and transactional DB fallback/export compatibility.
- If you change EPUB/PDF scheduling or review-time attribution, assert concrete `pdf` and `epub` card types stay separate in scheduler results, persisted stats, and runtime session time.
- If you change stats dialog helpers, cover summary metrics, 7/30-day Topics/Items/Other and PDF/EPUB/time series, streak/active-day calculations, EPUB labels/colors, review-time formatting, and hidden synthetic tags such as `__no_tags__`.
- If you change timer activity behavior, cover PDF and EPUB page counters separately, per-report reset after summaries, cumulative daily totals, and reset on scheduler logical-day changes.
- If you change support diagnostics, inject representative secrets into config, event extras, database rows, paths, URLs, IDs, exception messages, and tampered persisted logs, then assert none survive the exported ZIP. Also cover event-schema rejection, non-blocking writes, bounded queue drops/rotation, per-profile paths, fixed ZIP metadata, recorder health, safe row/column counts and schema/code hashes, non-collection export execution, operation attribution (including partials), scheduling/session/explicit-review lifecycle events, and menu/callback wiring.

## Current Baseline

- The full suite must collect and pass in one pytest process. UI tests that temporarily replace `aqt`, `aqt.qt`, or `PyQt6` modules must restore the original dependency modules immediately after importing their isolated module; do not leave collection-order contamination as accepted baseline noise.
- Release verification also compiles all shipped Python, runs extension tests, rebuilds both generated web targets, and validates the `.ankiaddon` contents.
