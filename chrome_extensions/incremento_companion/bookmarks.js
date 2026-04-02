"use strict";

const BRIDGE_URL = "http://127.0.0.1:8766/incremento/add-content";

const state = {
  tree: [],
  items: new Map(),
  busy: false,
};

const treeEl = document.getElementById("bookmark-tree");
const rowsEl = document.getElementById("import-rows");
const selectionSummaryEl = document.getElementById("selection-summary");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const reloadBtn = document.getElementById("reload-bookmarks");
const importBtn = document.getElementById("import-selected");
const progressPanelEl = document.getElementById("progress-panel");
const progressCountEl = document.getElementById("progress-count");
const progressNoteEl = document.getElementById("progress-note");
const progressFillEl = document.getElementById("progress-fill");
const progressTrackEl = document.querySelector(".progress-track");

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (match) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
  }[match] || match));
}

function setStatus(text, kind = "") {
  statusEl.textContent = String(text || "");
  statusEl.className = "status";
  if (kind) {
    statusEl.classList.add(`is-${kind}`);
  }
}

function setBusy(nextBusy) {
  state.busy = !!nextBusy;
  reloadBtn.disabled = state.busy;
  importBtn.disabled = state.busy;
  for (const el of document.querySelectorAll("input, select")) {
    if (el.id !== "reload-bookmarks" && el.id !== "import-selected") {
      el.disabled = state.busy;
    }
  }
}

function resetProgress() {
  progressPanelEl.classList.add("is-hidden");
  progressCountEl.textContent = "0 / 0";
  progressNoteEl.textContent = "Waiting to start.";
  progressFillEl.style.width = "0%";
  progressTrackEl.setAttribute("aria-valuenow", "0");
}

function updateProgress(total, completed, note = "") {
  const safeTotal = Math.max(0, Number(total) || 0);
  const safeCompleted = Math.max(0, Math.min(safeTotal, Number(completed) || 0));
  const percent = safeTotal > 0 ? Math.round((safeCompleted / safeTotal) * 100) : 0;
  progressPanelEl.classList.remove("is-hidden");
  progressCountEl.textContent = `${safeCompleted} / ${safeTotal}`;
  progressNoteEl.textContent = String(note || "");
  progressFillEl.style.width = `${percent}%`;
  progressTrackEl.setAttribute("aria-valuenow", String(percent));
}

function isPdfUrl(url) {
  try {
    const parsed = new URL(String(url || ""));
    return parsed.pathname.toLowerCase().endsWith(".pdf");
  } catch (_err) {
    return false;
  }
}

