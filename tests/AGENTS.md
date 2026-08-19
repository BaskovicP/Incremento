# Tests Agent Notes

Use this file for work in `tests/`.

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
.venv/bin/python -m pytest -o addopts= tests/test_db.py tests/test_writing_dock.py -q
.venv/bin/python -m pytest -o addopts= tests/test_statistics.py tests/test_stats_dialog.py tests/test_timer_widget.py tests/test_session.py tests/test_scheduler.py -q
```

## Expectations

- If you change browser import behavior, cover backend normalization and extension-facing behavior.
- If you change profile-aware paths or migration behavior, keep assertions explicitly profile-scoped.
- If you change reviewer or dock behavior, prefer regression tests that exercise the user-visible state transition instead of only helper internals.
- Item-card `Fail / Pass` regressions must cover every Anki state: `Fail` remains `Again` (ease 1), and `Pass` becomes `Good` (ease 3), including learning and relearning cards. Keep topic-card behavior separate.
- Topic-button regressions must verify configurable immediate scheduling: `More` subtracts its configured percentage, `Same` stays at 100%, and `Less` adds its configured percentage to the normal A-factor interval, with matching labels, persisted precise intervals, rounded due dates, and future A-factor changes. Cover defaults, config normalization, settings persistence, and custom percentages.
- If you change note creation or import provenance, assert that metadata lands in dedicated `Incremento_*` note fields and not inline in the main content field.
- If you change knowledge-tree behavior, cover both raw structure helpers and a user-facing consumer such as branch study, postpone, subset review, or branch-summary formatting.
- If you change session selection or refill behavior, cover `tests/test_session_selection.py`, `tests/test_session.py`, and any `frontend/learn_dialog.py` save/load wiring affected by `include_new` or `auto_refill_session`.
- If you change settings dialog fields, config defaults, or config-backed normalization, cover `tests/test_settings_dialog.py` plus the subsystem-specific helper tests that consume those values.
- If you change video-card behavior, cover both backend media helpers and the frontend-facing flow that consumes them.
- If you change writing-card behavior, cover both DB persistence and the dock-side helper/config behavior. Writing stats are per card, and the current-card session resets on reopen.
- If you change custom scheduling or the reviewer badge, add a regression for the “missing rule” case so schedule text does not appear by default.
- If you change Browser quick tags, cover complete-set deduplication, case/order-insensitive persisted identity, row-major nine-position layout, no promotion on reuse, new-tag admission, automatic versus fixed mode, nine fixed-slot persistence/validation, reserved green for `topic`, custom-color persistence/reset, and collision-free effective colors. The focused files are `tests/test_reviewer_tags.py`, `tests/test_tag_colors.py`, and `tests/test_db.py`.
- If you change stats normalization or export behavior, cover `StatsManager`, `custom_learn_stats.json`, `export_stats_json()`, dirty input cleanup, file-first loading, and DB fallback/export compatibility.
- If you change EPUB/PDF scheduling or review-time attribution, assert concrete `pdf` and `epub` card types stay separate in scheduler results, persisted stats, and runtime session time.
- If you change stats dialog helpers, cover summary metrics, EPUB labels/colors, review-time formatting, and hidden synthetic tags such as `__no_tags__`.
- If you change timer activity behavior, cover PDF and EPUB page counters separately, per-report reset after summaries, cumulative daily totals, and reset on scheduler logical-day changes.

## Current Baseline

- As of 2026-04-18, the full suite has one known unrelated failure in `tests/test_epub_manager.py` around section-title casing (`chapter1` vs `Chapter 1`). Treat that as existing baseline noise unless your change touches EPUB extraction.
