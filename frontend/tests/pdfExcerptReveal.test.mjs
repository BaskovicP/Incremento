import test from 'node:test';
import assert from 'node:assert/strict';
import {matchExcerpt} from '../src/pdfExcerptReveal.mjs';

test('repeated phrases use saved surrounding text rather than the first occurrence', () => {
  assert.deepEqual(matchExcerpt(['First example. Same phrase. Second example. Same phrase. End.'],
    {quote: 'Same phrase.', prefix: 'Second example. ', suffix: ' End.'}),
    {start: {part: 0, offset: 44}, end: {part: 0, offset: 56}});
});

test('locates only the exact excerpt across PDF text spans and whitespace', () => {
  assert.deepEqual(matchExcerpt(['Unrelated context. ', 'The selected', ' passage. More context.'], 'selected passage.'),
    {start: {part: 1, offset: 4}, end: {part: 2, offset: 9}});
  assert.equal(matchExcerpt(['Similar words elsewhere'], 'words that were selected'), null);
  assert.equal(matchExcerpt(['Anything'], ''), null);
  assert.deepEqual(matchExcerpt(['中文', '摘录'], '中文摘录'),
    {start: {part: 0, offset: 0}, end: {part: 1, offset: 2}});
});
