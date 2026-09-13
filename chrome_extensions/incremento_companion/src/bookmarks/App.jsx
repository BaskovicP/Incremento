import { useEffect, useMemo, useState } from "react";
import { loadBookmarksTree } from "../shared/chromeApi.js";
import { formatBridgeError, importIntoIncremento, loadBrowserCaptureMeta } from "../shared/bridge.js";
import { getPdfPayloadForUrl } from "../shared/pdfFetch.js";
import {
  DEFAULT_PRIORITY,
  buildBookmarkItems,
  collectBookmarkIds,
  findNodeById,
  formatPriority,
  getSelectedItems,
  parseTags,
  parsePriorityText,
  setSelectedForIds,
  sliderValueToPriority,
  updateBookmarkItem,
} from "./bookmarkModel.js";
import { BookmarkTree } from "./components/BookmarkTree.jsx";
import { ImportRows } from "./components/ImportRows.jsx";
import { ProgressPanel } from "./components/ProgressPanel.jsx";
import { ResultsList } from "./components/ResultsList.jsx";
import { displayMessage, message, t, tn } from "../shared/i18n.js";
import { useLanguage } from "../shared/i18nReact.js";

function makeStatus(text = "", kind = "") {
  return { text, kind };
}

function makeProgress(total = 0, completed = 0, note = message("waiting_start")) {
  const safeTotal = Math.max(0, Number(total) || 0);
  const safeCompleted = Math.max(0, Math.min(safeTotal, Number(completed) || 0));
  return {
    total: safeTotal,
    completed: safeCompleted,
    note,
    percent: safeTotal > 0 ? Math.round((safeCompleted / safeTotal) * 100) : 0,
  };
}

