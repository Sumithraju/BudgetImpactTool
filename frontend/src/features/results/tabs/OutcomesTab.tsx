/**
 * What the spend buys — M16.
 *
 * The question a payer asks straight after "what does it cost". Weight loss is
 * not an answer a budget holder can act on; avoided myocardial infarctions,
 * avoided new cases of diabetes and the admissions that come with them are.
 *
 * Two things this panel is careful about, because they are the two ways an
 * outcomes screen misleads:
 *
 * **An absent effect is stated, not shown as zero.** A therapy with no
 * published effect on an event class avoids no events *in this model*, which
 * is not the same claim as avoiding none. The panel says which.
 *
 * **Every count carries the rate it came from.** A 20% reduction on a 2.4%
 * annual event rate and the same reduction on a 0.3% rate are the same
 * statistic and completely different findings, and a bare count of events
 * avoided hides which one you are looking at.
 */

import { useState } from "react";
import { RankedBarChart } from "../WithWithout";
import type { Calculation } from "../../../shared/api";
import { Card, Placeholder, Stat, StatRow } from "../../../shared/ui";
import {
  formatCount,
  formatMoney,
  formatMoneyCompact,
  formatPercent,
  warningLabel,
} from "../../../shared/format";

export function OutcomesTab({ calculation }: { calculation: Calculation }) {
  const [market, setMarket] = useState(
    calculation.countries[0]?.country_code ?? "",
  );
  const selected =
    calculation.countries.find((c) => c.country_code === market) ??
    calculation.countries[0];
  const outcomes = selected?.outcomes ?? null;

  const noEvidence = outcomes?.warnings.some(
    (w) => w.code === "NO_OUTCOME_EVIDENCE",
  );

  if (!outcomes || (!outcomes.events.length && !outcomes.responders_by_year)) {
    return (
      <Card title="What the spend buys">
        <Placeholder title="No treatment effect is published for this asset">
          {noEvidence
            ? "Nothing here is an assertion that the therapy avoids nothing — no effect was supplied for it, and the model refuses to infer one from its drug class or its mechanism. Seed a relative risk reduction from a named trial and this panel fills in."
            : "Select a market with a modelled treatment effect, or seed one for this asset."}
        </Placeholder>
      </Card>
    );
  }

  const totalAvoided = outcomes.events.reduce((n, e) => n + e.total_avoided, 0);
  const chartData = outcomes.events.map((event) => ({
    name: event.label,
    avoided: event.total_avoided,
    cost: event.total_cost_avoided,
  }));

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

      <StatRow>
        {outcomes.responders_by_year && (
          <Stat
            label="Weight-loss responders"
            value={formatCount(outcomes.responders_by_year.at(-1) ?? 0)}
            sub={
              outcomes.responder_trial
                ? `at ≥5% loss · ${outcomes.responder_trial}`
                : "at ≥5% loss"
            }
            tone="good"
          />
        )}
        {outcomes.mean_weight_loss_pct != null && (
          <Stat
            label="Mean weight change"
            value={`−${outcomes.mean_weight_loss_pct.toFixed(1)}%`}
            sub="in the trial that reported it"
          />
        )}
        <Stat
          label="Clinical events avoided"
          value={formatCount(totalAvoided)}
          sub={`across ${calculation.horizon_years} years`}
          tone="good"
        />
        <Stat
          label="Care cost avoided"
          value={formatMoneyCompact(outcomes.total_cost_avoided, outcomes.currency)}
          sub="offsets the therapy's own cost"
          tone="good"
        />
        {outcomes.regain_per_year != null && (
          <Stat
            label="Weight regain assumed"
            value={formatPercent(outcomes.regain_per_year, 0)}
            sub="a year, from year 2"
            tone={outcomes.regain_per_year > 0 ? "warn" : "neutral"}
          />
        )}
      </StatRow>

      <Card
        title="Events avoided, and what they were worth"
        lede={
          <>
            Counted only for patients still on therapy — an effect accrues while
            a patient takes the drug, and counting a discontinued patient as a
            responder overstates the clinical result and the economic one
            together.
          </>
        }
      >
        <RankedBarChart
          data={chartData}
          dataKey="avoided"
          name="Events avoided"
          fill="var(--series-4)"
          height={Math.max(180, chartData.length * 64)}
          labelWidth={168}
          tooltipFormatter={formatCount}
        />

        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Event</th>
                <th>Baseline rate</th>
                <th>Reduction</th>
                <th>Would have occurred</th>
                <th>Avoided</th>
                <th>Care cost avoided</th>
                <th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {outcomes.events.map((event) => (
                <tr key={event.event_class}>
                  <td>
                    <span className="mkt-name">{event.label}</span>
                  </td>
                  <td className="num">
                    {formatPercent(event.baseline_annual_rate, 2)}
                    <span className="cur">a year</span>
                  </td>
                  <td className="num">{formatPercent(event.relative_reduction, 0)}</td>
                  <td className="num">
                    {formatCount(
                      event.events_without_by_year.reduce((a, b) => a + b, 0),
                    )}
                  </td>
                  <td className="num strong">{formatCount(event.total_avoided)}</td>
                  <td className="num">
                    {formatMoney(event.total_cost_avoided, outcomes.currency)}
                  </td>
                  <td className="src-cell">
                    <span
                      className={`chip t-${event.effect_provenance.confidence_tier}`}
                      title={event.effect_provenance.source}
                    >
                      {event.effect_provenance.confidence_tier}
                    </span>{" "}
                    {event.trial}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card
        title="Year by year"
        lede="Events avoided rise with adoption and fall with any assumed weight regain, which applies from year 2 — a trial's reported effect is the year-one effect, so decaying it in the year it was measured would double-count regain the trial already saw."
      >
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Event</th>
                {outcomes.events[0]?.avoided_by_year.map((_, index) => (
                  <th key={index}>
                    Y{index + 1} · {calculation.launch_year + index}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {outcomes.events.map((event) => (
                <tr key={event.event_class}>
                  <td>{event.label}</td>
                  {event.avoided_by_year.map((value, index) => (
                    <td key={index} className="num">
                      {formatCount(value)}
                    </td>
                  ))}
                </tr>
              ))}
              {outcomes.responders_by_year && (
                <tr>
                  <td>Weight-loss responders</td>
                  {outcomes.responders_by_year.map((value, index) => (
                    <td key={index} className="num">
                      {formatCount(value)}
                    </td>
                  ))}
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {outcomes.warnings.length > 0 && (
        <Card title="What this rests on">
          <ul className="warnings">
            {outcomes.warnings.map((warning, index) => (
              <li key={index}>
                <code>{warningLabel(warning.code)}</code>
                <span>{warning.message}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}
