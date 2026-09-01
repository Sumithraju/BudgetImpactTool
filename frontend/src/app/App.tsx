/**
 * The shell. Inputs on the left, results on the right, in that order.
 *
 * ARCHITECTURE.md Phase 15 asks for the flow to read inputs first and then
 * outputs, and for every field to be explained in place. Both are structural
 * here rather than decorative: the input studio is ordered by the model's own
 * computation sequence, and its hover text comes from the API's field guide so
 * that the interface, the import template and the exported workbook cannot
 * describe the same input three different ways.
 *
 * The workspace has three modes rather than one scroll — build the scenario,
 * price it, read it. A price grid and a tornado do not belong on the same
 * screen, and stacking them means whichever is on top wins.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  ApiError,
  type BreakEven,
  type Calculation,
  type CountryOption,
  type CriterionOption,
  type DrugPrice,
  type EvidenceGapReport,
  type FieldGroup,
  type ImportResult,
  type IndicationOption,
  type Owsa,
  type PerspectiveOption,
  type Psa,
  type SubgroupOption,
  type UptakeScenarios,
} from "../shared/api";
import { InputStudio, type Draft } from "../features/scenario-builder/InputStudio";
import { PriceGrid } from "../features/scenario-builder/PriceGrid";
import { WorkbookPanel } from "../features/scenario-builder/WorkbookPanel";
import { MarketBurden } from "../features/scenario-builder/MarketBurden";
import { ResultsView } from "../features/results/ResultsView";
import { ScenarioCompare, type SavedRun } from "../features/scenario-compare/ScenarioCompare";
import { ComparatorDiscovery } from "../features/comparator-discovery/ComparatorDiscovery";
import { ComparatorRegistry } from "../features/comparator-discovery/ComparatorRegistry";
import { EviTrack } from "../features/evitrack/EviTrack";
import { Placeholder } from "../shared/ui";
import { formatMoneyCompact } from "../shared/format";
import { useStickyHeaderHeight } from "../shared/useStickyHeader";
import { Brand } from "../shared/BrandMark";

const DEFAULT_DRAFT: Draft = {
  name: "Wegovy obesity launch",
  assetName: "Wegovy (semaglutide 2.4 mg)",
  indicationId: 1,
  launchYear: 2028,
  horizonYears: 3,
  reportingCurrency: "EUR",
  countryCodes: ["USA", "DEU", "GBR", "DNK", "IND"],
  prevalence: null,
  diagnosisRate: null,
  treatmentRate: null,
  accessRate: null,
  uptakeYear1: null,
  uptakeTerminal: null,
  uptakeCurve: "logistic",
  regainPerYear: null,
  criteriaFactors: {},
  substitutionNaive: null,
  perspective: "health_system",
  coveredPopulation: null,
  subgroupCodes: [],
  priceEdits: [],
  imported: [],
};

type Workspace = "build" | "prices" | "comparators" | "results" | "evitrack";

export function App() {
  // The header wraps from one row to three between a monitor and a phone, and
  // grows again when a result adds the figure line. Everything that sticks
  // below it reads the measured height rather than a constant that would be
  // wrong at most widths — and wrong here means content hidden under an
  // opaque bar.
  const topbar = useRef<HTMLElement>(null);
  useStickyHeaderHeight(topbar);

  const [countries, setCountries] = useState<CountryOption[]>([]);
  const [indications, setIndications] = useState<IndicationOption[]>([]);
  const [subgroups, setSubgroups] = useState<SubgroupOption[]>([]);
  const [perspectives, setPerspectives] = useState<PerspectiveOption[]>([]);
  const [guide, setGuide] = useState<FieldGroup[]>([]);
  const [criteria, setCriteria] = useState<CriterionOption[]>([]);
  const [bands, setBands] = useState<Record<string, number>>({});
  // Panel reasoning is off by default and remembered per browser. An analyst
  // reviewing the model wants every word; the same person presenting it wants
  // the figures. Neither should have to be the default for the other.
  const [explain, setExplain] = useState(() => {
    try {
      return localStorage.getItem("biet.explain") === "on";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem("biet.explain", explain ? "on" : "off");
    } catch {
      // A browser with site data blocked still works; the choice just does
      // not survive a reload.
    }
  }, [explain]);

  const [prices, setPrices] = useState<DrugPrice[]>([]);
  const [pricesLoading, setPricesLoading] = useState(false);

  const [draft, setDraft] = useState<Draft>(DEFAULT_DRAFT);
  const [workspace, setWorkspace] = useState<Workspace>("build");

  const [calculation, setCalculation] = useState<Calculation | null>(null);
  const [owsa, setOwsa] = useState<Owsa | null>(null);
  const [psa, setPsa] = useState<Psa | null>(null);
  const [gaps, setGaps] = useState<EvidenceGapReport | null>(null);
  const [breakEven, setBreakEven] = useState<BreakEven | null>(null);
  const [uptakeCases, setUptakeCases] = useState<UptakeScenarios | null>(null);

  /** Every run this session, so any two can be compared. Kept in memory rather
   *  than re-fetched: the scenarios are already persisted server-side and this
   *  is only the shortlist the user has actually looked at. */
  const [saved, setSaved] = useState<SavedRun[]>([]);
  const [busy, setBusy] = useState(false);
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [error, setError] = useState<{ message: string; field: string | null } | null>(
    null,
  );

  const [comparatorIndication, setComparatorIndication] = useState(
    DEFAULT_DRAFT.indicationId,
  );
  const [registryToken, setRegistryToken] = useState(0);

  /** M14. Projecting the launch-year landscape is a scenario variant, not a
   *  base case: every entrant admitted rests on three tier-D assumptions. */
  const [projectLandscape, setProjectLandscape] = useState(false);

  useEffect(() => {
    Promise.all([
      api.countries(),
      api.indications(),
      api.affordabilityBands(),
      api.perspectives(),
      api.fieldGuide(),
    ])
      .then(([c, i, b, p, g]) => {
        setCountries(c);
        setIndications(i);
        setBands(b);
        setPerspectives(p);
        setGuide(g);
      })
      .catch((e: ApiError) =>
        setError({ message: `Could not reach the API — ${e.message}`, field: null }),
      );
  }, []);

  useEffect(() => {
    api
      .subgroups(draft.indicationId)
      .then(setSubgroups)
      .catch(() => setSubgroups([]));
  }, [draft.indicationId]);

  // The criterion stack belongs to the disease, so it reloads with it. A
  // factor the reader moved is keyed by criterion code and would be
  // meaningless against another disease's codes, so the overrides clear too.
  useEffect(() => {
    api
      .criteria(draft.indicationId)
      .then(setCriteria)
      .catch(() => setCriteria([]));
    setDraft((current) =>
      Object.keys(current.criteriaFactors).length
        ? { ...current, criteriaFactors: {} }
        : current,
    );
  }, [draft.indicationId]);

  // The price grid reloads when the market set or the disease changes, since
  // both change which cells exist. Edits are keyed by therapy and market, so
  // an edit to a market still in the set survives the reload.
  const marketKey = draft.countryCodes.join(",");
  useEffect(() => {
    if (!draft.countryCodes.length) return;
    setPricesLoading(true);
    api
      .prices(draft.indicationId, draft.countryCodes)
      .then(setPrices)
      .catch(() => setPrices([]))
      .finally(() => setPricesLoading(false));
  }, [draft.indicationId, marketKey]);

  /** Overrides are only sent for fields the user actually touched: a null means
   *  "use the seeded default", which is not the same as sending the default
   *  back as an override — that would relabel a published figure tier C. */
  const overrides = useMemo(() => {
    const out: { parameter_path: string; value: number | string; country_code?: string }[] =
      [];
    const add = (path: string, value: number | null) => {
      if (value !== null) out.push({ parameter_path: path, value });
    };
    add("epidemiology.prevalence", draft.prevalence);
    add("funnel.diagnosis_rate", draft.diagnosisRate);
    add("funnel.treatment_rate", draft.treatmentRate);
    add("funnel.access_rate", draft.accessRate);
    add("uptake.year_1", draft.uptakeYear1);
    add("uptake.terminal", draft.uptakeTerminal);
    add("outcomes.regain_per_year", draft.regainPerYear);
    add("substitution.naive", draft.substitutionNaive);
    for (const [code, factor] of Object.entries(draft.criteriaFactors)) {
      out.push({ parameter_path: `criteria.${code}.factor`, value: factor });
    }
    if (draft.uptakeCurve !== "logistic") {
      out.push({ parameter_path: "uptake.curve", value: draft.uptakeCurve });
    }
    // Imported values are per-market and go out as such. Sent alongside the
    // typed ones rather than merged into them: an override naming a market
    // beats one that does not, so the two must stay distinguishable.
    for (const item of draft.imported) {
      out.push({
        parameter_path: item.parameter_path,
        value: item.value,
        ...(item.country_code ? { country_code: item.country_code } : {}),
      });
    }
    for (const edit of draft.priceEdits) {
      out.push({
        parameter_path: `therapy.${edit.drug_id}.price_local`,
        value: edit.unit_price,
        country_code: edit.country_code,
      });
    }
    return out;
  }, [draft]);

  const run = useCallback(async () => {
    setBusy(true);
    setAnalysisBusy(true);
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
        perspective: draft.perspective,
        covered_population: draft.coveredPopulation,
        subgroup_codes: draft.subgroupCodes,
        overrides,
      });

      // The forward result first, so the headline paints immediately; the
      // analyses are slower and arrive after.
      const result = await api.calculate(scenario.scenario_id, true, projectLandscape);
      setCalculation(result);
      setOwsa(null);
      setPsa(null);
      setGaps(null);
      setBreakEven(null);
      setUptakeCases(null);
      setWorkspace("results");
      setSaved((current) => [
        ...current,
        {
          scenarioId: scenario.scenario_id,
          label: `Run ${current.length + 1}`,
          cumulative: result.totals.cumulative,
          currency: result.totals.currency,
        },
      ]);
      setBusy(false);

      // Every analysis is independent of the others, so they go out together
      // rather than in sequence — and each lands as it arrives instead of the
      // slowest one gating the rest.
      const settle = <T,>(promise: Promise<T>, set: (v: T) => void) =>
        promise.then(set).catch(() => undefined);

      await Promise.all([
        settle(api.owsa(scenario.scenario_id), setOwsa),
        settle(api.psa(scenario.scenario_id, 5000), setPsa),
        settle(api.evidenceGaps(scenario.scenario_id), setGaps),
        settle(api.breakEven(scenario.scenario_id), setBreakEven),
        settle(api.uptakeScenarios(scenario.scenario_id), setUptakeCases),
      ]);
    } catch (e) {
      const err = e as ApiError;
      setError({ message: err.message, field: err.field });
      setCalculation(null);
      setBusy(false);
    } finally {
      setAnalysisBusy(false);
    }
  }, [draft, overrides, projectLandscape]);

  /** An imported workbook fills the draft; it never runs on its own. The
   *  analyst sees what the file was read as, in the ordinary inputs, and
   *  presses Run themselves. */
  const applyImport = useCallback((result: ImportResult) => {
    const parsed = result.scenario;
    setDraft((current) => {
      const next = { ...current };
      if (parsed.asset_name) next.assetName = parsed.asset_name;
      if (parsed.launch_year) next.launchYear = parsed.launch_year;
      if (parsed.horizon_years) next.horizonYears = parsed.horizon_years;
      if (parsed.reporting_currency) next.reportingCurrency = parsed.reporting_currency;
      if (parsed.country_codes.length) next.countryCodes = parsed.country_codes;
      if (parsed.perspective) next.perspective = parsed.perspective;
      if (parsed.covered_population) next.coveredPopulation = parsed.covered_population;
      if (parsed.subgroup_codes.length) next.subgroupCodes = parsed.subgroup_codes;

      // Anything naming a market stays an imported value — editable, and
      // labelled as coming from the file. Only the market-agnostic ones can
      // fold into the ordinary typed fields, because those have no market.
      next.imported = parsed.overrides
        .filter((o) => Boolean((o as { country_code?: string }).country_code))
        .map((o) => ({
          parameter_path: o.parameter_path,
          country_code: (o as { country_code?: string }).country_code ?? null,
          value: Number(o.value),
          note: o.note ?? null,
        }));

      for (const override of parsed.overrides) {
        if ((override as { country_code?: string }).country_code) continue;
        const value = Number(override.value);
        switch (override.parameter_path) {
          case "epidemiology.prevalence":
            next.prevalence = value;
            break;
          case "funnel.diagnosis_rate":
            next.diagnosisRate = value;
            break;
          case "funnel.treatment_rate":
            next.treatmentRate = value;
            break;
          case "funnel.access_rate":
            next.accessRate = value;
            break;
          case "uptake.year_1":
            next.uptakeYear1 = value;
            break;
          case "uptake.terminal":
            next.uptakeTerminal = value;
            break;
          case "outcomes.regain_per_year":
            next.regainPerYear = value;
            break;
        }
      }

      next.priceEdits = parsed.prices
        .filter((p) => p.unit_price != null && p.unit_price > 0)
        .map((p) => ({
          drug_id: p.drug_id,
          country_code: p.country_code,
          unit_price: p.unit_price as number,
        }));
      return next;
    });
    setWorkspace("build");
  }, []);

  // Numbered, because the order is a sequence rather than a menu — and the
  // sequence is the one the model itself depends on. You cannot price a
  // comparator basket before you know which markets are in scope (Build), you
  // cannot compare against a therapy that has no price (Prices), and a result
  // computed before either is a result about the wrong world. Results is last
  // because it is the only step that reads rather than writes.
  const modes: { id: Workspace; step: number; label: string; hint: string }[] = [
    { id: "build", step: 1, label: "Build", hint: "who and where" },
    { id: "prices", step: 2, label: "Prices", hint: "what it costs" },
    { id: "comparators", step: 3, label: "Comparators", hint: "what it displaces" },
    { id: "results", step: 4, label: "Results", hint: "what it means" },
    { id: "evitrack", step: 5, label: "EviTrack", hint: "find and curate evidence" },
  ];

  return (
    <div className="shell" data-explain={explain ? "on" : "off"}>
      <header className="topbar" ref={topbar}>
        <Brand />

        <nav className="modes" aria-label="Workspace">
          {modes.map((mode) => (
            <button
              key={mode.id}
              type="button"
              className="mode"
              aria-pressed={workspace === mode.id}
              disabled={mode.id === "results" && !calculation}
              onClick={() => setWorkspace(mode.id)}
            >
              <span className="mode-step">{mode.step}</span>
              <span className="mode-text">
                <b>{mode.label}</b>
                <em>{mode.hint}</em>
              </span>
            </button>
          ))}
        </nav>

        <div className="topmeta">
          <button
            type="button"
            className="explain-toggle"
            aria-pressed={explain}
            title={
              explain
                ? "Hide the notes above each panel"
                : "Show the notes above each panel — what it is, and why it is here"
            }
            onClick={() => setExplain((v) => !v)}
          >
            Guide
          </button>
          {calculation && (
            <>
              <span className="topfigure mono">
                {formatMoneyCompact(
                  calculation.totals.cumulative,
                  calculation.totals.currency,
                )}
              </span>
              <span>engine {calculation.engine_version}</span>
              <span>FX {calculation.fx_snapshot_date}</span>
              <span>{calculation.duration_ms} ms</span>
            </>
          )}
        </div>
      </header>

      <div className="layout">
        <InputStudio
          draft={draft}
          onChange={setDraft}
          countries={countries}
          indications={indications}
          subgroups={subgroups}
          perspectives={perspectives}
          guide={guide}
          criteria={criteria}
          calculation={calculation}
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

          {workspace === "build" && (
            <>
              <div className="intro">
                <h2>Define the scenario on the left, then run it.</h2>
                {/* The heading is an instruction and always shows; the two
                    paragraphs below it are reasoning, so they follow the same
                    Explain control as every panel lede. */}
                <p className="lede-explain">
                  The inputs are in the order the model computes them — population,
                  epidemiology, eligibility, current care, the intervention, uptake,
                  behaviour, horizon, perspective. Every field explains itself where
                  it sits; the same explanation appears in the import template and
                  the exported workbook.
                </p>
                <p className="lede-explain">
                  Every figure that comes back carries the source it was resolved
                  from, its vintage and its confidence tier. Where a value is an
                  assumption rather than an observation, the result says so on the
                  figure rather than in a footnote.
                </p>
              </div>
              <MarketBurden countryCodes={draft.countryCodes} />
              {calculation && (
                <div className="intro-actions">
                  <button
                    type="button"
                    className="run"
                    onClick={() => setWorkspace("results")}
                  >
                    Back to the last result
                  </button>
                </div>
              )}
              <ScenarioCompare saved={saved} />
            </>
          )}

          {workspace === "prices" && (
            <>
              <PriceGrid
                prices={prices}
                edits={draft.priceEdits}
                loading={pricesLoading}
                onChange={(priceEdits) =>
                  setDraft((current) => ({ ...current, priceEdits }))
                }
                templateHref={api.priceTemplateUrl(
                  draft.indicationId,
                  draft.countryCodes,
                )}
              />
              <WorkbookPanel
                templateXlsx={api.templateUrl(
                  "xlsx",
                  draft.indicationId,
                  draft.countryCodes,
                )}
                templateCsv={api.templateUrl("csv", draft.indicationId, [])}
                onApply={applyImport}
              />
            </>
          )}

          {workspace === "comparators" && indications.length > 0 && (
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

          {workspace === "results" &&
            (calculation ? (
              <ResultsView
                calculation={calculation}
                owsa={owsa}
                psa={psa}
                gaps={gaps}
                bands={bands}
                breakEven={breakEven}
                uptakeCases={uptakeCases}
                analysisBusy={analysisBusy}
              />
            ) : (
              <Placeholder title="Nothing has been run yet">
                Define the scenario on the left and press Run.
              </Placeholder>
            ))}
          {workspace === "evitrack" && <EviTrack />}
        </main>
      </div>
    </div>
  );
}
