import { createRoot } from 'react-dom/client';
import PdfViewer from './PdfViewer.jsx';
import ReferencePdfViewer from './ReferencePdfViewer.jsx';
import SharedReferencePdfViewer from './SharedReferencePdfViewer.jsx';

const container = document.getElementById('pdf-react-root');
if (container) {
  const reference = new URLSearchParams(window.location.search).get('reference');
  createRoot(container).render(reference === 'reader' ? <SharedReferencePdfViewer /> : reference === '1' ? <ReferencePdfViewer /> : <PdfViewer />);
}
