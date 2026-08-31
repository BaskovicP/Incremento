import test from 'node:test';
import assert from 'node:assert/strict';

import {
  normalizeExternalHttpUrl,
  resolvePdfAnnotationLink,
} from '../src/pdfLinks.mjs';


test('external PDF links accept only uncredentialed HTTP(S) URLs', () => {
  assert.equal(
    normalizeExternalHttpUrl('https://docs.example.test/guide?q=1#part'),
    'https://docs.example.test/guide?q=1#part',
  );
  assert.equal(normalizeExternalHttpUrl('http://example.test'), 'http://example.test');

  for (const unsafe of [
    'javascript:alert(1)',
    'file:///etc/passwd',
    'data:text/html,owned',
    'mailto:user@example.test',
    'https://user:secret@example.test/',
    'https://example.test/line\nbreak',
    'https:\\example.test\\spoofed',
  ]) {
    assert.equal(normalizeExternalHttpUrl(unsafe), null, unsafe);
  }
});


test('external PDF annotations become normalized viewport hit targets', async () => {
  const viewport = {
    convertToViewportRectangle: (rect) => [120, 80, 40, 20],
  };

  const link = await resolvePdfAnnotationLink(
    {
      annotationType: 2,
      rect: [1, 2, 3, 4],
      url: 'https://example.test/reference',
      title: 'Reference',
    },
    {},
    viewport,
  );

  assert.deepEqual(link, {
    kind: 'external',
    url: 'https://example.test/reference',
    label: 'Reference',
    left: 40,
    top: 20,
    width: 80,
    height: 60,
  });
});


test('named and direct PDF destinations resolve to one-based pages', async () => {
  const viewport = {
    convertToViewportRectangle: () => [10, 10, 30, 30],
  };
  const pdfDocument = {
    numPages: 8,
    getDestination: async (name) => {
      assert.equal(name, 'chapter-two');
      return [{ num: 9, gen: 0 }, { name: 'XYZ' }];
    },
    getPageIndex: async (ref) => {
      assert.deepEqual(ref, { num: 9, gen: 0 });
      return 4;
    },
  };

  const named = await resolvePdfAnnotationLink(
    { annotationType: 2, rect: [0, 0, 1, 1], dest: 'chapter-two' },
    pdfDocument,
    viewport,
  );
  const direct = await resolvePdfAnnotationLink(
    { annotationType: 2, rect: [0, 0, 1, 1], dest: [2, { name: 'Fit' }] },
    pdfDocument,
    viewport,
  );

  assert.equal(named.kind, 'internal');
  assert.equal(named.targetPage, 5);
  assert.equal(direct.targetPage, 3);
});


test('malformed, non-link, and zero-area PDF annotations fail closed', async () => {
  const viewport = {
    convertToViewportRectangle: (rect) => rect,
  };

  assert.equal(
    await resolvePdfAnnotationLink(
      { annotationType: 1, rect: [0, 0, 10, 10], url: 'https://example.test' },
      {},
      viewport,
    ),
    null,
  );
  assert.equal(
    await resolvePdfAnnotationLink(
      { subtype: 'Link', rect: [0, 0, 0, 10], url: 'https://example.test' },
      {},
      viewport,
    ),
    null,
  );
  assert.equal(
    await resolvePdfAnnotationLink(
      { subtype: 'Link', rect: [0, 0, 10, 10], url: 'javascript:alert(1)' },
      {},
      viewport,
    ),
    null,
  );
});
