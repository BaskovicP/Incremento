/** Local PDF bytes use the existing authenticated reader bridge, with no network. */
export function decodePdfByteRange(encoded, target, decode = atob) {
  if (typeof target.setFromBase64 === 'function') {
    const result = target.setFromBase64(encoded, {lastChunkHandling: 'strict'});
    if (result.read !== encoded.length || result.written !== target.length) throw new Error('Invalid PDF byte count');
    return;
  }
  const text = decode(encoded);
  if (text.length !== target.length) throw new Error('Invalid PDF byte count');
  for (let index = 0; index < text.length; index++) target[index] = text.charCodeAt(index);
}

export function createPdfByteRangeTransport(lib, metadata, send, onError, host = window) {
  const {token, cardId, length, chunkSize} = metadata;
  if (typeof token !== 'string' || !Number.isSafeInteger(length) || length <= 0
      || chunkSize !== 262144 || !Number.isSafeInteger(cardId) || cardId <= 0) {
    throw new Error('Invalid PDF byte source');
  }
  const range = new lib.PDFDataRangeTransport(length, new Uint8Array(0), true);
  const queued = [], pending = new Map();
  let retired = false, nextId = 0;
  const previous = host.incrementoReceivePdfRange;
  const abort = () => {
    retired = true; queued.length = 0; pending.clear();
    if (host.incrementoReceivePdfRange === receive) {
      if (previous) host.incrementoReceivePdfRange = previous;
      else delete host.incrementoReceivePdfRange;
    }
  };
  const fail = () => {if (!retired) {abort(); onError(new Error('PDF range unavailable'));}};
  const drain = () => {
    while (!retired && queued.length && pending.size < 2) {
      const request = {...queued.shift(), requestId: ++nextId, cardId, token};
      pending.set(request.requestId, request);
      const {begin, end, requestId} = request;
      try {send('incremento_pdf_range:' + JSON.stringify({begin, end, requestId, cardId, token}));} catch (_) {fail();}
    }
  };
  const receive = payload => {
    if (retired || payload?.token !== token) return;
    const request = pending.get(payload.requestId);
    if (!request) return;
    if (payload.error || payload.begin !== request.begin || typeof payload.data !== 'string'
        || payload.data.length > Math.ceil(chunkSize / 3) * 4) {fail(); return;}
    try {
      const group = request.group;
      const offset = request.begin - group.begin;
      decodePdfByteRange(payload.data, group.bytes.subarray(offset, offset + request.end - request.begin), host.atob);
      pending.delete(payload.requestId);
      group.received += request.end - request.begin;
      // PDF.js matches a range reader by its original begin offset and closes
      // it after one response. Reassemble bounded bridge reads before delivery.
      if (group.received === group.bytes.length) range.onDataRange(group.begin, group.bytes);
      drain();
    } catch (_) {fail();}
  };
  host.incrementoReceivePdfRange = receive;
  range.abort = abort;
  range.requestDataRange = (begin, end) => {
    if (retired) return;
    if (!Number.isSafeInteger(begin) || !Number.isSafeInteger(end) || begin < 0 || end > length || begin >= end) {
      fail(); return;
    }
    const group = {begin, bytes: new Uint8Array(end - begin), received: 0};
    // New page requests take precedence over queued neighbor preparation.
    for (let offset = begin + Math.floor((end - begin - 1) / chunkSize) * chunkSize;
      offset >= begin; offset -= chunkSize) {
      queued.unshift({begin: offset, end: Math.min(end, offset + chunkSize), group});
    }
    drain();
  };
  return range;
}
