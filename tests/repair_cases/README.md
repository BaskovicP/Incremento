# Repair-loop evaluation corpus

These cases evaluate the repair harness itself. They must contain only synthetic,
reviewable data—never support bundles, card/note text, real profile names, real
local paths, real URLs, credentials, or other user data. Guard cases may use an
obviously synthetic `.invalid` address, placeholder path, or fake token to prove
that the corresponding input is rejected.

`guard` cases run offline and belong in CI. `repair` cases may name a historical
Git `base_ref` containing a known bug and are run manually with
`--run-repair-cases`; they invoke Codex, create isolated worktrees, and write one
artifact bundle per case. Add a case whenever a real incident exposes a new
repair-loop failure mode, but rewrite it into the smallest synthetic example.

For a `repair` case, set `operation` to `repair_pipeline`, use a structured
incident as `input`, and define the artifact contract in `expected`:

```json
{
  "status": "candidate_ready",
  "minimum_score": 90,
  "required_paths": ["backend/example.py"],
  "forbidden_paths": ["AGENTS.md", "SECURITY.md", "scripts", "user_files"]
}
```

Required paths must appear in the persisted iteration evidence. A forbidden
path also forbids all descendants. Scoring additionally requires a meaningful
red reproducer and `human_review_required: true`; a model's final prose alone
can never pass an eval.

Validate the committed guard corpus with:

```bash
.venv/bin/python scripts/llm_repair_eval.py tests/repair_cases --deterministic-only --json
```

Run authorized repair cases with an artifact directory outside the repository:

```bash
.venv/bin/python scripts/llm_repair_eval.py tests/repair_cases \
  --run-repair-cases --output-dir /tmp/incremento-repair-evals
```
