import { isPdfUrl, isSupportedVideoUrl } from "../shared/url.js";

function buildPath(segments) {
  return segments.filter(Boolean).join(" / ");
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

function registerBookmark(itemsById, node, pathParts) {
  const id = String(node.id);
  if (itemsById[id]) {
    return itemsById;
  }
  return {
    ...itemsById,
    [id]: {
      id,
      title: String(node.title || "").trim() || "Untitled bookmark",
      url: String(node.url || "").trim(),
      folderPath: buildPath(pathParts),
      kind: detectKind(node.url || ""),
      tagsText: "",
      selected: false,
      importState: "",
      importError: "",
    },
  };
}

export function buildBookmarkItems(nodes, pathParts = [], itemsById = {}) {
  let nextItems = itemsById;
  for (const node of nodes || []) {
    if (node.url) {
      nextItems = registerBookmark(nextItems, node, pathParts);
      continue;
    }
    const nextPath = node.id === "0"
      ? pathParts
      : [...pathParts, String(node.title || "").trim()].filter(Boolean);
    nextItems = buildBookmarkItems(node.children || [], nextPath, nextItems);
  }
  return nextItems;
}

export function collectBookmarkIds(node, itemsById) {
  if (!node) {
    return [];
  }
  if (node.url) {
    return itemsById[String(node.id)] ? [String(node.id)] : [];
  }
  const out = [];
  for (const child of node.children || []) {
    out.push(...collectBookmarkIds(child, itemsById));
  }
  return out;
}

export function countSelected(ids, itemsById) {
  return ids.reduce((count, id) => count + (itemsById[id]?.selected ? 1 : 0), 0);
}

export function findNodeById(nodes, targetId) {
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

export function setSelectedForIds(itemsById, ids, selected) {
  const nextItems = { ...itemsById };
  for (const id of ids) {
    if (nextItems[id]) {
      nextItems[id] = {
        ...nextItems[id],
        selected: Boolean(selected),
      };
    }
  }
  return nextItems;
}

export function updateBookmarkItem(itemsById, id, updates) {
  if (!itemsById[id]) {
    return itemsById;
  }
  return {
    ...itemsById,
    [id]: {
      ...itemsById[id],
      ...updates,
    },
  };
}

export function parseTags(raw) {
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

export function getSelectedItems(itemsById) {
  return Object.values(itemsById).filter((item) => item.selected);
}
