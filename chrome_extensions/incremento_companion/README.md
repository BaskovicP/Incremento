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

Open the Companion popup on a normal webpage. Before importing, you can edit the title and choose the deck, tags, and priority. Tags may be separated by spaces or commas. Focus the tag field or start typing to see matching tags from the active Anki profile; click a suggestion, or use the arrow keys with Enter/Tab, to complete only the tag currently being typed. You can still enter a new tag normally. The same autocomplete is available in the full text/snapshot capture form.

Enable **Remember tags for this website** below Tags to reuse the popup's tag set on later visits. Enabling it saves the current tags immediately; later edits save automatically. Wait for **Saving website tags…** to disappear before closing the popup. All pages with the same hostname share the set across HTTP/HTTPS and ports; subdomains remain separate. Turning the checkbox off forgets that website's saved set without clearing the current input. This option starts off for every website and stores only explicitly remembered hostnames and tags in the active Anki profile's `incremento.db`, included in normal backups. Anki must be open. Save/load failures appear beside the checkbox with **Retry**. There is a limit of 1,000 remembered websites per profile and 100 tags of up to 200 characters per website.

Remembered website tags also prefill text and snapshot capture, including snapshot **Extract now**, replacing the capture form's older tag defaults. An explicitly saved empty set leaves Tags blank. Other capture choices, such as note type, deck, priority, and field mappings, keep their saved defaults. Triggering capture from the popup waits for pending website-tag saves before opening the form.

The popup provides six import actions:

- **Add as PDF** creates an Incremento PDF card. A direct PDF URL is downloaded when possible; a normal webpage is rendered to PDF by Incremento.
- **Capture opened page as PDF** sends the already-loaded page directly to Anki and creates the PDF automatically. Use this after completing a CAPTCHA or signing in: there is no Print dialog, saved file, or file picker. Content already added by JavaScript is included. It keeps your layout/link-appendix preferences while avoiding a reload in a different browser. Choose the title, deck, tags, and priority in this popup, or use the shortcut for the page title and standard import defaults.
- **Add as Video** creates an Incremento Video card from the current YouTube or Vimeo URL. It is enabled only on supported video pages.
- **Add as Webpage** creates a live Incremento Web card. If the page contains playing media, its detected position can be stored with the new card.
- **Add Selection to Markdown** creates an Incremento Writing card from the text currently selected on the page.
- **Add Page to Markdown** converts either the page's main content or the entire page to markdown, according to **Webpage markdown scope**. Main-content capture selects the largest semantic `main`/`article` region and removes scripts, styles, embedded frames, and hidden/navigation chrome before applying the 2,000,000-character safety limit. Metadata-only actions such as Video and Webpage do not serialize the page HTML.

After an import button is clicked, the popup reports three visible stages: reading the current tab, preparing the destination card, and waiting for Incremento/Anki to create it. The destination summary includes the deck, tag count, and priority. Success is explicitly confirmed; failures identify the stage that stopped instead of disappearing silently. When the operation finishes, the full popup border appears once—green for confirmed creation or red for failure—stays steady briefly, then fades out once; the non-interactive effect respects reduced-motion preferences. Import failures also open a selectable diagnostic block with a **Copy error details** button. The copied report includes the extension version, action, stage, reason, stable error code, and relevant size/scope counters, but never page content, URLs, bridge tokens, or card data.

When a browser tab was opened from an Incremento card, new content created from that tab retains the source-card relationship. A webpage created with **Add as Webpage** also becomes linked to the current tab so its URL and media progress can continue to synchronize.

Only normal HTTP(S) pages are supported. Browser-internal pages such as `chrome://extensions`, `brave://extensions`, and browser store pages do not allow extension capture.

### Webpage-to-PDF settings

Open **Settings → Webpage to PDF** in the popup, choose your defaults, and click **Save**. **Cancel** discards changes. These preferences are saved in the current Chrome/Brave profile and apply to both **Add as PDF** and its keyboard shortcut:

