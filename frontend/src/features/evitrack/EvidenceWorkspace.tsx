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

type EvidenceWorkspaceProps = {
  selected: EvidenceResult[];
  onRemove: (sourceId: string) => void;
  onClear: () => void;
};

export function EvidenceWorkspace({
  selected,
  onRemove,
  onClear,
}: EvidenceWorkspaceProps) {
  return (
    <section className="evitrack-section evitrack-workspace">
      <div className="evitrack-workspace-header">
        <div>
          <h3>Evidence workspace</h3>
          <p>
            Curate supporting evidence before using it in your analysis.
          </p>
        </div>

        {selected.length > 0 && (
          <button
            type="button"
            className="evitrack-button"
            onClick={onClear}
          >
            Clear all
          </button>
        )}
      </div>

      {selected.length === 0 ? (
        <div className="evitrack-empty">
          <strong>No evidence selected</strong>
          <p>
            Add relevant publications from the search results to build
            an evidence set for review.
          </p>
        </div>
      ) : (
        <div className="evitrack-selected">
          {selected.map((result) => (
            <article
              key={`${result.source}-${result.source_id ?? result.title}`}
              className="evitrack-selected-item"
            >
              <div>
                <span className="evitrack-source">
                  {result.source}
                </span>

                {result.year !== null && (
                  <span className="evitrack-year">
                    {" · "}
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

              <div className="evitrack-actions">
                <a
                  href={result.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="evitrack-button"
                >
                  Open source
                </a>

                {result.source_id !== null && (
                  <button
                    type="button"
                    className="evitrack-button"
                    onClick={() => onRemove(result.source_id!)}
                  >
                    Remove
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
