/**
 * What every field and figure means, in the analyst's language — M21 section 7.
 *
 * Keyed by the same dotted vocabulary the override system already uses, so a
 * field and its explanation cannot drift apart by name.
 *
 * **Where this should eventually live.** M21 section 7 puts the glossary in the
 * backend, so one definition feeds the interface, the PDF, the deck and the
 * exported workbook. It is here for now, which means the exports carry their
 * own wording and the two can diverge. Moving it server-side is a swap of this
 * module's implementation, not of its callers.
 */
import type { HintContent } from "./Hint";

export const GLOSSARY: Record<string, HintContent> = {
  // --- scenario -----------------------------------------------------------
  "asset.name": {
    what: "The therapy whose introduction is being costed.",
    affects: "nothing on its own — it labels the run and its exports.",
  },
  "scenario.indication": {
    what: "The disease this model covers. One disease, split into subgroups below.",
    affects: "which population, comparators and outcome evidence are in scope.",
  },
  "scenario.launch_year": {
    what: "The calendar year the therapy becomes available. Year 1 of the model.",
    affects: "every year label, and which pipeline competitors have entered by then.",
  },
  "scenario.horizon_years": {
    what: "How many years the payer is being asked to look ahead.",
    affects: "the cumulative impact, and how much weight late-year uptake carries.",
    watchFor: "budget impact is a 3–5 year instrument. Longer needs a different model.",
  },
  "scenario.reporting_currency": {
    what: "The currency cross-market totals are shown in.",
    affects: "presentation only. Each market is calculated in its own currency and "
      + "converted at the rate snapshotted into this run.",
  },
  "scenario.markets": {
    what: "The countries in scope. Each one gets its own funnel, prices and result.",
    affects: "everything — population, prices and affordability are all per market.",
  },

  // --- funnel -------------------------------------------------------------
  "funnel.diagnosis_rate": {
    what: "The share of people with the disease whose condition has actually been "
      + "diagnosed and recorded by a clinician.",
    affects: "every stage below it, and therefore the number of patients treated.",
    watchFor: "undiagnosed people cannot be prescribed to. A rate near 100% usually "
      + "means the figure is prevalence, not diagnosed prevalence.",
  },
  "funnel.treatment_rate": {
    what: "The share of diagnosed patients who are actively on some treatment today.",
    affects: "the treated population, and so the cost the new therapy displaces.",
  },
  "funnel.access_rate": {
    what: "The share of label-eligible patients who can actually obtain the therapy "
      + "under the assumed reimbursement position.",
    affects: "the addressable population — the last narrowing before uptake applies.",
    watchFor: "this is formulary and reimbursement reality, not clinical eligibility.",
  },
  "funnel.diseased": {
    what: "Adults in this market who have the disease, from published prevalence.",
    affects: "the whole funnel beneath it, and the subgroup split.",
  },

  // --- uptake -------------------------------------------------------------
  "uptake.year_1": {
    what: "The share of addressable patients on the new therapy in its launch year.",
    affects: "first-year budget impact, which is often the only year a payer commits to.",
  },
  "uptake.terminal": {
    what: "The share reached by the final year of the horizon — peak adoption.",
    affects: "the shape of the curve and the cumulative impact.",
  },

  // --- subgroups ----------------------------------------------------------
  "subgroup.share": {
    what: "The share of adults with obesity whose most serious qualifying condition "
      + "is this one.",
    affects: "how many patients sit in each group, and eventually what each group costs.",
    watchFor: "not raw comorbidity prevalence. Someone with obesity, diabetes and high "
      + "blood pressure is counted once, in the most serious group they qualify for — "
      + "adding the three published prevalences would count them three times.",
  },
  "subgroup.residual": {
    what: "Everyone with obesity and none of the listed conditions. Derived as 100% "
      + "minus the four above, never entered directly.",
    affects: "nothing you can set — it moves when the four above move.",
  },

  // --- outputs ------------------------------------------------------------
  "result.budget_impact": {
    what: "The extra money the payer spends because the therapy exists: what they "
      + "spend with it, minus what they would have spent without it.",
    affects: "this is the headline the whole model produces.",
    watchFor: "it is not the cost of the new therapy. Most of that cost replaces "
      + "spending that was happening anyway.",
  },
  "result.cost_without": {
    what: "What the payer spends on this population in a year if the therapy never "
      + "launches — current care, continuing as it is.",
  },
  "result.cost_with": {
    what: "What the payer spends on the same population once the therapy launches: "
      + "the patients who switch, plus everyone still on current care.",
  },
  "result.addressable": {
    what: "Patients who could be treated — diagnosed, eligible, and with access. "
      + "Not everyone who has the disease.",
  },
  "result.patients_on_new": {
    what: "Patients actually on the new therapy that year, after uptake and after "
      + "allowing for those who stop taking it.",
    watchFor: "lower than uptake alone suggests, because people discontinue.",
  },
  "result.net_cost_per_switch": {
    what: "What one patient moving onto the new therapy costs the payer, after "
      + "subtracting the therapy they came off.",
    watchFor: "this is the incremental figure per patient, not the therapy's price.",
  },
  "result.affordability": {
    what: "The budget impact as a share of what this country spends on health "
      + "altogether.",
    watchFor: "measured against the whole health budget, not the drug budget, so it "
      + "understates the pressure on a pharmacy line specifically.",
  },
  "result.cumulative": {
    what: "Every year of the horizon added together — the total extra spend the payer "
      + "is being asked to absorb.",
  },
};
