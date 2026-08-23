---
name: biet-frontend
description: "Engineering standards for BIET frontend work — React 18, TypeScript, Vite, TanStack Query, Zustand, Tailwind, Recharts and Plotly. Use whenever writing, reviewing, or refactoring anything under frontend/ — feature slices, components, hooks, API client usage, charts, forms, routing, or frontend tests. Covers the feature-sliced architecture and its import boundaries, naming conventions, generated API types, state-management selection, constants instead of literals, formatting and provenance display rules, DRY and component reuse, and the definition of done. Do NOT use for backend work — see biet-backend."
---

# BIET Frontend Engineering Standards

Authority: [docs/ARCHITECTURE.md](../../../docs/ARCHITECTURE.md) §11. This skill is *how* to build what that section specifies. Where the two disagree, the architecture document wins and this skill gets fixed.

---

## 1. Feature-sliced architecture

There is no Module Federation. Modularity is structural and enforced at build time (ARCHITECTURE.md §3.3).

```
src/
├── app/              # shell, router, providers, layout — composition root
├── features/         # one directory per feature slice
│   └── <slice>/
│       ├── components/
│       ├── hooks/
│       ├── api/          # queries/mutations for this slice
│       ├── constants.ts
│       ├── types.ts
│       └── index.ts      # the slice's ONLY public surface
└── shared/           # cross-slice primitives
    ├── api/          # generated client, base query config
    ├── components/   # design-system primitives
    ├── charts/       # themed chart wrappers
    ├── hooks/
    ├── constants/
    ├── types/        # generated from OpenAPI
    └── utils/
```

### Import boundaries

Enforced by `eslint-plugin-boundaries`. A violation fails the build.

| From | May import |
|---|---|
| `features/<slice>` | `shared/**`, its own internals |
| `features/<slice>` | **NOT** another slice's internals — only `features/<other>` via its `index.ts`, and only when genuinely unavoidable |
| `shared/**` | `shared/**` only. Never a feature. |
| `app/**` | Anything |
| anything | **NOT** `app/**` |

Cross-slice communication goes through the scenario store, route state, or `shared/`. If two slices need the same component, it moves to `shared/components/` — it does not get imported sideways.

Every slice exports through `index.ts`. Deep imports like `features/price-solver/components/CorridorChart` from outside the slice are forbidden.

---

## 2. API types are generated, never hand-written

Types come from the backend OpenAPI schema. Hand-writing a response interface guarantees drift.

```bash
npm run generate:api    # openapi-typescript → src/shared/types/api.ts
```

```ts
// WRONG — hand-rolled, will silently diverge
interface CalculationResponse { countries: { code: string; impact: number }[] }

// RIGHT
import type { components } from '@/shared/types/api';
type CalculationResponse = components['schemas']['CalculationResponse'];
```

`src/shared/types/api.ts` is generated output. Never edit it by hand. If a type is wrong, fix the backend schema and regenerate.

---

## 3. State management — pick by class, not by habit

| State | Mechanism | Example |
|---|---|---|
| Server data | TanStack Query | reference data, calculation results, run history |
| Scenario draft (unsaved, cross-slice) | Zustand `useScenarioStore` | in-progress assumption edits |
| Ephemeral UI | `useState` | modal open, accordion expanded |
| Navigational | React Router search params | active scenario, tab, selected markets |

Rules:

- **Never** copy server data into Zustand or `useState`. Derive from the query result.
- **Never** use `useEffect` to sync state that could be derived during render.
- Query keys are built by factory functions in `shared/api/queryKeys.ts` — never inline string arrays.

```ts
// shared/api/queryKeys.ts
export const queryKeys = {
  countries: () => ['reference', 'countries'] as const,
  scenario: (id: string) => ['scenarios', id] as const,
  calculation: (id: string, hash: string) => ['scenarios', id, 'calculate', hash] as const,
} as const;
```

### Debounced recalculation

Slider and numeric inputs call `POST /calculate` through a shared hook with a 250 ms trailing debounce, cancellation on supersession, and retention of the previous result while in flight (ARCHITECTURE.md §11.4).

**Do not reimplement engine arithmetic in TypeScript.** The server is the single source of truth. A client-side mirror will diverge from the engine and produce two different answers to the same question — which destroys the auditability the whole system exists to provide. If latency is a problem, fix the endpoint.

---

## 4. Constants — no literals in components

```
shared/constants/
├── index.ts
├── domain.ts       # enums mirroring backend StrEnums
├── formatting.ts   # precision, locales
├── charts.ts       # palette, dimensions, axis config
└── routes.ts       # route paths
```

