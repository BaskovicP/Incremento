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
  aqua:   'rgba(45,212,191,0.42)',
  orange: 'rgba(251,146,60,0.42)',
  red:    'rgba(248,113,113,0.42)',
  purple: 'rgba(168,85,247,0.4)',
  snapshot: 'rgba(37,99,235,0.12)',
};

function isSnapshotHighlight(highlight) {
  return String(highlight?.color || '') === 'snapshot';
}

export default function HighlightLayer({
  pageHighlights,
  renderInfo,
  deleteHighlight,
  editHighlightNote,
  focusedHighlightId,
  showHighlightNote,
  moveHighlightNote,
  hideHighlightNote,
  snapshotMode,
  snapRect,
  handleSnapStart,
  handleSnapMove,
  handleSnapEnd,
}) {
  const renderNoteIcon = (hasNote) => (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      width="10"
      height="10"
      style={{ display: 'block' }}
    >
      <path
        d="M3 2.5h6.5L13 6v7a.5.5 0 0 1-.5.5h-9A.5.5 0 0 1 3 13z"
        fill={hasNote ? 'rgba(191,219,254,0.98)' : 'none'}
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      <path
        d="M9.5 2.5V6H13"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      <path
        d="M5.2 8.1h5.2M5.2 10.2h4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.1"
        strokeLinecap="round"
      />
    </svg>
  );

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
              border:        isSnapshotHighlight(h) ? '2px solid rgba(37,99,235,0.95)' : 'none',
              boxSizing:     'border-box',
              mixBlendMode:  isSnapshotHighlight(h) ? 'normal' : 'multiply',
              outline:       h.id === focusedHighlightId ? '2px solid rgba(255,255,255,0.95)' : 'none',
              boxShadow:     h.id === focusedHighlightId ? '0 0 0 3px rgba(56,189,248,0.55)' : 'none',
              pointerEvents: 'none',
              zIndex:        1,
            }}
          />
        ))
      )}

      {/* ── Hover targets for note-bearing highlights — above text layer ── */}
      {pageHighlights.map(h =>
        !String(h.note || '').trim()
          ? null
          : h.rects.map((r, ri) => (
              <div
                key={`note-${h.id}-${ri}`}
                title={String(h.note || '').trim()}
                onMouseEnter={(event) => showHighlightNote(h, event)}
                onMouseMove={moveHighlightNote}
                onMouseLeave={hideHighlightNote}
                style={{
                  position: 'absolute',
                  left: renderInfo.tlLeft + r.x * renderInfo.scale,
                  top: r.y * renderInfo.scale,
                  width: r.w * renderInfo.scale,
                  height: r.h * renderInfo.scale,
                  background: 'transparent',
                  cursor: 'help',
                  zIndex: 9,
                }}
              />
            ))
      )}

      {/* ── Highlight action buttons — above text layer (z:10), one cluster per highlight ── */}
      {pageHighlights.map(h => {
        if (!h.rects.length) return null;
        const r = h.rects[0];
        const hasNote = !!String(h.note || '').trim();
        return (
          <div
            key={`actions-${h.id}`}
            style={{
              position: 'absolute',
              left: renderInfo.tlLeft + (r.x + r.w) * renderInfo.scale - 28,
              top: r.y * renderInfo.scale - 8,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              zIndex: 10,
            }}
          >
            <button
              title={hasNote ? 'Edit highlight note' : 'Add highlight note'}
              onClick={() => editHighlightNote(h.id)}
              style={{
                width: 16,
                height: 16,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: 0,
                border: hasNote ? '1px solid rgba(96,165,250,0.92)' : '1px solid rgba(148,163,184,0.9)',
                background: hasNote ? 'rgba(37,99,235,0.92)' : 'rgba(55,65,81,0.9)',
                color: '#fff',
                borderRadius: '50%',
                cursor: 'pointer',
                boxShadow: hasNote ? '0 0 0 1px rgba(191,219,254,0.3)' : 'none',
              }}
            >
              {renderNoteIcon(hasNote)}
            </button>
            <button
              title={isSnapshotHighlight(h) ? 'Remove snapshot highlight' : 'Remove highlight'}
              onClick={() => deleteHighlight(h.id)}
              style={{
                width: 16,
                height: 16,
                fontSize: 10,
                lineHeight: '16px',
                textAlign: 'center',
                padding: 0,
                border: 'none',
                background: 'rgba(80,80,80,0.85)',
                color: '#fff',
                borderRadius: '50%',
                cursor: 'pointer',
              }}
            >
              ×
            </button>
          </div>
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
