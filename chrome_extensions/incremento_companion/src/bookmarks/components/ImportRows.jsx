import {
  PRIORITY_SLIDER_MAX,
  formatPriority,
  priorityToSliderValue,
} from "../bookmarkModel.js";
import { t } from "../../shared/i18n.js";
import { formatBridgeError } from "../../shared/bridge.js";

export function ImportRows({
  items,
  disabled,
  onToggleSelected,
  onUpdateTitle,
  onUpdateKind,
  onUpdateTags,
  onUpdatePrioritySlider,
  onUpdatePriorityText,
  onCommitPriorityText,
}) {
  if (items.length === 0) {
    return (
      <div className="empty-state">
        {t("select_bookmarks_left")}
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
              <span className="field-label">{t("title")}</span>
              <input
                type="text"
                value={item.title}
                spellCheck="false"
                disabled={disabled}
                onChange={(event) => onUpdateTitle(item.id, event.target.value)}
              />
            </div>
            <div className="field">
              <span className="field-label">{t("type")}</span>
              <select
                value={item.kind}
                disabled={disabled}
                onChange={(event) => onUpdateKind(item.id, event.target.value)}
              >
                <option value="pdf">PDF</option>
                <option value="video">{t("video_kind")}</option>
                <option value="webpage">{t("webpage_kind")}</option>
                <option value="writing">{t("writing_kind")}</option>
              </select>
            </div>
            <div className="field">
              <span className="field-label">{t("tags")}</span>
              <input
                type="text"
                value={item.tagsText}
                placeholder="tag1 tag2"
                spellCheck="false"
                disabled={disabled}
                onChange={(event) => onUpdateTags(item.id, event.target.value)}
              />
            </div>
            <div className="field priority-field">
              <span className="field-label">{t("priority")}</span>
              <div className="priority-controls">
                <div className="priority-slider-wrap">
                  <input
                    className="priority-slider"
                    type="range"
                    min="0"
                    max={String(PRIORITY_SLIDER_MAX)}
                    step="1"
                    value={String(priorityToSliderValue(item.priority))}
                    disabled={disabled}
                    onChange={(event) => onUpdatePrioritySlider(item.id, event.target.value)}
                  />
                  <div className="priority-scale">
                    <span>0</span>
                    <span>100</span>
                  </div>
                </div>
                <input
                  className="priority-number"
                  type="text"
                  inputMode="decimal"
                  pattern="^\\d{1,3}(\\.\\d{0,4})?$"
                  value={item.priorityText || formatPriority(item.priority)}
                  placeholder="50.0000"
                  spellCheck="false"
                  disabled={disabled}
                  onChange={(event) => onUpdatePriorityText(item.id, event.target.value)}
                  onBlur={() => onCommitPriorityText(item.id)}
                />
              </div>
            </div>
          </div>
          <div className="row-meta">
            <div className="row-url">{item.url}</div>
            <div className="row-url">{item.folderPath || t("bookmarks")}</div>
            {item.importState === "error" && item.importError ? (
              <div className="row-error">{item.importErrorCause ? formatBridgeError(item.importErrorCause, t("import_bookmark_failed")) : item.importError}</div>
            ) : null}
          </div>
        </article>
      ))}
    </div>
  );
}
