import { t } from "../../shared/i18n.js";
import { formatBridgeError } from "../../shared/bridge.js";
import { cardKindLabel } from "../../shared/cardKind.js";

export function ResultsList({ results }) {
  if (results.length === 0) {
    return <div className="results"></div>;
  }

  return (
    <div className="results">
      {results.map((result, index) => {
        const ok = Boolean(result?.ok);
        const detail = ok
          ? t("created_card", { kind: cardKindLabel(result?.kind), id: result?.cardId ? ` #${result.cardId}` : "" })
          : (result?.errorCause ? formatBridgeError(result.errorCause, t("import_failed")) : (result?.error || t("import_failed")));
        return (
          <div className={`result-card ${ok ? "is-success" : "is-error"}`} key={`${result?.title || "result"}-${index}`}>
            <strong>{result?.title || t("untitled")}</strong>
            <div className="result-line">{detail}</div>
          </div>
        );
      })}
    </div>
  );
}
