/**
 * The figures a payer conversation opens with — M17.
 *
 * Per-member-per-month against the payer's own covered lives, the price at
 * which the therapy stops adding cost, and the same scenario at three adoption
 * levels.
 *
 * The `covered_population_is_assumed` flag is rendered on the figure itself
 * rather than as a note below it. An insurer reading a PMPM computed against a
 * national population is reading a number roughly two orders of magnitude too
 * small, and it looks entirely plausible — the only defence is saying, on the
 * number, which denominator produced it.
 */

import { ColumnChart } from "../WithWithout";
import type { BreakEven, Calculation, UptakeScenarios } from "../../../shared/api";
import { Card, Placeholder, Stat, StatRow } from "../../../shared/ui";
import {
  formatCount,
  formatMoney,
  formatMoneyPrecise,
  formatPercent,
} from "../../../shared/format";

export function PayerTab({
  calculation,
  breakEven,
  uptakeCases,
  busy,
}: {
  calculation: Calculation;
  breakEven: BreakEven | null;
  uptakeCases: UptakeScenarios | null;
  busy: boolean;
}) {
  const payer = calculation.payer;

  return (
    <>
      {payer && (
        <>
          <StatRow>
            <Stat
              label="Per member per month"
              value={formatMoneyPrecise(payer.pmpm_by_year.at(-1) ?? 0, payer.currency)}
              sub={`${payer.perspective_label} · final year`}
              tone="accent"
              caveat={
                payer.covered_population_is_assumed
                  ? "Computed against the modelled population, not this payer's covered lives — enter them to make this figure theirs."
                  : undefined
              }
            />
            <Stat
              label="Per member per year"
              value={formatMoneyPrecise(payer.pmpy_by_year.at(-1) ?? 0, payer.currency)}
              sub="final year"
            />
            <Stat
              label="Covered lives"
              value={formatCount(payer.covered_population)}
              sub={
                payer.covered_population_is_assumed
                  ? "assumed — the modelled population"
                  : payer.perspective === "health_system" ||
                      payer.perspective === "government"
                    ? "the modelled population, which is this perspective's denominator"
                    : "as supplied"
              }
              tone={payer.covered_population_is_assumed ? "warn" : "neutral"}
            />
            <Stat
              label="Cost per treated patient"
              value={formatMoney(payer.cost_per_treated_patient, payer.currency)}
              sub="cumulative impact ÷ patient-years"
            />
          </StatRow>

          <Card
            title="Per member per month, year by year"
            lede={
              <>
                The incremental cost spread across every covered life, whether or
                not they receive the therapy. This is the figure a plan compares
                against its own trend, and it is not the annual figure divided by
                twelve unless the two denominators match.
              </>
            }
          >
            <div className="tablewrap">
              <table>
                <thead>
                  <tr>
                    <th>Year</th>
                    <th>PMPM</th>
                    <th>PMPY</th>
                    <th>Patients treated</th>
                    <th>Cost, current care</th>
                    <th>Cost, with the therapy</th>
                  </tr>
                </thead>
                <tbody>
                  {payer.pmpm_by_year.map((pmpm, index) => (
                    <tr key={index}>
                      <td>
                        Y{index + 1}
                        <span className="cur">{calculation.launch_year + index}</span>
                      </td>
                      <td className="num strong">
                        {formatMoneyPrecise(pmpm, payer.currency)}
                      </td>
                      <td className="num">
                        {formatMoneyPrecise(payer.pmpy_by_year[index] ?? 0, payer.currency)}
                      </td>
                      <td className="num">
                        {formatCount(payer.patients_treated_by_year[index] ?? 0)}
                      </td>
                      <td className="num">
                        {formatMoney(
                          payer.total_cost_current_care[index] ?? 0,
                          payer.currency,
                        )}
                      </td>
                      <td className="num">
                        {formatMoney(
                          payer.total_cost_with_intervention[index] ?? 0,
                          payer.currency,
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      <Card
        title="Break-even price"
        lede={
          <>
            The unit price at which incremental budget impact is exactly zero —
            the point where the new therapy costs the payer what the care it
            displaces costs today. Above it the asset adds budget; below it, it
            saves. This is a different question from the affordability corridor,
            which solves to a threshold somebody has to agree on first.
          </>
        }
      >
        {busy && !breakEven && <Placeholder title="Solving">Running the forward model at trial prices, market by market.</Placeholder>}
        {breakEven && (
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Market</th>
                  <th>Price today</th>
                  <th>Break-even price</th>
                  <th>Annual cost today</th>
                  <th>At break-even</th>
                  <th>Headroom</th>
                </tr>
              </thead>
              <tbody>
                {breakEven.entries.map((entry) => (
                  <tr key={entry.country_code}>
                    <td>
                      <span className="mkt-name">{entry.country_code}</span>
                      <span className="cur">{entry.currency}</span>
                    </td>
                    <td className="num">
                      {formatMoney(entry.current_unit_price, entry.currency)}
                    </td>
                    <td className="num strong">
                      {entry.break_even_unit_price == null
                        ? "—"
                        : formatMoney(entry.break_even_unit_price, entry.currency)}
                    </td>
                    <td className="num">
                      {formatMoney(entry.current_annual_cost, entry.currency)}
                    </td>
                    <td className="num">
                      {entry.break_even_annual_cost == null
                        ? "—"
                        : formatMoney(entry.break_even_annual_cost, entry.currency)}
                    </td>
                    <td className="num">
                      {entry.headroom_pct == null ? (
                        <span className="dim">{entry.method}</span>
                      ) : (
                        <span
                          className={`chip ${entry.headroom_pct >= 0 ? "b-low" : "b-high"}`}
                        >
                          {entry.headroom_pct >= 0 ? "+" : ""}
                          {formatPercent(entry.headroom_pct, 0)}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {breakEven?.entries.some((e) => e.note) && (
          <ul className="warnings">
            {breakEven.entries
              .filter((e) => e.note)
              .map((entry) => (
                <li key={entry.country_code}>
                  <code>{entry.country_code}</code>
                  <span>{entry.note}</span>
                </li>
              ))}
          </ul>
        )}
      </Card>

      <Card
        title="Low, medium and high adoption"
        lede={
          <>
            The same scenario at half and at 1.75 times the base terminal uptake.
            Deliberately <em>not</em> an uncertainty interval — the Uncertainty
            tab is that. No source supplies an adoption distribution for an
            unlaunched asset, so these are three stated multipliers a reader can
            argue with.
          </>
        }
      >
        {busy && !uptakeCases && (
          <Placeholder title="Running">Three forward passes, one per adoption case.</Placeholder>
        )}
        {uptakeCases && (
          <>
            <ColumnChart
              data={uptakeCases.cases.map((c) => ({
                name: c.label,
                cumulative: c.cumulative,
              }))}
              dataKey="cumulative"
              name="Cumulative impact"
              fill="var(--series-2)"
              height={260}
              currency={uptakeCases.currency}
            />

            <div className="tablewrap">
              <table>
                <thead>
                  <tr>
                    <th>Case</th>
                    <th>Terminal uptake</th>
                    <th>Cumulative</th>
                    <th>Peak year</th>
                    <th>Patients, final year</th>
                  </tr>
                </thead>
                <tbody>
                  {uptakeCases.cases.map((c) => (
                    <tr key={c.case} className={c.case === "base" ? "peak" : ""}>
                      <td>
                        <span className="mkt-name">{c.label}</span>
                        <span className="cur">×{c.multiplier}</span>
                      </td>
                      <td className="num">{formatPercent(c.uptake_terminal)}</td>
                      <td className="num strong">
                        {formatMoney(c.cumulative, c.currency)}
                      </td>
                      <td className="num">Y{c.peak_year}</td>
                      <td className="num">
                        {formatCount(c.patients_treated_final_year)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Card>
    </>
  );
}
