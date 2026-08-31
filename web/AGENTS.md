# Shipped Web Asset Agent Notes

Use this file for work in `web/`. These files ship inside the Anki addon and execute in Qt WebEngine or card-rendering contexts.

## Source and Ownership Map

- `pdf_dock.html`: hand-maintained host page for the React PDF reader. It defines the root DOM/loading contract and strict Content Security Policy, and loads vendored PDF.js plus the generated viewer bundle.
- `web/dist/pdf_viewer.js`: committed generated output from `frontend/src/` via `frontend/vite.config.js`. Never hand-edit it.
- `pdfjs/pdf.min.js`, `pdfjs/pdf.worker.min.js`, and `pdfjs/pdf.sandbox.min.js`: vendored/minified PDF.js runtime. Treat them as dependency artifacts, not local source files.
- `video_player.html`: hand-maintained YouTube iframe wrapper used by the remote-playback path.
- `web_dock_bridge.js`: hand-maintained JavaScript template injected by `frontend/web_dock.py` for tracked webpage progress, bookmarks, snapshots, and media state.

## Generated PDF Viewer

- Make behavior changes in `frontend/src/`, run its Node tests, then rebuild:

```bash
npm --prefix frontend test
npm --prefix frontend run build
```

- `frontend/vite.config.js` owns output format/path. The host expects one bundle at `web/dist/pdf_viewer.js`; keep the Vite target and `pdf_dock.html` script loading aligned.
- Commit source and generated bundle together. Inspect the generated diff for unexpected drift, but review the source and source-level tests as the behavioral authority.
- Link handling, anchor locations, and Jump Back logic have pure source modules/tests. Preserve the default-off link toggle, validated PDF annotation targets, internal-destination limits, current-card/nonce bridge checks, and bounded back stack.
- Changes to host DOM IDs, global startup functions, bridge command names, or data attributes are cross-language API changes and require aligned updates in `frontend/pdf_dock.py`, React source/tests, Python regression tests, and manual documentation.

## Host and Content Security

- Keep `pdf_dock.html` CSP least-privileged. Do not add remote script/style/font origins, `unsafe-eval`, wildcard sources, or inline execution merely to simplify a build. Any CSP change needs an explicit threat-model review and reader regression.
- PDF/EPUB content is untrusted. It must not gain arbitrary network navigation, local-file enumeration, top-level navigation, Anki bridge access, or script execution through a host-page change.
- Remote external links are opt-in, normalized to uncredentialed HTTP(S), and opened by Python in the system browser after nonce/current-card validation. Internal links remain in the active document. The web view itself must not navigate to them remotely.
- Treat messages from WebEngine JavaScript as attacker-controlled strings. Python owns command allowlists, type/size/range checks, card identity, nonce validation, profile checks, and local path containment.
- Avoid embedding user titles, filenames, URLs, selections, or card content into executable JavaScript. Pass serialized data through the established escaped/template boundary.

## Vendored PDF.js

- Do not edit `pdfjs/*.min.js` directly. For an intentional upgrade, record the upstream version/source, replace the related main/worker/sandbox set together, verify licenses/notices, and test worker compatibility with the current host CSP and Qt WebEngine.
- Keep the worker path local and packaged. A CDN fallback would leak document usage and break offline reading.
- Verify PDF rendering, highlights, internal/external links, search, and large-document cancellation after an upgrade.

## Video Player

- `video_player.html` is the YouTube iframe wrapper used by Incremento's remote-playback path. Keep its `startVideo(videoId, startSec)` API aligned with `frontend/video_dock.py` and backend provider helpers. The separate local-video/caption overlay is assembled by the Python dock and does not live in this file.
- Validate provider/media identifiers and timestamps before interpolating or seeking. Do not accept arbitrary HTML/player script URLs from card fields.
- Preserve bounded progress events and teardown. Reopening/switching cards must stop the old player from continuing to report time against the new card.
- Remote provider limitations are real; do not claim local caption-overlay parity when provider playback cannot support it.

## Web Dock Bridge Template

- `web_dock_bridge.js` contains placeholders substituted by `frontend/web_dock.py`. Keep placeholder names, escaping, message prefix/nonce, and current-card validation aligned with Python.
- Progress/media events must be throttled and bounded. Bookmarks, snapshots, and resume state must identify only the active tracked card and must stop after navigation/card/profile change.
- The bridge runs in an untrusted remote page context. Page scripts can call or imitate exposed JavaScript, so authorization belongs in Python and the extension/backend; secrecy of function names is not a defense.
- Snapshot and bookmark data are plain untrusted payloads. Do not send cookies, local storage, authorization headers, or arbitrary page resources.

## Packaging and Checks

- `scripts/package_addon.py` explicitly packages `pdf_dock.html`, `video_player.html`, `web_dock_bridge.js`, `dist/pdf_viewer.js`, and the PDF.js directory. Update required runtime paths and `tests/test_package_addon.py` when adding/removing a shipped asset.
- Relevant checks:

```bash
npm --prefix frontend test
npm --prefix frontend run build
.venv/bin/python -m pytest -o addopts= tests/test_pdf_dock.py tests/test_reader_links.py tests/test_video_web.py tests/test_package_addon.py -q
```

- Run `git diff --check` and verify the build leaves only the expected `web/dist/pdf_viewer.js` change. Release packaging must succeed before distributing a new web asset.
