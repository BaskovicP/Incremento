import { availableLanguages, formatNumber, t } from "../shared/i18n.js";

export function LanguageSettingsPanel({languageDraft, pendingPacks, busy, error, preview, fileInputRef, onSelect, onExportTemplate, onExportSelected, onImport, onSave, onCancel}) {
  return (
    <section className="panel" aria-label={t("settings")}>
      <div className="eyebrow">{t("settings")}</div>
      <h1>{t("language")}</h1>
      <p className="note">{t("language_description")}</p>
      <label className="field" htmlFor="ui-language">
        <span>{t("language")}</span>
        <select id="ui-language" value={languageDraft} disabled={busy} onChange={event => onSelect(event.target.value)}>
          {availableLanguages(pendingPacks).map(option => <option key={option.code} value={option.code}>{option.code === "auto" ? t("language_auto") : option.code.startsWith("custom:") ? t("language_custom_name", {name: option.name}) : option.name}</option>)}
        </select>
      </label>
      <p className="note">{t("language_sheet_help")}</p>
      <div className="actions">
        <button type="button" className="ghost-btn" disabled={busy} onClick={onExportTemplate}>{t("language_export_template")}</button>
        <button type="button" className="ghost-btn" disabled={busy} onClick={onExportSelected}>{t("language_export_selected")}</button>
        <button type="button" className="ghost-btn" disabled={busy} onClick={() => fileInputRef.current?.click()}>{t("language_import_csv")}</button>
        <input ref={fileInputRef} type="file" accept=".csv,.tsv,text/csv,text/tab-separated-values" hidden aria-label={t("language_import_csv")} onChange={onImport} />
      </div>
      {preview ? <p role="status" className="note">{t("language_pack_preview", {name: preview.name, count: formatNumber(preview.translated), total: formatNumber(preview.total)})}</p> : null}
      {error ? <p role="alert" className="field-hint is-error">{error}</p> : null}
      <div className="actions">
        <button type="button" className="kind-btn" disabled={busy} onClick={onSave}>{t("language_save")}</button>
        <button type="button" className="ghost-btn" disabled={busy} onClick={onCancel}>{t("language_cancel")}</button>
      </div>
    </section>
  );
}