```ts
// domain.ts — mirrors the backend enums exactly
export const AFFORDABILITY_BAND = {
  LOW: 'low', MODERATE: 'moderate', HIGH: 'high', CRITICAL: 'critical',
} as const;
export type AffordabilityBand = typeof AFFORDABILITY_BAND[keyof typeof AFFORDABILITY_BAND];

export const CONFIDENCE_TIER = { A: 'A', B: 'B', C: 'C', D: 'D' } as const;

export const FUNNEL_STAGE_LABELS: Record<FunnelStage, string> = {
  total_population: 'Total population',
  adult_population: 'Adult population',
  diseased: 'Diseased',
  diagnosed: 'Diagnosed',
  treated: 'Treated',
  label_eligible: 'Label-eligible',
  addressable: 'Addressable',
};
```

No colour hex codes, spacing values, thresholds, route strings, or display labels inline in a component. Colours come from Tailwind tokens or `constants/charts.ts`. Route paths come from `constants/routes.ts`.

```tsx
// WRONG
<Link to={`/scenarios/${id}/results`} className="text-[#2E5C8A]">

// RIGHT
<Link to={routes.scenarioResults(id)} className="text-brand-accent">
```

---

## 5. Formatting and domain display rules

All formatting goes through `shared/utils/format.ts`. Never call `toFixed`, `toLocaleString`, or string-concatenate a currency symbol in a component.

```ts
export const formatMoney = (amount: number, currency: string, opts?) => ...
export const formatPercent = (fraction: number, dp = 1) => ...   // takes 0–1, not 0–100
export const formatCount = (n: number) => ...
export const formatCompact = (n: number) => ...                  // 2.8B, 331M
```

Domain rules that mirror the backend invariants:

| Rule | Detail |
|---|---|
| **Rates are fractions** | State holds `0.0–1.0`. `formatPercent` is the only place that multiplies by 100. A slider bound 0–100 converts at the boundary, not in state. |
| **Money needs a currency** | Never render an amount without its currency code from the response. Never hardcode `$`. |
| **Years are launch-relative** | Display `Year 1 (2028)` — the response carries both `year` and `calendar_year`. Never compute calendar year in the client. |
| **Provenance is visible** | Every displayed input shows source, vintage and confidence tier. Use `<ProvenanceBadge>` from `shared/components`. Dropping provenance from a display is a product defect, not a styling choice. |
| **Resolution level is visible** | Show whether a value came from global default, country override or scenario override (ARCHITECTURE.md §7.3). Use `<ResolutionIndicator>`. |
| **Warnings surface** | Render `warnings[]` from the response. A `STALE_VINTAGE` warning must reach the user, not just the console. |

---

## 6. Components

- **Function components only.** No classes.
- One component per file. File name matches the export.
- Props typed with an explicit `interface`, not inline. No `React.FC`.
- Destructure props in the signature.
- Keep components under ~150 lines. Past that, extract subcomponents or move logic to a hook.
- Business logic lives in hooks; components render.

```tsx
interface FunnelChartProps {
  stages: FunnelStage[];
  currency: string;
  onStageClick?: (stage: FunnelStageName) => void;
}

export function FunnelChart({ stages, currency, onStageClick }: FunnelChartProps) { ... }
```

### Required states

Every component that reads server data handles all four. A component that only handles the success path is incomplete.

```tsx
if (isLoading) return <Skeleton variant="chart" />;
if (isError)   return <ErrorState error={error} onRetry={refetch} />;
if (!data?.countries.length) return <EmptyState message={EMPTY.NO_MARKETS} />;
return <Results data={data} />;
```

### Charts

Never import Recharts or Plotly directly in a feature slice. Use the wrappers in `shared/charts/`, which apply the shared palette, axis formatting, tooltip style and responsive container. This is what keeps eight visualisations looking like one product.

---

## 7. Error and response handling

Handled **centrally, once**. No `fetch` in a component. No `try`/`catch` around a query. No
hand-written error strings. If you are shaping an error message in a component, it belongs here.

### 7.1 The typed error

The backend returns one error envelope for every non-2xx (`biet-backend` §8.3). The API client
parses it into a single error type; nothing downstream ever touches a raw `Response`.

