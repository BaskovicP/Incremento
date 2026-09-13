import { useEffect, useMemo, useRef, useState } from "react";
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
import { normalizeAvailableTags } from "../shared/tagAutocomplete.js";
import { TagAutocompleteInput } from "./TagAutocompleteInput.jsx";
import { LanguageSettingsPanel } from "./LanguageSettingsPanel.jsx";
import { currentPreference, currentLanguagePacks, resolveLocale, displayMessage, message, saveLanguageSettings, t, formatNumber } from "../shared/i18n.js";
import { builtinLanguagePack, downloadLanguagePackCsv, readLanguagePackFile, packCoverage, stageLanguagePack, LanguagePackError, MAX_PACKS } from "../shared/languagePacks.js";
import { useLanguage } from "../shared/i18nReact.js";
import { cardKindMessage } from "../shared/cardKind.js";

function languagePackErrorText(error) {
  const reasonKeys = {
    header: "language_pack_error_header", metadata: "language_pack_error_metadata",
    version: "language_pack_error_version", locale: "language_pack_error_locale",
    name: "language_pack_error_name", duplicate: "language_pack_error_duplicate",
    unknown: "language_pack_error_unknown", component: "language_pack_error_unknown",
    source: "language_pack_error_source", tokens: "language_pack_error_tokens",
    markup: "language_pack_error_markup", size: "language_pack_error_size",
    rows: "language_pack_error_rows", cell: "language_pack_error_cell", packs: "language_pack_error_packs",
    columns: "language_pack_error_csv", csv: "language_pack_error_csv", encoding: "language_pack_error_encoding",
  };
  if (error instanceof LanguagePackError) return t("language_pack_error", {row: formatNumber(error.row), reason: t(reasonKeys[error.code] || "language_pack_error_file")});
  return t("language_pack_error_file");
}

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
  const language = useLanguage();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [languageDraft, setLanguageDraft] = useState(currentPreference);
  const [languageBusy, setLanguageBusy] = useState(false);
  const [languageError, setLanguageError] = useState("");
  const [languagePacksDraft, setLanguagePacksDraft] = useState({});
  const [languagePackPreview, setLanguagePackPreview] = useState(null);
  const languageFileInput = useRef(null);
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
  const [tagNames, setTagNames] = useState([]);

  const pageUrl = String(snapshot?.url || getTabUrl(activeTab) || "").trim();
  const pageTitle = String(snapshot?.title || activeTab?.title || "").trim();
  const selectionText = String(snapshot?.selectionText || "");
  const hasSupportedPage = Boolean(activeTab && isHttpUrl(pageUrl));
  const onVideoPage = isSupportedVideoUrl(pageUrl);
  const detectedTimeText = mediaContext?.hasDetectedTime ? formatMediaTime(mediaContext.seconds) : "";

  function openSettings() {
    setLanguageDraft(currentPreference());
    setLanguagePacksDraft({});
    setLanguagePackPreview(null);
    setLanguageError("");
    setSettingsOpen(true);
  }

  async function saveSettingsLanguage() {
    setLanguageBusy(true);
    setLanguageError("");
    try {
      await saveLanguageSettings(languageDraft, languagePacksDraft);
      setSettingsOpen(false);
    } catch (error) {
      setLanguageError(error instanceof LanguagePackError ? languagePackErrorText(error) : t("language_save_error"));
    } finally {
      setLanguageBusy(false);
    }
  }

  async function importLanguageFile(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setLanguageBusy(true);
    setLanguageError("");
    try {
      const pack = await readLanguagePackFile(file);
      const staged = stageLanguagePack(languagePacksDraft, pack);
      if (Object.keys({...currentLanguagePacks(), ...staged}).length > MAX_PACKS) throw new LanguagePackError("packs");
      setLanguagePacksDraft(staged);
      setLanguageDraft(`custom:${pack.locale}`);
      setLanguagePackPreview({name: pack.name, ...packCoverage(pack)});
    } catch (error) {
      setLanguageError(languagePackErrorText(error));
    } finally {
      setLanguageBusy(false);
    }
  }

  async function exportLanguageFile(blank = false) {
    setLanguageBusy(true);
    setLanguageError("");
    try {
      let pack = null;
      if (!blank) {
        pack = languageDraft.startsWith("custom:")
          ? {...currentLanguagePacks(), ...languagePacksDraft}[languageDraft.slice(7)]
          : await builtinLanguagePack(resolveLocale(languageDraft, chrome.i18n.getUILanguage()));
        if (!pack) throw new LanguagePackError("locale");
      }
      downloadLanguagePackCsv(pack);
    } catch (error) {
      setLanguageError(languagePackErrorText(error));
    } finally {
      setLanguageBusy(false);
    }
  }

  const writingNote = useMemo(() => {
    if (onVideoPage) {
      return t("video_cards_note");
    }
    if (selectionText) {
      return t("selection_writing_note", { count: selectionText.length });
    }
    return t("page_writing_note");
  }, [onVideoPage, selectionText, language]);

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
          setTagNames(normalizeAvailableTags(meta?.tagNames));
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
            setTagNames([]);
            setDeckName((currentDeck) => currentDeck || "Topics");
            setDeckLoadError(error);
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
            text: error?.message || t("page_inspect_failed"),
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
        error: t("manual_time_invalid"),
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
        text: message("open_http_page"),
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
      setStatus({ text: message("no_active_tab"), kind: "error" });
      return;
    }
    if (!isHttpUrl(currentPageUrl)) {
      setStatus({ text: message("only_http_pages"), kind: "error" });
      return;
    }
    if (kind === "video" && !isSupportedVideoUrl(currentPageUrl)) {
      setStatus({ text: message("open_video_page"), kind: "error" });
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
          text: message("select_page_text"),
          kind: "error",
        });
        return;
      }
      if (writingMode === "webpage_markdown") {
        payload.pageContentScope = String(pageContentScope || "main");
        if (!currentSnapshot?.html) {
          setStatus({
            text: message("web_content_failed"),
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
        setStatus({ text: timing.error || t("web_time_invalid"), kind: "error" });
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
        ? message("adding_writing")
        : message("adding_card", { kind: cardKindMessage(kind) })
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
      setStatus({ text: message("added_card", { kind: cardKindMessage(result.kind), title: result.title }), kind: "success" });
    } catch (error) {
      setStatus({
        text: formatBridgeError(error, t("add_content_failed")),
        kind: "error",
      });
    } finally {
      setBusy(false);
    }
  }

  async function handleCopyVideoTime() {
    setBusy(true);
    setStatus({ text: message("copying_video_time"), kind: "" });
    try {
      const response = await copyLatestVideoTime();
      if (response?.ok) {
        setStatus({ text: message("copied_video_time"), kind: "success" });
      } else {
        setStatus({ text: message("no_stored_video_time"), kind: "error" });
      }
    } catch (error) {
      setStatus({ text: error?.message || t("copy_video_time_failed"), kind: "error" });
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveManualTime() {
    setBusy(true);
    setStatus({ text: message("saving_browser_time"), kind: "" });
    try {
      const tab = await getActiveTab();
      if (!tab?.id) {
        setStatus({ text: message("no_active_tab"), kind: "error" });
        return;
      }

      const { linked, media } = await refreshManualTimeContext(tab);
      if (!linked?.linked || Number(linked.cardId) <= 0) {
        setStatus({
          text: message("tab_not_linked"),
          kind: "error",
        });
        return;
      }

      const rawManualTime = String(manualTime || "").trim();
      const parsedManualTime = rawManualTime ? parseManualTimeInput(rawManualTime) : null;
      if (rawManualTime && parsedManualTime === null) {
        setStatus({
          text: message("manual_time_invalid"),
          kind: "error",
        });
        return;
      }

      const detectedSeconds = media?.hasDetectedTime ? Number(media.seconds) : null;
      const seconds = parsedManualTime ?? detectedSeconds;
      if (seconds === null || !Number.isFinite(Number(seconds)) || Number(seconds) < 0) {
        setStatus({
          text: message("no_detected_time"),
          kind: "error",
        });
        return;
      }

      const pageUrlForSave = String(media?.pageUrl || getTabUrl(tab) || "").trim();
      if (!isHttpUrl(pageUrlForSave)) {
        setStatus({
          text: message("only_http_time"),
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
        text: message("saved_time_card", { time: saved.timeText || formatMediaTime(saved.seconds), count: saved.cardId }),
        kind: "success",
      });
    } catch (error) {
      setStatus({
        text: formatBridgeError(error, t("save_browser_time_failed")),
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
        text: error?.message || t("open_bookmarks_failed"),
        kind: "error",
      });
    }
  }

  async function handleOpenShortcutsPage() {
    try {
      await openExtensionShortcutsPage();
    } catch (error) {
      setStatus({
        text: error?.message || t("open_shortcuts_failed"),
        kind: "error",
      });
    }
  }

  async function handleTriggerBrowserCapture(mode) {
    if (!activeTab?.id) {
      setStatus({
        text: message("no_active_tab"),
        kind: "error",
      });
      return;
    }
    setBusy(true);
    setStatus({
      text: mode === "snapshot" ? message("starting_snapshot") : message("starting_text_capture"),
      kind: "",
    });
    try {
      const response = await triggerBrowserCaptureForTab(activeTab.id, mode);
      if (response?.ok) {
        setStatus({
          text: mode === "snapshot" ? message("snapshot_opened") : message("text_capture_opened"),
          kind: "success",
        });
        window.close();
        return;
      }
      setStatus({
        text: response?.error || (mode === "snapshot"
          ? message("snapshot_not_started")
          : message("text_capture_not_started")),
        kind: "error",
      });
    } catch (error) {
      setStatus({
        text: error?.message || t("trigger_capture_failed"),
        kind: "error",
      });
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveLinkSettings() {
    setBusy(true);
    setStatus({ text: message("saving_link_settings"), kind: "" });
    try {
      const normalized = normalizeLinkSaveSettings(linkSaveSettings);
      await setLocalExtensionSetting(LINK_SAVE_SETTINGS_KEY, normalized);
      setLinkSaveSettings(normalized);
      setStatus({ text: message("saved_link_settings"), kind: "success" });
    } catch (error) {
      setStatus({
        text: error?.message || t("save_link_settings_failed"),
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
        ? message("disabling_site_access")
        : message("requesting_site_access"),
      kind: "",
    });
    try {
      if (persistentSiteAccess) {
        await removePersistentSiteAccess();
        const stillEnabled = await hasPersistentSiteAccess();
        setPersistentSiteAccess(stillEnabled);
        setStatus({
          text: stillEnabled
            ? message("site_access_still_enabled")
            : message("site_access_disabled"),
          kind: stillEnabled ? "error" : "success",
        });
        return;
      }

      const granted = await requestPersistentSiteAccess();
      setPersistentSiteAccess(granted);
      setStatus({
        text: granted
          ? message("site_access_enabled")
          : message("site_access_not_granted"),
        kind: granted ? "success" : "error",
      });
    } catch (error) {
      setPersistentSiteAccess(await hasPersistentSiteAccess().catch(() => false));
      setStatus({
        text: error?.message || t("site_access_change_failed"),
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
      <nav className="popup-navigation">
        <button className="ghost-btn" type="button" disabled={settingsOpen && languageBusy} onClick={settingsOpen ? () => setSettingsOpen(false) : openSettings}>
          {settingsOpen ? t("language_cancel") : t("settings")}
        </button>
      </nav>
      <div hidden={settingsOpen}>
      <section className="panel">
        <div className="eyebrow">{t("current_page")}</div>
        <h1>{t("send_to_incremento")}</h1>
        <p className="muted" id="page-url">{pageUrl || t("no_supported_page")}</p>
        <label className="field">
          <span>{t("title")}</span>
          <input
            id="title-input"
            type="text"
            spellCheck="false"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <label className="field">
          <span>{t("deck")}</span>
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
          <p className="field-hint is-error">{formatBridgeError(deckLoadError, t("deck_load_failed"))}</p>
        ) : null}
        <div className="field">
          <label htmlFor="tags-input">{t("tags")}</label>
          <TagAutocompleteInput
            id="tags-input"
            value={tagsText}
            availableTags={tagNames}
            disabled={busy}
            onChange={setTagsText}
          />
          <p className="field-hint">{t("tag_hint")}</p>
        </div>
        <label className="field">
          <span>{t("priority")}</span>
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
          <span>{t("markdown_scope")}</span>
          <select
            id="writing-scope"
            value={pageContentScope}
            onChange={(event) => setPageContentScope(event.target.value)}
          >
            <option value="main">{t("main_content")}</option>
            <option value="full">{t("entire_page")}</option>
          </select>
        </label>
        <div className="actions">
          <button
            className="kind-btn"
            data-kind="pdf"
            disabled={busy || !hasSupportedPage}
            onClick={() => void handleAdd("pdf")}
          >
            {t("add_as_pdf")}
          </button>
          <button
            className="kind-btn"
            data-kind="video"
            disabled={busy || !hasSupportedPage || !onVideoPage}
            onClick={() => void handleAdd("video")}
          >
            {t("add_as_video")}
          </button>
          <button
            className="kind-btn"
            data-kind="webpage"
            disabled={busy || !hasSupportedPage}
            onClick={() => void handleAdd("webpage")}
          >
            {t("add_as_webpage")}
          </button>
          <button
            className="kind-btn"
            data-kind="writing"
            disabled={busy || !hasSupportedPage}
            onClick={() => void handleAdd("writing", { writingMode: "selection" })}
          >
            {t("add_selection_markdown")}
          </button>
          <button
            className="kind-btn"
            data-kind="writing-page"
            disabled={busy || !hasSupportedPage}
            onClick={() => void handleAdd("writing", { writingMode: "webpage_markdown" })}
          >
            {t("add_page_markdown")}
          </button>
        </div>
        <p className={`status${status.kind ? ` is-${status.kind}` : ""}`} id="status" role="status" aria-live="polite">
          {displayMessage(status.text)}
        </p>
      </section>

      <section className="panel panel-secondary">
        <div className="eyebrow">{t("automatic_site_access")}</div>
        <p className="note">
          {t("automatic_site_access_note")}
        </p>
        <button
          className="ghost-btn"
          type="button"
          disabled={busy}
          onClick={() => void handlePersistentSiteAccess()}
        >
          {persistentSiteAccess
            ? t("disable_auto_site_access")
            : t("enable_auto_site_access")}
        </button>
      </section>

      <section className="panel panel-secondary">
        <div className="eyebrow">{t("quick_link_save")}</div>
        <p className="note">
          {t("quick_link_save_note")}
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
          <span>{t("enable_modifier_save")}</span>
        </label>
        <label className="field">
          <span>{t("modifier_key")}</span>
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
          <span>{t("continue_following_link")}</span>
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
          <span>{t("enable_context_link")}</span>
        </label>
        <button
          className="ghost-btn"
          type="button"
          disabled={busy}
          onClick={() => void handleSaveLinkSettings()}
        >
          {t("save_quick_link_settings")}
        </button>
      </section>

      <section className="panel panel-secondary">
        <button
          className="ghost-btn"
          id="open-bookmarks"
          disabled={busy}
          onClick={() => void handleOpenBookmarks()}
        >
          {t("download_bookmarks")}
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
            {t("trigger_text_capture")}
          </button>
          <button
            className="kind-btn"
            type="button"
            disabled={busy || !hasSupportedPage}
            onClick={() => void handleTriggerBrowserCapture("snapshot")}
          >
            {t("trigger_snapshot_capture")}
          </button>
        </div>
      </section>

      <section className="panel panel-secondary">
        <div className="shortcut-status">
          <div>
            <strong>{t("text_capture")}</strong>
            <span>{selectionShortcut || t("not_assigned_chrome")}</span>
          </div>
          <div>
            <strong>{t("snapshot_capture")}</strong>
            <span>{snapshotShortcut || t("not_assigned_chrome")}</span>
          </div>
        </div>
        <button
          className="ghost-btn"
          type="button"
          onClick={() => void handleOpenShortcutsPage()}
        >
          {t("open_shortcut_settings")}
        </button>
      </section>

      <section className="panel panel-secondary">
        <div className="eyebrow">{t("linked_card")}</div>
        <p className="note">
          {linkedCard.linked && linkedCard.cardId > 0
            ? t("linked_card_status", { count: linkedCard.cardId })
            : t("not_linked_card_status")}
        </p>
        <p className="note">
          {detectedTimeText
            ? t("detected_video_time", { time: detectedTimeText })
            : t("no_video_time_page")}
        </p>
        <label className="field">
          <span>{t("manual_time")}</span>
          <input
            id="manual-time-input"
            type="text"
            spellCheck="false"
            placeholder={t("manual_time_placeholder")}
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
          {t("save_manual_time")}
        </button>
      </section>

      <section className="panel panel-secondary">
        <button
          className="ghost-btn"
          id="copy-video-time"
          disabled={busy}
          onClick={() => void handleCopyVideoTime()}
        >
          {t("copy_last_video_time")}
        </button>
      </section>
      </div>
      {settingsOpen ? (
        <LanguageSettingsPanel
          languageDraft={languageDraft} pendingPacks={languagePacksDraft}
          busy={languageBusy} error={languageError} preview={languagePackPreview}
          fileInputRef={languageFileInput} onSelect={setLanguageDraft}
          onExportTemplate={() => void exportLanguageFile(true)}
          onExportSelected={() => void exportLanguageFile()}
          onImport={event => void importLanguageFile(event)}
          onSave={() => void saveSettingsLanguage()}
          onCancel={() => setSettingsOpen(false)}
        />
      ) : null}
    </main>
  );
}
