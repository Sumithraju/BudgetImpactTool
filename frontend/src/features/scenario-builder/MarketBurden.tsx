/**
 * What the chosen markets look like, before anything is run.
 *
 * Choosing markets is an epidemiological decision — India and the United States
 * differ by a factor of four in obesity prevalence, and that difference drives
 * the answer more than most of the levers below it. Putting WHO's figures on
 * the same screen as the choice means the analyst sees what they are picking
 * rather than discovering it in the result.
 *
 * Prevalence and incidence sit in separate columns, in separate units, for the
 * reason they do everywhere else in this tool: one is a standing pool and the
 * other an annual flow, and for a persistent condition they differ by more than
 * an order of magnitude.
 */

import { useEffect, useState } from "react";
import { api, type HealthIndicator } from "../../shared/api";
import { Card, Placeholder } from "../../shared/ui";
import { formatCount, formatPercent, TIER_MEANING } from "../../shared/format";

const PREVALENCE = "obesity_prevalence_adult";
const INCIDENCE = "obesity_incidence_annual";
const DIABETES = "diabetes_prevalence";
const HYPERTENSION = "hypertension_prevalence";

export function MarketBurden({ countryCodes }: { countryCodes: string[] }) {
  const [rows, setRows] = useState<HealthIndicator[]>([]);
  const [loading, setLoading] = useState(false);
  const key = countryCodes.join(",");

  useEffect(() => {
    if (!countryCodes.length) return;
    setLoading(true);
    api
      .marketEpidemiology(countryCodes)
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
    // `key` is the market set as a stable string; the array identity changes on
    // every render and would re-fetch forever.
  }, [key]);

  if (loading && !rows.length) {
    return (
      <Card title="Disease burden in the chosen markets">
        <Placeholder title="Loading WHO indicators">
          Prevalence, incidence and comorbidity figures for each selected market.
        </Placeholder>
      </Card>
    );
  }
  if (!rows.length) return null;

  const byMarket = new Map<string, Map<string, HealthIndicator>>();
  for (const row of rows) {
    if (!byMarket.has(row.country_code)) byMarket.set(row.country_code, new Map());
    byMarket.get(row.country_code)!.set(row.indicator, row);
  }
  // Every selected market gets a row, including the ones WHO's file does not
  // cover. An omitted row reads as "not selected"; a row of dashes reads as
  // "selected, and we have nothing for it" — which is the true state and the
  // one that tells the analyst their result there rests on fallbacks.
  const markets = countryCodes;
  const missing = markets.filter((c) => !byMarket.has(c));
  if (!byMarket.size) return null;

  const value = (code: string, indicator: string) =>
    byMarket.get(code)?.get(indicator);

  return (
    <Card
      title="Disease burden in the chosen markets"
      lede={
        <>
          WHO's published figures for the markets currently selected. Prevalence
          is the standing pool the funnel starts from; incidence is the annual
          inflow, quoted per 100,000 at risk. They are different quantities and
          are never added together.
        </>
      }
    >
      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th>Market</th>
              <th>
                Obesity prevalence
                <span className="cur">adults, age-std</span>
              </th>
              <th>
                Obesity incidence
                <span className="cur">per 100k / yr</span>
              </th>
              <th>
                Diabetes prevalence
                <span className="cur">adults</span>
              </th>
              <th>
                Hypertension prevalence
                <span className="cur">adults 30-79</span>
              </th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {markets.map((code) => {
              const prevalence = value(code, PREVALENCE);
              const incidence = value(code, INCIDENCE);
              return (
                <tr key={code}>
                  <td>
                    <span className="mkt-name">{code}</span>
                  </td>
                  <td className="num strong">
                    {prevalence?.value == null
                      ? "—"
                      : formatPercent(prevalence.value, 1)}
                  </td>
                  <td className="num">
                    {incidence?.per_100k == null
                      ? "—"
                      : formatCount(incidence.per_100k)}
                  </td>
                  <td className="num">
                    {value(code, DIABETES)?.value == null
                      ? "—"
                      : formatPercent(value(code, DIABETES)!.value!, 1)}
                  </td>
                  <td className="num">
                    {value(code, HYPERTENSION)?.value == null
                      ? "—"
                      : formatPercent(value(code, HYPERTENSION)!.value!, 1)}
                  </td>
                  <td>
                    {prevalence && (
                      <span
                        className={`chip t-${prevalence.confidence_tier}`}
                        title={TIER_MEANING[prevalence.confidence_tier]}
                      >
                        {prevalence.confidence_tier}
                      </span>
                    )}
                    {incidence && (
                      <span
                        className={`chip t-${incidence.confidence_tier}`}
                        title={incidence.source}
                      >
                        incidence {incidence.confidence_tier}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="chart-note">
        WHO publishes prevalence, not incidence. The incidence column is derived
        from prevalence under a stated mean-duration assumption and carries a
        weaker confidence tier for that reason — hover it to see the derivation.
      </p>
      {missing.length > 0 && (
        <p className="chart-note warn">
          <b>{missing.join(", ")}</b> {missing.length === 1 ? "is" : "are"} in
          this scenario but not in the WHO indicator set loaded here, so{" "}
          {missing.length === 1 ? "its" : "their"} prevalence comes from the
          model's own epidemiology table instead. The run still works; the
          figures behind {missing.length === 1 ? "that market" : "those markets"}{" "}
          are simply not the ones in this table.
        </p>
      )}
    </Card>
  );
}
