/**
 * Can each market actually pay for this?
 *
 * The second tab, straight after the population that generates the cost. It
 * answers one question — how large is this against the money that already
 * exists — and it answers it per market, because the same absolute impact is
 * trivial in the United States and prohibitive in India.
 *
 * The logarithmic scale on the gauge is load-bearing rather than stylistic:
 * real ratios here run near 0.02% against a 1% critical threshold, so a linear
 * axis would pin every market to the left edge and show nothing at all.
 */

import type { Calculation } from "../../../shared/api";
import { AffordabilityGauge } from "../../affordability/AffordabilityGauge";
import { Card, Placeholder, Stat, StatRow } from "../../../shared/ui";
import { Interpretation, verdictOf } from "../Interpretation";
import { formatMoney, formatMoneyCompact, formatPercent } from "../../../shared/format";

const BAND_MEANING: Record<string, string> = {
  low: "Absorbable within normal budget variance.",
  moderate: "Visible in the budget; expect it to be questioned.",
  high: "Large enough to need a funding decision of its own.",
  critical: "Above the threshold at which access is usually restricted.",
};

export function AffordabilityTab({
  calculation,
  bands,
}: {
  calculation: Calculation;
  bands: Record<string, number>;
}) {
  const priced = calculation.countries.filter((c) => c.affordability);
  if (!priced.length) {
    return (
      <Card title="Affordability">
        <Placeholder title="No affordability ratio could be computed">
          Every market needs a national health expenditure figure to divide by.
          None of the markets in this run resolved one.
        </Placeholder>
      </Card>
    );
  }

  const worst = [...priced].sort(
    (a, b) =>
      (b.affordability?.cumulative_ratio ?? 0) -
      (a.affordability?.cumulative_ratio ?? 0),
  )[0];
  const savers = priced.filter(
    (c) => (c.affordability?.cumulative_ratio ?? 0) < 0,
  );

  return (
    <>
      <StatRow>
        <Stat
          label="Most constrained market"
          value={worst.country_code}
          sub={`${formatPercent(worst.affordability!.cumulative_ratio, 3)} of health spend · ${worst.affordability!.band}`}
          tone={
            worst.affordability!.band === "low"
              ? "good"
              : worst.affordability!.band === "critical"
                ? "warn"
                : "accent"
          }
        />
        <Stat
          label="Markets that save money"
          value={`${savers.length} of ${priced.length}`}
          sub={
            savers.length
              ? savers.map((c) => c.country_code).join(", ")
              : "none — every market adds cost"
          }
          tone={savers.length ? "good" : "neutral"}
        />
        <Stat
          label="Cumulative impact"
          value={formatMoneyCompact(
            calculation.totals.cumulative,
            calculation.totals.currency,
          )}
          sub={`across ${calculation.horizon_years} years, all markets`}
        />
      </StatRow>

      <Interpretation calculation={calculation} />

      {Object.keys(bands).length > 0 && (
        <Card
          title="Impact against national health expenditure"
          lede="Cumulative budget impact as a share of what each market already spends on health. The scale is logarithmic — real ratios run near 0.02% against a 1% critical threshold, and a linear axis would pin every market to the left edge."
        >
          <AffordabilityGauge countries={calculation.countries} bands={bands} />
        </Card>
      )}

      <Card
        title="Per market"
        lede="A negative ratio is a saving: the therapy displaces care that costs more than it does."
      >
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Market</th>
                <th>Cumulative impact</th>
                <th>Health expenditure</th>
                <th>Share of health spend</th>
                <th>Band</th>
                <th>Reading</th>
              </tr>
            </thead>
            <tbody>
              {priced.map((c) => {
                const a = c.affordability!;
                const verdict = verdictOf(c.cumulative_budget_impact);
                return (
                  <tr key={c.country_code}>
                    <td>
                      <span className="mkt-name">{c.country_code}</span>
                      <span className="cur">{c.currency}</span>
                    </td>
                    <td className={`num strong ${verdict.tone}`}>
                      {formatMoney(c.cumulative_budget_impact, c.currency)}
                    </td>
                    <td className="num">
                      {formatMoneyCompact(a.health_budget, c.currency)}
                    </td>
                    <td className="num">{formatPercent(a.cumulative_ratio, 4)}</td>
                    <td>
                      <span className={`chip b-${a.band}`}>{a.band}</span>
                    </td>
                    <td className="src-cell">
                      {a.cumulative_ratio < 0
                        ? "A saving — this market spends less with the therapy than without it."
                        : BAND_MEANING[a.band] ?? ""}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
