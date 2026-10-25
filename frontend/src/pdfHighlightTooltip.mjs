/** Only the tooltip subscribes; pointer movement never rerenders the reader. */
export function createPdfHighlightTooltip({schedule = run => window.requestAnimationFrame(run),
  cancel = id => window.cancelAnimationFrame(id)} = {}) {
  const listeners = new Set();
  let value = null, position = null, frame = null;
  const publish = next => {value = next; for (const listener of listeners) listener();};
  const stop = () => {if (frame !== null) cancel(frame); frame = null; position = null;};
  return {
    subscribe(listener) {listeners.add(listener); return () => listeners.delete(listener);},
    getSnapshot: () => value,
    show(highlight, event) {
      const note = String(highlight?.note || '').trim();
      if (!note) return;
      stop(); publish({id: String(highlight.id || ''), note,
        x: Number(event?.clientX || 0), y: Number(event?.clientY || 0)});
    },
    move(event) {
      if (!value) return;
      position = {x: Number(event?.clientX ?? value.x), y: Number(event?.clientY ?? value.y)};
      if (frame === null) frame = schedule(() => {
        frame = null;
        if (value && position) publish({...value, ...position});
        position = null;
      });
    },
    hide() {stop(); if (value) publish(null);},
  };
}
