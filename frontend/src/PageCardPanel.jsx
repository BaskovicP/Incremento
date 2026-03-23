/**
 * PageCardPanel — collapsible list of Anki cards created on the current page.
 * Rendered only when showCardPanel is true and pageCards is non-empty.
 */

export default function PageCardPanel({ page, pageCards }) {
  return (
    <div style={{
      margin:       '6px 8px 2px',
      padding:      '8px 10px',
      background:   'rgba(74,144,217,0.08)',
      border:       '1px solid rgba(74,144,217,0.3)',
      borderRadius: 6,
      fontSize:     12,
    }}>
      <div style={{ fontWeight: 'bold', marginBottom: 6, color: 'rgb(74,144,217)' }}>
        Cards created on page {page}
      </div>
      {pageCards.map((c, i) => (
        <div
          key={c.note_id}
          style={{
            padding:      '5px 8px',
            marginBottom: i < pageCards.length - 1 ? 5 : 0,
            background:   'rgba(255,255,255,0.05)',
            borderRadius: 4,
            borderLeft:   '3px solid rgba(74,144,217,0.5)',
            cursor:       'pointer',
            userSelect:   'none',
          }}
          onClick={() => window.pycmd('incremento_open_card:' + c.note_id)}
          title="Click to open in card browser"
        >
          {c.excerpt || <em style={{ color: '#888' }}>No text</em>}
        </div>
      ))}
    </div>
  );
}
