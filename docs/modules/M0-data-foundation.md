# M0 — Data Foundation & Ingestion

Module specification v1.0 · Owner area: Data · Blocks: everything

---

## 1. Purpose

Produce a populated, validated, provenance-carrying reference database for ten markets and two
indications, from public sources only. Every downstream module reads from the tables this module
publishes; none of them fetch or parse source data themselves.

## 2. Scope

**In scope.** Fetchers for eight sources; validation; normalisation; staging tables; transform to
clean reference tables; curated seed data for values no public source supplies; Alembic schema;
provenance and confidence tagging on every published row.

**Out of scope.** Any calculation. Any licensed data source. Claims-based population derivation.
Automated scheduling — ingestion is run manually or by cron outside the application.

## 3. Dependencies

None upstream. Requires PostgreSQL 16 with the `vector` extension available.

## 4. Contracts

Output is the reference tables of ARCHITECTURE.md §8.1. The module exposes no Python API to the
application beyond the repositories built in M1.

```python
# data/ingestion/base.py
class SourceResult(BaseModel):
    source_id: str                  # "worldbank" | "who_gho" | "nadac" | ...
    rows_fetched: int
    rows_published: int
    fetched_at: datetime
    warnings: list[str]
    ok: bool


class Fetcher(Protocol):
    source_id: str
    def fetch(self) -> Path: ...            # writes raw payload to data/raw/
    def validate(self, raw: Path) -> None:  # raises SourceValidationError
    def transform(self, raw: Path) -> pd.DataFrame: ...
    def publish(self, df: pd.DataFrame, session: Session) -> SourceResult: ...
```

## 5. Logic specification

### 5.1 Configuration and secrets — do this first

The existing scripts carry a hardcoded institutional proxy credential in three places. Before any
other work:

1. Remove every hardcoded proxy string, database password and API key from source.
2. Rotate the exposed IBAB account password out of band.
3. Introduce `data/ingestion/config.py` using `pydantic-settings`:

```python
class IngestionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: PostgresDsn
    http_proxy: str | None = None            # optional — must work without it
    https_proxy: str | None = None
    request_timeout_s: int = 90
    request_retries: int = 3
```

4. `.env.example` documents every key with placeholder values. `.env` stays git-ignored.

Proxy support is **optional**. All eight endpoints are reachable without a proxy; verified
2026-08-23 (World Bank, WHO GHO, Frankfurter all returned HTTP 200 direct).

### 5.2 Source 1 — World Bank

```
GET https://api.worldbank.org/v2/country/{ISO_LIST}/indicator/{CODE}
    ?format=json&per_page=500&date=2018:2026
```

`ISO_LIST` = `USA;GBR;DEU;FRA;ITA;ESP;IND;CHN;BRA;JPN`

| Indicator code | Published as | Notes |
|---|---|---|
| `SP.POP.TOTL` | `population_total` | Populated through 2025 |
| `NY.GDP.PCAP.PP.CD` | `gdp_pc_ppp` | Populated through 2025 |
| `SH.XPD.CHEX.PC.CD` | `health_exp_pc_usd` | **Lags to 2023/2024; 2025 rows exist but are null** |
| `SH.XPD.OOPC.CH.ZS` | `oop_health_pct` | Lags similarly |
| `SP.POP.0014.TO.ZS` | `pop_0014_pct` | **New — required to derive adult share** |

**Transform rule — latest non-null year, per indicator, per country, independently.**

```python
def latest_non_null(rows: list[dict], country: str, indicator: str) -> tuple[int, float]:
    candidates = [(int(r["date"]), float(r["value"]))
                  for r in rows
                  if r["countryiso3code"] == country
                  and r["indicator"]["id"] == indicator
                  and r["value"] is not None]
    if not candidates:
        raise SourceValidationError(f"no non-null value for {country}/{indicator}")
    return max(candidates, key=lambda t: t[0])
```

Joining all indicators on a single fixed year silently discards health expenditure for every
market. The resolved year is stored in `country_economics.year` and surfaced as the vintage.

