const MAX_EXTERNAL_URL_CHARS = 4096;
const PDFJS_LINK_ANNOTATION_TYPE = 2;


export function normalizeExternalHttpUrl(rawUrl) {
  const candidate = String(rawUrl || '').trim();
  if (!candidate || candidate.length > MAX_EXTERNAL_URL_CHARS) return null;
  if (/\s/.test(candidate) || candidate.includes('\\')) return null;
  try {
    const parsed = new URL(candidate);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return null;
    if (!parsed.hostname || parsed.username || parsed.password) return null;
  } catch (_err) {
    return null;
  }
  return candidate;
}


function viewportRect(annotation, viewport) {
  if (!Array.isArray(annotation?.rect) || annotation.rect.length < 4) return null;
  if (!viewport || typeof viewport.convertToViewportRectangle !== 'function') return null;
  let converted;
  try {
    converted = viewport.convertToViewportRectangle(annotation.rect);
  } catch (_err) {
    return null;
  }
  if (!Array.isArray(converted) || converted.length < 4) return null;
  const numbers = converted.slice(0, 4).map(Number);
  if (!numbers.every(Number.isFinite)) return null;
  const [x1, y1, x2, y2] = numbers;
  const left = Math.min(x1, x2);
  const top = Math.min(y1, y2);
  const width = Math.abs(x2 - x1);
  const height = Math.abs(y2 - y1);
  if (width <= 0 || height <= 0) return null;
  return { left, top, width, height };
}


async function destinationPage(pdfDocument, rawDestination) {
  if (!pdfDocument || rawDestination == null) return null;
  try {
    const destination = typeof rawDestination === 'string'
      ? await pdfDocument.getDestination(rawDestination)
      : rawDestination;
    if (!Array.isArray(destination) || destination.length === 0) return null;
    const pageReference = destination[0];
    const pageIndex = Number.isInteger(pageReference)
      ? pageReference
      : await pdfDocument.getPageIndex(pageReference);
    const targetPage = Number(pageIndex) + 1;
    const totalPages = Number(pdfDocument.numPages || 0);
    if (!Number.isInteger(targetPage) || targetPage < 1) return null;
    if (totalPages > 0 && targetPage > totalPages) return null;
    return targetPage;
  } catch (_err) {
    return null;
  }
}


export async function resolvePdfAnnotationLink(annotation, pdfDocument, viewport) {
  const subtype = String(annotation?.subtype || '');
  const isLinkAnnotation = subtype
    ? subtype.toLowerCase() === 'link'
    : Number(annotation?.annotationType) === PDFJS_LINK_ANNOTATION_TYPE;
  if (!isLinkAnnotation) return null;
  const rect = viewportRect(annotation, viewport);
  if (!rect) return null;

  const externalUrl = normalizeExternalHttpUrl(annotation?.url);
  if (externalUrl) {
    return {
      kind: 'external',
      url: externalUrl,
      label: String(annotation?.title || annotation?.contents || externalUrl).slice(0, 240),
      ...rect,
    };
  }

  const targetPage = await destinationPage(pdfDocument, annotation?.dest);
  if (targetPage == null) return null;
  return {
    kind: 'internal',
    targetPage,
    label: String(annotation?.title || annotation?.contents || `Go to page ${targetPage}`).slice(0, 240),
    ...rect,
  };
}
