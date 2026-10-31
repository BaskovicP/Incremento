import {useSyncExternalStore} from 'react';
import AnnotationNote from './AnnotationNote.jsx';

export default function PdfHighlightTooltip({tooltip}) {
  const note = useSyncExternalStore(tooltip.subscribe, tooltip.getSnapshot);
  if (!note) return null;
  return <div role="tooltip" style={{position: 'fixed', left: note.x + 14, top: note.y + 16,
    maxWidth: 280, maxHeight: 'min(320px, 60vh)', overflow: 'hidden', padding: '8px 10px', background: 'rgba(20,20,20,0.96)',
    border: '1px solid rgba(147,197,253,0.45)', borderRadius: 6, color: 'rgb(219,234,254)',
    fontSize: 12, lineHeight: 1.4, boxShadow: '0 8px 18px rgba(0,0,0,0.35)',
    pointerEvents: 'none', zIndex: 120}}><AnnotationNote note={note.note} html={note.html} /></div>;
}
