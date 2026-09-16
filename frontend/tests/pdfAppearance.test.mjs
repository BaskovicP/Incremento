import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  PDF_APPEARANCE_MODES,
  normalizePdfAppearanceMode,
  pdfPageAppearance,
} from '../src/pdfAppearance.mjs';

test('PDF appearance exposes original, dark, and warm night page modes', () => {
  assert.deepEqual(PDF_APPEARANCE_MODES, ['original', 'dark', 'night']);

  assert.deepEqual(pdfPageAppearance('original'), {
    background: '#1e1e1e',
    filter: 'none',
  });
  assert.deepEqual(pdfPageAppearance('dark'), {
    background: '#09090b',
    filter: 'invert(0.9) hue-rotate(180deg) brightness(0.92) contrast(0.92)',
  });
  assert.deepEqual(pdfPageAppearance('night'), {
    background: '#17130d',
    filter: 'invert(0.88) hue-rotate(180deg) sepia(0.24) saturate(0.78) brightness(0.82) contrast(0.9)',
  });
});

test('unsupported PDF appearance values fail closed to the original page', () => {
  for (const value of [null, undefined, '', 'sepia', 'DARK', 3, {}]) {
    assert.equal(normalizePdfAppearanceMode(value), 'original');
    assert.deepEqual(pdfPageAppearance(value), pdfPageAppearance('original'));
  }
});

test('the PDF reader applies the selected page appearance and exposes it in both toolbar layouts', () => {
  const source = readFileSync(new URL('../src/PdfViewer.jsx', import.meta.url), 'utf8');

  assert.match(source, /const \[appearanceMode, setAppearanceMode\] = useState\('original'\)/);
  assert.match(source, /const pageAppearance = pdfPageAppearance\(appearanceMode\)/);
  assert.ok(source.includes("filter: pageAppearance.filter"));
  assert.ok(source.includes("background: pageAppearance.background"));
  assert.equal(source.match(/aria-label=\{tr\("reader_pdf_appearance"\)\}/g)?.length, 2);
  assert.ok(source.includes("PDF_APPEARANCE_MODES.map"));
});

test('the PDF appearance menus keep readable native colors in every Anki theme', () => {
  const source = readFileSync(new URL('../src/PdfViewer.jsx', import.meta.url), 'utf8');

  assert.match(source, /const PDF_APPEARANCE_SELECT_STYLE = \{/);
  assert.match(source, /colorScheme: 'dark'/);
  assert.match(source, /const PDF_APPEARANCE_OPTION_STYLE = \{/);
  assert.match(source, /backgroundColor: '#27272a'/);
  assert.equal(source.match(/style=\{PDF_APPEARANCE_OPTION_STYLE\}/g)?.length, 2);
});

test('the PDF reader restores startup appearance and persists explicit changes', () => {
  const source = readFileSync(new URL('../src/PdfViewer.jsx', import.meta.url), 'utf8');

  assert.match(source, /startAppearanceMode = 'original'/);
  assert.match(source, /setAppearanceMode\(normalizePdfAppearanceMode\(startAppearanceMode\)\)/);
  assert.match(source, /incremento_pdf_appearance:/);
  assert.match(source, /window\.incrementoSetPdfAppearanceMode = \(mode\) =>/);
  assert.equal(source.match(/onChange=\{\(event\) => applyAppearanceMode\(event\.target\.value\)\}/g)?.length, 2);
  assert.ok(source.includes("pending.appearanceMode || 'original'"));
});
