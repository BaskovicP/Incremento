# Incremento Companion (Chrome/Brave)

Incremento Companion connects normal browser pages to the Incremento Anki add-on. It can import the current page, capture selected text or screenshots into any Anki note type, batch-import bookmarks, save links while browsing, and synchronize browser video progress with Incremento cards.

The extension is optional. Incremento's Anki-only workflows continue to work without it.

## Requirements

- Desktop Anki with the Incremento add-on installed
- Chrome or Brave with permission to load an unpacked extension
- Anki open while importing, capturing, or synchronizing linked web cards
- AnkiConnect running on `http://127.0.0.1:8765` for automatic YouTube/Vimeo timestamp updates

Incremento itself provides the local browser bridge on `http://127.0.0.1:8766`. The bridge starts when Anki loads the add-on.

## Install the extension

1. In Anki, open **Tools → Add-ons**.
2. Select **Incremento**, then click **View Files**.
3. Open `chrome_extensions/incremento_companion/`. This is the extension folder; it contains `manifest.json` and `dist/`.
4. Open `chrome://extensions` in Chrome or `brave://extensions` in Brave.
5. Enable **Developer mode**.
6. Click **Load unpacked** and select the `incremento_companion` folder itself. Do not select its `dist` subfolder.
7. Pin **Incremento Companion** to the browser toolbar for quick access.

The installed add-on folder may be named `1013949798` when Incremento came from AnkiWeb, or `incremento` when installed from source or a local package. Using **View Files** avoids having to find that folder manually.

After updating Incremento, return to the browser's extensions page and click **Reload** on Incremento Companion. Reload any browser tabs that were already open so they receive the new content script.

### Confirm the connection

1. Keep Anki open.
2. Open a normal `http://` or `https://` page.
3. Click the Companion icon.
4. Confirm that the **Deck** list loads your Anki decks.

