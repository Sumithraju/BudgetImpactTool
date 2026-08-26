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
  totals: {
    by_year: number[];
    cumulative: number;
    peak_year: number;
    currency: string;
    /** The two worlds `by_year` is the difference of, in the reporting
     *  currency. Empty on a run made before these were carried. */
    without_by_year: number[];
    with_by_year: number[];
  };
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
  is_baseline: boolean;
  is_archived: boolean;
  overrides: OverrideItem[];
}

/** M19 — comparator workbook import. */
export type FindingSeverity = "error" | "warning";

export interface CellRef {
  sheet: string;
  cell: string;
  column_label: string | null;
  row_number: number | null;
}

export interface ImportFinding {
  severity: FindingSeverity;
  code: string;
  message: string;
  ref: CellRef | null;
  supplied: string | null;
  expected: string | null;
}

export interface ImportedComparator {
  name: string;
  therapy_type: string | null;
  country_code: string;
  currency_code: string;
  /** A fraction, already divided by 100 at the import boundary. */
  market_share: number;
  drug_cost: number;
  admin_cost: number;
  monitoring_cost: number;
  ae_cost: number;
  total_cost: number;
  source: string;
  confidence_tier: string;
  origin: string;
}

export interface ComparatorImportResult {
  accepted: boolean;
  filename: string;
  sheet: string;
  rows_read: number;
  findings: ImportFinding[];
  comparators: ImportedComparator[];
  share_totals: Record<string, number>;
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
      detail?.message ?? body?.error.message ?? response.statusText,
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

  /** Multipart, so this cannot go through `request` — a JSON content-type
   *  header would stop the browser writing the multipart boundary. The error
   *  envelope is still parsed the same way. */
  importComparators: async (file: File): Promise<ComparatorImportResult> => {
    const form = new FormData();
    form.append("file", file);
    const response = await fetch("/api/v1/comparators/import", {
      method: "POST",
      body: form,
    });
    if (!response.ok) {
      let body: ApiErrorBody | null = null;
      try {
        body = (await response.json()) as ApiErrorBody;
      } catch {
        // A non-JSON error body has no envelope to read.
      }
      throw new ApiError(
        body?.error.code ?? "HTTP_" + response.status,
        body?.error.message ?? response.statusText,
        body?.error.field ?? null,
        body?.request_id ?? "unknown",
      );
    }
    return (await response.json()) as ComparatorImportResult;
  },

  comparatorTemplateUrl: () => "/api/v1/comparators/import/template",
};