function isSupportedVideoUrl(url) {
  try {
    const u = new URL(String(url || ""));
    const host = String(u.hostname || "").toLowerCase();
    if (host === "youtu.be" || host.endsWith(".youtu.be")) {
      return Boolean(u.pathname.split("/").filter(Boolean)[0]);
    }
    if (host === "youtube.com" || host.endsWith(".youtube.com")) {
      if (u.searchParams.get("v")) {
        return true;
      }
      const parts = u.pathname.split("/").filter(Boolean);
      return ["embed", "shorts", "live"].includes(parts[0]) && Boolean(parts[1]);
    }
    if (host === "vimeo.com" || host.endsWith(".vimeo.com")) {
      return /(?:\/video\/|\/)(\d{5,})(?:[/?#]|$)/.test(u.pathname);
    }
  } catch (_err) {
    return false;
  }
  return false;
}

function detectKind(url) {
  if (isPdfUrl(url)) {
    return "pdf";
  }
  if (isSupportedVideoUrl(url)) {
    return "video";
  }
  return "webpage";
}

function parseTags(raw) {
  return Array.from(
    new Set(
      String(raw || "")
        .replaceAll(",", " ")
        .split(/\s+/)
        .map((part) => part.trim())
        .filter(Boolean)
    )
  );
}

function collectBookmarkIds(node) {
  if (!node) {
    return [];
  }
  if (node.url) {
    return state.items.has(String(node.id)) ? [String(node.id)] : [];
  }
  const out = [];
  for (const child of node.children || []) {
    out.push(...collectBookmarkIds(child));
  }
  return out;
}

function countSelected(ids) {
  let selected = 0;
  for (const id of ids) {
    if (state.items.get(id)?.selected) {
      selected += 1;
    }
  }
  return selected;
}

function buildPath(segments) {
  return segments.filter(Boolean).join(" / ");
}

function registerBookmark(node, pathParts) {
  const id = String(node.id);
  if (state.items.has(id)) {
    return;
  }
  state.items.set(id, {
    id,
    title: String(node.title || "").trim() || "Untitled bookmark",
    url: String(node.url || "").trim(),
    folderPath: buildPath(pathParts),
    kind: detectKind(node.url || ""),
    tagsText: "",
    selected: false,
    importState: "",
    importError: "",
  });
}

function indexTree(nodes, pathParts = []) {
  for (const node of nodes || []) {
    if (node.url) {
      registerBookmark(node, pathParts);
      continue;
    }
    const nextPath = node.id === "0"
      ? pathParts
      : [...pathParts, String(node.title || "").trim()].filter(Boolean);
    indexTree(node.children || [], nextPath);
  }
}

function renderTreeNodes(nodes) {
  if (!Array.isArray(nodes) || nodes.length === 0) {
    return "";
  }
  const parts = ['<ul class="tree-list">'];
  for (const node of nodes) {
    if (node.url) {
      const item = state.items.get(String(node.id));
      if (!item) {
        continue;
      }
      parts.push(`
        <li class="tree-node">
          <label class="tree-row tree-label">
            <input class="tree-checkbox" type="checkbox" data-bookmark-id="${escapeHtml(item.id)}" ${item.selected ? "checked" : ""}>
            <span class="tree-title">${escapeHtml(item.title)}</span>
            <span class="tree-meta">${escapeHtml(item.folderPath || "Bookmarks")} · ${escapeHtml(item.url)}</span>
          </label>
        </li>
      `);
      continue;
    }

    const bookmarkIds = collectBookmarkIds(node);
    if (bookmarkIds.length === 0) {
      continue;
    }
    const selectedCount = countSelected(bookmarkIds);
    const isChecked = selectedCount > 0 && selectedCount === bookmarkIds.length;
    const isPartial = selectedCount > 0 && selectedCount < bookmarkIds.length;
    parts.push(`
      <li class="tree-node tree-folder">
        <details>
          <summary>
            <div class="tree-folder-summary">
              <span class="tree-toggle" aria-hidden="true">▶</span>
              <input class="tree-checkbox" type="checkbox" data-folder-id="${escapeHtml(String(node.id))}" ${isChecked ? "checked" : ""} ${isPartial ? 'data-indeterminate="true"' : ""}>
              <label class="tree-row tree-label">
              <span class="tree-title">${escapeHtml(String(node.title || "Folder").trim() || "Folder")}</span>
              <span class="tree-meta">${selectedCount}/${bookmarkIds.length} selected</span>
              </label>
            </div>
          </summary>
          <div class="tree-children">${renderTreeNodes(node.children || [])}</div>
        </details>
      </li>
    `);
  }
  parts.push("</ul>");
  return parts.join("");
}

function selectedItems() {
  return Array.from(state.items.values()).filter((item) => item.selected);
}

function renderRows() {
  const items = selectedItems().sort((a, b) => a.title.localeCompare(b.title));
  selectionSummaryEl.textContent = `${items.length} bookmark${items.length === 1 ? "" : "s"} selected`;
  if (items.length === 0) {
    rowsEl.innerHTML = '<div class="empty-state">Select folders or individual bookmarks on the left to build the import list.</div>';
    return;
  }

  rowsEl.innerHTML = items.map((item) => `
    <article class="import-row ${item.importState === "error" ? "is-error" : ""}">
      <div class="row-top">
        <label>
          <input class="row-checkbox" type="checkbox" data-row-id="${escapeHtml(item.id)}" checked>
        </label>
        <div class="field">
          <span class="field-label">Title</span>
          <input type="text" data-title-id="${escapeHtml(item.id)}" value="${escapeHtml(item.title)}" spellcheck="false">
        </div>
        <div class="field">
          <span class="field-label">Type</span>
          <select data-kind-id="${escapeHtml(item.id)}">
            <option value="pdf" ${item.kind === "pdf" ? "selected" : ""}>PDF</option>
            <option value="video" ${item.kind === "video" ? "selected" : ""}>YouTube/Video</option>
            <option value="webpage" ${item.kind === "webpage" ? "selected" : ""}>Webpage</option>
            <option value="writing" ${item.kind === "writing" ? "selected" : ""}>Writing</option>
          </select>
        </div>
        <div class="field">
          <span class="field-label">Tags</span>
          <input type="text" data-tags-id="${escapeHtml(item.id)}" value="${escapeHtml(item.tagsText)}" placeholder="tag1 tag2" spellcheck="false">
        </div>
      </div>
      <div class="row-meta">
        <div class="row-url">${escapeHtml(item.url)}</div>
        <div class="row-url">${escapeHtml(item.folderPath || "Bookmarks")}</div>
        ${item.importState === "error" && item.importError
          ? `<div class="row-error">${escapeHtml(item.importError)}</div>`
          : ""}
      </div>
    </article>
  `).join("");
}

function renderTree() {
  treeEl.innerHTML = renderTreeNodes(state.tree);
  for (const checkbox of treeEl.querySelectorAll('[data-indeterminate="true"]')) {
    checkbox.indeterminate = true;
  }
}

function renderResults(results) {
  if (!Array.isArray(results) || results.length === 0) {
    resultsEl.innerHTML = "";
    return;
  }
  resultsEl.innerHTML = results.map((result) => {
    const ok = Boolean(result?.ok);
    const title = escapeHtml(result?.title || "Untitled");
    const kind = escapeHtml(result?.kind || "");
    const detail = ok
      ? `Created ${kind} card${result?.cardId ? ` #${escapeHtml(String(result.cardId))}` : ""}`
      : escapeHtml(result?.error || "Import failed.");
    return `
      <div class="result-card ${ok ? "is-success" : "is-error"}">
        <strong>${title}</strong>
        <div class="result-line">${detail}</div>
      </div>
    `;
  }).join("");
}

function setSelected(ids, nextSelected) {
  for (const id of ids) {
    const item = state.items.get(String(id));
    if (item) {
      item.selected = !!nextSelected;
    }
  }
  renderTree();
  renderRows();
}

function findNodeById(nodes, targetId) {
  for (const node of nodes || []) {
    if (String(node.id) === String(targetId)) {
      return node;
    }
    const childMatch = findNodeById(node.children || [], targetId);
    if (childMatch) {
      return childMatch;
    }
  }
  return null;
}

async function loadBookmarks() {
  setBusy(true);
  setStatus("Loading bookmarks...");
  resetProgress();
  renderResults([]);
  try {
    const tree = await chrome.bookmarks.getTree();
    state.tree = Array.isArray(tree) ? tree : [];
    state.items = new Map();
    indexTree(state.tree);
    renderTree();
    renderRows();
    setStatus("Bookmarks loaded.");
  } catch (err) {
    treeEl.innerHTML = '<div class="empty-state">Failed to load bookmarks.</div>';
    rowsEl.innerHTML = "";
    setStatus(err?.message || "Failed to load bookmarks.", "error");
  } finally {
    setBusy(false);
  }
}

async function importSelected() {
  const items = selectedItems().map((item) => ({
    id: item.id,
    kind: item.kind,
    url: item.url,
    title: item.title,
    tags: parseTags(item.tagsText),
  }));
  if (items.length === 0) {
    setStatus("Select at least one bookmark before importing.", "error");
    return;
  }

  setBusy(true);
  setStatus(`Importing ${items.length} bookmark${items.length === 1 ? "" : "s"}...`);
  updateProgress(items.length, 0, "Preparing import...");
  renderResults([]);

  for (const item of state.items.values()) {
    item.importState = "";
    item.importError = "";
  }
  renderRows();

  const results = [];
  let okCount = 0;
  let failCount = 0;

  try {
    for (let i = 0; i < items.length; i += 1) {
      const item = items[i];
      const rowItem = state.items.get(item.id);
      updateProgress(items.length, i, `Importing ${i + 1} of ${items.length}: ${item.title}`);

      let result = null;
      try {
        const payload = {
          kind: item.kind,
          url: item.url,
          title: item.title,
          tags: item.tags,
        };
        if (
          item.kind === "pdf"
          && typeof fetchPdfPayloadForImport === "function"
          && pdfUrlLooksLikePdf(item.url)
        ) {
          try {
            const pdfPayload = await fetchPdfPayloadForImport(item.url);
            payload.pdfBase64 = pdfPayload.pdfBase64;
            payload.pdfFilename = pdfPayload.pdfFilename;
          } catch (_err) {
            // Fall back to addon-side retrieval if browser-side fetch fails.
          }
        }

        const response = await fetch(BRIDGE_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data?.ok) {
          throw new Error(String(data?.error || `Request failed (${response.status})`));
        }
        result = data;
        okCount += 1;
        if (rowItem) {
          rowItem.importState = "success";
          rowItem.importError = "";
        }
      } catch (err) {
        const message = err instanceof TypeError
          ? "Failed to reach Incremento in Anki. Keep Anki open and reload the addon."
          : (err?.message || "Failed to import bookmark.");
        result = {
          ok: false,
          kind: item.kind,
          title: item.title,
          error: message,
        };
        failCount += 1;
        if (rowItem) {
          rowItem.importState = "error";
          rowItem.importError = message;
        }
      }

      results.push(result);
      renderResults(results);
      renderRows();
      updateProgress(
        items.length,
        i + 1,
        result?.ok
          ? `Imported ${i + 1} of ${items.length}: ${item.title}`
          : `Failed ${i + 1} of ${items.length}: ${item.title}`
      );
    }

    if (failCount > 0) {
      setStatus(`Imported ${okCount} bookmark${okCount === 1 ? "" : "s"}; ${failCount} failed.`, "error");
      progressNoteEl.textContent = `Finished with ${okCount} imported and ${failCount} failed.`;
    } else {
      setStatus(`Imported ${okCount} bookmark${okCount === 1 ? "" : "s"}.`, "success");
      progressNoteEl.textContent = `Finished importing ${okCount} bookmark${okCount === 1 ? "" : "s"}.`;
    }
  } finally {
    setBusy(false);
  }
}

treeEl.addEventListener("change", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) {
    return;
  }

  if (target.dataset.folderId) {
    const node = findNodeById(state.tree, target.dataset.folderId);
    if (!node) {
      return;
    }
    setSelected(collectBookmarkIds(node), target.checked);
    return;
  }

  if (target.dataset.bookmarkId) {
    setSelected([target.dataset.bookmarkId], target.checked);
  }
});

treeEl.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) {
    return;
  }
  if (target.dataset.folderId || target.dataset.bookmarkId) {
    event.stopPropagation();
  }
});

rowsEl.addEventListener("change", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }

  if (target instanceof HTMLInputElement && target.dataset.rowId) {
    setSelected([target.dataset.rowId], target.checked);
    return;
  }

  if (target instanceof HTMLSelectElement && target.dataset.kindId) {
    const item = state.items.get(target.dataset.kindId);
    if (item) {
      item.kind = target.value;
    }
  }
});

rowsEl.addEventListener("input", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) {
    return;
  }
  if (target.dataset.titleId) {
    const item = state.items.get(target.dataset.titleId);
    if (item) {
      item.title = target.value.trim() || "Untitled bookmark";
      renderTree();
    }
    return;
  }
  if (target.dataset.tagsId) {
    const item = state.items.get(target.dataset.tagsId);
    if (item) {
      item.tagsText = target.value;
    }
  }
});

reloadBtn.addEventListener("click", () => {
  void loadBookmarks();
});

importBtn.addEventListener("click", () => {
  void importSelected();
});

resetProgress();
void loadBookmarks();