export function BookmarksApp() {
  const language = useLanguage();
  const [tree, setTree] = useState([]);
  const [itemsById, setItemsById] = useState({});
  const [deckNames, setDeckNames] = useState(["Topics"]);
  const [deckName, setDeckName] = useState("Topics");
  const [deckLoadError, setDeckLoadError] = useState("");
  const [treeLoadError, setTreeLoadError] = useState(false);
  const [treeLoaded, setTreeLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(makeStatus());
  const [results, setResults] = useState([]);
  const [progress, setProgress] = useState(makeProgress());

  const selectedItems = useMemo(
    () => getSelectedItems(itemsById).sort((left, right) => left.title.localeCompare(right.title, language)),
    [itemsById, language]
  );

  async function loadBookmarks() {
    setBusy(true);
    setStatus(makeStatus(message("loading_bookmarks")));
    setProgress(makeProgress());
    setResults([]);
    try {
      const nextTree = await loadBookmarksTree();
      const nextItemsById = buildBookmarkItems(nextTree);
      setTree(nextTree);
      setItemsById(nextItemsById);
      setTreeLoadError(false);
      setTreeLoaded(true);
      setStatus(makeStatus(message("bookmarks_loaded")));
    } catch (error) {
      setTree([]);
      setItemsById({});
      setTreeLoadError(true);
      setTreeLoaded(true);
      setStatus(makeStatus(error?.message || t("load_bookmarks_failed"), "error"));
    } finally {
      setBusy(false);
    }
  }

  async function loadDecks() {
    try {
      const meta = await loadBrowserCaptureMeta();
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
      setDeckNames(["Topics"]);
      setDeckName((currentDeck) => currentDeck || "Topics");
      setDeckLoadError(error);
    }
  }

  useEffect(() => {
    void loadBookmarks();
    void loadDecks();
  }, []);

  function toggleFolder(folderId, checked) {
    const node = findNodeById(tree, folderId);
    if (!node) {
      return;
    }
    const bookmarkIds = collectBookmarkIds(node, itemsById);
    setItemsById((currentItems) => setSelectedForIds(currentItems, bookmarkIds, checked));
  }

  function toggleBookmark(bookmarkId, checked) {
    setItemsById((currentItems) => setSelectedForIds(currentItems, [bookmarkId], checked));
  }

  function updateTitle(bookmarkId, value) {
    setItemsById((currentItems) => updateBookmarkItem(
      currentItems,
      bookmarkId,
      { title: value.trim() || "Untitled bookmark" }
    ));
  }

  function updateKind(bookmarkId, value) {
    setItemsById((currentItems) => updateBookmarkItem(currentItems, bookmarkId, { kind: value }));
  }

  function updateTags(bookmarkId, value) {
    setItemsById((currentItems) => updateBookmarkItem(currentItems, bookmarkId, { tagsText: value }));
  }

  function updatePrioritySlider(bookmarkId, sliderValue) {
    const priority = sliderValueToPriority(sliderValue);
    setItemsById((currentItems) => updateBookmarkItem(currentItems, bookmarkId, {
      priority,
      priorityText: formatPriority(priority),
    }));
  }

  function updatePriorityText(bookmarkId, value) {
    const text = String(value ?? "");
    if (!/^\d{0,3}(\.\d{0,4})?$/.test(text)) {
      return;
    }
    setItemsById((currentItems) => {
      const item = currentItems[bookmarkId];
      if (!item) {
        return currentItems;
      }
      const parsed = parsePriorityText(text, item.priority);
      return updateBookmarkItem(currentItems, bookmarkId, {
        priorityText: text,
        priority: parsed ?? item.priority,
      });
    });
  }

  function commitPriorityText(bookmarkId) {
    setItemsById((currentItems) => {
      const item = currentItems[bookmarkId];
      if (!item) {
        return currentItems;
      }
      const parsed = parsePriorityText(item.priorityText, item.priority ?? DEFAULT_PRIORITY);
      const priority = parsed ?? item.priority ?? DEFAULT_PRIORITY;
      return updateBookmarkItem(currentItems, bookmarkId, {
        priority,
        priorityText: formatPriority(priority),
      });
    });
  }

  async function importSelected() {
    const items = selectedItems.map((item) => ({
      id: item.id,
      kind: item.kind,
      url: item.url,
      title: item.title,
      tags: parseTags(item.tagsText),
      priority: item.priority,
    }));
    if (items.length === 0) {
      setStatus(makeStatus(message("select_bookmark_first"), "error"));
      return;
    }

    setBusy(true);
    setStatus(makeStatus(message("importing_bookmarks", {}, items.length)));
    setProgress(makeProgress(items.length, 0, message("preparing_import")));
    setResults([]);
    setItemsById((currentItems) => {
      const nextItems = { ...currentItems };
      for (const item of Object.values(nextItems)) {
        nextItems[item.id] = {
          ...item,
          importState: "",
          importError: "",
          importErrorCause: null,
        };
      }
      return nextItems;
    });

    const nextResults = [];
    let okCount = 0;
    let failCount = 0;

    try {
      for (let index = 0; index < items.length; index += 1) {
        const item = items[index];
        setProgress(makeProgress(items.length, index, message("importing_item", { index: index + 1, count: items.length, title: item.title })));

        let result;
        try {
          const payload = {
            kind: item.kind,
            url: item.url,
            title: item.title,
            deckName,
            tags: item.tags,
            priority: item.priority,
          };
          if (item.kind === "pdf") {
            const pdfPayload = await getPdfPayloadForUrl(item.url);
            if (pdfPayload) {
              payload.pdfBase64 = pdfPayload.pdfBase64;
              payload.pdfFilename = pdfPayload.pdfFilename;
            }
          }

          result = await importIntoIncremento(payload);
          okCount += 1;
          setItemsById((currentItems) => updateBookmarkItem(currentItems, item.id, {
            importState: "success",
            importError: "",
            importErrorCause: null,
          }));
        } catch (error) {
          const message = formatBridgeError(error, t("import_bookmark_failed"));
          result = {
            ok: false,
            kind: item.kind,
            title: item.title,
            error: message,
            errorCause: error,
          };
          failCount += 1;
          setItemsById((currentItems) => updateBookmarkItem(currentItems, item.id, {
            importState: "error",
            importError: message,
            importErrorCause: error,
          }));
        }

        nextResults.push(result);
        setResults([...nextResults]);
        setProgress(
          makeProgress(
            items.length,
            index + 1,
            result?.ok
              ? message("imported_item", { index: index + 1, count: items.length, title: item.title })
              : message("failed_item", { index: index + 1, count: items.length, title: item.title })
          )
        );
      }

      if (failCount > 0) {
        setStatus(makeStatus(
          message("imported_failed", { ok: okCount, failed: failCount }),
          "error"
        ));
        setProgress(makeProgress(items.length, items.length, message("finished_with_errors", { ok: okCount, failed: failCount })));
      } else {
        setStatus(makeStatus(message("imported_bookmarks", {}, okCount), "success"));
        setProgress(makeProgress(items.length, items.length, message("finished_bookmarks", {}, okCount)));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page">
      <section className="hero">
        <div className="eyebrow">{t("bookmark_import")}</div>
        <h1>{t("send_chrome_bookmarks")}</h1>
        <p className="hero-copy">
          {t("bookmark_import_intro")}
        </p>
      </section>

      <ProgressPanel progress={progress} />

      <section className="workspace">
        <aside className="panel tree-panel">
          <div className="panel-head">
            <h2>{t("bookmarks")}</h2>
            <button
              className="ghost-btn ghost-btn-inline"
              id="reload-bookmarks"
              disabled={busy}
              onClick={() => void loadBookmarks()}
            >
              {t("reload")}
            </button>
          </div>
          <p className="muted">{t("folder_includes_nested")}</p>
          <div className="bookmark-tree" id="bookmark-tree">
            {tree.length > 0 ? (
              <BookmarkTree
                nodes={tree}
                itemsById={itemsById}
                disabled={busy}
                onToggleFolder={toggleFolder}
                onToggleBookmark={toggleBookmark}
              />
            ) : treeLoadError ? (
              <div className="empty-state">{t("load_bookmarks_failed")}</div>
            ) : treeLoaded ? (
              <div className="empty-state">{t("no_bookmarks")}</div>
            ) : null}
          </div>
        </aside>

        <section className="panel rows-panel">
          <div className="panel-head">
            <div>
              <h2>{t("import_list")}</h2>
              <p className="muted" id="selection-summary">
                {tn("bookmarks_selected", selectedItems.length)}
              </p>
            </div>
            <button
              className="primary-btn"
              id="import-selected"
              disabled={busy}
              onClick={() => void importSelected()}
            >
              {t("import_selected")}
            </button>
          </div>
          <div className="global-controls">
            <div className="field deck-field">
              <span className="field-label">{t("import_deck")}</span>
              <select
                id="bookmark-deck-select"
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
              <p className="deck-hint">{t("all_selected_deck")}</p>
              {deckLoadError ? (
                <p className="deck-hint is-error">{formatBridgeError(deckLoadError, t("deck_load_failed"))}</p>
              ) : null}
            </div>
          </div>
          <ImportRows
            items={selectedItems}
            disabled={busy}
            onToggleSelected={toggleBookmark}
            onUpdateTitle={updateTitle}
            onUpdateKind={updateKind}
            onUpdateTags={updateTags}
            onUpdatePrioritySlider={updatePrioritySlider}
            onUpdatePriorityText={updatePriorityText}
            onCommitPriorityText={commitPriorityText}
          />
          <p className={`status${status.kind ? ` is-${status.kind}` : ""}`} id="status" role="status" aria-live="polite">
            {displayMessage(status.text)}
          </p>
          <ResultsList results={results} />
        </section>
      </section>
    </main>
  );
}
