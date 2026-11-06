import {useEffect, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import {createPdfPageLinks} from './pdfPageLinks.mjs';
import {pdfExcerptRange} from './pdfExcerptReveal.mjs';

/** Keep the bridge alive when responsive toolbar buttons mount or unmount. */
export function usePdfPageLinks({cardId, page, generation, enabled = true, onCommand, captureSource}) {
  const [view, setView] = useState({links: [], writing: [], loading: false, error: false});
  const send = useRef(onCommand);
  send.current = onCommand;
  const capture = useRef(captureSource), source = useRef(null);
  capture.current = captureSource;
  const model = useRef(null);
  if (!model.current) model.current = createPdfPageLinks(message => send.current({ ...message,
    ...(['create', 'manage'].includes(message.operation) && source.current ? {passage: source.current} : {})}), setView);
  useEffect(() => {
    model.current.start(enabled ? cardId : 0, page, generation);
    source.current = null;
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
    writing: current ? view.writing : [], openWriting: row => model.current.openWriting(row),
    loading: !current || view.loading, error: current && view.error,
    create: () => model.current.create(), manage: () => model.current.manage(),
    rememberSelection: () => {source.current = capture.current?.() || null;},
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
      onMouseDown={event => {linksState.rememberSelection?.(); event.preventDefault();}}
      aria-haspopup="dialog" aria-expanded={!!expanded} aria-controls={expanded ? 'pdf-page-links-panel' : undefined}
      onClick={() => setOpenedFor(expanded ? null : key)}>
      {tr('reader_page_links')}{links.length > 0 ? ` (${links.length})` : ''}
    </button>
    {expanded && createPortal(<section ref={panel} id="pdf-page-links-panel" data-pdf-page-links="true"
      role="dialog" aria-label={tr('reader_page_links')} onMouseDown={event => {
        if (event.target.closest('button')) event.preventDefault();
      }}
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

/** A real margin next to the canvas; source text is never covered by backlinks. */
export function PdfWritingMargin({linksState, tr, textLayer, wrapper, renderInfo}) {
  const {writing = [], openWriting} = linksState;
  const [positions, setPositions] = useState({});
  useEffect(() => {
    if (!writing.length || !wrapper.current) return;
    const top = wrapper.current.getBoundingClientRect().top;
    const anchors = writing.map((row, index) => {
      const range = renderInfo?.textReady && pdfExcerptRange(textLayer.current, row.quote);
      const rect = range && Array.from(range.getClientRects()).find(rect => rect.width && rect.height);
      return {anchor: row.anchor, y: rect ? Math.max(2, rect.top - top) : 4 + index * 26};
    }).sort((a, b) => a.y - b.y);
    let bottom = -26;
    const next = {};
    for (const {anchor, y} of anchors) {
      next[anchor] = Math.max(y, bottom + 2);
      bottom = next[anchor] + 24;
    }
    setPositions(next);
  }, [writing, renderInfo, textLayer, wrapper]);
  if (!writing.length) return null;
  return <aside id="pdf-writing-margin" aria-label={tr('writing_excerpt_backlinks')}
    style={{flex: '0 0 32px', width: 32, alignSelf: 'stretch', position: 'relative'}}>
    <style>{`#pdf-writing-margin button:focus-visible {outline: 3px solid #93c5fd; outline-offset: 1px;}`}</style>
    {writing.map((row, index) => <button type="button" key={row.anchor} onClick={() => openWriting(row)}
      aria-label={tr('writing_excerpt_backlinks') + ': ' + row.title}
      title={row.title + '\n' + row.quote.slice(0, 180)}
      style={{position: 'absolute', left: 4, top: positions[row.anchor] ?? 4 + index * 26,
        width: 24, height: 24, padding: 0, borderRadius: 4, fontSize: 17, lineHeight: '22px',
        background: '#292b31', color: '#c4d8ff', border: '1px solid #687795', cursor: 'pointer'}}>
      ↗
    </button>)}
  </aside>;
}
