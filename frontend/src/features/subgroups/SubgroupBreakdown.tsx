/**
 * The obesity population, split into the clinically distinct groups inside it
 * — M18 sections 5.1 and 5.2.
 *
 * The split hangs off the **diseased** stage of the funnel, which is the adult
 * population that actually has obesity. Applying it further up would divide
 * people who do not have the disease across its subgroups.
 *
 * Two things this component exists to make impossible to miss. The five adult
 * groups partition the population — a patient with obesity, diabetes and
 * hypertension is counted once, in the highest-risk group they qualify for,
 * because adding the three raw comorbidity prevalences would count them three
 * times. And obesity alone is the *residual*: it is derived from the other
 * four, never supplied, and it is labelled as derived on screen.
 */
import { useEffect, useState } from "react";
import { api, ApiError, type SubgroupOption } from "../../shared/api";
import { formatCount, formatPercent, TIER_MEANING } from "../../shared/format";

interface SubgroupBreakdownProps {
  /** The `diseased` stage count for the selected market. */
  diseased: number;
}

export function SubgroupBreakdown({ diseased }: SubgroupBreakdownProps) {
  const [options, setOptions] = useState<SubgroupOption[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .subgroups()
      .then(setOptions)
      .catch((e: ApiError) => setError(e.message));
  }, []);

  if (error) {
    return <p className="note">Subgroup taxonomy unavailable — {error}</p>;
  }
  if (!options) {
    return <p className="note">Loading subgroups…</p>;
  }

  const adult = options.filter((o) => !o.is_disjoint);
  const supplied = adult.filter((o) => o.default_share !== null);
  const suppliedTotal = supplied.reduce((sum, o) => sum + (o.default_share ?? 0), 0);
  const residualShare = 1 - suppliedTotal;

  const rows = adult.map((option) => {
    const share = option.is_residual ? residualShare : (option.default_share ?? 0);
    return { option, share, patients: diseased * share };
  });

  const paediatric = options.find((o) => o.is_disjoint);

  return (
    <div className="subgroups">
      <h3 className="nsec">Who these patients are</h3>
      <p className="lede">
        The {formatCount(diseased)} adults with obesity above, split into the groups that
        differ in what they are treated with today and in the events a therapy avoids.
        Each patient is counted once, in the highest-risk group they qualify for — adding
        raw comorbidity prevalences would count someone with obesity, diabetes and
        hypertension three times.
      </p>

      <div className="tablewrap">
        <table className="subgroup-table">
          <thead>
            <tr>
              <th>Subgroup</th>
              <th>Share</th>
              <th>Patients</th>
              <th>Basis</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ option, share, patients }) => (
              <tr key={option.code}>
                <td>
                  <span className="subgroup-name">{option.label}</span>
                  <span className="field-foot">{option.definition}</span>
                </td>
                <td className="num">{formatPercent(share)}</td>
                <td className="num">{formatCount(patients)}</td>
                <td>
                  {option.is_residual ? (
                    <span className="derived">derived residual</span>
                  ) : (
                    <span
                      className={`tier tier-${option.confidence_tier}`}
                      title={TIER_MEANING[option.confidence_tier]}
                    >
                      {option.confidence_tier}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td><strong>All adults with obesity</strong></td>
              <td className="num"><strong>{formatPercent(1)}</strong></td>
              <td className="num"><strong>{formatCount(diseased)}</strong></td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>

      {paediatric && (
        <p className="note">
          <strong>{paediatric.label}</strong> is deliberately not in the table above.
          {" "}{paediatric.definition}
        </p>
      )}

      <p className="note">
        Every share is <strong>tier {supplied[0]?.confidence_tier ?? "C"}</strong> and global
        rather than country-specific: {supplied[0]?.source.toLowerCase()}. This split is one of
        the least certain things in the model, and the evidence-priority panel ranks it
        accordingly rather than presenting it as settled.
      </p>
    </div>
  );
}
