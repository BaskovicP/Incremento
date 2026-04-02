# Incremento Video Time Clipboard (Chrome/Brave)

Copies the last watched YouTube/Vimeo time to your clipboard when a video tab closes, and can send the current page to Incremento as a PDF, webpage card, or writing card.

## What it does

- Runs on `youtube.com`, `youtu.be`, and `vimeo.com` / `player.vimeo.com`.
- Reads the active `<video>` element `currentTime`.
- Sends heartbeats to extension background.
- On tab close, copies formatted time (`M:SS` or `H:MM:SS`) to clipboard.
- On tab close, also pushes the timestamp to Anki via AnkiConnect by updating `Incremento Video` notes (`YouTube_URL` field).
- The popup can add the current browser page to Incremento as:
  - `PDF` using the page snapshot rendered by the addon
  - `Webpage` using an `Incremento Web` card
  - `Writing` using an `Incremento Writing` card seeded with the page title/source and current text selection
- Also pushes timestamp (no clipboard copy) on pause, visibility hidden, and page unload/navigation events.
- Stores the last captured value in extension storage as backup.
- The popup also includes a `Copy last video time` button.
- Keyboard shortcut `Alt+Shift+V` (customizable in `chrome://extensions/shortcuts`) copies latest stored time.
- Reuses useful UX patterns from your `ankiExport` extension: in-page toast feedback and robust background/content message handling.

## Install (Load Unpacked)

1. Open Chrome/Brave and go to `chrome://extensions`.
2. Enable `Developer mode`.
3. Click `Load unpacked`.
4. Select this folder:
   - `.../incremento/chrome_extensions/incremento_video_time_clipboard`
5. Pin the extension (optional, recommended).

## Usage

1. On any normal webpage, click the extension icon.
2. Choose `Add as PDF`, `Add as Webpage`, or `Add as Writing`.
3. Keep the prefilled title or edit it before clicking.

For video time capture:

1. Watch a YouTube/Vimeo video in browser.
2. Close that video tab.
3. Return to Anki; paste the copied time into the stop-time dialog.

If clipboard was not updated in an edge case, click the extension icon once to copy the last captured time from storage.
You can also press `Alt+Shift+V`.

## Notes

- Requires Anki running with AnkiConnect on `http://127.0.0.1:8765`.
- Requires the Incremento addon loaded in Anki so the local bridge on `http://127.0.0.1:8766` can create `pdf`, `webpage`, and `writing` content.
- If URL contains `inc_card_id=<card_id>` (added by Incremento browser-open), sync targets that exact card/note first.
- Otherwise, sync falls back to matching `Incremento Video` notes whose `YouTube_URL` contains the same video id.
- This depends on browser extension APIs and clipboard permissions.
- Some private/incognito/restricted contexts may limit clipboard behavior.
- The extension is local-only and does not send data externally.
- Clipboard copy uses layered fallbacks (service worker clipboard, offscreen document, then active-tab script injection) for better compatibility.
