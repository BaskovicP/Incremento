import test from 'node:test';
import assert from 'node:assert/strict';
import {React, renderToString, loadJsx} from './reactHarness.js';
import {buildBookmarkItems, buildBookmarkTreeIndex, bookmarkSelectionPrefix} from '../src/bookmarks/bookmarkModel.js';

test('closed bookmark folders mount no descendants and keep the complete selected total', async () => {
  const leaves = Array.from({length: 10000}, (_, i) => ({id: `leaf-${i}`, title: `Bookmark ${i}`, url: 'https://example.test'}));
  const tree = [{id: 'root', title: 'Folder', children: leaves}];
  const items = buildBookmarkItems(tree);
  items['leaf-9999'].selected = true;
  const index = buildBookmarkTreeIndex(tree);
  const {BookmarkTree} = await loadJsx(new URL('../src/bookmarks/components/BookmarkTree.jsx', import.meta.url));
  const html = renderToString(React.createElement(BookmarkTree, {nodes: tree, itemsById: items,
    treeIndex: index, selectionPrefix: bookmarkSelectionPrefix(index, items)}));
  assert.equal((html.match(/type="checkbox"/g) || []).length, 1);
  assert.match(html, /1/);
  assert.doesNotMatch(html, /Bookmark 9999/);
});

test('the selected import list mounts at most 100 editable rows and keeps page navigation', async () => {
  const nodes = Array.from({length: 10000}, (_, i) => ({id: `leaf-${i}`, title: `Bookmark ${i}`, url: 'https://example.test'}));
  const items = Object.values(buildBookmarkItems(nodes));
  const {ImportRows} = await loadJsx(new URL('../src/bookmarks/components/ImportRows.jsx', import.meta.url));
  const html = renderToString(React.createElement(ImportRows, {items}));
  assert.equal((html.match(/<article /g) || []).length, 100);
  assert.match(html, /Next page/);
  assert.equal(items.length, 10000);
});
