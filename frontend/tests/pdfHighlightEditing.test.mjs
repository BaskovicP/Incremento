import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import { normalizeHighlightColor, highlightSolidColor } from '../src/highlightColors.mjs';
const source = readFileSync(new URL('../src/PdfViewer.jsx', import.meta.url), 'utf8');

test('Ctrl and Cmd H highlight the PDF selection and stop the native shortcut', () => {
  for (const modifier of ['ctrlKey', 'metaKey', 'altKey']) {
    let handler;
    let made = 0;
    let prevented = 0;
    let stopped = 0;
    const selection = { isCollapsed: false, rangeCount: 1, getRangeAt: () => ({ commonAncestorContainer: {} }), removeAllRanges() {} };
    const block = source.slice(source.indexOf('    const idxFromShortcut'), source.indexOf('  // ── Copy cleaned selection'));
    vm.runInNewContext('(function(){' + block.slice(0, block.lastIndexOf('  }, [textLayerRef')) + '})()', {
      window: { getSelection: () => selection, addEventListener: (_name, fn) => { handler = fn; } },
      textLayerRef: { current: { contains: () => true } }, makeHighlight: () => { made++; },
    });
    handler({ code: 'KeyH', key: 'h', [modifier]: true, preventDefault: () => { prevented++; }, stopPropagation: () => { stopped++; } });
    assert.equal(made, 1);
    assert.equal(prevented, 1);
    assert.equal(stopped, 1);
  }
});

test('recoloring preserves highlight identity, range, notes and linkage and emits an update', () => {
  const original = { id: 'saved', page: 2, color: 'yellow', text: 'text', note: 'note', linked_note_id: 8, rects: [{ x: 1, y: 2, w: 30, h: 10 }] };
  let highlights = [original];
  const commands = [];
  const scope = { highlights, normalizeHighlightColor, highlightSolidColor, useCallback: fn => fn,
    cardIdRef: { current: 42 }, setHighlights: fn => { highlights = fn(highlights); },
    window: { pycmd: command => commands.push(command) } };
  const start = source.indexOf('  const recolorHighlight =');
  assert.ok(start >= 0, 'reader needs a saved-highlight recolor action');
  vm.runInNewContext(source.slice(start, source.indexOf('  const makeHighlight', start)) + '\nrecolorHighlight("saved", "blue");', scope);
  assert.deepEqual(JSON.parse(JSON.stringify(highlights[0])), { ...original, color: 'blue' });
  assert.deepEqual(JSON.parse(commands[0].split(':').slice(1).join(':')), { cardId: 42, highlight: { ...original, color: 'blue' } });
  assert.equal(original.color, 'yellow');
});
