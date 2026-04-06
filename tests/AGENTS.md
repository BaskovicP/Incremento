# Tests Agent Notes

Use this file for work in `tests/`.

## Test Environment

- Use `.venv/bin/python`.
- `tests/conftest.py` sets the active profile to `TestProfile`, so test DB and path helpers use `user_files/TestProfile/`.
- Prefer focused regression tests for the subsystem you change, then run the full suite when the change is broad enough to justify it.

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
```

## Expectations

- If you change browser import behavior, cover backend normalization and extension-facing behavior.
- If you change profile-aware paths or migration behavior, keep assertions explicitly profile-scoped.
- If you change reviewer or dock behavior, prefer regression tests that exercise the user-visible state transition instead of only helper internals.
