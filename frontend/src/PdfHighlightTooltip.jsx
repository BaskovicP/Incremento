import {useSyncExternalStore} from 'react';
import AnnotationNote from './AnnotationNote.jsx';
import {pdfHighlightTooltipSurfaceStyle} from './pdfHighlightTooltip.mjs';

export default function PdfHighlightTooltip({tooltip}) {
  const note = useSyncExternalStore(tooltip.subscribe, tooltip.getSnapshot);
  if (!note) return null;
  const surface = pdfHighlightTooltipSurfaceStyle(note, window.innerWidth, window.innerHeight);
  return <div role="tooltip" onPointerEnter={tooltip.cancelHide} onPointerLeave={tooltip.scheduleHide}
    onWheel={event => event.stopPropagation()} onPointerDown={event => event.stopPropagation()}
    style={{position: 'fixed', ...surface, boxSizing: 'border-box', scrollbarGutter: 'stable',
    padding: '10px 12px', background: 'rgba(20,20,20,0.96)',
    border: '1px solid rgba(147,197,253,0.45)', borderRadius: 6, color: 'rgb(219,234,254)',
    fontSize: 12, lineHeight: 1.4, boxShadow: '0 8px 18px rgba(0,0,0,0.35)',
    textAlign: 'left', cursor: 'default', zIndex: 120}}><AnnotationNote note={note.note} html={note.html} /></div>;
}
