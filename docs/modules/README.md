# BIET Module Specifications

One specification per module. Each is self-contained enough to be assigned to one engineer and
built without further clarification.

**Authority chain.** [ARCHITECTURE.md](../ARCHITECTURE.md) defines *what* the system is. These
specs define *what each module does in detail*. The `biet-backend` and `biet-frontend` skills
define *how to write the code*. Where they conflict, the architecture document wins.

## Index

| Spec | Module | Owner area | Depends on |
|---|---|---|---|
| [M0](M0-data-foundation.md) | Data Foundation & Ingestion | Data | — |
| [M1](M1-scenario-workspace.md) | Scenario Workspace | Backend + Frontend | M0 |
| [M2](M2-population-funnel.md) | Population Funnel Engine | Engine | M0 |
| [M3](M3-eligibility-segmentation.md) | Eligibility & Segmentation | Engine | M0, M2 |
| [M4](M4-uptake-market-mix.md) | Uptake & Market Mix | Engine | M2, M3 |
| [M5](M5-cost-pricing.md) | Cost & Pricing Engine | Engine | M0 |
| [M6](M6-persistence.md) | Persistence & Adherence | Engine | — |
| [M7](M7-budget-impact.md) | Budget Impact Calculator | Engine | M2–M6 |
| [M8](M8-affordability-solver.md) | Affordability & Price Solver | Engine | M5, M7 |
| [M9](M9-uncertainty-sensitivity.md) | Uncertainty & Sensitivity | Engine | M7, M8 |
| [M10](M10-evidence-narrative-export.md) | Evidence, Narrative & Export | Backend + AI | M7–M9 |

### Comparator intelligence (Phases 7–11)

M0–M10 assume the comparator set is known. These five remove that assumption. See
ARCHITECTURE.md §4A for the requirement coverage map.

| Spec | Module | Owner area | Depends on |
|---|---|---|---|
| [M11](M11-comparator-discovery.md) | Comparator Discovery | Data + Backend | M0, M4, M5 |
| [M12](M12-comparator-registry.md) | Comparator Registry & Asset Intake | Backend + Data | M0, M5, M11 |
| [M13](M13-safety-ae-economics.md) | Safety & Adverse-Event Economics | Engine + Backend | M5, M7, M12 |
| [M14](M14-launch-year-landscape.md) | Launch-Year Competitive Landscape | Engine + Backend | M4, M11, M12 |
| [M15](M15-evidence-gap-intelligence.md) | Evidence-Gap Intelligence | Backend | M9, M10 |

## Build order

```
M0 ──┬── M1 ──────────────────────────────┐
     ├── M2 ── M3 ──┐                      │
     ├── M5 ────────┼── M4 ── M7 ── M8 ──┬─┴── M10
     └───────────── M6 ──┘                └── M9
```

M0 blocks everything. M6 is independent and can be built first by anyone as a warm-up — it is
a single closed-form function with no dependencies.

Comparator intelligence layers on top, and its own order is close to a straight line — each module
needs the previous one's output to be worth building:

```
M11 ── M12 ──┬── M13 ── (M5, M7)
             └── M14 ── (M4, M7)

M9 ── M15
```

M12 is the hinge. Until a discovered molecule can be promoted into a priced comparator, M13 has
nothing to attach a safety profile to and M14 has nothing to admit into a baseline. M15 depends on
none of them — it needs only a sensitivity result and the tiers already on every value, so it can be
built at any point.

## Specification template

Every spec follows the same twelve sections. If you write a new one, match the template.

1. Purpose · 2. Scope · 3. Dependencies · 4. Contracts · 5. Logic · 6. Validation & edge cases
· 7. Data requirements · 8. API surface · 9. Frontend · 10. Tests · 11. Acceptance criteria
· 12. Assumptions & open questions

## Shared contracts

These types are used across modules. Defined once in `biet_engine/models.py`; do not redefine
them per module.

```python
from decimal import Decimal
from enum import StrEnum
from typing import Final
from pydantic import BaseModel, ConfigDict, Field


class ConfidenceTier(StrEnum):
    A = "A"   # published, country-specific, with stated interval
    B = "B"   # published, regional or extrapolated
    C = "C"   # analogue-derived or expert assumption
    D = "D"   # placeholder requiring replacement


class ResolutionLevel(StrEnum):
    GLOBAL_DEFAULT = "global_default"
    COUNTRY_OVERRIDE = "country_override"
    SCENARIO_OVERRIDE = "scenario_override"


class Provenance(BaseModel):
    """Travels with every resolved value. Never dropped by any transform."""
    model_config = ConfigDict(frozen=True)

    source: str                              # "WHO NCD_BMI_30A"
    vintage_year: int | None = None
    confidence_tier: ConfidenceTier
    resolution_level: ResolutionLevel
    is_projected: bool = False
    note: str | None = None


class Valued(BaseModel):
    """A number with its provenance and, where published, its interval."""
    model_config = ConfigDict(frozen=True)

    value: float
    low: float | None = None                 # 95% lower bound, where published
    high: float | None = None                # 95% upper bound
    provenance: Provenance


class Money(BaseModel):
    model_config = ConfigDict(frozen=True)

    amount: float                            # float inside the engine; Decimal at the boundary
    currency: str = Field(min_length=3, max_length=3)


class Warning_(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str                                # STALE_VINTAGE | TIER_D_INPUT | ...
    message: str
    country_code: str | None = None
    parameter_path: str | None = None
```

## Canonical golden case

Every module that touches the calculation chain must reproduce its slice of this case exactly.
Germany, obesity, launch year 2028, 3-year horizon, logistic uptake, Year-1 uptake 5%.

**These are frozen synthetic values, not live reference data.** A golden fixture must not change
when WHO refreshes an indicator or the World Bank revises a population estimate — that is the point
of it. The "derivation" column names where each figure's real-world counterpart comes from, not a
value the pipeline will reproduce today. As of 2026-08-23 the live pipeline derives DEU
`adult_share` as 0.8334 against the fixture's 0.820; both are correct in their own context.

| Quantity | Value | Derivation |
|---|---|---|
| Total population | 83,500,000 | World Bank `SP.POP.TOTL` 2025 |
| Adult share | 0.820 | `1 - SP.POP.0014.TO.ZS/100` |
| Adult population | 68,470,000 | 83,500,000 × 0.820 |
| Obesity prevalence | 0.2064 | WHO `NCD_BMI_30A` 2024 |
| Diseased | 14,132,208 | 68,470,000 × 0.2064 |
| Diagnosis rate | 0.600 | Seeded default, tier C |
| Diagnosed | 8,479,325 | 14,132,208 × 0.600 |
| Treatment rate | 0.150 | Seeded default, tier C |
| Treated | 1,271,899 | 8,479,325 × 0.150 |
| Criterion stack | 0.350 | Product of enabled criteria |
| Label-eligible | 445,165 | 1,271,899 × 0.350 |
| Access rate | 0.700 | Seeded default, tier C |
| **Addressable** | **311,615** | 445,165 × 0.700 |
| Year-1 uptake | 0.05 | — |
| Patients on new therapy, Y1 | 15,581 | 311,615 × 0.05 |
| Persistence `p₁₂` | 0.50 | Incretin class default |
| Persistence fraction `f` | 0.7213 | (1 − 0.50) / (−ln 0.50) |

Fixtures live at `backend/tests/engine/golden/fixtures/`. Changing any of these numbers requires
a `biet_engine` version bump and a written justification in the pull request.
