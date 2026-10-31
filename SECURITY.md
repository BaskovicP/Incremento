# Security Policy

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Send the maintainer a private report through the repository host's private security-advisory channel. Include the affected version, impact, minimal reproduction, and a suggested mitigation if known.

Do not include Anki databases, `user_files`, card or note content, profile/deck/tag names, local paths, URLs, browser history, API keys, cookies, or extension tokens. The **Incremento → Export Support Bundle…** output is designed for ordinary bug reports, but it should still be reviewed before sharing.

## Security boundaries

- The opt-in MCP endpoint binds only `127.0.0.1:8767`, validates Host/Origin, and requires its own private per-profile token. Browser extension authentication cannot authorize it. Read-only mode hides and rejects writes; queued work rechecks permission and collection/generation. Timeouts cancel queued work; already-running Anki operations may finish. Request IDs prevent replay within a server lifetime. Fixed tools expose bounded content and reversible data edits, never generic SQL, code, filesystem, or native-action execution. Retrieved text is untrusted data and enters the AI client's/provider's context. Tokens are excluded from backups and connector bundles. Support diagnostics must never record tokens or tool arguments/results.
- Every MCP data mutation writes a bounded private reversal record before changing user data. Per-profile atomic history and request outcomes survive restarts; corrupt/unsafe/concurrently replaced history fails closed. Reversals validate exact affected state, schema and ownership, preserving newer edits/reviews and excluding sync transport counters and derived Anki modification timestamps from semantic comparisons. Created notes/cards restore through native Anki packages, never direct collection SQL. Import reversal moves only tracked managed copies into private retained storage and preserves originals. Preview plans use fixed validated tools and reject stale state; generic/nested execution remains prohibited. Open native writing editors block competing file edits. Full history refuses new writes without evicting reversals; pending outcomes require state inspection/revision confirmation. Histories, retained packages and snapshots never enter support diagnostics, connector bundles, or release artifacts. Private full profile backups include them; authorization tokens remain excluded.

- Advanced MCP schema/type edits require exact previews and full-sync acknowledgement; managed Incremento note types remain protected. Restores verify native recovery packages and dependency identities before removing live notes, and never write collection SQL. Rich HTML/CSS strips active content and remote resources; selected attachments use unique names, byte/type checks, retained originals and newer-reference guards. OCR uses only discovered local Tesseract with bounded raster headers, pixels, input/output/time and owned-process cleanup; no runtime/model downloads or remote image fetches occur. PDF OCR overrides require the source hash to match. Meaning search and smart lists are bounded offline profile files, never code or external-service configurations. Stale index cursors, rules, query candidates and malformed stores fail closed. New private corpus/OCR/rule files and recovery assets must not enter diagnostics, connector bundles or release packages.

- Anki's collection remains canonical for notes, cards, scheduling, revlog, and undo/redo.
- Incremento runtime data is isolated below `user_files/<profile>/` and is never included in release packages.
- Imported EPUB/PDF/web content is untrusted. Readers block remote/local cross-boundary requests and bridge only bounded, authenticated messages.
- The companion bridge listens on `127.0.0.1`, accepts one exact extension origin from the selected browser (Chrome by default, or Firefox), rotates its token on restart or browser selection changes, and bounds request size and concurrency. This protects against ordinary webpages; it is not a defense against malicious local software or a separately installed extension with permission to forge local requests.
- Wire JSON always crosses import normalization; supplying internal-looking keys cannot grant prepared-file ownership or bypass batch limits. Only in-process normalized requests can use the internal preparation path. Queued collection access rechecks the original extension origin/token after downloads and main-thread waits. Revoked in-flight requests fail without requesting an automatic retry into the next profile, and work that times out while still queued cannot execute later. Already-running operations are not forcibly interrupted.
- The companion extension uses temporary `activeTab` access for user-triggered actions on ordinary HTTP(S) pages; required hosts are limited to supported media providers and loopback. Persistent HTTP(S) access is a separate, explained popup opt-in and its dynamic content script is removed when permission is revoked. Browser-side PDF fallback is HTTP(S)-only, streamed under a 48 MiB cap, validates redirects and file signatures, and capture payloads have local text/image/count limits before the bridge validates them again.
- An Anki-initiated CAPTCHA handoff may use separately granted optional access to the requested site (and known archive aliases). Its read-only verification watcher is restricted to that pending tab and main frame; unrelated pages are never captured. The loopback handoff landing page is inert, has no request/user data, sends no-store/no-referrer headers and a deny-all CSP, and accepts only the exact loopback Host. Its random fragment identifies one expiring import and is never a bridge authentication token. Describe/submit/fail RPCs retain protocol-2 exact-origin/token authentication. At most four handoffs and 2,000,000 HTML characters per snapshot are held in memory, for at most ten minutes. Source path/query matching, profile/generation checks, cancellation, and single consumption prevent unrelated, stale, or duplicate imports. HTML still goes through the guarded offline PDF exporter and journaled PDF manager; no browser cookies or credentials are transferred.
- Server-side URL fetches reject credentials, private/loopback/link-local/special addresses, unsafe redirects, and oversized responses. Literal hosts, DNS results, and connected-peer checks share the public-unicast rule, including rejection of IPv4-mapped multicast addresses.
- Webpage-to-PDF captures bounded CSS, fonts, and images through that public-network boundary before rendering. The isolated renderer disables JavaScript and can load only embedded data and its own generated temporary HTML document; other local files and network requests remain blocked. Temporary snapshots are removed after printing, including failures.
- The optional dynamic webpage exporter runs Playwright/Chromium in a disposable subprocess and fresh non-persistent browser context. All page/resource requests are fulfilled by the guarded public-network client, with 8 concurrent downloads, 256 fetched resources, 8 MiB per response, 64 MiB total, and a shared deadline. Direct browser networking uses a nonfunctional proxy; WebSockets, service workers, non-proxied WebRTC, downloads, subframes, permissions, and non-GET requests are blocked. Browser sandboxing remains enabled. PDFs are capped at 48 MiB. Cancellation, profile switches, and the outer timeout terminate the owned worker/browser tree and remove temporary files. Setup is explicit; its package/browser downloads live under excluded `.dependencies/` and are never included in a release archive.

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

- Native MCP workflows use a fixed action/schema registry and bounded cross-store checkpoints. Collection-package restorations require closed reviewer/writing contexts; full restores with a configured sync account require automatic collection/media sync off. Sync, profile switching and add-on installation/removal are status-only because their external effects cannot be fully reversed. Media engines prepare private files before bounded publication, and native collection calls recheck the captured profile. Stale queued jobs cannot claim intervening edits as their own undo. Explicit unused-file quarantine rejects native media references, encoded note references and unsaved drafts. Recovery packages and UI receipts stay private and excluded from releases, connector bundles and diagnostics.
