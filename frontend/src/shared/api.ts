/**
 * The single place the frontend talks to the API.
 *
 * Every response type here mirrors a Pydantic schema in
 * `biet_api/schemas/`. Keeping them in one file means a contract change
 * surfaces as a TypeScript error in one place rather than as `undefined` at
 * runtime in five components.
 */

export interface Provenance {
  source: string;
  vintage_year: number | null;
  confidence_tier: string;
  resolution_level: string;
  is_projected: boolean;
  note: string | null;
}

export interface FunnelStage {
  stage: string;
  value: number;
  factor: number | null;
  provenance: Provenance | null;
}

export interface YearResult {
  year: number;
  calendar_year: number;
  uptake: number;
  addressable: number;
  patients_on_new: number;
  cost_without: number;
  cost_with: number;
  budget_impact: number;
  net_cost_per_switch: number;
  impact_per_patient: number | null;
}

export interface Criterion {
  code: string;
  label: string;
  factor: number;
  enabled: boolean;
  correlated_with: string[];
}

export interface Therapy {
  drug_id: number;
  name: string;
  is_new: boolean;
  unit_price: number;
  currency: string;
  price_basis: string;
  provenance: Provenance;
  persistence_12m: number;
}

export interface Affordability {
  cumulative_ratio: number;
  band: string;
  health_budget: number;
  pmpy: number | null;
}

export interface CountryResult {
  country_code: string;
  currency: string;
  cumulative_budget_impact: number;
  funnel: FunnelStage[];
  years: YearResult[];
  criteria: Criterion[];
  therapies: Therapy[];
  new_therapy: Therapy;
  affordability: Affordability | null;
  /** Year-invariant: persistence, substitution and unit costs do not vary by
   *  year, so one bridge explains every year's net cost per switch. */
  cost_bridge: CostBridge | null;
  /** M16 — what the spend buys in this market. */
  outcomes: Outcomes | null;
  /** M17 — this market's per-member view. */
  payer: PayerView | null;
  /** Prevalence and incidence, and the funnel with its arithmetic shown. */
  epidemiology: Epidemiology | null;
}

export interface Warning {
  code: string;
  message: string;
  country_code: string | null;
  parameter_path: string | null;
}

export interface Calculation {
  scenario_id: string;
  run_id: string | null;
  engine_version: string;
  reporting_currency: string;
  fx_snapshot_date: string;
  launch_year: number;
  horizon_years: number;
  countries: CountryResult[];
  totals: { by_year: number[]; cumulative: number; peak_year: number; currency: string };
  /** M18 — empty when the run covers the whole diagnosed population as one
   *  undifferentiated segment. */
  subgroups: SubgroupResult[];
  payer: PayerView | null;
  perspective: string | null;
  warnings: Warning[];
  duration_ms: number | null;
}

export interface OwsaEntry {
  parameter_path: string;
  label: string;
  base_value: number;
  low_value: number;
  high_value: number;
  result_at_low: number;
  result_at_high: number;
  swing: number;
  rank: number;
}

export interface Owsa {
  base_result: number;
  currency: string;
  entries: OwsaEntry[];
}

export interface Psa {
  currency: string;
  iterations: number;
  mean: number;
  median: number;
  p2_5: number;
  p97_5: number;
  histogram: number[];
  histogram_min: number;
  histogram_max: number;
  exceedance: Record<string, number>;
  converged: boolean;
}

export interface CorridorEntry {
  country_code: string;
  max_unit_price_usd: number | null;
  max_annual_acquisition_usd: number | null;
  feasible: boolean;
  unbounded: boolean;
  method: string;
  iterations: number | null;
  shortfall_usd: number | null;
}

export interface Corridor {
  target_ratio: number;
  entries: CorridorEntry[];
  /** The market that sets the ceiling — the corridor is only as wide as
   *  its narrowest market, so this is what a single global price must clear. */
  binding_market: string | null;
  single_global_price_ceiling_usd: number | null;
  warnings: Warning[];
}

export interface DiffEntry {
  parameter_path: string;
  country_code: string | null;
  values: Record<string, number | string | boolean | null>;
  resolution_levels: Record<string, string>;
}

export interface Comparison {
  scenario_ids: string[];
  indication_id: number;
  reporting_currency: string;
  results: Calculation[];
  diff: DiffEntry[];
}

export interface Citation {
  issuing_body: string;
  document_title: string;
  page_number: number | null;
  similarity: number;
  excerpt: string;
}