**Derived value.** `countries.adult_share`, computed at publish time and stored on `countries`.

The World Bank publishes a **0-14** band, not 0-17, so `1 - pop_0014_pct/100` is a 15+ share and
still includes the 15-17 cohort that WHO's 18+ prevalence excludes. Left uncorrected this
overstates the adult denominator — and therefore the diseased population — by **3.2% (DEU) to 6.4%
(IND)**, verified against live data 2026-08-23.

```
age_15_17_pct = pop_0014_pct x ADOLESCENT_BAND_RATIO      # 3/15, uniform-cohort assumption
adult_share   = 1 - (pop_0014_pct + age_15_17_pct) / 100
```

Confidence tier **B**, not A: the 15-17 estimate is an approximation, not an observation. Supplying
an observed 15-17 share per market via `data/seed/age_bands.csv` overrides the approximation and
upgrades the tier to A.

Derived values, 2026-08-23: USA 0.7948, GBR 0.7964, DEU 0.8334, FRA 0.8053, ITA 0.8601,
ESP 0.8486, JPN 0.8651, CHN 0.8151, BRA 0.7674, IND 0.7097.

### 5.3 Source 2 — WHO Global Health Observatory

```
GET https://ghoapi.azureedge.net/api/{INDICATOR_CODE}
```

| Code | Indication | Latest year available |
|---|---|---|
| `NCD_BMI_30A` | Obesity (BMI ≥ 30) | **2024** |
| `NCD_BMI_25A` | Overweight (BMI ≥ 25) | 2024 |
| `NCD_GLUC_04` | Diabetes | **2014 — stale by twelve years** |

**Mandatory filters.** The response contains aggregate rows alongside country rows. Applying all
three filters is required:

```python
df = df[
    (df.SpatialDimType == "COUNTRY")            # excludes WORLDBANKINCOMEGROUP, REGION
    & (df.SpatialDim.isin(TARGET_COUNTRIES))
    & (df.Dim1 == "SEX_BTSX")                   # both sexes
    & (df.Dim2 == "AGEGROUP_YEARS18-PLUS")      # adults
]
```

Omitting the `SpatialDimType` filter loads World Bank income groups and WHO regions as if they
were markets.

**Published columns.** `prevalence_pct` ← `NumericValue`, `prevalence_low` ← `Low`,
`prevalence_high` ← `High`. The interval is published by WHO and is used directly by M9 to
parameterise the probabilistic sensitivity analysis — do not discard it.

**Diabetes staleness handling.**

- Publish the 2014 row with `year = 2014`, `confidence_tier = 'B'`, `is_projected = False`.
- Additionally publish a projected row for the current model year:
  `prevalence(y) = prevalence(2014) × (1 + cagr)^(y − 2014)`, with `cagr` from
  `data/seed/diabetes_cagr.csv` (per market, sourced and cited), `is_projected = True`,
  `confidence_tier = 'C'`.
- Any run consuming a row where `is_projected` is true, or where
  `model_year − vintage_year > STALE_VINTAGE_YEARS` (default 5), emits a `STALE_VINTAGE` warning.
- The schema must permit a manual IDF Diabetes Atlas override to supersede both.

### 5.4 Source 3 — NADAC

```
GET https://download.medicaid.gov/data/nadac-national-average-drug-acquisition-cost-{MM-DD-YYYY}.csv
```

The dated URL rolls off. Resolve the current file from the data.medicaid.gov dataset API rather
than hardcoding a date; fall back through the last four weekly dates on failure.

**Established constraint — do not plan around branded pricing.** Filtering the full extract
(~1,497,925 rows) to the therapy classes of interest yields **1,204 rows: 1,174 insulin, 30 generic
liraglutide, zero semaglutide, zero tirzepatide.** NADAC reports pharmacy acquisition cost, which
exists principally for multi-source products. NADAC's role is confined to insulin and generic
comparators. Branded incretin pricing comes from §5.6.

**Unit conversion.** `Pricing Unit` takes values `ML` (1,018 rows) and `EA` (186 rows). Converting
a per-unit cost to an annual cost per patient requires an explicit mapping — never inferred:

