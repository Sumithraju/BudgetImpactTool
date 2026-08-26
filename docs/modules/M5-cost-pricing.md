# M5 — Cost & Pricing Engine

Module specification v1.0 · Owner area: Engine · Depends on: M0

---

## 1. Purpose

Compute the annual cost per treated patient-year of every therapy in every market, including the
new therapy, and derive a price for markets where none is observed.

## 2. Scope

**In scope.** Regimen-based acquisition cost; wastage; discount and gross-to-net; administration,
monitoring and adverse-event costs; cost offsets; purchasing-power-parity price derivation;
currency handling.

**Out of scope.** Persistence adjustment (M6 — this module returns cost per *full* treated
patient-year; M6 scales it). Market shares (M4). The reverse price solve (M8).

## 3. Dependencies

Consumes `drugs`, `drug_regimens`, `drug_prices` and country economics via M1's resolution.
Produces `TherapyCost` consumed by M7 and M8.

## 4. Contracts

```python
class PriceBasis(StrEnum):
    LIST = "list"
    NADAC = "nadac"
    ESTIMATED_NET = "estimated_net"
    PPP_DERIVED = "ppp_derived"


class Regimen(BaseModel):
    model_config = ConfigDict(frozen=True)
    units_per_admin: Valued
    admins_per_year: Valued
    wastage_pct: Valued                     # [0, 1)


class TherapyInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    drug_id: int
    name: str
    is_new: bool
    regimen: Regimen
    unit_price: Money                       # local currency, per unit
    price_basis: PriceBasis
    discount_pct: Valued                    # [0, 1) — gross-to-net
    admin_cost: Money
    monitoring_cost: Money
    ae_cost: Money
    offset: Money                           # avoided-event savings, subtracted
    persistence_12m: Valued                 # consumed by M6, carried here


class TherapyCost(BaseModel):
    model_config = ConfigDict(frozen=True)

    drug_id: int
    country_code: str
    acquisition: Money
    admin: Money
    monitoring: Money
    ae: Money
    offset: Money
    total: Money                            # annual cost per full treated patient-year
    price_basis: PriceBasis
    provenance: Provenance


# biet_engine/cost.py
def compute_therapy_cost(therapy: TherapyInput, country_code: str) -> TherapyCost: ...
def derive_ppp_price(
    reference_price: float, gdp_pc_ppp_target: float,
    gdp_pc_ppp_reference: float, elasticity: float, floor: float,
) -> float: ...
```

## 5. Logic specification

Per ARCHITECTURE.md §5.5.

### 5.1 Acquisition cost

```
acq = unit_price × units_per_admin × admins_per_year × (1 + wastage) × (1 − discount)
```

Order matters and is fixed: wastage inflates volume, discount reduces realised price. Applying
them in the other order gives a different number.

### 5.2 Total annual cost

```
AC = acq + admin_cost + monitoring_cost + ae_cost − offset
```

`offset` is a positive number that is subtracted. A negative `offset` is rejected; entering an
avoided cost as negative is a common error and must fail loudly.

`AC` may legitimately be negative when offsets exceed direct costs. Do not floor it at zero — a
cost-saving therapy is a real result and flooring it would hide a budget saving.

### 5.3 Cross-market price derivation

Where no observed price exists for a market:

```
price(c) = max( price(ref) × [ gdp_pc_ppp(c) / gdp_pc_ppp(ref) ] ^ ε ,  floor × price(ref) )
```

Defaults `ε = 1.0`, `floor = 0.05`. The result carries `price_basis = PPP_DERIVED`,
`confidence_tier = C`, and emits an `UNPRICED_MARKET` warning.

This is a **modelling assumption, not an observation**. Every surface that displays a derived
price must label it as derived — the frontend requirement in §9 is not optional. Both `ε` and
`floor` are exposed as sensitivity levers in M9 because international reference pricing behaviour
varies substantially by market.

Reference market defaults to USA. Where the reference market itself has no price, raise
`UnpricedReferenceError` rather than deriving from a derived price.

### 5.4 Currency

Every `Money` carries an ISO 4217 code. Rules:

- Costs are computed in the therapy's **local** currency.
- Conversion to the reporting currency happens in M7, using the run's FX snapshot — never here,
  and never via a live lookup.
- Adding two `Money` values with different currencies raises `CurrencyMismatchError`. No implicit
  conversion, ever.
