import { useEffect, useMemo, useState } from "react";
import {
  captureSnapshot,
  getCurrentMediaContextForTab,
  getLinkedCardContextForTab,
  getCommandShortcuts,
  getLocalExtensionSetting,
  copyLatestVideoTime,
  getActiveTab,
  openExtensionShortcutsPage,
  openBookmarksPage,
  registerWebCardTrackingForTab,
  setLocalExtensionSetting,
  triggerBrowserCaptureForTab,
  updateBrowserMediaRefBadgeForTab,
} from "../shared/chromeApi.js";
import {
  formatBridgeError,
  importIntoIncremento,
  loadBrowserCaptureMeta,
  saveBrowserMediaRef,
} from "../shared/bridge.js";
import { getPdfPayloadForUrl } from "../shared/pdfFetch.js";
import { isHttpUrl, isSupportedVideoUrl } from "../shared/url.js";
import {
  buildAutomaticWritingTitle,
  buildPreferredWritingFilename,
  shouldAutoGenerateWritingTitle,
} from "../shared/writingTitle.js";
import {
  DEFAULT_LINK_SAVE_SETTINGS,
  LINK_SAVE_SETTINGS_KEY,
  MODIFIER_OPTIONS,
  normalizeLinkSaveSettings,
} from "../shared/linkSaveModel.js";
import {
  DEFAULT_PRIORITY,
  PRIORITY_SLIDER_MAX,
  formatPriority,
  parseTags,
  parsePriorityText,
  priorityToSliderValue,
  sliderValueToPriority,
} from "../bookmarks/bookmarkModel.js";
import {
  hasPersistentSiteAccess,
  removePersistentSiteAccess,
  requestPersistentSiteAccess,
} from "../shared/siteAccess.js";

function initialStatus() {
  return { text: "", kind: "" };
}