- **Website appearance** keeps the site's screen layout.
- **Clean article** removes navigation and sharing controls for a simpler reading layout.
- **Website print layout (Wikipedia PDF)** uses the site's print styling and Wikipedia's official PDF service when available. This remains the default until you change it.
- **Load content added by JavaScript** reloads the public page in a disposable browser. First use **Set up browser component…** in Anki's **Incremento → Add Content → Webpage to PDF** dialog. Chrome sign-in and cookies are not transferred.
- **Include a list of link destinations** adds a deduplicated appendix of external links.

Direct PDF downloads are imported unchanged. These preferences are separate from the choices in Anki's own Webpage to PDF dialog. After updating the add-on, restart Anki and reload the extension on your browser's extensions page.

When **Webpage to PDF → Import** in Anki encounters HTTP 403/429 or a recognized CAPTCHA/login page, it automatically opens a browser verification handoff. Keep Companion installed in the default Chrome/Brave browser. On first use, allow capture of that site; archive.is also asks for its known archive aliases so verification redirects continue to work. This is optional site access under the existing optional HTTP(S) permissions, not a new required browsing permission. On later imports, just finish verification: Companion waits for readable, stable page content, returns the rendered HTML to that one waiting import, and Anki saves the PDF, activates its window, and shows a success message. The original Anki title, tags, layout, links setting, and source URL are preserved. No capture click, shortcut, file save, or import confirmation is required. Closing the tab cancels the handoff; the Anki dialog also drops late responses after cancellation/profile changes. Pending requests expire after ten minutes. The handoff uses an opaque, single-import identifier and the authenticated protocol-2 bridge; it never transfers browser cookies. The temporary tab association survives service-worker restarts in session storage and is removed after completion or tab closure. Unexpected redirects to another article cannot complete the import.

Alternatively, start directly in your normal browser, finish verification, then press **Alt+Shift+P** (**Option+Shift+P** on macOS), or choose **Capture opened page as PDF** in the popup. The opened-page action always uses the current tab's rendered HTML, even if **Load content added by JavaScript** is selected for ordinary exports. It does not change that saved preference or require Incremento's separate browser component. Anki must be open. Scripts and embedded frames are removed, and optional images/styles/fonts still use the guarded public downloader; resources requiring sign-in may be missing.

## Capture text into any Anki note type

Text capture creates a normal Anki note using field mappings that you choose.

1. Select text on a webpage.
2. Press the assigned **Text capture** shortcut (default `Alt+X`; `Option+X` on macOS), or click **Trigger text capture** in the popup.
3. In **Send capture to Anki**, choose a note type, deck, tags, and priority.
4. Map the page title, selected text, and source URL to the desired note fields. Choose **Do not insert** for anything you do not want.
5. Press **Enter** to create the note, or click **Create note**. The form initially focuses **Create note**, so you can select text, press **Option/Alt+X**, then **Enter** using saved settings. Enter adds a newline while editing selected text, and accepts a tag suggestion while that menu is open; press Enter again afterward to submit.

Field mappings are remembered separately for each note type. Incremento also keeps browser-capture provenance in its dedicated metadata fields when those fields are available.

The shortcut and popup use the same capture startup, with a short, bounded wait for the page listener and retries for a temporarily unavailable background metadata connection. Note creation is never automatically resent after a connection failure. If the page says Companion is disconnected, reload **Incremento Companion** in **Chrome → Extensions**, then reload the webpage. After updating an unpacked extension, both reloads are needed to replace its old background and page code. If the shortcut does nothing, verify **Text capture** is assigned to **Option/Alt+X** with scope **In Chrome** in **Chrome → Extensions → Keyboard shortcuts**.

The **Source URL field** now receives a clickable page-title link. **Link to the original passage** is enabled by default and uses the original selected text, even after you edit the excerpt. Supporting browsers scroll to the passage; changed pages or browsers without passage-link support still open the source page. Turn this option off to keep a normal page link. Existing captures with browser-source metadata also show a clickable source during Anki review, without changing their note templates.

