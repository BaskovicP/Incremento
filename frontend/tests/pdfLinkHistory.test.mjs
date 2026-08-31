import test from 'node:test';
import assert from 'node:assert/strict';

import {
  pushPdfLinkHistory,
  takePdfLinkHistory,
} from '../src/pdfLinkHistory.mjs';


test('PDF link history stores normalized locations without mutating the caller', () => {
  const original = [{ page: 2, scrollRatio: 0.25 }];
  const updated = pushPdfLinkHistory(original, { page: '7', scrollRatio: 1.8 });

  assert.deepEqual(original, [{ page: 2, scrollRatio: 0.25 }]);
  assert.deepEqual(updated, [
    { page: 2, scrollRatio: 0.25 },
    { page: 7, scrollRatio: 1 },
  ]);
});


test('PDF link history is bounded and ignores invalid locations', () => {
  let history = [];
  for (let page = 1; page <= 55; page += 1) {
    history = pushPdfLinkHistory(history, { page, scrollRatio: page / 100 }, 50);
  }

  assert.equal(history.length, 50);
  assert.equal(history[0].page, 6);
  assert.equal(history.at(-1).page, 55);
  assert.strictEqual(
    pushPdfLinkHistory(history, { page: 0, scrollRatio: 0.5 }),
    history,
  );
});


test('taking PDF link history returns the newest location and remaining stack', () => {
  const history = [
    { page: 3, scrollRatio: 0.1 },
    { page: 9, scrollRatio: 0.8 },
  ];

  assert.deepEqual(takePdfLinkHistory(history), {
    location: { page: 9, scrollRatio: 0.8 },
    history: [{ page: 3, scrollRatio: 0.1 }],
  });
  assert.deepEqual(takePdfLinkHistory([]), { location: null, history: [] });
});
