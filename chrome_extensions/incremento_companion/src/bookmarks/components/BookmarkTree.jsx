import { useEffect, useRef } from "react";
import { collectBookmarkIds, countSelected } from "../bookmarkModel.js";

function FolderCheckbox({ folderId, checked, indeterminate, disabled, onToggle }) {
  const checkboxRef = useRef(null);

  useEffect(() => {
    if (checkboxRef.current) {
      checkboxRef.current.indeterminate = indeterminate;
    }
  }, [indeterminate]);

  return (
    <input
      ref={checkboxRef}
      className="tree-checkbox"
      type="checkbox"
      data-folder-id={folderId}
      checked={checked}
      disabled={disabled}
      onClick={(event) => event.stopPropagation()}
      onChange={(event) => onToggle(folderId, event.target.checked)}
    />
  );
}

function BookmarkNode({ node, item, disabled, onToggleBookmark }) {
  return (
    <li className="tree-node">
      <label className="tree-row tree-label">
        <input
          className="tree-checkbox"
          type="checkbox"
          data-bookmark-id={item.id}
          checked={item.selected}
          disabled={disabled}
          onChange={(event) => onToggleBookmark(item.id, event.target.checked)}
        />
        <span className="tree-title">{item.title}</span>
        <span className="tree-meta">{`${item.folderPath || "Bookmarks"} · ${node.url}`}</span>
      </label>
    </li>
  );
}

function FolderNode({ node, itemsById, disabled, onToggleFolder, onToggleBookmark }) {
  const bookmarkIds = collectBookmarkIds(node, itemsById);
  if (bookmarkIds.length === 0) {
    return null;
  }
  const selectedCount = countSelected(bookmarkIds, itemsById);
  const isChecked = selectedCount > 0 && selectedCount === bookmarkIds.length;
  const isPartial = selectedCount > 0 && selectedCount < bookmarkIds.length;

  return (
    <li className="tree-node tree-folder">
      <details>
        <summary>
          <div className="tree-folder-summary">
            <span className="tree-toggle" aria-hidden="true">▶</span>
            <FolderCheckbox
              folderId={String(node.id)}
              checked={isChecked}
              indeterminate={isPartial}
              disabled={disabled}
              onToggle={onToggleFolder}
            />
            <label className="tree-row tree-label">
              <span className="tree-title">{String(node.title || "Folder").trim() || "Folder"}</span>
              <span className="tree-meta">{`${selectedCount}/${bookmarkIds.length} selected`}</span>
            </label>
          </div>
        </summary>
        <div className="tree-children">
          <BookmarkTree
            nodes={node.children || []}
            itemsById={itemsById}
            disabled={disabled}
            onToggleFolder={onToggleFolder}
            onToggleBookmark={onToggleBookmark}
          />
        </div>
      </details>
    </li>
  );
}

export function BookmarkTree({ nodes, itemsById, disabled, onToggleFolder, onToggleBookmark }) {
  const visibleNodes = (nodes || []).map((node) => {
    if (node.url) {
      const item = itemsById[String(node.id)];
      return item
        ? (
          <BookmarkNode
            key={String(node.id)}
            node={node}
            item={item}
            disabled={disabled}
            onToggleBookmark={onToggleBookmark}
          />
        )
        : null;
    }
    return (
      <FolderNode
        key={String(node.id)}
        node={node}
        itemsById={itemsById}
        disabled={disabled}
        onToggleFolder={onToggleFolder}
        onToggleBookmark={onToggleBookmark}
      />
    );
  }).filter(Boolean);

  if (visibleNodes.length === 0) {
    return null;
  }

  return <ul className="tree-list">{visibleNodes}</ul>;
}