export interface Assumption {
  parameter_path: string;
  country_code: string | null;
  value: number;
  confidence_tier: string;
  source: string;
}

export interface NarrativeDoc {
  sections: Record<string, string>;
  limitations: string[];
  citations: Citation[];
  assumptions: Assumption[];
  /** Which path wrote the prose — the deterministic composer, or a model
   *  draft that passed numeric validation. The reader is entitled to know. */
  generated_by: string;
  warnings: string[];
}

/** M13 — one component's contribution to the net cost per switch. */
export interface BridgeTerm {
  component: string;
  new_therapy: number;
  displaced: number;
  delta: number;
}

export interface CostBridge {
  terms: BridgeTerm[];
  net_cost_per_switch: number;
}

/** M13 — what an expected adverse-event cost was computed from. */
export interface EventIncidenceRead {
  observed: number;
  annualised: number;
  exposure_weeks: number | null;
  population: string | null;
  evidence_type: string;
  source: string;
  source_url: string | null;
  vintage_year: number | null;
  confidence_tier: string;
}

export interface SafetyEventRow {
  ae_code: string;
  ae_label: string;
  is_serious: boolean;
  unit_cost: number | null;
  unit_cost_source: string | null;
  unit_cost_tier: string | null;
  by_drug: Record<string, EventIncidenceRead>;
}

export interface SafetyComparison {
  country_code: string;
  events: SafetyEventRow[];
}

/** M15 — what to go and find out, ranked. */
export interface EvidenceGap {
  parameter_path: string;
  label: string;
  swing: number;
  influence: number;
  confidence_tier: string;
  weakness: number;
  priority_score: number;
  priority: string;
  source: string;
  has_provenance: boolean;
}

export interface EvidenceGapReport {
  scenario_id: string;
  currency: string;
  max_swing: number;
  gaps: EvidenceGap[];
}

/** M16 — one event class, and what avoiding it is worth. */
export interface AvoidedEvent {
  event_class: string;
  label: string;
  trial: string;
  baseline_annual_rate: number;
  relative_reduction: number;
  events_without_by_year: number[];
  avoided_by_year: number[];
  cost_avoided_by_year: number[];
  total_avoided: number;
  total_cost_avoided: number;
  baseline_provenance: Provenance;
  effect_provenance: Provenance;
}

export interface Outcomes {
  country_code: string;
  currency: string;
  /** null, not zero, when no response profile was published — an absence of
   *  evidence and a finding of no responders are different claims. */
  responders_by_year: number[] | null;
  mean_weight_loss_pct: number | null;
  responder_threshold: string | null;
  responder_trial: string | null;
  regain_per_year: number | null;
  events: AvoidedEvent[];
  total_cost_avoided: number;
  total_cost_avoided_by_year: number[];
  warnings: Warning[];
}

/** M17 — the payer's own denominator. */
export interface PayerView {
  perspective: string;
  perspective_label: string;
  currency: string;
  covered_population: number;
  /** True when no covered population was supplied and the modelled one stood
   *  in. Rendered on the figure, never as a footnote: a PMPM against the
   *  wrong denominator looks entirely plausible. */
  covered_population_is_assumed: boolean;
  pmpm_by_year: number[];
  pmpy_by_year: number[];
  cumulative_pmpm: number;
  patients_treated_by_year: number[];
  cost_per_treated_patient: number;
  total_cost_current_care: number[];
  total_cost_with_intervention: number[];
}

export interface UptakeCase {
  case: string;
  label: string;
  multiplier: number;
  uptake_terminal: number;
  by_year: number[];
  cumulative: number;
  peak_year: number;
  patients_treated_final_year: number;
  currency: string;
}

export interface UptakeScenarios {
  currency: string;
  cases: UptakeCase[];
  warnings: Warning[];
}

export interface BreakEvenEntry {
  country_code: string;
  currency: string;
  current_unit_price: number;
  break_even_unit_price: number | null;
  current_annual_cost: number;
  break_even_annual_cost: number | null;
  headroom_pct: number | null;
  feasible: boolean;
  method: string;
  note: string | null;
}

export interface BreakEven {
  entries: BreakEvenEntry[];
  warnings: Warning[];
}

