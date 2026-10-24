import test from 'node:test';
import assert from 'node:assert/strict';
import {sharedPdfReaderStartup, pdfReaderGroups} from '../src/sharedPdfReader.mjs';

test('side reading uses the main reader controls without review or card management', () => {
  assert.deepEqual(pdfReaderGroups(true), ['navigation', 'reading', 'annotation']);
  assert.deepEqual(pdfReaderGroups(false), ['navigation', 'reading', 'annotation', 'review']);
});

test('reference startup preserves its own position and loads shared annotations and preferences', () => {
  const data = sharedPdfReaderStartup({card_id: 7, filename: 'book.pdf', page: 8,
    scroll_ratio: .6, max_page: 12, highlights: [{id: 'shared'}], bookmarks: [{id: 'saved'}],
    read_page: 3, appearance: 'night', locale: 'en', page_y: .4, controls_collapsed: false});
  assert.equal(data.pending.page, 8);
  assert.equal(data.pending.scrollRatio, .6);
  assert.equal(data.pending.readPage, 3);
  assert.equal(data.pending.pageY, .4);
  assert.equal(data.pending.appearanceMode, 'night');
  assert.equal(data.pending.controlsCollapsed, false);
  assert.deepEqual(data.highlights, [{id: 'shared'}]);
  assert.deepEqual(data.pending.bookmarks, [{id: 'saved'}]);
  assert.equal(data.pending.limitStatus.allowed_max_page, 12);
});
