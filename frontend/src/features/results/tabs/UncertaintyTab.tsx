/**
 * How sure we are, and what would make us surer.
 *
 * Two panels that are usually confused with each other and answer different
 * questions. The tornado says what *moves* the answer. The evidence ranking
 * says what is worth *going and finding out*, which is the tornado re-weighted
 * by how weakly each input is founded — a parameter with a huge swing and a
 * published country-specific source is settled, and time spent re-deriving it
 * is time not spent on the assumption next to it.
 */

import type { EvidenceGapReport, Owsa, Psa } from "../../../shared/api";
import { EvidencePriority } from "../EvidencePriority";
import { Card, Placeholder } from "../../../shared/ui";
import { formatCount, formatMoneyCompact } from "../../../shared/format";

export function UncertaintyTab({
  owsa,
  psa,
  gaps,
  busy,
}: {
  owsa: Owsa | null;
  psa: Psa | null;
  gaps: EvidenceGapReport | null;
  busy: boolean;
}) {
  if (busy && !owsa && !psa) {
    return (
      <Card title="Uncertainty">
        <Placeholder title="Running the analyses">
          A one-way sweep of every parameter, then a Monte Carlo over all of them
          together. Both are seeded, so a re-run reproduces exactly.
        </Placeholder>
      </Card>
    );
  }

  return (
    <>
      {owsa && owsa.entries.length > 0 && (
        <Card
          title="What moves the answer"
          lede={
            <>
              Each assumption swept to its own bounds with everything else held at
              base. The mark is the{" "}
              {formatMoneyCompact(owsa.base_result, owsa.currency)} base case.
            </>
          }
        >
          <Tornado owsa={owsa} />
        </Card>
      )}

      {gaps && <EvidencePriority report={gaps} />}

      {psa && (
        <Card
          title="Probabilistic sensitivity"
          lede={
            <>
              Every uncertain input sampled together, {formatCount(psa.iterations)}{" "}
              times. This is the interval to quote — the three adoption cases on
              the Payer tab are a framing device, not an uncertainty range.
            </>
          }
        >
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
              The Monte Carlo has not converged at this iteration count. The
              interval is indicative rather than settled — raise the iterations or
              treat it as a stated limitation.
            </p>
          )}
        </Card>
      )}
    </>
  );
}

function Tornado({ owsa }: { owsa: Owsa }) {
  const lo = Math.min(
    ...owsa.entries.map((e) => Math.min(e.result_at_low, e.result_at_high)),
  );
  const hi = Math.max(
    ...owsa.entries.map((e) => Math.max(e.result_at_low, e.result_at_high)),
  );
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
