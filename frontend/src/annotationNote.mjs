import {normalizeExternalHttpUrl} from './pdfLinks.mjs';

const tags = new Set(['p', 'br', 'b', 'i', 'u', 's', 'ul', 'ol', 'li', 'a']);
const entities = {'&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#x27;': "'"};
const decode = text => text.replace(/&(?:amp|lt|gt|quot|#x27);/g, value => entities[value]);

/** Parse only our canonical grammar into inert React data, never live HTML. */
export function annotationNoteTree(note, html) {
  const markup = String(html || '');
  if (!markup || markup.length > 262144) return null;
  const root = {children: []}, stack = [root];
  let plain = '';
  for (const token of markup.match(/<[^>]*>|[^<]+|</g) || []) {
    if (!token.startsWith('<')) {
      const text = decode(token);
      stack.at(-1).children.push(text);
      plain += text;
      continue;
    }
    const closing = /^<\/(\w+)>$/.exec(token);
    if (closing) {
      if (stack.length === 1 || stack.at(-1).tag !== closing[1]) return null;
      if (closing[1] === 'p' || closing[1] === 'li') plain += '\n';
      stack.pop();
      continue;
    }
    const opening = /^<(\w+)(?: href="([^"]*)")?>$/.exec(token);
    if (!opening || !tags.has(opening[1]) || stack.length > 64) return null;
    const tag = opening[1], node = {tag, children: []};
    if (tag === 'a') {
      node.href = normalizeExternalHttpUrl(decode(opening[2] || ''));
      if (!node.href) return null;
    } else if (opening[2] !== undefined) return null;
    stack.at(-1).children.push(node);
    if (tag === 'br') plain += '\n';
    else stack.push(node);
  }
  if (stack.length !== 1 || plain.replace(/\u00a0/g, ' ').trim() !== String(note || '').trim()) return null;
  return root.children;
}
