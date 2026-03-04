# Incremento Add-on - AI Agent Guide

This repository is an Anki add-on. Use this file as the working agreement for AI agents.

## Goals
- Keep the add-on stable and backwards-compatible with existing Anki data.
- Prefer small, safe changes with clear reasoning.
- Avoid breaking user configuration and settings.

## Project Context
- Entry points: `__init__.py` and modules under `utils/`.
- User data: stored under `user_files/`.
- Configuration: `config.json`.

## Working Rules
- Favor small, isolated edits. Avoid large refactors unless requested.
- Do not delete or overwrite user data in `user_files/`.
- Do not change `config.json` defaults unless explicitly requested.
- Use `rg` for search when possible.
- Keep changes ASCII unless the file already uses Unicode.

## Quality Checklist (Before Finishing)
- Run tests or at least a basic import check if feasible.
- Ensure new code paths handle missing config gracefully.
- Avoid network access unless explicitly required.
- Confirm the add-on still loads by verifying module imports.

## Running Tests

```bash
cd "/Users/paulobaskovic/Library/Application Support/Anki2/addons21/incremento"
.venv/bin/python -m pytest tests/ -v
```

Or activate the venv first:

```bash
source .venv/bin/activate
pytest tests/ -v
```

Common variants:

```bash
# Single test file
.venv/bin/python -m pytest tests/test_scheduler.py -v

# Single test
.venv/bin/python -m pytest tests/test_scheduler.py::TestEdgeCases::test_returns_none_when_no_topic_cards -v
```

## When Unsure
- Ask for clarification before making irreversible changes.
- Prefer a safe, conservative implementation over cleverness.