function formatMediaTime(totalSeconds) {
  const t = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const s = t % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${m}:${String(s).padStart(2, "0")}`;
}

function parseManualTimeInput(rawValue) {
  const raw = String(rawValue || "").trim().toLowerCase();
  if (!raw) {
    return null;
  }
  if (/^\d+$/.test(raw)) {
    return Math.max(0, Number(raw));
  }
  const clockParts = raw.split(":").map((part) => part.trim());
  if (clockParts.length >= 2 && clockParts.length <= 3 && clockParts.every((part) => /^\d+$/.test(part))) {
    if (clockParts.length === 2) {
      return Number(clockParts[0]) * 60 + Number(clockParts[1]);
    }
    return Number(clockParts[0]) * 3600 + Number(clockParts[1]) * 60 + Number(clockParts[2]);
  }
  const matches = Array.from(raw.matchAll(/(\d+)\s*([hms])/g));
  if (!matches.length) {
    return null;
  }
  let total = 0;
  let consumed = "";
  for (const match of matches) {
    const value = Number(match[1] || 0);
    const unit = String(match[2] || "");
    consumed += match[0] || "";
    if (unit === "h") {
      total += value * 3600;
    } else if (unit === "m") {
      total += value * 60;
    } else if (unit === "s") {
      total += value;
    }
  }
  return consumed.replace(/\s+/g, "") === raw.replace(/\s+/g, "") ? total : null;
}

function getTabUrl(tab) {
  return String(tab?.url || tab?.pendingUrl || "").trim();
}

export function PopupApp() {
  const [activeTab, setActiveTab] = useState(null);
  const [snapshot, setSnapshot] = useState(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(initialStatus);
  const [title, setTitle] = useState("");
  const [commandShortcuts, setCommandShortcuts] = useState([]);
  const [pageContentScope, setPageContentScope] = useState("main");
  const [linkedCard, setLinkedCard] = useState({ linked: false, cardId: 0 });
  const [mediaContext, setMediaContext] = useState(null);
  const [manualTime, setManualTime] = useState("");
  const [linkSaveSettings, setLinkSaveSettings] = useState(DEFAULT_LINK_SAVE_SETTINGS);
  const [persistentSiteAccess, setPersistentSiteAccess] = useState(false);
  const [deckNames, setDeckNames] = useState(["Topics"]);
  const [deckName, setDeckName] = useState("Topics");
  const [deckLoadError, setDeckLoadError] = useState("");
  const [priority, setPriority] = useState(DEFAULT_PRIORITY);
  const [priorityText, setPriorityText] = useState(formatPriority(DEFAULT_PRIORITY));
  const [tagsText, setTagsText] = useState("");

  const pageUrl = String(snapshot?.url || getTabUrl(activeTab) || "").trim();
  const pageTitle = String(snapshot?.title || activeTab?.title || "").trim();
  const selectionText = String(snapshot?.selectionText || "");
  const hasSupportedPage = Boolean(activeTab && isHttpUrl(pageUrl));
  const onVideoPage = isSupportedVideoUrl(pageUrl);
  const detectedTimeText = mediaContext?.hasDetectedTime ? formatMediaTime(mediaContext.seconds) : "";

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

        try {
          const enabled = await hasPersistentSiteAccess();
          if (!cancelled) {
            setPersistentSiteAccess(enabled);
          }
        } catch (_error) {
          if (!cancelled) {
            setPersistentSiteAccess(false);
          }
        }

        let nextSnapshot = null;
        if (tab?.id && isHttpUrl(getTabUrl(tab))) {
          nextSnapshot = await captureSnapshot(tab.id);
          if (cancelled) {
            return;
          }
          setSnapshot(nextSnapshot);
        }

        const nextTitle = String(nextSnapshot?.title || tab?.title || nextSnapshot?.url || getTabUrl(tab) || "").trim();
        if (nextTitle) {
          setTitle(nextTitle);
        }

        if (tab?.id) {
          try {
            const linked = await getLinkedCardContextForTab(tab.id, getTabUrl(tab));
            if (!cancelled) {
              setLinkedCard(linked?.linked ? {
                linked: true,
                cardId: Number(linked.cardId) || 0,
              } : { linked: false, cardId: 0 });
            }
          } catch (_error) {
            if (!cancelled) {
              setLinkedCard({ linked: false, cardId: 0 });
            }
          }

          if (isHttpUrl(getTabUrl(tab))) {
            try {
              const media = await getCurrentMediaContextForTab(tab.id);
              if (!cancelled) {
                setMediaContext(media?.ok ? media : null);
              }
            } catch (_error) {
              if (!cancelled) {
                setMediaContext(null);
              }
            }
          } else if (!cancelled) {
            setMediaContext(null);
          }
        }

        const commands = await getCommandShortcuts();
        if (!cancelled) {
          setCommandShortcuts(Array.isArray(commands) ? commands : []);
        }

        try {
          const meta = await loadBrowserCaptureMeta();
          if (cancelled) {
            return;
          }
          const nextDeckNames = Array.from(
            new Set(
              Array.isArray(meta?.deckNames)
                ? meta.deckNames.map((value) => String(value || "").trim()).filter(Boolean)
                : []
            )
          );
          const availableDecks = nextDeckNames.length > 0 ? nextDeckNames : ["Topics"];
          setDeckNames(availableDecks);
          setDeckName((currentDeck) => {
            if (availableDecks.includes(currentDeck)) {
              return currentDeck;
            }
            if (availableDecks.includes("Topics")) {
              return "Topics";
            }
            return availableDecks[0] || "Topics";
          });
          setDeckLoadError("");
        } catch (error) {
          if (!cancelled) {
            setDeckNames(["Topics"]);
            setDeckName((currentDeck) => currentDeck || "Topics");
            setDeckLoadError(formatBridgeError(error, "Failed to load decks from Anki. Using Topics."));
          }
        }

        const storedLinkSaveSettings = await getLocalExtensionSetting(
          LINK_SAVE_SETTINGS_KEY,
          DEFAULT_LINK_SAVE_SETTINGS,
        );
        if (!cancelled) {
          setLinkSaveSettings(normalizeLinkSaveSettings(storedLinkSaveSettings));
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

  async function refreshManualTimeContext(currentTab = null) {
    const tab = currentTab || await getActiveTab();
    if (!tab?.id) {
      setLinkedCard({ linked: false, cardId: 0 });
      setMediaContext(null);
      return { tab: null, linked: { linked: false, cardId: 0 }, media: null };
    }

    let linked = { linked: false, cardId: 0 };
    try {
      const result = await getLinkedCardContextForTab(tab.id, getTabUrl(tab));
      if (result?.linked && Number(result.cardId) > 0) {
        linked = {
          linked: true,
          cardId: Number(result.cardId) || 0,
        };
      }
    } catch (_error) {
      linked = { linked: false, cardId: 0 };
    }
    setLinkedCard(linked);

    let media = null;
    if (isHttpUrl(getTabUrl(tab))) {
      try {
        const result = await getCurrentMediaContextForTab(tab.id);
        media = result?.ok ? result : null;
      } catch (_error) {
        media = null;
      }
    }
    setMediaContext(media);
    if (currentTab) {
      setActiveTab(currentTab);
    }
    return { tab, linked, media };
  }

  async function readCurrentPageContext() {
    const tab = await getActiveTab();
    let nextSnapshot = null;
    if (tab?.id && isHttpUrl(getTabUrl(tab))) {
      nextSnapshot = await captureSnapshot(tab.id);
    }
    if (tab) {
      setActiveTab(tab);
    }
    setSnapshot(nextSnapshot);
    return {
      tab,
      snapshot: nextSnapshot,
      pageUrl: String(nextSnapshot?.url || getTabUrl(tab) || "").trim(),
      pageTitle: String(nextSnapshot?.title || tab?.title || nextSnapshot?.url || getTabUrl(tab) || "").trim(),
      selectionText: String(nextSnapshot?.selectionText || ""),
    };
  }

  async function resolveWebpageMediaTiming(tab, pageUrl) {
    const rawManualTime = String(manualTime || "").trim();
    const parsedManualTime = rawManualTime ? parseManualTimeInput(rawManualTime) : null;
    if (rawManualTime && parsedManualTime === null) {
      return {
        ok: false,
        error: "Enter a valid time like 12:34, 1:02:03, 90, or 1m30s.",
      };
    }

    const fallbackMedia = String(mediaContext?.pageUrl || "").trim() === String(pageUrl || "").trim()
      ? mediaContext
      : null;
    let media = fallbackMedia;
    if (tab?.id && isHttpUrl(pageUrl)) {
      try {
        const result = await getCurrentMediaContextForTab(tab.id);
        media = result?.ok ? result : null;
        setMediaContext(media);
      } catch (_error) {
        media = fallbackMedia;
      }
    }

    const detectedSeconds = media?.hasDetectedTime ? Number(media.seconds) : 0;
    const seconds = parsedManualTime ?? detectedSeconds;
    if (!Number.isFinite(Number(seconds)) || Number(seconds) <= 0) {
      return { ok: true, seconds: 0, media: media || null };
    }
    return {
      ok: true,
      seconds: Math.max(0, Math.floor(Number(seconds) || 0)),
      media: media || null,
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

  function handlePrioritySlider(value) {
    const nextPriority = sliderValueToPriority(value);
    setPriority(nextPriority);
    setPriorityText(formatPriority(nextPriority));
  }

  function handlePriorityText(value) {
    setPriorityText(value);
    const parsed = parsePriorityText(value, priority);
    if (parsed !== null) {
      setPriority(parsed);
    }
  }

  function commitPriorityText() {
    const parsed = parsePriorityText(priorityText, priority);
    const nextPriority = parsed ?? priority ?? DEFAULT_PRIORITY;
    setPriority(nextPriority);
    setPriorityText(formatPriority(nextPriority));
  }

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
      deckName,
      priority,
      tags: parseTags(tagsText),
      selectedText: currentSelectionText,
    };
    let currentLinkedCard = linkedCard;
    try {
      const linked = await getLinkedCardContextForTab(currentTab.id, currentPageUrl);
      currentLinkedCard = linked?.linked && Number(linked.cardId) > 0
        ? { linked: true, cardId: Number(linked.cardId) || 0 }
        : { linked: false, cardId: 0 };
      setLinkedCard(currentLinkedCard);
    } catch (_error) {
      currentLinkedCard = linkedCard;
    }
    if (currentLinkedCard?.linked && Number(currentLinkedCard.cardId) > 0) {
      payload.parentCardId = Math.max(0, Math.floor(Number(currentLinkedCard.cardId) || 0));
    }
    if (kind === "pdf" && currentSnapshot?.html) {
      payload.html = String(currentSnapshot.html);
    }
    if (kind === "writing") {
      const writingMode = String(options.writingMode || "selection");
      const shouldAutoTitle = shouldAutoGenerateWritingTitle(title, currentPageTitle, currentPageUrl);
      if (shouldAutoTitle) {
        payload.title = buildAutomaticWritingTitle(
          currentPageTitle,
          currentPageUrl,
          writingMode,
          currentSelectionText
        );
      }
      payload.writingMode = writingMode;
      payload.preferredFilename = buildPreferredWritingFilename(
        shouldAutoTitle ? currentPageTitle : payload.title,
        currentPageUrl
      );
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
    if (kind === "webpage") {
      const timing = await resolveWebpageMediaTiming(currentTab, currentPageUrl);
      if (!timing.ok) {
        setStatus({ text: timing.error || "Invalid web page time.", kind: "error" });
        return;
      }
      if (Number(timing.seconds) > 0) {
        payload.mediaSeconds = Number(timing.seconds);
        payload.mediaUrl = String(timing.media?.mediaUrl || "").trim();
        payload.mediaTitle = String(
          timing.media?.mediaTitle || timing.media?.pageTitle || currentPageTitle || ""
        ).trim();
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
      if (kind === "webpage" && currentTab?.id && Number(result?.cardId) > 0) {
        try {
          await registerWebCardTrackingForTab(currentTab.id, Number(result.cardId), currentPageUrl);
          setLinkedCard({ linked: true, cardId: Number(result.cardId) });
          if (Number(payload.mediaSeconds) > 0) {
            await updateBrowserMediaRefBadgeForTab(currentTab.id, {
              ok: true,
              hasReference: true,
              cardId: Number(result.cardId),
              pageUrl: currentPageUrl,
              mediaUrl: String(payload.mediaUrl || ""),
              mediaTitle: String(payload.mediaTitle || ""),
              seconds: Number(payload.mediaSeconds),
              timeText: formatMediaTime(payload.mediaSeconds),
            });
          }
        } catch (_error) {
          // Card creation succeeded; tracking can still start when the page is opened from Anki.
        }
      }
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

  async function handleSaveManualTime() {
    setBusy(true);
    setStatus({ text: "Saving browser time to the linked card...", kind: "" });
    try {
      const tab = await getActiveTab();
      if (!tab?.id) {
        setStatus({ text: "No active tab found.", kind: "error" });
        return;
      }

      const { linked, media } = await refreshManualTimeContext(tab);
      if (!linked?.linked || Number(linked.cardId) <= 0) {
        setStatus({
          text: "This tab is not linked to an Incremento card. Open the page from a card first.",
          kind: "error",
        });
        return;
      }

      const rawManualTime = String(manualTime || "").trim();
      const parsedManualTime = rawManualTime ? parseManualTimeInput(rawManualTime) : null;
      if (rawManualTime && parsedManualTime === null) {
        setStatus({
          text: "Enter a valid time like 12:34, 1:02:03, 90, or 1m30s.",
          kind: "error",
        });
        return;
      }

      const detectedSeconds = media?.hasDetectedTime ? Number(media.seconds) : null;
      const seconds = parsedManualTime ?? detectedSeconds;
      if (seconds === null || !Number.isFinite(Number(seconds)) || Number(seconds) < 0) {
        setStatus({
          text: "No current video time was detected. Enter a time manually to save it.",
          kind: "error",
        });
        return;
      }

      const pageUrlForSave = String(media?.pageUrl || getTabUrl(tab) || "").trim();
      if (!isHttpUrl(pageUrlForSave)) {
        setStatus({
          text: "Only normal http(s) pages can store browser times.",
          kind: "error",
        });
        return;
      }

      const saved = await saveBrowserMediaRef({
        cardId: Number(linked.cardId),
        pageUrl: pageUrlForSave,
        mediaUrl: String(media?.mediaUrl || "").trim(),
        mediaTitle: String(media?.mediaTitle || media?.pageTitle || tab.title || "").trim(),
        seconds: Number(seconds),
      });
      await updateBrowserMediaRefBadgeForTab(tab.id, saved);
      setManualTime("");
      setStatus({
        text: `Saved ${saved.timeText || formatMediaTime(saved.seconds)} to card ${saved.cardId}.`,
        kind: "success",
      });
    } catch (error) {
      setStatus({
        text: formatBridgeError(error, "Failed to save browser time."),
        kind: "error",
      });
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

  async function handleSaveLinkSettings() {
    setBusy(true);
    setStatus({ text: "Saving quick link settings...", kind: "" });
    try {
      const normalized = normalizeLinkSaveSettings(linkSaveSettings);
      await setLocalExtensionSetting(LINK_SAVE_SETTINGS_KEY, normalized);
      setLinkSaveSettings(normalized);
      setStatus({ text: "Saved quick link settings.", kind: "success" });
    } catch (error) {
      setStatus({
        text: error?.message || "Failed to save quick link settings.",
        kind: "error",
      });
    } finally {
      setBusy(false);
    }
  }

  async function handlePersistentSiteAccess() {
    setBusy(true);
    setStatus({
      text: persistentSiteAccess
        ? "Disabling automatic site access..."
        : "Requesting automatic site access...",
      kind: "",
    });
    try {
      if (persistentSiteAccess) {
        await removePersistentSiteAccess();
        const stillEnabled = await hasPersistentSiteAccess();
        setPersistentSiteAccess(stillEnabled);
        setStatus({
          text: stillEnabled
            ? "Chrome/Brave kept site access enabled. Change it in extension settings."
            : "Automatic site access disabled. User-triggered actions still work on the current tab.",
          kind: stillEnabled ? "error" : "success",
        });
        return;
      }

      const granted = await requestPersistentSiteAccess();
      setPersistentSiteAccess(granted);
      setStatus({
        text: granted
          ? "Automatic site access enabled for link saving and Web-card tracking across navigation."
          : "Site access was not granted. User-triggered actions still work on the current tab.",
        kind: granted ? "success" : "error",
      });
    } catch (error) {
      setPersistentSiteAccess(await hasPersistentSiteAccess().catch(() => false));
      setStatus({
        text: error?.message || "Could not change automatic site access.",
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
        <label className="field">
          <span>Deck</span>
          <select
            id="deck-select"
            value={deckName}
            disabled={busy}
            onChange={(event) => setDeckName(event.target.value)}
          >
            {deckNames.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        {deckLoadError ? (
          <p className="field-hint is-error">{deckLoadError}</p>
        ) : null}
        <label className="field">
          <span>Tags</span>
          <input
            id="tags-input"
            type="text"
            value={tagsText}
            placeholder="tag1 tag2"
            spellCheck="false"
            disabled={busy}
            onChange={(event) => setTagsText(event.target.value)}
          />
        </label>
        <label className="field">
          <span>Priority</span>
          <div className="priority-controls">
            <div className="priority-slider-wrap">
              <input
                className="priority-slider"
                type="range"
                min="0"
                max={String(PRIORITY_SLIDER_MAX)}
                step="1"
                value={String(priorityToSliderValue(priority))}
                disabled={busy}
                onChange={(event) => handlePrioritySlider(event.target.value)}
              />
              <div className="priority-scale">
                <span>0</span>
                <span>100</span>
              </div>
            </div>
            <input
              className="priority-number"
              type="text"
              inputMode="decimal"
              pattern="^\\d{1,3}(\\.\\d{0,4})?$"
              value={priorityText}
              placeholder="50.0000"
              spellCheck="false"
              disabled={busy}
              onChange={(event) => handlePriorityText(event.target.value)}
              onBlur={commitPriorityText}
            />
          </div>
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
        <div className="eyebrow">Automatic site access</div>
        <p className="note">
          On-demand actions use temporary access to the current tab. Enable persistent HTTP(S)
          access only if modifier-click saving and Web-card media tracking should continue after
          navigation.
        </p>
        <button
          className="ghost-btn"
          type="button"
          disabled={busy}
          onClick={() => void handlePersistentSiteAccess()}
        >
          {persistentSiteAccess
            ? "Disable automatic site access"
            : "Enable automatic site access..."}
        </button>
      </section>

      <section className="panel panel-secondary">
        <div className="eyebrow">Quick link save</div>
        <p className="note">
          Save clicked links directly to Incremento as webpage cards and optionally keep navigating.
        </p>
        <label className="toggle-row">
          <input
            type="checkbox"
            checked={linkSaveSettings.modifierClickEnabled}
            onChange={(event) => setLinkSaveSettings((current) => ({
              ...current,
              modifierClickEnabled: event.target.checked,
            }))}
          />
          <span>Enable modifier-click save on links</span>
        </label>
        <label className="field">
          <span>Modifier key</span>
          <select
            value={linkSaveSettings.modifierKey}
            onChange={(event) => setLinkSaveSettings((current) => ({
              ...current,
              modifierKey: event.target.value,
            }))}
          >
            {MODIFIER_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="toggle-row">
          <input
            type="checkbox"
            checked={linkSaveSettings.navigateAfterSave}
            onChange={(event) => setLinkSaveSettings((current) => ({
              ...current,
              navigateAfterSave: event.target.checked,
            }))}
          />
          <span>Continue following the link after saving</span>
        </label>
        <label className="toggle-row">
          <input
            type="checkbox"
            checked={linkSaveSettings.contextMenuEnabled}
            onChange={(event) => setLinkSaveSettings((current) => ({
              ...current,
              contextMenuEnabled: event.target.checked,
            }))}
          />
          <span>Enable right-click link action</span>
        </label>
        <button
          className="ghost-btn"
          type="button"
          disabled={busy}
          onClick={() => void handleSaveLinkSettings()}
        >
          Save quick link settings
        </button>
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
        <div className="eyebrow">Linked card</div>
        <p className="note">
          {linkedCard.linked && linkedCard.cardId > 0
            ? `This tab is linked to card ${linkedCard.cardId}.`
            : "This tab is not linked to an Incremento card yet. Open it from a card's browser action first."}
        </p>
        <p className="note">
          {detectedTimeText
            ? `Detected current video time: ${detectedTimeText}`
            : "No current video time detected on this page right now."}
        </p>
        <label className="field">
          <span>Manual time</span>
          <input
            id="manual-time-input"
            type="text"
            spellCheck="false"
            placeholder="12:34, 1:02:03, 90, or 1m30s"
            value={manualTime}
            onChange={(event) => setManualTime(event.target.value)}
          />
        </label>
        <button
          className="kind-btn"
          type="button"
          disabled={busy || !activeTab || !hasSupportedPage}
          onClick={() => void handleSaveManualTime()}
        >
          Save manual time
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