/** M18 — one segment's contribution to the total. */
export interface SubgroupResult {
  subgroup_code: string;
  subgroup_label: string;
  description: string | null;
  share_of_diagnosed: number;
  eligible_factor: number;
  uptake_multiplier: number;
  confidence_tier: string;
  source: string;
  currency: string;
  by_year: number[];
  cumulative: number;
  peak_year: number;
  addressable_final_year: number;
  patients_treated_final_year: number;
  net_cost_per_switch: number;
  total_events_avoided: number;
  total_cost_avoided: number;
  responders_final_year: number | null;
}

export interface SubgroupOption {
  subgroup_code: string;
  subgroup_label: string;
  description: string | null;
  share_of_diagnosed: number;
  eligible_factor: number;
  uptake_multiplier: number;
  confidence_tier: string;
  source: string;
  event_classes: string[];
  /** True when this subgroup shares patients with its siblings, so only one
   *  may be modelled at a time — the model refuses to add overlapping
   *  populations rather than double-counting the patients in both. */
  is_overlapping: boolean;
}

export interface PerspectiveOption {
  code: string;
  label: string;
  description: string;
  /** Whether this perspective's denominator is a subset of the nation, and so
   *  has to be supplied before any per-member figure means anything. */
  requires_covered_population: boolean;
}

/** One therapy's price in one market, observed or derived — and editable. */
export interface DrugPrice {
  drug_id: number;
  drug_name: string;
  is_new_asset: boolean;
  country_code: string;
  currency_code: string;
  unit_price: number;
  annual_cost: number;
  price_basis: string;
  is_observed: boolean;
  confidence_tier: string;
  source: string;
  source_url: string | null;
  vintage_year: number | null;
  /** Supplied by the API so no component ever builds an override path by
   *  string concatenation — a path outside the closed vocabulary is discarded
   *  silently, which is the failure the vocabulary exists to prevent. */
  parameter_path: string;
}

/** M19 — what a workbook parsed to, and everything wrong with it. */
export interface ImportIssue {
  sheet: string;
  row: number;
  column: string;
  value: string | null;
  message: string;
  severity: "error" | "warning";
}

export interface ImportedScenario {
  name: string | null;
  asset_name: string | null;
  indication_id: number | null;
  launch_year: number | null;
  horizon_years: number | null;
  reporting_currency: string | null;
  country_codes: string[];
  perspective: string | null;
  covered_population: number | null;
  subgroup_codes: string[];
  overrides: {
    parameter_path: string;
    /** Present when the value came from a per-market row. */
    country_code?: string | null;
    value: number;
    note?: string | null;
  }[];
  prices: {
    drug_id: number;
    country_code: string;
    unit_price: number | null;
    annual_cost: number | null;
    note: string | null;
  }[];
}

export interface ImportResult {
  scenario: ImportedScenario;
  issues: ImportIssue[];
  rows_read: number;
  accepted: boolean;
}

/** The field dictionary — one description of each input, shared by the hover
 *  text here, the import template, and the exported workbook. */
export interface FieldSpec {
  key: string;
  label: string;
  description: string;
  effect: string | null;
  unit: string;
  parameter_path: string | null;
  example: string | null;
  typical_range: string | null;
}

export interface FieldGroup {
  key: string;
  label: string;
  summary: string;
  fields: FieldSpec[];
}

/** A published burden figure, carrying the unit it is actually in. */
export interface HealthIndicator {
  country_code: string;
  indicator: string;
  /** prevalence | incidence | coverage | policy — never inferred from the
   *  name. A prevalence and an incidence differ by more than an order of
   *  magnitude for a persistent condition, and reading one as the other is the
   *  commonest error an epidemiology panel makes. */
  kind: string;
  label: string;
  value: number | null;
  per_100k: number | null;
  source: string;
  source_url: string | null;
  vintage_year: number | null;
  confidence_tier: string;
}

/** One funnel step, with the multiplication that produced it. */
export interface FunnelStep {
  stage: string;
  label: string;
  definition: string;
  value: number;
  factor: number | null;
  factor_label: string | null;
  /** The step written out — "8,519,657 x 12.0% = 1,022,359". A funnel that
   *  shows only its outputs cannot be checked, and checking it is the whole
   *  reason a budget impact model shows one. */
  working: string | null;
  provenance: Provenance | null;
}

export interface Epidemiology {
  country_code: string;
  country_name: string;
  population_total: number;
  adult_population: number;
  /** PREVALENCE — the share who have the condition now. */
  prevalence: number;
  prevalent_cases: number;
  prevalence_low: number | null;
  prevalence_high: number | null;
  /** INCIDENCE — the share who newly acquire it each year. Kept apart from
   *  prevalence deliberately; they are different quantities in different
   *  units. */
  incidence_annual: number | null;
  incidence_per_100k: number | null;
  incident_cases_per_year: number | null;
  diagnosed_cases: number;
  eligible_cases: number;
  treated_cases: number;
  funnel: FunnelStep[];
  indicators: HealthIndicator[];
}

