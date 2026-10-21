import {useEffect, useRef, useState} from 'react';
import {attachPdfLinkPreview, createPdfPreviewRenderer} from './pdfLinkPreview.mjs';

export default function PdfLinkPreview({containerRef, pdfDocRef, links, tlLeft, sourcePage,
  documentToken, disabled, maxPage, pageLabels, appearance, tr, zoom, onZoom}) {
  const [preview, setPreview] = useState(null);
  const popupRef = useRef(null);
  const contentRef = useRef(null);
  const rendererRef = useRef(null);
  const zoomRef = useRef(zoom);
  zoomRef.current = zoom;
  useEffect(() => {
    const container = containerRef.current, popup = popupRef.current;
    const doc = pdfDocRef.current;
    if (!container || !popup || !doc || disabled || !links.length) return;
    const renderer = createPdfPreviewRenderer({createCanvas: () => document.createElement('canvas'),
      onChange: setPreview, pixelRatio: window.devicePixelRatio, zoom: zoomRef.current});
    rendererRef.current = renderer;
    const detach = attachPdfLinkPreview({container, popup, host: window, links, tlLeft, doc,
      preview: renderer, maxPage});
    return () => {detach(); renderer.dispose(); rendererRef.current = null;};
  }, [containerRef, pdfDocRef, links, tlLeft, sourcePage, documentToken, disabled, maxPage]);

  useEffect(() => {void rendererRef.current?.setZoom(zoom);}, [zoom]);

  const canvas = preview?.canvas;
  useEffect(() => {
    if (!canvas || !contentRef.current) return;
    canvas.style.width = preview.region.width + 'px';
    canvas.style.height = preview.region.height + 'px';
    contentRef.current.replaceChildren(canvas);
    contentRef.current.scrollLeft = preview.region.scrollLeft;
    contentRef.current.scrollTop = 0;
  }, [canvas]); // Accessible text updates must not reset the reader's preview scroll.

  useEffect(() => {
    if (!canvas) return;
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', preview.text || tr('reader_link_preview'));
    canvas.style.filter = appearance.filter;
  }, [canvas, preview?.text, appearance.filter, tr]);

  const width = Math.max(1, Math.min(560, window.innerWidth - 24));
  const bodyHeight = Math.max(40, Math.min(260, window.innerHeight - 120));
  const height = bodyHeight + 100;
  const anchor = preview?.anchor || {x: 0, y: 0};
  const left = Math.max(12, Math.min(anchor.x - 24, window.innerWidth - width - 12));
  const top = anchor.y + height + 20 < window.innerHeight
    ? anchor.y + 20 : Math.max(12, anchor.y - height - 20);
  const targetPage = preview?.link?.targetPage;
  const pageLabel = pageLabels?.[targetPage - 1] || targetPage;
  return (
    <aside ref={popupRef} id="pdf-link-preview" role="dialog" aria-modal="false"
      aria-label={tr('reader_link_preview')}
      style={{display: preview ? 'flex' : 'none', flexDirection: 'column', position: 'fixed',
        left, top, width, maxHeight: Math.max(40, window.innerHeight - top - 12), zIndex: 180,
        textAlign: 'left', background: '#252525', color: '#f4f4f5', border: '1px solid #777',
        borderRadius: 8, boxShadow: '0 8px 28px rgba(0,0,0,0.45)', overflow: 'hidden'}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 12, padding: '8px 12px', fontSize: 13}}>
        <strong style={{flex: 1}}>{tr('reader_link_preview')}</strong>
        <span>{targetPage ? tr('reader_page_number', {page: pageLabel}) : ''}</span>
        <button type="button" aria-label={tr('reader_close')} onClick={() => rendererRef.current?.clear()}
          style={{padding: '2px 7px'}}>×</button>
      </div>
      <div style={{position: 'relative', minHeight: 48, height: bodyHeight, flexShrink: 1,
        background: appearance.background, color: '#f4f4f5'}}>
        <div ref={contentRef} tabIndex={preview?.status === 'ready' ? 0 : -1}
          aria-label={tr('reader_link_preview')} style={{height: '100%', overflow: 'auto',
            overscrollBehavior: 'contain',
            display: preview?.status === 'ready' ? 'block' : 'none'}} />
        {preview && preview.status !== 'ready' && <div role="status"
          style={{padding: 16, background: '#252525', height: '100%', boxSizing: 'border-box'}}>
          {tr(preview.status === 'loading' ? 'reader_link_preview_loading'
            : preview.status === 'limited' ? 'reader_link_preview_limit' : 'reader_link_preview_unavailable')}
        </div>}
      </div>
      <div style={{display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10,
        padding: '7px 12px', fontSize: 11, color: '#d4d4d8'}}>
        <div role="group" aria-label={tr('reader_link_preview_zoom')}
          style={{display: 'flex', alignItems: 'center', gap: 7}}>
          <button type="button" aria-label={tr('reader_zoom_out')} disabled={zoom <= 1}
            onClick={() => onZoom(zoom - 0.25)} style={{padding: '2px 8px'}}>−</button>
          <output aria-live="polite" style={{minWidth: 36, textAlign: 'center'}}>{Math.round(zoom * 100)}%</output>
          <button type="button" aria-label={tr('reader_zoom_in')} disabled={zoom >= 4}
            onClick={() => onZoom(zoom + 0.25)} style={{padding: '2px 8px'}}>+</button>
        </div>
        <span>{tr('reader_link_preview_hint')}</span>
      </div>
    </aside>
  );
}
