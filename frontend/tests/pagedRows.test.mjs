import test from 'node:test';
import assert from 'node:assert/strict';
import {pageWindow} from '../src/pagedRows.mjs';

test('bounded pages preserve every row and clamp after filtering/deletion', () => {
  const seen = [];
  for (let offset = 0; offset < 10003; offset += 50) {
    const page = pageWindow(10003, offset);
    assert.ok(page.end - page.start <= 50);
    for (let row = page.start; row < page.end; row++) seen.push(row);
  }
  assert.deepEqual(seen, Array.from({length: 10003}, (_, i) => i));
  assert.equal(pageWindow(3, 10000).start, 0);
  assert.deepEqual(pageWindow(0), {start: 0, end: 0, previous: 0, next: 0, count: 0});
});
