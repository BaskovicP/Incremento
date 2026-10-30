import test from 'node:test';
import assert from 'node:assert/strict';
import {ANNOTATION_STYLES, annotationStyle, withAnnotationStyle, annotationLine} from '../src/annotationStyles.mjs';

test('style choices are stable and infer imported PDF markup without changing shapes', () => {
  assert.deepEqual(ANNOTATION_STYLES, ['highlight', 'underline', 'squiggly', 'dashed', 'dotted', 'strikeout']);
  assert.equal(annotationStyle({}), 'highlight');
  assert.equal(annotationStyle({pdf_annotation: {kind: 'Squiggly'}}), 'squiggly');
  assert.equal(annotationStyle({pdf_annotation: {kind: 'Square'}}), null);
  assert.equal(annotationStyle({color: 'snapshot'}), null);
});

test('restyling preserves identity, notes, color and range but invalidates native geometry', () => {
  const mark = {id: 'mark', color: '#123456', rects: [{x: 10, y: 20, w: 80, h: 15}],
    note: 'My note', linked_note_id: 123, pdf_annotation: {name: 'Stable', kind: 'Highlight',
      opacity: .42, quads: [], xref: 12}};
  const next = withAnnotationStyle(mark, 'dashed');
  assert.deepEqual(next, {...mark, pdf_annotation: {name: 'Stable', kind: 'Underline',
    opacity: 1, incremento_style: 'dashed'}});
  assert.equal(mark.pdf_annotation.kind, 'Highlight');
  assert.equal(withAnnotationStyle(mark, 'url(evil)'), null);
});

test('line paths distinguish squiggles, dashes, dots and strikethrough at PDF coordinates', () => {
  assert.equal(annotationLine('highlight', 100, 16), null);
  assert.deepEqual(annotationLine('dashed', 100, 16), {path: 'M0 14 L100 14', dash: '4 3', cap: 'butt'});
  assert.deepEqual(annotationLine('dotted', 100, 16), {path: 'M0 14 L100 14', dash: '0 3', cap: 'round'});
  assert.equal(annotationLine('strikeout', 100, 16).path, 'M0 8 L100 8');
  assert.match(annotationLine('squiggly', 100, 16).path, /Q/);
  assert.equal(annotationLine('squiggly', Infinity, 16), null);
});
