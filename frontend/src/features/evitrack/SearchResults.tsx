type EvidenceResult = {
  title: string;
  source: string;
  source_id: string | null;
  year: number | null;
  authors: string[];
  abstract: string | null;
  doi: string | null;
  url: string;
  evidence_type: string;
  relevance: number | null;
};

type SearchResultsProps = {
  results: EvidenceResult[];
  selectedIds?: string[];
  onAdd?: (result: EvidenceResult) => void;
};

export function SearchResults({
  results,
  selectedIds = [],
  onAdd,
}: SearchResultsProps) {
  return (
    <section className="evitrack-section">
      <h3>External evidence</h3>

      {results.length === 0 ? (
        <p>No external evidence found.</p>
      ) : (
        results.map((result) => {
          const selected =
            result.source_id !== null &&
            selectedIds.includes(result.source_id);

          return (
            <article
              key={`${result.source}-${result.source_id ?? result.title}`}
              className="evitrack-result"
            >
              <div className="evitrack-result-header">
                <span className="evitrack-source">
                  {result.source}
                </span>

                {result.year !== null && (
                  <span className="evitrack-year">
                    {result.year}
                  </span>
                )}
              </div>

              <h4>{result.title}</h4>

              {result.authors.length > 0 && (
                <p className="evitrack-authors">
                  {result.authors.slice(0, 5).join(", ")}
                  {result.authors.length > 5 && " et al."}
                </p>
              )}

              <p className="evitrack-type">
                {result.evidence_type.replaceAll("_", " ")}
              </p>

              {result.doi !== null && (
                <p className="evitrack-doi">
                  DOI: {result.doi}
                </p>
              )}

              {result.relevance !== null && (
                <small>
                  Search relevance: {result.relevance.toFixed(2)}
                </small>
              )}

              <div className="evitrack-actions">
                <a
                  href={result.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="evitrack-button"
                >
                  Open source
                </a>

                {onAdd !== undefined && result.source_id !== null && (
                  <button
                    type="button"
                    onClick={() => onAdd(result)}
                    disabled={selected}
                    className="evitrack-button"
                  >
                    {selected ? "Added" : "Add evidence"}
                  </button>
                )}
              </div>
            </article>
          );
        })
      )}
    </section>
  );
}