```
annual_cost = nadac_per_unit × units_per_presentation × presentations_per_year
```

`data/seed/ndc_regimen_map.csv` supplies `ndc, drug_id, units_per_presentation,
presentations_per_year, source`. An NDC without a mapping row is not published.

### 5.5 Sources 5–7 — context and FX

| Source | Endpoint | Published to | On the calculation path? |
|---|---|---|---|
| openFDA | `https://api.fda.gov/drug/drugsfda.json` | `drugs` metadata | No |
| ClinicalTrials.gov | `https://clinicaltrials.gov/api/v2/studies` | `staging_*` only | No |
| Frankfurter | `https://api.frankfurter.dev/v1/latest?base=USD` | `fx_rates` | **Yes** |

openFDA and ClinicalTrials payloads embed serialised JSON in `submissions` and `products`. Parse
to flat projections; never read them from the engine.

FX must cover `EUR, GBP, JPY, CNY, BRL, INR` plus an identity row for `USD`. A fetch returning
fewer than seven currencies fails validation.

### 5.6 Source 4 — curated seed data

Values no public source supplies. Every row cites a public reference and states its assumption.
Maintained as CSV under `data/seed/`, loaded transactionally, and version-controlled.

| File | Populates | Required columns |
|---|---|---|
| `countries.csv` | `countries` | `country_code, country_name, currency_code, region, health_system_type` |
| `indications.csv` | `indications` | `indication_id, indication_name, therapy_area, icd10, who_indicator_code` |
| `drugs.csv` | `drugs` | `drug_id, drug_name, generic_name, company, drug_class, route, indication_id, is_comparator` |
| `drug_regimens.csv` | `drug_regimens` | `drug_id, dose_amount, dose_unit, units_per_admin, admins_per_year, wastage_pct, persistence_12m, source, confidence_tier` |
| `drug_prices.csv` | `drug_prices` | `drug_id, country_code, price_local, currency_code, price_basis, gross_to_net_pct, effective_date, source, source_url, confidence_tier` |
| `funnel_defaults.csv` | `funnel_defaults` | `indication_id, country_code, stage, value, value_low, value_high, source, confidence_tier` |
| `eligibility_criteria.csv` | `eligibility_criteria` | `indication_id, criterion_code, criterion_label, criterion_type, default_factor, factor_low, factor_high, source, confidence_tier, correlated_with` |
| `ndc_regimen_map.csv` | NADAC conversion | `ndc, drug_id, units_per_presentation, presentations_per_year, source` |
| `diabetes_cagr.csv` | Projection | `country_code, cagr, source` |
| `age_bands.csv` | `countries.adult_share` | `country_code, age_15_17_pct, source` |

`price_basis` is one of `list`, `nadac`, `estimated_net`, `ppp_derived`. A row with basis
`estimated_net` must carry `gross_to_net_pct` and cite the assumption.

Minimum comparator coverage for launch: obesity — semaglutide 2.4 mg, tirzepatide, liraglutide
3.0 mg, orlistat, no-pharmacotherapy; type 2 diabetes — semaglutide, tirzepatide, dulaglutide,
metformin, basal insulin, rapid-acting insulin.

### 5.7 Pipeline

```
extract → validate → normalise → stage → transform → publish
```

- **Idempotent.** Re-running produces the same published state.
- **Staged.** Raw extracts land in `staging_<source>` unmodified, preserving the audit trail from
  published value back to source payload.
- **Transactional publish.** Upsert on the natural key. Prior values are superseded, never deleted.
- **Fail-safe.** A source failing validation does not overwrite previously published reference data.

## 6. Validation & edge cases

