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

  calculate: (id: string, persist = false) =>
    request<Calculation>(`/api/v1/scenarios/${id}/calculate?persist=${persist}`, {
      method: "POST",
    }),

  owsa: (id: string) => request<Owsa>(`/api/v1/scenarios/${id}/owsa`),
  psa: (id: string, iterations = 4000) =>
    request<Psa>(`/api/v1/scenarios/${id}/psa?iterations=${iterations}`),
};
