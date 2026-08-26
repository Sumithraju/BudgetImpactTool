/**
 * Where the patient number in the budget came from.
 *
 * This is the first tab because it is the first question. A budget impact
 * figure is only as believable as the population behind it, and "50,000
 * eligible patients" is not believable until a reader can see the chain that
 * produced it and disagree with one link.
 *
 * Two things the panel refuses to blur:
 *
 * **Prevalence and incidence are separate cards, never one "burden" number.**
 * Prevalence is the standing pool — who has the condition now. Incidence is
 * the annual inflow — who newly acquires it. For a persistent condition they
 * differ by more than an order of magnitude (US adult obesity: 42.9% prevalent
 * against roughly 1,716 new cases per 100,000 a year), and reading one as the
 * other misstates the addressable population by a factor of twenty-five.
 *
 * **Every funnel step shows its arithmetic.** "1,022,359" tells a reader
 * nothing they can check. "8,519,657 × 12.0% = 1,022,359" lets them argue with
 * the 12% specifically, which is the conversation this tool exists to start.
 */

import { useState } from "react";
import type { Calculation, FunnelStep } from "../../../shared/api";
import { Card, Help, Stat, StatRow } from "../../../shared/ui";
import {
  formatCount,
  formatMoneyCompact,
  formatPercent,
  TIER_MEANING,
} from "../../../shared/format";

const Tier = ({ tier, title }: { tier: string; title?: string }) => (
  <span className={`chip t-${tier}`} title={title ?? TIER_MEANING[tier] ?? ""}>
    {tier}
  </span>
);

/** The source panel a reader opens on any assumption they doubt. */
function SourceNote({ step }: { step: FunnelStep }) {
  const [open, setOpen] = useState(false);
  if (!step.provenance) return null;
  return (
    <>
      <button
        type="button"
        className="srcbtn"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        ⓘ Source
      </button>
      {open && (
        <div className="srcnote">
          <dl>
            <dt>Confidence</dt>
            <dd>
              <Tier tier={step.provenance.confidence_tier} />{" "}
              {TIER_MEANING[step.provenance.confidence_tier]}
            </dd>
            {step.provenance.vintage_year && (
              <>
                <dt>Vintage</dt>
                <dd>{step.provenance.vintage_year}</dd>
              </>
            )}
            <dt>Resolved from</dt>
            <dd>{step.provenance.resolution_level.replace(/_/g, " ")}</dd>
            <dt>Source</dt>
            <dd>{step.provenance.source}</dd>
            {step.provenance.note && (
              <>
                <dt>Note</dt>
                <dd>{step.provenance.note}</dd>
              </>
            )}
          </dl>
        </div>
      )}
    </>
  );
}

