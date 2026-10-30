import {useEffect, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import {createPdfPageLinks} from './pdfPageLinks.mjs';

/** Keep the bridge alive when responsive toolbar buttons mount or unmount. */
export function usePdfPageLinks({cardId, page, generation, enabled = true, onCommand}) {
  const [view, setView] = useState({links: [], loading: false, error: false});
  const send = useRef(onCommand);
  send.current = onCommand;
  const model = useRef(null);
  if (!model.current) model.current = createPdfPageLinks(message => send.current(message), setView);
  useEffect(() => {
    model.current.start(enabled ? cardId : 0, page, generation);
    return () => model.current.close();
  }, [cardId, page, generation, enabled]);
  useEffect(() => {
    window.incrementoReceivePdfPageLinks = data => model.current.receive(data);
    window.incrementoRefreshPdfPageLinks = () => model.current.refresh();
    return () => {
      delete window.incrementoReceivePdfPageLinks;
      delete window.incrementoRefreshPdfPageLinks;
    };
  }, []);
  // Hide old destinations before the next page's request effect runs.
  const current = enabled && view.cardId === cardId && view.page === page && view.generation === generation;
  return {cardId, page, generation, enabled, links: current ? view.links : [],
    loading: !current || view.loading, error: current && view.error,
    create: () => model.current.create(), manage: () => model.current.manage(),
    recordings: () => model.current.recordings(), linkRecording: () => model.current.linkRecording(),
    remove: row => model.current.remove(row),
    jump: (row, mode) => model.current.jump(row, mode)};
}

/** A compact toolbar button; its dismissible panel never changes page geometry. */
export default function PdfPageLinks({linksState, tr}) {
  const {cardId, page, generation, enabled, links, loading, error, create, manage, jump, remove, recordings, linkRecording} = linksState;
  const [openedFor, setOpenedFor] = useState(null);
  const root = useRef(null), trigger = useRef(null), panel = useRef(null);
  const key = `${cardId}:${page}:${generation}`;
  const expanded = enabled && openedFor === key;
  const close = () => {setOpenedFor(null); trigger.current?.focus();};
  useEffect(() => {setOpenedFor(null);}, [key, enabled]);
  useEffect(() => {
    if (!expanded) return;
    const outside = event => {
      if (!root.current?.contains(event.target) && !panel.current?.contains(event.target)) setOpenedFor(null);
    };
    const escape = event => {
      if (event.key !== 'Escape') return;
      event.preventDefault(); event.stopPropagation();
      setOpenedFor(null); trigger.current?.focus();
    };
    window.addEventListener('pointerdown', outside, true);
    window.addEventListener('keydown', escape, true);
    return () => {
      window.removeEventListener('pointerdown', outside, true);
      window.removeEventListener('keydown', escape, true);
    };
  }, [expanded]);
  const act = command => {close(); command();};
  return <span ref={root} data-pdf-page-links="true" style={{display: 'contents'}}>
    <style>{`[data-pdf-page-links] button:focus-visible {outline: 3px solid #93c5fd; outline-offset: 2px;}`}</style>
    <button ref={trigger} type="button" disabled={!enabled} aria-label={tr('reader_page_links')}
      aria-haspopup="dialog" aria-expanded={!!expanded} aria-controls={expanded ? 'pdf-page-links-panel' : undefined}
      onClick={() => setOpenedFor(expanded ? null : key)}>
      {tr('reader_page_links')}{links.length > 0 ? ` (${links.length})` : ''}
    </button>
    {expanded && createPortal(<section ref={panel} id="pdf-page-links-panel" data-pdf-page-links="true"
      role="dialog" aria-label={tr('reader_page_links')}
      style={{position: 'fixed', bottom: 'calc(var(--pdf-controls-height, 58px) + 6px)', left: 8, zIndex: 60,
        width: 'min(520px, calc(100vw - 16px))', boxSizing: 'border-box',
        maxHeight: 'min(320px, calc(100vh - var(--pdf-controls-height, 58px) - 16px))',
        overflow: 'auto', background: '#27272a', color: '#f3f7ff', border: '1px solid #555',
        borderRadius: 8, boxShadow: '0 -3px 12px #0006', padding: 10, fontSize: 13}}>
      <div style={{display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginBottom: 8}}>
        <strong style={{whiteSpace: 'nowrap'}}>{tr('reader_page_links')}</strong>
        <button type="button" onClick={() => act(create)}>{tr('reader_link_this_page')}</button>
        <button type="button" onClick={() => act(manage)}>{tr('reader_reference_links')}</button>
        <button type="button" onClick={() => act(linkRecording)}>{tr('study_link_recording')}</button>
        <button type="button" onClick={() => act(recordings)}>{tr('study_resources')}</button>
        <button type="button" aria-label={tr('reader_close')} onClick={close} style={{marginLeft: 'auto'}}>×</button>
      </div>
      <div style={{display: 'flex', flexDirection: 'column', gap: 6}} aria-live="polite">
        {links.map(row => {
          const label = tr('reader_pdf_copied_label', {title: row.title, page: row.target_page});
          return <div key={row.id + ':' + row.direction} style={{display: 'flex', flexWrap: 'wrap', gap: 4, minWidth: 0}}>
            <button type="button" disabled={!row.available} title={tr('reader_jump_to_linked_page')}
              aria-label={tr('reader_jump_to_linked_page') + ': ' + label}
              style={{flex: '1 1 220px', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', textAlign: 'left', whiteSpace: 'nowrap',
                padding: '6px 10px', border: '1px solid #6ca9e8', borderRadius: 6, cursor: 'pointer'}}
              onClick={() => act(() => jump(row))}>↗ {label}</button>
            <button type="button" disabled={!row.available} title={tr('reader_reference_pin')}
              aria-label={tr('reader_reference_pin') + ': ' + label}
              style={{flexShrink: 0, whiteSpace: 'nowrap'}}
              onClick={() => act(() => jump(row, 'beside'))}>{tr('reader_reference_pin')}</button>
            <button type="button" aria-label={tr('reader_reference_remove') + ': ' + label}
              onClick={() => act(() => remove(row))}>{tr('reader_reference_remove')}</button>
          </div>;
        })}
        {!links.length && <span role="status" style={{color: '#cbd8e9'}}>
          {tr(error ? 'reader_reference_unavailable' : loading ? 'reader_link_preview_loading' : 'reader_page_links_empty')}
        </span>}
      </div>
    </section>, document.body)}
  </span>;
}
