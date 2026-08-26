import { useState } from "react";
import { api, ApiError, type Comparison } from "../../shared/api";
import { formatMoneyCompact, formatPercent } from "../../shared/format";

/**
 * Side-by-side comparison of 2–4 saved runs.
 *
 * The diff shows only assumptions that actually differ. Listing every
 * identical parameter would bury the handful that moved, which is the whole
 * question a comparison is asked — so the API filters, and this renders
 * what survives.
 */

export interface SavedRun {
  scenarioId: string;
  label: string;
  cumulative: number;
  currency: string;
}

const MIN = 2;
const MAX = 4;

export function ScenarioCompare({ saved }: { saved: SavedRun[] }) {
  const [selected, setSelected] = useState<string[]>([]);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = (id: string) => {
    setComparison(null);
    setSelected((current) =>
      current.includes(id)
        ? current.filter((x) => x !== id)
        : current.length >= MAX
          ? current
          : [...current, id],
    );
  };

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      setComparison(await api.compare(selected));
    } catch (e) {
      setError((e as ApiError).message);
      setComparison(null);
    } finally {
      setBusy(false);
    }
  };

  if (saved.length < MIN) {
    return (
      <section>
        <h2>Compare</h2>
        <p className="lede">
          Run at least two scenarios and they become comparable here. Change an
          assumption between runs — the diff will show only what you moved.
        </p>
      </section>
    );
  }

  const labelFor = (id: string) =>
    saved.find((s) => s.scenarioId === id)?.label ?? id.slice(0, 8);

  return (
    <section>
      <h2>Compare</h2>
      <p className="lede">
        Pick {MIN} to {MAX} runs sharing an indication. Only assumptions that differ are
        listed.
      </p>

      <div className="cmp-picker">
        {saved.map((s) => (
          <button
            key={s.scenarioId}
            type="button"
            aria-pressed={selected.includes(s.scenarioId)}
            onClick={() => toggle(s.scenarioId)}
          >
            {s.label}
            <em>{formatMoneyCompact(s.cumulative, s.currency)}</em>
          </button>
        ))}
        <button
          type="button"
          className="cmp-run"
          disabled={selected.length < MIN || busy}
          onClick={run}
        >
          {busy ? "Comparing…" : `Compare ${selected.length || ""}`}
        </button>
      </div>

      {error && (
        <div className="alert" role="alert">
          {error}
        </div>
      )}

      {comparison && (
        <>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Metric</th>
                  {comparison.scenario_ids.map((id) => (
                    <th key={id}>{labelFor(id)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Cumulative impact</td>
                  {comparison.results.map((r) => (
                    <td className="num" key={r.scenario_id}>
                      {formatMoneyCompact(r.totals.cumulative, r.totals.currency)}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td>Peak year</td>
                  {comparison.results.map((r) => (
                    <td className="num" key={r.scenario_id}>
                      Y{r.totals.peak_year}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td>Markets</td>
                  {comparison.results.map((r) => (
                    <td className="num" key={r.scenario_id}>
                      {r.countries.length}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td>Addressable, final year</td>
                  {comparison.results.map((r) => (
                    <td className="num" key={r.scenario_id}>
                      {Math.round(
                        r.countries.reduce(
                          (sum, c) => sum + c.years[c.years.length - 1].addressable,
                          0,
                        ),
                      ).toLocaleString()}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>

          <h3 className="difftitle">What differs</h3>
          {comparison.diff.length === 0 ? (
            <p className="lede">
              These runs share every assumption — any difference in the totals comes from
              the scenario definition (markets, horizon, launch year) rather than from an
              override.
            </p>
          ) : (
            <div className="tablewrap">
              <table>
                <thead>
                  <tr>
                    <th>Assumption</th>
                    <th>Market</th>
                    {comparison.scenario_ids.map((id) => (
                      <th key={id}>{labelFor(id)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {comparison.diff.map((d) => (
                    <tr key={`${d.parameter_path}-${d.country_code ?? "all"}`}>
                      <td>
                        <code>{d.parameter_path}</code>
                      </td>
                      <td>{d.country_code ?? "all"}</td>
                      {comparison.scenario_ids.map((id) => {
                        const value = d.values[id];
                        const overridden =
                          d.resolution_levels[id] === "scenario_override";
                        return (
                          <td className="num" key={id}>
                            {value === null ? (
                              <span className="dim">seeded default</span>
                            ) : (
                              <span className={overridden ? "val-set" : ""}>
                                {typeof value === "number"
                                  ? formatPercent(value)
                                  : String(value)}
                              </span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
