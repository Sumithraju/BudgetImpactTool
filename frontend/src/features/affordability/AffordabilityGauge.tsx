import type { CountryResult } from "../../shared/api";
import { formatPercent } from "../../shared/format";

/**
 * Budget impact as a share of national health expenditure, per market.
 *
 * The scale is logarithmic, and that is not decoration. Real affordability
 * ratios here run around 0.02% while the critical threshold sits at 1% — a
 * linear axis would pin every marker to the far left, indistinguishable
 * from each other and from zero, which is the opposite of what a gauge is
 * for. A log axis makes two markets an order of magnitude apart look an
 * order of magnitude apart.
 */

const FLOOR = 1e-5; // 0.001% — below this the exact value stops mattering
const CEILING = 0.02; // 2% — comfortably past the critical threshold

const position = (ratio: number): number => {
  const clamped = Math.min(Math.max(ratio, FLOOR), CEILING);
  return (
    ((Math.log10(clamped) - Math.log10(FLOOR)) /
      (Math.log10(CEILING) - Math.log10(FLOOR))) *
    100
  );
};

export function AffordabilityGauge({
  countries,
  bands,
}: {
  countries: CountryResult[];
  bands: Record<string, number>;
}) {
  const priced = countries.filter((c) => c.affordability);
  if (priced.length === 0) return null;

  // Band boundaries come from the API so the gauge cannot drift from the
  // thresholds the engine actually classified against.
  const boundaries = Object.entries(bands).sort((a, b) => a[1] - b[1]);

  return (
    <section>
      <h2>Affordability</h2>
      <p className="lede">
        Cumulative impact against each market's total health expenditure. The scale is
        logarithmic — these ratios span orders of magnitude, and a linear axis would
        stack every market on the left edge.
      </p>

      <div className="gauge">
        <div className="gauge-track">
          {boundaries.map(([band, threshold]) => (
            <span
              key={band}
              className={`gauge-tick b-${band}`}
              style={{ left: `${position(threshold)}%` }}
            >
              <em>{formatPercent(threshold, 1)}</em>
              <span>{band}</span>
            </span>
          ))}
        </div>

        {priced.map((c) => {
          const a = c.affordability!;
          return (
            <div className="gauge-row" key={c.country_code}>
              <div className="gauge-label">{c.country_code}</div>
              <div className="gauge-bar">
                <i style={{ width: `${position(a.cumulative_ratio)}%` }} className={`b-${a.band}`} />
                <u
                  style={{ left: `${position(a.cumulative_ratio)}%` }}
                  className={`b-${a.band}`}
                />
              </div>
              <div className={`gauge-val mono b-${a.band}`}>
                {formatPercent(a.cumulative_ratio, 3)}
              </div>
              <div className={`chip b-${a.band}`}>{a.band}</div>
            </div>
          );
        })}
      </div>

      <p className="lede" style={{ marginTop: 16 }}>
        Every market lands in the low band here, which is the expected result for a
        single asset against a whole national health budget. The band matters more for
        a broad-label launch, or when the same scenario is run at a much higher price.
      </p>
    </section>
  );
}
