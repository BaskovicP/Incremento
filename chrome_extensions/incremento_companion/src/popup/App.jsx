import { useEffect, useMemo, useState } from "react";
import {
  captureSnapshot,
  copyLatestVideoTime,
  getActiveTab,
  openBookmarksPage,
} from "../shared/chromeApi.js";
import { formatBridgeError, importIntoIncremento } from "../shared/bridge.js";
import { getPdfPayloadForUrl } from "../shared/pdfFetch.js";
import { isHttpUrl, isSupportedVideoUrl } from "../shared/url.js";

function initialStatus() {
  return { text: "", kind: "" };
}

export function PopupApp() {
  const [activeTab, setActiveTab] = useState(null);
  const [snapshot, setSnapshot] = useState(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(initialStatus);
  const [title, setTitle] = useState("");

  const pageUrl = String(snapshot?.url || activeTab?.url || "").trim();
  const pageTitle = String(snapshot?.title || activeTab?.title || "").trim();
  const selectionText = String(snapshot?.selectionText || "");
  const hasSupportedPage = Boolean(activeTab && isHttpUrl(pageUrl));
  const onVideoPage = isSupportedVideoUrl(pageUrl);

  const selectionNote = useMemo(() => {
    if (onVideoPage) {
      return "Video cards use the current YouTube or Vimeo URL.";
    }
    if (selectionText) {
      return `Writing cards will include the current selection (${selectionText.length} chars).`;
    }
    return "Writing cards will start with the page title and source link.";
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

  useEffect(() => {
    if (!busy && !hasSupportedPage) {
      setStatus({
        text: "Open a normal http(s) page first.",
        kind: "error",
      });
    }
  }, [busy, hasSupportedPage]);

  async function handleAdd(kind) {
    if (!activeTab) {
      setStatus({ text: "No active tab found.", kind: "error" });
      return;
    }
    if (!isHttpUrl(pageUrl)) {
      setStatus({ text: "Only http(s) pages can be sent to Incremento.", kind: "error" });
      return;
    }
    if (kind === "video" && !onVideoPage) {
      setStatus({ text: "Open a YouTube or Vimeo page to add a video card.", kind: "error" });
      return;
    }

    const payload = {
      kind,
      url: pageUrl,
      title: title.trim() || pageTitle || pageUrl,
      selectedText: selectionText,
    };
    if (kind === "pdf" && snapshot?.html) {
      payload.html = String(snapshot.html);
    }
    if (kind === "pdf") {
      const pdfPayload = await getPdfPayloadForUrl(pageUrl);
      if (pdfPayload) {
        payload.pdfBase64 = pdfPayload.pdfBase64;
        payload.pdfFilename = pdfPayload.pdfFilename;
      }
    }

    setBusy(true);
    setStatus({ text: `Adding ${kind} card...`, kind: "" });
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
        <p className="note" id="selection-note">{selectionNote}</p>
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
            onClick={() => void handleAdd("writing")}
          >
            Add as Writing
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