export function PopulationTab({ calculation }: { calculation: Calculation }) {
  const [market, setMarket] = useState(
    calculation.countries[0]?.country_code ?? "",
  );
  const selected =
    calculation.countries.find((c) => c.country_code === market) ??
    calculation.countries[0];
  const epi = selected.epidemiology;
  const top = selected.funnel[0]?.value ?? 1;

  const horizon = calculation.horizon_years;
  const currency = calculation.totals.currency;

  return (
    <>
      <div className="picker">
        {calculation.countries.map((c) => (
          <button
            key={c.country_code}
            type="button"
            aria-pressed={c.country_code === selected.country_code}
            onClick={() => setMarket(c.country_code)}
          >
            {c.country_code}
          </button>
        ))}
      </div>

      {/* KPI row — the big number, the definition small underneath. -------- */}
      {epi && (
        <StatRow>
          <Stat
            label="Target population"
            value={formatCount(epi.population_total)}
            sub={`${formatCount(epi.adult_population)} adults`}
          />
          <Stat
            label="Prevalent patients"
            value={formatCount(epi.prevalent_cases)}
            sub={
              <>
                {formatPercent(epi.prevalence, 1)} of adults have the condition
                {epi.prevalence_low != null && epi.prevalence_high != null && (
                  <>
                    {" "}
                    · range {formatPercent(epi.prevalence_low, 1)}–
                    {formatPercent(epi.prevalence_high, 1)}
                  </>
                )}
              </>
            }
            tone="accent"
          />
          {epi.incidence_per_100k != null && (
            <Stat
              label="New cases a year"
              value={formatCount(epi.incident_cases_per_year ?? 0)}
              sub={`${formatCount(epi.incidence_per_100k)} per 100,000 at risk per year`}
            />
          )}
          <Stat
            label="Clinically eligible"
            value={formatCount(epi.eligible_cases)}
            sub="meet the label and formulary restrictions"
          />
          <Stat
            label={`Treated, Y${horizon}`}
            value={formatCount(epi.treated_cases)}
            sub="on the new therapy in the final year"
            tone="good"
            trend={selected.years.map((y) => y.patients_on_new)}
          />
          <Stat
            label="Incremental budget impact"
            value={formatMoneyCompact(calculation.totals.cumulative, currency)}
            sub={`cumulative over ${horizon} years`}
            tone={calculation.totals.cumulative < 0 ? "good" : "accent"}
            trend={calculation.totals.by_year}
          />
        </StatRow>
      )}

      {/* Prevalence vs incidence, side by side and never merged. ----------- */}
      {epi && (
        <Card
          title="Prevalence and incidence are different questions"
          lede="One is the pool a therapy launches into; the other is how fast that pool refills. A multi-year budget needs both, and they are never added together."
        >
          <div className="twoup">
            <div className="epibox">
              <span className="epikind">Prevalence — the standing pool</span>
              <span className="epibig mono">{formatPercent(epi.prevalence, 1)}</span>
              <span className="epicount mono">
                {formatCount(epi.prevalent_cases)} patients
              </span>
              <p>
                The share of adults who have the condition <b>right now</b>.
                This is the population the funnel narrows down, and every
                patient figure in the budget descends from it.
              </p>
              <code className="working">
                {formatCount(epi.adult_population)} adults ×{" "}
                {formatPercent(epi.prevalence, 1)} ={" "}
                {formatCount(epi.prevalent_cases)}
              </code>
            </div>

            <div className="epibox">
              <span className="epikind">Incidence — the annual inflow</span>
              {epi.incidence_per_100k != null ? (
                <>
                  <span className="epibig mono">
                    {formatCount(epi.incidence_per_100k)}
                  </span>
                  <span className="epicount mono">
                    per 100,000 at risk, per year
                  </span>
                  <p>
                    The share who <b>newly acquire</b> the condition each year.
                    It does not enter the funnel — the funnel starts from the
                    standing pool — but it is what makes a five-year addressable
                    population larger than a one-year one.
                  </p>
                  <code className="working">
                    {formatCount(
                      epi.adult_population - epi.prevalent_cases,
                    )}{" "}
                    at risk × {formatPercent(epi.incidence_annual ?? 0, 2)} ={" "}
                    {formatCount(epi.incident_cases_per_year ?? 0)} new cases a
                    year
                  </code>
                </>
              ) : (
                <p className="dim">
                  No incidence figure is available for this market. WHO
                  publishes prevalence, not incidence, so an incidence has to be
                  derived — and one that has not been derived is absent rather
                  than assumed.
                </p>
              )}
            </div>
          </div>
        </Card>
      )}

      {/* The funnel, with the arithmetic on every step. -------------------- */}
      <Card
        title={`Population funnel — ${selected.country_code}`}
        lede={
          <>
            Each step shows the multiplier it applied and the multiplication
            written out, so the chain can be checked rather than trusted. Open{" "}
            <b>ⓘ Source</b> on any step to see what the figure rests on.
          </>
        }
      >
        <div className="funnel-steps">
          {(epi?.funnel ?? []).map((step, index) => (
            <div className="fstep" key={step.stage}>
              <div className="fstep-head">
                <Help
                  spec={{
                    key: step.stage,
                    label: step.label,
                    description: step.definition,
                    effect: null,
                    unit: "patients",
                    parameter_path: null,
                    example: null,
                    typical_range: null,
                  }}
                >
                  <span className="fstep-label">{step.label}</span>
                </Help>
                {step.provenance && (
                  <Tier tier={step.provenance.confidence_tier} />
                )}
              </div>
              <div className="fstep-bar">
                <i
                  style={{
                    width: `${Math.max((step.value / top) * 100, 0.35)}%`,
                  }}
                />
              </div>
              <div className="fstep-value mono">{formatCount(step.value)}</div>
              <div className="fstep-working">
                {step.working ? (
                  <code>{step.working}</code>
                ) : (
                  <span className="dim">the starting population</span>
                )}
                <SourceNote step={step} />
              </div>
              {index < (epi?.funnel.length ?? 0) - 1 && (
                <span className="fstep-arrow" aria-hidden>
                  ↓
                </span>
              )}
            </div>
          ))}
        </div>
      </Card>

      {/* From eligible patients to money. ---------------------------------- */}
      <Card
        title="From the funnel to the budget"
        lede="The same chain continued: addressable patients, the share of them who adopt, and what that costs."
      >
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Year</th>
                <th>Addressable patients</th>
                <th>Uptake</th>
                <th>Treated patients</th>
                <th>Incremental budget impact</th>
              </tr>
            </thead>
            <tbody>
              {selected.years.map((year, index) => (
                <tr key={year.year}>
                  <td>
                    Y{year.year}
                    <span className="cur">{year.calendar_year}</span>
                  </td>
                  <td className="num">{formatCount(year.addressable)}</td>
                  <td className="num">{formatPercent(year.uptake)}</td>
                  <td className="num strong">{formatCount(year.patients_on_new)}</td>
                  <td className="num">
                    {formatMoneyCompact(
                      calculation.totals.by_year[index] ?? 0,
                      currency,
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="chart-note">
          The budget column is the cross-market total in {currency}; the patient
          columns are {selected.country_code} only, so they will not divide into
          each other.
        </p>
      </Card>

      {/* Eligibility criteria, which is where the funnel narrows most. ----- */}
      <Card
        title="Eligibility criteria"
        lede="Each is a multiplier on the treated population, and they multiply — two criteria at 50% leave 25%. Clinically overlapping pairs are flagged rather than silently combined."
      >
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Criterion</th>
                <th>Factor</th>
                <th>Applied</th>
                <th>Overlaps with</th>
              </tr>
            </thead>
            <tbody>
              {selected.criteria.map((c) => (
                <tr key={c.code} className={c.enabled ? "" : "muted"}>
                  <td>
                    <span className="mkt-name">{c.label}</span>
                  </td>
                  <td className="num">× {c.factor.toFixed(4)}</td>
                  <td>
                    {c.enabled ? (
                      <span className="chip t-A">applied</span>
                    ) : (
                      <span className="derived">available, not applied</span>
                    )}
                  </td>
                  <td className="src-cell">
                    {c.correlated_with.length ? c.correlated_with.join(", ") : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* The published indicators behind all of it. ------------------------ */}
      {epi && epi.indicators.length > 0 && (
        <Card
          title={`WHO indicators — ${epi.country_name}`}
          lede="The published figures this market's epidemiology rests on, each labelled with the kind of quantity it is."
        >
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Indicator</th>
                  <th>Kind</th>
                  <th>Value</th>
                  <th>Per 100,000</th>
                  <th>Vintage</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {epi.indicators.map((row) => (
                  <tr key={row.indicator}>
                    <td>
                      <span className="mkt-name">{row.label}</span>
                    </td>
                    <td>
                      <span className={`chip kind-${row.kind}`}>{row.kind}</span>
                    </td>
                    <td className="num">
                      {row.value == null ? "—" : formatPercent(row.value, 2)}
                    </td>
                    <td className="num">
                      {row.per_100k == null ? "—" : formatCount(row.per_100k)}
                    </td>
                    <td className="num">{row.vintage_year ?? "—"}</td>
                    <td className="src-cell">
                      <Tier tier={row.confidence_tier} /> {row.source}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}