export interface CountryOption {
  country_code: string;
  country_name: string;
  currency_code: string;
  region: string | null;
  adult_share: number | null;
}

export interface IndicationOption {
  indication_id: number;
  indication_name: string;
  therapy_area: string;
}

export interface OverrideItem {
  country_code?: string | null;
  parameter_path: string;
  value: number | string | boolean | number[];
  note?: string | null;
}

export interface Scenario {
  scenario_id: string;
  name: string;
  indication_id: number;
  asset_name: string;
  launch_year: number;
  horizon_years: number;
  reporting_currency: string;
  country_codes: string[];
  perspective: string;
  covered_population: number | null;
  subgroup_codes: string[];
  is_baseline: boolean;
  is_archived: boolean;
  overrides: OverrideItem[];
}

/** The API's error envelope — one shape for every non-2xx response. */
interface ApiErrorBody {
  error: { code: string; message: string; field?: string | null };
  details?: { message: string; field?: string | null }[];
  request_id: string;
}

export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly field: string | null,
    readonly requestId: string,
  ) {
    super(message);
  }
}

/**
 * Something a person can act on, for a response that carried no message.
 *
 * `response.statusText` is the HTTP reason phrase — "Internal Server Error",
 * "Bad Gateway" — and putting it on screen tells a market-access reader that
 * something broke without telling them whether it was their input, their
 * network, or the tool. These say which, and what to do next.
 */
function statusMessage(status: number): string {
  if (status === 0) {
    return "The tool could not be reached. Check that it is still running.";
  }
  if (status === 401 || status === 403) {
    return "You do not have access to that. Check your sign-in and try again.";
  }
  if (status === 404) {
    return "That is not available. It may have been removed, or the link may be out of date.";
  }
  if (status === 408 || status === 504) {
    return "That took too long and was stopped. Try a smaller market set, or try again.";
  }
  if (status === 413) {
    return "That file is too large to read. Try a smaller one.";
  }
  if (status === 429) {
    return "Too many requests at once. Wait a moment and try again.";
  }
  if (status === 503) {
    return "An external data source is unavailable right now. This is usually temporary — try again shortly. Everything not relying on it still works.";
  }
  if (status >= 500) {
    return "Something went wrong at our end, so this step did not complete. Nothing was saved. Try again, and if it keeps happening the run details are in the server log.";
  }
  return "That request could not be completed.";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });

  if (!response.ok) {
    let body: ApiErrorBody | null = null;
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      // A non-JSON error body (a proxy 502, say) has no envelope to read.
    }
    // Prefer the first field-level detail: on a validation failure it names
    // the offending field, which the top-level message does not.
    const detail = body?.details?.[0];
    throw new ApiError(
      body?.error.code ?? "HTTP_" + response.status,
      detail?.message ?? body?.error.message ?? statusMessage(response.status),
      detail?.field ?? body?.error.field ?? null,
      body?.request_id ?? "unknown",
    );
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** M11 — one discovered molecule and why it scored what it scored. */
export interface ScoreFactor {
  name: string;
  weight: number;
  matched: boolean;
}

export interface DiscoveredDrug {
  source_id: string;
  name: string;
  drug_type: string | null;
  max_clinical_stage: string;
  mechanism_of_action: string | null;
  action_type: string | null;
  target_symbol: string;
  indications: string[];
  competitor_class: string;
  relevance: number;
  rationale: string;
  seeded_drug_id: number | null;
  /** No price and no regimen, so it cannot enter a calculation yet
   *  (M11 section 5.7). Rendered distinctly wherever it appears. */
  needs_pricing: boolean;
  sources: string[];
  pathway_ids: string[];
  factors: ScoreFactor[];
}

export interface ComparatorWarning {
  code: string;
  message: string;
}

export interface ComparatorBasket {
  target_symbol: string;
  target_id: string;
  indication_id: number;
  indication_name: string;
  mechanism: string | null;
  pathway_ids: string[];
  direct: DiscoveredDrug[];
  therapeutic: DiscoveredDrug[];
  pipeline: DiscoveredDrug[];
  excluded: DiscoveredDrug[];
  warnings: ComparatorWarning[];
}

