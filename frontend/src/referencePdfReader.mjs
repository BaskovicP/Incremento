export function referenceActionLocation(requested, rendered) {
  if (!rendered || rendered.page !== requested.page || rendered.zoom !== requested.zoom
      || rendered.generation !== requested.generation) return null;
  return {page: rendered.page, zoom: rendered.zoom};
}

export function referenceSelectionText(selection, layer) {
  if (!layer || !selection || selection.isCollapsed || !selection.rangeCount
      || !layer.contains(selection.getRangeAt(0).commonAncestorContainer)) return '';
  return selection.toString().slice(0, 6000).trim();
}

export function referenceRenderPlan(base, width, zoom, pixelRatio) {
  if (![base.width, base.height, width, zoom].every(value => Number.isFinite(value) && value > 0)) {
    throw new RangeError('Invalid PDF page geometry');
  }
  const scale = Math.min(Math.min(width / base.width, 2) * Math.min(4, zoom),
    16384 / base.width, 16384 / base.height);
  const w = base.width * scale, h = base.height * scale;
  const pixels = Math.min(Number.isFinite(pixelRatio) && pixelRatio > 0 ? pixelRatio : 1, 2,
    8192 / w, 8192 / h, Math.sqrt((8_000_000 - 32768) / (w * h)));
  return {scale, pixels, canvasWidth: Math.max(1, Math.ceil(w * pixels)),
    canvasHeight: Math.max(1, Math.ceil(h * pixels))};
}

export function referenceRestoreRatio({page, renderedPage, ratio, initial = null}) {
  const candidate = initial !== null ? initial : page === renderedPage ? ratio : 0;
  return Number.isFinite(candidate) ? Math.max(0, Math.min(1, candidate)) : 0;
}

export function referenceScrollSnapshot(current, rendered, previous) {
  if (current.width !== rendered.width || current.height !== rendered.height) return previous;
  return current.extent > 0 ? Math.max(0, Math.min(1, current.top / current.extent)) : 0;
}

export function referenceExcerptItemIndex(items, excerpt) {
  const normalize = value => String(value || '').normalize('NFKC').replace(/\s+/g, ' ').trim().toLocaleLowerCase();
  const needle = normalize(excerpt).slice(0, 320);
  if (!needle) return -1;
  let text = '';
  const ends = [];
  for (const item of items.slice(0, 20000)) {
    text += normalize(item.str) + ' ';
    ends.push(text.length);
    if (text.length > 250000) break;
  }
  const found = text.indexOf(needle);
  return found < 0 ? -1 : ends.findIndex(end => end > found);
}

/** Independent, read-only reference navigation. No Anki/progress messages. */
export function createReferenceReader(onChange = () => {}) {
  let doc = null, task = null, generation = 0, searchGeneration = 0, closed = false;
  let page = 1, pages = 0, zoom = 1;
  const history = [];
  const state = () => ({page, pages, zoom, generation, canBack: history.length > 0});
  const notify = () => onChange(state());
  const navigate = (target, remember = true) => {
    if (closed || !Number.isInteger(target) || target < 1 || target > pages) return false;
    ++searchGeneration;
    if (target !== page && remember) {history.push(page); if (history.length > 50) history.shift();}
    page = target; notify(); return true;
  };
  return {
    state, document: () => doc, navigate,
    back() {if (history.length) navigate(history.pop(), false);},
    setZoom(value) {if (!closed && doc && Number.isFinite(value)) {zoom = Math.max(.25, Math.min(4, value)); notify();}},
    async load(lib, url, startPage = 1, maxPage = 1_000_000) {
      const token = ++generation;
      ++searchGeneration;
      closed = false; doc = null; pages = 0; history.length = 0;
      page = Number.isInteger(startPage) ? Math.max(1, startPage) : 1;
      zoom = 1;
      notify();
      try {task?.destroy()?.catch?.(() => {});} catch (_) {}
      task = lib.getDocument({url, isEvalSupported: false});
      try {
        const loaded = await task.promise;
        if (closed || token !== generation) {loaded.destroy()?.catch?.(() => {}); return;}
        doc = loaded; pages = Math.max(1, Math.min(loaded.numPages, maxPage));
        page = Math.max(1, Math.min(Number.isInteger(startPage) ? startPage : 1, pages));
        notify();
      } catch (error) {if (!closed && token === generation) throw error;}
    },
    async find(raw) {
      const query = String(raw || '').trim().toLocaleLowerCase().slice(0, 200);
      if (!doc || !query || closed) return null;
      const token = ++searchGeneration, document = doc, start = page;
      for (let offset = 1; offset <= pages; offset++) {
        const target = ((start - 1 + offset) % pages) + 1;
        const pdfPage = await document.getPage(target);
        if (closed || token !== searchGeneration || doc !== document) return undefined;
        const content = await pdfPage.getTextContent();
        if (closed || token !== searchGeneration || doc !== document) return undefined;
        let text = '';
        for (const item of content.items.slice(0, 20000)) {
          text += String(item.str || '').slice(0, 250000 - text.length) + ' ';
          if (text.length >= 250000) break;
        }
        if (text.toLocaleLowerCase().includes(query)) {
          navigate(target); return target;
        }
      }
      return null;
    },
    close() {
      closed = true; ++generation; ++searchGeneration;
      try {task?.destroy()?.catch?.(() => {});} catch (_) {}
      task = null; doc = null;
    },
  };
}
