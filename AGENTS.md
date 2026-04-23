# Incremento Agent Notes

Compact repo guide for coding agents. Keep this file high-signal and current.

## Repo Shape

- `__init__.py`: addon entry point, hook registration, settings save/load, reviewer patches, bridge startup.
- `backend/`: scheduling, persistence, import logic, profile-aware path helpers, browser bridge.
- `frontend/`: Qt dialogs/docks plus React source for the PDF viewer.
- `chrome_extensions/incremento_companion/`: Chrome extension for imports, browser capture, bookmark import, and playback sync.
- `web/`: shipped web assets exported by Anki.
- `tests/`: Python regression suite.
- `user_files/`: runtime data only. All user data is per-profile.

Important newer hotspots:

- `backend/knowledge_tree.py`, `backend/knowledge_tree_postpone.py`, `frontend/knowledge_tree_dialog.py`: the knowledge-tree workspace, branch study, branch priority tools, postpone flow, and subset review.
- `backend/note_metadata.py`: shared Incremento provenance fields and helpers. New note-creation paths should use this instead of appending source/parent text into content fields.
- `backend/video_manager.py`, `frontend/video_dock.py`: video import, deferred local download, subtitle management, and local dual-caption playback.
- `backend/custom_schedule.py`, `frontend/custom_schedule_dialog.py`: browser-side custom scheduling rules and their dialog/workflow.
- `frontend/reviewer_priority_badge.py`: reviewer overlay that shows priority, topic A-factor, saved browser time, and active custom schedule at a glance.
- `frontend/writing_dock.py`: markdown writing dock with per-card editor state, word-progress counters, and configurable word-count mode.

## Read The Local Guide

- If you work in `backend/`, read `backend/AGENTS.md`.
- If you work in `frontend/`, read `frontend/AGENTS.md`.
- If you work in `chrome_extensions/incremento_companion/`, read `chrome_extensions/incremento_companion/AGENTS.md`.
- If you work in `tests/`, read `tests/AGENTS.md`.

## Per-Profile Data Isolation

All runtime data lives under `user_files/<ProfileName>/`, not flat in `user_files/`.

```text
user_files/
└── MyProfile/
    ├── incremento.db
    ├── custom_learn_stats.json
    ├── pdfs/
    ├── epubs/
    ├── epub_extracted/
    ├── videos/
    ├── writing/
    ├── video_profile/
    └── web_profile/
```

Key modules:

- `backend/paths.py`: central path construction. Keep it pure; do not import Anki here.
- `backend/migration.py`: idempotent migration from legacy flat `user_files/` to `user_files/<profile>/`.

Preferred profile import pattern in backend modules:

```python
try:
    from .paths import get_active_profile as _active_profile
except ImportError:
    from paths import get_active_profile as _active_profile
```

Frontend modules that already import `_paths` should use `_paths.get_active_profile()`.

## Hard Boundaries

- Do not put shipped code or assets inside `user_files/`.
- Keep all runtime and user content per-profile.
- Shipped HTML, JS, and CSS belong under `web/`.
- Any helper that returns a path under `user_files/` must go through `backend/paths.py`.
- When adding functions that read or write under `user_files/`, thread `profile` from the call site instead of reaching for global state deep inside helper stacks.

## Cross-Cutting Rules

- Preserve profile-aware error paths so users can locate files under `user_files/<profile>/...`.
- Avoid touching `user_files/` unless the task is explicitly about migration or cleanup.
- When moving shipped assets, update both source references and generated or runtime references.
- If you change PDF viewer React source or extension source, rebuild before finishing.
- Keep provenance in dedicated `Incremento_*` note fields. Do not reintroduce inline `Source:` / parent blocks into the main content field for new notes.
- Knowledge-tree nodes are card-backed. One tree node maps to one `card_id`, with at most one parent and any number of children.
- If a knowledge-tree action is exposed in multiple places such as toolbar, inspector, and context menu, keep those entry points aligned.
- Writing-card editor state is per card and persisted in SQLite. Writing progress counters are also per card; `session` means the current open session for that writing card.
- Custom-schedule badges in the reviewer should appear only when a real rule exists for that card; missing rules must not fall back to the default preset text.

## Tests / Checks

Use `.venv/bin/python`.

Full suite:

```bash
.venv/bin/python -m pytest tests/ -q
```

Useful focused suites:

```bash
.venv/bin/python -m pytest -o addopts= tests/test_knowledge_tree.py tests/test_db.py tests/test_session_selection.py -q
.venv/bin/python -m pytest -o addopts= tests/test_note_metadata.py tests/test_browser_bridge.py tests/test_pdf_manager.py tests/test_video_web.py -q
.venv/bin/python -m pytest -o addopts= tests/test_reviewer_priority_badge.py tests/test_custom_schedule.py -q
.venv/bin/python -m pytest -o addopts= tests/test_db.py tests/test_writing_dock.py -q
```

If the local environment lacks `pytest-cov` but `pytest.ini` expects it, use:

```bash
.venv/bin/python -m pytest -o addopts= tests/test_add_card_dock.py -q
```
