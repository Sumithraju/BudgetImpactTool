import { useState } from "react";
import { api, ApiError, type Corridor } from "../../shared/api";
import { formatMoney, formatPercent } from "../../shared/format";

/**
 * Reverse mode — M8's more useful direction.
 *
 * Forward asks "what does this price cost the payer?". This asks the
 * question a pricing team actually has: given a ceiling we are willing to
 * defend, what is the most this asset could be priced at and still clear it
 * everywhere? The answer is set by the *narrowest* market, so the binding
 * one is called out rather than left for the reader to find by scanning.
 */

const PRESETS = [0.001, 0.005, 0.01];

export function PriceCorridor({
  scenarioId,
  currentPriceUsd,
}: {
  scenarioId: string;
  currentPriceUsd: number | null;
}) {
  const [target, setTarget] = useState(0.005);
  const [corridor, setCorridor] = useState<Corridor | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const solve = async (ratio: number) => {
    setBusy(true);
    setError(null);
    setTarget(ratio);
    try {
      setCorridor(await api.solve(scenarioId, ratio));
    } catch (e) {
      setError((e as ApiError).message);
      setCorridor(null);
    } finally {
      setBusy(false);
    }
  };

  const feasible = corridor?.entries.filter((e) => e.feasible && e.max_unit_price_usd) ?? [];
  const widest = Math.max(...feasible.map((e) => e.max_unit_price_usd ?? 0), 0);

  return (
    <section>
      <h2>Price corridor</h2>
      <p className="lede">
        Given an affordability ceiling, the highest unit price this asset could carry
        and still clear it in each market.
      </p>

      <div className="solve-controls">
        <span className="eyebrow">Target ceiling</span>
        {PRESETS.map((p) => (
          <button
            key={p}
            type="button"
            aria-pressed={target === p}
            onClick={() => solve(p)}
            disabled={busy}
          >
            {formatPercent(p, 1)}
          </button>
        ))}
        {busy && <span className="dim mono">solving…</span>}
      </div>

      {error && (
        <div className="alert" role="alert">
          {error}
        </div>
      )}

      {corridor && (
        <>
          {corridor.binding_market && corridor.single_global_price_ceiling_usd !== null && (
            <div className="binding">
              <div>
                <span className="eyebrow">Single global price ceiling</span>
                <span className="figure-sm mono">
                  {formatMoney(corridor.single_global_price_ceiling_usd, "USD")}
                  <em> / unit</em>
                </span>
              </div>
              <p>
                Set by <b>{corridor.binding_market}</b> — the corridor is only as wide as
                its narrowest market, so this is the price a single global figure has to
                satisfy.
                {currentPriceUsd !== null && (
                  <>
                    {" "}
                    The current price is {formatMoney(currentPriceUsd, "USD")}, which is{" "}
                    <b>
                      {currentPriceUsd <= corridor.single_global_price_ceiling_usd
                        ? "inside"
                        : "above"}
                    </b>{" "}
                    that ceiling.
                  </>
                )}
              </p>
            </div>
          )}

          <div className="corridor">
            {corridor.entries.map((e) => {
              const binding = e.country_code === corridor.binding_market;
              const width = e.max_unit_price_usd
                ? Math.max((e.max_unit_price_usd / widest) * 100, 1)
                : 0;
              return (
                <div className={binding ? "crow binding-row" : "crow"} key={e.country_code}>
                  <div className="clab">
                    {e.country_code}
                    {binding && <span className="chip t-C">binding</span>}
                  </div>
                  <div className="cbar">
                    <i style={{ width: `${width}%` }} />
                    {currentPriceUsd !== null && widest > 0 && (
                      <u
                        style={{ left: `${(currentPriceUsd / widest) * 100}%` }}
                        title={`current price ${formatMoney(currentPriceUsd, "USD")}`}
                      />
                    )}
                  </div>
                  <div className="cval mono">
                    {e.feasible && e.max_unit_price_usd !== null
                      ? formatMoney(e.max_unit_price_usd, "USD")
                      : e.unbounded
                        ? "unbounded"
                        : "infeasible"}
                  </div>
                  <div className="cmethod mono">{e.method}</div>
                </div>
              );
            })}
          </div>
          <p className="lede" style={{ marginTop: 14 }}>
            The dashed mark is the asset's current price. Solved analytically where
            budget impact is linear in price, which it is here — bisection exists only
            as a fallback for tiered or volume-dependent discounting.
          </p>
        </>
      )}
    </section>
  );
}
