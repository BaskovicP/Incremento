import test from 'node:test';
import assert from 'node:assert/strict';
import {annotationNoteTree} from '../src/annotationNote.mjs';

test('annotation formatting renders as inert nodes with validated links', () => {
  const tree = annotationNoteTree('Rice & theorem\nRead more', '<p><b>Rice</b> &amp; <i>theorem</i></p><ul><li><a href="https://example.com/?a=1&amp;b=2">Read more</a></li></ul>');
  assert.equal(tree[0].tag, 'p');
  assert.deepEqual(tree[0].children[0], {tag: 'b', children: ['Rice']});
  assert.equal(tree[1].children[0].children[0].href, 'https://example.com/?a=1&b=2');
});

test('corrupt, active, stale and oversized markup falls back to literal plain text', () => {
  for (const markup of ['<img src=x onerror=bad()>', '<p onclick="bad()">note</p>',
    '<a href="javascript:bad()">note</a>', '<a href="file:///tmp/private">note</a>',
    '<a href="https://user:pass@example.com">note</a>', '<b>other</b>', '<b>note</i>',
    '<p>' + 'x'.repeat(262145) + '</p>']) {
    assert.equal(annotationNoteTree('note', markup), null, markup.slice(0, 80));
  }
  assert.equal(annotationNoteTree('<b>literal</b>', ''), null);
});
