import {createElement, useLayoutEffect, useRef, useState} from 'react';
import {annotationNoteTree} from './annotationNote.mjs';

export default function AnnotationNote({note, html, onOpenLink}) {
  const tree = annotationNoteTree(note, html);
  const root = useRef(null);
  const [compact, setCompact] = useState(false);
  const hasFloat = Boolean(tree && String(html || '').includes(' style="float:'));
  useLayoutEffect(() => {
    if (!hasFloat || !root.current) return;
    const measure = () => {if (root.current) setCompact(root.current.getBoundingClientRect().width < 360);};
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(root.current);
    return () => observer.disconnect();
  }, [hasFloat]);
  if (!tree) return <span style={{whiteSpace: 'pre-wrap'}}>{note}</span>;
  const render = (node, key) => {
    if (typeof node === 'string') return node;
    const props = {key};
    let tag = node.tag;
    if (tag === 'p') props.style = {margin: '0 0 4px', whiteSpace: 'pre-wrap',
      ...(node.align ? {textAlign: node.align, clear: 'both'} : {})};
    if (tag === 'ul' || tag === 'ol') props.style = {margin: '4px 0', paddingLeft: 22};
    if (tag === 'img') {
      Object.assign(props, {src: node.src, width: node.width, height: node.height, alt: '',
        style: {maxWidth: '100%', height: 'auto', aspectRatio: `${node.width} / ${node.height}`, verticalAlign: 'middle'}});
      if (node.float) Object.assign(props.style, compact
        ? {display: 'block', float: 'none', margin: '0 auto 8px'}
        : {float: node.float, margin: node.float === 'left' ? '0 10px 6px 0' : '0 0 6px 10px'});
    }
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
    return createElement(tag, props, tag === 'br' || tag === 'img' ? undefined : node.children.map(render));
  };
  return <div ref={root} style={{display: 'flow-root', overflowWrap: 'anywhere'}}>{tree.map(render)}</div>;
}
