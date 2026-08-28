# Extension Agent Notes

Use this file for work in `chrome_extensions/incremento_companion/`.

## Ownership

- This area owns browser import, browser capture, bookmark import, and tracked playback sync for the companion Chrome extension.

## Layout

- Source: `src/`
- Built runtime bundles: `dist/`
- Bookmark importer runtime files also come from `dist/`

## Popup and Capture Behavior

- Popup actions include `Add as PDF`, `Add as Video`, `Add as Webpage`, `Add Selection to Markdown`, `Add Page to Markdown`, and browser-capture triggers for text and snapshot capture.
- Snapshot capture no longer dims the page with a gray overlay.
- Popup writing imports auto-generate a unique title only when the user leaves the default page title unchanged.
- Auto-generated writing titles use a microsecond-resolution timestamp suffix.
- Markdown preferred filenames are kept short and slug-based; do not feed the full generated note title back into the filename.
- Browser-capture provenance now lands in dedicated Incremento note metadata fields on the backend. The extension should continue sending raw title, URL, selection, and snapshot payloads instead of trying to format source metadata into content fields itself.

## Playback and Reinjection Rules

- Tracked web-card playback can come from iframe players; content and background reinjection must preserve `allFrames: true`.
- Web-card resume handoff for original-page resume is passed through a URL fragment marker, not server-visible query params.
- Content scripts sanitize temporary Incremento tracking and resume markers back out of the visible URL after load.

## Backend-Owned Behavior

- Current statistics, focus timer, review-time attribution, and PDF-vs-EPUB document-type behavior are backend/frontend-owned. Do not rebuild the extension for those changes unless `src/` or extension runtime bundles change.

## Local Bridge Authentication

- All port `8766` requests go through `src/shared/bridgeAuth.js`; do not add direct bridge `fetch()` calls elsewhere.
- Protocol 2 obtains an ephemeral token from `/incremento/handshake`, then sends `X-Incremento-Token` and `X-Incremento-Protocol` on every request.
- A `401` triggers exactly one fresh handshake/retry. Do not persist the token in extension storage.
- The backend binds one exact `chrome-extension://<id>` origin per bridge run and applies body/concurrency limits. Keep source, extension tests, and generated `dist/` aligned when the protocol changes.

## Build and Checks

If you change extension source:

```bash
npm --prefix frontend run build:extension
```

Useful focused checks:

```bash
npm --prefix chrome_extensions/incremento_companion test
node --check chrome_extensions/incremento_companion/dist/background.js
node --check chrome_extensions/incremento_companion/dist/content.js
node --check chrome_extensions/incremento_companion/dist/offscreen.js
node --check chrome_extensions/incremento_companion/dist/popup.js
node --check chrome_extensions/incremento_companion/dist/bookmarks.js
```
