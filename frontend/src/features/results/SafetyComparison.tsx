/**
 * M13 section 9 — what the adverse-event cost was computed from.
 *
 * The bridge gives one number per therapy. This is its working: each
 * incidence with the trial it was observed in, the population it was observed
 * in, and the window it was observed over. A reader can check it rather than
 * take it, which is the whole basis on which this tool is allowed to put a
 * price on a safety difference.
 */
import { useEffect, useState } from "react";
import {
  api,
  type ApiError,
  type SafetyComparison as Comparison,
  type Therapy,
} from "../../shared/api";
import { formatMoney } from "../../shared/format";

export function SafetyComparison({
  countryCode,
  currency,
  therapies,
}: {
  countryCode: string;
  currency: string;
  therapies: Therapy[];
}) {
  const [data, setData] = useState<Comparison | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ids = therapies.map((t) => t.drug_id);
  const key = `${countryCode}:${ids.join(",")}`;

  useEffect(() => {
    let live = true;
    api
      .safetyComparison(countryCode, ids)
      .then((d) => live && setData(d))
      .catch((e: ApiError) => live && setError(e.message));
    return () => {
      live = false;
    };
    // `key` collapses the two dependencies that actually matter; `ids` is a
    // fresh array every render and would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  if (error) return null;
  if (!data || data.events.length === 0) return null;

  // Only therapies that actually have a profile get a column. A column of
  // blanks would read as "no events", which is not what a missing profile
  // means (M13 section 5.1).
  const withProfile = therapies.filter((t) =>
    data.events.some((e) => e.by_drug[String(t.drug_id)]),
  );

  return (
    <details className="safety-detail">
      <summary>
        Where the adverse-event figure comes from — {data.events.length} events,{" "}
        {withProfile.length} of {therapies.length} therapies
      </summary>

      <table className="safety-table">
        <thead>
          <tr>
            <th>Event</th>
            <th>Cost each</th>
            {withProfile.map((t) => (
              <th key={t.drug_id}>{t.name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.events.map((event) => (
            <tr key={event.ae_code}>
              <td>{event.ae_label}</td>
              <td className="num">
                {event.unit_cost === null ? "—" : formatMoney(event.unit_cost, currency)}
                {event.unit_cost_tier && (
                  <span className={`tier tier-${event.unit_cost_tier}`}>
                    {event.unit_cost_tier}
                  </span>
                )}
              </td>
              {withProfile.map((t) => {
                const cell = event.by_drug[String(t.drug_id)];
                if (!cell) return <td key={t.drug_id}>—</td>;
                return (
                  <td key={t.drug_id} className="num" title={cell.source}>
                    {(cell.annualised * 100).toFixed(1)}%
                    <span className="observed">
                      {(cell.observed * 100).toFixed(1)}% over {cell.exposure_weeks ?? 52}w
                    </span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

      <p className="footnote">
        The larger figure is the rate as annualised for this model; the smaller is what the
        trial reported, over the window it reported it. Converting assumes constant hazard,
        which overstates the back half of the year for events concentrated in titration —
        gastrointestinal events on an incretin, characteristically. Unit costs marked C are
        analyst constructions rather than observed costs; hover any rate for its trial.
      </p>
    </details>
  );
}