| Check | Rule | On failure |
|---|---|---|
| Prevalence range | `0 < prevalence_pct < 100` | Quarantine row |
| Interval ordering | `low ≤ value ≤ high` | Quarantine row |
| Rate range | every `funnel_defaults.value` in `(0, 1]` | Reject file |
| Adult share | `0.5 < adult_share < 0.95` | Reject country |
| Country coverage | all 10 markets present per indicator | Fail source |
| FX coverage | ≥ 7 currencies incl. USD identity | Fail source |
| Price positivity | `price_local > 0` | Reject row |
| Currency validity | ISO 4217, matches `countries.currency_code` | Reject row |
| NDC mapping | every published NADAC NDC has a regimen map row | Skip row, warn |
| Referential integrity | every FK resolves | Fail transaction |

Edge cases to handle explicitly: a World Bank indicator null for **all** years for a country;
a WHO country missing entirely for an indicator; a NADAC weekly file 404; an FX fetch returning a
stale `date`; duplicate NDC rows with different effective dates (take the latest).

## 7. Data requirements

Creates and populates every table in ARCHITECTURE.md §8.1 and §8.3. Schema is authored as Alembic
migrations — never `CREATE TABLE` from a script. Migrations must be reversible.

## 8. API surface

None. This module is offline. M1 builds the repositories that read these tables.

## 9. Frontend

None.

## 10. Test specification

| Class | Test |
|---|---|
| Unit | `latest_non_null` picks 2023 when 2024/2025 are null |
| Unit | WHO filter excludes `WORLDBANKINCOMEGROUP` and `REGION` rows |
| Unit | WHO filter keeps only `SEX_BTSX` and `AGEGROUP_YEARS18-PLUS` |
| Unit | adult share derives 0.820 for DEU from `pop_0014_pct = 18.0` |
| Unit | NADAC unit conversion for a known NDC matches a hand-computed annual cost |
| Unit | diabetes projection: 2014 value 5.00% at CAGR 0.02 → 2028 gives 6.60% |
| Integration | full pipeline against recorded fixtures populates all reference tables |
| Integration | re-running the pipeline is idempotent (row counts and values unchanged) |
| Integration | a source failing validation leaves prior published data intact |
| Contract | every published row has non-null `source` and `confidence_tier` |

Fixtures are recorded API payloads under `data/ingestion/tests/fixtures/`. **Tests never hit the
network.**

## 11. Acceptance criteria

- [ ] No credential, proxy string or connection string in source; `.env.example` complete
- [ ] Pipeline runs end to end with **no** proxy configured
- [ ] `countries` — 10 rows, each with `adult_share` (18+, 15-17 cohort removed) and `currency_code`
- [ ] `country_economics` — 5 indicators × 10 countries, each with its own resolved vintage year
- [ ] `epidemiology` — obesity 2024 for 10 markets with `low`/`high` populated; diabetes 2014 plus
      a projected row for the model year, flagged
- [ ] `fx_rates` — ≥ 7 currencies including USD identity
- [ ] `drugs`, `drug_regimens`, `drug_prices` — minimum comparator coverage of §5.6, every price
      citing a source URL
- [ ] `funnel_defaults`, `eligibility_criteria` — populated for both indications
- [ ] `guideline_chunks` — corpus embedded, ivfflat index built
- [ ] Every published row carries `source` and `confidence_tier`
- [ ] Alembic migrations reversible; `downgrade` tested
- [ ] Ingestion tests pass offline

## 12. Assumptions & open questions

**Assumptions.** Public sources remain freely accessible without authentication. WHO will not
refresh `NCD_GLUC_04` before delivery. Gross-to-net assumptions are stated estimates, not
observations, and are labelled as such wherever a derived net price is displayed.

**Open questions.**
0. Whether to source observed 15-17 population shares (UN World Population Prospects publishes
   single-year cohorts) to replace the uniform-cohort approximation in the adult-share derivation
   and upgrade it from tier B to A. Worth doing: it currently moves every market's result by 3-6%.
1. Source for per-market diabetes CAGR — IDF Atlas historical series is the likeliest; needs
   confirming and citing before `diabetes_cagr.csv` is populated.
2. Whether the US should carry plan-level covered-lives figures in addition to national
   population, to enable PMPY reporting (ARCHITECTURE.md §5.7). Deferred unless US plan-level
   output is required for launch.
