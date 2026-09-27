import { useEffect, useRef, useState } from 'react';
import { createReaderLanguage } from './i18n.mjs';
import {
  installPrecisePdfSelectionDrag,
  movePdfSelectionEndpoint,
  observePdfTextSelection,
} from './pdfSelection.mjs';

const DEFAULT_LANGUAGE = createReaderLanguage('en');

// Draw the current selection above the PDF as blue rectangles with interactive
// endpoint handles. Saved annotations remain in HighlightLayer.
export default function PdfSelectionLayer({ language = DEFAULT_LANGUAGE, textLayerRef, renderInfo }) {
  const [rects, setRects] = useState([]);
  const [dragPreview, setDragPreview] = useState(null);
  const resizeRef = useRef(null);
  useEffect(() => {
    const textLayer = textLayerRef.current;
    if (!textLayer) return;
    const stopObserving = observePdfTextSelection(textLayer, setRects);
    const stopPreciseDrag = installPrecisePdfSelectionDrag(textLayer, {
      onDragPreview: setDragPreview,
    });
    return () => {
      stopPreciseDrag();
      stopObserving();
    };
  }, [textLayerRef, renderInfo]);

  const beginResize = (endpoint, event) => {
    const textLayer = textLayerRef.current;
    const selection = window.getSelection();
    if (!textLayer || !selection || selection.isCollapsed || !selection.rangeCount) return;
    const range = selection.getRangeAt(0);
    if (!textLayer.contains(range.commonAncestorContainer)) return;
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget?.setPointerCapture?.(event.pointerId);
    resizeRef.current = {
      endpoint,
      range: range.cloneRange(),
      original: range.cloneRange(),
      pointerId: Number.isFinite(Number(event.pointerId)) ? Number(event.pointerId) : null,
    };
  };

  const moveResize = (event) => {
    const session = resizeRef.current;
    const textLayer = textLayerRef.current;
    if (!session || !textLayer) return;
    if (session.pointerId !== null && Number(event.pointerId) !== session.pointerId) return;
    const next = movePdfSelectionEndpoint(
      textLayer,
      session.range,
      session.endpoint,
      Number(event.clientX),
      Number(event.clientY),
    );
    if (next) session.range = next;
  };

  const endResize = (event) => {
    if (!resizeRef.current) return;
    moveResize(event);
    event.currentTarget?.releasePointerCapture?.(event.pointerId);
    resizeRef.current = null;
  };

  const cancelResize = (event) => {
    const session = resizeRef.current;
    if (!session) return;
    const selection = window.getSelection();
    if (selection) {
      selection.removeAllRanges();
      selection.addRange(session.original);
    }
    event.currentTarget?.releasePointerCapture?.(event.pointerId);
    resizeRef.current = null;
  };

  // Hide native fragmented paint only while we have a replacement to draw.
  // Removing this style with the overlay restores the host's native fallback.
  if (!rects.length && !dragPreview) return null;
  const first = rects[0];
  const last = rects[rects.length - 1];
  const handles = rects.length ? [
    { endpoint: 'start', left: first.x - 12, top: first.y - 28, stemTop: 14, dotTop: 2 },
    { endpoint: 'end', left: last.x + last.w - 12, top: last.y + last.h, stemTop: 0, dotTop: 14 },
  ] : [];
  return (
    <>
      <style>{'#pdf-text-layer ::selection { background: transparent; }'}</style>
      <div
        id="pdf-selection-layer"
        aria-hidden={false}
        // Local rectangle coordinates are already zoomed; only offset the layer
        // to match the centered PDF. Let mouse events pass through to the text.
        style={{ position: 'absolute', left: renderInfo.tlLeft, top: 0,
                 pointerEvents: 'none', userSelect: 'none', zIndex: 3 }}
      >
        {rects.map((rect, index) => (
          <div
            key={index}
            style={{ position: 'absolute', left: rect.x, top: rect.y,
                     width: rect.w, height: rect.h,
                     background: 'rgba(0,100,255,0.3)', mixBlendMode: 'multiply' }}
          />
        ))}
        {dragPreview ? (
          <div
            className="incremento-pdf-selection-loupe"
            aria-hidden="true"
            style={{
              position: 'absolute',
              left: dragPreview.x,
              top: dragPreview.y < 64 ? dragPreview.y + 24 : dragPreview.y - 18,
              transform: dragPreview.y < 64 ? 'translate(-50%, 0)' : 'translate(-50%, -100%)',
              display: 'flex',
              alignItems: 'center',
              minWidth: 64,
              maxWidth: 300,
              minHeight: 34,
              padding: '4px 10px',
              border: '1px solid rgba(255,255,255,0.92)',
              borderRadius: 9,
              boxSizing: 'border-box',
              overflow: 'hidden',
              color: '#fff',
              background: 'rgba(24,31,39,0.94)',
              boxShadow: '0 3px 12px rgba(0,0,0,0.42)',
              fontFamily: 'Georgia, Times New Roman, serif',
              fontSize: 18,
              lineHeight: 1.25,
              whiteSpace: 'pre',
              pointerEvents: 'none',
              zIndex: 5,
            }}
          >
            <span>{dragPreview.before || '\u00a0'}</span>
            <span
              className="incremento-pdf-selection-loupe-caret"
              style={{ width: 2, height: 24, flex: '0 0 2px', background: 'rgb(34,211,238)' }}
            />
            <span>{dragPreview.after || '\u00a0'}</span>
          </div>
        ) : null}
        {handles.map((handle) => (
          <button
            key={handle.endpoint}
            type="button"
            className="incremento-pdf-selection-resize-handle"
            data-endpoint={handle.endpoint}
            aria-label={language.tr(
              handle.endpoint === 'start' ? 'reader_resize_highlight_start' : 'reader_resize_highlight_end',
            )}
            title={language.tr(
              handle.endpoint === 'start' ? 'reader_resize_highlight_start' : 'reader_resize_highlight_end',
            )}
            onPointerDown={(event) => beginResize(handle.endpoint, event)}
            onPointerMove={moveResize}
            onPointerUp={endResize}
            onPointerCancel={cancelResize}
            style={{
              position: 'absolute',
              left: handle.left,
              top: handle.top,
              width: 24,
              height: 28,
              margin: 0,
              padding: 0,
              border: 0,
              background: 'transparent',
              cursor: 'ew-resize',
              pointerEvents: 'auto',
              touchAction: 'none',
              zIndex: 4,
            }}
          >
            <span aria-hidden="true" style={{
              position: 'absolute',
              left: 11,
              top: handle.stemTop,
              width: 2,
              height: 12,
              borderRadius: 2,
              background: 'rgb(14,116,144)',
              boxShadow: '0 0 0 1px rgba(255,255,255,0.78)',
            }} />
            <span aria-hidden="true" style={{
              position: 'absolute',
              left: 6,
              top: handle.dotTop,
              width: 12,
              height: 12,
              borderRadius: '50%',
              background: 'rgb(14,116,144)',
              border: '2px solid #fff',
              boxSizing: 'border-box',
              boxShadow: '0 1px 4px rgba(0,0,0,0.45)',
            }} />
          </button>
        ))}
      </div>
    </>
  );
}
