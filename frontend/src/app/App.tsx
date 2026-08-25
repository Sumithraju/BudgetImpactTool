import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  ApiError,
  type Calculation,
  type CountryOption,
  type IndicationOption,
  type EvidenceGapReport,
  type Owsa,
  type Psa,
} from "../shared/api";
import { ScenarioForm, type Draft } from "../features/scenario-builder/ScenarioForm";
import { Results } from "../features/results/Results";
import { ScenarioCompare, type SavedRun } from "../features/scenario-compare/ScenarioCompare";
import { Evidence } from "../features/evidence/Evidence";
import { ComparatorDiscovery } from "../features/comparator-discovery/ComparatorDiscovery";
import { ComparatorRegistry } from "../features/comparator-discovery/ComparatorRegistry";

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
  const [gaps, setGaps] = useState<EvidenceGapReport | null>(null);

  /** Every run this session, so any two can be compared. Kept in memory
   *  rather than re-fetched: the scenarios are already persisted server-side
   *  and this is only the shortlist the user has actually looked at. */
  const [saved, setSaved] = useState<SavedRun[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; field: string | null } | null>(null);

  /** Which indication the comparator panels are looking at, and a token the
   *  discovery panel bumps when it registers something so the registry
   *  reloads — neither component owning the other's state. */
  const [comparatorIndication, setComparatorIndication] = useState(DEFAULT_DRAFT.indicationId);
  const [registryToken, setRegistryToken] = useState(0);

  /** M14. Projecting the launch-year landscape is a scenario variant, not a
   *  base case: every entrant admitted rests on three tier-D assumptions. */
  const [projectLandscape, setProjectLandscape] = useState(false);

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
      const result = await api.calculate(scenario.scenario_id, true, projectLandscape);
      setCalculation(result);
      setOwsa(null);
      setPsa(null);
      setGaps(null);
      setSaved((current) => [
        ...current,
        {
          scenarioId: scenario.scenario_id,
          label: `Run ${current.length + 1}`,
          cumulative: result.totals.cumulative,
          currency: result.totals.currency,
        },
      ]);

      // M15's ranking needs the same sweep the tornado does, so all three
      // are fetched together rather than the panel triggering a second one.
      const [o, p, g] = await Promise.all([
        api.owsa(scenario.scenario_id),
        api.psa(scenario.scenario_id, 4000),
        api.evidenceGaps(scenario.scenario_id),
      ]);
      setOwsa(o);
      setPsa(p);
      setGaps(g);
    } catch (e) {
      const err = e as ApiError;
      setError({ message: err.message, field: err.field });
      setCalculation(null);
    } finally {
      setBusy(false);
    }
  }, [draft, overrides, projectLandscape]);

  return (
    <div className="shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">BIET · Pricing &amp; Market Access</div>
          <h1>Budget Impact Estimation</h1>
          <p className="tagline">
            Indication-specific, multi-market, ISPOR-aligned — every input traceable to
            its source and its confidence tier.
          </p>
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
          projectLandscape={projectLandscape}
          onProjectLandscapeChange={setProjectLandscape}
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
                Define the scenario on the left and run it. Every figure returned carries the
                source it was resolved from, its vintage and its confidence tier.
              </p>
            </div>
          )}

          {/* Discovery sits above the result because it answers the question
              that comes first: what is the world-without actually made of.
              It runs independently of a calculation. */}
          {indications.length > 0 && (
            <>
              <ComparatorDiscovery
                indications={indications}
                onIndicationChange={setComparatorIndication}
                onRegistered={() => setRegistryToken((n) => n + 1)}
              />
              <ComparatorRegistry
                indicationId={comparatorIndication}
                countries={countries}
                reloadToken={registryToken}
              />
            </>
          )}

          {calculation && (
            <>
              <Results
                calculation={calculation}
                owsa={owsa}
                psa={psa}
                gaps={gaps}
                bands={bands}
              />
              <Evidence scenarioId={calculation.scenario_id} />
              <ScenarioCompare saved={saved} />
            </>
          )}
        </main>
      </div>
    </div>
  );
}
