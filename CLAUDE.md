# Incremento — Codebase Guide

## Overview

Incremento is an Anki addon for incremental learning. It schedules a mixed session of topic cards (concept notes) and item cards (flashcards/Q&A), places them in a filtered deck, and records statistics per scope.

**Runtime:** Python 3.14
**Venv:** `.venv/` at project root
**Run tests:** `.venv/bin/python -m pytest tests/ -q`
**Current test count:** 60 tests, all passing

---

## File Map

```
__init__.py                  — addon entry point; registers menu actions
utils/
  cards.py                   — Anki card query helpers (_sort_by_due, get_* functions)
  scheduler.py               — card selection logic (soft_pick, get_card_from_scheduler)
  scheduler_config.py        — SchedulerConfig dataclass + load_scheduler_config()
  learn_dialog.py            — SchedulerConfigDialog (pre-session settings UI)
  statistics.py              — StatsManager + load/save/delete helpers
  stats_dialog.py            — StatsDialog (post-session/historical statistics viewer)
tests/
  conftest.py                — mocks anki/aqt before any import; adds utils/ to path
  test_scheduler.py          — scheduler + card selection tests
  test_statistics.py         — StatsManager tests (uses importlib to avoid stdlib shadow)
```

---

## Architecture & Data Flow

```
learnFunction() [__init__.py]
  └─ SchedulerConfigDialog.exec()     — user configures session
  └─ _pick() loop                     — calls get_card_from_scheduler() N times
       └─ get_card_from_scheduler()   — soft_pick for type/mode/tag, queries cards.py
       └─ stores card metadata in _picked_meta (does NOT record stats here)
  └─ filtered deck created via Anki protobuf API
  └─ reviewer_did_answer_card hook    — records stats only on actual review
  └─ reviewer_will_end hook           — shows summary, removes hooks, updates _session_counts
```

**Critical invariant:** `stats.record()` is called only inside `_on_card_answered` (the reviewer hook), never during the picking loop. This ensures daily/lifetime scopes only count cards the user actually reviewed, not just scheduled ones.

---

## SchedulerConfig (`utils/scheduler_config.py`)

Dataclass holding all session parameters:

| Field | Type | Default | Notes |
|---|---|---|---|
| `session_card_count` | int | 50 | cards to schedule |
| `topics_rate` | float | 0.9 | share of topic cards (0–1) |
| `random_rate` | float | 0.99 | share of random-mode picks (0–1) |
| `use_tags` | bool | False | True when tag rows exist |
| `tag_weights` | dict | {} | `{tag: normalised_weight}` |
| `include_rest` | bool | True | fill remaining slots after tag phases |
| `scheduler_scope` | str | "session" | which scope drives the debt counter |
| `day_end_time` | str | "00:00" | HH:MM logical day boundary |
| `priority_order` | list | ["tags","type","mode"] | hard-enforcement order |
| `enforce_priority` | bool | True | False = soft debt-based ordering |
| `topics_filter` | str | "deck:Topics" | Anki search for topic cards |
| `items_filter` | str | "-deck:Topics" | Anki search for item cards |
| `include_new` | bool | True | include is:new |
| `include_learning` | bool | True | include is:learn |
| `include_due` | bool | True | include is:due |

`ready_filter` is a computed property that builds the `(is:new OR is:learn OR is:due)` clause from the three include_* booleans. Falls back to `is:new` if all are unchecked.

---

## Card Fetching (`utils/cards.py`)

All four public fetch functions call `_sort_by_due()` which fetches `card.due` for every ID and sorts ascending (most overdue / lowest position first). This makes `cards[0]` correct for priority mode without any extra logic in the scheduler.

```python
_sort_by_due(card_ids)                    # sort by card.due ascending
get_all_topic_cards(topics_filter, ready_filter)
get_all_item_cards(items_filter, ready_filter)
get_topic_cards_by_tag(tag, topics_filter, ready_filter)
get_item_cards_by_tag(tag, items_filter, ready_filter)
```

All parameters have defaults matching original behaviour; callers pass them through from `SchedulerConfig`.

---

## Scheduler (`utils/scheduler.py`)

`soft_pick(weights, counts, alpha, epsilon)` — debt-based weighted random selection. Computes a "debt" for each key (`weight * n - count`) and samples proportionally. Prevents any one bucket from being over-represented over time.

`get_card_from_scheduler(...)` — orchestrates one card pick:
1. `soft_pick` (or `force_card_type`) chooses topics vs items
2. `soft_pick` (or `force_mode`) chooses random vs priority
3. Fetch candidates via `cards.py`; fallback to the other card type if empty
4. Return `SchedulerResult(card, card_type, tag, mode)`
5. In priority mode, `cards[0]` is automatically the most overdue (sorted by `_sort_by_due`)

---

## Statistics (`utils/statistics.py`)

### Scopes
- **session** — in-memory only; reset each time `learnFunction` runs
- **daily** — persisted to disk; keyed by effective date (respects `day_end_time`)
- **lifetime** — persisted to disk; cumulative

### StatsManager
```python
sm = StatsManager(addon_dir, day_end_time="00:00")
counts = sm.counts_for(scope)      # returns a REFERENCE — mutated in-place by learnFunction
sm.record(result, scheduled_scope) # updates the OTHER two scopes + saves to disk
```

