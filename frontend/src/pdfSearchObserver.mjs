// PDF.js owns the text layer. Observe its changes, excluding our mark writes.
export function observeSearchText(target, {
  render, clear,
  createObserver = (callback) => new MutationObserver(callback),
  requestFrame = (callback) => window.requestAnimationFrame(callback),
  cancelFrame = (id) => window.cancelAnimationFrame(id),
}) {
  let frame = 0;
  let closed = false;
  const refresh = () => {
    frame = 0;
    if (closed) return;
    observer.disconnect();
    try { render(); }
    finally {
      if (!closed) observer.observe(target, { childList: true, subtree: true, characterData: true });
    }
  };
  const observer = createObserver(() => {
    if (!closed && !frame) frame = requestFrame(refresh);
  });
  refresh();
  return () => {
    closed = true;
    if (frame) cancelFrame(frame);
    observer.disconnect();
    clear();
  };
}
