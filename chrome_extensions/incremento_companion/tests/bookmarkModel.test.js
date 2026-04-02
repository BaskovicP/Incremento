import test from "node:test";
import assert from "node:assert/strict";

import {
  buildBookmarkItems,
  collectBookmarkIds,
  countSelected,
  findNodeById,
  getSelectedItems,
  parseTags,
  setSelectedForIds,
  updateBookmarkItem,
} from "../src/bookmarks/bookmarkModel.js";

function makeTree() {
  return [
    {
      id: "0",
      title: "",
      children: [
        {
          id: "10",
          title: "Programming",
          children: [
            {
              id: "11",
              title: "JS Video",
              url: "https://www.youtube.com/watch?v=abc123",
            },
            {
              id: "12",
              title: "Spec PDF",
              url: "https://example.com/spec.pdf",
            },
          ],
        },
        {
          id: "20",
          title: "Reference",
          children: [
            {
              id: "21",
              title: "Article",
              url: "https://example.com/article",
            },
          ],
        },
      ],
    },
  ];
}

test("buildBookmarkItems indexes bookmarks with folder path and detected kind", () => {
  const items = buildBookmarkItems(makeTree());

  assert.equal(Object.keys(items).length, 3);
  assert.deepEqual(items["11"], {
    id: "11",
    title: "JS Video",
    url: "https://www.youtube.com/watch?v=abc123",
    folderPath: "Programming",
    kind: "video",
    tagsText: "",
    selected: false,
    importState: "",
    importError: "",
  });
  assert.equal(items["12"].kind, "pdf");
  assert.equal(items["21"].kind, "webpage");
  assert.equal(items["21"].folderPath, "Reference");
});

test("collectBookmarkIds returns nested bookmark ids that exist in the index", () => {
  const tree = makeTree();
  const items = buildBookmarkItems(tree);

  assert.deepEqual(collectBookmarkIds(tree[0].children[0], items), ["11", "12"]);
  assert.deepEqual(collectBookmarkIds(tree[0].children[1], items), ["21"]);
});

test("findNodeById finds nested folders and bookmarks", () => {
  const tree = makeTree();

  assert.equal(findNodeById(tree, "10")?.title, "Programming");
  assert.equal(findNodeById(tree, "12")?.title, "Spec PDF");
  assert.equal(findNodeById(tree, "999"), null);
});

test("setSelectedForIds updates only the requested bookmark ids", () => {
  const initial = buildBookmarkItems(makeTree());
  const updated = setSelectedForIds(initial, ["11", "21"], true);

  assert.equal(updated["11"].selected, true);
  assert.equal(updated["21"].selected, true);
  assert.equal(updated["12"].selected, false);
  assert.equal(initial["11"].selected, false);
});

test("countSelected and getSelectedItems reflect selected bookmarks", () => {
  const items = setSelectedForIds(buildBookmarkItems(makeTree()), ["11", "12"], true);

  assert.equal(countSelected(["11", "12", "21"], items), 2);
  assert.deepEqual(
    getSelectedItems(items).map((item) => item.id).sort(),
    ["11", "12"]
  );
});

test("updateBookmarkItem applies targeted updates", () => {
  const items = buildBookmarkItems(makeTree());
  const updated = updateBookmarkItem(items, "12", {
    title: "Updated PDF",
    tagsText: "anki pdf",
  });

  assert.equal(updated["12"].title, "Updated PDF");
  assert.equal(updated["12"].tagsText, "anki pdf");
  assert.equal(items["12"].title, "Spec PDF");
});

test("parseTags normalizes whitespace, commas, and duplicates", () => {
  assert.deepEqual(parseTags("anki, pdf  browser   anki"), ["anki", "pdf", "browser"]);
  assert.deepEqual(parseTags(""), []);
});
