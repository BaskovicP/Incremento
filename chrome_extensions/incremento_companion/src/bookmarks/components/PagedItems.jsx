import {useState} from 'react';
import {t} from '../../shared/i18n.js';

export function PagedItems({items, children, size = 100}) {
  const [requested, setRequested] = useState(0);
  const last = Math.max(0, Math.floor((items.length - 1) / size) * size);
  const start = Math.min(last, requested);
  const end = Math.min(items.length, start + size);
  return <>
    {items.length > size && <nav style={{display: 'flex', gap: 12}}>
      <button type="button" disabled={!start} onClick={() => setRequested(Math.max(0, start - size))}>{t('bookmark_previous_page')}</button>
      <span role="status" aria-live="polite">{start + 1}–{end} / {items.length}</span>
      <button type="button" disabled={end === items.length} onClick={() => setRequested(Math.min(last, start + size))}>{t('bookmark_next_page')}</button>
    </nav>}
    {children(items.slice(start, end))}
  </>;
}