Capture preserves safe paragraphs, lists, emphasis, and code formatting while removing page styling, navigation, scripts, and remote images. You can edit **Page title** and **Selected text** before saving; editing the excerpt uses cleaned plain text. **Preview** shows the saved content for each mapped field, snapshots, and a clickable source. It does not create a note. Your Anki template controls the final card layout, and first-field title mappings receive their unique label only when saved.

If the same passage from the same page already exists, capture offers **Open existing note** in Anki's Browser or **Create another** to save it deliberately. The check ignores whitespace/formatting differences, verifies that the existing card is still present, and stays inside the current Anki profile. It also recognizes older captures that retain their source metadata. Ordinary capture never adds fields to an existing note type; keep a Source URL field mapping when the chosen type has no Incremento metadata fields.

## Capture page snapshots

Snapshot mode creates one Anki note containing one or more selected regions of the visible browser page.

1. Press Chrome's assigned **Snapshot capture** shortcut (default `Alt+Shift+X`, **Option+Shift+X** on macOS), or click **Trigger snapshot capture** in the popup.
2. Draw a rectangle around the first region. The region is captured immediately.
3. Scroll and draw more rectangles if desired.
4. Use **Undo** to remove the latest capture or **Clear** to remove all captures.
5. Choose one of these finishes:
   - **Continue** opens the full form, where you can choose the note type, deck, tags, priority, and destination fields.
   - **Extract now** immediately creates a note with the last saved snapshot settings.

Use **Continue** at least once before relying on **Extract now**, so a valid snapshot field and destination note type are saved. In the full form, **Capture more** returns to region selection, and individual preview images can be removed before creating the note.

Snapshots are limited to the current viewport, but you can scroll between captures to collect multiple parts of a long page. One capture note can contain up to 12 snapshots; each image is limited to 8 MB and the combined decoded image data to 32 MB. The extension reports a local error instead of silently truncating an oversized capture.

Snapshot shortcuts must be registered in **Chrome → Extensions → Keyboard shortcuts**, with **Scope** set to **In Chrome**, so Chrome grants temporary capture access to the page. **Global** commands do not receive that grant, even when pressed inside Chrome. Companion detects a command without an authorized tab and shows the scope instructions instead of opening the snapshot overlay; the popup also explains this setting. The warning's **Open shortcut settings** button opens Chrome's shortcut settings in a new tab. Snapshot permission errors and old page-only shortcut hints provide the same button. These warnings stay visible until you open settings or choose **Dismiss warning**; if opening settings fails, the warning remains available for retry. The old page-only **Option+Command+X** combination shows your actual registered shortcut. If no shortcut is assigned, assign **Snapshot capture** there. You can also click the Companion toolbar icon on the page and choose **Trigger snapshot capture**. If you switch tabs while drawing a region, capture is rejected; return to the original tab and try again. These actions do not require all-sites access.

New installations explicitly default both text and snapshot capture shortcuts to **In Chrome**. Chrome preserves user-customized assignments across updates and does not expose an extension API to change their scope. If an existing installation uses **Global**, change it once in Chrome's shortcut settings; reloading or updating Companion cannot reset it automatically. Chrome may leave a shortcut unassigned if another extension already uses those keys; use the popup's **Open shortcut settings** button to resolve that conflict.

## Save links while browsing

The **Quick link save** section of the popup can create Incremento cards without first opening the target link.

### Modifier-click

1. Enable **Enable modifier-click save on links**.
2. If it should keep working after you navigate to other pages without reopening the popup, use **Enable automatic site access...** and approve the browser prompt.
3. Choose Alt, Shift, Ctrl, or Meta/Cmd as the modifier.
4. Choose whether **Continue following the link after saving** should remain enabled.
5. Click **Save quick link settings**.
6. Hold only the chosen modifier and left-click an HTTP(S) link.

