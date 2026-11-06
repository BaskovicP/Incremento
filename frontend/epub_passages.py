"""Inert range capture, temporary reveal, and layout-independent EPUB coverage.

Inserted inside the existing isolated reader closure, after its text helpers.
"""

EPUB_PASSAGE_SCRIPT = r"""
      function currentPassage() {
        const meta = selectionMeta();
        if (!meta || meta.endOffset <= meta.startOffset) return {};
        const nodes = textNodes(), text = nodes.map(node => node.nodeValue).join('');
        if (text.length > 2000000) return {};
        const start = meta.startOffset, end = Math.min(meta.endOffset, start + 2000);
        return {start, end, quote: text.slice(start, end),
          prefix: text.slice(Math.max(0, start - 160), start), suffix: text.slice(end, end + 160)};
      }
      function coverageRange(start, end, textLength) {
        const maximum = Math.max(1, STATE.sectionLengths[STATE.sectionIndex] || textLength);
        return {start: Math.max(0, Math.floor(start * maximum / textLength)),
          end: Math.min(maximum, Math.ceil(end * maximum / textLength))};
      }
      function selectionCoverage() {
        const meta = selectionMeta();
        if (!meta) return null;
        const length = textNodes().reduce((sum, node) => sum + node.nodeValue.length, 0);
        return length ? coverageRange(meta.startOffset, meta.endOffset, length) : null;
      }
      function visibleCoverage() {
        if (document.hidden) return null;
        const nodes = textNodes();
        if (nodes.length > 20000) return null;
        const length = nodes.reduce((sum, node) => sum + node.nodeValue.length, 0);
        if (!length || length > 2000000) return null;
        let first = null, last = null;
        let base = 0;
        for (const node of nodes) {
          const range = document.createRange();
          range.selectNodeContents(node);
          for (const rect of range.getClientRects()) {
            if (rect.width <= 0 || rect.height <= 0 || rect.bottom <= 0 || rect.top >= innerHeight
                || rect.right <= 0 || rect.left >= innerWidth) continue;
            const y = Math.max(1, Math.min(innerHeight - 1, (Math.max(0, rect.top) + Math.min(innerHeight, rect.bottom)) / 2));
            const a = caretRangeAtPoint(Math.max(1, rect.left + 1), y);
            const b = caretRangeAtPoint(Math.min(innerWidth - 1, rect.right - 1), y);
            if (a && a.startContainer === node) {
              const value = base + a.startOffset;
              first = first === null ? value : Math.min(first, value);
            }
            if (b && b.startContainer === node) {
              const value = base + b.startOffset + 1;
              last = last === null ? value : Math.max(last, value);
            }
          }
          base += node.nodeValue.length;
        }
        return first !== null && last > first ? coverageRange(first, Math.min(length, last), length) : null;
      }
      function revealPassage(anchor) {
        if (!anchor || !anchor.quote) return false;
        const text = textNodes().map(node => node.nodeValue).join('');
        if (text.length > 2000000) return false;
        let start = anchor.start, end = anchor.end;
        if (!Number.isInteger(start) || !Number.isInteger(end)
            || normText(text.slice(start, end)) !== normText(anchor.quote)) {
          start = text.indexOf(anchor.quote);
          while (start >= 0 && ((anchor.prefix && !text.slice(0, start).endsWith(anchor.prefix))
              || (anchor.suffix && !text.slice(start + anchor.quote.length).startsWith(anchor.suffix)))) {
            start = text.indexOf(anchor.quote, start + 1);
          }
          if (start < 0) return false;
          end = start + anchor.quote.length;
        }
        const a = pointFromOffset(start, true), b = pointFromOffset(end);
        if (!a || !b) return false;
        const range = document.createRange();
        range.setStart(a.node, a.offset); range.setEnd(b.node, b.offset);
        const overlays = Array.from(range.getClientRects()).filter(rect => rect.width && rect.height).map(rect => {
          const overlay = document.createElement('div');
          overlay.dataset.incPassageReveal = '1';
          Object.assign(overlay.style, {position:'absolute',pointerEvents:'none',zIndex:999,
            left:(rect.left + scrollX)+'px',top:(rect.top + scrollY)+'px',width:rect.width+'px',height:rect.height+'px',
            background:'rgba(59,130,246,.28)',outline:'1px solid rgba(59,130,246,.8)'});
          document.body.append(overlay); return overlay;
        });
        if (!overlays.length) return false;
        overlays[0].scrollIntoView({block:'center'});
        let timer;
        const clear = () => {
          clearTimeout(timer); overlays.forEach(node => node.remove());
          document.removeEventListener('pointerdown', clear, true);
          document.removeEventListener('keydown', key, true);
          window.removeEventListener('resize', clear);
        };
        const key = event => {if (event.key === 'Escape') clear();};
        document.addEventListener('pointerdown', clear, true);
        document.addEventListener('keydown', key, true);
        window.addEventListener('resize', clear);
        timer = setTimeout(clear, 4000);
        return true;
      }
"""