```ts
// shared/api/errors.ts
export interface ErrorDetail {
  code: string;
  message: string;
  field?: string;
  context?: Record<string, unknown>;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: ErrorDetail[] = [],
    readonly requestId?: string,
  ) { super(message); this.name = 'ApiError'; }

  get isValidation() { return this.status === 422; }
  get isNotFound()   { return this.status === 404; }
  get isRetryable()  { return this.status >= 500 || this.status === 0; }

  /** Field path -> message, for binding server errors back onto a form. */
  get fieldErrors(): Record<string, string> {
    return Object.fromEntries(
      this.details.filter(d => d.field).map(d => [d.field!, d.message]),
    );
  }
}
```

### 7.2 One client, one parse point

```ts
// shared/api/client.ts
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(
      res.status,
      body?.error?.code ?? ERROR_CODE.UNKNOWN,
      body?.error?.message ?? 'Request failed.',
      body?.details ?? [],
      body?.request_id ?? res.headers.get('X-Request-ID') ?? undefined,
    );
  }
  return res.status === 204 ? (undefined as T) : res.json();
}
```

Every query and mutation goes through this. A `fetch` anywhere else is a defect.

### 7.3 Error codes and messages are a shared registry

Codes mirror the backend `ErrorCode` enum exactly. Messages live in one map so wording is
consistent and translatable, and so a code the frontend has never seen still renders sensibly.

```ts
// shared/constants/errors.ts
export const ERROR_CODE = {
  UNKNOWN: 'UNKNOWN',
  ENTITY_NOT_FOUND: 'ENTITY_NOT_FOUND',
  VALIDATION_FAILED: 'VALIDATION_FAILED',
  CONFLICT: 'CONFLICT',
  UPSTREAM_UNAVAILABLE: 'UPSTREAM_UNAVAILABLE',
  FUNNEL_NOT_MONOTONIC: 'FUNNEL_NOT_MONOTONIC',
  UNRESOLVED_PARAMETER: 'UNRESOLVED_PARAMETER',
  CURRENCY_MISMATCH: 'CURRENCY_MISMATCH',
  SOLVER_INFEASIBLE: 'SOLVER_INFEASIBLE',
} as const;

export const ERROR_MESSAGES: Record<string, string> = {
  [ERROR_CODE.ENTITY_NOT_FOUND]: 'That scenario no longer exists.',
  [ERROR_CODE.UPSTREAM_UNAVAILABLE]:
    'The narrative service is unavailable. Results and exports still work.',
  [ERROR_CODE.FUNNEL_NOT_MONOTONIC]:
    'A funnel factor is greater than 1. Check that rates are entered as fractions.',
  [ERROR_CODE.SOLVER_INFEASIBLE]:
    'No non-negative price meets this affordability target.',
  [ERROR_CODE.UNRESOLVED_PARAMETER]:
    'A required assumption has no value for one of the selected markets.',
};

export const messageFor = (e: ApiError) =>
  ERROR_MESSAGES[e.code] ?? e.message ?? 'Something went wrong.';
```

Never write a user-facing error string inside a component.

### 7.4 Query client defaults

Retry policy and global handling are configured once, not per call.

```ts
// app/providers.tsx
new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, err) => err instanceof ApiError && err.isRetryable && count < 2,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
    mutations: {
      onError: (err) => toast.error(messageFor(err as ApiError)),
    },
  },
});
```

**Never retry a 4xx.** A 422 will fail identically every time; retrying it delays the error the
user needs to see.

### 7.5 Where each error surfaces

Match the surface to the failure. Getting this wrong is the most common UX defect in this area.

| Failure | Surface |
|---|---|
| Query fails (data cannot load) | Inline `<ErrorState>` in place of the content, with retry |
| Mutation fails (an action did not complete) | Toast, and keep the user's input on screen |
| 422 with `fieldErrors` | Bind onto the offending form fields via `setError`; do **not** toast |
| 404 on the primary resource | Route-level not-found view |
| 503 on narrative/copilot | Inline degraded notice; the rest of the page keeps working |
| Render crash | Error boundary |

`<ErrorState>` is a single shared component taking `error` and `onRetry`. It shows the mapped
message and, for 5xx, the `requestId` so a user can quote it in a bug report.

### 7.6 Error boundaries

One boundary per route in `app/`, plus one around each chart region. A Plotly failure on the
tornado must not blank the results page.

### 7.7 Warnings are not errors

`warnings[]` in a successful calculation response (`biet-backend` §8.6) is data, rendered as
informational notices — never as errors, never swallowed, never console-only.

```tsx
<WarningList warnings={data.warnings} />
```

`STALE_VINTAGE`, `PROJECTED_VALUE`, `TIER_D_INPUT`, `UNPRICED_MARKET` and `SUBSTITUTION_FLOOR` each
map to a message in `shared/constants/warnings.ts` and, where they carry a `country_code` or
`parameter_path`, link to the input that caused them.

