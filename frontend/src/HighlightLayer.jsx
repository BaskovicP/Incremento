/**
 * HighlightLayer — renders highlight rects, delete buttons, and the
 * snapshot selection overlay, all absolutely positioned inside the
 * #pdf-canvas-wrapper.
 */

const HL_COLORS = {
  yellow: 'rgba(255,220,0,0.45)',
  green:  'rgba(0,200,80,0.4)',
  blue:   'rgba(30,144,255,0.4)',
  pink:   'rgba(255,80,140,0.4)',
};

export default function HighlightLayer({
  pageHighlights,
  renderInfo,
  deleteHighlight,
  snapshotMode,
  snapRect,
  handleSnapStart,
  handleSnapMove,
  handleSnapEnd,
}) {
  return (
    <>
      {/* ── Highlight rects — below text layer (z:1), non-blocking ── */}
      {pageHighlights.map(h =>
        h.rects.map((r, ri) => (
          <div
            key={`${h.id}-${ri}`}
            style={{
              position:      'absolute',
              left:          renderInfo.tlLeft + r.x * renderInfo.scale,
              top:           r.y * renderInfo.scale,
              width:         r.w * renderInfo.scale,
              height:        r.h * renderInfo.scale,
              background:    HL_COLORS[h.color] || HL_COLORS.yellow,
              mixBlendMode:  'multiply',
              pointerEvents: 'none',
              zIndex:        1,
            }}
          />
        ))
      )}

      {/* ── Delete buttons — above text layer (z:10), one per highlight ── */}
      {pageHighlights.map(h => {
        if (!h.rects.length) return null;
        const r = h.rects[0];
        return (
          <button
            key={`del-${h.id}`}
            title="Remove highlight"
            onClick={() => deleteHighlight(h.id)}
            style={{
              position:   'absolute',
              left:       renderInfo.tlLeft + (r.x + r.w) * renderInfo.scale - 8,
              top:        r.y * renderInfo.scale - 8,
              width: 16, height: 16,
              fontSize: 10, lineHeight: '16px', textAlign: 'center',
              padding: 0, border: 'none',
              background: 'rgba(80,80,80,0.85)', color: '#fff',
              borderRadius: '50%', cursor: 'pointer',
              zIndex: 10,
            }}
          >
            ×
          </button>
        );
      })}

      {/* ── Snapshot selection overlay (z:20) ── */}
      {snapshotMode && (
        <div
          style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
                   cursor: 'crosshair', zIndex: 20, userSelect: 'none' }}
          onMouseDown={handleSnapStart}
          onMouseMove={handleSnapMove}
          onMouseUp={handleSnapEnd}
        >
          {snapRect && snapRect.w > 2 && snapRect.h > 2 && (
            <div style={{
              position:   'absolute',
              left:       snapRect.x, top: snapRect.y,
              width:      snapRect.w, height: snapRect.h,
              border:     '2px dashed rgb(37,99,235)',
              background: 'rgba(37,99,235,0.08)',
              pointerEvents: 'none',
              boxSizing:  'border-box',
            }} />
          )}
        </div>
      )}
    </>
  );
}