- PPP derivation operates on USD-normalised values; convert in, convert out, and record both.

### 5.5 The no-pharmacotherapy therapy

The therapy set includes a `no_pharmacotherapy` entry (M4 §5.3) with every cost component zero and
`persistence_12m = 1.0`. It requires no special handling here — it flows through the same path and
yields `total = 0`.

## 6. Validation & edge cases

| Rule | Behaviour |
|---|---|
| `unit_price ≤ 0` | Raise `ValueError` |
| `wastage_pct` outside `[0, 1)` | Raise `ValueError` |
| `discount_pct` outside `[0, 1)` | Raise `ValueError` |
| `offset < 0` | Raise `ValueError` |
| Mixed currencies in a sum | Raise `CurrencyMismatchError` |
| `admins_per_year ≤ 0` | Raise `ValueError` |
| Reference market unpriced | Raise `UnpricedReferenceError` |
| `AC < 0` | Permitted — cost-saving therapy |
| PPP floor binds | Permitted; warn `PPP_FLOOR_APPLIED` |
| `ε = 0` | Yields the reference price everywhere; permitted |

## 7. Data requirements

`drugs`, `drug_regimens`, `drug_prices`, `country_economics.gdp_pc_ppp`, `fx_rates`.

**Established data constraint.** NADAC supplies no branded incretin pricing — 1,204 rows filtered
to the classes of interest are 1,174 insulin and 30 generic liraglutide, with zero semaglutide or
tirzepatide (M0 §5.4). Branded prices come from `data/seed/drug_prices.csv` with
`price_basis = list` or `estimated_net`, each citing a public source URL and stating its
gross-to-net assumption.

## 8. API surface

`GET /api/v1/reference/drugs?indication_id=&country_codes=` returns therapies with regimens and
resolved prices. Costs also appear inside the calculation response per therapy.

## 9. Frontend

Slice `features/cost-pricing/`.

- `RegimenEditor` — dose, units per administration, administrations per year, wastage
- `PriceInput` — local price with currency, discount/gross-to-net, and a **basis badge**; any
  therapy with `price_basis = ppp_derived` renders a distinct "derived" marker and a tooltip
  stating the elasticity and reference market used
- `CostBreakdown` — waterfall from acquisition through admin, monitoring, AE and offset to total
- All amounts via `formatMoney(amount, currency)`. Never a hardcoded currency symbol.

## 10. Test specification

| Class | Test |
|---|---|
| Unit | acq: price 100, 1 unit, 12 admins, 5% wastage, 20% discount → 1,008.00 |
| Unit | wastage-then-discount order verified against the reverse order producing a different number |
| Unit | total: acq 1,008 + admin 50 + monitoring 120 + AE 30 − offset 200 → 1,008.00 |
| Unit | negative offset raises |
| Unit | negative total permitted when offset dominates |
| Unit | PPP: ref 10,000 USD, target GDP 29,333, ref GDP 90,027, ε=1 → 3,258.24 |
| Unit | PPP floor binds for IND at ε=1: 10,000 × (11,748/90,027) = 1,304.94 > 500 floor, no bind |
| Unit | PPP with ε=2 for IND → 170.29, floor 500 binds, warning emitted |
| Unit | mixed-currency addition raises `CurrencyMismatchError` |
| Unit | `no_pharmacotherapy` yields total 0 |
| Property | acquisition cost is monotonically increasing in unit price |
| Property | total cost is monotonically decreasing in offset |

## 11. Acceptance criteria

- [ ] Pure; no I/O
- [ ] Wastage-before-discount order implemented and tested
- [ ] Negative totals permitted; offsets validated non-negative
- [ ] No implicit currency conversion anywhere
- [ ] PPP derivation labelled, warned, and exposed as a sensitivity lever
- [ ] Frontend visibly distinguishes derived prices from observed
- [ ] 100% branch coverage on `cost.py`

## 12. Assumptions & open questions

**Assumptions.** One regimen per therapy — no dose titration schedule. Costs are constant across
the horizon; no price erosion, no loss of exclusivity. Gross-to-net is a scalar, not a tiered
schedule.

**Open questions.**
1. Whether year-on-year price erosion is needed for launch. Currently absent; adding it makes
   `TherapyCost` per-year and touches M7 and M8's solver linearity (M8 §5.3).
2. Whether tiered or volume-dependent discounts are required. If so, M8's analytic solver becomes
   invalid and the bisection fallback becomes the primary path.
