# Extension Agent Notes

Use this file for work in `chrome_extensions/incremento_companion/`.

## Ownership

- This is a Manifest V3 Chrome extension for Incremento imports, browser capture, bookmark import, link saving, and tracked playback/resume.
- The extension gathers browser-owned data and sends it to bounded backend endpoints. The addon backend owns Anki note creation, provenance fields, profile storage, and final validation; extension-side capture/fetch memory limits still matter before transport.
- `manifest.json` is a security boundary. Permissions, host access, commands, service-worker entry points, content-script scope, and web-accessible resources must match real behavior; do not broaden them as a convenience.

## Source and Runtime Map

- `src/background/main.js`: service-worker orchestration, commands/context menus, tab/frame injection, playback tracking, AnkiConnect compatibility calls, bridge imports, and clipboard fallback.
- `src/content/main.js`: per-page/frame selection, snapshot, media detection/tracking, URL-marker cleanup, and link-save behavior.
- `src/popup/App.jsx` and `src/popup/main.jsx`: popup state and import actions.
- `src/bookmarks/App.jsx` and `src/bookmarks/main.jsx`: bookmark-import orchestration and entry point. `src/bookmarks/components/BookmarkTree.jsx`, `src/bookmarks/components/ImportRows.jsx`, `src/bookmarks/components/ProgressPanel.jsx`, and `src/bookmarks/components/ResultsList.jsx` own the corresponding bounded UI surfaces.
- `src/bookmarks/bookmarkModel.js`: pure bookmark flattening/classification/selection model; keep UI-independent behavior here.
- `src/offscreen/main.js`: narrowly scoped clipboard write handler for service-worker environments without direct clipboard access.
- `src/shared/bridgeAuth.js`: authenticated port `8766` fetch boundary; all Incremento bridge calls pass through it.
- `src/shared/bridge.js`: typed Incremento endpoints and payload transport.
- `src/shared/chromeApi.js`: promise wrappers, tab capture, injection, storage, and Chrome capability fallbacks.
- `src/shared/browserCaptureModel.js`, `linkSaveModel.js`, `pdfFetch.js`, `url.js`, and `writingTitle.js`: deterministic input normalization used by popup/background/content flows and covered by Node tests.
- `content-loader.js`: hand-maintained bootstrap that dynamically imports `dist/content.js`; the manifest keeps it in every HTTP(S) frame.
- `popup.html`, `popup.css`, `bookmarks.html`, `bookmarks.css`, `offscreen.html`, `manifest.json`, `icons/`, `package.json`, and `README.md`: hand-maintained static/configuration files. The package file intentionally uses Node's built-in test runner and does not own the Vite dependency tree.
- `dist/`: committed generated runtime output. `frontend/vite.extension.config.js` maps the five source entry points to `background.js`, `content.js`, `offscreen.js`, `popup.js`, and `bookmarks.js`, plus shared chunks under `dist/assets/`.
- Node coverage is split by pure boundary: `tests/bookmarkModel.test.js`, `tests/bridge.test.js`, `tests/browserCaptureModel.test.js`, `tests/linkSaveModel.test.js`, `tests/pdfFetch.test.js`, `tests/url.test.js`, and `tests/writingTitle.test.js`.

## Trust Boundaries and Bridge Protocols

- Port `8766` is Incremento bridge protocol 2. Obtain the ephemeral token from `/incremento/handshake`, then send `X-Incremento-Token` and `X-Incremento-Protocol` on every data request through `bridgeAuth.js`.
- A `401` allows exactly one fresh handshake and retry. Keep the token only in module memory; never place it in `chrome.storage`, a URL, DOM, log, or clipboard.
- The addon binds one exact `chrome-extension://<id>` origin and enforces request-size/concurrency limits. Preserve the extension `Origin`; do not add proxy/server relays or a direct unauthenticated `fetch()` to port `8766`.
- Port `8765` is the optional AnkiConnect API and is intentionally separate from the Incremento bridge. Its direct JSON request in the background worker must not be copied to Incremento endpoints or treated as bridge authentication.
- The current-tab URL, title, selection, HTML snapshot, bookmark row, provider metadata, media progress, filenames, and fetched bytes are all untrusted. Shared models should normalize early, but backend validation remains mandatory.
- `src/shared/pdfFetch.js` is the browser-side fallback for document URLs that Python cannot retrieve. Preserve response-status, captcha, content-type/signature, and filename handling, while treating backend validation as final authority.
- Snapshot/capture code must not execute captured page HTML or format provenance into content fields. Send raw data through the bounded backend endpoint for inert snapshot handling; add the local pre-transport budgets described below rather than relying only on server rejection.

## Known Hardening Gaps

