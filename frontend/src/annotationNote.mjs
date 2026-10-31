import {normalizeExternalHttpUrl} from './pdfLinks.mjs';

const tags = new Set(['p', 'br', 'b', 'i', 'u', 's', 'ul', 'ol', 'li', 'a']);
const entities = {'&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#x27;': "'"};
const decode = text => text.replace(/&(?:amp|lt|gt|quot|#x27);/g, value => entities[value]);

export const hasAnnotationNote = highlight => Boolean(String(highlight?.note || '').trim()
  || String(highlight?.note_html || '').includes('<img '));

function imageNode(token) {
  const match = /^<img src="(data:image\/(png|jpeg);base64,([A-Za-z0-9+/]+={0,2}))" width="([1-9]\d{0,2})" height="([1-9]\d{0,2})" alt=""(?: style="float:(left|right)")?>$/.exec(token);
  if (!match || match[3].length > 109228) return null;
  let data;
  try {data = atob(match[3]);} catch {return null;}
  if (data.length > 81920) return null;
  const byte = index => data.charCodeAt(index);
  const short = index => byte(index) * 256 + byte(index + 1);
  const long = index => short(index) * 65536 + short(index + 2);
  let width = 0, height = 0;
  if (match[2] === 'png' && data.startsWith('\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR')
    && data.length >= 45 && data.endsWith('\x00\x00\x00\x00IEND\xaeB`\x82')) {
    width = long(16); height = long(20);
  } else if (match[2] === 'jpeg' && data.startsWith('\xff\xd8') && data.endsWith('\xff\xd9')) {
    for (let offset = 2; offset + 4 <= data.length;) {
      const size = short(offset + 2), marker = byte(offset + 1);
      if (byte(offset) !== 255 || size < 2 || offset + 2 + size > data.length) break;
      if ((marker === 0xc0 || marker === 0xc2) && size >= 8) {
        height = short(offset + 5); width = short(offset + 7); break;
      }
      offset += size + 2;
    }
  }
  const displayWidth = Number(match[4]), displayHeight = Number(match[5]);
  if (Math.min(width, height) < 1 || Math.max(width, height) > 960 || displayWidth > 640
    || displayHeight > 960) return null;
  return {tag: 'img', src: match[1], width: displayWidth, height: displayHeight,
    ...(match[6] ? {float: match[6]} : {}), children: []};
}

/** Parse only our canonical grammar into inert React data, never live HTML. */
export function annotationNoteTree(note, html) {
  const markup = String(html || '');
  if (!markup || markup.length > 262144) return null;
  const root = {children: []}, stack = [root];
  let plain = '', images = 0;
  for (const token of markup.match(/<[^>]*>|[^<]+|</g) || []) {
    if (!token.startsWith('<')) {
      const text = decode(token);
      stack.at(-1).children.push(text);
      plain += text;
      continue;
    }
    if (token.startsWith('<img ')) {
      const node = imageNode(token);
      if (!node || ++images > 4) return null;
      stack.at(-1).children.push(node);
      continue;
    }
    const closing = /^<\/(\w+)>$/.exec(token);
    if (closing) {
      if (stack.length === 1 || stack.at(-1).tag !== closing[1]) return null;
      if (closing[1] === 'p' || closing[1] === 'li') plain += '\n';
      stack.pop();
      continue;
    }
    const opening = /^<(\w+)(?: href="([^"]*)")?(?: align="(left|center|right)")?>$/.exec(token);
    if (!opening || !tags.has(opening[1]) || stack.length > 64) return null;
    const tag = opening[1], node = {tag, children: []};
    if (opening[3]) {
      if (tag !== 'p') return null;
      node.align = opening[3];
    }
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
