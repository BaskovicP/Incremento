export function ImportRows({ items, disabled, onToggleSelected, onUpdateTitle, onUpdateKind, onUpdateTags }) {
  if (items.length === 0) {
    return (
      <div className="empty-state">
        Select folders or individual bookmarks on the left to build the import list.
      </div>
    );
  }

  return (
    <div className="import-rows">
      {items.map((item) => (
        <article className={`import-row${item.importState === "error" ? " is-error" : ""}`} key={item.id}>
          <div className="row-top">
            <label>
              <input
                className="row-checkbox"
                type="checkbox"
                data-row-id={item.id}
                checked={item.selected}
                disabled={disabled}
                onChange={(event) => onToggleSelected(item.id, event.target.checked)}
              />
            </label>
            <div className="field">
              <span className="field-label">Title</span>
              <input
                type="text"
                value={item.title}
                spellCheck="false"
                disabled={disabled}
                onChange={(event) => onUpdateTitle(item.id, event.target.value)}
              />
            </div>
            <div className="field">
              <span className="field-label">Type</span>
              <select
                value={item.kind}
                disabled={disabled}
                onChange={(event) => onUpdateKind(item.id, event.target.value)}
              >
                <option value="pdf">PDF</option>
                <option value="video">YouTube/Video</option>
                <option value="webpage">Webpage</option>
                <option value="writing">Writing</option>
              </select>
            </div>
            <div className="field">
              <span className="field-label">Tags</span>
              <input
                type="text"
                value={item.tagsText}
                placeholder="tag1 tag2"
                spellCheck="false"
                disabled={disabled}
                onChange={(event) => onUpdateTags(item.id, event.target.value)}
              />
            </div>
          </div>
          <div className="row-meta">
            <div className="row-url">{item.url}</div>
            <div className="row-url">{item.folderPath || "Bookmarks"}</div>
            {item.importState === "error" && item.importError ? (
              <div className="row-error">{item.importError}</div>
            ) : null}
          </div>
        </article>
      ))}
    </div>
  );
}
