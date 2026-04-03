import { useEffect, useMemo, useState } from "react";
import { loadBookmarksTree } from "../shared/chromeApi.js";
import { formatBridgeError, importIntoIncremento } from "../shared/bridge.js";
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

function makeStatus(text = "", kind = "") {
  return { text, kind };
}

function makeProgress(total = 0, completed = 0, note = "Waiting to start.") {
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
  const [tree, setTree] = useState([]);
  const [itemsById, setItemsById] = useState({});
  const [treeLoadError, setTreeLoadError] = useState(false);
  const [treeLoaded, setTreeLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(makeStatus());
  const [results, setResults] = useState([]);
  const [progress, setProgress] = useState(makeProgress());

  const selectedItems = useMemo(
    () => getSelectedItems(itemsById).sort((left, right) => left.title.localeCompare(right.title)),
    [itemsById]
  );

  async function loadBookmarks() {
    setBusy(true);
    setStatus(makeStatus("Loading bookmarks..."));
    setProgress(makeProgress());
    setResults([]);
    try {
      const nextTree = await loadBookmarksTree();
      const nextItemsById = buildBookmarkItems(nextTree);
      setTree(nextTree);
      setItemsById(nextItemsById);
      setTreeLoadError(false);
      setTreeLoaded(true);
      setStatus(makeStatus("Bookmarks loaded."));
    } catch (error) {
      setTree([]);
      setItemsById({});
      setTreeLoadError(true);
      setTreeLoaded(true);
      setStatus(makeStatus(error?.message || "Failed to load bookmarks.", "error"));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void loadBookmarks();
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
      setStatus(makeStatus("Select at least one bookmark before importing.", "error"));
      return;
    }

    setBusy(true);
    setStatus(makeStatus(`Importing ${items.length} bookmark${items.length === 1 ? "" : "s"}...`));
    setProgress(makeProgress(items.length, 0, "Preparing import..."));
    setResults([]);
    setItemsById((currentItems) => {
      const nextItems = { ...currentItems };
      for (const item of Object.values(nextItems)) {
        nextItems[item.id] = {
          ...item,
          importState: "",
          importError: "",
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
        setProgress(makeProgress(items.length, index, `Importing ${index + 1} of ${items.length}: ${item.title}`));

        let result;
        try {
          const payload = {
            kind: item.kind,
            url: item.url,
            title: item.title,
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
          }));
        } catch (error) {
          const message = formatBridgeError(error, "Failed to import bookmark.");
          result = {
            ok: false,
            kind: item.kind,
            title: item.title,
            error: message,
          };
          failCount += 1;
          setItemsById((currentItems) => updateBookmarkItem(currentItems, item.id, {
            importState: "error",
            importError: message,
          }));
        }

        nextResults.push(result);
        setResults([...nextResults]);
        setProgress(
          makeProgress(
            items.length,
            index + 1,
            result?.ok
              ? `Imported ${index + 1} of ${items.length}: ${item.title}`
              : `Failed ${index + 1} of ${items.length}: ${item.title}`
          )
        );
      }

      if (failCount > 0) {
        setStatus(makeStatus(
          `Imported ${okCount} bookmark${okCount === 1 ? "" : "s"}; ${failCount} failed.`,
          "error"
        ));
        setProgress(makeProgress(items.length, items.length, `Finished with ${okCount} imported and ${failCount} failed.`));
      } else {
        setStatus(makeStatus(`Imported ${okCount} bookmark${okCount === 1 ? "" : "s"}.`, "success"));
        setProgress(makeProgress(items.length, items.length, `Finished importing ${okCount} bookmark${okCount === 1 ? "" : "s"}.`));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page">
      <section className="hero">
        <div className="eyebrow">Bookmark Import</div>
        <h1>Send Chrome bookmarks to Incremento</h1>
        <p className="hero-copy">
          Select folders or individual bookmarks, edit tags per row, choose whether each item
          becomes a PDF, YouTube/Video, Webpage, or Writing card, and set each card priority
          before importing them in one run.
        </p>
      </section>

      <ProgressPanel progress={progress} />

      <section className="workspace">
        <aside className="panel tree-panel">
          <div className="panel-head">
            <h2>Bookmarks</h2>
            <button
              className="ghost-btn ghost-btn-inline"
              id="reload-bookmarks"
              disabled={busy}
              onClick={() => void loadBookmarks()}
            >
              Reload
            </button>
          </div>
          <p className="muted">Checking a folder includes all nested bookmark links.</p>
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
              <div className="empty-state">Failed to load bookmarks.</div>
            ) : treeLoaded ? (
              <div className="empty-state">No bookmarks available.</div>
            ) : null}
          </div>
        </aside>

        <section className="panel rows-panel">
          <div className="panel-head">
            <div>
              <h2>Import list</h2>
              <p className="muted" id="selection-summary">
                {`${selectedItems.length} bookmark${selectedItems.length === 1 ? "" : "s"} selected`}
              </p>
            </div>
            <button
              className="primary-btn"
              id="import-selected"
              disabled={busy}
              onClick={() => void importSelected()}
            >
              Import selected
            </button>
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
            {status.text}
          </p>
          <ResultsList results={results} />
        </section>
      </section>
    </main>
  );
}
