/**
 * The answer, and the two totals it sits between.
 *
 * Everything a formulary conversation opens with is here and nothing else is:
 * what it costs cumulatively, what that is per year, how it compares with
 * doing nothing, and how uncertain the whole thing is. The working is on the
 * other tabs.
 */

import type { Calculation, Psa } from "../../../shared/api";
import { Card, Stat, StatRow } from "../../../shared/ui";
import {
  formatCount,
  formatMoney,
  formatMoneyCompact,
  formatPercent,
} from "../../../shared/format";
import { ImpactChart, WithWithoutChart } from "../WithWithout";
import { Interpretation, VerdictChip } from "../Interpretation";

export function SummaryTab({
  calculation,
  psa,
}: {
  calculation: Calculation;
  psa: Psa | null;
}) {
  const { totals, payer } = calculation;
  const horizon = calculation.horizon_years;
  const lastYear = calculation.launch_year + horizon - 1;
  const saving = totals.cumulative < 0;

  const patientsFinalYear = calculation.countries.reduce(
    (sum, c) => sum + (c.years.at(-1)?.patients_on_new ?? 0),
    0,
  );
  const addressableFinalYear = calculation.countries.reduce(
    (sum, c) => sum + (c.years.at(-1)?.addressable ?? 0),
    0,
  );
  const eventsAvoided = calculation.countries.reduce(
    (sum, c) =>
      sum + (c.outcomes?.events.reduce((n, e) => n + e.total_avoided, 0) ?? 0),
    0,
  );
  const costAvoided = calculation.countries.reduce(
    (sum, c) => sum + (c.outcomes?.total_cost_avoided ?? 0),
    0,
  );
  // Patients on the new therapy, summed across markets, per year — the shape
  // the adoption curve actually produces rather than its two endpoints.
  const patientsByYear = totals.by_year.map((_, index) =>
    calculation.countries.reduce(
      (sum, c) => sum + (c.years[index]?.patients_on_new ?? 0),
      0,
    ),
  );

  return (
    <>
      <section className="headline">
        <div className="eyebrow">
          Cumulative incremental budget impact · {calculation.launch_year}–{lastYear}
        </div>
        <div className={`figure ${saving ? "figure-saving" : ""}`}>
          {formatMoneyCompact(totals.cumulative, totals.currency)}
        </div>

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
          This is the <em>incremental</em> figure — spend in the world with the
          asset minus the world without it, net of the incumbent therapy it
          displaces. It is never the gross cost of the new therapy.
          {saving && " It is negative here, which means a saving."}
        </p>
      </section>

      <StatRow>
        <Stat
          label="Peak single year"
          value={`Y${totals.peak_year}`}
          sub={formatMoneyCompact(
            totals.by_year[totals.peak_year - 1] ?? 0,
            totals.currency,
          )}
          tone="accent"
          trend={totals.by_year}
        />
        <Stat
          label={`Patients treated, Y${horizon}`}
          value={formatCount(patientsFinalYear)}
          sub={`of ${formatCount(addressableFinalYear)} addressable`}
          trend={patientsByYear}
          delta={
            patientsByYear.length > 1 && patientsByYear[0] > 0
              ? patientsByYear[patientsByYear.length - 1] / patientsByYear[0] - 1
              : null
          }
        />
        <Stat
          label="Cost per treated patient"
          value={
            payer
              ? formatMoney(payer.cost_per_treated_patient, payer.currency)
              : "—"
          }
          sub="cumulative impact ÷ patient-years"
        />
        {eventsAvoided > 0 && (
          <Stat
            label="Clinical events avoided"
            value={formatCount(eventsAvoided)}
            sub={`${formatMoneyCompact(costAvoided, totals.currency)} of care avoided`}
            tone="good"
          />
        )}
      </StatRow>

      <Interpretation calculation={calculation} />

      <Card
        title="Without intervention against with intervention"
        lede={
          <>
            Total cost of care for this population under current treatment,
            beside the same population with the new therapy in the mix. The two
            bars are close, and that is the finding rather than a chart failing
            to be dramatic — budget impact is a small number found between two
            large ones. The difference is charted on its own scale below.
          </>
        }
      >
        {payer ? (
          <WithWithoutChart
            launchYear={calculation.launch_year}
            without={payer.total_cost_current_care}
            withNew={payer.total_cost_with_intervention}
            currency={totals.currency}
          />
        ) : (
          <p className="dim">No payer view for this run.</p>
        )}
      </Card>

      {payer && (
        <Card
          title="Current scenario against new scenario"
          lede="The same population under each, so the incremental figure can be read as the difference between two columns rather than taken on trust."
        >
          <div className="tablewrap">
            <table className="scenario-compare">
              <thead>
                <tr>
                  <th />
                  <th>Without intervention</th>
                  <th>With intervention</th>
                  <th>Difference</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Addressable patients, Y{horizon}</td>
                  <td className="num">{formatCount(addressableFinalYear)}</td>
                  <td className="num">{formatCount(addressableFinalYear)}</td>
                  <td className="num dim">no change</td>
                </tr>
                <tr>
                  <td>Patients on the new therapy, Y{horizon}</td>
                  <td className="num">0</td>
                  <td className="num">{formatCount(patientsFinalYear)}</td>
                  <td className="num strong">
                    +{formatCount(patientsFinalYear)}
                  </td>
                </tr>
                <tr>
                  <td>Annual cost of care, Y{horizon}</td>
                  <td className="num">
                    {formatMoney(payer.total_cost_current_care.at(-1) ?? 0, totals.currency)}
                  </td>
                  <td className="num">
                    {formatMoney(
                      payer.total_cost_with_intervention.at(-1) ?? 0,
                      totals.currency,
                    )}
                  </td>
                  <td className="num strong">
                    {formatMoney(totals.by_year.at(-1) ?? 0, totals.currency)}
                  </td>
                </tr>
                <tr className="peak">
                  <td>
                    <b>Cumulative over {horizon} years</b>
                  </td>
                  <td className="num">
                    {formatMoney(
                      payer.total_cost_current_care.reduce((a, b) => a + b, 0),
                      totals.currency,
                    )}
                  </td>
                  <td className="num">
                    {formatMoney(
                      payer.total_cost_with_intervention.reduce((a, b) => a + b, 0),
                      totals.currency,
                    )}
                  </td>
                  <td className="num strong">
                    {formatMoney(totals.cumulative, totals.currency)}{" "}
                    <VerdictChip amount={totals.cumulative} />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Card
        title="Incremental impact, year by year"
        lede="The difference on its own axis, where its shape is legible, with the running cumulative over it. Bars below the zero line are years the therapy saves money."
      >
        <ImpactChart
          launchYear={calculation.launch_year}
          impact={totals.by_year}
          cumulative={totals.cumulative}
          currency={totals.currency}
          peakYear={totals.peak_year}
        />
      </Card>

      <Card title="The numbers behind the charts">
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Year</th>
                <th>Without intervention</th>
                <th>With intervention</th>
                <th>Incremental</th>
                <th>Cumulative</th>
                <th>Patients treated</th>
              </tr>
            </thead>
            <tbody>
              {totals.by_year.map((impact, index) => {
                const cumulative = totals.by_year
                  .slice(0, index + 1)
                  .reduce((a, b) => a + b, 0);
                const patients = calculation.countries.reduce(
                  (sum, c) => sum + (c.years[index]?.patients_on_new ?? 0),
                  0,
                );
                return (
                  <tr key={index} className={index + 1 === totals.peak_year ? "peak" : ""}>
                    <td>
                      Y{index + 1}
                      <span className="cur">{calculation.launch_year + index}</span>
                    </td>
                    <td className="num">
                      {payer
                        ? formatMoney(
                            payer.total_cost_current_care[index] ?? 0,
                            totals.currency,
                          )
                        : "—"}
                    </td>
                    <td className="num">
                      {payer
                        ? formatMoney(
                            payer.total_cost_with_intervention[index] ?? 0,
                            totals.currency,
                          )
                        : "—"}
                    </td>
                    <td className="num strong">
                      {formatMoney(impact, totals.currency)}
                    </td>
                    <td className="num">{formatMoney(cumulative, totals.currency)}</td>
                    <td className="num">{formatCount(patients)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {payer && (
          <p className="chart-note">
            Incremental as a share of current spend runs from{" "}
            {formatPercent(
              (totals.by_year[0] ?? 0) / (payer.total_cost_current_care[0] || 1),
              2,
            )}{" "}
            in Y1 to{" "}
            {formatPercent(
              (totals.by_year.at(-1) ?? 0) /
                (payer.total_cost_current_care.at(-1) || 1),
              2,
            )}{" "}
            in Y{horizon}.
          </p>
        )}
      </Card>
    </>
  );
}
