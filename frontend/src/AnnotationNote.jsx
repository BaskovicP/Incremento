import {createElement} from 'react';
import {annotationNoteTree} from './annotationNote.mjs';

export default function AnnotationNote({note, html, onOpenLink}) {
  const tree = annotationNoteTree(note, html);
  if (!tree) return <span style={{whiteSpace: 'pre-wrap'}}>{note}</span>;
  const render = (node, key) => {
    if (typeof node === 'string') return node;
    const props = {key};
    let tag = node.tag;
    if (tag === 'p') props.style = {margin: '0 0 4px', whiteSpace: 'pre-wrap'};
    if (tag === 'ul' || tag === 'ol') props.style = {margin: '4px 0', paddingLeft: 22};
    if (tag === 'a') {
      props.style = {color: 'inherit', textDecoration: 'underline'};
      props.title = node.href;
      if (onOpenLink) {
        props.href = node.href;
        props.onClick = event => {
          event.preventDefault();
          event.stopPropagation();
          if (event.nativeEvent.isTrusted) onOpenLink(node.href);
        };
      } else tag = 'span';
    }
    return createElement(tag, props, tag === 'br' ? undefined : node.children.map(render));
  };
  return tree.map(render);
}
