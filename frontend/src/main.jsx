import { createRoot } from 'react-dom/client';
import PdfViewer from './PdfViewer.jsx';
import ReferencePdfViewer from './ReferencePdfViewer.jsx';

const container = document.getElementById('pdf-react-root');
if (container) {
  const reference = new URLSearchParams(window.location.search).get('reference') === '1';
  createRoot(container).render(reference ? <ReferencePdfViewer /> : <PdfViewer />);
}
