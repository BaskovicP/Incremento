# Incremento Video Time Clipboard (Chrome/Brave)

Copies the last watched YouTube/Vimeo time to your clipboard when a video tab closes, so you can paste it back in Anki.

## What it does

- Runs on `youtube.com`, `youtu.be`, and `vimeo.com` / `player.vimeo.com`.
- Reads the active `<video>` element `currentTime`.
- Sends heartbeats to extension background.
- On tab close, copies formatted time (`M:SS` or `H:MM:SS`) to clipboard.
- Stores the last captured value in extension storage as backup.
- Clicking the extension icon copies the latest stored time again.
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

1. Watch a YouTube/Vimeo video in browser.
2. Close that video tab.
3. Return to Anki; paste the copied time into the stop-time dialog.

If clipboard was not updated in an edge case, click the extension icon once to copy the last captured time from storage.
You can also press `Alt+Shift+V`.

## Notes

- This depends on browser extension APIs and clipboard permissions.
- Some private/incognito/restricted contexts may limit clipboard behavior.
- The extension is local-only and does not send data externally.