Incremento creates a webpage card and displays a small success or error message in the browser. When navigation is disabled, the link is saved without leaving the current page.

### Right-click action

Enable **Enable right-click link action**, choose the **Right-click destination deck**, save the settings, then right-click a link and choose **Add link to Incremento**. Every card created by this action receives the `topic` tag and goes to the selected deck. Supported YouTube and Vimeo video links create Incremento Video cards automatically; other HTTP(S) links create Incremento Web cards. YouTube watch, short, live, embed, and `youtu.be` links are recognized, and a timestamp in the clicked URL is preserved. When you right-click a YouTube thumbnail or its duration overlay, Companion uses the surrounding video's title instead of the duration label.

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

For automatic media detection, resume, modifier-click handling, and tracking across arbitrary-site navigation, enable **Automatic site access** in the Companion popup. Without that optional grant, explicit popup, shortcut, and context-menu actions still work on the current tab through temporary access.

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
| Capture opened page as PDF | `Alt+Shift+P` (`Option+Shift+P` on macOS) |
| Copy the latest video time | `Alt+Shift+V` |

The extension also exposes commands for adding the current page as PDF, Video, or Webpage, adding the selection to Markdown, and adding the page to Markdown. These commands are unassigned by default; assign any of them from the browser shortcut page.

The popup displays the active Text capture, Snapshot capture, and opened-page PDF capture assignments. A shortcut may be unavailable if the browser or another extension already uses it.

## Privacy and permissions

Incremento Companion communicates with Anki only through local loopback addresses:

- `127.0.0.1:8766` for Incremento imports, browser captures, linked web cards, and media references
- `127.0.0.1:8765` for AnkiConnect video-note updates

It does not upload captured page data to an Incremento cloud service or another third-party service. The extension stores its settings, linked-tab session state, and latest video time in browser extension storage.

Port `8766` uses Incremento bridge protocol 2. The extension first performs a bodyless local POST handshake so Chrome/Brave reliably includes its real extension origin; Anki binds that exact origin, and every later request carries a short-lived token plus protocol header. Read-only metadata requests use the same bodyless POST transport and may retry safely, while ambiguous write failures are not repeated. The token is regenerated whenever the bridge restarts and is not written to extension storage. Request paths, origin, body size, and concurrent request count are bounded by the add-on.

One extension origin is bound per Anki bridge run. If you alternate between separately installed Chrome and Brave copies, restart Anki before connecting the other browser. Ordinary browser tabs do not receive the bridge token; only the extension runtime does.

Ordinary webpages are accessed on demand: clicking the extension, using one of its commands, or choosing its context-menu action grants temporary access to that tab through Chrome/Brave's `activeTab` model. Required persistent host access is limited to supported YouTube/Vimeo providers and the two loopback services. HTTP(S) host patterns are declared only as optional permissions; the extension does not require `<all_urls>` or the broad `tabs` permission at installation.

The popup explains and controls the optional **Automatic site access** feature. If enabled, Chrome/Brave prompts once and the extension registers its content loader on ordinary HTTP(S) pages so modifier-click saving and Web-card media tracking continue across navigation. Disabling it removes both the optional grant and the dynamic registration; user-triggered current-tab actions remain available.

Browser-side PDF fallback downloads are streamed with a 48 MiB ceiling, validate the final HTTP(S) URL and actual PDF signature, and sanitize the suggested filename. Page capture also rejects HTML above 2,000,000 characters or selected text above 200,000 characters before it is sent to Anki. These local limits complement the bridge's independent server-side checks.

The bookmarks permission is used only by the bookmark importer, and clipboard permission is used to copy the latest video time.

## Troubleshooting

### "Failed to reach Incremento in Anki"

- Keep desktop Anki open.
- Confirm Incremento is enabled in **Tools → Add-ons**.
- Restart Anki so the local bridge on port `8766` starts cleanly.
- Reload the extension from `chrome://extensions` or `brave://extensions`, then reload the webpage.
- If you switched between Chrome and Brave, restart Anki so the new extension origin can perform the protocol-2 handshake.

