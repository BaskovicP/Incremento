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

## Tests / Checks

Use `.venv/bin/python`.

Full suite:

```bash
.venv/bin/python -m pytest tests/ -q
```

If the local environment lacks `pytest-cov` but `pytest.ini` expects it, use:

```bash
.venv/bin/python -m pytest -o addopts= tests/test_add_card_dock.py -q
```
