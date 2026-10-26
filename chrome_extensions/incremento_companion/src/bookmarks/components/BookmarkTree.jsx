import {PagedItems} from "./PagedItems.jsx";
import { useEffect, useRef, useState } from "react";
import { formatNumber, t } from "../../shared/i18n.js";

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
        <span className="tree-meta">{`${item.folderPath || t("bookmarks")} · ${node.url}`}</span>
      </label>
    </li>
  );
}

function FolderNode({ node, itemsById, treeIndex, selectionPrefix, disabled, onToggleFolder, onToggleBookmark }) {
  const [expanded, setExpanded] = useState(false);
  const [start, end] = treeIndex.ranges.get(String(node.id)) || [0, 0];
  const count = end - start;
  if (count === 0) {
    return null;
  }
  const selectedCount = selectionPrefix[end] - selectionPrefix[start];
  const isChecked = selectedCount > 0 && selectedCount === count;
  const isPartial = selectedCount > 0 && selectedCount < count;

  return (
    <li className="tree-node tree-folder">
      <details onToggle={(event) => { if (event.target === event.currentTarget) setExpanded(event.currentTarget.open); }}>
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
              <span className="tree-title">{String(node.title || t("folder")).trim() || t("folder")}</span>
              <span className="tree-meta">{t("selected_count", { selected: formatNumber(selectedCount), total: formatNumber(count) })}</span>
            </label>
          </div>
        </summary>
        {expanded ? <div className="tree-children">
          <BookmarkTree
            nodes={node.children || []}
            itemsById={itemsById}
            treeIndex={treeIndex}
            selectionPrefix={selectionPrefix}
            disabled={disabled}
            onToggleFolder={onToggleFolder}
            onToggleBookmark={onToggleBookmark}
          />
        </div> : null}
      </details>
    </li>
  );
}

export function BookmarkTree({ nodes, itemsById, treeIndex, selectionPrefix, disabled, onToggleFolder, onToggleBookmark }) {
  return <PagedItems items={nodes || []}>{visible => {
  const visibleNodes = visible.map((node) => {
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
        treeIndex={treeIndex}
        selectionPrefix={selectionPrefix}
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
  }}</PagedItems>;
}