export interface ResolvedTarget {
  symbol: string;
  target_id: string;
  uniprot_accession: string | null;
  pathway_ids: string[];
}

/** M12 — the registry record for one molecule in one indication. */
export interface MarketApproval {
  country_code: string;
  approval_year: number | null;
  is_reimbursed: boolean | null;
  source: string;
  confidence_tier: string;
}

export interface RegisteredAsset {
  asset_id: number;
  source_id: string;
  asset_name: string;
  indication_id: number;
  target_symbol: string;
  mechanism_of_action: string | null;
  action_type: string | null;
  pathway_ids: string[];
  max_clinical_stage: string;
  competitor_class: string;
  relevance: number;
  rationale: string;
  brand_name: string | null;
  manufacturer: string | null;
  line_of_therapy: string | null;
  sponsor: string | null;
  expected_entry_year: number | null;
  is_new_asset: boolean;
  drug_id: number | null;
  is_promoted: boolean;
  /** Named per market — "price:DEU", not a single boolean. */
  missing_for_promotion: string[];
  source: string;
  confidence_tier: string;
  approvals: MarketApproval[];
}

export interface PromotionRequest {
  regimen: {
    dose_amount: number;
    dose_unit: string;
    units_per_admin: number;
    admins_per_year: number;
    wastage_pct: number;
    persistence_12m: number;
    source: string;
    confidence_tier: string;
  };
  prices: {
    country_code: string;
    price_local: number;
    currency_code: string;
    price_basis: string;
    source: string;
    confidence_tier: string;
  }[];
}

