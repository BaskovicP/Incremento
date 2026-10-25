import {useEffect, useState} from 'react';
import PdfViewer from './PdfViewer.jsx';
import {sharedPdfReaderStartup} from './sharedPdfReader.mjs';
import {createReaderLanguage} from './i18n.mjs';

/** The side pane mounts the actual reader; only its Python bridge and scope differ. */
export default function SharedReferencePdfViewer() {
  const [config, setConfig] = useState(null);
  const [generation, setGeneration] = useState(0);
  useEffect(() => {
    const start = data => {
      const {pending, highlights} = sharedPdfReaderStartup(data);
      window._pdfWorkerSrc = data.worker;
      window._pdfFileUrl = data.url;
      window._incPdfByteRange = data.byte_range || null;
      window._incPdfHighlights = highlights;
      window._pdfNativeHighlightsVisible = data.native_highlights_visible === true;
      window._incPdfPending = pending;
      setConfig(data);
      setGeneration(value => value + 1);
    };
    window.incrementoReferenceStart = start;
    window.incrementoReferenceReload = start;
    if (window._incReferencePending) {
      start(window._incReferencePending);
      window._incReferencePending = null;
    }
    return () => {delete window.incrementoReferenceStart; delete window.incrementoReferenceReload;};
  }, []);
  if (!config) return null;
  const tr = createReaderLanguage(config.locale, config.custom_language).tr;
  const send = action => window.incrementoReferenceCommand?.({action});
  return <PdfViewer key={generation} readingOnly referenceControls={({ready}) => <>
    <button disabled={!ready} onMouseDown={event => event.preventDefault()}
      onClick={() => send('copy')}>{tr('reader_copy_link_to_place')}</button>
    <button onClick={() => send('pin')}>{tr('reader_reference_pin')}</button>
    <button disabled={!ready} onClick={() => send('open')}>{tr('reader_reference_open')}</button>
    <button onClick={() => send('close')}>{tr('reader_close')}</button>
  </>} />;
}
