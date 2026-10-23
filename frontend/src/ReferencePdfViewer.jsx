import {useEffect, useRef, useState} from 'react';
import {createReferenceReader, referenceRestoreRatio, referenceExcerptItemIndex, referenceScrollSnapshot} from './referencePdfReader.mjs';
import {referenceRenderPlan, referenceActionLocation, referenceSelectionText} from './referencePdfReader.mjs';
import {createReaderLanguage} from './i18n.mjs';
import PdfPageLinks, {usePdfPageLinks} from './PdfPageLinks.jsx';
import {capturePdfDestination, pdfDestinationScrollRatio} from './pdfDestination.mjs';

/** Each Qt view mounts its own app; pinning reparents the view without reloading. */
export default function ReferencePdfViewer() {
  const [config, setConfig] = useState(null);
  const [state, setState] = useState({page: 1, pages: 0, zoom: 1});
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [width, setWidth] = useState(600);
  const [label, setLabel] = useState('');
  const [rendered, setRendered] = useState(null);
  const [pickPending, setPickPending] = useState(false);
  const [chosenSpot, setChosenSpot] = useState(null);
  const [searchRender, setSearchRender] = useState(0);
  const model = useRef(null), host = useRef(null), scroll = useRef(null);
  const initialScroll = useRef(null);
  const initialPoint = useRef(null);
  const renderedPage = useRef(0), pendingExcerpt = useRef('');
  const savedScroll = useRef(0), renderedSize = useRef({width: 0, height: 0});
  if (!model.current) model.current = createReferenceReader(setState);
  const tr = createReaderLanguage(config?.locale || 'en', config?.custom_language).tr;
  const actionLocation = referenceActionLocation(state, rendered);
  const choosing = !!config?.choose_destination;
  const currentSpot = chosenSpot?.page === state.page && chosenSpot?.generation === state.generation ? chosenSpot : null;
  const send = (action, extra = {}) => {
    if (!config) return;
    if (['copy', 'extract', 'open', 'pick'].includes(action) && !actionLocation) return;
    if (pickPending && action !== 'close') return;
    const element = scroll.current;
    const ratio = element && element.scrollHeight > element.clientHeight
      ? element.scrollTop / (element.scrollHeight - element.clientHeight) : 0;
    window.pycmd?.(JSON.stringify({action, page: state.page, zoom: state.zoom, scroll_ratio: ratio, ...extra}));
  };
  const pageLinksState = usePdfPageLinks({cardId: config?.card_id || 0, page: state.page,
    generation: state.generation || 1, enabled: !choosing && !!actionLocation && !!config?.card_id,
    onCommand: message => send('page_links', {...message,
      page_y: capturePdfDestination(scroll.current, host.current, window.getSelection())?.page_y})});

  useEffect(() => {
    const start = data => {
      setConfig(data); initialScroll.current = data.scroll_ratio || 0;
      initialPoint.current = typeof data.page_y === 'number' && data.page_y >= 0 && data.page_y <= 1 ? data.page_y : null;
      setChosenSpot(null); setPickPending(false);
      setRendered(null); setLabel(''); setStatus('reader_link_preview_loading');
      pendingExcerpt.current = data.excerpt || '';
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = data.worker;
      model.current.load(window.pdfjsLib, data.url, data.page, data.max_page)
        .catch(() => setStatus('reader_load_error'));
    };
    window.incrementoReferenceStart = start;
    window.incrementoReferencePickPending = setPickPending;
    if (window._incReferencePending) {start(window._incReferencePending); window._incReferencePending = null;}
    return () => {delete window.incrementoReferenceStart; delete window.incrementoReferencePickPending; model.current.close();};
  }, []);

  useEffect(() => {
    if (!scroll.current) return;
    const observer = new ResizeObserver(entries => setWidth(Math.max(100, entries[0].contentRect.width - 24)));
    observer.observe(scroll.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const doc = model.current.document();
    setRendered(null);
    if (!doc || !host.current) {host.current?.replaceChildren(); return;}
    setStatus('reader_link_preview_loading');
    let retired = false, renderTask, textTask;
    const restoreRatio = referenceRestoreRatio({page: state.page, renderedPage: renderedPage.current,
      ratio: savedScroll.current,
      initial: initialScroll.current});
    const canvas = document.createElement('canvas'), text = document.createElement('div');
    doc.getPage(state.page).then(async page => {
      if (retired) return;
      const base = page.getViewport({scale: 1});
      const plan = referenceRenderPlan(base, width, state.zoom, window.devicePixelRatio || 1);
      const {scale, pixels} = plan;
      const viewport = page.getViewport({scale});
      canvas.width = plan.canvasWidth; canvas.height = plan.canvasHeight;
      canvas.style.width = viewport.width + 'px'; canvas.style.height = viewport.height + 'px';
      renderTask = page.render({canvasContext: canvas.getContext('2d'), viewport,
        transform: [pixels, 0, 0, pixels, 0, 0]});
      await renderTask.promise;
      if (retired) return;
      const wrapper = host.current;
      wrapper.style.width = viewport.width + 'px'; wrapper.style.height = viewport.height + 'px';
      text.className = 'textLayer';
      text.id = 'pdf-text-layer';
      text.style.cssText = `position:absolute;inset:0;width:${viewport.width}px;height:${viewport.height}px;--scale-factor:${scale}`;
      wrapper.replaceChildren(canvas, text);
      textTask = new window.pdfjsLib.TextLayer({textContentSource: page.streamTextContent(), container: text, viewport});
      textTask.render().then(async () => {
        if (retired) return;
        setRendered({page: state.page, zoom: state.zoom, generation: state.generation});
        if (!pendingExcerpt.current) return;
        const content = await page.getTextContent();
        if (retired) return;
        const index = referenceExcerptItemIndex(content.items, pendingExcerpt.current);
        pendingExcerpt.current = '';
        const span = textTask.textDivs[index];
        if (span) {
          const top = span.getBoundingClientRect().top - scroll.current.getBoundingClientRect().top;
          scroll.current.scrollTop += top - 40;
        }
      }).catch(() => {});
      const ratio = initialPoint.current == null ? restoreRatio
        : pdfDestinationScrollRatio(initialPoint.current, viewport.height, scroll.current.clientHeight);
      scroll.current.scrollTop = ratio * Math.max(0, scroll.current.scrollHeight - scroll.current.clientHeight);
      savedScroll.current = ratio;
      renderedSize.current = {width: scroll.current.clientWidth, height: scroll.current.clientHeight};
      initialScroll.current = null;
      initialPoint.current = null;
      renderedPage.current = state.page;
      setStatus('');
    }).catch(() => {if (!retired) setStatus('reader_render_error');});
    doc.getPageLabels().then(labels => {if (!retired) setLabel(labels?.[state.page - 1] || String(state.page));}).catch(() => {});
    return () => {retired = true; renderTask?.cancel(); textTask?.cancel();};
  }, [state.page, state.pages, state.zoom, state.generation, width, searchRender]);

  useEffect(() => {
    if (!choosing || !currentSpot || !actionLocation || !host.current) return;
    const marker = document.createElement('div');
    marker.dataset.pdfDestination = String(currentSpot.page_y);
    marker.style.cssText = `position:absolute;left:0;right:0;top:${currentSpot.page_y * 100}%;border-top:2px solid #fbbf24;pointer-events:none;user-select:none;z-index:5;color:#181818;font-size:12px`;
    const label = document.createElement('span');
    label.textContent = tr('reader_destination_marker');
    label.style.cssText = 'position:absolute;left:0;bottom:2px;background:#fbbf24;padding:2px 6px';
    marker.appendChild(label);
    host.current.appendChild(marker);
    return () => marker.remove();
  }, [choosing, currentSpot, rendered]);

  useEffect(() => {
    if (config) send('position');
  }, [config, state.page]);

  useEffect(() => {
    window.incrementoHandleExtractShortcut = index => {
      if (choosing) return;
      const text = referenceSelectionText(window.getSelection(), host.current?.querySelector('#pdf-text-layer'));
      if (text) send('extract', {index, text});
    };
    const handler = event => {
      if (event.key === 'Escape') send('close');
      if ((event.metaKey || event.ctrlKey) && /^[1-4]$/.test(event.key)) {
        event.preventDefault(); window.incrementoHandleExtractShortcut(Number(event.key) - 1); return;
      }
      if (['INPUT', 'TEXTAREA'].includes(event.target.tagName)) return;
      if (pickPending) return;
      if (event.key === 'ArrowRight') {event.preventDefault(); model.current.navigate(state.page + 1);}
      if (event.key === 'ArrowLeft') {event.preventDefault(); model.current.navigate(state.page - 1);}
    };
    window.addEventListener('keydown', handler);
    return () => {window.removeEventListener('keydown', handler); delete window.incrementoHandleExtractShortcut;};
  });

  const confirmDestination = () => {
    const selection = window.getSelection();
    const point = capturePdfDestination(scroll.current, host.current, selection);
    if (!point) return;
    const selected = referenceSelectionText(selection, host.current?.querySelector('#pdf-text-layer'));
    send('pick', {...point, page_y: selected ? point.page_y : currentSpot?.page_y ?? point.page_y});
  };

  return <div style={{position: 'fixed', inset: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', color: '#eee', background: '#252525'}}>
    <nav aria-label={tr('reader_reference_title')} style={{display: 'flex', gap: 6, padding: 8, flexWrap: 'wrap', alignItems: 'center'}}>
      <strong>{config?.title || tr('reader_reference_title')}</strong>
      <button onClick={() => model.current.back()} disabled={pickPending || !state.canBack}>{tr('reader_jump_back')}</button>
      <button aria-label={tr('reader_previous_page')} disabled={pickPending || state.page <= 1} onClick={() => model.current.navigate(state.page - 1)}>←</button>
      <label>{tr('reader_page_number', {page: label || state.page})} <input type="number" min="1" max={state.pages} value={state.page}
        disabled={pickPending}
        aria-label={tr('reader_reference_page')} style={{width: 60}}
        onChange={event => model.current.navigate(Number(event.target.value))} /> / {state.pages}</label>
      <button aria-label={tr('reader_next_page')} disabled={pickPending || state.page >= state.pages} onClick={() => model.current.navigate(state.page + 1)}>→</button>
      <button aria-label={tr('reader_zoom_out')} disabled={pickPending} onClick={() => {initialScroll.current = scroll.current.scrollTop / Math.max(1, scroll.current.scrollHeight - scroll.current.clientHeight); model.current.setZoom(state.zoom - .25);}}>−</button>
      <span>{Math.round(state.zoom * 100)}%</span>
      <button aria-label={tr('reader_zoom_in')} disabled={pickPending} onClick={() => {initialScroll.current = scroll.current.scrollTop / Math.max(1, scroll.current.scrollHeight - scroll.current.clientHeight); model.current.setZoom(state.zoom + .25);}}>+</button>
      {choosing ? <>
        <button disabled={pickPending || !actionLocation} onMouseDown={event => event.preventDefault()}
          onClick={confirmDestination}>{tr(pickPending ? 'reader_destination_saving' : 'reader_destination_confirm')}</button>
        <button onClick={() => send('close')}>{tr('reader_cancel')}</button>
      </> : null}
    </nav>
    {choosing && <p style={{margin: '0 8px 8px', color: '#d7e5f8'}}>{tr('reader_destination_hint')}</p>}
    <form style={{display: 'flex', gap: 8, padding: '0 8px 8px'}} onSubmit={async event => {
      event.preventDefault(); setStatus('reader_reference_searching');
      if (pickPending) return;
      try {
        const found = await model.current.find(query);
        if (found !== undefined) setStatus(found ? '' : 'reader_reference_no_match');
        if (found) {pendingExcerpt.current = query; setSearchRender(value => value + 1);}
      }
      catch (_) {setStatus('reader_page_error');}
    }}>
      <input aria-label={tr('reader_reference_search')} disabled={pickPending} value={query} maxLength={200} onChange={event => setQuery(event.target.value)} />
      <button disabled={pickPending}>{tr('reader_reference_search')}</button>
      <span role="status">{status ? tr(status) : ''}</span>
    </form>
    <div ref={scroll} tabIndex="0" aria-label={tr('reader_reference_title')}
      onScroll={event => {
        const el = event.currentTarget;
        savedScroll.current = referenceScrollSnapshot({width: el.clientWidth, height: el.clientHeight,
          top: el.scrollTop, extent: el.scrollHeight - el.clientHeight}, renderedSize.current, savedScroll.current);
      }} style={{flex: 1, minHeight: 0, overflow: 'auto', padding: 12}}>
      <div ref={host} onPointerUp={event => {
        if (!choosing || !actionLocation || pickPending || event.button !== 0) return;
        const point = capturePdfDestination(scroll.current, host.current, window.getSelection(), event.clientY);
        if (point) setChosenSpot({...point, page: state.page, generation: state.generation});
      }} style={{position: 'relative', margin: '0 auto', background: 'white'}} />
    </div>
    {!choosing && <nav role="toolbar" aria-label={tr('reader_pdf_controls')}
      style={{position: 'relative', display: 'flex', alignItems: 'center', flexWrap: 'wrap', flexShrink: 0,
        gap: 6, padding: 8, borderTop: '1px solid #555'}}>
      <PdfPageLinks linksState={pageLinksState} tr={tr} />
      <button disabled={!actionLocation} onMouseDown={event => event.preventDefault()} onClick={() => send('copy')}>{tr('reader_copy_link_to_place')}</button>
      <button disabled={!actionLocation} onMouseDown={event => event.preventDefault()} onClick={() => window.incrementoHandleExtractShortcut(0)}>{tr('reader_extract')}</button>
      <button onClick={() => send('pin')}>{tr('reader_reference_pin')}</button>
      <button disabled={!actionLocation} onClick={() => send('open')}>{tr('reader_reference_open')}</button>
      <button onClick={() => send('close')}>{tr('reader_close')}</button>
    </nav>}
  </div>;
}