### 7.8 Rules

- No `fetch` outside `shared/api/client.ts`.
- No `try`/`catch` in a component; use the query/mutation error state.
- No error string literals in components; use `messageFor`.
- Never render a raw error object, stack, or JSON body to the user.
- Never swallow an error to keep the UI tidy — an empty chart with no explanation is worse than an
  error message.

## 8. DRY and reuse

- A component used by two slices moves to `shared/components/`.
- A formatting or calculation helper used twice moves to `shared/utils/`.
- Repeated query logic becomes a shared hook.
- Repeated Tailwind class strings become a variant via `cva` or a shared component — not a copy-pasted string.

Extract on the **second** occurrence. Do not build an abstraction for a single call site.

---

## 9. Naming

| Thing | Convention | Example |
|---|---|---|
| Component file & export | `PascalCase` | `FunnelChart.tsx` → `FunnelChart` |
| Hook file & export | `camelCase`, `use` prefix | `useScenarioCalculation.ts` |
| Non-component module | `camelCase` | `formatCurrency.ts`, `queryKeys.ts` |
| Slice directory | `kebab-case` | `price-solver/`, `population-funnel/` |
| Type / interface | `PascalCase`, no `I` prefix | `ScenarioDraft`, `FunnelChartProps` |
| Constant | `UPPER_SNAKE_CASE` | `PSA_DEFAULT_ITERATIONS` |
| Boolean prop | `is` / `has` / `should` | `isLoading`, `hasOverride` |
| Event handler prop | `on` + event | `onStageClick` |
| Handler implementation | `handle` + event | `handleStageClick` |
| Test file | Adjacent `.test.tsx` | `FunnelChart.test.tsx` |

Domain vocabulary matches Appendix A of the architecture document. `addressable`, `persistence`, `budgetImpact`, `affordabilityRatio` — the same words the API and the engine use.

---

## 10. Forms

React Hook Form + Zod. Zod schemas mirror the backend Pydantic constraints and live in the slice's `types.ts`.

```ts
export const scenarioSchema = z.object({
  name: z.string().min(1).max(200),
  horizonYears: z.number().int().min(1).max(5),
  countryCodes: z.array(z.string().length(3)).min(1),
});
```

Client validation is for responsiveness only. The server validates authoritatively; never assume client validation is sufficient.

---

## 11. TypeScript quality

- `strict: true`. No `any` — use `unknown` and narrow.
- No non-null assertion `!` without an adjacent comment justifying it.
- No `@ts-ignore`; `@ts-expect-error` with an explanation if genuinely unavoidable.
- Prefer `type` for unions, `interface` for object shapes.
- Path alias `@/` for `src/`. No `../../../` chains.

---

## 12. Testing

Vitest + React Testing Library. Test behaviour, not implementation.

- Query by role and accessible name, not by test id or class.
- Mock at the network boundary with MSW, not by mocking hooks.
- Every slice has at least: renders with data, renders loading, renders error, and its primary interaction.
- Formatting utilities have unit tests — especially `formatPercent`, given the fraction convention.

---

## 13. Accessibility baseline

- Semantic elements. A clickable element is a `<button>`, not a `<div onClick>`.
- Every input has an associated `<label>`.
- Charts carry a text alternative or an accompanying data table — a screen-reader user must be able to reach the numbers.
- Colour is never the sole carrier of meaning; affordability bands pair colour with a text label.
- Visible focus states. Keyboard reachable.

---

## 14. Definition of done

- [ ] Slice boundaries respected; ESLint boundary rules pass
- [ ] API types generated, not hand-written
- [ ] No magic strings, hex colours, thresholds, or route literals in components
- [ ] Rates held as fractions; all formatting via `shared/utils/format.ts`
- [ ] Provenance, resolution level and response warnings surfaced
- [ ] Loading, error and empty states handled
- [ ] All requests through `shared/api/client.ts`; no stray `fetch`
- [ ] Errors surfaced by the §7.5 table; 422s bound to form fields, not toasted
- [ ] No error strings in components; new codes added to the shared registry
- [ ] Response `warnings[]` rendered, not swallowed
- [ ] Charts use `shared/charts/` wrappers
- [ ] No engine arithmetic reimplemented client-side
- [ ] `tsc --noEmit` and `eslint` clean; no `any`
- [ ] Tests added for the new behaviour
- [ ] Keyboard reachable, labelled, focus-visible
