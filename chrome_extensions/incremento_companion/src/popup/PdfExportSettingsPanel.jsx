import { t } from "../shared/i18n.js";

export function PdfExportSettingsPanel({settings, busy = false, onChange}) {
  return (
    <div role="group" aria-labelledby="pdf-export-heading" className="pdf-export-settings">
      <h1 id="pdf-export-heading">{t("pdf_export_heading")}</h1>
      <p className="note">{t("pdf_export_description")}</p>
      <label className="field" htmlFor="pdf-export-style">
        <span>{t("pdf_export_layout")}</span>
        <select id="pdf-export-style" value={settings.style} disabled={busy} onChange={event => onChange({...settings, style: event.target.value})}>
          <option value="website">{t("pdf_export_website")}</option>
          <option value="article">{t("pdf_export_article")}</option>
          <option value="print">{t("pdf_export_print")}</option>
        </select>
      </label>
      <label className="toggle-row" htmlFor="pdf-export-dynamic">
        <input id="pdf-export-dynamic" type="checkbox" checked={settings.dynamic} disabled={busy} onChange={event => onChange({...settings, dynamic: event.target.checked})} />
        <span>{t("pdf_export_dynamic")}</span>
      </label>
      <p className="note">{t("pdf_export_dynamic_help")}</p>
      <label className="toggle-row" htmlFor="pdf-export-links">
        <input id="pdf-export-links" type="checkbox" checked={settings.includeLinks} disabled={busy} onChange={event => onChange({...settings, includeLinks: event.target.checked})} />
        <span>{t("pdf_export_links")}</span>
      </label>
    </div>
  );
}
