import { createRoot } from 'react-dom/client';
import PdfViewer from './PdfViewer.jsx';

const container = document.getElementById('pdf-react-root');
if (container) {
  createRoot(container).render(<PdfViewer />);
}
