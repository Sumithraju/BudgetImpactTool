/**
 * What the number means, in the words a reader would use.
 *
 * A budget impact figure has a sign, and the sign is the whole finding. Every
 * result in this system can come out either way — the therapy adds cost where
 * it displaces cheap care, and saves money where it displaces expensive care,
 * and Germany and the United Kingdom genuinely land on opposite sides for that
 * reason.
 *
 * A minus sign in a table is not enough to carry that. "−£28,757,333" is read
 * as a large cost by anyone skimming, and the difference between a cost and a
 * saving is the difference between two opposite recommendations. So the sign is
 * stated in words, on the figure, every time.
 *
 * The interpretations here are deliberately not conclusions. They say what the
 * arithmetic means, and where the model knows the arithmetic rests on something
 * shaky — a mixed price basis, an assumed denominator — they say that too,
 * because a saving produced by comparing an observed price against derived
 * comparators is an artefact and reads exactly like a finding.
 */

import type { Calculation } from "../../shared/api";
import { Card } from "../../shared/ui";
import { formatMoneyCompact, formatPercent } from "../../shared/format";

export interface Verdict {
  /** "cost" | "saving" | "neutral" */
  kind: "cost" | "saving" | "neutral";
  label: string;
  tone: "pos" | "neg" | "flat";
}

/** Near enough to zero that calling it either is overclaiming. */
const NEUTRAL_BAND = 1e-6;

export function verdictOf(amount: number): Verdict {
  if (Math.abs(amount) < NEUTRAL_BAND) {
    return { kind: "neutral", label: "budget-neutral", tone: "flat" };
  }
  return amount > 0
    ? { kind: "cost", label: "adds cost", tone: "pos" }
    : { kind: "saving", label: "saves money", tone: "neg" };
}

/** Codes that make a *saving* untrustworthy specifically. */
const ARTEFACT_CODES = new Set(["MIXED_PRICE_BASIS", "COMPARATOR_UNPRICED"]);

export function Interpretation({ calculation }: { calculation: Calculation }) {
  const { totals } = calculation;
  const overall = verdictOf(totals.cumulative);
  const horizon = calculation.horizon_years;
  const currency = totals.currency;

  const costs = calculation.countries.filter((c) => c.cumulative_budget_impact > 0);
  const savings = calculation.countries.filter((c) => c.cumulative_budget_impact < 0);

  const artefacts = calculation.warnings.filter((w) => ARTEFACT_CODES.has(w.code));
  const artefactMarkets = new Set(
    artefacts.map((w) => w.country_code).filter(Boolean) as string[],
  );

  const peakShare =
    totals.by_year.length > 0
      ? (totals.by_year[totals.peak_year - 1] ?? 0) / (totals.cumulative || 1)
      : 0;

  return (
    <Card title="How to read this">
      <div className={`verdict verdict-${overall.tone}`}>
        <span className="verdict-figure mono">
          {formatMoneyCompact(totals.cumulative, currency)}
        </span>
        <span className="verdict-label">
          {overall.kind === "cost"
            ? "Adds cost to the budget"
            : overall.kind === "saving"
              ? "Saves money against current care"
              : "Budget-neutral"}
        </span>
      </div>

      <ul className="reading">
        <li>
          <b>The sign.</b>{" "}
          {overall.kind === "cost" ? (
            <>
              This is <b>positive</b>, so funding the therapy costs the payer{" "}
              {formatMoneyCompact(totals.cumulative, currency)} more over{" "}
              {horizon} years than continuing with current care. It is the{" "}
              <em>incremental</em> figure — what the therapy costs minus what the
              care it displaces costs — never the gross cost of the new therapy.
            </>
          ) : overall.kind === "saving" ? (
            <>
              This is <b>negative</b>, which means a saving rather than a large
              cost. The therapy displaces care that costs more than it does, so
              the payer spends{" "}
              {formatMoneyCompact(Math.abs(totals.cumulative), currency)} less
              over {horizon} years than by continuing as they are.
            </>
          ) : (
            <>
              The therapy costs the payer almost exactly what the care it
              displaces costs. Neither a cost nor a saving at this price.
            </>
          )}
        </li>

        {costs.length > 0 && savings.length > 0 && (
          <li>
            <b>Markets disagree.</b> {costs.map((c) => c.country_code).join(", ")}{" "}
            {costs.length === 1 ? "adds" : "add"} cost, while{" "}
            {savings.map((c) => c.country_code).join(", ")}{" "}
            {savings.length === 1 ? "saves" : "save"} money. That is normal
            rather than contradictory: the same therapy at the same price
            displaces different comparators at different local prices, and the
            sign follows whichever is dearer.
          </li>
        )}

        <li>
          <b>The year that matters.</b> The peak single year is Y
          {totals.peak_year} at{" "}
          {formatMoneyCompact(totals.by_year[totals.peak_year - 1] ?? 0, currency)}{" "}
          — {formatPercent(Math.abs(peakShare), 0)} of the cumulative figure. A
          budget holder has to find that in one year, which is usually a harder
          question than the total.
        </li>

        {artefacts.length > 0 && (
          <li className="reading-warn">
            <b>Read the sign with caution
            {artefactMarkets.size > 0 ? ` in ${[...artefactMarkets].join(", ")}` : ""}.
            </b>{" "}
            {artefacts.some((w) => w.code === "MIXED_PRICE_BASIS") && (
              <>
                Some markets compare an observed price for the new asset against
                comparators whose prices are derived from a different market.
                Derived prices inherit the reference market's price level, and
                where that level is higher the comparison is not like-for-like —
                a saving produced that way is an artefact of the price basis, not
                a finding about the therapy.{" "}
              </>
            )}
            {artefacts.some((w) => w.code === "COMPARATOR_UNPRICED") && (
              <>
                At least one therapy that is part of current care carries no
                price at all and is excluded from the world-without, so the cost
                shown is higher than it would be with that therapy included.
              </>
            )}
          </li>
        )}

        <li>
          <b>What would change it.</b> The Uncertainty tab ranks the assumptions
          by how far each one moves this figure, and separately by which of them
          are worth going and finding out. The Payer view gives the price at
          which the sign flips.
        </li>
      </ul>
    </Card>
  );
}

/**
 * A compact sign-aware badge, for tables where the full reading is too much.
 */
export function VerdictChip({ amount }: { amount: number }) {
  const verdict = verdictOf(amount);
  return <span className={`chip v-${verdict.tone}`}>{verdict.label}</span>;
}
