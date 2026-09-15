import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import { createReaderLanguage, normalizeReaderLocale } from '../src/i18n.mjs';

// Exercise the actual global bridge registration without mounting the canvas or
// PDF.js. React state setters and the render pipeline are the boundary fakes.
function registerBridge(pending = null) {
  const source = readFileSync(new URL('../src/PdfViewer.jsx', import.meta.url), 'utf8');
  const start = source.indexOf('    const startWithHighlights = (');
  const finish = source.indexOf('    return () => {', start);
  assert.ok(start > 0 && finish > start);
  const state = { language: createReaderLanguage('en'), starts: [] };
  const scope = {
    window: { _incPdfPending: pending },
    document: { documentElement: { lang: 'en' } },
    createReaderLanguage,
    normalizeReaderLocale,
    setLanguage: (value) => { state.language = value; },
    setLocale: () => {},
    startViewer: (...args) => state.starts.push(args),
    clampScrollRatio: (value) => value,
    compareHighlights: () => 0,
    DEFAULT_LIMIT_STATUS: {},
  };
  for (const name of [
    'setLinkBackHistory', 'setHighlights', 'setNativeHighlightsVisible', 'setBookmarks', 'setFindOpen',
    'setSearchQuery', 'setSearchHits', 'setActiveSearchHitIndex', 'setReadAnchor',
    'setActiveHighlightId', 'suppressScrollPersistence', 'setLimitStatus',
    'setLimitNotice', 'applyAutoHighlightSetting', 'applyScrollToTopOnPageChangeSetting',
    'limitAwareNav', 'adjustZoom', 'limitAwareMarkRead', 'openFind', 'setPageCards',
    'updateHighlightNote', 'setSearchJumpNonce',
  ]) scope[name] = () => {};
  for (const name of [
    'pendingExcerptJumpRef', 'pendingHighlightScrollRef', 'pendingReadAnchorScrollRef',
    'pendingPageTopScrollRef', 'pendingResumeScrollRef', 'pendingResumePageRef',
    'pageRef', 'suppressSearchSyncRef',
  ]) scope[name] = { current: null };
  vm.runInNewContext(source.slice(start, finish), scope);
  return { scope, state };
}

const customLanguage = { locale: 'de', messages: {
  reader_previous_page: 'Vorherige Seite',
  reader_add_highlight_note: 'Notiz hinzufügen',
} };

function startDirect(scope, payload = customLanguage) {
  scope.window.incrementoPdfStart(
    10, '<title>我的.pdf', 1, 1, 0, 0, null, '', [], -1, '', '',
    false, null, false, true, [], 'de', payload,
  );
}

for (const entry of ['pending', 'direct']) {
  test(`${entry} PDF startup installs custom language, preserves user filename, and clears it on next start`, () => {
    const { scope, state } = registerBridge(entry === 'pending' ? {
      cardId: 10, filename: '<title>我的.pdf', page: 1, zoom: 1,
      locale: 'de', customLanguage,
    } : null);
    if (entry === 'direct') startDirect(scope);
    assert.equal(scope.document.documentElement.lang, 'de');
    assert.equal(state.language.tr('reader_previous_page'), 'Vorherige Seite');
    assert.equal(state.language.tr('reader_add_highlight_note'), 'Notiz hinzufügen');
    assert.equal(state.starts[0][1], '<title>我的.pdf');
    assert.equal(scope.window._incPdfPending, null);

    startDirect(scope, null);
    assert.equal(scope.document.documentElement.lang, 'en');
    assert.equal(state.language.tr('reader_previous_page'), 'Previous page');
  });
}
