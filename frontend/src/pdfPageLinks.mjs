/** Match the space reserved for reading to wrapped or customized controls. */
export function observePdfToolbarHeight(element, changed, Observer) {
  if (!element) return () => {};
  let active = true, previous = 0;
  const measure = () => {
    if (!active) return;
    const height = Math.ceil(element.getBoundingClientRect().height);
    if (height > 0 && height !== previous) {previous = height; changed(height);}
  };
  const observer = Observer ? new Observer(measure) : null;
  measure();
  observer?.observe(element);
  return () => {active = false; observer?.disconnect();};
}

/** Only the bottom toolbar reserves space; link popups never move the page. */
export function pdfPageLinksViewport({scrollY, wrapperTop, pageHeight, windowHeight, controlsHeight}) {
  const visibleHeight = Math.max(1, windowHeight - controlsHeight);
  return {pageTop: scrollY + wrapperTop, pageHeight, visibleHeight,
    maxOffset: Math.max(0, pageHeight - visibleHeight)};
}

/** Page-local connection state. Replies and actions cannot outlive their page. */
export function createPdfPageLinks(send, changed) {
  let current = null, serial = 0, links = [], writing = [];
  function refresh() {
    links = [];
    writing = [];
    if (!current) {changed({links, writing, loading: false, error: false}); return;}
    current = {...current, request: ++serial};
    changed({...current, links, writing, loading: true, error: false});
    send({...current, operation: 'list'});
  }
  function command(operation, extra = {}) {
    if (current) send({...current, operation, ...extra});
  }
  return {
    start(cardId, page, generation) {
      current = Number.isSafeInteger(cardId) && cardId > 0 && Number.isInteger(page) && page > 0
        ? {cardId, page, generation} : null;
      refresh();
    },
    refresh,
    receive(data) {
      if (!current || !data || !['request', 'cardId', 'page', 'generation'].every(key => data[key] === current[key])) return;
      links = Array.isArray(data.links) ? data.links.slice(0, 200).filter(row => row && Number.isSafeInteger(row.id)
        && row.id > 0 && ['outgoing', 'incoming'].includes(row.direction) && Number.isInteger(row.target_page)
        && row.target_page > 0 && typeof row.title === 'string' && typeof row.available === 'boolean') : [];
      writing = Array.isArray(data.writing) ? data.writing.slice(0, 200).filter(row => row
        && typeof row.anchor === 'string' && /^[a-f0-9]{32}$/.test(row.anchor)
        && typeof row.title === 'string' && typeof row.quote === 'string') : [];
      changed({...current, links, writing, loading: false, error: !!data.error});
    },
    openWriting(row) {
      if (writing.includes(row)) command('writing', {anchor: row.anchor});
    },
    jump(row, mode = 'jump') {
      if (links.includes(row) && row.available && ['jump', 'beside'].includes(mode)) {
        command('jump', {id: row.id, direction: row.direction, mode});
      }
    },
    remove(row) {
      if (links.includes(row)) command('remove', {id: row.id, direction: row.direction});
    },
    create() {command('create');},
    manage() {command('manage');},
    recordings() {command('recordings');},
    linkRecording() {command('link_recording');},
    close() {current = null; links = []; writing = [];},
  };
}
