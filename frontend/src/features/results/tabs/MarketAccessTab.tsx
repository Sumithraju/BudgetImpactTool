/**
 * What it would take to get reimbursed, market by market.
 *
 * The third tab. Affordability says whether the impact is large; this says what
 * to do about it — the price each market can bear, the price at which the
 * therapy stops adding cost at all, and which market is the binding constraint
 * on a single global price.
 *
 * The price-basis column is on the main table rather than buried in warnings,
 * because it decides how much of this to believe: a market whose new asset
 * carries an observed price while its comparators are derived from a US anchor
 * is not making a like-for-like comparison, and its impact can come out
 * negative for that reason alone.
 */

import { useState } from "react";
import type { BreakEven, Calculation } from "../../../shared/api";
import { PriceCorridor } from "../../price-solver/PriceCorridor";
import { CostBridge } from "../CostBridge";
import { Card, Placeholder, Stat, StatRow } from "../../../shared/ui";
import { VerdictChip, verdictOf } from "../Interpretation";
import {
  BASIS_LABELS,
  formatCount,
  formatMoney,
  formatPercent,
} from "../../../shared/format";

export function MarketAccessTab({
  calculation,
  breakEven,
  busy,
}: {
  calculation: Calculation;
  breakEven: BreakEven | null;
  busy: boolean;
}) {
  const [market, setMarket] = useState(
    calculation.countries[0]?.country_code ?? "",
  );
  const selected =
    calculation.countries.find((c) => c.country_code === market) ??
    calculation.countries[0];

  const observed = calculation.countries.filter(
    (c) => c.new_therapy.price_basis !== "ppp_derived",
  );
  const needsCut = breakEven?.entries.filter(
    (e) => e.headroom_pct != null && e.headroom_pct < 0,
  ).length;
  const headroom = breakEven?.entries.filter(
    (e) => e.headroom_pct != null && e.headroom_pct >= 0,
  ).length;

  return (
    <>
      <StatRow>
        <Stat
          label="Markets modelled"
          value={calculation.countries.length}
          sub={`${observed.length} with an observed price for the asset`}
        />
        {breakEven && (
          <>
            <Stat
              label="Markets needing a price cut"
              value={needsCut ?? 0}
              sub="to reach budget neutrality"
              tone={needsCut ? "warn" : "good"}
            />
            <Stat
              label="Markets with price headroom"
              value={headroom ?? 0}
              sub="already below break-even"
              tone={headroom ? "good" : "neutral"}
            />
          </>
        )}
      </StatRow>

      <Card
        title="Market by market"
        lede="Each market is computed in its own currency at its own prices, then converted into the reporting currency through the run's snapshotted exchange rates."
      >
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Market</th>
                <th>Addressable</th>
                <th>Treated, final year</th>
                <th>Cumulative impact</th>
                <th>Reading</th>
                <th>Net cost / switch</th>
                <th>Price basis</th>
              </tr>
            </thead>
            <tbody>
              {calculation.countries.map((c) => {
                const last = c.years[c.years.length - 1];
                const derived = c.new_therapy.price_basis === "ppp_derived";
                const verdict = verdictOf(c.cumulative_budget_impact);
                return (
                  <tr key={c.country_code}>
                    <td>
                      <span className="mkt-name">{c.country_code}</span>
                      <span className="cur">{c.currency}</span>
                    </td>
                    <td className="num">{formatCount(last.addressable)}</td>
                    <td className="num">{formatCount(last.patients_on_new)}</td>
                    <td className={`num strong ${verdict.tone}`}>
                      {formatMoney(c.cumulative_budget_impact, c.currency)}
                    </td>
                    <td>
                      <VerdictChip amount={c.cumulative_budget_impact} />
                    </td>
                    <td className="num">
                      {formatMoney(last.net_cost_per_switch, c.currency)}
                    </td>
                    <td>
                      <span
                        className={derived ? "derived" : "chip t-B"}
                        title={c.new_therapy.provenance.source}
                      >
                        {BASIS_LABELS[c.new_therapy.price_basis] ??
                          c.new_therapy.price_basis}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <Card
        title="Break-even price"
        lede="The unit price at which incremental budget impact is exactly zero — where the therapy costs the payer what the care it displaces costs today. Above it the asset adds budget; below it, it saves."
      >
        {busy && !breakEven && (
          <Placeholder title="Solving">
            Running the forward model at trial prices, market by market.
          </Placeholder>
        )}
        {breakEven && (
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Market</th>
                  <th>Annual cost today</th>
                  <th>At break-even</th>
                  <th>Headroom</th>
                  <th>What it means</th>
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
                      {formatMoney(entry.current_annual_cost, entry.currency)}
                    </td>
                    <td className="num strong">
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
                    <td className="src-cell">
                      {entry.note
                        ? entry.note
                        : entry.headroom_pct == null
                          ? "—"
                          : entry.headroom_pct >= 0
                            ? `Priced below break-even. The asset could cost ${formatPercent(entry.headroom_pct, 0)} more and still not add budget.`
                            : `The price would have to fall ${formatPercent(Math.abs(entry.headroom_pct), 0)} for this market to be budget-neutral.`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card
        title="Affordable price corridor"
        lede="The reverse solve: given an affordability ceiling, the maximum price each market can bear. The corridor is only as wide as its narrowest market, so the binding one is what a single global price has to clear."
      >
        <PriceCorridor
          scenarioId={calculation.scenario_id}
          currentPriceUsd={
            calculation.countries.find((c) => c.currency === "USD")?.new_therapy
              .unit_price ?? null
          }
        />
      </Card>

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

      {selected.cost_bridge && (
        <CostBridge
          bridge={selected.cost_bridge}
          currency={selected.currency}
          countryCode={selected.country_code}
          therapies={[selected.new_therapy, ...selected.therapies]}
        />
      )}
    </>
  );
}
