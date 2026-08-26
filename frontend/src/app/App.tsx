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
  type SubgroupOption,
  type SegmentedCalculation,
} from "../shared/api";
import { ScenarioForm, type Draft } from "../features/scenario-builder/ScenarioForm";
import { Results } from "../features/results/Results";
import { ScenarioCompare, type SavedRun } from "../features/scenario-compare/ScenarioCompare";
import { Evidence } from "../features/evidence/Evidence";
import { ComparatorDiscovery } from "../features/comparator-discovery/ComparatorDiscovery";
import { ComparatorRegistry } from "../features/comparator-discovery/ComparatorRegistry";
import { ComparatorImport } from "../features/comparator-import/ComparatorImport";
import {
  NewIntervention,
  EMPTY_INTERVENTION,
  type InterventionDraft,
} from "../features/new-intervention/NewIntervention";
import { Tabs, type TabDefinition } from "../shared/Tabs";
import type { SubgroupShares } from "../features/subgroups/SubgroupShareEditor";

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
  const [segmented, setSegmented] = useState<SegmentedCalculation | null>(null);

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

  /** Which tab is open. Ephemeral UI state — it does not belong in the
   *  scenario, and a run does not reset it. */
  const [tab, setTab] = useState("comparators");

  /** The new therapy's own costs. Held here rather than in the scenario
   *  because the priced comparator the engine reads still comes from the
   *  registry; this panel is the intake for that, not a second cost path. */
  const [intervention, setIntervention] = useState<InterventionDraft>({
    ...EMPTY_INTERVENTION,
    name: DEFAULT_DRAFT.assetName,
  });

  /** The subgroup split. Owned here because the sidebar edits it and the
   *  results panel renders it — neither owning the other's state. Seeded from
   *  the API's defaults on first load, then the analyst's to change. */
  const [subgroupOptions, setSubgroupOptions] = useState<SubgroupOption[]>([]);
  const [subgroupShares, setSubgroupShares] = useState<SubgroupShares>({});

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

    // Fetched on its own rather than in the batch above. The taxonomy is
    // served from constants and needs no database, so it can succeed when the
    // reference tables cannot be read — and a `Promise.all` would have taken
    // it down with them, hiding the subgroup panel for a reason that has
    // nothing to do with subgroups.
    api
      .subgroups()
      .then((s) => {
        setSubgroupOptions(s);
        setSubgroupShares(
          Object.fromEntries(
            s
              .filter((o) => o.default_share !== null)
              .map((o) => [o.code, o.default_share as number]),
          ),
        );
      })
      .catch(() => setSubgroupOptions([]));
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
      setSegmented(null);
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
      const [o, p, g, seg] = await Promise.all([
        api.owsa(scenario.scenario_id),
        api.psa(scenario.scenario_id, 4000),
        api.evidenceGaps(scenario.scenario_id),
        api.calculateSegments(scenario.scenario_id, subgroupShares),
      ]);
      setOwsa(o);
      setPsa(p);
      setGaps(g);
      setSegmented(seg);
    } catch (e) {
      const err = e as ApiError;
      setError({ message: err.message, field: err.field });
      setCalculation(null);
    } finally {
      setBusy(false);
    }
  }, [draft, overrides, projectLandscape, subgroupShares]);

  /** The tabs, in the order the model runs: what the world without the asset
   *  is made of, what is being introduced, then what the difference costs.
   *  A tab whose data has not arrived says so rather than rendering empty. */
  const tabs: TabDefinition[] = [
    {
      id: "comparators",
      label: "Current care",
      badge: indications.length > 0 ? undefined : "…",
      content:
        indications.length > 0 ? (
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
        ) : (
          <div className="empty"><p>Loading reference data from the API…</p></div>
        ),
    },
    {
      id: "import",
      label: "Import",
      content: <ComparatorImport />,
    },
    {
      id: "intervention",
      label: "New intervention",
      content: (
        <NewIntervention
          draft={intervention}
          currency={draft.reportingCurrency}
          onChange={setIntervention}
        />
      ),
    },
    {
      id: "results",
      label: "Results",
      badge: calculation ? undefined : "—",
      content: calculation ? (
        <Results
          calculation={calculation}
          owsa={owsa}
          psa={psa}
          gaps={gaps}
          bands={bands}
          subgroupOptions={subgroupOptions}
          subgroupShares={subgroupShares}
          segments={segmented?.segments ?? null}
          segmentCurrency={segmented?.totals.currency ?? null}
        />
      ) : (
        <div className="empty">
          <p>
            Define the scenario on the left and run it. Every figure returned carries the
            source it was resolved from, its vintage and its confidence tier.
          </p>
        </div>
      ),
    },
    {
      id: "evidence",
      label: "Evidence",
      content: calculation ? (
        <Evidence scenarioId={calculation.scenario_id} />
      ) : (
        <div className="empty"><p>Run a scenario to generate its cited narrative.</p></div>
      ),
    },
    {
      id: "compare",
      label: "Compare",
      badge: saved.length || undefined,
      content: <ScenarioCompare saved={saved} />,
    },
  ];

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
          subgroupOptions={subgroupOptions}
          subgroupShares={subgroupShares}
          onSubgroupSharesChange={setSubgroupShares}
        />

        <main className="results">
          {error && (
            <div className="alert" role="alert">
              <strong>{error.field ? `${error.field} — ` : ""}</strong>
              {error.message}
            </div>
          )}

          <Tabs tabs={tabs} activeId={tab} onChange={setTab} />
        </main>
      </div>
    </div>
  );
}
