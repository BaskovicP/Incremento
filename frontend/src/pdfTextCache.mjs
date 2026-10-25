// Page proxies remain cached by PDF.js: resource release explicitly forgets text.
const cache = new WeakMap();

function save(page, entry, content) {
  if (cache.get(page) === entry) {
    if ((content?.items?.length || 0) <= 20000) entry.value = content;
    else cache.delete(page);
  }
  return content;
}

async function collect(reader) {
  const content = {items: [], styles: {}, lang: null};
  while (true) {
    const {value, done} = await reader.read();
    if (done) return content;
    content.items.push(...(value.items || []));
    Object.assign(content.styles, value.styles);
    content.lang ??= value.lang;
  }
}

export function pdfPageTextContent(page) {
  let entry = cache.get(page);
  if (entry) return entry.promise;
  entry = {};
  cache.set(page, entry);
  entry.promise = Promise.resolve().then(() => {
    if (typeof page.getTextContent === 'function') return page.getTextContent();
    const stream = page.streamTextContent?.();
    if (!stream?.getReader) return {items: [], styles: {}};
    entry.reader = stream.getReader();
    return collect(entry.reader);
  }).then(content => save(page, entry, content), error => {
    if (cache.get(page) === entry) cache.delete(page);
    throw error;
  });
  return entry.promise;
}

export function pdfPageTextSource(page) {
  const previous = cache.get(page);
  if (previous) return {source: previous.value || previous.promise, content: previous.promise};
  const stream = page.streamTextContent?.();
  if (!stream?.tee) {
    const content = pdfPageTextContent(page);
    return {source: content, content};
  }
  const [source, metadata] = stream.tee();
  const entry = {reader: metadata.getReader(), source};
  cache.set(page, entry);
  entry.promise = collect(entry.reader).then(content => save(page, entry, content), error => {
    if (cache.get(page) === entry) cache.delete(page);
    throw error;
  });
  return {source, content: entry.promise};
}

export function forgetPdfPageText(page) {
  const entry = cache.get(page);
  cache.delete(page);
  try {entry?.reader?.cancel()?.catch(() => {});} catch (_) {}
  try {entry?.source?.cancel()?.catch(() => {});} catch (_) {}
}
