import { useEffect, useMemo, useState } from "react";
import {
  captureSnapshot,
  getCommandShortcuts,
  copyLatestVideoTime,
  getActiveTab,
  openExtensionShortcutsPage,
  openBookmarksPage,
  triggerBrowserCaptureForTab,
} from "../shared/chromeApi.js";
import { formatBridgeError, importIntoIncremento } from "../shared/bridge.js";
import { getPdfPayloadForUrl } from "../shared/pdfFetch.js";
import { isHttpUrl, isSupportedVideoUrl } from "../shared/url.js";

function initialStatus() {
  return { text: "", kind: "" };
}

function buildPreferredWritingFilename(title, url) {
  const base = String(title || url || "writing-note")
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^[-._]+|[-._]+$/g, "")
    || "writing-note";
  return `${base}-${Date.now()}.md`;
}

export function PopupApp() {
  const [activeTab, setActiveTab] = useState(null);
  const [snapshot, setSnapshot] = useState(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(initialStatus);
  const [title, setTitle] = useState("");
  const [commandShortcuts, setCommandShortcuts] = useState([]);
  const [pageContentScope, setPageContentScope] = useState("main");

  const pageUrl = String(snapshot?.url || activeTab?.url || "").trim();
  const pageTitle = String(snapshot?.title || activeTab?.title || "").trim();
  const selectionText = String(snapshot?.selectionText || "");
  const hasSupportedPage = Boolean(activeTab && isHttpUrl(pageUrl));
  const onVideoPage = isSupportedVideoUrl(pageUrl);

  const writingNote = useMemo(() => {
    if (onVideoPage) {
      return "Video cards use the current YouTube or Vimeo URL.";
    }
    if (selectionText) {
      return `Selection writing will use the current selection (${selectionText.length} chars). Page writing imports webpage content as markdown.`;
    }
    return "Selection writing uses the current selection when present. Page writing imports webpage content as markdown.";
  }, [onVideoPage, selectionText]);

  useEffect(() => {
    let cancelled = false;

    async function initialize() {
      setBusy(true);
      try {
        const tab = await getActiveTab();
        if (cancelled) {
          return;
        }
        setActiveTab(tab);

        let nextSnapshot = null;
        if (tab?.id && isHttpUrl(tab.url)) {
          nextSnapshot = await captureSnapshot(tab.id);
          if (cancelled) {
            return;
          }
          setSnapshot(nextSnapshot);
        }

        const nextTitle = String(nextSnapshot?.title || tab?.title || nextSnapshot?.url || tab?.url || "").trim();
        if (nextTitle) {
          setTitle(nextTitle);
        }

        const commands = await getCommandShortcuts();
        if (!cancelled) {
          setCommandShortcuts(Array.isArray(commands) ? commands : []);
        }
      } catch (error) {
        if (!cancelled) {
          setStatus({
            text: error?.message || "Failed to inspect the current page.",
            kind: "error",
          });
        }
      } finally {
        if (!cancelled) {
          setBusy(false);
        }
      }
    }

    void initialize();
    return () => {
      cancelled = true;
    };
  }, []);

  async function readCurrentPageContext() {
    const tab = await getActiveTab();
    let nextSnapshot = null;
    if (tab?.id && isHttpUrl(String(tab.url || "").trim())) {
      nextSnapshot = await captureSnapshot(tab.id);
    }
    if (tab) {
      setActiveTab(tab);
    }
    setSnapshot(nextSnapshot);
    return {
      tab,
      snapshot: nextSnapshot,
      pageUrl: String(nextSnapshot?.url || tab?.url || "").trim(),
      pageTitle: String(nextSnapshot?.title || tab?.title || nextSnapshot?.url || tab?.url || "").trim(),
      selectionText: String(nextSnapshot?.selectionText || ""),
    };
  }

  useEffect(() => {
    if (!busy && !hasSupportedPage) {
      setStatus({
        text: "Open a normal http(s) page first.",
        kind: "error",
      });
    }
  }, [busy, hasSupportedPage]);

  async function handleAdd(kind, options = {}) {
    const context = await readCurrentPageContext();
    const currentTab = context.tab;
    const currentSnapshot = context.snapshot;
    const currentPageUrl = context.pageUrl;
    const currentPageTitle = context.pageTitle;
    const currentSelectionText = context.selectionText;

    if (!currentTab) {
      setStatus({ text: "No active tab found.", kind: "error" });
      return;
    }
    if (!isHttpUrl(currentPageUrl)) {
      setStatus({ text: "Only http(s) pages can be sent to Incremento.", kind: "error" });
      return;
    }
    if (kind === "video" && !isSupportedVideoUrl(currentPageUrl)) {
      setStatus({ text: "Open a YouTube or Vimeo page to add a video card.", kind: "error" });
      return;
    }

    const payload = {
      kind,
      url: currentPageUrl,
      title: title.trim() || currentPageTitle || currentPageUrl,
      selectedText: currentSelectionText,
    };
    if (kind === "pdf" && currentSnapshot?.html) {
      payload.html = String(currentSnapshot.html);
    }
    if (kind === "writing") {
      const writingMode = String(options.writingMode || "selection");
      payload.writingMode = writingMode;
      payload.preferredFilename = buildPreferredWritingFilename(payload.title, currentPageUrl);
      if (writingMode === "selection" && !currentSelectionText) {
        setStatus({
          text: "Select text on the page first.",
          kind: "error",
        });
        return;
      }
      if (writingMode === "webpage_markdown") {
        payload.pageContentScope = String(pageContentScope || "main");
        if (!currentSnapshot?.html) {
          setStatus({
            text: "Could not read webpage content from this tab.",
            kind: "error",
          });
          return;
        }
        payload.html = String(currentSnapshot.html);
      }
    }
    if (kind === "pdf") {
      const pdfPayload = await getPdfPayloadForUrl(currentPageUrl);
      if (pdfPayload) {
        payload.pdfBase64 = pdfPayload.pdfBase64;
        payload.pdfFilename = pdfPayload.pdfFilename;
      }
    }

    setBusy(true);
    const statusLabel = (
      kind === "writing" && payload.writingMode === "webpage_markdown"
        ? "Adding writing card from webpage markdown..."
        : `Adding ${kind} card...`
    );
    setStatus({ text: statusLabel, kind: "" });
    try {
      const result = await importIntoIncremento(payload);
      setStatus({ text: `Added ${result.kind} card: ${result.title}`, kind: "success" });
    } catch (error) {
      setStatus({
        text: formatBridgeError(error, "Failed to add content."),
        kind: "error",
      });
    } finally {
      setBusy(false);
    }
  }

  async function handleCopyVideoTime() {
    setBusy(true);
    setStatus({ text: "Copying last video time...", kind: "" });
    try {
      const response = await copyLatestVideoTime();
      if (response?.ok) {
        setStatus({ text: "Copied last video time.", kind: "success" });
      } else {
        setStatus({ text: "No stored video time yet.", kind: "error" });
      }
    } catch (error) {
      setStatus({ text: error?.message || "Failed to copy video time.", kind: "error" });
    } finally {
      setBusy(false);
    }
  }

  async function handleOpenBookmarks() {
    try {
      await openBookmarksPage();
      window.close();
    } catch (error) {
      setStatus({
        text: error?.message || "Failed to open bookmark importer.",
        kind: "error",
      });
    }
  }

  async function handleOpenShortcutsPage() {
    try {
      await openExtensionShortcutsPage();
    } catch (error) {
      setStatus({
        text: error?.message || "Failed to open Chrome shortcut settings.",
        kind: "error",
      });
    }
  }

  async function handleTriggerBrowserCapture(mode) {
    if (!activeTab?.id) {
      setStatus({
        text: "No active tab found.",
        kind: "error",
      });
      return;
    }
    setBusy(true);
    setStatus({
      text: mode === "snapshot" ? "Starting snapshot capture..." : "Starting text capture...",
      kind: "",
    });
    try {
      const response = await triggerBrowserCaptureForTab(activeTab.id, mode);
      if (response?.ok) {
        setStatus({
          text: mode === "snapshot" ? "Snapshot capture opened in the page." : "Text capture opened in the page.",
          kind: "success",
        });
        window.close();
        return;
      }
      setStatus({
        text: String(
          response?.error || (
            mode === "snapshot"
              ? "Snapshot capture did not start on this tab."
              : "Text capture did not start. Select text on the page first."
          )
        ),
        kind: "error",
      });
    } catch (error) {
      setStatus({
        text: error?.message || "Failed to trigger browser capture.",
        kind: "error",
      });
    } finally {
      setBusy(false);
    }
  }

  const selectionShortcut = commandShortcuts.find((command) => command.name === "browser-capture-selection")?.shortcut || "";
  const snapshotShortcut = commandShortcuts.find((command) => command.name === "browser-capture-snapshot")?.shortcut || "";

  return (
    <main className="popup">
      <section className="panel">
        <div className="eyebrow">Current page</div>
        <h1>Send to Incremento</h1>
        <p className="muted" id="page-url">{pageUrl || "No supported page selected."}</p>
        <label className="field">
          <span>Title</span>
          <input
            id="title-input"
            type="text"
            spellCheck="false"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <p className="note" id="selection-note">{writingNote}</p>
        <label className="field">
          <span>Webpage markdown scope</span>
          <select
            id="writing-scope"
            value={pageContentScope}
            onChange={(event) => setPageContentScope(event.target.value)}
          >
            <option value="main">Main content</option>
            <option value="full">Entire page</option>
          </select>
        </label>
        <div className="actions">
          <button
            className="kind-btn"
            data-kind="pdf"
            disabled={busy || !hasSupportedPage}
            onClick={() => void handleAdd("pdf")}
          >
            Add as PDF
          </button>
          <button
            className="kind-btn"
            data-kind="video"
            disabled={busy || !hasSupportedPage || !onVideoPage}
            onClick={() => void handleAdd("video")}
          >
            Add as Video
          </button>
          <button
            className="kind-btn"
            data-kind="webpage"
            disabled={busy || !hasSupportedPage}
            onClick={() => void handleAdd("webpage")}
          >
            Add as Webpage
          </button>
          <button
            className="kind-btn"
            data-kind="writing"
            disabled={busy || !hasSupportedPage}
            onClick={() => void handleAdd("writing", { writingMode: "selection" })}
          >
            Add Selection to Markdown
          </button>
          <button
            className="kind-btn"
            data-kind="writing-page"
            disabled={busy || !hasSupportedPage}
            onClick={() => void handleAdd("writing", { writingMode: "webpage_markdown" })}
          >
            Add Page to Markdown
          </button>
        </div>
        <p className={`status${status.kind ? ` is-${status.kind}` : ""}`} id="status" role="status" aria-live="polite">
          {status.text}
        </p>
      </section>

      <section className="panel panel-secondary">
        <button
          className="ghost-btn"
          id="open-bookmarks"
          disabled={busy}
          onClick={() => void handleOpenBookmarks()}
        >
          Download bookmarks
        </button>
      </section>

      <section className="panel panel-secondary">
        <div className="actions">
          <button
            className="kind-btn"
            type="button"
            disabled={busy || !hasSupportedPage}
            onClick={() => void handleTriggerBrowserCapture("selection")}
          >
            Trigger text capture
          </button>
          <button
            className="kind-btn"
            type="button"
            disabled={busy || !hasSupportedPage}
            onClick={() => void handleTriggerBrowserCapture("snapshot")}
          >
            Trigger snapshot capture
          </button>
        </div>
      </section>

      <section className="panel panel-secondary">
        <div className="shortcut-status">
          <div>
            <strong>Text capture</strong>
            <span>{selectionShortcut || "Not assigned in Chrome"}</span>
          </div>
          <div>
            <strong>Snapshot capture</strong>
            <span>{snapshotShortcut || "Not assigned in Chrome"}</span>
          </div>
        </div>
        <button
          className="ghost-btn"
          type="button"
          onClick={() => void handleOpenShortcutsPage()}
        >
          Open shortcut settings
        </button>
      </section>

      <section className="panel panel-secondary">
        <button
          className="ghost-btn"
          id="copy-video-time"
          disabled={busy}
          onClick={() => void handleCopyVideoTime()}
        >
          Copy last video time
        </button>
      </section>
    </main>
  );
}
