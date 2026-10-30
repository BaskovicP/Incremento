import {useEffect, useRef, useState, useSyncExternalStore} from 'react';
import { INACTIVE_PDF_SNAPSHOT_MODE } from './pdfSnapshot.mjs';
import {attachPdfLinkPreview, createPdfPreviewRenderer, pdfLinkPreviewLayout} from './pdfLinkPreview.mjs';

export default function PdfLinkPreview({containerRef, pdfDocRef, links, tlLeft, sourcePage,
  documentToken, disabled, snapshotMode = INACTIVE_PDF_SNAPSHOT_MODE, maxPage, pageLabels, appearance, tr, zoom, onZoom,
  size = null, onResize}) {
  const capturing = useSyncExternalStore(snapshotMode.subscribe, snapshotMode.getSnapshot);
  const unavailable = disabled || capturing;
  const [preview, setPreview] = useState(null);
  const popupRef = useRef(null);
  const contentRef = useRef(null);
  const rendererRef = useRef(null);
  const zoomRef = useRef(zoom);
  zoomRef.current = zoom;
  const onResizeRef = useRef(onResize);
  onResizeRef.current = onResize;
  useEffect(() => {
    const container = containerRef.current, popup = popupRef.current;
    const doc = pdfDocRef.current;
    if (!container || !popup || !doc || unavailable || !links.length) return;
    const renderer = createPdfPreviewRenderer({createCanvas: () => document.createElement('canvas'),
      onChange: setPreview, pixelRatio: window.devicePixelRatio, zoom: zoomRef.current});
    rendererRef.current = renderer;
    const detach = attachPdfLinkPreview({container, popup, host: window, links, tlLeft, doc,
      preview: renderer, maxPage, onResize: value => onResizeRef.current?.(value)});
    return () => {detach(); renderer.dispose(); rendererRef.current = null;};
  }, [containerRef, pdfDocRef, links, tlLeft, sourcePage, documentToken, unavailable, maxPage]);

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

  const {width, height, left, top, maxWidth, maxHeight} = pdfLinkPreviewLayout(
    size, preview?.anchor || {x: 0, y: 0}, window.innerWidth, window.innerHeight);
  const targetPage = preview?.link?.targetPage;
  const pageLabel = pageLabels?.[targetPage - 1] || targetPage;
  return (
    <aside ref={popupRef} id="pdf-link-preview" role="dialog" aria-modal="false"
      aria-label={tr('reader_link_preview')}
      style={{display: preview && !unavailable ? 'flex' : 'none', flexDirection: 'column', position: 'fixed',
        left, top, width, height, minWidth: Math.min(280, maxWidth), minHeight: Math.min(160, maxHeight),
        maxWidth, maxHeight, resize: 'both', boxSizing: 'border-box', zIndex: 180,
        textAlign: 'left', background: '#252525', color: '#f4f4f5', border: '1px solid #777',
        borderRadius: 8, boxShadow: '0 8px 28px rgba(0,0,0,0.45)', overflow: 'hidden'}}>
      <div style={{display: 'flex', flexShrink: 0, alignItems: 'center', gap: 12, padding: '8px 12px', fontSize: 13}}>
        <strong style={{flex: 1}}>{tr('reader_link_preview')}</strong>
        <span>{targetPage ? tr('reader_page_number', {page: pageLabel}) : ''}</span>
        <button type="button" aria-label={tr('reader_close')} onClick={() => rendererRef.current?.clear()}
          style={{padding: '2px 7px'}}>×</button>
      </div>
      <div style={{position: 'relative', minHeight: 48, flex: 1,
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
      <div style={{display: 'flex', flexShrink: 0, flexWrap: 'wrap', alignItems: 'center', gap: 10,
        padding: '7px 20px 12px 12px', fontSize: 11, color: '#d4d4d8'}}>
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
