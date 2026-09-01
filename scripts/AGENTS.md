# Scripts Agent Notes

Use this file for work in `scripts/`. These utilities are developer/release tooling, not addon runtime modules.

## Script Map

- `package_addon.py`: stages a clean runtime tree, optionally runs release gates, generates the package-root Anki `manifest.json`, creates a `.ankiaddon`, and validates its contents.
- `repair_pipeline.py`: security boundary and implementation for bounded incident parsing, detached-worktree reproduce/repair/verify/critic stages, deterministic gates, optional disposable-Anki smoke, and review artifacts.
- `llm_repair_loop.py`: compatibility/CLI adapter over `repair_pipeline.py`; keep shared constants and policy in the pipeline instead of forking behavior here.
- `llm_repair_eval.py`: validates the synthetic eval corpus, runs deterministic guard cases in CI, and optionally scores authorized end-to-end repair artifacts.
- `disposable_anki_smoke.py`: copies shipped addon code into an empty external Anki base, launches only that copy under a restricted environment/sandbox, and records bounded startup evidence.
- `mutation_smoke.py`: deterministic targeted mutation gate that copies config normalization and its regressions into a temporary directory and fails if a high-risk mutant survives; it never edits the checkout.
- `generate_icons.py`: deterministic Pillow-based source for the companion extension PNG icon set.

## Release Packaging

- `package_addon.py` is the packaging source of truth. Keep its root-file list, required runtime paths, web assets, extension files, exclusions, and `tests/test_package_addon.py` aligned.
- The minimum supported Anki point version is encoded as `MIN_ANKI_POINT_VERSION` (currently `241100`). Change it only with an explicit compatibility decision and update user documentation.
- Normal packages include shipped Python/docs, `web/` runtime assets, vendored PDF.js, and the extension runtime. They exclude `user_files/`, tests, agent/development files, source dependency trees, caches, local `meta.json` by default, and repository-level build output.
- The package-root `manifest.json` is generated in staging and is unrelated to the Chrome extension's `manifest.json`. Do not add a development root manifest to source just to package the addon.
- `--include-meta` is an explicit local-only escape hatch. Friend/public release artifacts should not inherit local addon state.
- Archive validation rejects missing required assets, corrupt ZIP entries, traversal/absolute names, runtime-data leaks, caches, and developer-only top-level paths. Staging is an explicit trusted-source allowlist; do not add symlinked inputs or broad copy roots without first adding symlink rejection and package tests. Never weaken validation merely to include an unclassified file.
- `--release` runs frontend and extension builds, Ruff/mypy/ESLint, the targeted mutation smoke, Python compilation/tests, extension tests, staging, and archive validation. Use:

```bash
.venv/bin/python scripts/package_addon.py --release --clean-staging
```

- The default output is under repository `dist/`, which is untracked release output. Report the absolute `.ankiaddon` path after packaging; do not commit the archive.

## Repair Pipeline Safety Model

- Repair automation creates a candidate for human review. It must never apply a patch to the source checkout, commit, push, publish, deploy, merge, or edit a live Anki profile.
- Incidents/reports and artifact/worktree destinations must be outside the repository. Inputs are bounded and reject URLs, credentials, email-like data, local absolute paths, and other support/user secrets. Use only privacy-safe structured incident facts.
- Always resolve a committed `base_ref`, require a clean source worktree, create a detached temporary worktree, and link only approved local toolchains. Do not relax source-worktree or runtime-data preflights to make a run convenient.
- The reproduce stage may add only a hash-named regression under an approved test root and must prove a meaningful red assertion. The repair stage may change production code but may not edit the immutable reproducer or any other test.
- Protected paths include agent/security/control files, Git/Codex metadata, workflows, scripts, repair cases, user data, dependency manifests/locks, Vite configs, secret-like basenames/suffixes, and generated assets except through controlled build verification. Keep `PROTECTED_PREFIXES`, `PROTECTED_FILES`, basename/suffix rules, and eval cases aligned.
- Bound report, agent event, command output, diagnostics, diff, iteration count, score threshold, and timeouts. Truncate/sanitize evidence deliberately; do not stream unbounded subprocess output into memory or artifacts.
- Reproducer, repair, verifier, and critic are separate evidence stages. Verify the worktree did not change during read-only verifier/critic stages, compare baseline/candidate gates, and keep generated-output snapshots deterministic.
- A passing model narrative is not evidence. Candidate readiness requires the red reproducer, green deterministic/final gates, acceptable critic result, persisted hashes/records, and `human_review_required: true`.
- Artifact bundles contain reviewable `run.json`, candidate/reproducer patches, and optional smoke evidence only. Do not include raw agent homes, support bundles, full command environments, credentials, live DBs, or uncontrolled logs.
- Extend safety behavior with `tests/test_llm_repair_pipeline.py`, adapter behavior with `tests/test_llm_repair_loop.py`, and synthetic guard cases under `tests/repair_cases/`. Never put real incidents or user data in the corpus.

Deterministic guard command:

```bash
.venv/bin/python scripts/llm_repair_eval.py tests/repair_cases --deterministic-only --json
```

Repair cases invoke Codex and are manual/authorized. Put their artifacts outside the repository:

```bash
.venv/bin/python scripts/llm_repair_eval.py tests/repair_cases \
  --run-repair-cases --output-dir /tmp/incremento-repair-evals
```

## Disposable Real-Anki Smoke

- This is opt-in integration evidence, not a substitute for unit/integration tests. It may start a GUI process and therefore requires explicit authorization and an actual Anki executable.
- The base directory must be empty, non-symlinked, and outside the addon repository. The copy excludes `.git`, agent/Codex files, scripts, tests, dependency trees, caches, `meta.json`, and all `user_files/` content before writing its own synthetic smoke manifest.
- Reject source symlinks rather than following them. Add only the synthetic load probe to the disposable copy; never patch the source entry point.
- Use a sterile environment rooted at the disposable base, disable user-site Python and network access, bind debugging to loopback, and expose only the Anki application plus disposable base to the sandbox.
- Track the exact process group started by the smoke and terminate only that group. Never use broad `pkill`, kill an existing Anki instance, or point `-b` at the developer's normal Anki base.
- Screenshots and page summaries are bounded artifacts and can still reveal synthetic UI state; keep them outside the repository. A startup marker proves load only, not full behavioral correctness.
- Changes require `tests/test_llm_repair_pipeline.py` coverage for gate integration and direct tests of copy, path, environment, process, timeout, and evidence safeguards.

## Icon Generation

- `generate_icons.py` is the editable icon source. It requires Pillow and overwrites `icon-16.png`, `icon-32.png`, `icon-48.png`, `icon-128.png`, and `icon-512.png`.
- Run it only for an intentional icon redesign, inspect each rendered size, and commit the script plus all changed PNGs together. It does not build extension JavaScript.

## Checks

```bash
.venv/bin/python -m pytest -o addopts= tests/test_package_addon.py tests/test_llm_repair_pipeline.py tests/test_llm_repair_loop.py -q
.venv/bin/python scripts/llm_repair_eval.py tests/repair_cases --deterministic-only --json
.venv/bin/python -m compileall -q scripts
```

When packaging code changes, also run a release build and inspect the archive listing. When repair safety changes, run the full Python suite because protected-path and gate selection rules cross many subsystems.
