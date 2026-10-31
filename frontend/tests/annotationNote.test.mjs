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

const imageSource = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAIAAAB7QOjdAAAAD0lEQVR4nGP4z8DA8J8BAAf/Af8Bf4mnAAAAAElFTkSuQmCC';
const image = `<img src="${imageSource}" width="2" height="1" alt="">`;
test('embedded raster images render with bounded dimensions alongside searchable captions or alone', () => {
  const tree = annotationNoteTree('A landmark', `<p>${image}</p><p>A landmark</p>`);
  assert.equal(tree[0].children[0].tag, 'img');
  assert.equal(tree[0].children[0].src, imageSource);
  assert.equal(tree[0].children[0].width, 2);
  assert.equal(tree[0].children[0].height, 1);
  assert.equal(annotationNoteTree('', image)[0].tag, 'img');
});

test('image grammar rejects remote URLs, active formats, extra attributes and excessive dimensions', () => {
  for (const invalid of [image.replace(imageSource, 'https://example.com/tracker'),
    image.replace(imageSource, 'data:image/svg+xml;base64,PHN2Zz4='),
    image.replace(imageSource, 'data:image/png;base64,YmFk'),
    image.replace('width="2"', 'width="99999"'), image.replace('alt=""', 'onerror="bad()"'),
    image.repeat(5)]) {
    assert.equal(annotationNoteTree('', invalid), null);
  }
});

test('intentionally stretched image dimensions are retained', () => {
  const markup = image.replace('width="2" height="1"', 'width="120" height="80"');
  const node = annotationNoteTree('', markup)[0];
  assert.equal(node.width, 120);
  assert.equal(node.height, 80);
});

test('canonical image wrapping and centered paragraphs are inert layout choices', () => {
  for (const side of ['left', 'right']) {
    const wrapped = image.replace('alt=""', `alt="" style="float:${side}"`);
    const tree = annotationNoteTree('Caption', `<p>${wrapped}Caption</p>`);
    assert.equal(tree[0].children[0].float, side);
  }
  assert.equal(annotationNoteTree('Caption', `<p align="center">${image}</p><p>Caption</p>`)[0].align, 'center');
  assert.equal(annotationNoteTree('', image.replace('alt=""', 'alt="" style="position:fixed"')), null);
});

test('own-line images keep left, center, or right alignment as safe paragraph metadata', () => {
  for (const alignment of ['left', 'center', 'right']) {
    const tree = annotationNoteTree('Caption', `<p align="${alignment}">${image}</p><p>Caption</p>`);
    assert.equal(tree[0].align, alignment);
  }
  assert.equal(annotationNoteTree('', `<p align="left;position:fixed">${image}</p>`), null);
});
