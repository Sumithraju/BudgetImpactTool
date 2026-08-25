import { useEffect, useState } from "react";
import { api, ApiError, type NarrativeDoc } from "../../shared/api";

/**
 * The narrative, its citations, and the export links.
 *
 * `generated_by` is shown rather than hidden. A reader deciding how much to
 * trust the prose should know whether it came from the deterministic
 * composer or from a model draft that passed numeric validation — those are
 * different provenance claims, and the distinction is the same one the
 * confidence tiers make about the inputs.
 */

const SECTION_TITLES: Record<string, string> = {
  population: "Population",
  impact: "Budget impact",
  affordability: "Affordability",
  uncertainty: "Uncertainty",
  limitations: "Limitations",
};

export function Evidence({ scenarioId }: { scenarioId: string }) {
  const [doc, setDoc] = useState<NarrativeDoc | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setDoc(null);
    setError(null);
    api
      .narrative(scenarioId)
      .then((d) => !cancelled && setDoc(d))
      .catch((e: ApiError) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [scenarioId]);

  return (
    <section>
      <h2>Evidence &amp; export</h2>

      <div className="exports">
        <a className="export-btn" href={api.exportUrl(scenarioId, "pdf")}>
          Download PDF
          <em>narrative, citations, assumption register</em>
        </a>
        <a className="export-btn" href={api.exportUrl(scenarioId, "xlsx")}>
          Download workbook
          <em>Excel, live formulas</em>
        </a>
        <a className="export-btn" href={api.exportUrl(scenarioId, "pptx")}>
          Download deck
          <em>PowerPoint, 16:9</em>
        </a>
      </div>

      {error && (
        <div className="alert" role="alert">
          {error}
        </div>
      )}

      {!doc && !error && <p className="lede">Composing the narrative…</p>}

      {doc && (
        <>
          <p className="provenance-line">
            Written by <b>{doc.generated_by}</b> · {doc.citations.length} guideline
            passages cited · {doc.assumptions.length} assumptions on record
          </p>

          {doc.warnings.map((w) => (
            <p className="warnbox" key={w}>
              {w}
            </p>
          ))}

          <div className="narrative">
            {Object.entries(SECTION_TITLES).map(([key, title]) =>
              doc.sections[key] ? (
                <div className="nsec" key={key}>
                  <h3>{title}</h3>
                  <p>{doc.sections[key]}</p>
                </div>
              ) : null,
            )}
          </div>

          <details className="sources">
            <summary>Stated limitations ({doc.limitations.length})</summary>
            <ul className="limits">
              {doc.limitations.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </details>

          {doc.citations.length > 0 && (
            <details className="sources">
              <summary>Cited guidance ({doc.citations.length})</summary>
              <ul className="cites">
                {doc.citations.slice(0, 10).map((c, i) => (
                  <li key={i}>
                    <b>
                      {c.issuing_body}
                      {c.page_number !== null && ` · p.${c.page_number}`}
                    </b>
                    <span>{c.excerpt}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}

          <details className="sources">
            <summary>Assumption register ({doc.assumptions.length})</summary>
            <div className="tablewrap" style={{ marginTop: 12 }}>
              <table>
                <thead>
                  <tr>
                    <th>Parameter</th>
                    <th>Market</th>
                    <th>Value</th>
                    <th>Tier</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {doc.assumptions.slice(0, 40).map((a, i) => (
                    <tr key={i}>
                      <td>
                        <code>{a.parameter_path}</code>
                      </td>
                      <td>{a.country_code ?? "all"}</td>
                      <td className="num">{a.value.toPrecision(4)}</td>
                      <td>
                        <span className={`chip t-${a.confidence_tier}`}>
                          {a.confidence_tier}
                        </span>
                      </td>
                      <td className="src-cell">{a.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {doc.assumptions.length > 40 && (
              <p className="lede" style={{ marginTop: 10 }}>
                Showing 40 of {doc.assumptions.length}. The PDF export carries the full
                register.
              </p>
            )}
          </details>
        </>
      )}
    </section>
  );
}
