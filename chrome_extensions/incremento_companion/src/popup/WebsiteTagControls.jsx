import { formatBridgeError } from "../shared/bridge.js";
import { t } from "../shared/i18n.js";

export function WebsiteTagControls({state, busy = false, onToggle, onRetry}) {
  return (
    <div>
      <label className="toggle-row" htmlFor="remember-website-tags">
        <input id="remember-website-tags" type="checkbox" checked={state.enabled}
          disabled={busy || !state.ready} onChange={event => onToggle(event.target.checked)} />
        <span>{t("website_tags_remember")}</span>
      </label>
      {state.site ? <p className="field-hint">{t("website_tags_help", {site: state.site})}</p> : null}
      <div role="status" aria-live="polite">
        {state.loading ? <p className="field-hint">{t("website_tags_loading")}</p> : null}
        {state.saving ? <p className="field-hint">{t("website_tags_saving")}</p> : null}
      </div>
      {state.error ? <div role="alert" className="field-hint is-error">
        <p>{t("website_tags_error")} {formatBridgeError(state.error, t("website_tags_error"))}</p>
        <button type="button" disabled={busy || state.saving} onClick={onRetry}>{t("website_tags_retry")}</button>
      </div> : null}
    </div>
  );
}
