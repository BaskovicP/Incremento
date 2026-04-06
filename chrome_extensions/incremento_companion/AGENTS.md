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

## Playback and Reinjection Rules

- Tracked web-card playback can come from iframe players; content and background reinjection must preserve `allFrames: true`.
- Web-card resume handoff for original-page resume is passed through a URL fragment marker, not server-visible query params.
- Content scripts sanitize temporary Incremento tracking and resume markers back out of the visible URL after load.

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