### Decks do not load

The deck list comes from the Incremento bridge. If the popup or bookmark importer falls back to **Topics**, restore the Anki connection first and reopen the popup/importer.

Multiple open tabs are supported. The popup loads Anki decks and tags independently from inspecting the current page, shares bridge reconnect work, and retries brief bridge contention. Its handshake and metadata reads preserve the extension identity even when Chromium omits identity headers from privileged GET requests. After updating an unpacked Companion build, reload the extension once from `chrome://extensions` or `brave://extensions`.

### Capture does nothing

- Confirm the current tab is a normal HTTP(S) page.
- Reload tabs that were already open when the extension was installed or reloaded.
- For text capture, select some text before triggering it.
- Check the assignment and conflicts on the browser's extension shortcut page.
- Extensions cannot inject into browser settings, the Chrome/Brave Web Store, or other protected pages.

If text/snapshot capture reports **This Companion copy is not authorized** while the popup can load decks and tags, update and reload Companion. Capture metadata now uses the same origin-preserving authenticated POST as the popup; Chromium can omit the extension origin from the older GET request. After reloading the extension, refresh the page and retry capture. A remaining authorization error can still mean another Companion copy owns the running Anki bridge; restart Anki in that case.

### Snapshot **Extract now** reports that fields are not configured

Choose **Continue**, map **Snapshot field** to an actual note field, create the note once, and then use **Extract now** on later captures.

### A video time is not updating the expected card

- Open the video from Incremento when possible so the tab carries the exact card link.
- Confirm AnkiConnect is enabled and reachable on port `8765`.
- Multiple tracked tabs are queued through AnkiConnect instead of updating it in parallel.
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
npm --prefix frontend run lint
node --check chrome_extensions/incremento_companion/dist/background.js
node --check chrome_extensions/incremento_companion/dist/content.js
node --check chrome_extensions/incremento_companion/dist/offscreen.js
node --check chrome_extensions/incremento_companion/dist/popup.js
node --check chrome_extensions/incremento_companion/dist/bookmarks.js
```

## Interface language

Open the Companion popup and choose **Settings → Language** to select **Automatic**, **English**, **Hrvatski**, or **简体中文**. **Save** stores the choice in Chrome's local extension settings and updates open Companion pages and overlays immediately. **Cancel** leaves the saved choice unchanged. Automatic follows Chrome's UI language when supported and otherwise uses English. This setting is independent of Anki's language.

### Translate using a spreadsheet

In **Settings → Language**, choose **Export blank template…** to start a new language, or **Export selected language…** to edit an existing translation. The CSV includes Incremento, its PDF reader, and the Companion together. Open it in Excel, Google Sheets, or LibreOffice; fill the `translation` cell of the `meta/locale` row (for example `de`) and `meta/name` row (for example `Deutsch`). Then edit only the `translation` column. Keep IDs, source text, formatting tags, and placeholders unchanged. Save or download **CSV UTF-8**.

Choose **Import translations…** to validate the file and see its translated-row count. **Save** stores the imported language and activates it immediately; **Cancel** discards pending imports. Importing the same locale updates its imported copy. Bundled languages remain available separately. Empty translations use English. Exporting the imported language later preserves all three components and includes new empty rows from the current version. Import the same file separately in Incremento's Language settings to use it in Anki; the apps do not share their saved preferences automatically.

Imports stay offline in Chrome's local extension storage. A file may contain at most 2 MiB, 20,000 rows, and 16 KiB per cell; up to 20 languages can be saved. Chrome-owned extension names and command descriptions still follow Chrome's UI language. See [`TRANSLATING.md`](../../TRANSLATING.md) for spreadsheet examples, plural forms, troubleshooting, and developer instructions.

## License

All rights reserved. Using, copying, modifying, or distributing this code requires prior written permission from Paulo Baskovic.
