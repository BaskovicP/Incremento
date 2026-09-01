# Security Policy

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Send the maintainer a private report through the repository host's private security-advisory channel. Include the affected version, impact, minimal reproduction, and a suggested mitigation if known.

Do not include Anki databases, `user_files`, card or note content, profile/deck/tag names, local paths, URLs, browser history, API keys, cookies, or extension tokens. The **Incremento → Export Support Bundle…** output is designed for ordinary bug reports, but it should still be reviewed before sharing.

## Security boundaries

- Anki's collection remains canonical for notes, cards, scheduling, revlog, and undo/redo.
- Incremento runtime data is isolated below `user_files/<profile>/` and is never included in release packages.
- Imported EPUB/PDF/web content is untrusted. Readers block remote/local cross-boundary requests and bridge only bounded, authenticated messages.
- The companion bridge listens on `127.0.0.1`, accepts one exact Chrome-extension origin per run, rotates its token on restart, and bounds request size and concurrency. This protects against ordinary webpages; it is not a defense against malicious local software or a separately installed extension with permission to forge local requests.
- The companion extension uses temporary `activeTab` access for user-triggered actions on ordinary HTTP(S) pages; required hosts are limited to supported media providers and loopback. Persistent HTTP(S) access is a separate, explained popup opt-in and its dynamic content script is removed when permission is revoked. Browser-side PDF fallback is HTTP(S)-only, streamed under a 48 MiB cap, validates redirects and file signatures, and capture payloads have local text/image/count limits before the bridge validates them again.
- Server-side URL fetches reject credentials, private/loopback/link-local/special addresses, unsafe redirects, and oversized responses.

## Automated repair policy

`scripts/llm_repair_loop.py` can turn a sanitized report into a local review candidate. It is deliberately artifact-only: no outcome grants authority to apply, commit, push, open a pull request, publish, deploy, merge, message a reporter, or modify a live Anki profile.

### Input and isolation

- Reports are bounded UTF-8 text stored outside the repository. URLs, absolute home paths, and credential-like values are rejected. Structured reports accept a fixed incident schema and only privacy-safe add-on, Anki, OS-family, and Python environment fields.
- Incident content and verifier feedback are JSON-framed as untrusted evidence. They cannot close their prompt delimiter and do not become instructions.
- A stable SHA-256 incident fingerprint, not the raw incident, enters the run ledger.
- The selected `--base-ref` must resolve safely to a commit. The loop creates a detached Git worktree outside the source repository, excludes ignored runtime `user_files`, and links only known local toolchains for offline use. Dirty or active source checkouts are left untouched; uncommitted changes are intentionally absent from the candidate.

### Role and permission separation

The workflow uses fresh, ephemeral model sessions with schema-constrained results:

1. The reproducer can write only test roots. It must add exactly one small fingerprint-named regression without changing existing tests or production code, and the fixed verifier must observe a real assertion failure rather than a collection/environment error.
2. The repair role can write production files but cannot write tests, runtime data, automation/control files, CI, manifests, locks, or dependency trees. The reproducer remains immutable. A `blocked`, `not_reproduced`, or `needs_authority` result may not leave edits behind.
3. Deterministic verification runs in a separate offline, stripped-environment, read-mostly sandbox. Only bounded scratch space and generated bundle directories are writable; generated output is compared and restored after each build.
4. The critic is an independent read-only pass. Failed deterministic gates always score zero, and a candidate with high/critical findings or missing tests cannot be approved regardless of the numeric score.

All model stages disable web search and command-network access, use `approval_policy="never"`, ignore personal Codex configuration and exec-policy rules, deny common environment/credential/private-key files, and receive isolated HOME/TMP/cache locations. Agent JSONL and verifier output are size-bounded in memory and sanitized before any evidence is persisted.

### Verification, stopping, and evidence

- A green committed baseline is required before reproduction.
- Focused gates are selected from actual changed paths plus incident risk tags, including bridge/network security, storage rollback/recovery, scheduling lifecycle, concurrency, reader/UI, performance, and Anki compatibility suites.
- Every candidate must also pass dependency, compile, full Python, extension, generated-asset, and diff checks. An optional real-Anki gate is described below.
- Iterations, diff size, report size, stage output, per-command time, repeated failures, and non-improving scores are bounded. Product ambiguity stops as `needs_authority`.
- Artifacts must be outside the repository. `candidate.patch`, `reproducer.patch`, and `run.json` contain hashes and privacy-sanitized evidence. A successful status means only `candidate_ready`; `human_review_required` remains true.
- `tests/repair_cases/` contains a strict synthetic eval corpus. Offline guard cases run in CI; explicitly authorized historical repair cases can exercise the full loop and are scored from the persisted artifact, including required and forbidden changed paths.

### Optional real-Anki smoke gate

`--anki-smoke` copies only shipped candidate files into a new empty Anki base. It rejects symlinked/nonempty bases, excludes `user_files`, development files, dependency trees, and local `meta.json`, creates synthetic non-updating metadata, and adds a load marker only to the disposable copy. Anki then runs inside a separate filesystem sandbox with direct network disabled and a secret-stripped environment. Success requires the add-on entry point to finish loading and the process to remain alive; teardown targets only the process group started by the harness. This gate never opens a real profile and is opt-in because it launches a GUI application.

Run it with a sanitized report and an empty artifact directory outside the repository:

```bash
.venv/bin/python scripts/llm_repair_loop.py /tmp/incremento-incident.json \
  --base-ref HEAD \
  --max-iterations 2 \
  --output-dir /tmp/incremento-repair-result
```

This is defense in depth, not proof that a model-generated patch is correct or safe. A maintainer must inspect the patch, confirm the test expresses intended behavior, review residual risk, and choose whether to reproduce or apply it. If a report includes a support bundle, inspect the bundle separately; never feed binary attachments, raw logs, databases, or user content into the model.
