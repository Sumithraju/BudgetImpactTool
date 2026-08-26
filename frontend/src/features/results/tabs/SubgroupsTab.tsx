/**
 * Where the cost — and the benefit — actually lands. M18.
 *
 * The aggregate answers what the asset costs. This answers where that cost is
 * concentrated and what it buys in each place, which is the question a
 * formulary committee asks second and the one that decides eligibility
 * criteria.
 *
 * The panel is built to make one comparison easy on sight: cost per patient is
 * roughly flat across segments, because it is a price, while events avoided per
 * patient varies by an order of magnitude, because it is a clinical rate. That
 * contrast is the argument for restricting eligibility to the segments where
 * the therapy does the most, and it is invisible in any un-segmented result.
 */

import { RankedBarChart } from "../WithWithout";
import type { Calculation } from "../../../shared/api";
import { Card, Placeholder, Stat, StatRow } from "../../../shared/ui";
import {
  formatCount,
  formatMoney,
  formatMoneyCompact,
  formatPercent,
} from "../../../shared/format";

export function SubgroupsTab({ calculation }: { calculation: Calculation }) {
  const segments = calculation.subgroups;

  if (!segments.length) {
    return (
      <Card title="Subgroups">
        <Placeholder title="This run covers the whole diagnosed population">
          Pick clinical subgroups under <b>Eligibility</b> in the inputs and run
          again. The engine runs once per segment and the results aggregate, so
          you get the same total plus the breakdown behind it — and the
          breakdown is where the case for restricting eligibility lives.
        </Placeholder>
      </Card>
    );
  }

  const currency = segments[0].currency;
  const total = segments.reduce((sum, s) => sum + s.cumulative, 0);
  const coverage = segments.reduce((sum, s) => sum + s.share_of_diagnosed, 0);

  const chartData = segments.map((s) => ({
    name: s.subgroup_label.replace(/^Obesity \+ /, "+ ").replace(/^Obesity /, ""),
    cumulative: s.cumulative,
    perPatient:
      s.patients_treated_final_year > 0
        ? s.cumulative / s.patients_treated_final_year
        : 0,
    eventsPer1000:
      s.patients_treated_final_year > 0
        ? (s.total_events_avoided / s.patients_treated_final_year) * 1000
        : 0,
  }));

  const richest = [...segments].sort(
    (a, b) =>
      b.total_events_avoided / Math.max(b.patients_treated_final_year, 1) -
      a.total_events_avoided / Math.max(a.patients_treated_final_year, 1),
  )[0];
  const costliest = [...segments].sort((a, b) => b.cumulative - a.cumulative)[0];

  return (
    <>
      <StatRow>
        <Stat
          label="Segments modelled"
          value={segments.length}
          sub={`${formatPercent(coverage, 0)} of the diagnosed population`}
          tone={Math.abs(coverage - 1) > 1e-6 ? "warn" : "neutral"}
          caveat={
            Math.abs(coverage - 1) > 1e-6
              ? "A partial selection. Every figure is for that share only, and is not comparable with a whole-population run without saying so."
              : undefined
          }
        />
        <Stat
          label="Largest cost"
          value={costliest.subgroup_label.replace(/^Obesity \+ /, "")}
          sub={formatMoneyCompact(costliest.cumulative, currency)}
        />
        <Stat
          label="Most events avoided per patient"
          value={richest.subgroup_label.replace(/^Obesity \+ /, "")}
          sub={`${(
            (richest.total_events_avoided /
              Math.max(richest.patients_treated_final_year, 1)) *
            1000
          ).toFixed(1)} per 1,000 treated`}
          tone="good"
        />
      </StatRow>

      <Card
        title="Cost, and what it buys, by segment"
        lede={
          <>
            Cumulative impact on the left; events avoided per thousand patients
            treated on the right. Cost per patient barely moves between segments
            — it is a price. Events avoided per patient moves by an order of
            magnitude — it is a clinical rate. That gap is the case for treating
            the segments differently.
          </>
        }
      >
        <RankedBarChart
          data={chartData}
          dataKey="cumulative"
          name="Cumulative budget impact"
          fill="var(--series-2)"
          height={Math.max(220, segments.length * 54)}
          labelWidth={186}
          tickFormatter={(v: number) => formatMoneyCompact(v, currency)}
          tooltipFormatter={(v: number) => formatMoneyCompact(v, currency)}
        />

        <RankedBarChart
          data={chartData}
          dataKey="eventsPer1000"
          name="Events avoided per 1,000 treated"
          fill="var(--series-4)"
          height={Math.max(200, segments.length * 48)}
          labelWidth={186}
          tooltipFormatter={(v: number) => `${v.toFixed(1)} per 1,000`}
        />
      </Card>

      <Card title="Segment detail">
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Segment</th>
                <th>Share of diagnosed</th>
                <th>Uptake</th>
                <th>Addressable, final year</th>
                <th>Patients treated</th>
                <th>Cumulative impact</th>
                <th>Share of total</th>
                <th>Net cost / switch</th>
                <th>Events avoided</th>
                <th>Care cost avoided</th>
              </tr>
            </thead>
            <tbody>
              {segments.map((s) => (
                <tr key={s.subgroup_code}>
                  <td>
                    <span className="mkt-name" title={s.description ?? ""}>
                      {s.subgroup_label}
                    </span>
                    <span className={`chip t-${s.confidence_tier}`} title={s.source}>
                      {s.confidence_tier}
                    </span>
                  </td>
                  <td className="num">{formatPercent(s.share_of_diagnosed, 0)}</td>
                  <td className="num">×{s.uptake_multiplier.toFixed(2)}</td>
                  <td className="num">{formatCount(s.addressable_final_year)}</td>
                  <td className="num">{formatCount(s.patients_treated_final_year)}</td>
                  <td className="num strong">{formatMoney(s.cumulative, currency)}</td>
                  <td className="num">
                    {total !== 0 ? formatPercent(s.cumulative / total, 0) : "—"}
                  </td>
                  <td className="num">{formatMoney(s.net_cost_per_switch, currency)}</td>
                  <td className="num">{formatCount(s.total_events_avoided)}</td>
                  <td className="num">
                    {formatMoney(s.total_cost_avoided, currency)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="What each segment is">
        <ul className="seglist">
          {segments.map((s) => (
            <li key={s.subgroup_code}>
              <b>{s.subgroup_label}</b>
              <span>{s.description}</span>
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}
