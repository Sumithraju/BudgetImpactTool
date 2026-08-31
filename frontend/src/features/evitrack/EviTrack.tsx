import { useState } from "react";
import { SearchBox } from "./SearchBox";
import { SearchResults } from "./SearchResults";
import { EvidenceWorkspace } from "./EvidenceWorkspace";
import "./styles.css";

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

export function EviTrack() {
  const [results, setResults] = useState<EvidenceResult[]>([]);
  const [selectedEvidence, setSelectedEvidence] =
    useState<EvidenceResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch(query: string) {
    if (!query.trim()) {
      setResults([]);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `/api/v1/evitrack/search?q=${encodeURIComponent(query)}&limit=10`
      );

      if (!response.ok) {
        throw new Error(`Search failed (${response.status})`);
      }

      const data = await response.json();
      setResults(data.results ?? []);
    } catch (err) {
      setResults([]);
      setError(
        err instanceof Error
          ? err.message
          : "Unable to search evidence."
      );
    } finally {
      setLoading(false);
    }
  }

  function handleAddEvidence(result: EvidenceResult) {
    if (result.source_id === null) {
      return;
    }

    setSelectedEvidence((current) => {
      const alreadySelected = current.some(
        (item) => item.source_id === result.source_id
      );

      if (alreadySelected) {
        return current;
      }

      return [...current, result];
    });
  }

  function handleRemoveEvidence(sourceId: string) {
    setSelectedEvidence((current) =>
      current.filter((item) => item.source_id !== sourceId)
    );
  }

  function handleClearEvidence() {
    setSelectedEvidence([]);
  }

  const selectedIds = selectedEvidence
    .map((result) => result.source_id)
    .filter((id): id is string => id !== null);

  return (
    <section className="evitrack">
      <header className="evitrack-header">
        <div>
          <h2>EviTrack</h2>
          <p>
            Find, curate and manage external evidence for your BIA.
          </p>
        </div>

        {selectedEvidence.length > 0 && (
          <div className="evitrack-count">
            {selectedEvidence.length} selected
          </div>
        )}
      </header>

      <SearchBox onSearch={handleSearch} />

      {loading && <p>Searching evidence...</p>}

      {error && <p role="alert">{error}</p>}

      {!loading && !error && (
        <SearchResults
          results={results}
          selectedIds={selectedIds}
          onAdd={handleAddEvidence}
        />
      )}

      <EvidenceWorkspace
        selected={selectedEvidence}
        onRemove={handleRemoveEvidence}
        onClear={handleClearEvidence}
      />
    </section>
  );
}