- `manifest.json` currently carries broad and partly redundant host access (`<all_urls>` plus HTTP(S) patterns) alongside powerful `tabs`, `scripting`, `bookmarks`, clipboard, and navigation capabilities. Treat permission reduction as a release/security task with popup, bookmark, PDF, iframe playback, context-menu, and provider coverage; never add another permission without documenting the exact API call and user-facing need.
- `src/shared/pdfFetch.js` currently materializes `response.arrayBuffer()` without a local byte cap and can accept non-PDF bytes when a URL merely ends in `.pdf` (apart from its specific captcha check). Do not expand this path as though it were bounded. The intended fix needs scheme validation, redirect/final-URL policy, `Content-Length` plus streamed byte limits, unconditional PDF-signature enforcement, filename tests, and an oversized-response regression before behavior changes.
- Full-page capture fallbacks currently materialize `document.documentElement.outerHTML`, and screenshot arrays can grow before the bridge rejects an oversized request. Keep backend request limits intact, but also add explicit extension-side text/image/count budgets when changing capture so a hostile page cannot exhaust extension memory first.
- These are documented limitations, not permission to weaken backend checks or silently drop user data. Surface a clear local error when a future cap is reached and cover it in the relevant shared-model/bridge tests.

## Storage and Lifecycle

- Use `chrome.storage.session` for linked-card/tab and active web-playback tracking state. It is session-scoped by design and must not survive as a durable cross-browser identity map.
- Use `chrome.storage.local` only for user preferences/settings and deliberately persistent convenience state such as the last copied playback time. Do not persist bridge tokens, full snapshots, private browsing contents, or unbounded history.
- Manifest V3 service workers can stop between events. Reconstruct state from the correct storage scope, make listener registration idempotent, and do not rely on process-global timers or variables as durable state.
- Content/background reinjection must preserve `allFrames: true` because embedded players can own the tracked media. Injection may occur repeatedly; page listeners, markers, and overlays must deduplicate cleanly.
- Original-page resume uses an Incremento URL fragment marker rather than a server-visible query parameter. Sanitize temporary tracking/resume markers out of the visible URL after the content script consumes them.
- Tab IDs and frame IDs are ephemeral. Revalidate them before executing scripts or associating a progress update, and remove stale session mappings when tabs/navigation invalidate them.

## Popup, Capture, and Bookmark Behavior

- Popup actions include PDF, video, webpage, selection-to-Markdown, page-to-Markdown, text capture, and snapshot capture. Keep shortcut, context-menu, popup, and backend payload semantics aligned when an action exists in more than one surface.
- Snapshot capture must not leave overlays, selection artifacts, or page style changes behind, including after errors.
- Writing imports auto-generate a unique timestamped title only when the user leaves the default page title unchanged. Keep preferred Markdown filenames short and slug-based; do not feed a long generated note title back into the filename.
- Browser-capture provenance belongs in backend `Incremento_*` metadata fields. Send raw title, URL, selection, and snapshot values; do not append `Source:` blocks to the content in extension code.
- Bookmark import separates pure tree/model transformations from Chrome API access and UI progress. Preserve stable selection when rows are edited, deterministic kind detection, bounded concurrency, per-row errors, and explicit user confirmation before sending imports.
- Link-save context menus are driven by normalized settings/state. Never register duplicate menus on service-worker restart or treat arbitrary page markup as a trusted card link.

## Playback, Clipboard, and Offscreen Rules

- Tracked playback can originate in nested iframes. Progress updates must carry only the currently linked card/media context and must stop after unlink/navigation/tab removal.
- Keep update frequency bounded. A noisy media element must not flood port `8766`, Chrome storage, or Anki's main thread.
- Clipboard writes prefer the narrowest available capability and fall back to `offscreen.html` only for the `offscreen-copy` message. Do not expand the offscreen document into a general background page.
- The “copy last video time” value is convenience state, not card identity. Validate and format it before writing; never copy hidden tokens or raw diagnostic payloads.

## Generated Output and Static Files

- Never patch `dist/*.js` or `dist/assets/*.js` as the source of a fix. Edit `src/` or `frontend/vite.extension.config.js`, rebuild, inspect the generated diff, and commit source plus output together.
- `npm --prefix frontend run build:extension` empties and recreates `dist/`. If an entry point or shared chunk changes, verify `manifest.json`, static HTML script loading, `content-loader.js`, and `web_accessible_resources` still reference valid files.
- Static HTML/CSS and `manifest.json` are not generated by Vite. Review their CSP/loading/permission implications directly.
- Extension icons are generated intentionally by `scripts/generate_icons.py`; it requires Pillow and overwrites the existing PNG set. Do not rerun it for unrelated work.
- Update the extension `README.md` when installation steps, permissions, commands, or user-facing behavior changes.

## Build and Checks

Run source tests first, then rebuild and syntax-check every entry bundle:

```bash
npm --prefix chrome_extensions/incremento_companion test
npm --prefix frontend run build:extension
node --check chrome_extensions/incremento_companion/dist/background.js
node --check chrome_extensions/incremento_companion/dist/content.js
node --check chrome_extensions/incremento_companion/dist/offscreen.js
node --check chrome_extensions/incremento_companion/dist/popup.js
node --check chrome_extensions/incremento_companion/dist/bookmarks.js
```

Bridge or import changes also require the matching Python boundary tests:

```bash
.venv/bin/python -m pytest -o addopts= tests/test_browser_bridge.py tests/test_video_web.py tests/test_pdf_manager.py -q
```

After rebuilding, use `git diff --stat` and `git diff -- chrome_extensions/incremento_companion/manifest.json chrome_extensions/incremento_companion/src chrome_extensions/incremento_companion/dist` to confirm that generated changes correspond to the edited source and no hand-maintained file disappeared.