export const api = {
  countries: () => request<CountryOption[]>("/api/v1/reference/countries"),
  indications: () => request<IndicationOption[]>("/api/v1/reference/indications"),
  parameterPaths: () => request<string[]>("/api/v1/reference/parameter-paths"),

  createScenario: (body: unknown) =>
    request<Scenario>("/api/v1/scenarios", { method: "POST", body: JSON.stringify(body) }),

  replaceOverrides: (id: string, overrides: OverrideItem[]) =>
    request<Scenario>(`/api/v1/scenarios/${id}/overrides`, {
      method: "PUT",
      body: JSON.stringify({ overrides }),
    }),

  /** `projectLandscape` admits M14's pipeline entrants into the
   *  world-without. Off by default and never implicit — it changes what the
   *  new asset is compared against, on assumptions the evidence does not
   *  supply. */
  calculate: (id: string, persist = false, projectLandscape = false) =>
    request<Calculation>(
      `/api/v1/scenarios/${id}/calculate?persist=${persist}` +
        `&project_landscape=${projectLandscape}`,
      { method: "POST" },
    ),

  owsa: (id: string) => request<Owsa>(`/api/v1/scenarios/${id}/owsa`),

  evidenceGaps: (id: string) =>
    request<EvidenceGapReport>(`/api/v1/scenarios/${id}/evidence-gaps`),

  affordabilityBands: () =>
    request<Record<string, number>>("/api/v1/reference/affordability-bands"),

  subgroups: (indicationId: number) =>
    request<SubgroupOption[]>(
      `/api/v1/reference/subgroups?indication_id=${indicationId}`,
    ),

  perspectives: () => request<PerspectiveOption[]>("/api/v1/reference/perspectives"),

  /** WHO's burden figures for a market set, before any run — so the build
   *  screen can show what a scenario rests on while it is being defined. */
  marketEpidemiology: (countryCodes: string[]) => {
    const q = new URLSearchParams();
    for (const code of countryCodes) q.append("country_codes", code);
    return request<HealthIndicator[]>(`/api/v1/reference/epidemiology?${q}`);
  },

  /** The whole therapy x market price grid, including the cells with no
   *  observed price — those carry the derivation the engine would use, and
   *  are the ones worth an analyst's attention first. */
  prices: (indicationId: number, countryCodes: string[]) => {
    const q = new URLSearchParams({ indication_id: String(indicationId) });
    for (const code of countryCodes) q.append("country_codes", code);
    return request<DrugPrice[]>(`/api/v1/reference/prices?${q}`);
  },

  /** One description of each input, served rather than duplicated here — the
   *  same string appears in the import template and the exported workbook. */
  fieldGuide: () => request<FieldGroup[]>("/api/v1/workbook/field-guide"),

  breakEven: (id: string) => request<BreakEven>(`/api/v1/scenarios/${id}/break-even`),

  uptakeScenarios: (id: string) =>
    request<UptakeScenarios>(`/api/v1/scenarios/${id}/uptake-scenarios`),

  /** Templates are hrefs, not fetches — letting the browser navigate keeps the
   *  Content-Disposition filename, which a blob download would discard. */
  templateUrl: (
    format: "xlsx" | "csv",
    indicationId: number,
    countryCodes: string[],
  ) => {
    const q = new URLSearchParams({ indication_id: String(indicationId) });
    for (const code of countryCodes) q.append("country_codes", code);
    return `/api/v1/workbook/template.${format}?${q}`;
  },

  priceTemplateUrl: (indicationId: number, countryCodes: string[]) => {
    const q = new URLSearchParams({ indication_id: String(indicationId) });
    for (const code of countryCodes) q.append("country_codes", code);
    return `/api/v1/workbook/prices.csv?${q}`;
  },

  /** Returns a parsed draft; nothing is saved. The caller shows what the file
   *  was read as, then creates the scenario through the ordinary endpoint so
   *  an imported scenario passes exactly the validation a typed one does. */
  importWorkbook: async (file: File): Promise<ImportResult> => {
    const body = new FormData();
    body.append("file", file);
    // No content-type header: the browser sets the multipart boundary, and
    // overriding it here produces a body the server cannot split.
    const response = await fetch("/api/v1/workbook/import", { method: "POST", body });
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as {
        error?: { code: string; message: string; field?: string | null };
        request_id?: string;
      } | null;
      throw new ApiError(
        payload?.error?.code ?? `HTTP_${response.status}`,
        payload?.error?.message ?? statusMessage(response.status),
        payload?.error?.field ?? null,
        payload?.request_id ?? "unknown",
      );
    }
    return (await response.json()) as ImportResult;
  },

  solve: (id: string, targetRatio: number) =>
    request<Corridor>(`/api/v1/scenarios/${id}/solve`, {
      method: "POST",
      body: JSON.stringify({ target_ratio: targetRatio }),
    }),

  narrative: (id: string) => request<NarrativeDoc>(`/api/v1/scenarios/${id}/narrative`),

  /** Export URLs are hrefs, not fetches — letting the browser navigate keeps
   *  the Content-Disposition filename, which a blob download would discard. */
  exportUrl: (id: string, format: "pdf" | "pptx" | "xlsx") =>
    `/api/v1/scenarios/${id}/export.${format}`,

  compare: (scenarioIds: string[]) =>
    request<Comparison>("/api/v1/scenarios/compare", {
      method: "POST",
      body: JSON.stringify({ scenario_ids: scenarioIds }),
    }),
  psa: (id: string, iterations = 4000) =>
    request<Psa>(`/api/v1/scenarios/${id}/psa?iterations=${iterations}`),

  listAssets: (indicationId: number) =>
    request<RegisteredAsset[]>(
      `/api/v1/comparators/assets?indication_id=${indicationId}`,
    ),

  /** Idempotent on (source_id, indication_id): registering a molecule
   *  discovery returned twice is ordinary, not a conflict. */
  registerAsset: (intake: unknown) =>
    request<RegisteredAsset>("/api/v1/comparators/assets", {
      method: "POST",
      body: JSON.stringify(intake),
    }),

  promoteAsset: (assetId: number, body: PromotionRequest) =>
    request<RegisteredAsset>(`/api/v1/comparators/assets/${assetId}/promote`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  safetyComparison: (countryCode: string, drugIds: number[]) => {
    const q = new URLSearchParams({ country_code: countryCode });
    for (const id of drugIds) q.append("drug_ids", String(id));
    return request<SafetyComparison>(`/api/v1/comparators/safety?${q}`);
  },

  resolveTarget: (symbol: string) =>
    request<ResolvedTarget>(`/api/v1/comparators/targets/${encodeURIComponent(symbol)}`),

  /** Pathway expansion is opt-in because it costs several seconds of extra
   *  round trips — it is the only way to find a competitor acting on a
   *  different target, and not every query needs one. */
  discover: (
    target: string,
    indicationId: number,
    mechanism: string | null,
    includePathway: boolean,
  ) => {
    const q = new URLSearchParams({
      target,
      indication_id: String(indicationId),
      include_pathway: String(includePathway),
    });
    if (mechanism) q.set("mechanism", mechanism);
    return request<ComparatorBasket>(`/api/v1/comparators/discover?${q}`);
  },
};
