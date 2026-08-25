/**
 * M13 section 9 — the cost bridge.
 *
 * A waterfall from the new therapy's cost through each component to the net
 * cost per patient switched. It answers what a payer actually asks: not what
 * the new therapy costs, but of the difference, how much is price and how
 * much is everything else.
 *
 * The terms sum to the net exactly — that is asserted in the engine, not
 * arranged here — so the chart can be read as arithmetic rather than as an
 * illustration.
 */
import { type CostBridge as Bridge, type Therapy } from "../../shared/api";
import { formatMoney } from "../../shared/format";
import { SafetyComparison } from "./SafetyComparison";

const LABELS: Record<string, string> = {
  acquisition: "Acquisition",
  admin: "Administration",
  monitoring: "Monitoring",
  ae: "Adverse events",
  offset: "Cost offsets",
};

const EXPLAIN: Record<string, string> = {
  acquisition: "What the drug costs to buy, net of discount and inflated for wastage",
  admin: "Delivering it — infusion chairs, pharmacy time, day-case slots",
  monitoring: "Tests and visits the therapy itself requires",
  ae: "Expected cost of managing its adverse events, incidence times unit cost",
  offset: "Costs avoided elsewhere. A saving, so it subtracts",
};

export function CostBridge({
  bridge,
  currency,
  countryCode,
  therapies,
}: {
  bridge: Bridge;
  currency: string;
  countryCode: string;
  therapies: Therapy[];
}) {
  // The offset enters negatively, as it does in the annual cost itself.
  const signed = bridge.terms.map((t) => ({
    ...t,
    contribution: t.component === "offset" ? -t.delta : t.delta,
  }));

  const scale = Math.max(
    ...signed.map((t) => Math.abs(t.contribution)),
    Math.abs(bridge.net_cost_per_switch),
    1,
  );

  return (
    <section>
      <h2>What the difference is made of</h2>
      <p className="lede">
        Every patient who switches to the new therapy costs the payer{" "}
        <strong>{formatMoney(bridge.net_cost_per_switch, currency)}</strong> more than the
        care they were receiving. Not the new therapy's price — the difference between it
        and what it displaces, across every component of cost.
      </p>

      <ul className="bridge">
        {signed.map((term) => (
          <li key={term.component} title={EXPLAIN[term.component] ?? term.component}>
            <span className="bridge-label">{LABELS[term.component] ?? term.component}</span>
            <span className="bridge-track">
              <span
                className={term.contribution >= 0 ? "bridge-bar up" : "bridge-bar down"}
                style={{ width: `${(Math.abs(term.contribution) / scale) * 100}%` }}
              />
            </span>
            <span className="bridge-value num">
              {term.contribution >= 0 ? "+" : "−"}
              {formatMoney(Math.abs(term.contribution), currency)}
            </span>
          </li>
        ))}
        <li className="bridge-net">
          <span className="bridge-label">Net cost per switch</span>
          <span className="bridge-track">
            <span
              className={
                bridge.net_cost_per_switch >= 0 ? "bridge-bar up net" : "bridge-bar down net"
              }
              style={{
                width: `${(Math.abs(bridge.net_cost_per_switch) / scale) * 100}%`,
              }}
            />
          </span>
          <span className="bridge-value num">
            {formatMoney(bridge.net_cost_per_switch, currency)}
          </span>
        </li>
      </ul>

      <table className="bridge-table">
        <thead>
          <tr>
            <th>Component</th>
            <th>New therapy</th>
            <th>What it displaces</th>
            <th>Difference</th>
          </tr>
        </thead>
        <tbody>
          {bridge.terms.map((term) => (
            <tr key={term.component}>
              <td>{LABELS[term.component] ?? term.component}</td>
              <td className="num">{formatMoney(term.new_therapy, currency)}</td>
              <td className="num">{formatMoney(term.displaced, currency)}</td>
              <td className="num">{formatMoney(term.delta, currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <SafetyComparison
        countryCode={countryCode}
        currency={currency}
        therapies={therapies}
      />

      <p className="footnote">
        Both sides are persistence-adjusted and weighted by where the switching patients
        came from, so the figures are per patient-year of actual exposure rather than per
        prescription. Adverse-event costs are modelled only where trial or label evidence
        states an incidence — the tool prices the events evidence reports, and never asserts
        a safety advantage of its own.
      </p>
    </section>
  );
}