`record()` skips the `scheduled_scope` (that scope's counts are mutated live during picking to drive `soft_pick` debt). All other scopes get updated and saved.

### Disk format
```json
{
  "daily":    {"date": "2026-03-21", "counts": {"type": {}, "tags": {}, "mode": {}}},
  "lifetime": {"type": {}, "tags": {}, "mode": {}}
}
```
File: `user_files/custom_learn_stats.json`. Written atomically via `.tmp` + `os.replace`.

### Delete / export helpers (module-level)
```python
load_stats(addon_dir)                 # returns raw dict or {}
save_stats(addon_dir, stats)          # atomic write
delete_daily_stats(addon_dir)         # removes "daily" key, re-saves
delete_lifetime_stats(addon_dir)      # removes "lifetime" key, re-saves
delete_all_stats(addon_dir)           # unlinks the file
```

---

## Session Stats Flow in `__init__.py`

```python
_session_counts: dict = {"type": {}, "tags": {}, "mode": {}}  # last session snapshot

def _reset_session_counts() -> None:
    global _session_counts
    _session_counts = {"type": {}, "tags": {}, "mode": {}}

# In learnFunction():
_picked_meta: dict[int, dict] = {}   # card_id → {card_type, tag, mode}

# _pick() stores metadata but does NOT call stats.record()

# After all picks:
_session_counts = copy.deepcopy(stats.session)

# Hook registered on filtered deck open:
def _on_card_answered(reviewer, card, ease):
    # called by gui_hooks.reviewer_did_answer_card
    # uses types.SimpleNamespace as fake SchedulerResult to call stats.record()
    # guarded by _reviewed_ids set to prevent double-counting

def _show_summary():
    # gui_hooks.reviewer_will_end — removes both hooks, shows info dialog
```

---

## Learn Dialog (`utils/learn_dialog.py`)

`SchedulerConfigDialog(parent, on_clear_session=None)` — pre-session config UI.

Sections (top to bottom):
1. Cards per session (QSpinBox)
2. Card types: New / Learning / Due-Review checkboxes → drive `ready_filter`
3. Topics ↔ Items slider
4. Live count label (`_counts_lbl`): "Topics: N ready  Items: M ready" in yellow
5. Priority ↔ Random slider
6. Scheduler scope + day-end time
7. Scheduling priority order (3 linked QComboBoxes) + strict/soft toggle
8. Tag quotas: per-tag rows with linked sliders, lock checkbox, live count annotation, remove button
9. Advanced: Topics filter / Items filter (QLineEdit) + Test buttons
10. **Statistics history**: Delete Today / Delete Session / Delete All Time / Delete All History / Export JSON
11. OK / Cancel

Key methods:
- `to_config()` → `SchedulerConfig`
- `save_config()` → writes to `mw.addonManager.writeConfig`
- `_refresh_counts()` — updates counts label + all tag row annotations; triggered by checkbox/filter changes
- `_refresh_tag_count(row_dict)` — per-row count annotation; uses `getattr` guard for setup-order safety
- `_ready_filter_from_checks()` — builds `is:…` clause from checkbox state
- `_rebalance()` / `_on_weight_changed()` — lock-aware linked slider logic
- `_delete_daily/session/lifetime/all` + `_export_json` — statistics management

`_ADDON_DIR` is a module-level constant: `normpath(join(dirname(abspath(__file__)), ".."))`.

---

## Stats Dialog (`utils/stats_dialog.py`)

`StatsDialog(addon_dir, session_counts, day_end_time, parent)` — read-only statistics viewer.

- Scope radio buttons: This Session / Today / All Time
- `_get_counts(scope)` loads from memory (session) or disk (daily/lifetime)
- `_refresh()` rebuilds scrollable content: Total, Card Types bar chart, Selection Mode bar chart, Tags bar chart (sorted descending)
- `_BarChart(QWidget)` — custom QPainter widget; uses `palette().text().color()` for dark-mode compatibility

---

## Testing

**conftest.py key pattern:**
```python
# 'incremento' must be plain ModuleType — not MagicMock — so pytest's
# plugin discovery gets [] for pytest_plugins, not a MagicMock.
sys.modules.setdefault("incremento", types.ModuleType("incremento"))

# Submodules as MagicMock so relative imports auto-stub:
for mod in ("incremento.utils", "incremento.utils.cards",
            "incremento.utils.statistics", "incremento.utils.stats_dialog"):
    sys.modules.setdefault(mod, MagicMock())

# utils/ added to sys.path so `import scheduler` / `import cards` resolve directly
```

**Mocking cards.mw for priority sort tests:**
```python
with patch("cards.mw") as mock_mw:
    mock_mw.col.find_cards.return_value = [201, 202, 203]
    mock_mw.col.get_card.side_effect = lambda cid: mock_cards[cid]
    with patch("scheduler.soft_pick", side_effect=["items", "priority"]):
        result = scheduler.get_card_from_scheduler(use_tags=False)
```

**test_statistics.py** uses `importlib.util.spec_from_file_location` to import `utils/statistics.py` directly, avoiding shadowing the stdlib `statistics` module.

**Lambda signatures in `_mock_card_utils`:** all tag-taking lambdas use `lambda tag, **kw:` and tagless ones use `lambda **kw:` to absorb `topics_filter`/`items_filter`/`ready_filter` kwargs added when those params were introduced.

---

## Gotchas

- `stats.record()` must never be called during picking — only inside `reviewer_did_answer_card`. Calling it during picking incorrectly inflates daily/lifetime counts before any review.
- `counts_for(scope)` returns a live reference. The picking loop mutates it in-place to drive `soft_pick` debt for the active scope.
- `_sort_by_due` calls `mw.col.get_card` once per card ID — acceptable for typical session sizes (≤500 cards).
- The `day_end_time` boundary shifts the logical date: if it's `04:00` and the wall clock is `03:30`, `_effective_date` returns yesterday's ISO string.
- Filtered deck uses Anki's protobuf API (`get_or_create_filtered_deck` / `add_or_update_filtered_deck`) — requires Anki 2.1.45+.
- `fdu.config.reschedule = True` is set so cards return to their original deck after review with updated scheduling.
