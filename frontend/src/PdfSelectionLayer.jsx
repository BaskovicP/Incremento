import { useEffect, useState } from 'react';
import { observePdfTextSelection } from './pdfSelection.mjs';

// Draw the current selection above the PDF as non-interactive blue rectangles.
// Saved annotations remain in HighlightLayer; both paths share line merging.
export default function PdfSelectionLayer({ textLayerRef, renderInfo }) {
  const [rects, setRects] = useState([]);
  useEffect(() => {
    const textLayer = textLayerRef.current;
    if (!textLayer) return;
    return observePdfTextSelection(textLayer, setRects);
  }, [textLayerRef, renderInfo]);

  // Hide native fragmented paint only while we have a replacement to draw.
  // Removing this style with the overlay restores the host's native fallback.
  if (!rects.length) return null;
  return (
    <>
      <style>{'#pdf-text-layer ::selection { background: transparent; }'}</style>
      <div
        id="pdf-selection-layer"
        aria-hidden={true}
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
      </div>
    </>
  );
}
