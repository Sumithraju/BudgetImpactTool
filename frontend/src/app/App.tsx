import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  ApiError,
  type Calculation,
  type CountryOption,
  type IndicationOption,
  type Owsa,
  type Psa,
} from "../shared/api";
import { ScenarioForm, type Draft } from "../features/scenario-builder/ScenarioForm";
import { Results } from "../features/results/Results";
import { ScenarioCompare, type SavedRun } from "../features/scenario-compare/ScenarioCompare";
import { Evidence } from "../features/evidence/Evidence";
import { ComparatorDiscovery } from "../features/comparator-discovery/ComparatorDiscovery";

const DEFAULT_DRAFT: Draft = {
  name: "Wegovy obesity launch",
  assetName: "Wegovy (semaglutide 2.4 mg)",
  indicationId: 1,
  launchYear: 2028,
  horizonYears: 3,
  reportingCurrency: "EUR",
  countryCodes: ["USA", "DEU", "GBR", "JPN", "IND"],
  diagnosisRate: null,
  treatmentRate: null,
  accessRate: null,
  uptakeYear1: null,
  uptakeTerminal: null,
};

export function App() {
  const [countries, setCountries] = useState<CountryOption[]>([]);
  const [indications, setIndications] = useState<IndicationOption[]>([]);
  const [bands, setBands] = useState<Record<string, number>>({});
  const [draft, setDraft] = useState<Draft>(DEFAULT_DRAFT);

  const [calculation, setCalculation] = useState<Calculation | null>(null);
  const [owsa, setOwsa] = useState<Owsa | null>(null);
  const [psa, setPsa] = useState<Psa | null>(null);

  /** Every run this session, so any two can be compared. Kept in memory
   *  rather than re-fetched: the scenarios are already persisted server-side
   *  and this is only the shortlist the user has actually looked at. */
  const [saved, setSaved] = useState<SavedRun[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; field: string | null } | null>(null);

  useEffect(() => {
    Promise.all([api.countries(), api.indications(), api.affordabilityBands()])
      .then(([c, i, b]) => {
        setCountries(c);
        setIndications(i);
        setBands(b);
      })
      .catch((e: ApiError) =>
        setError({ message: `Could not reach the API — ${e.message}`, field: null }),
      );
  }, []);

  /** Overrides are only sent for fields the user actually touched: a null
   *  means "use the seeded default", which is not the same as sending the
   *  default back as an override (that would relabel it tier C). */
  const overrides = useMemo(() => {
    const out: { parameter_path: string; value: number }[] = [];
    const add = (path: string, value: number | null) => {
      if (value !== null) out.push({ parameter_path: path, value });
    };
    add("funnel.diagnosis_rate", draft.diagnosisRate);
    add("funnel.treatment_rate", draft.treatmentRate);
    add("funnel.access_rate", draft.accessRate);
    add("uptake.year_1", draft.uptakeYear1);
    add("uptake.terminal", draft.uptakeTerminal);
    return out;
  }, [draft]);

  const run = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const scenario = await api.createScenario({
        name: draft.name,
        indication_id: draft.indicationId,
        asset_name: draft.assetName,
        launch_year: draft.launchYear,
        horizon_years: draft.horizonYears,
        reporting_currency: draft.reportingCurrency,
        country_codes: draft.countryCodes,
        overrides,
      });

      // The forward result first, so the headline paints immediately; the
      // two analyses are slower and arrive after.
      const result = await api.calculate(scenario.scenario_id, true);
      setCalculation(result);
      setOwsa(null);
      setPsa(null);
      setSaved((current) => [
        ...current,
        {
          scenarioId: scenario.scenario_id,
          label: `Run ${current.length + 1}`,
          cumulative: result.totals.cumulative,
          currency: result.totals.currency,
        },
      ]);

      const [o, p] = await Promise.all([
        api.owsa(scenario.scenario_id),
        api.psa(scenario.scenario_id, 4000),
      ]);
      setOwsa(o);
      setPsa(p);
    } catch (e) {
      const err = e as ApiError;
      setError({ message: err.message, field: err.field });
      setCalculation(null);
    } finally {
      setBusy(false);
    }
  }, [draft, overrides]);

  return (
    <div className="shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">Budget Impact Estimation Tool</div>
          <h1>What would launching this asset cost the payer?</h1>
        </div>
        <div className="topmeta">
          {calculation && (
            <>
              <span>engine {calculation.engine_version}</span>
              <span>FX {calculation.fx_snapshot_date}</span>
              <span>{calculation.duration_ms} ms</span>
            </>
          )}
        </div>
      </header>

      <div className="layout">
        <ScenarioForm
          draft={draft}
          onChange={setDraft}
          countries={countries}
          indications={indications}
          onRun={run}
          busy={busy}
          errorField={error?.field ?? null}
        />

        <main className="results">
          {error && (
            <div className="alert" role="alert">
              <strong>{error.field ? `${error.field} — ` : ""}</strong>
              {error.message}
            </div>
          )}

          {!calculation && !error && (
            <div className="empty">
              <p>
                Set the scenario on the left and run it. Every figure that comes back carries
                the source it was resolved from and how much weight it deserves.
              </p>
            </div>
          )}

          {/* Discovery sits above the result because it answers the question
              that comes first: what is the world-without actually made of.
              It runs independently of a calculation. */}
          {indications.length > 0 && <ComparatorDiscovery indications={indications} />}

          {calculation && (
            <>
              <Results calculation={calculation} owsa={owsa} psa={psa} bands={bands} />
              <Evidence scenarioId={calculation.scenario_id} />
              <ScenarioCompare saved={saved} />
            </>
          )}
        </main>
      </div>
    </div>
  );
}
