export function ResultsList({ results }) {
  if (results.length === 0) {
    return <div className="results"></div>;
  }

  return (
    <div className="results">
      {results.map((result, index) => {
        const ok = Boolean(result?.ok);
        const detail = ok
          ? `Created ${result?.kind || ""} card${result?.cardId ? ` #${result.cardId}` : ""}`
          : (result?.error || "Import failed.");
        return (
          <div className={`result-card ${ok ? "is-success" : "is-error"}`} key={`${result?.title || "result"}-${index}`}>
            <strong>{result?.title || "Untitled"}</strong>
            <div className="result-line">{detail}</div>
          </div>
        );
      })}
    </div>
  );
}
