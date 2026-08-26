/**
 * The thing you actually send someone.
 *
 * The narrative with its citations, the exports, and — first — the warnings.
 *
 * Warnings lead rather than trail because of what they are here. This system's
 * warnings are not lint: `MIXED_PRICE_BASIS` says the comparison is not
 * like-for-like, `TIER_D_INPUT` says a figure is an admitted placeholder,
 * `SUBGROUP_SHARES_UNBALANCED` says the denominator moved. A reader who exports
 * the deck without seeing them exports a number that reads as clean and is not.
 */

import type { Calculation } from "../../../shared/api";
import { Evidence } from "../../evidence/Evidence";
import { Card } from "../../../shared/ui";
import { warningLabel } from "../../../shared/format";

/** Codes that qualify the *headline* rather than a detail. Ordered first, and
 *  visually distinct, because the difference between "this figure rests on a
 *  placeholder" and "this market has no adverse-event costs" is the difference
 *  between a caveat and a footnote. */
const STRUCTURAL = new Set([
  "MIXED_PRICE_BASIS",
  "TIER_D_INPUT",
  "SUBGROUP_SHARES_UNBALANCED",
  "COVERED_POPULATION_ASSUMED",
  "NO_OUTCOME_EVIDENCE",
  "PIPELINE_ENTRANT_MODELLED",
]);

export function DeliverableTab({ calculation }: { calculation: Calculation }) {
  const structural = calculation.warnings.filter((w) => STRUCTURAL.has(w.code));
  const detail = calculation.warnings.filter((w) => !STRUCTURAL.has(w.code));

  return (
    <>
      {structural.length > 0 && (
        <Card
          title="Read these before quoting the number"
          lede="Each of these qualifies the headline figure itself rather than a detail below it."
        >
          <ul className="warnings structural">
            {structural.map((w, i) => (
              <li key={i}>
                <code>{warningLabel(w.code)}</code>
                <span>
                  {w.country_code && <b>{w.country_code} · </b>}
                  {w.message}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Evidence scenarioId={calculation.scenario_id} />

      {detail.length > 0 && (
        <Card title="Everything else this run flagged">
          <ul className="warnings">
            {detail.map((w, i) => (
              <li key={i}>
                <code>{warningLabel(w.code)}</code>
                <span>
                  {w.country_code && <b>{w.country_code} · </b>}
                  {w.message}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Run provenance">
        <dl className="import-read">
          <dt>Engine</dt>
          <dd>{calculation.engine_version}</dd>
          <dt>FX snapshot</dt>
          <dd>{calculation.fx_snapshot_date}</dd>
          <dt>Reporting currency</dt>
          <dd>{calculation.reporting_currency}</dd>
          <dt>Perspective</dt>
          <dd>{calculation.payer?.perspective_label ?? calculation.perspective ?? "—"}</dd>
          <dt>Horizon</dt>
          <dd>
            {calculation.launch_year}–
            {calculation.launch_year + calculation.horizon_years - 1}
          </dd>
          <dt>Computed in</dt>
          <dd>{calculation.duration_ms ?? "—"} ms</dd>
        </dl>
        <p className="chart-note">
          Exchange rates are snapshotted into the run rather than looked up live,
          so re-opening this result reproduces its original numbers exactly.
        </p>
      </Card>
    </>
  );
}