If the popup says it cannot reach Incremento or falls back to the Topics deck, see [Troubleshooting](#troubleshooting).

## Send the current page to Incremento

Open the Companion popup on a normal webpage. Before importing, you can edit the title and choose the deck, tags, and priority. Tags may be separated by spaces or commas.

The popup provides five import actions:

- **Add as PDF** creates an Incremento PDF card. A direct PDF URL is downloaded when possible; a normal webpage is rendered to PDF by Incremento.
- **Add as Video** creates an Incremento Video card from the current YouTube or Vimeo URL. It is enabled only on supported video pages.
- **Add as Webpage** creates a live Incremento Web card. If the page contains playing media, its detected position can be stored with the new card.
- **Add Selection to Markdown** creates an Incremento Writing card from the text currently selected on the page.
- **Add Page to Markdown** converts either the page's main content or the entire page to markdown, according to **Webpage markdown scope**.

When a browser tab was opened from an Incremento card, new content created from that tab retains the source-card relationship. A webpage created with **Add as Webpage** also becomes linked to the current tab so its URL and media progress can continue to synchronize.

Only normal HTTP(S) pages are supported. Browser-internal pages such as `chrome://extensions`, `brave://extensions`, and browser store pages do not allow extension capture.

## Capture text into any Anki note type

Text capture creates a normal Anki note using field mappings that you choose.

1. Select text on a webpage.
2. Press the assigned **Text capture** shortcut (default `Alt+X`; `Option+X` on macOS), or click **Trigger text capture** in the popup.
3. In **Send capture to Anki**, choose a note type, deck, tags, and priority.
4. Map the page title, selected text, and source URL to the desired note fields. Choose **Do not insert** for anything you do not want.
5. Edit the selected text if needed, then click **Create note**.

Field mappings are remembered separately for each note type. Incremento also keeps browser-capture provenance in its dedicated metadata fields when those fields are available.

## Capture page snapshots

Snapshot mode creates one Anki note containing one or more selected regions of the visible browser page.

1. Press the assigned **Snapshot capture** shortcut (default `Alt+Shift+X`), or click **Trigger snapshot capture** in the popup.
2. Draw a rectangle around the first region. The region is captured immediately.
3. Scroll and draw more rectangles if desired.
4. Use **Undo** to remove the latest capture or **Clear** to remove all captures.
5. Choose one of these finishes:
   - **Continue** opens the full form, where you can choose the note type, deck, tags, priority, and destination fields.
   - **Extract now** immediately creates a note with the last saved snapshot settings.

Use **Continue** at least once before relying on **Extract now**, so a valid snapshot field and destination note type are saved. In the full form, **Capture more** returns to region selection, and individual preview images can be removed before creating the note.

Snapshots are limited to the current viewport, but you can scroll between captures to collect multiple parts of a long page.

## Save links while browsing

The **Quick link save** section of the popup can create Incremento Web cards without first opening the target link.

### Modifier-click

1. Enable **Enable modifier-click save on links**.
2. Choose Alt, Shift, Ctrl, or Meta/Cmd as the modifier.
3. Choose whether **Continue following the link after saving** should remain enabled.
4. Click **Save quick link settings**.
5. Hold only the chosen modifier and left-click an HTTP(S) link.

Incremento creates a webpage card and displays a small success or error message in the browser. When navigation is disabled, the link is saved without leaving the current page.

### Right-click action

Enable **Enable right-click link action**, save the settings, then right-click a link and choose **Save link to Incremento as webpage**.

Links saved from a tab linked to an Incremento card retain that card as their source/parent context.

## Import Chrome/Brave bookmarks

Click **Download bookmarks** in the popup to open the bookmark importer. Despite the button's compact label, this opens an import workspace; it does not write a bookmark file to disk.

1. Select individual bookmarks or whole folders in the tree. Selecting a folder includes links in all nested folders.
2. Choose one destination deck for the import.
3. For each selected bookmark, review or edit its title, type, tags, and priority.
4. Click **Import selected**.

The importer detects direct PDF URLs and supported YouTube/Vimeo links automatically. You can override any row to create a PDF, YouTube/Video, Webpage, or Writing card. Imports run one at a time and show progress plus a separate result for every bookmark, so one failed row does not hide the successful rows.

## Linked web cards and browser media

Incremento can associate a browser tab with one specific Web card. A linked tab can:

- update the card's last visited URL as you navigate
- save the position of media playing on the page, including media inside supported frames
- resume saved media when the card is opened externally again
- provide source/parent context for new captures and imports

A tab becomes linked when either:

- you create it with **Add as Webpage** in the Companion popup, or
- you open a Web card through Incremento's **Open in Window** action with **Track via Chrome extension** enabled.

The page shows a **Tracking Web Card** badge while tracking is active. Temporary Incremento tracking markers are removed from the visible address bar after the link is established.

The popup's **Linked card** section shows the linked card ID and any detected media position. To save a specific point, enter a manual time such as `12:34`, `1:02:03`, `90`, or `1m30s`, then click **Save manual time**. With the input empty, the button uses the currently detected media time when one is available.

## YouTube and Vimeo video time

On YouTube and Vimeo, the extension monitors the active video position. It saves progress on pause, when the page becomes hidden or unloads, and when the video tab closes.

When possible, the extension updates the matching **Incremento Video** note through AnkiConnect:

1. A card ID supplied by Incremento is used first.
2. Otherwise, the extension falls back to matching the YouTube/Vimeo video ID in the note's `YouTube_URL` field.

Closing a recently active video tab also copies its formatted time (`M:SS` or `H:MM:SS`) to the clipboard. The latest value remains in extension storage as a fallback. Use **Copy last video time** in the popup or press `Alt+Shift+V` to copy it again.

## Keyboard shortcuts

Open `chrome://extensions/shortcuts` in Chrome or `brave://extensions/shortcuts` in Brave to review or change shortcuts.

Default assignments:

| Action | Default shortcut |
|---|---|
| Capture selected text | `Alt+X` |
| Capture snapshots | `Alt+Shift+X` |
| Copy the latest video time | `Alt+Shift+V` |

The extension also exposes commands for adding the current page as PDF, Video, or Webpage, adding the selection to Markdown, and adding the page to Markdown. These commands are unassigned by default; assign any of them from the browser shortcut page.

The popup displays the active Text capture and Snapshot capture assignments. A shortcut may be unavailable if the browser or another extension already uses it.

## Privacy and permissions

Incremento Companion communicates with Anki only through local loopback addresses:

- `127.0.0.1:8766` for Incremento imports, browser captures, linked web cards, and media references
- `127.0.0.1:8765` for AnkiConnect video-note updates

It does not upload captured page data to an Incremento cloud service or another third-party service. The extension stores its settings, linked-tab session state, and latest video time in browser extension storage.

Port `8766` uses Incremento bridge protocol 2. The extension first performs a local handshake, Anki binds the exact Chrome/Brave extension origin, and every later request carries a short-lived token plus protocol header. The token is regenerated whenever the bridge restarts and is not written to extension storage. Request paths, origin, body size, and concurrent request count are bounded by the add-on.

One extension origin is bound per Anki bridge run. If you alternate between separately installed Chrome and Brave copies, restart Anki before connecting the other browser. Ordinary browser tabs do not receive the bridge token; only the extension runtime does.

Broad site access is required because capture, link saving, webpage import, and media tracking must work on pages chosen by the user. The bookmarks permission is used only by the bookmark importer, and clipboard permission is used to copy the latest video time.

## Troubleshooting

### "Failed to reach Incremento in Anki"

- Keep desktop Anki open.
- Confirm Incremento is enabled in **Tools → Add-ons**.
- Restart Anki so the local bridge on port `8766` starts cleanly.
- Reload the extension from `chrome://extensions` or `brave://extensions`, then reload the webpage.
- If you switched between Chrome and Brave, restart Anki so the new extension origin can perform the protocol-2 handshake.

### Decks do not load

The deck list comes from the Incremento bridge. If the popup or bookmark importer falls back to **Topics**, restore the Anki connection first and reopen the popup/importer.

### Capture does nothing

- Confirm the current tab is a normal HTTP(S) page.
- Reload tabs that were already open when the extension was installed or reloaded.
- For text capture, select some text before triggering it.
- Check the assignment and conflicts on the browser's extension shortcut page.
- Extensions cannot inject into browser settings, the Chrome/Brave Web Store, or other protected pages.

### Snapshot **Extract now** reports that fields are not configured

Choose **Continue**, map **Snapshot field** to an actual note field, create the note once, and then use **Extract now** on later captures.

### A video time is not updating the expected card

- Open the video from Incremento when possible so the tab carries the exact card link.
- Confirm AnkiConnect is enabled and reachable on port `8765`.
- Confirm the note is an **Incremento Video** note and its `YouTube_URL` contains the same video ID.
- Pause the video or switch away from the tab to force a progress save.

### A Web card is not following browser navigation

Open the page again through the card's **Open in Window** action with **Track via Chrome extension** enabled, or create the Web card directly from the Companion popup. Look for the **Tracking Web Card** badge.

### Load unpacked reports a missing manifest or scripts

Select the `chrome_extensions/incremento_companion` folder containing both `manifest.json` and `dist/`. If `dist/` is missing in a source checkout, build the extension as described below.

## Development

Source lives under `src/`; Chrome/Brave loads the compiled runtime from `dist/`. Bookmark importer files are also generated into `dist/`.

Rebuild after changing extension source:

```bash
npm --prefix frontend run build:extension
```

Run the extension tests and JavaScript syntax checks:

```bash
npm --prefix chrome_extensions/incremento_companion test
node --check chrome_extensions/incremento_companion/dist/background.js
node --check chrome_extensions/incremento_companion/dist/content.js
node --check chrome_extensions/incremento_companion/dist/offscreen.js
node --check chrome_extensions/incremento_companion/dist/popup.js
node --check chrome_extensions/incremento_companion/dist/bookmarks.js
```

## License

All rights reserved. Using, copying, modifying, or distributing this code requires prior written permission from Paulo Baskovic.
