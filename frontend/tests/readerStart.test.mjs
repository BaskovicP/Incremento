import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import { createReaderLanguage, normalizeReaderLocale } from '../src/i18n.mjs';
import { normalizePdfAppearanceMode } from '../src/pdfAppearance.mjs';
import {DEFAULT_PDF_LINK_PREVIEW_ZOOM, normalizePdfLinkPreviewZoom} from '../src/pdfLinkPreview.mjs';
import {pdfFocusState} from '../src/pdfFocus.mjs';

// Exercise the actual global bridge registration without mounting the canvas or
// PDF.js. React state setters and the render pipeline are the boundary fakes.
function registerBridge(pending = null, focus = null) {
  const source = readFileSync(new URL('../src/PdfViewer.jsx', import.meta.url), 'utf8');
  const start = source.indexOf('    const startWithHighlights = (');
  const finish = source.indexOf('    return () => {', start);
  assert.ok(start > 0 && finish > start);
  const state = { language: createReaderLanguage('en'), starts: [], appearance: 'original', showDeleteX: true, previewZoom: 1.5,
    pageLinksDocument: {cardId: 0, generation: 0} };
  const scope = {
    window: { _incPdfPending: pending, _incPdfFocusState: focus },
    document: { documentElement: { lang: 'en' } },
    createReaderLanguage,
    normalizeReaderLocale,
    normalizePdfAppearanceMode,
    DEFAULT_PDF_LINK_PREVIEW_ZOOM, normalizePdfLinkPreviewZoom,
    setLanguage: (value) => { state.language = value; },
    setLocale: () => {},
    setAppearanceMode: (value) => { state.appearance = value; },
    setPdfFocusState: value => {state.focus = value;},
    setShowHighlightDeleteButtons: (value) => { state.showDeleteX = value; },
    setLinkPreviewZoom: (value) => {state.previewZoom = value;},
    setPageLinksDocument: update => {state.pageLinksDocument = update(state.pageLinksDocument);},
    startViewer: (...args) => state.starts.push(args),
    clampScrollRatio: (value) => value,
    snapshotMode: {setActive: value => {state.snapshotActive = value;}},
    compareHighlights: () => 0,
    DEFAULT_LIMIT_STATUS: {},
  };
  for (const name of [
    'setLinkBackHistory', 'setHighlights', 'setNativeHighlightsVisible', 'setBookmarks', 'setFindOpen',
    'setSearchQuery', 'setSearchHits', 'setActiveSearchHitIndex', 'setReadAnchor',
    'setFindStartPage',
    'setActiveHighlightId', 'suppressScrollPersistence', 'setLimitStatus',
    'setLimitNotice', 'applyAutoHighlightSetting', 'applyScrollToTopOnPageChangeSetting',
    'limitAwareNav', 'adjustZoom', 'limitAwareMarkRead', 'openFind', 'setPageCards',
    'updateHighlightNote', 'setSearchJumpNonce', 'finishHighlightColorPicker',
    'setResizingHighlightId',
  ]) scope[name] = () => {};
  for (const name of [
    'pendingExcerptJumpRef', 'pendingHighlightScrollRef', 'pendingReadAnchorScrollRef',
    'pendingPageTopScrollRef', 'pendingResumeScrollRef', 'pendingResumePageRef',
    'pageRef', 'cardIdRef', 'suppressSearchSyncRef', 'pendingHighlightSelectionRef',
    'resizeHighlightRef', 'contentsGenerationRef', 'pendingContentsFractionRef',
    'pendingDestinationPointRef', 'snapStartRef',
  ]) scope[name] = { current: null };
  scope.highlightRangeCacheRef = { current: new Map() };
  vm.runInNewContext(source.slice(start, finish), scope);
  return { scope, state };
}

for (const entry of ['pending', 'direct']) {
  test(`${entry} startup restores PDF focus and accepts committed toolbar/settings changes`, () => {
    const saved = {cardId: 42, enabled: true, available: true};
    const {scope, state} = registerBridge(entry === 'pending'
      ? {cardId: 42, filename: 'fixture.pdf', page: 1, zoom: 1} : null, saved);
    if (entry === 'direct') scope.window.incrementoPdfStart(42, 'fixture.pdf', 1, 1);
    assert.deepEqual(pdfFocusState(state.focus, state.pageLinksDocument.cardId), {enabled: true, available: true});
    scope.window.incrementoSetPdfFocusState({...saved, enabled: false});
    assert.deepEqual(pdfFocusState(state.focus, state.pageLinksDocument.cardId), {enabled: false, available: true});
    scope.window.incrementoPdfStart(43, 'next.pdf', 1, 1);
    assert.equal(pdfFocusState(state.focus, state.pageLinksDocument.cardId).available, false,
      'The old document must not enable the new toolbar before its current state arrives');
    scope.window.incrementoSetPdfFocusState({...saved, cardId: 43});
    assert.equal(pdfFocusState(state.focus, state.pageLinksDocument.cardId).available, true);
  });
}

