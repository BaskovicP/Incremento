import { useSyncExternalStore } from 'react';

export function PdfSnapshotButton({ mode, tr, onToggle }) {
  const active = useSyncExternalStore(mode.subscribe, mode.getSnapshot);
  return (
    <button
      type="button"
      title={active ? tr('reader_cancel_snapshot') : tr('reader_draw_snapshot')}
      aria-pressed={active}
      style={{
        background: active ? 'rgba(37,99,235,0.2)' : 'transparent',
        border: '1px solid rgba(37,99,235,0.5)', borderRadius: 8,
        color: active ? 'rgb(37,99,235)' : 'inherit', cursor: 'pointer',
        padding: '4px 10px', fontSize: 12, fontWeight: active ? 'bold' : 'normal',
      }}
      onClick={() => { onToggle(); mode.setActive(!mode.getSnapshot()); }}
    >
      &#x1F4F7; {tr('reader_snapshot')}
    </button>
  );
}

/** A sibling of the annotations: toggling capture never processes their geometry. */
export default function PdfSnapshotLayer({ mode, previewRef, onStart, onMove, onEnd }) {
  const active = useSyncExternalStore(mode.subscribe, mode.getSnapshot);
  if (!active) return null;
  return (
    <div data-pdf-snapshot-overlay="true"
      style={{ position: 'absolute', inset: 0, cursor: 'crosshair', zIndex: 20, userSelect: 'none' }}
      onMouseDown={onStart} onMouseMove={onMove} onMouseUp={onEnd}
    >
      <div ref={previewRef} style={{ display: 'none', position: 'absolute',
        border: '2px dashed rgb(37,99,235)', background: 'rgba(37,99,235,0.08)',
        pointerEvents: 'none', boxSizing: 'border-box' }} />
    </div>
  );
}
