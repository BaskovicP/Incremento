import assert from 'node:assert/strict';
import test from 'node:test';
import {capturePdfDestination, pdfDestinationScrollRatio} from '../src/pdfDestination.mjs';

function pageFixture() {
  const text = {};
  return {text, page: {contains: node => node === text, getBoundingClientRect: () => ({top: -100, height: 1000})},
    scroll: {scrollTop: 120, scrollHeight: 1024, clientHeight: 500, getBoundingClientRect: () => ({top: 20})}};
}

test('a clicked or selected passage records a position on the PDF page, independently of its scroll range', () => {
  const {page, scroll, text} = pageFixture();
  const clicked = capturePdfDestination(scroll, page, null, 650);
  assert.equal(clicked.page_y, .75);
  assert.equal(clicked.scroll_ratio, 120 / 524);
  const selected = {isCollapsed: false, rangeCount: 1, getRangeAt: () => ({
    commonAncestorContainer: text, getClientRects: () => [{top: 400, height: 20, width: 100}],
  })};
  assert.equal(capturePdfDestination(scroll, page, selected, 650).page_y, .5);
  scroll.clientHeight = scroll.scrollHeight;
  assert.equal(capturePdfDestination(scroll, page, selected).page_y, .5);
});

test('browsing without selecting a passage links to the top of the current view', () => {
  const {page, scroll} = pageFixture();
  assert.equal(capturePdfDestination(scroll, page).page_y, .12);
  assert.equal(capturePdfDestination(scroll, page, {isCollapsed: true}, -1000).page_y, 0);
  assert.equal(capturePdfDestination(scroll, page, null, 5000).page_y, 1);
  assert.equal(capturePdfDestination(scroll, {getBoundingClientRect: () => ({top: 0, height: 0})}), null);
});

test('reopening a chosen passage puts it inside the reading area at any page size', () => {
  for (const [pageHeight, visibleHeight] of [[1000, 400], [2000, 500]]) {
    const ratio = pdfDestinationScrollRatio(.6, pageHeight, visibleHeight);
    assert.equal(.6 * pageHeight - ratio * (pageHeight - visibleHeight), .25 * visibleHeight);
  }
  assert.equal(pdfDestinationScrollRatio(.6, 500, 800), 0);
  assert.equal(pdfDestinationScrollRatio(0, 1000, 400), 0);
  assert.equal(pdfDestinationScrollRatio(1, 1000, 400), 1);
});