test('PDF startup keeps the selected physical page spot and clears it for a normal open', () => {
  const {scope} = registerBridge({cardId: 8, filename: 'other.pdf', page: 42, zoom: 1, pageY: .65});
  assert.equal(scope.pendingDestinationPointRef.current, .65);
  scope.window.incrementoPdfStart(9, 'next.pdf', 1, 1);
  assert.equal(scope.pendingDestinationPointRef.current, null);
});

test('PDF startup and live settings hide the delete X without changing the highlight data', () => {
  const { scope, state } = registerBridge({
    cardId: 10, filename: 'source.pdf', page: 1, zoom: 1,
    showHighlightDeleteButtons: false,
  });
  assert.equal(state.showDeleteX, false);
  scope.window.incrementoSetPdfHighlightDeleteButtons(true);
  assert.equal(state.showDeleteX, true);
  scope.window.incrementoPdfStart(
    10, 'source.pdf', 1, 1, 0, 0, null, '', [], -1, '', '',
    false, null, false, true, [], 'en', null, 'original', false,
  );
  assert.equal(state.showDeleteX, false);
});

test('PDF startup restores profile preview zoom, accepts live Settings changes, and clears the previous profile value', () => {
  const {scope, state} = registerBridge({cardId: 42, filename: 'source.pdf', page: 1, zoom: 1, linkPreviewZoom: 2.5});
  assert.equal(state.previewZoom, 2.5);
  scope.window.incrementoSetPdfLinkPreviewZoom(3);
  assert.equal(state.previewZoom, 3);
  scope.window.incrementoPdfStart(43, 'next.pdf', 1, 1);
  assert.equal(state.previewZoom, 1.5);
});

test('starting another PDF retires the visible page-link document generation', () => {
  const {scope, state} = registerBridge({cardId: 7, filename: 'first.pdf', page: 3, zoom: 1});
  assert.equal(state.pageLinksDocument.cardId, 7);
  const previous = state.pageLinksDocument.generation;
  scope.window.incrementoPdfStart(8, 'second.pdf', 42, 1);
  assert.equal(state.pageLinksDocument.cardId, 8);
  assert.equal(state.pageLinksDocument.generation, previous + 1);
});

const customLanguage = { locale: 'de', messages: {
  reader_previous_page: 'Vorherige Seite',
  reader_add_highlight_note: 'Notiz hinzufügen',
} };

function startDirect(scope, payload = customLanguage) {
  scope.window.incrementoPdfStart(
    10, '<title>我的.pdf', 1, 1, 0, 0, null, '', [], -1, '', '',
    false, null, false, true, [], 'de', payload, 'night',
  );
}

for (const entry of ['pending', 'direct']) {
  test(`${entry} PDF startup installs custom language, preserves user filename, and clears it on next start`, () => {
    const { scope, state } = registerBridge(entry === 'pending' ? {
      cardId: 10, filename: '<title>我的.pdf', page: 1, zoom: 1,
      locale: 'de', customLanguage, appearanceMode: 'night',
    } : null);
    if (entry === 'direct') startDirect(scope);
    assert.equal(scope.document.documentElement.lang, 'de');
    assert.equal(state.language.tr('reader_previous_page'), 'Vorherige Seite');
    assert.equal(state.language.tr('reader_add_highlight_note'), 'Notiz hinzufügen');
    assert.equal(state.starts[0][1], '<title>我的.pdf');
    assert.equal(state.appearance, 'night');
    assert.equal(scope.window._incPdfPending, null);

    startDirect(scope, null);
    assert.equal(scope.document.documentElement.lang, 'en');
    assert.equal(state.language.tr('reader_previous_page'), 'Previous page');
  });
}

test('starting another PDF exits snapshot selection and clears an unfinished drag', () => {
  const {scope, state} = registerBridge(null);
  state.snapshotActive = true;
  scope.snapStartRef.current = {x: 10, y: 20};
  scope.window.incrementoPdfStart(17, 'fixture.pdf', 1, 1);
  assert.equal(state.snapshotActive, false);
  assert.equal(scope.snapStartRef.current, null);
});
