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
import type { SubgroupOption } from "../../shared/api";
import { formatCount, formatPercent, TIER_MEANING } from "../../shared/format";
import { GLOSSARY } from "../../shared/glossary";
import { Hint } from "../../shared/Hint";
import type { SubgroupShares } from "./SubgroupShareEditor";

interface SubgroupBreakdownProps {
  /** The `diseased` stage count for the selected market. */
  diseased: number;
  options: SubgroupOption[];
  /** The analyst's shares, which may differ from the seeded defaults. */
  shares: SubgroupShares;
}

export function SubgroupBreakdown({ diseased, options, shares }: SubgroupBreakdownProps) {
  if (options.length === 0) {
    return <p className="note">Subgroup taxonomy unavailable.</p>;
  }

  const adult = options.filter((o) => !o.is_disjoint);
  const supplied = adult.filter((o) => !o.is_residual);
  const suppliedTotal = supplied.reduce((sum, o) => sum + (shares[o.code] ?? 0), 0);
  const residualShare = 1 - suppliedTotal;

  // Over-allocated shares leave a negative residual, which would render as a
  // negative patient count — arithmetically consistent and clinically absurd.
  // The engine refuses this set outright; the interface says so rather than
  // drawing a table nobody should read.
  if (residualShare < 0) {
    return (
      <div className="subgroups">
        <h3 className="nsec">Who these patients are</h3>
        <p className="alert" role="alert">
          The four subgroup shares total {formatPercent(suppliedTotal)}, which leaves no
          room for patients with none of these conditions. They must total less than 100%
          before this population can be split. Adjust them in the panel on the left.
        </p>
      </div>
    );
  }

  const rows = adult.map((option) => {
    const share = option.is_residual ? residualShare : (shares[option.code] ?? 0);
    return {
      option,
      share,
      patients: diseased * share,
      // A share the analyst moved off the seeded default is their assumption
      // now, and is labelled as one rather than as published evidence.
      isOverridden:
        !option.is_residual
        && option.default_share !== null
        && Math.abs((shares[option.code] ?? 0) - option.default_share) > 1e-9,
    };
  });

  const paediatric = options.find((o) => o.is_disjoint);

  return (
    <div className="subgroups">
      <h3 className="nsec">
        Who these patients are
        <Hint content={GLOSSARY["subgroup.share"]} label="the subgroup split" />
      </h3>
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
            {rows.map(({ option, share, patients, isOverridden }) => (
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
                  ) : isOverridden ? (
                    <span className="derived">your override</span>
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
        Seeded shares are <strong>tier {supplied[0]?.confidence_tier ?? "C"}</strong> and global
        rather than country-specific: {supplied[0]?.source.toLowerCase()}. This split is one of
        the least certain things in the model, and the evidence-priority panel ranks it
        accordingly rather than presenting it as settled. Change any of them in the panel on
        the left, or import your own.
      </p>
    </div>
  );
}
