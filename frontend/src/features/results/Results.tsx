import { useState } from "react";
import type { Calculation, EvidenceGapReport, Owsa, Psa } from "../../shared/api";
import { AffordabilityGauge } from "../affordability/AffordabilityGauge";
import { PriceCorridor } from "../price-solver/PriceCorridor";
import { CostBridge } from "./CostBridge";
import { EvidencePriority } from "./EvidencePriority";
import {
  BASIS_LABELS,
  STAGE_LABELS,
  TIER_MEANING,
  formatCount,
  formatMoney,
  formatMoneyCompact,
  formatPercent,
  warningLabel,
} from "../../shared/format";

const Tier = ({ tier }: { tier: string }) => (
  <span className={`chip t-${tier}`} title={TIER_MEANING[tier] ?? ""}>
    {tier}
  </span>
);

export function Results({
  calculation,
  owsa,
  gaps,
  psa,
  bands,
}: {
  calculation: Calculation;
  owsa: Owsa | null;
  gaps: EvidenceGapReport | null;
  psa: Psa | null;
  bands: Record<string, number>;
}) {
  const [market, setMarket] = useState(calculation.countries[0]?.country_code ?? "");
  const selected =
    calculation.countries.find((c) => c.country_code === market) ?? calculation.countries[0];

  const { totals } = calculation;

  return (
    <>
      {/* headline ---------------------------------------------------- */}
      <section className="headline">
        <div className="eyebrow">
          Cumulative incremental budget impact · {calculation.launch_year}–
          {calculation.launch_year + calculation.horizon_years - 1}
        </div>
        <div className="figure">{formatMoneyCompact(totals.cumulative, totals.currency)}</div>

        {psa && (
          <div className="interval">
            <span>95% credible interval</span>
            <b>{formatMoneyCompact(psa.p2_5, psa.currency)}</b>
            <span>—</span>
            <b>{formatMoneyCompact(psa.p97_5, psa.currency)}</b>
            <span className="dim">· {formatCount(psa.iterations)} draws</span>
            {!psa.converged && <span className="flag">not converged</span>}
          </div>
        )}

        <p className="note">
          This is the <em>incremental</em> figure — spend in the world with the asset minus the
          world without it, net of the incumbent therapy it displaces. Peak year is Y
          {totals.peak_year}.
        </p>

        <div className="byyear">
          {totals.by_year.map((amount, i) => (
            <div key={i}>
              <span className="eyebrow">
                Y{i + 1} · {calculation.launch_year + i}
              </span>
              <span className="mono">{formatMoneyCompact(amount, totals.currency)}</span>
            </div>
          ))}
        </div>
      </section>

      {/* per-market -------------------------------------------------- */}
      <section>
        <h2>Per market</h2>
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Market</th>
                <th>Addressable</th>
                <th>On therapy, final year</th>
                <th>Cumulative impact</th>
                <th>Net cost / switch</th>
                <th>Price basis</th>
                <th>Affordability</th>
              </tr>
            </thead>
            <tbody>
              {calculation.countries.map((c) => {
                const last = c.years[c.years.length - 1];
                const derived = c.new_therapy.price_basis === "ppp_derived";
                return (
                  <tr key={c.country_code}>
                    <td>
                      <span className="mkt-name">{c.country_code}</span>
                      <span className="cur">{c.currency}</span>
                    </td>
                    <td className="num">{formatCount(last.addressable)}</td>
                    <td className="num">{formatCount(last.patients_on_new)}</td>
                    <td className="num">
                      {formatMoney(c.cumulative_budget_impact, c.currency)}
                    </td>
                    <td className="num">
                      {formatMoney(last.net_cost_per_switch, c.currency)}
                    </td>
                    <td>
                      <span className={derived ? "derived" : "chip t-B"}>
                        {BASIS_LABELS[c.new_therapy.price_basis] ?? c.new_therapy.price_basis}
                      </span>
                    </td>
                    <td>
                      {c.affordability && (
                        <span className={`chip b-${c.affordability.band}`}>
                          {c.affordability.band} ·{" "}
                          {formatPercent(c.affordability.cumulative_ratio, 3)}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* affordability ----------------------------------------------- */}
      {Object.keys(bands).length > 0 && (
        <AffordabilityGauge countries={calculation.countries} bands={bands} />
      )}

      {/* price corridor ---------------------------------------------- */}
      <PriceCorridor
        scenarioId={calculation.scenario_id}
        currentPriceUsd={
          // The solver reports in USD, so the comparison mark only means
          // something for a market already priced in USD.
          calculation.countries.find((c) => c.currency === "USD")?.new_therapy.unit_price ??
          null
        }
      />

      {/* cost bridge — M13 ------------------------------------------- */}
      {selected.cost_bridge && (
        <CostBridge
          bridge={selected.cost_bridge}
          currency={selected.currency}
          countryCode={selected.country_code}
          therapies={[selected.new_therapy, ...selected.therapies]}
        />
      )}

      {/* funnel ------------------------------------------------------ */}
      <section>
        <h2>Population funnel</h2>
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
        <div className="funnel">
          {selected.funnel.map((stage) => {
            const top = selected.funnel[0].value;
            return (
              <div className="frow" key={stage.stage}>
                <div className="fname">
                  {STAGE_LABELS[stage.stage] ?? stage.stage}
                  {stage.provenance && <Tier tier={stage.provenance.confidence_tier} />}
                </div>
                <div className="fbar">
                  <i style={{ width: `${Math.max((stage.value / top) * 100, 0.4)}%` }} />
                </div>
                <div className="fval mono">{formatCount(stage.value)}</div>
                <div className="ffac mono">
                  {stage.factor === null ? "—" : `× ${stage.factor.toFixed(4)}`}
                </div>
              </div>
            );
          })}
        </div>
        <details className="sources">
          <summary>Where these came from</summary>
          <ul>
            {selected.funnel
              .filter((s) => s.provenance)
              .map((s) => (
                <li key={s.stage}>
                  <b>{STAGE_LABELS[s.stage] ?? s.stage}</b>
                  <Tier tier={s.provenance!.confidence_tier} />
                  <span>{s.provenance!.source}</span>
                </li>
              ))}
          </ul>
        </details>
      </section>

      {/* tornado ----------------------------------------------------- */}
      {owsa && owsa.entries.length > 0 && (
        <section>
          <h2>What moves the answer</h2>
          <p className="lede">
            Each assumption swept to its own bounds with everything else held at base. The mark
            is the {formatMoneyCompact(owsa.base_result, owsa.currency)} base case.
          </p>
          <Tornado owsa={owsa} />
        </section>
      )}

      {/* evidence priority — M15, beside the tornado it reinterprets -- */}
      {gaps && <EvidencePriority report={gaps} />}

      {/* psa --------------------------------------------------------- */}
      {psa && (
        <section>
          <h2>Uncertainty</h2>
          <p className="lede">
            Every uncertain input sampled together, {formatCount(psa.iterations)} times.
          </p>
          <Histogram psa={psa} />
          <div className="psalegend">
            <span>
              Median <b>{formatMoneyCompact(psa.median, psa.currency)}</b>
            </span>
            <span>
              Mean <b>{formatMoneyCompact(psa.mean, psa.currency)}</b>
            </span>
            <span>
              2.5th <b>{formatMoneyCompact(psa.p2_5, psa.currency)}</b>
            </span>
            <span>
              97.5th <b>{formatMoneyCompact(psa.p97_5, psa.currency)}</b>
            </span>
          </div>
          {!psa.converged && (
            <p className="warnbox">
              The Monte Carlo has not converged at this iteration count. The interval is
              indicative rather than settled — raise the iterations or treat it as a stated
              limitation.
            </p>
          )}
        </section>
      )}

      {/* warnings ---------------------------------------------------- */}
      {calculation.warnings.length > 0 && (
        <section>
          <h2>Warnings</h2>
          <ul className="warnings">
            {calculation.warnings.map((w, i) => (
              <li key={i}>
                <code>{warningLabel(w.code)}</code>
                <span>{w.message}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

function Tornado({ owsa }: { owsa: Owsa }) {
  const lo = Math.min(...owsa.entries.map((e) => Math.min(e.result_at_low, e.result_at_high)));
  const hi = Math.max(...owsa.entries.map((e) => Math.max(e.result_at_low, e.result_at_high)));
  const pct = (v: number) => ((v - lo) / (hi - lo)) * 100;

  return (
    <div className="tor">
      {owsa.entries.map((e) => {
        const left = Math.min(e.result_at_low, e.result_at_high);
        const right = Math.max(e.result_at_low, e.result_at_high);
        return (
          <div className="trow" key={e.parameter_path}>
            <div className="tlab">{e.label}</div>
            <div className="tbar">
              <i style={{ left: `${pct(left)}%`, width: `${pct(right) - pct(left)}%` }} />
              <u style={{ left: `${pct(owsa.base_result)}%` }} />
              <span className="lo">{formatMoneyCompact(left, owsa.currency)}</span>
              <span className="hi">{formatMoneyCompact(right, owsa.currency)}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Histogram({ psa }: { psa: Psa }) {
  const max = Math.max(...psa.histogram);
  const span = psa.histogram_max - psa.histogram_min;
  const at = (v: number) => ((v - psa.histogram_min) / span) * 100;

  return (
    <div className="hist" role="img" aria-label={`Distribution of ${psa.iterations} draws`}>
      <div className="bars">
        {psa.histogram.map((n, i) => (
          <i key={i} style={{ height: `${(n / max) * 100}%` }} />
        ))}
      </div>
      <u className="median" style={{ left: `${at(psa.median)}%` }} />
      <u className="ci" style={{ left: `${at(psa.p2_5)}%` }} />
      <u className="ci" style={{ left: `${at(psa.p97_5)}%` }} />
      <div className="axis mono">
        <span>{formatMoneyCompact(psa.histogram_min, psa.currency)}</span>
        <span>{formatMoneyCompact(psa.histogram_max, psa.currency)}</span>
      </div>
    </div>
  );
}
